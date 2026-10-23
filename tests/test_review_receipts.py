from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator, autopilot, review_receipts, scientific_scope
from scripts.research_artifacts import read, write, record, sha
from tests.review_scope_fixtures import prepare_scope, seal_review


class ReviewReceiptTests(unittest.TestCase):
    def fixture(self, root):
        project = root / "fixture-study"
        state = {"paper_count": 1, "active_paper": "P01", "gate": "G5", "stage": "writing-and-review", "approvals": [], "approved_gates": []}
        write(project / "state/run.json", state)
        paper = project / "papers/P01/manuscript/main.tex"
        paper.parent.mkdir(parents=True)
        paper.write_text("Synthetic fixture manuscript. No scientific result is claimed.", encoding="utf-8")
        source = project / "evidence/source.txt"
        source.parent.mkdir()
        source.write_text("Located synthetic source evidence.", encoding="utf-8")
        prepare_scope(project, state)
        return project, state

    def test_current_same_run_receipts_survive_volatile_bookkeeping(self):
        with tempfile.TemporaryDirectory() as temp:
            project, state = self.fixture(Path(temp))
            seal_review(project, state)
            write(project / "state/cloud-checkpoint.json", {"sequence": 42})
            write(project / "state/runs/fixture/manifest.json", {"new_diagnostics": True})
            (project / "reviews/decision-log.md").write_text("Human-readable synthetic log", encoding="utf-8")
            self.assertEqual(review_receipts.validate_gate(project, "G5", "P01"), [])

    def test_source_or_evidence_change_requires_actual_fresh_review(self):
        for relative in ("papers/P01/manuscript/main.tex", "evidence/source.txt", "program/core-thesis.json"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temp:
                project, state = self.fixture(Path(temp))
                seal_review(project, state)
                path = project / relative
                path.write_text(path.read_text(encoding="utf-8") + "\nChanged source", encoding="utf-8")
                errors = review_receipts.validate_gate(project, "G5", "P01")
                self.assertTrue(any("stale" in error for error in errors))

    def test_latest_actual_receipt_not_lexical_run_name(self):
        with tempfile.TemporaryDirectory() as temp:
            project, state = self.fixture(Path(temp))
            seal_review(project, state, run_id="z-first")
            (project / "evidence/source.txt").write_text("Updated synthetic source", encoding="utf-8")
            seal_review(project, state, run_id="a-actually-later")
            self.assertEqual(review_receipts.validate_gate(project, "G5", "P01"), [])

    def test_missing_or_writer_forged_receipt_cannot_replace_critic(self):
        with tempfile.TemporaryDirectory() as temp:
            project, state = self.fixture(Path(temp))
            self.assertTrue(review_receipts.validate_gate(project, "G5", "P01"))
            seal_review(project, state)
            target = project / "state/review-receipts/G5-P01/fixture-review/final.json"
            value = read(target)
            value["materials"]["sha256"] = "0" * 64
            write(target, value)
            from scripts.output_provenance import record_model_writes
            record_model_writes(project, [target], family="openai", provider="writer", model="fixture", role="writer", run_id="fake")
            self.assertTrue(review_receipts.validate_gate(project, "G5", "P01"))

    def test_gate_revalidates_all_editorial_dispositions_and_matching_phases(self):
        with tempfile.TemporaryDirectory() as temp:
            project, state = self.fixture(Path(temp))
            seal_review(project, state)
            final = project / "state/review-receipts/G5-P01/fixture-review/final.json"
            value = read(final)
            value["dispositions"] = [n for n in value["dispositions"] if "CFH38 " not in n]
            write(final, value)
            pointer = project / "state/review-receipts/G5-P01/latest.json"
            write(pointer, {"path": final.relative_to(project).as_posix(), "sha256": sha(final)})
            record(project, [final, pointer], review_receipts.MODULE)
            self.assertTrue(any("CFH38" in error for error in review_receipts.validate_gate(project, "G5", "P01")))

    def test_receipt_rejects_cached_same_family_mismatched_or_changed_during_call(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project, state = self.fixture(Path(temp))
            audit = project / "reviews/independent/test-initial.json"
            write(audit, {"verdict": "revise", **{k: [] for k in review_receipts.FIELDS - {"verdict"}}})
            identity = {"provider": "fixture", "family": "anthropic", "requested_model": "fixture", "reported_model": "fixture", "completion_status": "completed", "cache_hit": False}
            materials = review_receipts.material_snapshot(project, "writing-and-review", "P01")
            for change in ({"cache_hit": True}, {"family": "openai"}, {"reported_model": "other"}, {"completion_status": "incomplete"}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    review_receipts.seal_phase(project, stage="writing-and-review", run_id="bad", phase="initial", audit_path=audit,
                        prompt="Synthetic prompt", identity={**identity, **change}, writer_family="openai", materials=materials)
            (project / "evidence/source.txt").write_text("Changed during call", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed during"):
                review_receipts.seal_phase(project, stage="writing-and-review", run_id="bad", phase="initial", audit_path=audit,
                    prompt="Synthetic prompt", identity=identity, writer_family="openai", materials=materials)

    def test_complete_api_and_cli_critic_prompts_exclude_raw_requests_preserve_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project, state = self.fixture(root)
            marker = "PREFERRED_VERDICT_SHOULD_NEVER_REACH_CRITIC"
            write(project / "program/cloud-operations.json", {"operations": [{"action": "ccfa_task", "request": {"task": marker}}]})
            write(project / "program/ccfa-request.json", {"skill": "ccf-paper-reviewer", "task": marker})
            write(project / "program/custom-review-invocation.json", {"skill": "ccf-paper-reviewer", "task": marker})
            write(project / "state/research-steps.json", {"ccfa": [{"result": {"request": {"task": marker}}}]})
            with patch.object(api_orchestrator, "project_root", return_value=project):
                for prompt in (api_orchestrator.critic_prompt(project.name, "writing-and-review", ""), autopilot.critic_prompt(project.name, state)):
                    self.assertNotIn(marker, prompt)
                    self.assertIn("Located synthetic source evidence", prompt)
                write(project / "program/context-plan.json", {"schema_version": "1.0", "stages": {"writing-and-review": {
                    "question": "Synthetic independent review", "items": [{"path": "program/custom-review-invocation.json", "reason": "Attempted raw request bypass", "stance": "neutral"}]}}})
                with self.assertRaisesRegex(ValueError, "prior review, or unsupported"):
                    api_orchestrator.critic_prompt(project.name, "writing-and-review", "")

    def test_cli_critic_has_no_tools_and_requires_reported_model_metadata(self):
        with patch("scripts.autopilot.shutil.which", return_value="/synthetic/claude"):
            command = autopilot.claude_command("Synthetic complete packet", "standard", 1, source_packet_only=True)
            self.assertEqual(command[command.index("--tools") + 1], "")
            self.assertNotIn("--allowedTools", command)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "stdout.json"
            write(target, {"result": "synthetic review", "modelUsage": {"claude-fixture": {"inputTokens": 10}}})
            self.assertEqual(review_receipts.cli_identity(target)["reported_model"], "claude-fixture")
            write(target, {"result": "synthetic review"})
            with self.assertRaises(ValueError):
                review_receipts.cli_identity(target)


if __name__ == "__main__":
    unittest.main()
