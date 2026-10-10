"""Cloud tests for byte-bound CLI logs without weakening protected state."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator, autopilot


AUDIT = {"verdict": "pass-with-conditions", "fatal_findings": [], "major_findings": [],
         "minor_findings": [], "missing_evidence": [], "remediation_steps": [], "uncertainty": []}


class Process:
    pid = 123456789

    def __init__(self, outcome=0):
        self.outcome = outcome

    def wait(self, timeout=None):
        if self.outcome == "timeout" and timeout is not None:
            raise subprocess.TimeoutExpired("mock CLI", timeout)
        return self.outcome if isinstance(self.outcome, int) else 0

    def kill(self):
        pass


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        project = root / "projects/demo"
        run = project / "state/runs/current-writing-and-review"
        run.mkdir(parents=True)
        state = {"schema_version": "2.0", "stage_index": 5, "stage": "writing-and-review",
                 "gate": "G5", "active_paper": "P01", "paper_statuses": {"P01": "active"},
                 "status": "awaiting_work", "approvals": []}
        (project / "state/run.json").write_text(json.dumps(state), encoding="utf-8")
        (run / "journal.json").write_text('{"status":"running"}', encoding="utf-8")
        with patch.object(autopilot, "ROOT", root), patch.object(api_orchestrator, "ROOT", root), patch.object(
            autopilot.researchctl, "PROJECTS_ROOT", root / "projects"
        ):
            yield root, project, run, state


def launch_writer(run, *, action=None, outcome=0, message=True, output=b"writer log"):
    def launch(command, **kwargs):
        if outcome == "spawn_error":
            raise OSError("mock CLI could not start")
        kwargs["stdout"].write(output)
        kwargs["stderr"].write(b"bounded diagnostic")
        if message:
            Path(command[command.index("-o") + 1]).write_bytes(b"Writer response")
        if action:
            action()
        return Process(outcome)
    return launch


def call_writer(run, before, name="writer", max_output=4096):
    message = run / f"codex-{name}-last-message.txt"
    return autopilot.invoke_writer("demo", before, name, ["mock-codex", "-o", str(message)],
                                   run, message, 1, max_output)


@unittest.skipUnless(os.open in os.supports_dir_fd, "safe invocation execution requires openat")
class CliInvocationControlsTests(unittest.TestCase):
    def test_run_stage_completes_writer_and_remediation_with_real_control_checks(self):
        with fixture() as (_, project, _, state):
            names = []

            def launch(command, **kwargs):
                if "-o" in command:
                    message = Path(command[command.index("-o") + 1])
                    name = "remediation" if "remediation" in message.name else "writer"
                    notes = [f"rejected: {code} Retained the supported statement after reviewing the current evidence."
                             for code in [*(f"H{i:02d}" for i in range(1, 27)), *(f"AD{i:02d}" for i in range(1, 9))]]
                    message.write_text(json.dumps({"dispositions": notes}) if name == "remediation" else "Writer complete", encoding="utf-8")
                    manuscript = project / "papers/P01/manuscript/main.tex"
                    manuscript.parent.mkdir(parents=True, exist_ok=True)
                    manuscript.write_text(f"The registered {name} comparison preserves every observed outcome.", encoding="utf-8")
                    payload = b"Codex event log"
                else:
                    name = command[-1]
                    payload = json.dumps({"result": json.dumps(AUDIT) if name != "planner" else "Internal research plan."}).encode()
                names.append(name)
                kwargs["stdout"].write(payload)
                return Process()

            with patch.object(autopilot, "load_stage_config", return_value={state["stage"]: {}}), patch.object(
                autopilot, "planner_prompt", return_value="planner"
            ), patch.object(autopilot, "writer_prompt", return_value="writer"), patch.object(
                autopilot, "remediation_prompt", return_value="remediation"
            ), patch.object(autopilot, "critic_prompt", side_effect=["critic", "final-critic"]), patch.object(
                autopilot, "claude_command", side_effect=lambda prompt, *args: ["mock-claude", prompt]
            ), patch.object(autopilot.shutil, "which", return_value="mock-codex"), patch.object(
                autopilot.subprocess, "Popen", side_effect=launch
            ), patch.object(autopilot, "refresh_post_write_evidence", return_value={"controlled_steps": None, "academic_style_audit": None}), patch.object(
                api_orchestrator, "refresh_research_method_audits", return_value=None
            ), patch.object(autopilot.researchctl, "gate_errors", return_value=[]), patch.object(
                autopilot.researchctl, "mark_ready"
            ) as ready:
                journal = autopilot.run_stage("demo", "", "standard", 1, 4096, 3.5)
            self.assertEqual(names, ["planner", "writer", "critic", "remediation", "final-critic"])
            self.assertEqual(journal["status"], "awaiting_human_approval")
            ready.assert_called_once()
            current = json.loads((project / "state/run.json").read_text())
            self.assertEqual(current["approvals"], [])
            self.assertEqual(current["gate"], "G5")
            run = next(path.parent for path in (project / "state/runs").glob("*/writer.json"))
            for name in ("writer", "remediation"):
                for filename in (f"{name}.stdout.txt", f"{name}.stderr.txt", f"{name}.json", f"codex-{name}-last-message.txt"):
                    self.assertTrue((run / filename).is_file(), filename)
            self.assertIn("AD08", (project / "reviews/decision-log.md").read_text())
            self.assertNotIn("captured_outputs", json.dumps(journal))

    def test_truncated_logs_are_bound_to_saved_bytes_not_full_stream_hash(self):
        with fixture() as (_, _, run, _):
            before = autopilot.protected_control_snapshot("demo")
            with patch.object(autopilot.subprocess, "Popen", side_effect=launch_writer(run, output=b"x" * 200)):
                result = call_writer(run, before, max_output=32)
            self.assertEqual(result["status"], "succeeded")
            self.assertTrue(result["stdout_truncated"])
            self.assertEqual((run / "writer.stdout.txt").read_bytes(), b"x" * 32)

    def test_extra_state_and_cleanup_forgery_are_removed_and_fail_the_invocation(self):
        with fixture() as (_, project, run, state):
            before = autopilot.protected_control_snapshot("demo")
            fake = project / "reports/watermark-cleanup/fake/receipt.json"

            def tamper():
                (project / "state/extra.json").write_text("forged")
                (project / "state/run.json").write_text('{"gate":null,"approvals":["model"]}')
                fake.parent.mkdir(parents=True)
                fake.write_text("forged")

            with patch.object(autopilot.subprocess, "Popen", side_effect=launch_writer(run, action=tamper)):
                result = call_writer(run, before)
            self.assertEqual(result["status"], "failed")
            self.assertFalse(fake.exists())
            self.assertFalse((project / "state/extra.json").exists())
            self.assertEqual(json.loads((project / "state/run.json").read_text()), state)
            self.assertTrue((run / "writer.json").is_file())
            self.assertIn("restored", result["error"])

    def test_existing_records_cannot_be_exempted_or_overwritten(self):
        with fixture() as (_, _, run, _):
            path = run / "writer.stdout.txt"
            path.write_bytes(b"original")
            before = autopilot.protected_control_snapshot("demo")
            with patch.object(autopilot.subprocess, "Popen") as process:
                with self.assertRaises(autopilot.AutopilotError):
                    call_writer(run, before)
                process.assert_not_called()
            path.write_bytes(b"forged")
            with self.assertRaises(autopilot.AutopilotError):
                autopilot.ensure_protected_control_unchanged("demo", before,
                    allowed_new_outputs={path.relative_to(autopilot.researchctl.project_dir("demo")).as_posix(): b"forged"})
            self.assertEqual(path.read_bytes(), b"original")

    def test_allowed_bytes_and_original_parent_markers_are_required(self):
        for new_parent in (False, True):
            with self.subTest(new_parent=new_parent), fixture() as (_, project, run, _):
                before = autopilot.protected_control_snapshot("demo")
                target = (run.with_name("unexpected-run") if new_parent else run) / "writer.stdout.txt"
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(b"modified" if not new_parent else b"captured")
                with self.assertRaises(autopilot.AutopilotError):
                    autopilot.ensure_protected_control_unchanged("demo", before,
                        allowed_new_outputs={target.relative_to(project).as_posix(): b"captured"})
                self.assertFalse(target.exists())

    def test_child_log_symlink_is_restored_before_controller_writes(self):
        with fixture() as (root, _, run, _):
            outside = root / "outside.txt"
            outside.write_bytes(b"unchanged sentinel")
            before = autopilot.protected_control_snapshot("demo")
            action = lambda: (run / "writer.stdout.txt").symlink_to(outside)
            with patch.object(autopilot.subprocess, "Popen", side_effect=launch_writer(run, action=action)):
                result = call_writer(run, before)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(outside.read_bytes(), b"unchanged sentinel")
            self.assertFalse((run / "writer.stdout.txt").is_symlink())
            self.assertEqual((run / "writer.stdout.txt").read_bytes(), b"writer log")

    def test_ordinary_invoke_never_writes_through_a_child_created_log_link(self):
        with fixture() as (root, _, run, _):
            outside = root / "outside.txt"
            outside.write_bytes(b"unchanged sentinel")

            def launch(command, **kwargs):
                kwargs["stdout"].write(b"must not reach the sentinel")
                (run / "planner.stdout.txt").symlink_to(outside)
                return Process()

            with patch.object(autopilot.subprocess, "Popen", side_effect=launch):
                with self.assertRaises(OSError):
                    autopilot.invoke("planner", ["mock"], run, 1, 4096)
            self.assertEqual(outside.read_bytes(), b"unchanged sentinel")

    def test_last_message_link_is_rejected_and_removed(self):
        with fixture() as (root, _, run, _):
            outside = root / "outside-message.txt"
            outside.write_bytes(b"unchanged sentinel")
            before = autopilot.protected_control_snapshot("demo")

            def tamper():
                message = run / "codex-writer-last-message.txt"
                message.unlink()
                message.symlink_to(outside)

            with patch.object(autopilot.subprocess, "Popen", side_effect=launch_writer(run, action=tamper)):
                result = call_writer(run, before)
            self.assertEqual(result["status"], "failed")
            self.assertFalse((run / "codex-writer-last-message.txt").exists())
            self.assertEqual(outside.read_bytes(), b"unchanged sentinel")

    def test_run_directory_link_is_restored_without_touching_external_files(self):
        with fixture() as (root, _, run, _):
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "writer.stdout.txt"
            sentinel.write_bytes(b"unchanged sentinel")
            before = autopilot.protected_control_snapshot("demo")

            def tamper():
                run.rename(run.with_name("moved-run"))
                run.symlink_to(outside, target_is_directory=True)

            with patch.object(autopilot.subprocess, "Popen", side_effect=launch_writer(run, action=tamper)):
                result = call_writer(run, before)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(sentinel.read_bytes(), b"unchanged sentinel")
            self.assertTrue(run.is_dir())
            self.assertFalse(run.is_symlink())
            self.assertEqual((run / "journal.json").read_text(), '{"status":"running"}')

    def test_failed_and_timed_out_invocations_keep_only_their_three_controller_logs(self):
        for outcome, expected in ((1, "failed"), ("timeout", "timed_out"), ("spawn_error", "failed")):
            with self.subTest(outcome=outcome), fixture() as (_, project, run, state):
                before = autopilot.protected_control_snapshot("demo")
                with patch.object(autopilot.subprocess, "Popen", side_effect=launch_writer(run, outcome=outcome, message=False)), patch.object(
                    autopilot.os, "killpg"
                ):
                    result = call_writer(run, before)
                self.assertEqual(result["status"], expected)
                for name in ("writer.stdout.txt", "writer.stderr.txt", "writer.json"):
                    self.assertTrue((run / name).is_file())
                self.assertFalse((run / "codex-writer-last-message.txt").exists())
                self.assertEqual(json.loads((project / "state/run.json").read_text()), state)


class UnsupportedInvocationExecutorTests(unittest.TestCase):
    def test_unsupported_directory_api_fails_before_starting_a_process(self):
        with fixture() as (_, _, run, _), patch.object(autopilot.os, "supports_dir_fd", set()), patch.object(
            autopilot.subprocess, "Popen"
        ) as process:
            with self.assertRaisesRegex(autopilot.AutopilotError, "safely open"):
                autopilot.invoke("planner", ["mock"], run, 1, 4096)
            process.assert_not_called()
