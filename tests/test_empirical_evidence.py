"""Empirical adapters compose with native coverage, freezes and decisions.

All data, plans and sealed receipts are synthetic engineering fixtures. No test
receipt authorizes a real study or establishes causal identification.
"""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import empirical_design, empirical_reporting, empirical_runtime, empirical_workflow
from scripts import experiment_evidence as evidence, experiment_evidence_acceptance as acceptance
from scripts.research_artifacts import read, sha, write
from tests import test_empirical_design as design_fixtures
from tests.figure_lineage_fixtures import sealed_run

NUMERIC = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("scipy") is not None
REFERENCE = importlib.util.find_spec("statsmodels") is not None


class EmpiricalEvidencePlanTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.project = Path(temp.name) / "synthetic"
        self.protocol = acceptance.fixture(self.project)
        self.comp = self.protocol["comparisons"][0]
        self.original_comparison = copy.deepcopy(self.comp)
        self.comp.update(analysis_mode="empirical_estimator", empirical_specification_id="spec-main",
            unit_design="model", pairs=[], aggregation="model_based_on_declared_units", minimum_effect=0,
            unit_column="unit", value_column="outcome",
            registered_result={"run_id": "proposed-11", "output": "papers/P01/results/empirical.json", "method_id": "did_2x2"})
        self.card = {"paper_id": "P01", "dataset_id": "synthetic-only", "sample": {"unit_column": "unit"},
            "specifications": [{"id": "spec-main", "run_id": "proposed-11", "output": "papers/P01/results/empirical.json",
                "method": "did_2x2", "family": self.comp["family"], "phase": "confirmatory", "claim_ids": ["C1"],
                "outcome": "outcome", "confidence_level": 1 - .05 / 7}]}
        plan = read(self.project / "experiments/plan.json")
        next(row for row in plan["runs"] if row["run_id"] == "proposed-11")["expected_outputs"].append("papers/P01/results/empirical.json")
        write(self.project / "experiments/plan.json", plan)
        power = read(self.project / "papers/P01/power-analysis.json")
        power["method"] = "monte_carlo_simulation"
        write(self.project / "papers/P01/power-analysis.json", power)
        self.check = patch("scripts.empirical_design.audit", return_value={"errors": [], "status": "ready_for_scientific_review"})
        self.check.start(); self.addCleanup(self.check.stop)
        self.save()

    def save(self):
        write(self.project / "papers/P01/empirical-design.json", self.card)
        write(self.project / "papers/P01" / evidence.PLAN, self.protocol)

    def errors(self):
        self.save()
        return "; ".join(evidence.validate_plan(self.project, "P01"))

    def test_model_mode_reuses_existing_coverage_without_inventing_arms(self):
        self.assertEqual(self.errors(), "")
        self.assertEqual(self.comp["pairs"], [])
        self.assertEqual(self.comp["unit_design"], "model")

    def test_schema_exposes_explicit_estimator_identity_and_model_unit(self):
        schema = read(Path(evidence.__file__).resolve().parents[1] / "schemas/experiment-evidence-plan.schema.json")
        props = schema["properties"]["comparisons"]["items"]["properties"]
        self.assertIn("empirical_estimator", props["analysis_mode"]["enum"])
        self.assertIn("model", props["unit_design"]["enum"])
        self.assertIn("empirical_specification_id", props)

    def test_removing_the_last_native_comparison_does_not_disable_registered_spec_coverage(self):
        self.comp.clear()
        self.comp.update(self.original_comparison)
        self.assertIn("every registered empirical specification", self.errors())

    def test_specification_identity_and_exact_run_output_method_are_required(self):
        self.comp["empirical_specification_id"] = "invented"
        self.assertIn("actual empirical specification", self.errors())
        self.comp["empirical_specification_id"] = "spec-main"
        self.comp["registered_result"]["method_id"] = "different-method"
        self.assertIn("binding differs", self.errors())

    def test_claim_family_phase_and_dataset_must_match_actual_design(self):
        spec = self.card["specifications"][0]
        for key, wrong in (("claim_ids", ["C2"]), ("family", "another-family"), ("phase", "exploratory")):
            before = spec[key]; spec[key] = wrong
            self.assertIn("claim/family/phase/dataset differs", self.errors())
            spec[key] = before
        self.card["dataset_id"] = "different-data"
        self.assertIn("claim/family/phase/dataset differs", self.errors())

    def test_model_mode_cannot_supply_paired_rows_or_seed_averaging(self):
        self.comp["pairs"] = [{"seed": 11, "treatment": {}, "comparator": {}}]
        self.assertIn("must not invent paired arms", self.errors())
        self.comp["pairs"] = []
        self.comp["aggregation"] = "mean_within_unit_then_mean_across_seeds"
        self.assertIn("must not invent paired arms", self.errors())

    def test_estimator_still_needs_a_pilot_dependency(self):
        plan = read(self.project / "experiments/plan.json")
        next(row for row in plan["runs"] if row["run_id"] == "proposed-11")["depends_on"] = []
        write(self.project / "experiments/plan.json", plan)
        self.assertIn("pilot dependency", self.errors())

    def test_zero_null_only_and_design_specific_simulation_power(self):
        self.comp["minimum_effect"] = .1
        self.assertIn("zero-null superiority", self.errors())
        self.comp["decision_rule"] = "equivalence"
        self.assertIn("zero-null superiority", self.errors())
        self.comp.update(decision_rule="superiority", minimum_effect=0)
        power = read(self.project / "papers/P01/power-analysis.json")
        power["method"] = "ttest_paired"
        write(self.project / "papers/P01/power-analysis.json", power)
        self.assertIn("design-specific simulation", self.errors())

    def test_family_interval_coverage_and_planned_independent_n_remain_required(self):
        self.card["specifications"][0]["confidence_level"] = .95
        self.assertIn("multiplicity family", self.errors())
        self.card["specifications"][0]["confidence_level"] = 1 - .05 / 7
        self.comp["minimum_units"] = 11
        self.assertIn("power-analysis requirement", self.errors())

    def test_model_mode_does_not_waive_the_other_required_baselines(self):
        self.protocol["comparisons"].pop(1)
        self.assertIn("all declared baselines", self.errors())

    def test_one_estimator_run_cannot_masquerade_as_multiple_baselines(self):
        other = self.protocol["comparisons"][1]
        for key in ("analysis_mode", "empirical_specification_id", "unit_design", "pairs", "aggregation", "minimum_effect", "unit_column", "value_column", "registered_result"):
            other[key] = copy.deepcopy(self.comp[key])
        self.assertIn("reuse", self.errors().lower())


def sealed_estimate(project):
    """Exact native source seal around a genuinely recomputed synthetic result."""
    card = design_fixtures.make_project(project)
    spec = card["specifications"][0]
    plan = read(project / "experiments/plan.json")
    estimation_run = plan["runs"][0]
    estimation_run.update(seed=0, timeout_seconds=30, estimated_cost_usd=0,
                          isolation={"kind": "host"}, depends_on=[])
    result = empirical_runtime.calculate(card, spec, project / card["data"]["path"], design_path=project / "papers/P01/empirical-design.json")
    _, approval, receipt = sealed_run(project, run_id=spec["run_id"], output=spec["output"], body=json.dumps(result))
    write(project / "experiments/plan.json", plan)
    sources = ["papers/P01/empirical-design.json", card["data"]["path"], card["runtime"]["path"], "experiments/plan.json", "experiments/budget.json"]
    write(project / "papers/P01/preregistration.json", {"status": "frozen", "files": [{"path": relative, "sha256": sha(project / relative)} for relative in sources]})
    approval.update(experiment_plan_sha256=sha(project / "experiments/plan.json"),
        frozen_protocol_sha256={"papers/P01/preregistration.json": sha(project / "papers/P01/preregistration.json")})
    write(project / "state/run.json", {"approved_gates": ["G3"], "approvals": [approval]})
    for key in ("argv", "inputs", "seed", "cwd", "timeout_seconds"):
        receipt[key] = estimation_run[key]
    receipt["approved_plan_sha256"] = sha(project / "experiments/plan.json")
    write(project / f"experiments/runs/{receipt['attempt_id']}/run.json", receipt)
    (project / "experiments/registry.jsonl").write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    return card, spec, result, receipt


@unittest.skipUnless(NUMERIC, "actual estimator recomputation runs on cloud scientific CPU")
class EmpiricalMeasurementTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        self.card, self.spec, self.result, self.receipt = sealed_estimate(self.project)
        self.comp = {"analysis_mode": "empirical_estimator", "empirical_specification_id": self.spec["id"],
            "registered_result": {"run_id": self.spec["run_id"], "output": self.spec["output"], "method_id": "did_2x2"},
            "direction": "higher", "minimum_units": 20, "alpha": .05}

    def measure(self, family_size=1):
        return evidence._measure(self.project, self.comp, [], sha(self.project / "experiments/plan.json"), family_size)

    def test_actual_sealed_did_output_is_recomputed_and_signed_interval_is_preserved(self):
        self.assertEqual(empirical_design.audit(self.project, "P01")["errors"], [])
        row = self.measure()
        self.assertAlmostEqual(row["estimate"], 1.7, places=10)
        self.assertEqual(row["independent_units"], 20)
        self.assertEqual(row["n_observations"], 40)
        self.assertEqual(row["seed_effects"], [])
        self.assertFalse(row["scientific_validity_verified"])
        self.comp["direction"] = "lower"
        reverse = self.measure()
        self.assertAlmostEqual(reverse["estimate"], -row["estimate"])
        self.assertAlmostEqual(reverse["ci_low"], -row["ci_high"])
        self.assertAlmostEqual(reverse["ci_high"], -row["ci_low"])

    def test_real_output_tampering_is_detected_even_with_a_resigned_synthetic_receipt(self):
        path = self.project / self.spec["output"]
        altered = read(path); altered["estimate"] += 10
        write(path, altered)
        self.receipt["outputs"][0]["sha256"] = sha(path)
        write(self.project / f"experiments/runs/{self.receipt['attempt_id']}/run.json", self.receipt)
        (self.project / "experiments/registry.jsonl").write_text(json.dumps(self.receipt) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "deterministic estimator recomputation"):
            self.measure()

    def test_actual_sample_size_and_simultaneous_confidence_checks_cannot_be_overridden(self):
        self.comp["minimum_units"] = 21
        with self.assertRaisesRegex(evidence.EvidenceError, "fewer empirical units"):
            self.measure()
        self.comp["minimum_units"] = 20
        with self.assertRaisesRegex(evidence.EvidenceError, "family coverage"):
            self.measure(family_size=2)


class EmpiricalFreezeCompositionTests(unittest.TestCase):
    def test_preregistration_adds_actual_card_data_runtime_and_dataset_contract_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp); card = design_fixtures.make_project(project)
            contract = read(project / "papers/P01/paper-contract.json")
            contract["datasets"] = [card["dataset_id"]]
            write(project / "papers/P01/paper-contract.json", contract)
            dictionary = project / f"data/contracts/{card['dataset_id']}.json"
            write(dictionary, {"synthetic_freeze_composition_only": True})
            checked = {"errors": [], "inputs": [{"path": dictionary.relative_to(project).as_posix(), "sha256": sha(dictionary)}]}
            with patch("scripts.data_contracts.audit", return_value=checked):
                actual = {path.relative_to(project).as_posix() for path in empirical_workflow.preregistration_inputs(project, "P01")}
            self.assertTrue({"papers/P01/empirical-design.json", card["data"]["path"], card["runtime"]["path"], dictionary.relative_to(project).as_posix()} <= actual)


@unittest.skipUnless(REFERENCE, "native Holm composition executes on cloud statsmodels runtime")
class EmpiricalDecisionCompositionTests(unittest.TestCase):
    def test_holm_and_interval_guards_remain_and_exploration_never_establishes_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "fixture"; protocol = acceptance.fixture(project)
            first = protocol["comparisons"][0]
            first.update(analysis_mode="empirical_estimator", minimum_effect=0)
            protocol["comparisons"][-1]["analysis_phase"] = "exploratory"
            write(project / "papers/P01" / evidence.PLAN, protocol)
            (project / "experiments/registry.jsonl").write_text("", encoding="utf-8")
            def measured(_project, comp, *_args):
                low, high, p = (1, 2, .001) if comp["comparison_id"] == "weak" else (1, 2, .03) if comp["comparison_id"] == "domain" else (-2, -1, .0001) if comp["comparison_id"] == "recent" else (1, 2, .001) if comp["comparison_id"] == "noise" else (-2, 2, 1)
                return {"estimate": (low + high)/2, "ci_low": low, "ci_high": high, "p_value": p, "ci_confidence": .999,
                        "independent_units": 20, "sources": [], "scientific_validity_verified": False}
            with patch("scripts.experiment_evidence.validate_plan", return_value=[]), \
                 patch("scripts.research_quality.validate_preregistration", return_value=[]), \
                 patch("scripts.results_validation.validate_registry", return_value=[]), \
                 patch("scripts.experiment_evidence._measure", side_effect=measured):
                report = evidence.build_report(project, "P01")
            rows = {row["comparison_id"]: row for row in report["comparisons"]}
            self.assertEqual(report["status"], "complete", report["errors"])
            self.assertEqual(rows["weak"]["decision"], "meets_preregistered_threshold")
            self.assertGreater(rows["domain"]["p_adjusted"], .05)
            self.assertEqual(rows["domain"]["decision"], "does_not_establish_claim")
            self.assertLess(rows["recent"]["p_adjusted"], .05)
            self.assertEqual(rows["recent"]["decision"], "does_not_establish_claim")
            self.assertEqual(rows["noise"]["decision"], "exploratory_only")
            self.assertFalse(report["scientific_completion_verified"])


if __name__ == "__main__":
    unittest.main()
