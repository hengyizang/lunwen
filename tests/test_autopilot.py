from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock

from scripts import autopilot


class AutopilotTests(unittest.TestCase):
    @mock.patch("scripts.autopilot.shutil.which", return_value="/usr/bin/claude")
    def test_claude_command_is_noninteractive_bounded_and_redacted(self, _which) -> None:
        prompt = "You are the authoring orchestrator " + "x" * 600
        command = autopilot.claude_command(prompt, "standard", 3.5)
        self.assertIn("-p", command)
        self.assertIn("--max-budget-usd", command)
        self.assertIn("3.5", command)
        self.assertIn("Bash(python3 scripts/researchctl.py gate-check *)", command)
        self.assertNotIn("Bash(python3 scripts/researchctl.py approve *)", command)
        self.assertNotIn(prompt, autopilot.public_command(command))
        self.assertNotIn("--bare", command)

    @mock.patch("scripts.autopilot.shutil.which", return_value="/usr/bin/codex")
    def test_codex_critic_is_read_only_and_schema_bound(self, _which) -> None:
        command = autopilot.codex_command("Act as an independent adversarial critic", Path("out"))
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn("--output-schema", command)
        self.assertIn("--ephemeral", command)

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


if __name__ == "__main__":
    unittest.main()
