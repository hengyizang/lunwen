"""External revision history, genuine source coverage and spending boundaries."""
from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import output_provenance, rebuttal_triage, researchctl, reviewer_rounds as rounds
from scripts.research_artifacts import read, sha, write


class ReviewerRoundTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.projects = Path(temporary.name) / "projects"
        self.project = self.projects / "demo"
        self.paper = self.project / "papers/P01"
        self.source = "evidence/reviewer-intake/P01/intake.json"
        self.cloud = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"})
        self.cloud.start()
        self.addCleanup(self.cloud.stop)
        project_patch = patch.object(researchctl, "PROJECTS_ROOT", self.projects)
        project_patch.start()
        self.addCleanup(project_patch.stop)
        self.put("papers/P01/manuscript/main.tex", "\\documentclass{article}\n\\begin{document}\n\\section{Methods}\nThe protocol uses a fixed split.\n\\end{document}\n")
        write(self.paper / "paper-contract.json", {"paper_id": "P01"})
        write(self.project / "state/run.json", {"schema_version": "2.0", "project": "demo", "stage_index": 6,
            "stage": "submission-ready", "gate": None, "status": "submission_ready", "active_paper": "P01",
            "paper_count": 1, "paper_statuses": {"P01": "submission_ready"}, "approved_gates": ["G3", "G4", "G5:P01"],
            "approvals": [{"gate": "G3", "actor": "Author", "experiment_plan_sha256": "old-approved-plan"}], "history": []})
        self.intake()
        self.approve_fixture()

    def put(self, relative, content):
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        output_provenance.record_model_writes(self.project, [target], family="openai", provider="synthetic-fixture",
            model="fixture", role="writer", run_id="fixture")
        return target

    def intake(self, *, experiments=False, kind="external", comment="Clarify the fixed split."):
        original = self.put("evidence/reviewer-intake/P01/reviewer.txt", "Reviewer 1\n" + comment + "\n")
        receipt = self.put("evidence/reviewer-intake/P01/submission.txt", "Synthetic fixture only: manuscript DEMO-1 received.\n")
        value = {"schema_version": "1.0", "paper_id": "P01", "review_type": kind, "journal": "Fixture Journal",
            "manuscript_id": "DEMO-1", "submitted_at": "2026-01-01T00:00:00Z",
            "submission_receipt": {"path": receipt.relative_to(self.project).as_posix(), "sha256": sha(receipt),
                "locator": "receipt line 1", "quote": "manuscript DEMO-1 received"},
            "reviewer_source": {"path": original.relative_to(self.project).as_posix(), "sha256": sha(original)},
            "needs_new_experiments": experiments,
            "comments": [{"comment_id": "R1-C1", "reviewer_id": "Reviewer 1", "comment": comment,
                "source_location": {"start_line": 2, "end_line": 2}}]}
        write(self.project / self.source, value)
        return value

    def approve_fixture(self):
        state = read(self.project / "state/run.json")
        state["paper_statuses"]["P01"] = "submission_ready"
        state.update(stage_index=6, stage="submission-ready", gate=None, status="submission_ready")
        if "G5:P01" not in state["approved_gates"]:
            state["approved_gates"].append("G5:P01")
        state["approvals"].append({"gate": "G5", "paper_id": "P01", "actor": "Fixture Author",
            "paper_artifact_sha256": researchctl.paper_artifact_hash("demo", "P01")})
        write(self.project / "state/run.json", state)

    def start(self):
        return rounds.start_revision(self.project, "P01", self.source, "Fixture Author", "a" * 64, "123")

    def response(self):
        answer = "We clarified the fixed split in Methods; the protocol itself is unchanged."
        evidence = self.put("evidence/fixed-split.md", "The registered protocol specifies the fixed split.\n")
        write(self.paper / "reviews/reviewer-response.json", {"schema_version": "1.0", "round_id": "R001",
            "responses": [{"comment_id": "R1-C1", "response": answer, "evidence": [
                {"path": evidence.relative_to(self.project).as_posix(), "sha256": sha(evidence),
                 "locator": "protocol evidence line 1", "quote": "registered protocol specifies the fixed split"}]}]})
        self.put("papers/P01/submission-materials/response-letter.md", "# Response to reviewers\n\n## R1-C1\n\n" + answer + "\n")
        card = {"comment_id": "R1-C1", "stance": "clarify", "impact": "minor", "underlying_concern": "split definition",
            "action": "clarify existing protocol", "evidence_status": "registered", "full_response": answer,
            "short_response": answer, "manuscript_location": "Methods", "effort": "small"}
        cards = {"venue_word_limit": 500, "editor_summary": "The fixed split is now explicit.", "cards": [card]}
        write(self.paper / "reviews/concern-cards.json", cards)
        original = read(self.paper / "reviews/original-comments.json")
        coverage = rebuttal_triage.triage(original, cards)
        for key, filename in (("full_text", "internal-full.md"), ("short_text", "submitted-short.md"), ("editor_summary", "editor-summary.md")):
            self.put("papers/P01/reviews/concern-response/" + filename, coverage.pop(key))
        coverage.update(original_sha256=sha(self.paper / "reviews/original-comments.json"), cards_sha256=sha(self.paper / "reviews/concern-cards.json"))
        write(self.paper / "reviews/concern-response/coverage.json", coverage)
        matrix = self.paper / "reviews/response-matrix.csv"
        with matrix.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["comment_id", "commitment_id", "fulfillment_status", "location", "revised_text", "unfulfilled_rationale"])
            writer.writeheader()
            writer.writerow({"comment_id": "R1-C1", "commitment_id": "C1", "fulfillment_status": "fulfilled",
                "location": "Methods", "revised_text": "The protocol uses a fixed split.", "unfulfilled_rationale": ""})
        output_provenance.record_model_writes(self.project, [self.paper / "reviews/reviewer-response.json",
            self.paper / "reviews/concern-cards.json", matrix], family="openai", provider="synthetic-fixture",
            model="fixture", role="writer", run_id="fixture")

    def test_preview_is_pure_and_binds_real_sources(self):
        before = (self.project / "state/run.json").read_bytes()
        result = rounds.prepare_start(self.project, "P01", self.source, "Fixture Author")
        self.assertEqual(result["round_id"], "R001")
        self.assertEqual(result["comment_ids"], ["R1-C1"])
        self.assertEqual((self.project / "state/run.json").read_bytes(), before)
        self.assertFalse((self.project / rounds.PREFIX).exists())
        self.assertEqual(result["limits"]["paid_calls"], 0)

    def test_start_archives_prior_submission_and_reopens_only_selected_paper(self):
        prior = read(self.project / "state/run.json")
        with patch("scripts.model_runtime.call", side_effect=AssertionError("paid calls forbidden")):
            result = self.start()
        state = read(self.project / "state/run.json")
        self.assertEqual(state["gate"], "G5")
        self.assertEqual(state["status"], "awaiting_work")
        self.assertNotIn("G5:P01", state["approved_gates"])
        self.assertEqual(state["approvals"], prior["approvals"])
        frozen = self.project / Path(result["manifest"]["path"]).parent
        self.assertEqual(read(frozen / "prior-state.json"), prior)
        self.assertEqual((frozen / "paper/manuscript/main.tex").read_bytes(), (self.paper / "manuscript/main.tex").read_bytes())
        self.assertEqual((self.paper / "reviews/revision-base/main.tex").read_bytes(), (self.paper / "manuscript/main.tex").read_bytes())
        self.assertEqual(result["audit_status"], "revise")

    def test_complete_text_response_has_current_coverage_and_exact_source_locations(self):
        self.start()
        self.response()
        report = rounds.refresh(self.project, "P01")
        self.assertEqual(report["status"], "pass", report["errors"])
        self.assertEqual(rounds.validate_saved_report(self.project, "P01"), [])
        self.assertEqual(report["checks"][0]["comment_id"], "R1-C1")
        self.assertFalse(report["scientific_completion_verified"])

    def test_frozen_original_tampering_is_rejected(self):
        self.start()
        frozen = self.project / f"{rounds.PREFIX}/P01/R001/original-reviewer-source.txt"
        frozen.write_text("Forged reviewer opinion", encoding="utf-8")
        self.assertIn("immutable", " ".join(rounds.validate_saved_report(self.project, "P01")))

    def test_missing_response_and_simulated_substitution_cannot_pass(self):
        self.start()
        self.response()
        working = self.paper / "reviews/original-comments.json"
        value = read(working)
        value["review_type"] = "simulated"
        write(working, value)
        self.assertIn("immutable external source", " ".join(rounds.refresh(self.project, "P01")["errors"]))

    def test_new_experiments_remain_blocked_without_mutating_original_g3(self):
        self.intake(experiments=True)
        original_g3 = read(self.project / "state/run.json")["approvals"][0]
        self.start()
        self.response()
        report = rounds.refresh(self.project, "P01")
        self.assertEqual(report["status"], "revise")
        self.assertIn("separately approved supplemental protocol", " ".join(report["errors"]))
        self.assertEqual(read(self.project / "state/run.json")["approvals"][0], original_g3)
        self.assertEqual(report["experiments_executed"], 0)
        self.assertIn("reviewer-required-experiment-plan.json", rounds.prompt_feedback(self.project, "P01")["experiment_proposal"])

    def test_wrong_source_locations_or_stale_receipt_fail_before_mutation(self):
        value = read(self.project / self.source)
        value["comments"][0]["source_location"]["start_line"] = 1
        value["comments"][0]["source_location"]["end_line"] = 1
        write(self.project / self.source, value)
        with self.assertRaisesRegex(ValueError, "absent"):
            self.start()
        self.intake()
        self.put("evidence/reviewer-intake/P01/submission.txt", "Changed receipt")
        with self.assertRaisesRegex(ValueError, "source quote"):
            self.start()
        self.assertFalse((self.project / rounds.PREFIX).exists())

    def test_non_external_intake_and_duplicate_ids_are_rejected(self):
        self.intake(kind="simulated")
        with self.assertRaisesRegex(ValueError, "external"):
            self.start()
        value = self.intake()
        value["comments"].append(value["comments"][0])
        write(self.project / self.source, value)
        with self.assertRaisesRegex(ValueError, "unique"):
            self.start()

    def test_stale_scientific_version_cannot_be_presented_as_original_submission(self):
        self.put("papers/P01/manuscript/main.tex", "Changed after the human G5 approval")
        with self.assertRaisesRegex(ValueError, "changed since prior G5"):
            self.start()

    def test_source_tampering_after_response_invalidates_saved_audit(self):
        self.start()
        self.response()
        rounds.refresh(self.project, "P01")
        self.put("evidence/fixed-split.md", "The registered evidence changed.")
        self.assertTrue(rounds.validate_saved_report(self.project, "P01"))

    def test_second_round_requires_new_human_g5_and_chains_previous_round(self):
        first = self.start()
        with self.assertRaisesRegex(ValueError, "completed its human G5"):
            self.start()
        self.response()
        rounds.refresh(self.project, "P01")
        self.approve_fixture()
        self.intake(comment="Clarify the protocol again.")
        second = self.start()
        self.assertEqual(second["round_id"], "R002")
        manifest = read(self.project / second["manifest"]["path"])
        self.assertEqual(manifest["previous_round"], first["manifest"])
        self.assertEqual(read(self.project / first["manifest"]["path"])["comment_ids"], ["R1-C1"])

    def test_cross_paper_selection_only_from_completed_portfolio(self):
        state = read(self.project / "state/run.json")
        state["active_paper"] = "P06"
        state["paper_statuses"]["P06"] = "submission_ready"
        write(self.project / "state/run.json", state)
        self.start()
        self.assertEqual(read(self.project / "state/run.json")["active_paper"], "P01")
        self.assertEqual(read(self.project / "state/run.json")["history"][-1]["previous_active_paper"], "P06")

    def test_other_active_work_and_local_mutations_are_rejected(self):
        state = read(self.project / "state/run.json")
        state.update(stage_index=5, stage="writing-and-review", gate="G5", active_paper="P02")
        write(self.project / "state/run.json", state)
        with self.assertRaisesRegex(ValueError, "unfinished"):
            self.start()
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(ValueError, "cloud executor"):
                self.start()

    def test_letter_mismatch_and_omitted_matrix_comment_cannot_pass(self):
        self.start()
        self.response()
        self.put("papers/P01/submission-materials/response-letter.md", "# Incomplete reply\n")
        self.assertIn("exact response", " ".join(rounds.refresh(self.project, "P01")["errors"]))
        self.response()
        matrix = self.paper / "reviews/response-matrix.csv"
        matrix.write_text(matrix.read_text(encoding="utf-8").replace("R1-C1", "SIMULATED-C1"), encoding="utf-8")
        self.assertIn("exactly the real external", " ".join(rounds.refresh(self.project, "P01")["errors"]))

    def test_claude_reply_cannot_be_promoted_to_final_response(self):
        self.start()
        self.response()
        response = self.paper / "submission-materials/response-letter.md"
        output_provenance.record_model_writes(self.project, [response], family="anthropic", provider="synthetic-fixture",
            model="fixture", role="writer", run_id="fixture")
        self.assertIn("anthropic", " ".join(rounds.refresh(self.project, "P01")["errors"]))

    def test_intake_must_identify_the_selected_paper(self):
        value = read(self.project / self.source)
        value["paper_id"] = "P02"
        write(self.project / self.source, value)
        with self.assertRaisesRegex(ValueError, "paper_id"):
            self.start()

    def test_response_cannot_be_placed_under_a_different_comment_heading(self):
        self.start()
        self.response()
        path = self.paper / "submission-materials/response-letter.md"
        path.write_text(path.read_text(encoding="utf-8").replace("## R1-C1\n", "## R1-C1\n\n## UNRELATED\n"), encoding="utf-8")
        self.assertTrue(rounds.refresh(self.project, "P01")["errors"])

    def test_owner_start_is_hash_bound_nonpaid_and_preserves_budget(self):
        from scripts import cloud_human_controls as controls, cloud_job
        budget = self.project / "state/model-spend-control.json"
        write(budget, {"synthetic": True, "authorized_ceiling_cny": 300, "spent_cny": 50})
        before = budget.read_bytes()
        common = {"schema_version": "1.0", "project": "demo", "actor": "Fixture Author", "allow_paid": False,
                  "paper_id": "P01", "source": self.source}
        request = cloud_job.validate_request({**common, "action": "review_dossier", "operation": "start_revision"})
        dossier = controls.dossier(request)
        self.assertTrue(dossier["ready_for_operation"], dossier["blockers"])
        job = cloud_job.validate_request({**common, "action": "start_revision", "expected_sha256": dossier["review_sha256"],
                                         "note": "I reviewed the actual synthetic comments and archived version."})
        with self.assertRaisesRegex(controls.HumanControlError, "changed"):
            controls.execute({**job, "expected_sha256": "0" * 64}, "123")
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.validate_request({**job, "allow_paid": True})
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid calls")):
            result = controls.execute(job, "123")
        self.assertEqual(result["state_after"]["gate"], "G5")
        self.assertEqual(result["paid_calls"], 0)
        self.assertEqual(budget.read_bytes(), before)
        fence = chr(96) * 3
        event = {"action": "opened", "repository": {"full_name": cloud_job.REPOSITORY, "owner": {"id": cloud_job.OWNER_ID}},
                 "issue": {"user": {"id": 42}, "title": "[research-cloud] reviewer round",
                           "body": cloud_job.MARKER + "\n" + fence + "json\n" + json.dumps(job) + "\n" + fence}}
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(event)

    def test_unused_feature_is_optional_but_orphan_archive_is_not_ignored(self):
        self.assertEqual(rounds.validate_saved_report(self.project, "P01"), [])
        directory = self.project / f"{rounds.PREFIX}/P01/R001"
        directory.mkdir(parents=True)
        self.assertIn("orphaned", " ".join(rounds.validate_saved_report(self.project, "P01")))


if __name__ == "__main__":
    unittest.main()
