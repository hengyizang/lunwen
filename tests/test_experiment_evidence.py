from __future__ import annotations

import copy
import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import artifact_ownership, experiment_evidence as evidence
from scripts import experiment_evidence_acceptance as acceptance
from scripts import experiment_runner as runner, results_validation


class ExperimentEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_dir = tempfile.TemporaryDirectory()
        cls.base = Path(cls.base_dir.name) / "synthetic-base"
        acceptance.fixture(cls.base)
        cls.registry = runner.execute(cls.base.name, project_root=cls.base)
        cls.report = evidence.build_report(cls.base, "P01")
        if cls.report["status"] != "complete":
            raise AssertionError(cls.report)
        acceptance.write(cls.base / "papers/P01" / evidence.REPORT, cls.report)

    @classmethod
    def tearDownClass(cls):
        cls.base_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "fixture"
        shutil.copytree(self.base, self.project)
        self.protocol = evidence.read(self.project / "papers/P01" / evidence.PLAN)

    def save_protocol(self):
        acceptance.write(self.project / "papers/P01" / evidence.PLAN, self.protocol)

    def assert_plan_error(self, text):
        self.save_protocol()
        self.assertIn(text, "; ".join(evidence.validate_plan(self.project, "P01")))

    def test_known_effects_negative_null_and_equivalence_are_preserved(self):
        report = evidence.build_report(self.project, "P01")
        rows = {r["comparison_id"]: r for r in report["comparisons"]}
        self.assertEqual(report["status"], "complete")
        self.assertFalse(report["scientific_completion_verified"])
        self.assertAlmostEqual(rows["weak"]["estimate"], 2.22)
        self.assertAlmostEqual(rows["recent"]["estimate"], -.345)
        self.assertLess(rows["recent"]["ci_high"], 0)
        self.assertEqual(rows["weak"]["decision"], "meets_preregistered_threshold")
        self.assertEqual(rows["recent"]["decision"], "does_not_establish_claim")
        self.assertEqual(rows["noise"]["decision"], "does_not_establish_claim")
        self.assertEqual(rows["null-control"]["decision"], "meets_preregistered_threshold")
        self.assertTrue(all(r["p_adjusted"] >= r["p_value"] for r in rows.values()))

    def test_unit_aggregation_is_not_rows_times_seeds(self):
        for row in self.report["comparisons"]:
            self.assertEqual(row["independent_units"], 12)
            self.assertEqual(row["seeds"], 3)
            self.assertEqual(len(row["seed_effects"]), 3)
            self.assertEqual(row["family_size"], 7)
            self.assertAlmostEqual(row["ci_confidence"], 1-.05/7)

    def test_reference_student_interval(self):
        # n=5, mean=1, sample SD=sqrt(2.5), t(.975,4)=2.776445105.
        comp = copy.deepcopy(self.protocol["comparisons"][0])
        comp.update(minimum_units=5, minimum_effect=0, pairs=comp["pairs"][:1])
        records = copy.deepcopy(self.registry)
        for arm, values in (("treatment", [-1, 0, 1, 2, 3]), ("comparator", [0]*5)):
            binding = comp["pairs"][0][arm]
            path = self.project / binding["output"]
            path.write_text("unit,value\n" + "".join(f"{i},{v}\n" for i, v in enumerate(values)), encoding="utf-8")
            record = next(r for r in records if r["run_id"] == binding["run_id"])
            record["outputs"][0]["sha256"] = evidence.sha(path)
            acceptance.write(self.project / f"experiments/runs/{record['attempt_id']}/run.json", record)
        row = evidence._measure(self.project, comp, records, evidence.sha(self.project / "experiments/plan.json"), 1)
        self.assertAlmostEqual(row["estimate"], 1)
        self.assertAlmostEqual(row["ci_low"], -.963243161, places=7)
        self.assertAlmostEqual(row["ci_high"], 2.963243161, places=7)

    def test_missing_baseline_is_blocked(self):
        self.protocol["comparisons"].pop(0)
        self.assert_plan_error("all declared baselines")

    def test_missing_seed_is_blocked(self):
        self.protocol["comparisons"][0]["pairs"].pop()
        self.assert_plan_error("every preregistered seed")

    def test_missing_ablation_or_negative_control_is_blocked(self):
        for role in ("ablation", "negative_control", "robustness"):
            with self.subTest(role=role):
                self.protocol = evidence.read(self.base / "papers/P01" / evidence.PLAN)
                self.protocol["comparisons"] = [c for c in self.protocol["comparisons"] if c["role"] != role]
                self.assert_plan_error(f"executable {role}")

    def test_one_run_cannot_be_relabeled_as_other_conditions(self):
        self.protocol["comparisons"][1]["pairs"] = copy.deepcopy(self.protocol["comparisons"][0]["pairs"])
        self.assert_plan_error("relabeled")

    def test_power_sample_size_and_multiplicity_are_enforced(self):
        self.protocol["comparisons"][0]["minimum_units"] = 11
        self.assert_plan_error("power-analysis requirement")
        self.protocol["comparisons"][0]["minimum_units"] = 12
        self.save_protocol()
        power = evidence.read(self.project / "papers/P01/power-analysis.json")
        power["alpha"] = .05
        acceptance.write(self.project / "papers/P01/power-analysis.json", power)
        self.assertIn("multiplicity", "; ".join(evidence.validate_plan(self.project, "P01")))

    def test_each_claim_needs_all_baselines(self):
        contract = evidence.read(self.project / "papers/P01/paper-contract.json")
        contract["independence"]["unique_claim_ids"].append("C2")
        acceptance.write(self.project / "papers/P01/paper-contract.json", contract)
        self.protocol["comparisons"][0]["claim_ids"].append("C2")
        self.assert_plan_error("every declared baseline")

    def test_absent_pilot_dependency_is_blocked(self):
        plan = evidence.read(self.project / "experiments/plan.json")
        plan["runs"][1]["depends_on"] = []
        acceptance.write(self.project / "experiments/plan.json", plan)
        self.assertIn("successful pilot", "; ".join(evidence.validate_plan(self.project, "P01")))

    def test_dependencies_must_be_earlier_same_paper_runs(self):
        for change in ("later", "other_paper", "duplicate"):
            plan = evidence.read(self.project / "experiments/plan.json")
            if change == "later":
                plan["runs"][0]["depends_on"] = [plan["runs"][1]["run_id"]]
            elif change == "other_paper":
                plan["runs"][0]["paper_id"] = "P02"
            else:
                plan["runs"][1]["depends_on"] = ["pilot-0", "pilot-0"]
            self.assertTrue(runner.validate_plan(plan), change)

    def test_failed_pilot_prevents_process_and_attempt(self):
        project = Path(self.temp.name) / "failed-pilot"
        acceptance.fixture(project, fail_pilot=True)
        result = runner.execute(project.name, ["pilot-0"], project_root=project)[0]
        self.assertEqual(result["status"], "failed")
        with self.assertRaisesRegex(runner.ExperimentError, "did not succeed"):
            runner.execute(project.name, ["proposed-11"], project_root=project)
        self.assertEqual(len((project / "experiments/registry.jsonl").read_text().splitlines()), 1)
        self.assertFalse((project / "results/proposed-11.csv").exists())

    def test_changed_pilot_output_prevents_dependent_run(self):
        (self.project / "results/pilot-0.csv").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(runner.ExperimentError, "output changed"):
            runner.execute(self.project.name, ["proposed-11"], project_root=self.project)

    def test_frozen_protocol_and_locked_design_cannot_change_before_execution(self):
        for relative in ("papers/P01/preregistration.json", "papers/P01/experiments/primary.json"):
            path = self.project / relative
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.assertRaisesRegex(runner.ExperimentError, "changed after G3"):
                runner.approved_plan(self.project, self.project / "experiments/plan.json",
                                     self.project / "experiments/budget.json")
            path.write_bytes(original)

    def test_changed_output_hash_blocks_report(self):
        (self.project / "results/weak-11.csv").write_text("unit,value\nu00,1000\n", encoding="utf-8")
        self.assertEqual(evidence.build_report(self.project, "P01")["status"], "blocked")

    def test_executor_receipt_mismatch_blocks_report(self):
        path = self.project / "experiments/runs/weak-11-attempt-001/run.json"
        receipt = evidence.read(path)
        receipt["seed"] = 12345
        acceptance.write(path, receipt)
        self.assertIn("receipt", "; ".join(evidence.build_report(self.project, "P01")["errors"]))

    def test_repeated_attempt_cannot_select_best_result(self):
        receipt = copy.deepcopy(next(r for r in self.registry if r["run_id"] == "weak-11"))
        receipt["attempt_id"] = "weak-11-attempt-002"
        runner.append_registry(self.project / "experiments/registry.jsonl", receipt)
        self.assertIn("exactly one", "; ".join(evidence.build_report(self.project, "P01")["errors"]))

    def test_nonfinite_or_missing_values_are_never_silently_dropped(self):
        path = self.project / "bad.csv"
        for value in ("NaN", "inf", "", "non-number"):
            path.write_text(f"unit,value\nu00,{value}\n", encoding="utf-8")
            with self.assertRaises(evidence.EvidenceError):
                evidence._unit_values(path, self.protocol["comparisons"][0])

    def test_custom_analysis_is_hash_bound_and_not_claimed_recomputed(self):
        comp = copy.deepcopy(self.protocol["comparisons"][0])
        measured = evidence._measure(self.project, comp, self.registry,
                                     evidence.sha(self.project / "experiments/plan.json"), 7)
        comp["analysis_mode"] = "registered_result"
        comp["registered_result"] = {"run_id": "custom-analysis", "output": "results/custom.json", "method_id": "fixture-model-v1"}
        custom = {k: measured[k] for k in ("estimate", "ci_low", "ci_high", "p_value", "ci_confidence", "independent_units")}
        custom.update({k: comp[k] for k in ("decision_rule", "direction", "minimum_effect", "aggregation", "analysis_unit")})
        custom.update(schema_version="1.0", comparison_id=comp["comparison_id"], method_id="fixture-model-v1",
                      source_hashes={s["path"]: s["sha256"] for s in measured["sources"]})
        def evaluate(payload):
            acceptance.write(self.project / "results/custom.json", payload)
            receipt = {"run_id": "custom-analysis", "attempt_id": "custom-001", "status": "succeeded",
                       "approved_plan_sha256": evidence.sha(self.project / "experiments/plan.json"),
                       "outputs": [{"path": "results/custom.json", "sha256": evidence.sha(self.project / "results/custom.json")}]}
            acceptance.write(self.project / "experiments/runs/custom-001/run.json", receipt)
            return evidence._measure(self.project, comp, self.registry + [receipt],
                                     evidence.sha(self.project / "experiments/plan.json"), 7)
        self.assertFalse(evaluate(custom)["recomputed_from_units"])
        changed = copy.deepcopy(custom)
        changed["minimum_effect"] = 0
        with self.assertRaisesRegex(evidence.EvidenceError, "threshold"):
            evaluate(changed)
        changed = copy.deepcopy(custom)
        changed["source_hashes"].pop(next(iter(changed["source_hashes"])))
        with self.assertRaisesRegex(evidence.EvidenceError, "source hashes"):
            evaluate(changed)

    def test_calibrated_claims_require_all_comparisons_and_sources(self):
        path = acceptance.claim_matrix(self.project, self.report)
        self.assertEqual(results_validation.validate_claim_evidence(self.project, path, self.registry), [])
        path = acceptance.claim_matrix(self.project, self.report, "supported")
        self.assertIn("every confirmatory", "; ".join(results_validation.validate_claim_evidence(self.project, path, self.registry)))
        path = acceptance.claim_matrix(self.project, self.report)
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields, row = reader.fieldnames, next(reader)
        row["comparison_ids"] = "weak;domain"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow(row)
        self.assertIn("every preregistered", "; ".join(results_validation.validate_claim_evidence(self.project, path, self.registry)))

    def test_cross_paper_run_cannot_support_claim(self):
        path = acceptance.claim_matrix(self.project, self.report)
        registry = copy.deepcopy(self.registry)
        next(r for r in registry if r["run_id"] == "weak-11")["paper_id"] = "P02"
        self.assertIn("different paper", "; ".join(results_validation.validate_claim_evidence(self.project, path, registry)))

    def test_statistical_report_and_frozen_inputs_are_protected_from_model_writes(self):
        for relative in ("papers/P01/experiment-evidence.json", "papers/P01/experiment-evidence-plan.json",
                         "papers/P01/experiments/primary.json", "papers/P01/preregistration.json"):
            self.assertTrue(artifact_ownership.executor_owned(self.project, relative), relative)

    def test_hand_edited_statistical_summary_is_rejected(self):
        report = copy.deepcopy(self.report)
        report["comparisons"][0]["estimate"] = 10000
        acceptance.write(self.project / "papers/P01" / evidence.REPORT, report)
        self.assertIn("stale", "; ".join(evidence.validate_report(self.project, "P01")))


if __name__ == "__main__":
    unittest.main()
