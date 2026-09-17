from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.dashboard import (
    JobManager,
    SessionConfig,
    build_command,
    project_detail,
    update_config,
)


class DashboardTests(unittest.TestCase):
    def test_project_detail_uses_newest_report_by_modification_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            projects = Path(directory)
            project = projects / "demo"
            data = project / "data"
            data.mkdir(parents=True)
            older = data / "discovery-z-old.json"
            newer = data / "discovery-a-new.json"
            for path, created_at in ((older, "old"), (newer, "new")):
                path.write_text(
                    json.dumps(
                        {
                            "created_at": created_at,
                            "query": "bearing",
                            "providers": [],
                            "candidate_count": 0,
                            "candidates": [],
                        }
                    ),
                    encoding="utf-8",
                )
            os.utime(older, ns=(1_000_000_000, 1_000_000_000))
            os.utime(newer, ns=(2_000_000_000, 2_000_000_000))
            with patch("scripts.dashboard.PROJECTS_ROOT", projects), patch(
                "scripts.dashboard.project_state", return_value={"paper_count": 6}
            ):
                detail = project_detail("demo")
        self.assertEqual(detail["data_reports"][0]["created_at"], "new")

    def test_stage_workspaces_are_ordered_top_to_bottom(self) -> None:
        html = (Path(__file__).resolve().parents[1] / "dashboard" / "index.html").read_text(encoding="utf-8")
        phase_positions = [html.index(f'data-phase-index="{index}"') for index in range(7)]
        self.assertEqual(phase_positions, sorted(phase_positions))
        self.assertLess(html.index('id="dataSearchForm"'), html.index('id="datasetManifest"'))
        self.assertLess(html.index('id="datasetManifest"'), html.index('id="experimentRun"'))
        self.assertLess(html.index('id="experimentRun"'), html.index('id="venuePaper"'))
        self.assertLess(html.index('id="venuePaper"'), html.index('id="packagePaper"'))

    def test_public_configuration_never_contains_api_key(self) -> None:
        config = SessionConfig(api_key="super-secret", base_url="https://gateway.example", anthropic_model="claude", openai_model="gpt")
        public = config.public()
        self.assertTrue(public["key_configured"])
        self.assertNotIn("super-secret", str(public))
        self.assertNotIn("api_key", public)

    def test_configuration_requires_https_and_keeps_blank_key(self) -> None:
        config = SessionConfig(api_key="existing")
        with self.assertRaises(ValueError):
            update_config(config, {"base_url": "http://unsafe.example"})
        update_config(
            config,
            {
                "api_key": "",
                "base_url": "https://gateway.example/v1/",
                "anthropic_model": "claude-model",
                "openai_model": "gpt-model",
                "strict_model_id": True,
            },
        )
        self.assertEqual(config.api_key, "existing")
        self.assertEqual(config.base_url, "https://gateway.example/v1")

    def test_job_log_redacts_session_secrets(self) -> None:
        manager = JobManager(SessionConfig(api_key="secret-token", tavily_key="tavily-secret"))
        value = manager.redact("Authorization: Bearer secret-token api_key=tavily-secret")
        self.assertNotIn("secret-token", value)
        self.assertNotIn("tavily-secret", value)

    def test_queued_job_can_be_cancelled_before_process_start(self) -> None:
        manager = JobManager(SessionConfig())
        for _ in range(3):
            manager.capacity.acquire()
        try:
            job = manager.start(
                "test",
                "queued test",
                [sys.executable, "-c", "raise SystemExit(99)"],
                None,
            )
            manager.cancel(job.job_id)
        finally:
            for _ in range(3):
                manager.capacity.release()
        deadline = time.monotonic() + 2
        while job.status == "queued" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(job.status, "cancelled")
        self.assertIsNone(job.return_code)

    def test_start_command_is_argument_safe_and_role_separated(self) -> None:
        command, label, project = build_command(
            "start",
            {"project": "dashboard-new-test", "context": "No lab; public data only."},
        )
        self.assertEqual(command[:3], ["bash", "scripts/start.sh", "dashboard-new-test"])
        self.assertEqual(command[-1], "No lab; public data only.")
        self.assertEqual(project, "dashboard-new-test")
        self.assertIn("G0", label)

    def test_cycle_uses_default_automatic_data_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dashboard-test").mkdir()
            with patch("scripts.dashboard.PROJECTS_ROOT", root), patch(
                "scripts.dashboard.researchctl.load_state"
            ) as load_state:
                load_state.return_value = {
                    "stage": "topic-intelligence",
                    "gate": "G1",
                    "status": "awaiting_work",
                }
                command, label, project = build_command(
                    "cycle",
                    {
                        "project": "dashboard-test",
                        "context": "Public licensed data only.",
                        "discovery_query": "",
                        "max_output_tokens": 12000,
                    },
                )
        self.assertEqual(project, "dashboard-test")
        self.assertIn("topic-intelligence", label)
        self.assertNotIn("--no-auto-data-discovery", command)

    def test_style_audit_command_is_local_and_paper_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dashboard-test" / "papers" / "P01").mkdir(parents=True)
            with patch("scripts.dashboard.PROJECTS_ROOT", root), patch(
                "scripts.dashboard.researchctl.load_state"
            ) as load_state:
                load_state.return_value = {
                    "stage": "writing-and-review",
                    "gate": "G5",
                    "status": "awaiting_work",
                    "active_paper": "P01",
                }
                command, label, project = build_command(
                    "style_audit",
                    {"project": "dashboard-test", "paper": "P01"},
                )
        self.assertEqual(project, "dashboard-test")
        self.assertEqual(
            command[1:],
            [
                "scripts/academic_style.py",
                "audit",
                "--project",
                "dashboard-test",
                "--paper",
                "P01",
            ],
        )
        self.assertIn("P01", label)

    def test_project_detail_exposes_line_level_style_and_local_tool_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = (
                root
                / "dashboard-test"
                / "papers"
                / "P01"
                / "style"
                / "academic-style-audit.json"
            )
            report_path.parent.mkdir(parents=True)
            report_path.write_text(
                json.dumps(
                    {
                        "status": "revise",
                        "created_at": "2026-09-17T00:00:00+00:00",
                        "errors": ["formulaic wording"],
                        "warnings": [],
                        "detector_score_used": False,
                        "analysis": {
                            "word_count": 1200,
                            "formulaic_pattern_findings": [
                                {
                                    "rule_id": "vague-attribution",
                                    "line": 12,
                                    "message": "The attribution is too vague to audit.",
                                }
                            ],
                        },
                        "external_linters": [
                            {"name": "proselint", "status": "pass", "diagnostic_count": 0},
                            {"name": "harper", "status": "advisory", "diagnostic_count": 2},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch("scripts.dashboard.PROJECTS_ROOT", root), patch(
                "scripts.dashboard.project_state",
                return_value={"paper_count": 1, "paper_statuses": {"P01": "active"}},
            ):
                detail = project_detail("dashboard-test")
        style = detail["style_audits"]["P01"]
        self.assertEqual(style["formulaic_finding_count"], 1)
        self.assertEqual(style["formulaic_findings"][0]["line"], 12)
        self.assertEqual(style["harper_status"], "advisory")

    def test_dashboard_has_style_finding_monitor(self) -> None:
        html = (Path(__file__).resolve().parents[1] / "dashboard" / "index.html").read_text(
            encoding="utf-8"
        )
        javascript = (Path(__file__).resolve().parents[1] / "dashboard" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="styleAuditFindings"', html)
        self.assertIn("formulaic_findings", javascript)
        self.assertIn("harper_status", javascript)

    def test_project_slug_rejects_shell_metacharacters(self) -> None:
        with self.assertRaises(ValueError):
            build_command("start", {"project": "bad;touch-x", "context": "test"})


if __name__ == "__main__":
    unittest.main()
