"""Cloud-run data contracts; synthetic rows never establish causal validity."""
import copy
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import data_contracts as contracts
from scripts.research_artifacts import read, sha, write
from tests.test_dataset_fetch import valid_manifest


class DataContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.dataset = "fixture"
        self.source = self.project/"data/raw/fixture.csv"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("id,year,value,treated\na,2019,100,0\na,2020,200,1\nb,2019,300,0\nb,2020,400,0\n", encoding="utf-8")
        self.manifest = valid_manifest(); self.manifest["dataset_id"] = self.dataset
        self.manifest["download"]["sha256"] = sha(self.source)
        self.spec = {"schema_version": "1.0", "dataset_id": self.dataset,
            "input": self.binding(self.source), "manifest": {}, "variables": [
                {"name": name, "type": kind, "definition": "Synthetic " + name, "unit": unit,
                 "source_field": name, "formula": "identity(" + name + ")", "missing_codes": ["", "NA"], "required": True}
                for name, kind, unit in (("id", "string", "device identifier"), ("year", "integer", "calendar year"),
                                         ("value", "number", "cents"), ("treated", "boolean", "indicator"))],
            "joins": [], "cleaning_steps": [], "cleaning_implementation_sha256": sha(Path(contracts.__file__)),
            "cleaning_runtime_sha256": sha(Path(contracts.__file__).with_name("data_cleaning_runtime.py")),
            "panel": {"unit_columns": ["id"], "time_column": "year", "expected_times": ["2019", "2020"],
                "balance_policy": "require_balanced"}}
        self.save()

    def binding(self, path):
        return {"path": path.relative_to(self.project).as_posix(), "sha256": sha(path)}

    def save(self):
        manifest_path = self.project/f"data/manifests/{self.dataset}.json"
        write(manifest_path, self.manifest)
        registry = self.project/"data/datasets.jsonl"; registry.parent.mkdir(exist_ok=True)
        registry.write_text(json.dumps(self.manifest)+"\n", encoding="utf-8")
        self.spec["manifest"] = self.binding(manifest_path)
        write(self.project/f"data/contracts/{self.dataset}.json", self.spec)

    def replace_source(self, value):
        self.source.write_text(value, encoding="utf-8")
        self.spec["input"] = self.binding(self.source)
        self.manifest["download"]["sha256"] = sha(self.source)
        self.save()

    def report(self):
        return contracts.audit(self.project, self.dataset)

    def approved(self, output="data/processed/fixture.csv", receipt="reports/data-cleaning/fixture.json"):
        return {"runs": [{"run_id": "clean-fixture", "expected_outputs": [output, receipt], "inputs": self.report()["inputs"]}]}

    def test_complete_dictionary_audit_is_read_only_and_not_a_scientific_gate(self):
        original = self.source.read_bytes(); result = self.report()
        self.assertTrue(result["pass"], result)
        self.assertTrue(result["complete_scan"])
        self.assertEqual(result["panel"]["expected_cells"], 4)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse((self.project/"reports").exists())
        for key in ("data_mutated", "scientific_validity_verified", "data_rights_verified", "gate_approved"):
            self.assertFalse(result[key])

    def test_dictionary_requires_every_column_and_meaningful_units_formula(self):
        original = copy.deepcopy(self.spec)
        for field in ("unit", "definition", "source_field", "formula"):
            self.spec = copy.deepcopy(original); self.spec["variables"][0][field] = ""
            self.save(); self.assertFalse(self.report()["pass"])
        self.spec = original; self.spec["variables"].pop()
        self.save(); self.assertFalse(self.report()["pass"])

    def test_source_manifest_and_registry_changes_are_replayed(self):
        contracts.refresh(self.project, self.dataset)
        self.assertEqual(contracts.validate_saved_report(self.project, self.dataset), [])
        self.source.write_text(self.source.read_text()+"b,2021,0,0\n", encoding="utf-8")
        self.assertTrue(contracts.validate_saved_report(self.project, self.dataset))
        self.spec["input"] = self.binding(self.source); self.save()
        self.assertTrue(any("original download" in x for x in self.report()["errors"]))

    def test_registry_cannot_relabel_a_different_manifest(self):
        registry = self.project/"data/datasets.jsonl"
        changed = copy.deepcopy(self.manifest); changed["version"] = "unapproved replacement"
        registry.write_text(json.dumps(changed)+"\n", encoding="utf-8")
        self.assertFalse(self.report()["pass"])

    def test_full_calendar_detects_a_wholly_absent_period(self):
        self.spec["panel"]["expected_times"] = ["2019", "2020", "2021"]
        self.save(); result = self.report()
        self.assertFalse(result["pass"])
        self.assertEqual(result["panel"]["wholly_absent_times"], ["2021"])
        self.assertEqual(result["panel"]["missing_cells"], 2)

    def test_unbalanced_policy_preserves_all_rows_and_records_attrition(self):
        self.replace_source("id,year,value,treated\na,2019,100,0\na,2020,200,1\nb,2019,300,0\n")
        self.spec["panel"]["balance_policy"] = "allow_unbalanced"; self.save()
        result = self.report()
        self.assertTrue(result["pass"], result)
        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["panel"]["exited_before_last_period"], 1)
        self.assertEqual(result["panel"]["singletons"], 1)
        self.assertTrue(result["warnings"])

    def test_duplicates_and_missing_keys_are_not_waived_for_unbalanced_panel(self):
        self.replace_source("id,year,value,treated\na,2019,100,0\na,2019,200,1\nNA,2020,300,0\n")
        self.spec["panel"]["balance_policy"] = "allow_unbalanced"; self.save()
        result = self.report()
        self.assertFalse(result["pass"])
        self.assertEqual(result["panel"]["duplicate_keys"], 1)
        self.assertEqual(result["panel"]["blank_keys"], 1)

    def test_nonfinite_wrong_type_and_required_missing_fail(self):
        for value in ("NaN", "Infinity", "not-a-number", "NA"):
            self.replace_source("id,year,value,treated\na,2019,"+value+",0\na,2020,200,1\n")
            self.assertFalse(self.report()["pass"], value)

    def test_treatment_timing_reversal_and_missing_pre_period_are_detected(self):
        self.spec["panel"]["treatment"] = {"column": "treated", "untreated_values": ["0"], "treated_values": ["1"],
            "absorbing": True, "minimum_pre_periods": 1, "minimum_post_periods": 1}
        self.save(); self.assertTrue(self.report()["pass"], self.report())
        self.replace_source("id,year,value,treated\na,2019,100,1\na,2020,200,0\nb,2019,300,0\nb,2020,400,0\n")
        result = self.report()
        self.assertFalse(result["pass"])
        self.assertEqual(result["panel"]["treatment_timing"]["reversals"], 1)
        self.assertEqual(result["panel"]["treatment_timing"]["insufficient_pre_post_units"], 1)

    def add_join(self, content="id,label\na,A\nb,B\n"):
        path = self.project/"data/raw/lookup.csv"; path.write_text(content, encoding="utf-8")
        self.spec["joins"] = [{"id": "lookup", "right": self.binding(path), "left_keys": ["id"], "right_keys": ["id"],
            "right_key_units": {"id": "device identifier"}, "right_key_missing_codes": {"id": ["", "NA"]},
            "cardinality": "many_to_one", "minimum_match_rate": 1, "reason": "Synthetic device metadata alignment."}]
        self.save()

    def test_join_cardinality_match_rates_and_units_are_checked_without_joining(self):
        self.add_join(); result = self.report()
        self.assertTrue(result["pass"], result)
        self.assertEqual(result["joins"][0]["matched_left_rows"], 4)
        self.assertFalse(result["joins"][0]["join_executed"])
        self.add_join("id,label\na,A\na,duplicate\n")
        result = self.report()
        self.assertFalse(result["pass"])
        self.assertEqual(result["joins"][0]["unmatched_left_rows"], 2)
        self.spec["joins"][0]["right_key_units"]["id"] = "different identifier system"
        self.save(); self.assertFalse(self.report()["pass"])

    def test_join_missing_codes_cannot_be_treated_as_matching_identifiers(self):
        self.add_join("id,label\na,A\nb,B\nNA,invalid\n")
        self.assertTrue(any("missing join keys" in x for x in self.report()["errors"]))

    def steps(self):
        return [{"id": "unit", "operation": "linear_unit_conversion", "column": "value", "from_unit": "cents", "to_unit": "dollars",
            "factor": 0.01, "offset": 0, "reason": "Convert a declared unit with an exact fixed factor."},
            {"id": "name", "operation": "rename", "column": "value", "to": "amount", "reason": "Use the preregistered analysis column name."}]

    def test_clean_plan_requires_matching_units_explicit_rules_and_frozen_code(self):
        self.spec["cleaning_steps"] = self.steps(); self.save()
        self.assertTrue(self.report()["pass"], self.report())
        self.spec["cleaning_steps"][0]["from_unit"] = "dollars"; self.save()
        self.assertFalse(self.report()["pass"])
        self.spec["cleaning_steps"] = [{"id": "hack", "operation": "eval", "column": "value", "reason": "Invalid custom code."}]
        self.save(); self.assertFalse(self.report()["pass"])
        self.spec["cleaning_steps"] = self.steps(); self.spec["cleaning_implementation_sha256"] = "0"*64
        self.save(); self.assertTrue(any("implementation" in x for x in self.report()["errors"]))

    def test_pure_cleaning_tracks_each_step_and_never_changes_input_rows(self):
        fields = [x["name"] for x in self.spec["variables"]]
        rows = list(csv.DictReader(io.StringIO(self.source.read_text())))
        before = copy.deepcopy(rows)
        variables = contracts._variables(self.spec["variables"], fields)
        result_fields, result_rows, definitions, history = contracts._clean_rows(fields, rows, variables, self.steps())
        self.assertEqual(rows, before)
        self.assertIn("amount", result_fields)
        self.assertEqual(result_rows[0]["amount"], "1.00")
        self.assertEqual(definitions["amount"]["unit"], "dollars")
        self.assertEqual(definitions["amount"]["formula"], "(identity(value)) * 0.01 + 0")
        self.assertEqual([step["rows_before"] for step in history], [4, 4])

    def test_missing_normalization_and_explicit_exclusions_preserve_accounting(self):
        variables = {x["name"]: x for x in self.spec["variables"]}
        fields = list(variables); rows = [{"id": "a", "year": "2019", "value": "NA", "treated": "0"},
            {"id": "b", "year": "2019", "value": "2", "treated": "0"}]
        steps = [{"id": "missing", "operation": "normalize_missing", "column": "value", "reason": "Declared code normalization."},
            {"id": "exclude", "operation": "exclude_values", "column": "id", "values": ["b"], "reason": "Synthetic preregistered exclusion."}]
        _, result, _, history = contracts._clean_rows(fields, rows, variables, steps)
        self.assertEqual(result[0]["value"], "")
        self.assertEqual(history[1]["rows_before"], 2)
        self.assertEqual(history[1]["rows_after"], 1)
        self.assertEqual(history[1]["rows_changed_or_excluded"], 1)

    def test_runtime_requires_existing_runner_and_never_mutates_raw(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "approved experiment runner"):
            contracts.clean(self.project, self.dataset, "data/processed/fixture.csv", "reports/data-cleaning/fixture.json")
        self.assertFalse((self.project/"data/processed").exists())

    def test_approved_runtime_writes_exact_outputs_and_reuses_identical_bytes(self):
        self.spec["cleaning_steps"] = self.steps(); self.save()
        original = self.source.read_bytes(); output = "data/processed/fixture.csv"; receipt = "reports/data-cleaning/fixture.json"
        with patch.dict(os.environ, {"RESEARCH_OS_RUN_ID": "clean-fixture"}), patch("scripts.experiment_runner.approved_plan", return_value=(self.approved(), 0)):
            first = contracts.clean(self.project, self.dataset, output, receipt)
            second = contracts.clean(self.project, self.dataset, output, receipt)
        self.assertEqual(first, second)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(first["output"]["sha256"], sha(self.project/output))
        self.assertEqual(first["rows_before"], 4)
        self.assertEqual(first["rows_after"], 4)
        self.assertEqual(first, read(self.project/receipt))

    def test_runtime_refuses_unapproved_outputs_inputs_and_generated_tampering(self):
        output, receipt = "data/processed/fixture.csv", "reports/data-cleaning/fixture.json"
        plan = self.approved(); plan["runs"][0]["inputs"] = []
        with patch.dict(os.environ, {"RESEARCH_OS_RUN_ID": "clean-fixture"}), patch("scripts.experiment_runner.approved_plan", return_value=(plan, 0)):
            with self.assertRaisesRegex(ValueError, "every data contract source"):
                contracts.clean(self.project, self.dataset, output, receipt)
        plan = self.approved(); (self.project/"data/processed").mkdir(); (self.project/output).write_text("tampered", encoding="utf-8")
        with patch.dict(os.environ, {"RESEARCH_OS_RUN_ID": "clean-fixture"}), patch("scripts.experiment_runner.approved_plan", return_value=(plan, 0)):
            with self.assertRaisesRegex(ValueError, "overwrite"):
                contracts.clean(self.project, self.dataset, output, receipt)
            with self.assertRaisesRegex(ValueError, "exact approved run"):
                contracts.clean(self.project, self.dataset, "data/raw/fixture.csv", receipt)
        self.assertFalse((self.project/receipt).exists())

    def test_report_tamper_fails_without_marking_science_complete(self):
        result = contracts.refresh(self.project, self.dataset)
        self.assertTrue(result["pass"])
        target = self.project/"reports/data-contracts/fixture.json"
        altered = read(target); altered["scientific_validity_verified"] = True; write(target, altered)
        self.assertTrue(contracts.validate_saved_report(self.project, self.dataset))


if __name__ == "__main__": unittest.main()
