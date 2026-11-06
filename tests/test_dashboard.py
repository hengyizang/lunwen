from __future__ import annotations

import json
import io
import os
import sys
import tempfile
import time
import unittest
import types
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.dashboard import (
    JobManager,
    SessionConfig,
    build_command,
    project_detail,
    project_state,
    update_config,
)


class DashboardTests(unittest.TestCase):
    def test_repeated_screening_checks_are_grouped_without_hiding_other_blockers(self):
        errors = [f"search-log record {index} requires a recorded screening decision" for index in range(118)]
        errors.extend(["Missing experiment source", "Dataset license remains unknown"])
        state = {"stage": "topic-intelligence", "gate": "G1", "status": "awaiting_work"}
        with patch("scripts.dashboard.researchctl.load_state", return_value=state), patch(
                "scripts.dashboard.researchctl.gate_errors", return_value=errors):
            result = project_state("demo")
        self.assertFalse(result["gate_ready"])
        self.assertEqual(result["gate_error_count"], 120)
        self.assertEqual(result["gate_errors"], errors)
        groups = result["gate_error_groups"]
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[0]["id"], "literature_screening")
        self.assertEqual(groups[0]["count"], 118)
        self.assertEqual(groups[0]["checks"], errors[:118])
        self.assertTrue(all(group["next_action"] for group in groups))
        self.assertEqual([check for group in groups for check in group["checks"]], errors)

    def test_identical_checks_keep_occurrence_count_and_unknown_causes_stay_separate(self):
        from scripts.researchctl import summarize_gate_errors
        errors = ["Missing evidence A", "Missing evidence A", "Missing evidence B"]
        groups = summarize_gate_errors(errors)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["count"], 2)
        self.assertEqual(groups[0]["checks"], ["Missing evidence A"])
        self.assertNotEqual(groups[0]["id"], groups[1]["id"])

    def test_grouping_never_turns_an_invalid_state_into_a_ready_gate(self):
        with patch("scripts.dashboard.researchctl.load_state", side_effect=ValueError("Broken state")):
            result = project_state("demo")
        self.assertEqual(result["status"], "invalid")
        self.assertFalse(result["gate_ready"])
        self.assertEqual(result["gate_error_groups"][0]["checks"], ["Broken state"])

    def test_cli_status_summarizes_checks_and_json_retains_every_original(self):
        from scripts import researchctl
        state = {"project": "demo", "stage": "topic-intelligence", "gate": "G1", "status": "awaiting_work"}
        errors = [f"record {index} requires a recorded screening decision" for index in range(3)]
        errors.append("Unknown research issue")
        with patch.object(researchctl, "load_state", return_value=state), patch.object(researchctl, "gate_errors", return_value=errors):
            output = io.StringIO()
            with redirect_stdout(output):
                researchctl.print_status(types.SimpleNamespace(project="demo", json=False))
            self.assertIn("3 check messages", output.getvalue())
            self.assertIn("Unknown research issue", output.getvalue())
            self.assertNotIn("record 2", output.getvalue())
            output = io.StringIO()
            with redirect_stdout(output):
                researchctl.print_status(types.SimpleNamespace(project="demo", json=True))
            result = json.loads(output.getvalue())
            self.assertEqual(result["gate_errors"], errors)
            self.assertFalse(result["gate_ready"])

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
        self.assertEqual(detail["metrics"]["model_cost_cny"], 0.0)
        self.assertEqual(
            detail["metrics"]["model_budget_remaining_cny"],
            detail["metrics"]["model_budget_cny"],
        )

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

    def test_dashboard_exposes_research_quality_controls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        html = (root / "dashboard" / "index.html").read_text(encoding="utf-8")
        javascript = (root / "dashboard" / "app.js").read_text(encoding="utf-8")
        for element in (
            'id="researchQualitySummary"',
            'id="runDataQuality"',
            'id="confirmDataQuality"',
            'id="runPower"',
            'id="freezePreregistration"',
            'id="confirmReproduction"',
            'id="runLiteratureSearch"',
            'id="screenLiterature"',
            'id="buildVenueCandidates"',
        ):
            self.assertIn(element, html)
        self.assertIn("renderResearchQuality", javascript)

    def test_power_command_is_argument_safe_and_paper_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dashboard-test" / "papers" / "P01").mkdir(parents=True)
            with patch("scripts.dashboard.PROJECTS_ROOT", root), patch(
                "scripts.dashboard.researchctl.load_state", return_value={"gate": "G3"}
            ):
                command, label, project = build_command(
                    "power_analysis",
                    {
                        "project": "dashboard-test",
                        "paper": "P01",
                        "method": "ttest_ind",
                        "effect_size": 0.5,
                        "effect_size_basis": "Prior registered study DOI 10.1000/example.",
                        "alpha": 0.05,
                        "power": 0.8,
                        "ratio": 1,
                    },
                )
        self.assertEqual(project, "dashboard-test")
        self.assertIn("scripts/research_quality.py", command)
        self.assertIn("P01", command)
        self.assertIn("统计功效", label)

    def test_literature_search_command_uses_fixed_provider_and_argument_array(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dashboard-test").mkdir()
            with patch("scripts.dashboard.PROJECTS_ROOT", root), patch(
                "scripts.dashboard.researchctl.load_state", return_value={"gate": "G1"}
            ):
                command, _label, project = build_command(
                    "literature_search",
                    {
                        "project": "dashboard-test",
                        "provider": "openalex",
                        "query": "auditable predictive maintenance",
                        "query_family": "core-method",
                        "date_range": "2021-2026",
                        "filters": "journal papers",
                        "limit": 25,
                    },
                )
        self.assertEqual(project, "dashboard-test")
        self.assertIn("scripts/literature_evidence.py", command)
        self.assertEqual(command[command.index("--provider") + 1], "openalex")

    def test_data_quality_check_uses_machine_record_without_human_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dashboard-test").mkdir()
            with patch("scripts.dashboard.PROJECTS_ROOT", root), patch(
                "scripts.dashboard.researchctl.load_state", return_value={"gate": "G3"}
            ):
                command, _label, project = build_command(
                    "confirm_data_quality",
                    {
                        "project": "dashboard-test",
                        "dataset_id": "bearing-v1",
                        "actor": "Researcher Name",
                    },
                )
        self.assertEqual(project, "dashboard-test")
        self.assertIn("scripts/automated_quality.py", command)
        self.assertNotIn("Researcher Name", command)

    def test_paper_topic_approval_passes_exact_paper_selector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"dashboard-test").mkdir()
            with patch("scripts.dashboard.PROJECTS_ROOT",root), patch("scripts.dashboard.researchctl.load_state",return_value={"gate":"G2"}):
                command,_,_=build_command("approve",{"project":"dashboard-test","actor":"Owner","paper":"P02","note":"Selected topic"})
                self.assertEqual(command[command.index("--paper")+1],"P02")
                with self.assertRaises(ValueError):
                    build_command("approve",{"project":"dashboard-test","actor":"Owner","note":"Missing paper"})

    def test_project_slug_rejects_shell_metacharacters(self) -> None:
        with self.assertRaises(ValueError):
            build_command("start", {"project": "bad;touch-x", "context": "test"})


if __name__ == "__main__":
    unittest.main()
