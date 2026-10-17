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


if __name__ == "__main__":
    unittest.main()
