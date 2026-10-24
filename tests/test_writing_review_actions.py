"""Cloud-run synthetic review tasks; no extra calls, ledger or scientific approval."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ccfa_science as science, output_provenance, writing_review_actions as actions
from scripts.research_artifacts import sha, write


class WritingReviewActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        cloud = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1", "GITHUB_ACTIONS": "true"})
        cloud.start(); self.addCleanup(cloud.stop)
        self.old = self.text("papers/P01/manuscript/old.md", "# Results\nThe method is better.\n")
        self.current = self.text("papers/P01/manuscript/current.md", "# Results\nThe mechanism needs a matched comparison.\n")
        self.material = self.text("evidence/comparison.md", "# Comparison material\nThe protocol compares the same held-out devices.\n")
        self.text("claims/claim-evidence.csv", "claim_id,paper_id,claim\nC1,P01,Transfer under drift\nC2,P02,Separate claim\n")

    def track(self, target):
        output_provenance.record_model_writes(self.project, [target], family="openai", provider="synthetic", model="fixture", role="writer", run_id="writing-action-fixture")
        return {"path": target.relative_to(self.project).as_posix(), "sha256": sha(target)}

    def text(self, relative, value):
        target = self.project/relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8")
        return self.track(target)

    def anchor(self, binding=None):
        binding = binding or self.current
        return {**binding, "locator": "L2", "excerpt": (self.project/binding["path"]).read_text(encoding="utf-8").splitlines()[1]}

    def action(self):
        return {"categories": ["missing_evidence", "unclear_contribution_comparison"],
            "scope": {"paper_ids": ["P01"], "claim_ids": ["C1"], "sections": ["Results"], "boundary": "Only the matched-device comparison supporting C1."},
            "locations": [self.anchor()],
            "required_materials": [{"id": "matched-comparison", "kind": "analysis", "description": "Matched-device analysis and uncertainty supporting C1.",
                "status": "missing", "reason": "The registered analysis output is not yet available.", "sources": []}],
            "action": "Replace the generic evaluation with the matched comparison and its uncertainty after reviewing the actual analysis.",
            "completion_conditions": ["The matched comparison is linked to C1 at the stated location.", "An independent review checks the comparison and inference boundary."]}

    def review(self, action=True):
        issue = {"id": "I1", "first_seen_version": "v1", "status": "unresolved", "origin": "previously_undetected", "applies_to": "both",
            "dimensions": ["comparison"], "severity": "major", "finding": "The comparison supporting the claimed contribution is missing.",
            "evidence": [self.anchor(self.old), self.anchor()], "resolution": "Provide the matched comparison before interpreting the contribution."}
        if action:
            issue["writing_action"] = self.action()
        return {"historical": self.old, "current": self.current, "scope": "Results comparison only",
            "criteria": [{"id": "comparison", "criterion": "Compare the mechanism against the relevant baseline.", "scope": "Results"}],
            "readiness_criteria": [{"id": "source", "criterion": "The source supporting the comparison is checked.", "scope": "Current Results"}],
            "issues": [issue], "readiness": [{"criterion_id": "source", "status": "satisfied", "rationale": "Located text exists; material adequacy still needs review.", "evidence": [self.anchor()]}]}

    def execute(self, data, previous=None):
        source = self.project/"program/ccfa-inputs/writing-review.json"
        write(source, {"schema_version": "1.0", "operation": "internal_review", "id": "writing-review", "doctoral_question": "When does calibration transfer?", "paper_ids": ["P01"], "data": data})
        binding = self.track(source)
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid call")):
            return science.execute(self.project, "internal_review", {"schema_version": "1.0", "id": "writing-review", "source": binding["path"],
                "expected_source_sha256": binding["sha256"], "expected_previous_sha256": previous})

    def test_legacy_issue_is_explicitly_not_assessed_and_status_is_preserved(self):
        report = self.execute(self.review(action=False))["report"]["result"]
        issue = report["issues"][0]
        self.assertEqual(issue["status"], "unresolved")
        self.assertEqual(issue["writing_action"]["status"], "not_assessed")
        self.assertFalse(issue["semantic_resolution_verified"])

    def test_missing_materials_remain_pending_even_if_model_declares_issue_resolved(self):
        data = self.review(); data["issues"][0]["status"] = "resolved"
        result = self.execute(data)["report"]["result"]
        issue = result["issues"][0]
        self.assertEqual(issue["status"], "resolved")
        self.assertEqual(issue["writing_action"]["status"], "pending_materials")
        self.assertEqual(issue["writing_action"]["missing_material_ids"], ["matched-comparison"])
        self.assertEqual(result["current_readiness"], "revise")
        self.assertFalse(issue["writing_action"]["completion_conditions_verified"])
        self.assertFalse((self.project/"state/run.json").exists())

    def test_supplied_materials_await_independent_review_and_are_bound_in_existing_report(self):
        data = self.review(); task = data["issues"][0]["writing_action"]
        task["required_materials"][0].update(status="supplied_pending_review", reason="A located comparison record is supplied for assessment.", sources=[self.anchor(self.material)])
        result = self.execute(data)
        issue = result["report"]["result"]["issues"][0]
        self.assertEqual(issue["writing_action"]["status"], "answered_pending_review")
        self.assertFalse(issue["writing_action"]["scientific_resolution_verified"])
        self.assertEqual(issue["writing_action"]["paid_calls"], 0)
        self.assertTrue(any(row["path"] == self.material["path"] for row in result["report"]["inputs"]))
        self.assertEqual(science.current(self.project, "internal_review", "writing-review"), result["report"])
        self.text(self.material["path"], "# Changed comparison\nA different cohort was used.\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            science.current(self.project, "internal_review", "writing-review")

    def test_fabricated_quote_wrong_locator_and_cross_paper_claim_are_refused(self):
        for mutate in (lambda task: task["locations"][0].update(excerpt="Invented statement"),
                       lambda task: task["locations"][0].update(locator="L99"),
                       lambda task: task["scope"].update(claim_ids=["C2"]),
                       lambda task: task["scope"].update(claim_ids=["C-missing"])):
            task = self.action(); mutate(task)
            with self.assertRaises(ValueError):
                actions.assess(self.project, task, paper_ids=["P01"])

    def test_scientific_categories_need_actual_claims_but_editorial_only_is_explicit(self):
        task = self.action(); task["scope"]["claim_ids"] = []
        with self.assertRaisesRegex(ValueError, "actual claim IDs"):
            actions.assess(self.project, task)
        task["categories"] = ["empty_evaluation"]
        result = actions.assess(self.project, task)
        self.assertEqual(result["claim_scope"], "editorial_only")
        self.assertEqual(result["status"], "pending_materials")

    def test_early_stage_claim_matrix_works_with_initialized_header_only_csv(self):
        self.text("claims/claim-evidence.csv", "claim_id,paper_id,claim\n")
        write(self.project/"program/novelty-claim-matrix.json", {"claims": [{"claim_id": "C1", "paper_ids": ["P01"], "claim": "A proposed mechanism."}]})
        result = actions.assess(self.project, self.action())
        self.assertEqual(result["status"], "pending_materials")
        self.assertTrue(any(row["path"] == "program/novelty-claim-matrix.json" for row in result["inputs"]))

    def test_verified_flags_and_material_states_cannot_be_self_assigned(self):
        for mutate in (lambda task: task.update(status="verified_resolved"),
                       lambda task: task.update(scientific_resolution_verified=True),
                       lambda task: task["required_materials"][0].update(status="verified")):
            task = self.action(); mutate(task)
            with self.assertRaises(ValueError):
                actions.assess(self.project, task)

    def test_material_supplied_and_not_applicable_need_real_sources(self):
        for status in ("supplied_pending_review", "not_applicable"):
            task = self.action(); task["required_materials"][0]["status"] = status
            with self.subTest(status=status), self.assertRaises(ValueError):
                actions.assess(self.project, task)
        task = self.action(); task["required_materials"][0]["sources"] = [self.anchor(self.material)]
        with self.assertRaisesRegex(ValueError, "Missing material"):
            actions.assess(self.project, task)

    def test_every_supported_material_kind_uses_the_same_pending_contract(self):
        task = self.action()
        original = task["required_materials"][0]
        task["required_materials"] = [{**copy.deepcopy(original), "id": kind, "kind": kind} for kind in sorted(actions.MATERIAL_KINDS)]
        result = actions.assess(self.project, task)
        self.assertEqual(len(result["missing_material_ids"]), 6)
        self.assertEqual(result["status"], "pending_materials")

    def test_material_history_and_stable_ids_survive_a_supply_update(self):
        task = self.action(); before = actions.assess(self.project, task)
        task["required_materials"][0].update(status="supplied_pending_review", sources=[self.anchor(self.material)], reason="Current comparison material supplied.")
        task["revision_reason"] = "The requested comparison record became available; adequacy is still unverified."
        after = actions.assess(self.project, task, previous=before)
        self.assertEqual(after["revision"], 2)
        self.assertEqual(after["history"][0]["definition"], before["definition"])
        self.assertEqual(after["history"][0]["status"], "pending_materials")
        self.assertEqual(after["status"], "answered_pending_review")
        self.assertEqual(actions.assess(self.project, task, previous=after), after)

    def test_inherited_task_cannot_disappear_drop_material_or_change_scope(self):
        before = actions.assess(self.project, self.action())
        with self.assertRaisesRegex(ValueError, "Do not remove"):
            actions.assess(self.project, None, previous=before)
        for mutate in (lambda task: task.update(required_materials=[]),
                       lambda task: task["required_materials"][0].update(id="replacement-id"),
                       lambda task: task["required_materials"][0].update(description="A different missing requirement."),
                       lambda task: task["scope"].update(boundary="A different scientific comparison."),
                       lambda task: task.update(categories=["inference_gap"])):
            task = self.action(); mutate(task); task["revision_reason"] = "A proposed change still cannot erase the original issue definition."
            with self.assertRaises(ValueError):
                actions.assess(self.project, task, previous=before)

    def test_inherited_change_needs_a_reason_and_ccfa_keeps_existing_issue_history(self):
        data = self.review(); first = self.execute(data)
        task = data["issues"][0]["writing_action"]
        task["required_materials"][0].update(status="supplied_pending_review", sources=[self.anchor(self.material)], reason="Located material now supplied.")
        data["issues"][0]["origin"] = "inherited"
        with self.assertRaisesRegex(ValueError, "reason for changing"):
            self.execute(data, previous=first["sha256"])
        task["revision_reason"] = "The comparison material is now supplied, pending the independent scientific check."
        second = self.execute(data, previous=first["sha256"])
        issue = second["report"]["result"]["issues"][0]
        self.assertEqual(issue["id"], "I1")
        self.assertEqual(issue["first_seen_version"], "v1")
        self.assertEqual(issue["status"], "unresolved")
        self.assertEqual(len(issue["writing_action"]["history"]), 1)
        self.assertIsNotNone(second["report"]["previous"])
        self.assertTrue((self.project/second["report"]["previous"]["path"]).is_file())

    def test_classification_location_material_and_completion_fields_are_all_required(self):
        for field in ("categories", "scope", "locations", "required_materials", "action", "completion_conditions"):
            task = self.action(); del task[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                actions.assess(self.project, task)

    def test_inherited_missing_materials_cannot_be_hidden_by_historical_applicability(self):
        data = self.review(); first = self.execute(data)
        data["issues"][0].update(origin="inherited", applies_to="historical", status="resolved")
        with self.assertRaisesRegex(ValueError, "applicability stable"):
            self.execute(data, previous=first["sha256"])

    def test_legacy_applicability_behavior_remains_compatible(self):
        data = self.review(action=False); first = self.execute(data)
        data["issues"][0].update(origin="inherited", applies_to="historical")
        result = self.execute(data, previous=first["sha256"])["report"]["result"]
        self.assertEqual(result["issues"][0]["applies_to"], "historical")
        self.assertEqual(result["issues"][0]["writing_action"]["status"], "not_assessed")


if __name__ == "__main__":
    unittest.main()
