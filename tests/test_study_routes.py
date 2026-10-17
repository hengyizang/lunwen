"""Type-specific evidence and adversarial controls; no paid model calls."""
from __future__ import annotations

import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import artifact_ownership, cloud_checkpoint, cloud_job, experiment_runner as runner
from scripts import meta_analysis_runtime as meta, research_quality as quality, study_route_acceptance as fixtures, study_routes
from scripts import supplemental_experiments as supplemental, researchctl, cloud_human_controls, reviewer_rounds
from scripts.research_artifacts import read, sha, write


class StudyRouteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "demo"
        self.env = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}); self.env.start(); self.addCleanup(self.env.stop)

    def fixture(self, kind="meta_analysis"):
        return fixtures.make_study(self.project, kind)

    def change(self, relative, callback):
        path = self.project / relative; value = read(path); callback(value); write(path, value)
        plan = read(self.project / "experiments/plan.json")
        for run in plan["runs"]:
            for item in run["inputs"]:
                if item["path"] == relative:
                    item["sha256"] = sha(path)
        write(self.project / "experiments/plan.json", plan)

    def test_meta_preregistration_has_real_sources_without_empirical_power(self):
        self.fixture()
        self.assertEqual(study_routes.plan_errors(self.project, "P01"), [])
        self.assertEqual(quality.validate_g3_quality(self.project, require_preregistration=False), [])
        frozen = quality.create_preregistration(self.project, "P01", "Synthetic reviewer")
        paths = {i["path"] for i in frozen["files"]}
        self.assertIn("evidence/extraction.json", paths)
        self.assertIn("analysis/runtime/P01/runtime.py", paths)
        self.assertNotIn("papers/P01/power-analysis.json", paths)

    def test_theory_requires_no_fabricated_dataset_or_power(self):
        self.fixture("theory")
        self.assertEqual(study_routes.plan_errors(self.project, "P01"), [])
        frozen = quality.create_preregistration(self.project, "P01", "Synthetic reviewer")
        self.assertIn("analysis/proof.lean", {i["path"] for i in frozen["files"]})
        self.assertNotIn("papers/P01/power-analysis.json", {i["path"] for i in frozen["files"]})
        self.assertTrue(any(i["path"] == "analysis/proof.lean" for i in cloud_checkpoint.inventory(self.project)))

    def test_missing_independent_extraction_is_blocked(self):
        self.fixture(); self.change("evidence/extraction.json", lambda v: v["records"][0].update(independent_extractions=[v["records"][0]["independent_extractions"][0]]))
        self.assertIn("two separately attributed", " ".join(study_routes.plan_errors(self.project, "P01")))

    def test_contract_flag_cannot_override_actual_identity(self):
        self.fixture(); self.change("papers/P01/paper-contract.json", lambda v: v.update(study_route="empirical"))
        self.assertIn("study_route", " ".join(study_routes.plan_errors(self.project, "P01")))

    def test_dependent_cohorts_are_not_independent_studies(self):
        self.fixture(); self.change("evidence/extraction.json", lambda v: v["records"][1].update(cohort_id=v["records"][0]["cohort_id"]))
        self.assertIn("dependent", " ".join(study_routes.plan_errors(self.project, "P01")))

    def test_unreported_exclusion_is_blocked(self):
        self.fixture(); self.change("evidence/selection.json", lambda v: v["records"].pop())
        self.assertIn("screen every retrieved", " ".join(study_routes.plan_errors(self.project, "P01")))

    def test_scale_mixing_is_blocked(self):
        self.fixture(); self.change("evidence/extraction.json", lambda v: v["records"][0].update(effect_measure="log_odds_ratio"))
        self.assertIn("scales", " ".join(study_routes.plan_errors(self.project, "P01")))

    def test_source_tampering_blocks_freeze(self):
        self.fixture(); (self.project / "evidence/study-1.txt").write_text("Changed source", encoding="utf-8")
        with self.assertRaises(ValueError):
            quality.create_preregistration(self.project, "P01", "Synthetic reviewer")

    def test_proof_needs_nonvacuity_and_scope_obligations(self):
        self.fixture("theory"); self.change("papers/P01/study-protocol.json", lambda v: v["theorems"].pop())
        self.assertIn("assumption witness", " ".join(study_routes.plan_errors(self.project, "P01")))

    def test_cyclic_proof_dependencies_are_blocked(self):
        self.fixture("theory")
        def cycle(v):
            v["theorems"][0]["depends_on"] = [v["theorems"][1]["declaration"]]
            v["theorems"][1]["depends_on"] = [v["theorems"][0]["declaration"]]
        self.change("papers/P01/study-protocol.json", cycle)
        self.assertIn("cyclic", " ".join(study_routes.plan_errors(self.project, "P01")))

    def test_postfreeze_protocol_change_blocks_execution(self):
        self.fixture(); fixtures.freeze(self.project)
        self.change("papers/P01/study-protocol.json", lambda v: v.update(question="Changed after inspecting an outcome."))
        with self.assertRaises(runner.ExperimentError):
            runner.approved_plan(self.project, self.project / "experiments/plan.json", self.project / "experiments/budget.json")

    def test_mutable_analysis_receipt_does_not_rewrite_study_identity_lock(self):
        self.fixture(); fixtures.freeze(self.project)
        path = self.project / "papers/P01/research-identity.json"; value = read(path)
        value["analysis_evidence"] = [{"attempt_id": "later", "path": "results/original.json", "sha256": "0" * 64}]
        write(path, value)
        self.assertEqual(quality.validate_preregistration(read(self.project / "papers/P01/preregistration.json"), "P01", self.project), [])
        value["methods"] = ["changed_method"]; write(path, value)
        self.assertIn("identity", " ".join(study_routes.plan_errors(self.project, "P01")))

    def test_model_authored_success_cannot_replace_executor_evidence(self):
        self.fixture(); fixtures.freeze(self.project)
        write(self.project / "papers/P01/experiment-evidence.json", {"status": "complete", "errors": []})
        self.assertNotEqual(study_routes.build_report(self.project, "P01")["status"], "complete")

    def test_child_state_registry_and_frozen_sources_are_protected(self):
        prefix = "experiments/supplemental/P01/R001/s001/"
        for relative in ("state/run.json", "experiments/registry.jsonl", "data/quality/a-confirmation.json", "results/result.json"):
            self.assertTrue(artifact_ownership.executor_owned(self.project, prefix + relative), relative)
        self.assertFalse(artifact_ownership.executor_owned(self.project, prefix + "papers/P01/study-protocol.json"))

    def test_scientific_confirmation_is_nonbillable_and_paper_specific(self):
        for action in ("confirm_study_validation", "approve_supplemental", "confirm_supplemental"):
            value = {"schema_version": "1.0", "action": action, "project": "demo", "actor": "Synthetic reviewer", "allow_paid": False,
                     "paper_id": "P01", "expected_sha256": "a" * 64, "note": "Review the actual bound evidence."}
            self.assertEqual(cloud_job.validate_request(value)["action"], action)
            value["allow_paid"] = True
            with self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request(value)

    def test_nonfinite_compute_estimates_and_budget_are_rejected(self):
        self.fixture(); plan = read(self.project / "experiments/plan.json"); plan["runs"][0]["estimated_cost_usd"] = math.nan
        self.assertTrue(runner.validate_plan(plan))
        with self.assertRaises(runner.ExperimentError):
            runner.budget_ceiling({"status": "ready_for_review", "hard_ceiling_usd": math.inf})


class MetaNumericalTests(unittest.TestCase):
    def test_pm_matches_independently_recorded_r_metafor_golden_result(self):
        # Numeric facts from statsmodels' BSD-3 test fixture results_meta.py at
        # b6b382183676557763bd12ce561b61e1f08c9258, exk1_metafor (R method PM).
        result = meta.pool([61, 61.4, 62.21, 62.3, 62.34, 62.6, 62.7, 62.84, 65.9],
                           [.2025, 1.21, .09, .2025, .3844, .5625, .0676, .0225, 1.8225])
        self.assertAlmostEqual(result["estimate"], 62.4076199113286, places=8)
        self.assertAlmostEqual(result["tau_squared"], .705395309224248, places=8)
        self.assertAlmostEqual(result["q"], 24.801897741835, places=8)
    def test_equal_effects_match_closed_form_with_conservative_t_interval(self):
        result = meta.pool([.2, .2, .2], [.04, .04, .04])
        self.assertAlmostEqual(result["estimate"], .2, places=12)
        self.assertAlmostEqual(result["tau_squared"], 0, places=12)
        self.assertAlmostEqual(result["se"], math.sqrt(.04 / 3), places=12)
        from scipy.stats import t
        self.assertAlmostEqual(result["ci_high"], .2 + t.ppf(.975, 2) * math.sqrt(.04 / 3), places=12)

    def test_invalid_variance_cannot_produce_a_pooled_result(self):
        for bad in (0, -1, math.nan, math.inf):
            with self.subTest(variance=bad), self.assertRaises(ValueError):
                meta.pool([.1, .2], [.1, bad])

    def test_null_outcome_and_all_sensitivities_are_retained(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(directory) / "demo"; protocol = fixtures.make_study(project, "meta_analysis")
            result = meta.calculate(protocol, read(project / "evidence/extraction.json"))
            outcome = result["outcomes"][0]
            self.assertEqual(outcome["decision"], "does_not_establish_claim")
            self.assertEqual(len(outcome["sensitivity"]["leave_one_out"]), 4)
            self.assertIsNotNone(outcome["sensitivity"]["exclude_high_risk"])
            self.assertFalse(outcome["small_study_diagnostic"]["absence_of_bias_verified"])


class SupplementalGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name) / "demo"
        self.env = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}); self.env.start(); self.addCleanup(self.env.stop)
        fixtures.make_study(self.parent, "meta_analysis"); fixtures.freeze(self.parent)
        self.case = fixtures.supplemental_acceptance(self.parent, execute=False)
        self.child = self.case["child"]

    def test_review_request_and_candidate_never_authorize_execution(self):
        with patch("scripts.experiment_runner.execute", side_effect=AssertionError("unapproved execution")):
            result = supplemental.resume(self.parent, "P01")
        self.assertEqual(result["status"], "awaiting_separate_protocol_approval")
        self.assertFalse(result["executed"])

    def test_zero_parent_compute_budget_cannot_be_raised_by_child(self):
        write(self.child / "experiments/budget.json", {"status": "ready_for_review", "hard_ceiling_usd": 1})
        with self.assertRaisesRegex(ValueError, "compute authorization"):
            supplemental.prepare_approval(self.parent, "P01", "Synthetic reviewer")

    def test_changed_original_plan_cannot_be_reused(self):
        path = self.parent / "experiments/plan.json"; value = read(path); value["runs"][0]["seed"] = 42; write(path, value)
        with self.assertRaisesRegex(ValueError, "original approved"):
            supplemental.candidate(self.parent, "P01")

    def test_stale_owner_dossier_cannot_approve_changed_child(self):
        with patch.object(researchctl, "PROJECTS_ROOT", self.parent.parent):
            value = {"schema_version": "1.0", "action": "review_dossier", "operation": "approve_supplemental", "project": "demo",
                     "actor": "Synthetic reviewer", "allow_paid": False, "paper_id": "P01"}
            dossier = cloud_human_controls.dossier(value)
            self.assertEqual(dossier["blockers"], [])
            path = self.child / "papers/P01/study-protocol.json"; protocol = read(path); protocol["question"] += " Changed."; write(path, protocol)
            value.update(action="approve_supplemental", expected_sha256=dossier["review_sha256"], note="Synthetic approval attempt after inputs changed."); value.pop("operation")
            with self.assertRaisesRegex(cloud_human_controls.HumanControlError, "dossier changed"):
                cloud_human_controls.execute(value, "123")

    def test_deleted_scope_control_cannot_hide_approved_history(self):
        supplemental.approve(self.parent, "P01", "Synthetic reviewer", "a" * 64, "123")
        controls = supplemental.controls(self.parent, "P01", "R001")
        controls[0][0].unlink()
        with self.assertRaisesRegex(ValueError, "orphaned"):
            supplemental.controls(self.parent, "P01", "R001")

    def test_failed_attempt_cost_is_not_released(self):
        registry = self.child / "experiments/registry.jsonl"
        registry.parent.mkdir(exist_ok=True)
        registry.write_text(json.dumps({"estimated_cost_usd": .5, "status": "failed"}) + "\n", encoding="utf-8")
        self.assertEqual(supplemental.all_compute_cost(self.parent), .5)

    def test_results_require_execution_and_a_separate_scientific_confirmation(self):
        supplemental.approve(self.parent, "P01", "Synthetic reviewer", "a" * 64, "123")
        errors = supplemental.revision_errors(self.parent, "P01", require_reporting=False)
        self.assertTrue(any("confirmation" in e for e in errors))

    def test_exploratory_followup_cannot_be_relabelled_confirmatory(self):
        path = self.child / "papers/P01/study-protocol.json"; value = read(path)
        value["outcomes"][0]["analysis_phase"] = "confirmatory"; write(path, value)
        with self.assertRaisesRegex(ValueError, "exploratory/prospective phase"):
            supplemental.prepare_approval(self.parent, "P01", "Synthetic reviewer")

    def test_readonly_review_survives_final_approval_and_packaging(self):
        path = self.parent / "state/run.json"; state = read(path)
        for status in ("awaiting_approval", "approved"):
            with self.subTest(status=status):
                state["status"] = status; write(path, state)
                self.assertEqual(supplemental.current(self.parent, "P01", execution=False)[0]["round_id"], "R001")
                with self.assertRaisesRegex(ValueError, "open reviewer"):
                    supplemental.current(self.parent, "P01")
        state.update(gate="G5", active_paper="P02", status="awaiting_work")
        state["paper_statuses"]["P01"] = "submission_ready"; state["approved_gates"].append("G5:P01"); write(path, state)
        self.assertEqual(supplemental.current(self.parent, "P01", execution=False)[0]["round_id"], "R001")
        with self.assertRaisesRegex(ValueError, "open reviewer"):
            supplemental.current(self.parent, "P01")

    def test_g5_binding_changes_when_supplemental_authority_changes(self):
        supplemental.approve(self.parent, "P01", "Synthetic reviewer", "a" * 64, "123")
        before = reviewer_rounds.review_binding(self.parent, "P01")
        control_path, control = supplemental.controls(self.parent, "P01", "R001")[0]
        control["cloud_review_sha256"] = "b" * 64; write(control_path, control)
        after = reviewer_rounds.review_binding(self.parent, "P01")
        self.assertEqual(before["report_sha256"], after["report_sha256"])
        self.assertNotEqual(before, after)

    def test_g5_binding_changes_when_child_reporting_or_attempts_change(self):
        supplemental.approve(self.parent, "P01", "Synthetic reviewer", "a" * 64, "123")
        before = reviewer_rounds.review_binding(self.parent, "P01")
        write(self.child / "papers/P01/statistical-reporting-map.json", {"schema_version": "1.0", "items": []})
        after_mapping = reviewer_rounds.review_binding(self.parent, "P01")
        self.assertNotEqual(before, after_mapping)
        (self.child / "experiments/registry.jsonl").write_text(json.dumps({"status": "failed"}) + "\n", encoding="utf-8")
        self.assertNotEqual(after_mapping, reviewer_rounds.review_binding(self.parent, "P01"))

    def test_g5_binding_does_not_require_reacquiring_raw_inputs(self):
        supplemental.approve(self.parent, "P01", "Synthetic reviewer", "a" * 64, "123")
        raw = self.child / "data/raw/synthetic.txt"; raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("Synthetic rehydratable input, never real participant data.", encoding="utf-8")
        frozen_path = self.child / "papers/P01/preregistration.json"; frozen = read(frozen_path)
        # Exercise the inventory contract with a registered raw-input entry.
        # G3 authority itself is separately verified by checked_child/G4.
        frozen["files"].append({"path": "data/raw/synthetic.txt", "sha256": sha(raw)})
        write(frozen_path, frozen)
        before = reviewer_rounds.review_binding(self.parent, "P01")
        raw.unlink()
        self.assertEqual(before, reviewer_rounds.review_binding(self.parent, "P01"))
        frozen["files"][-1]["sha256"] = "0" * 64; write(frozen_path, frozen)
        self.assertNotEqual(before, reviewer_rounds.review_binding(self.parent, "P01"))


if __name__ == "__main__":
    unittest.main()
