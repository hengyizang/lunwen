"""Cloud-only fixtures for preparation contracts, never scientific acceptance."""
import copy
import csv
import tempfile
import unittest
from pathlib import Path

from scripts import empirical_design as empirical
from scripts import empirical_runtime as runtime
from scripts.research_artifacts import read, sha, write


def make_project(project):
    data = project / "data/processed/panel.csv"
    data.parent.mkdir(parents=True)
    with data.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle); writer.writerow(["unit", "period", "treated", "outcome"])
        for unit in range(20):
            treated = int(unit < 10)
            for post, period in enumerate(("pre", "post")):
                value = 1 + unit * 0.05 + 2 * post + 1.7 * treated * post + 0.15 * ((unit * 7) % 5) * post
                writer.writerow([f"u{unit}", period, treated, value])
    copied = project / "analysis/empirical_runtime.py"
    copied.parent.mkdir(parents=True)
    copied.write_bytes(Path(runtime.__file__).read_bytes())
    card = {
        "schema_version": "1.0", "paper_id": "P01", "dataset_id": "synthetic-panel",
        "estimand": {key: "Synthetic bounded estimand, not a causal conclusion." for key in
                     ("outcome", "population", "exposure", "contrast", "time_horizon", "inference_boundary")},
        "assignment": {key: "Synthetic assignment for software checks only." for key in ("mechanism", "comparison_group", "timing")},
        "sample": {"inclusion_rule": "All twenty synthetic units in both periods.", "exclusion_rule": "No exclusions.",
                   "missingness_rule": "Reject missing values; do not impute.", "unit_column": "unit", "cluster_column": "unit"},
        "assumptions": [{"id": "trends", "statement": "Untreated trends would be parallel; this fixture cannot establish it.",
                         "status": "proposed", "evidence": []}],
        "rival_explanations": [{"id": "selection", "explanation": "Different untreated trends.",
                                "discriminating_test": "Separate registered falsification diagnostic; one pre-period cannot test trends."}],
        "diagnostics": [{"id": "falsification", "test": "Assignment and timing evidence audit", "purpose": "Assess a rival mechanism.",
                         "failure_action": "Withhold the causal conclusion and review design.", "run_id": "diagnostic", "output": "papers/P01/results/diagnostic.json"}],
        "data": {"path": data.relative_to(project).as_posix(), "sha256": sha(data)},
        "runtime": {"path": copied.relative_to(project).as_posix(), "sha256": sha(copied)},
        "specifications": [{"id": "spec-main", "run_id": "estimate-main", "method": "did_2x2", "phase": "confirmatory", "family": "main",
                            "claim_ids": ["C1"], "output": "papers/P01/results/spec-main.json", "outcome": "outcome", "covariates": [],
                            "confidence_level": 0.95, "covariance": "cluster", "treatment": "treated", "period": "period",
                            "pre_value": "pre", "post_value": "post", "minimum_clusters": 10}],
        "specification_policy": {"selection_rule": "report_all_preregistered", "exploratory_rule": "Exploratory results are labeled and retained.",
                                 "changes_require_amendment": True}}
    write(project / "papers/P01/paper-contract.json", {"independence": {"unique_claim_ids": ["C1"]}})
    save_card(project, card)
    return card


def save_card(project, card):
    path = project / "papers/P01/empirical-design.json"
    write(path, card)
    inputs = [{"path": "papers/P01/empirical-design.json", "sha256": sha(path)}, card["data"], card["runtime"]]
    runs = []
    for spec in card["specifications"]:
        runs.append({"run_id": spec["run_id"], "paper_id": "P01", "cwd": ".", "inputs": copy.deepcopy(inputs),
                     "expected_outputs": [spec["output"]], "argv": ["python", card["runtime"]["path"], "--design", "papers/P01/empirical-design.json",
                     "--data", card["data"]["path"], "--spec", spec["id"], "--output", spec["output"]]})
    runs.extend({"run_id": row["run_id"], "paper_id": "P01", "expected_outputs": [row["output"]]} for row in card["diagnostics"])
    write(project / "experiments/plan.json", {"runs": runs})


class EmpiricalDesignTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        self.card = make_project(self.project)

    def test_preparation_preserves_unverified_identification_and_starts_no_run(self):
        result = empirical.audit(self.project, "P01")
        self.assertTrue(result["pass"], result["errors"])
        self.assertEqual(result["status"], "ready_for_scientific_review")
        self.assertFalse(result["causal_identification_verified"])
        self.assertFalse(result["execution_started"])
        self.assertFalse(result["preregistered"])
        self.assertFalse((self.project / "experiments/registry.jsonl").exists())

    def test_missing_frozen_contract_blocks_execution_reporting(self):
        result = empirical.audit(self.project, "P01", require_frozen=True)
        self.assertFalse(result["pass"])
        self.assertIn("preregistration", " ".join(result["errors"]))

    def test_design_and_data_are_frozen_and_saved_report_is_current(self):
        current = empirical.audit(self.project, "P01")
        write(self.project / "papers/P01/preregistration.json", {"files": current["sources"][:3]})
        empirical.refresh(self.project, "P01")
        self.assertEqual(empirical.validate_saved_report(self.project, "P01"), [])
        self.card["specifications"][0]["phase"] = "exploratory"
        save_card(self.project, self.card)
        self.assertIn("changed after preregistration", " ".join(empirical.validate_saved_report(self.project, "P01")))

    def test_source_and_runtime_tampering_fail(self):
        for key in ("data", "runtime"):
            path = self.project / self.card[key]["path"]
            before = path.read_bytes(); path.write_bytes(before + b"\n")
            self.assertFalse(empirical.audit(self.project, "P01")["pass"])
            path.write_bytes(before)
        self.card["runtime"]["sha256"] = "a" * 64
        save_card(self.project, self.card)
        self.assertFalse(empirical.audit(self.project, "P01")["pass"])

    def test_unsupported_estimators_and_automatic_significance_selection_are_refused(self):
        self.card["specifications"][0]["method"] = "staggered_did"
        save_card(self.project, self.card)
        self.assertIn("unsupported", " ".join(empirical.audit(self.project, "P01")["errors"]))
        self.card["specifications"][0]["method"] = "did_2x2"
        self.card["specification_policy"]["selection_rule"] = "smallest_p_value"
        save_card(self.project, self.card)
        self.assertFalse(empirical.audit(self.project, "P01")["pass"])

    def test_wrong_claim_run_command_and_missing_diagnostics_are_refused(self):
        original = copy.deepcopy(self.card)
        self.card["specifications"][0]["claim_ids"] = ["C2"]
        save_card(self.project, self.card)
        self.assertIn("claims", " ".join(empirical.audit(self.project, "P01")["errors"]))
        self.card = original; save_card(self.project, self.card)
        plan = read(self.project / "experiments/plan.json")
        plan["runs"][0]["argv"].append("--choose-best")
        write(self.project / "experiments/plan.json", plan)
        self.assertIn("exact bounded", " ".join(empirical.audit(self.project, "P01")["errors"]))
        save_card(self.project, self.card)
        self.card["diagnostics"][0]["run_id"] = "not-planned"
        write(self.project / "papers/P01/empirical-design.json", self.card)
        plan = read(self.project / "experiments/plan.json")
        plan["runs"][0]["inputs"][0]["sha256"] = sha(self.project / "papers/P01/empirical-design.json")
        write(self.project / "experiments/plan.json", plan)
        self.assertIn("diagnostic", " ".join(empirical.audit(self.project, "P01")["errors"]))

    def test_unknown_assumptions_remain_unverified_but_fabricated_support_fails(self):
        self.card["assumptions"][0]["status"] = "source_supported"
        save_card(self.project, self.card)
        self.assertIn("located evidence", " ".join(empirical.audit(self.project, "P01")["errors"]))

    def test_inconsistent_multiplicity_family_confidence_is_refused(self):
        extra = copy.deepcopy(self.card["specifications"][0])
        extra.update(id="sensitivity", run_id="estimate-sensitivity", output="papers/P01/results/sensitivity.json", confidence_level=0.9)
        self.card["specifications"].append(extra)
        save_card(self.project, self.card)
        self.assertIn("common confidence", " ".join(empirical.audit(self.project, "P01")["errors"]))

    def test_deleted_design_cannot_remove_existing_audit_boundary(self):
        empirical.refresh(self.project, "P01")
        (self.project / "papers/P01/empirical-design.json").unlink()
        self.assertFalse(empirical.audit(self.project, "P01")["pass"])
        self.assertTrue(empirical.validate_saved_report(self.project, "P01"))

    def test_unconfigured_route_does_not_force_causal_methods_on_other_studies(self):
        fresh = self.project / "other"; fresh.mkdir()
        self.assertEqual(empirical.audit(fresh, "P01")["status"], "not_configured")
        self.assertEqual(empirical.validate_saved_report(fresh, "P01"), [])


if __name__ == "__main__":
    unittest.main()
