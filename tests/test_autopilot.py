from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock

from scripts import autopilot


class AutopilotTests(unittest.TestCase):
    @mock.patch("scripts.autopilot.shutil.which", return_value="/usr/bin/claude")
    def test_claude_command_is_read_only_bounded_and_redacted(self, _which) -> None:
        prompt = "You are Claude " + "x" * 600
        command = autopilot.claude_command(prompt, "standard", 3.5)
        self.assertIn("-p", command)
        self.assertIn("--max-budget-usd", command)
        self.assertIn("3.5", command)
        self.assertIn("Bash(python3 scripts/researchctl.py gate-check *)", command)
        self.assertNotIn("Bash(python3 scripts/researchctl.py approve *)", command)
        tools = command[command.index("--tools") + 1]
        self.assertNotIn("Write", tools)
        self.assertNotIn("Edit", tools)
        self.assertNotIn(prompt, autopilot.public_command(command))
        self.assertNotIn("--bare", command)

    @mock.patch("scripts.autopilot.shutil.which", return_value="/usr/bin/codex")
    def test_codex_writer_has_workspace_write_without_audit_schema(self, _which) -> None:
        command = autopilot.codex_writer_command(
            "Act as the non-Claude persistent artifact writer", Path("out")
        )
        self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
        self.assertNotIn("--output-schema", command)
        self.assertIn("--ephemeral", command)

    def test_claude_audit_wrapper_is_schema_checked(self) -> None:
        audit = {
            "verdict": "revise",
            "fatal_findings": [],
            "major_findings": ["missing evidence"],
            "minor_findings": [],
            "missing_evidence": [],
            "remediation_steps": ["add evidence"],
            "uncertainty": [],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "stdout.json"
            target = root / "audit.json"
            source.write_text(json.dumps({"result": json.dumps(audit)}), encoding="utf-8")
            autopilot.copy_claude_audit(source, target)
            self.assertEqual(json.loads(target.read_text()), audit)

    def test_author_cannot_change_gate_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            old_root = autopilot.researchctl.PROJECTS_ROOT
            autopilot.researchctl.PROJECTS_ROOT = Path(temp) / "projects"
            try:
                state_path = autopilot.researchctl.state_path("test-phd")
                state_path.parent.mkdir(parents=True)
                original = {"stage": "intake", "gate": "G0", "approvals": []}
                state_path.write_text(json.dumps(original), encoding="utf-8")
                state_path.write_text(
                    json.dumps({**original, "approvals": [{"actor": "model"}]}),
                    encoding="utf-8",
                )
                with self.assertRaises(autopilot.AutopilotError):
                    autopilot.ensure_run_state_unchanged("test-phd", original)
                self.assertEqual(json.loads(state_path.read_text()), original)
            finally:
                autopilot.researchctl.PROJECTS_ROOT = old_root

    def test_codex_cannot_modify_claude_plan_or_control_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            old_root = autopilot.researchctl.PROJECTS_ROOT
            autopilot.researchctl.PROJECTS_ROOT = Path(temp) / "projects"
            try:
                project = autopilot.researchctl.project_dir("test-phd")
                plan = project / "state" / "runs" / "run-1" / "planner.stdout.txt"
                plan.parent.mkdir(parents=True)
                (project / "state" / "run.json").write_text("{}", encoding="utf-8")
                (project / "state" / "output-provenance.json").write_text(
                    '{"schema_version":"1.0","files":{}}', encoding="utf-8"
                )
                plan.write_text("original Claude plan", encoding="utf-8")
                before = autopilot.protected_control_snapshot("test-phd", [plan])
                plan.write_text("tampered", encoding="utf-8")
                with self.assertRaises(autopilot.AutopilotError):
                    autopilot.ensure_protected_control_unchanged(
                        "test-phd", before
                    )
                self.assertEqual(plan.read_text(), "original Claude plan")
            finally:
                autopilot.researchctl.PROJECTS_ROOT = old_root


if __name__ == "__main__":
    unittest.main()
