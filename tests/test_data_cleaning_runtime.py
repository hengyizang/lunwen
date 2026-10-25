"""Standalone cloud-fixture execution and pre-G3-freeze preparation checks."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import data_cleaning_runtime as runtime, data_contracts as contracts
from scripts.research_artifacts import read, sha, write
from tests import test_data_contracts as fixtures


class StandaloneCleaningTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.DataContractTests("test_complete_dictionary_audit_is_read_only_and_not_a_scientific_gate")
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        self.fixture, self.project = fixture, fixture.project
        fixture.spec["cleaning_steps"] = fixture.steps(); fixture.save()
        self.output, self.receipt = "data/processed/fixture.csv", "reports/data-cleaning/fixture.json"

    def execute(self):
        with patch.dict(os.environ, {"RESEARCH_OS_RUN_ID": "synthetic-approved-fixture"}):
            return runtime.execute(self.project, "data/contracts/fixture.json", "fixture", self.output, self.receipt)

    def open_g3(self):
        write(self.project/"state/run.json", {"stage": "experiment-design", "gate": "G3", "status": "awaiting_work"})

    def preview(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            return contracts.preview_cleaning(self.project, "fixture")

    def test_copied_runtime_executes_without_native_package_plan_state_or_network(self):
        # This is an isolated software fixture, not scientific approval. Actual
        # launch authority belongs to the real runner preflight tested elsewhere.
        script = self.project/"analysis/data_cleaning_runtime.py"; script.parent.mkdir()
        script.write_bytes(Path(runtime.__file__).read_bytes())
        original = self.fixture.source.read_bytes()
        environment = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "RESEARCH_OS_RUN_ID"}}
        environment["RESEARCH_OS_RUN_ID"] = "synthetic-approved-fixture"
        result = subprocess.run([sys.executable, str(script), "--contract", "data/contracts/fixture.json", "--dataset-id", "fixture",
            "--output", self.output, "--receipt", self.receipt], cwd=self.project, env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.project/"state").exists())
        self.assertFalse((self.project/"experiments").exists())
        self.assertEqual(self.fixture.source.read_bytes(), original)
        receipt = read(self.project/self.receipt)
        self.assertEqual(receipt["output"]["sha256"], sha(self.project/self.output))
        self.assertFalse(receipt["gate_approved"])
        self.assertFalse(receipt["scientific_validity_verified"])

    def test_runtime_requires_runner_id_and_own_reviewed_digest(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "approved cloud executor"):
            runtime.execute(self.project, "data/contracts/fixture.json", "fixture", self.output, self.receipt)
        self.fixture.spec["cleaning_runtime_sha256"] = "0"*64; self.fixture.save()
        with self.assertRaisesRegex(ValueError, "runtime hash"):
            self.execute()
        self.assertFalse((self.project/self.output).exists())

    def test_runtime_hash_changes_and_raw_output_alias_are_refused(self):
        self.fixture.source.write_text("changed source", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source hash"):
            self.execute()
        self.fixture.replace_source("id,year,value,treated\na,2019,100,0\na,2020,200,1\n")
        self.output = "data/raw/fixture.csv"
        with self.assertRaisesRegex(ValueError, "disjoint"):
            self.execute()

    def test_controller_and_standalone_transforms_match_exact_output_and_formulas(self):
        result = self.execute()
        fields = [item["name"] for item in self.fixture.spec["variables"]]
        rows = runtime.csv.DictReader(io_string(self.fixture.source.read_text()))
        variables = {item["name"]: item for item in self.fixture.spec["variables"]}
        expected_fields, expected_rows, expected_definitions, expected_history = contracts._clean_rows(
            fields, list(rows), variables, self.fixture.spec["cleaning_steps"])
        output_fields, output_rows = runtime.csv.DictReader(io_string((self.project/self.output).read_text())).fieldnames, list(runtime.csv.DictReader(io_string((self.project/self.output).read_text())))
        self.assertEqual(output_fields, expected_fields)
        self.assertEqual(output_rows, expected_rows)
        self.assertEqual(result["output_dictionary"], list(expected_definitions.values()))
        self.assertEqual(result["steps"], expected_history)

    def test_nonfinite_unsupported_operation_and_overwrite_fail_closed(self):
        self.fixture.spec["cleaning_steps"][0]["factor"] = float("inf"); self.fixture.save()
        with self.assertRaisesRegex(ValueError, "finite"):
            self.execute()
        self.fixture.spec["cleaning_steps"] = [{"id": "custom", "reason": "Invalid unreviewed operation.", "operation": "eval", "column": "value"}]
        self.fixture.save()
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.execute()
        self.fixture.spec["cleaning_steps"] = self.fixture.steps(); self.fixture.save()
        self.execute()
        (self.project/self.output).write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.execute()

    def test_preview_prepares_data_without_an_experiment_and_is_replayable(self):
        self.open_g3(); original = self.fixture.source.read_bytes()
        result = self.preview()
        self.assertEqual(result["purpose"], "data_preparation_only")
        self.assertFalse(result["experiment_executed"])
        self.assertEqual(result["output"]["path"], "data/processed-preview/fixture.csv")
        self.assertEqual(self.fixture.source.read_bytes(), original)
        self.assertEqual(contracts.validate_preview(self.project, "fixture"), [])
        self.assertEqual(self.preview(), result)
        self.assertFalse((self.project/"experiments/registry.jsonl").exists())

    def test_preview_is_blocked_after_freeze_attempts_or_outside_open_g3(self):
        self.open_g3()
        write(self.project/"papers/P01/preregistration.json", {"status": "frozen", "files": []})
        with self.assertRaisesRegex(ValueError, "precede frozen"):
            self.preview()
        (self.project/"papers/P01/preregistration.json").unlink()
        registry = self.project/"experiments/registry.jsonl"; registry.parent.mkdir()
        registry.write_text('{"status":"failed"}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "after experimental attempts"):
            self.preview()
        registry.unlink()
        write(self.project/"state/run.json", {"stage": "experiment-execution", "gate": "G4", "status": "awaiting_work"})
        with self.assertRaisesRegex(ValueError, "open G3"):
            self.preview()

    def test_preparation_changes_keep_prior_recipe_and_tampering_invalidates(self):
        self.open_g3(); first = self.preview()
        self.fixture.spec["cleaning_steps"][0]["offset"] = 1; self.fixture.save()
        self.assertTrue(contracts.validate_preview(self.project, "fixture"))
        second = self.preview()
        self.assertNotEqual(first["output"]["sha256"], second["output"]["sha256"])
        archives = list((self.project/"reports/data-cleaning/preparation-history/fixture").glob("*.json"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(read(archives[0]), first)
        (self.project/second["output"]["path"]).write_text("tampered", encoding="utf-8")
        self.assertTrue(contracts.validate_preview(self.project, "fixture"))


def io_string(value):
    import io
    return io.StringIO(value)


if __name__ == "__main__": unittest.main()
