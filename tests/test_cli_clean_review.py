"""CLI review orchestration with synthetic invocations and real sealed receipts."""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import api_orchestrator, autopilot, output_provenance, review_receipts
from scripts.research_notebook import cycle_review
from scripts.research_artifacts import read, write
from tests.research_cycle_fixtures import pending_decision


class CLICleanReviewTests(unittest.TestCase):
    def run_clean_cycle(self, stage="topic-intelligence", gate="G1", index=1, writer_notes=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        project = root / "projects/demo"
        state = {"schema_version": "2.0", "stage_index": index, "stage": stage, "gate": gate,
                 "status": "awaiting_work", "active_paper": "P01", "paper_count": 1,
                 "paper_statuses": {"P01": "active"}, "approved_gates": [], "approvals": []}
        write(project / "state/run.json", state)
        write(project / "papers/P01/paper-contract.json", {"paper_id": "P01", "writing_phase": "scientific"})
        target = project / "program/scientific-notes.txt"
        target.parent.mkdir(parents=True)
        audit = {"verdict": "pass-with-conditions", "fatal_findings": [], "major_findings": [],
                 "minor_findings": [], "missing_evidence": [], "remediation_steps": [],
                 "uncertainty": ["Synthetic software fixture; scientific validity is not established."]}
        calls = []
        token = "clean-review-fixture"

        def invoke(name, command, run_dir, timeout, max_output, **kwargs):
            calls.append(name)
            self.assertIn(name, {"planner", "critic", "final-critic"})
            payload = {"result": json.dumps(audit) if name != "planner" else "Synthetic read-only plan.",
                       "model": "claude-software-fixture", "session_id": name + "-fixture"}
            write(run_dir / (name + ".stdout.txt"), payload)
            return {"name": name, "status": "succeeded", "exit_code": 0}

        def invoke_writer(slug, protected, name, command, run_dir, last_message, timeout, max_output):
            calls.append(name)
            self.assertEqual(name, "writer", "A clean initial review must not schedule remediation")
            target.write_text("Bounded independent evidence interpretation remains provisional.\n", encoding="utf-8")
            pending_decision(project, stage, token, "P01" if gate in {"G3", "G4", "G5"} else None)
            write(last_message, {"dispositions": writer_notes or []})
            return {"name": name, "status": "succeeded", "exit_code": 0}

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1",
                "ANTHROPIC_MODEL": "claude-software-fixture", "CLAUDE_MODEL": "claude-software-fixture"}))
            stack.enter_context(patch.object(autopilot, "ROOT", root))
            stack.enter_context(patch.object(api_orchestrator, "ROOT", root))
            stack.enter_context(patch.object(autopilot.researchctl, "PROJECTS_ROOT", root / "projects"))
            stack.enter_context(patch.object(autopilot, "load_stage_config", return_value={stage: {"gate": gate}}))
            stack.enter_context(patch.object(autopilot, "run_token", return_value=token))
            stack.enter_context(patch("scripts.scientific_scope.validate", return_value=[]))
            stack.enter_context(patch("scripts.cloud_research_steps.before_cycle", return_value={"control_only": False, "blockers": []}))
            stack.enter_context(patch.object(autopilot, "planner_prompt", return_value="Synthetic planner packet"))
            stack.enter_context(patch.object(autopilot, "writer_prompt", return_value="Synthetic writer packet"))
            stack.enter_context(patch.object(autopilot, "critic_prompt", side_effect=["Independent initial packet", "Fresh independent final packet"]))
            stack.enter_context(patch.object(autopilot, "claude_command", side_effect=lambda prompt, *args, **kwargs: ["synthetic-claude", prompt]))
            stack.enter_context(patch.object(autopilot, "codex_writer_command", side_effect=lambda prompt, path: ["synthetic-codex", prompt]))
            stack.enter_context(patch.object(autopilot, "invoke", side_effect=invoke))
            stack.enter_context(patch.object(autopilot, "invoke_writer", side_effect=invoke_writer))
            stack.enter_context(patch.object(autopilot, "refresh_post_write_evidence", return_value={"academic_style_audit": {}, "controlled_steps": {}}))
            stack.enter_context(patch.object(api_orchestrator, "refresh_research_method_audits", return_value={}))
            stack.enter_context(patch.object(autopilot.researchctl, "gate_errors", return_value=["Actual scientific stage remains unaccepted."]))
            # A clean review alone cannot complete a scientific gate in this test.
            stack.enter_context(patch("scripts.model_runtime.call", side_effect=AssertionError("No paid model calls")))
            result = autopilot.run_stage("demo", "", "standard", 1, 10000, 0)

        self.assertEqual(calls, ["planner", "writer", "critic", "final-critic"])
        self.assertEqual([row["name"] for row in result["runs"]], calls)
        self.assertEqual(result["status"], "needs_work")
        self.assertEqual(result["remediation"]["status"], "not_required")
        self.assertFalse(result["remediation"]["model_call_made"])
        run_dir = project / "state/runs" / result["run_id"]
        self.assertFalse((run_dir / "codex-remediation-last-message.txt").exists())
        self.assertFalse((run_dir / "remediation.stdout.txt").exists())
        key = gate + ("-P01" if gate == "G5" else "")
        receipt_root = project / review_receipts.PREFIX / key / token
        initial, final = read(receipt_root / "initial.json"), read(receipt_root / "final.json")
        self.assertEqual((initial["phase"], final["phase"]), ("initial", "final"))
        self.assertEqual(initial["run_id"], final["run_id"])
        self.assertNotEqual(initial["prompt_sha256"], final["prompt_sha256"])
        self.assertEqual(final["dispositions"], writer_notes or [])
        self.assertEqual(initial["identity"]["request_id"], "critic-fixture")
        self.assertEqual(final["identity"]["request_id"], "final-critic-fixture")
        self.assertFalse(final["identity"]["cache_hit"])
        self.assertFalse(final["scientific_completion_verified"])
        decision = cycle_review(project, stage, token)
        self.assertEqual(decision["decisions"][0]["outcome"], "pending")
        self.assertFalse(decision["scientific_completion_verified"])
        log = (project / "reviews/decision-log.md").read_text(encoding="utf-8")
        self.assertIn("Initial independent audit", log)
        self.assertIn("Final independent audit", log)
        for note in writer_notes or ["no actionable findings"]:
            self.assertIn(note, log)
        self.assertEqual(output_provenance.current_origin(project, target)["family"], "openai")
        self.assertEqual(read(project / "state/run.json"), state)
        return project, result, final

    def test_clean_initial_review_skips_cli_remediation_and_keeps_fresh_final_review(self):
        project, _, _ = self.run_clean_cycle()
        self.assertEqual(review_receipts.validate_gate(project, "G1"), [])

    def test_plain_uncertainty_notes_survive_both_fresh_cli_reviews_without_remediation(self):
        notes = ["The scientific interpretation remains provisional."]
        project, _, final = self.run_clean_cycle(writer_notes=notes)
        self.assertEqual(final["dispositions"], notes)
        self.assertEqual(review_receipts.validate_gate(project, "G1"), [])

    def test_scientific_writing_clean_review_skips_editorial_matrix_and_keeps_both_audits(self):
        project, _, final = self.run_clean_cycle("writing-and-review", "G5", 5)
        self.assertEqual(final["dispositions"], [])
        self.assertEqual(final["materials"]["review_purpose"], "scientific_writing")
        self.assertEqual(review_receipts.validate_gate(project, "G5", "P01", expected_purpose="scientific_writing"), [])
        self.assertEqual(read(project / "papers/P01/paper-contract.json")["writing_phase"], "scientific")
        self.assertFalse((project / "papers/P01/submission").exists())
        state = read(project / "state/run.json")
        state["writing_phases"] = {"P01": "submission"}
        write(project / "state/run.json", state)
        self.assertTrue(review_receipts.validate_gate(project, "G5", "P01"),
                        "A scientific-writing audit cannot stand in for the submission review")


if __name__ == "__main__":
    unittest.main()
