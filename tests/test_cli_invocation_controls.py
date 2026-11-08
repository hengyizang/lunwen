"""Retired process options fail before initialization or any API request."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from scripts import autopilot


class CliInvocationControlsTests(unittest.TestCase):
    def test_direct_entrypoints_work_without_pythonpath_or_project_cwd(self):
        script = Path(autopilot.__file__).resolve()
        environment = {
            key: value for key, value in os.environ.items() if key != "PYTHONPATH"
        }
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=directory,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("start", result.stdout)
        self.assertIn("resume", result.stdout)
        self.assertIn("plan", result.stdout)
        self.assertIn("retired", result.stdout)

    def test_process_options_are_not_silently_reused_as_token_or_spending_limits(self):
        options = (
            ("--claude-mode", "minimal"),
            ("--timeout", "3600"),
            ("--max-output-bytes", "100"),
            ("--claude-max-budget-usd", "5"),
        )
        for flag, value in options:
            with (
                self.subTest(option=flag),
                patch.object(autopilot.researchctl, "initialize") as initialize,
                patch.object(autopilot.api_orchestrator, "run_cycle") as cycle,
                redirect_stderr(io.StringIO()) as error,
                self.assertRaises(SystemExit) as stopped,
            ):
                autopilot.main(["start", "--project", "new-project", flag, value])
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn(flag, error.getvalue())
            self.assertIn("bytes are not tokens", error.getvalue())
            initialize.assert_not_called()
            cycle.assert_not_called()

    def test_invalid_api_limits_fail_before_creating_a_project(self):
        for control, writer in ((0, 12000), (5000, 4000), (4000, 100001)):
            with (
                self.subTest(control=control, writer=writer),
                patch.object(autopilot.researchctl, "initialize") as initialize,
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                autopilot.main(
                    [
                        "start",
                        "--project",
                        "new-project",
                        "--max-output-tokens",
                        str(writer),
                        "--control-max-output-tokens",
                        str(control),
                    ]
                )
            initialize.assert_not_called()

    def test_retired_python_process_signature_cannot_start_an_api_call(self):
        with patch.object(autopilot.api_orchestrator, "run_cycle") as cycle:
            with self.assertRaises(TypeError):
                autopilot.run_stage("demo", "", "standard", 3600, 100, 5)
        cycle.assert_not_called()

    def test_shell_cli_alias_explicitly_uses_the_api_compatibility_entry(self):
        root = Path(autopilot.__file__).resolve().parents[1]
        script = (root / "scripts/start.sh").read_text()
        self.assertIn("local Claude Code/Codex process backend is retired", script)
        self.assertIn('scripts/autopilot.py start --project "$project_slug"', script)
        self.assertNotIn("claude exec", script)
        self.assertNotIn("codex exec", script)
