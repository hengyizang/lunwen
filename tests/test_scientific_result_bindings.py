"""Real local synthetic executor receipts test joins, never scientific findings."""
from __future__ import annotations

import copy
import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import experiment_evidence as evidence, experiment_evidence_acceptance as acceptance
from scripts import experiment_runner as runner, results_validation as results


class ScientificResultBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.base = Path(cls.directory.name) / "base"
        acceptance.fixture(cls.base, current_protocol=True)
        cls.registry = runner.execute(cls.base.name, project_root=cls.base)
        cls.report = evidence.build_report(cls.base, "P01")
        if cls.report["status"] != "complete":
            raise AssertionError(cls.report["errors"])
        matrix = acceptance.claim_matrix(cls.base, cls.report)
        (cls.base / "claims").mkdir(exist_ok=True)
        shutil.copyfile(matrix, cls.base / "claims/claim-evidence.csv")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "fixture"
        shutil.copytree(self.base, self.project)

    def protocol(self, mutate):
        path = self.project / "papers/P01" / evidence.PLAN
        value = evidence.read(path)
        mutate(value)
        acceptance.write(path, value)

    def matrix(self, mutate):
        path = self.project / "claims/claim-evidence.csv"
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        mutate(rows)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_current_protocol_passes_with_mixed_adverse_results(self):
        self.assertEqual(evidence.validate_scientific_bindings(self.project, "P01", "G4"), [])
        actual = results.claim_outcomes(self.project, "P01")["claims"]["C1"]
        self.assertEqual(actual["result_status"], "partially_supported")
        self.assertIn("recent", actual["comparison_ids"])
        self.assertEqual(results.validate_result_statuses(self.project, "P01", [
            {"claim_id": "C1", "result_status": "partially_supported"}]), [])

    def test_g3_primary_cannot_switch_to_a_secondary_outcome(self):
        design_path = self.project / "papers/P01/experiments/primary.json"
        design = evidence.read(design_path)
        design["metrics"]["secondary"] = ["other_score"]
        acceptance.write(design_path, design)
        self.protocol(lambda p: p["comparisons"][0].update(metric="other_score"))
        errors = evidence.validate_scientific_bindings(self.project, "P01")
        self.assertTrue(any("contract" in e for e in errors), errors)

    def test_g3_falsification_condition_cannot_disappear_or_change_threshold(self):
        self.protocol(lambda p: p["comparisons"][0].update(condition_ids=[]))
        self.assertTrue(evidence.validate_scientific_bindings(self.project, "P01"))
        self.protocol(lambda p: p["comparisons"][0].update(condition_ids=["F1"], minimum_effect=.2))
        self.assertTrue(evidence.validate_scientific_bindings(self.project, "P01"))

    def test_contract_text_and_designed_condition_must_both_survive(self):
        path = self.project / "papers/P01/experiments/primary.json"
        design = evidence.read(path)
        design["falsification_criteria"] = ["An unrelated criterion"]
        acceptance.write(path, design)
        self.assertIn("exact contracted condition", "; ".join(evidence.validate_scientific_bindings(self.project, "P01")))

    def test_legacy_plan_is_diagnostic_but_cannot_enter_new_gate(self):
        self.protocol(lambda p: p.update(schema_version="1.0"))
        path = self.project / "papers/P01" / evidence.PLAN
        original = path.read_bytes()
        self.assertEqual(evidence.validate_plan(self.project, "P01"), [])
        self.assertIn("migrate before freezing", "; ".join(evidence.validate_scientific_bindings(self.project, "P01")))
        self.assertEqual(path.read_bytes(), original)

    def test_g5_cannot_upgrade_the_formal_partial_result_to_supported(self):
        self.assertIn("result_status differs", "; ".join(results.validate_result_statuses(self.project, "P01", [
            {"claim_id": "C1", "result_status": "supported"}])))
        self.matrix(lambda rows: rows[0].update(support="supported"))
        self.assertIn("every confirmatory threshold", "; ".join(results.validate_result_statuses(self.project, "P01")))

    def test_existing_contribution_audit_checks_the_actual_formal_outcome(self):
        from scripts.contribution_reporting import audit
        config = {"facts": [], "claim_alignment": [{"claim_id": "C1", "result_status": "supported"}]}
        report = audit(self.project, "P01", config)
        self.assertIsNotNone(report["outcome_binding"])
        self.assertTrue(any("result_status differs" in error for error in report["errors"]))
        config["claim_alignment"][0]["result_status"] = "partially_supported"
        report = audit(self.project, "P01", config)
        self.assertFalse(any("result_status differs" in error for error in report["errors"]))
        self.assertFalse(report["scientific_completion_verified"])

    def test_negative_and_inconclusive_results_are_valid_and_not_forced_to_succeed(self):
        for status in ("not_supported", "inconclusive"):
            self.matrix(lambda rows: rows[0].update(support=status))
            self.assertEqual(results.validate_result_statuses(self.project, "P01", [
                {"claim_id": "C1", "result_status": status}]), [])

    def test_no_significance_alone_cannot_be_called_contradiction(self):
        row = next(c for c in self.report["comparisons"] if c["comparison_id"] == "noise")
        self.assertIn("absence of significance", results._outcome_error("contradicted", [row], empirical=True))
        opposite = next(c for c in self.report["comparisons"] if c["comparison_id"] == "recent")
        self.assertIsNone(results._outcome_error("contradicted", [opposite], empirical=True))

    def test_exploratory_support_cannot_be_promoted_to_confirmatory_support(self):
        row = copy.deepcopy(next(c for c in self.report["comparisons"] if c["comparison_id"] == "weak"))
        row["analysis_phase"] = "exploratory"
        self.assertIsNotNone(results._outcome_error("supported", [row], empirical=True))
        self.assertIsNotNone(results._outcome_error("partially_supported", [row], empirical=True))

    def test_formal_matrix_cannot_omit_adverse_or_reference_unknown_runs(self):
        self.matrix(lambda rows: rows[0].update(comparison_ids="weak;domain"))
        self.assertTrue(results.validate_result_statuses(self.project, "P01"))
        shutil.copyfile(acceptance.claim_matrix(self.project, self.report), self.project / "claims/claim-evidence.csv")
        self.matrix(lambda rows: rows[0].update(analysis_ids=rows[0]["analysis_ids"] + ";invented"))
        self.assertTrue(results.validate_result_statuses(self.project, "P01"))

    def test_current_output_changes_cannot_reuse_previous_label(self):
        source = self.project / "results/proposed-11.csv"
        source.write_text("unit,value\nu0,999\n", encoding="utf-8")
        self.assertTrue(results.validate_result_statuses(self.project, "P01"))

    def test_g5_missing_or_duplicate_claim_alignment_is_rejected(self):
        self.assertTrue(results.validate_result_statuses(self.project, "P01", []))
        self.assertTrue(results.validate_result_statuses(self.project, "P01", [
            {"claim_id": "C1", "result_status": "partially_supported"}] * 2))
        folder = self.project / "papers/P01/reviews"
        folder.mkdir(exist_ok=True)
        acceptance.write(folder / "paper-facts.json", {})
        self.assertTrue(evidence.validate_scientific_bindings(self.project, "P01", "G5"))
