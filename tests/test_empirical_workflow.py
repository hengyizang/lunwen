"""Native controls compose without new permissions or paid service calls."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import empirical_workflow as workflow, data_contracts, data_cleaning_runtime
from scripts import artifact_ownership, cloud_research_steps
from scripts.research_artifacts import read, sha, write
from tests import test_data_contracts as data_fixtures
from tests import test_economic_data as economic_fixtures


class EmpiricalWorkflowTests(unittest.TestCase):
    def setUp(self):
        fixture = data_fixtures.DataContractTests("test_complete_dictionary_audit_is_read_only_and_not_a_scientific_gate")
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        self.fixture = fixture; self.project = fixture.project
        write(self.project/"papers/P01/paper-contract.json", {"datasets": ["fixture"], "empirical_workflow": {"data_contract_ids": ["fixture"]}})

    def test_selected_contract_is_required_and_missing_input_cannot_be_silently_disabled(self):
        self.assertTrue(workflow.gate_errors(self.project, "G3"))
        data_contracts.refresh(self.project, "fixture")
        self.assertEqual(workflow.gate_errors(self.project, "G3"), [])
        write(self.project/"papers/P01/paper-contract.json", {"datasets": ["fixture"]})
        (self.project/"data/contracts/fixture.json").unlink()
        self.assertTrue(workflow.gate_errors(self.project, "G3"))

    def test_other_designs_without_empirical_configuration_remain_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            write(project/"papers/P01/paper-contract.json", {"study_route": "theory", "datasets": []})
            for gate in ("G3", "G4", "G5"):
                self.assertEqual(workflow.gate_errors(project, gate, "P01"), [])
            self.assertEqual(workflow.refresh(project, "experiment-design")["status"], "not_configured")

    def test_freeze_includes_contract_registry_manifest_and_original_csv(self):
        inputs = {p.relative_to(self.project).as_posix() for p in workflow.preregistration_inputs(self.project, "P01")}
        self.assertTrue({"data/contracts/fixture.json", "data/datasets.jsonl", "data/manifests/fixture.json", "data/raw/fixture.csv"} <= inputs)
        self.fixture.source.write_text("changed original")
        with self.assertRaisesRegex(ValueError, "invalid data contract"):
            workflow.preregistration_inputs(self.project, "P01")

    def test_declared_features_and_ids_cannot_be_malformed_or_cross_paper(self):
        for value in ({"data_contract_ids": ["other"]}, {"data_contract_ids": ["../escape"]}, {"causal_design": "yes"}, {"arbitrary_command": "bad"}):
            write(self.project/"papers/P01/paper-contract.json", {"datasets": ["fixture"], "empirical_workflow": value})
            self.assertTrue(workflow.gate_errors(self.project, "G3"))

    def cleaning_run(self):
        runtime = self.project/"analysis/data_cleaning_runtime.py"
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_bytes(Path(data_cleaning_runtime.__file__).read_bytes())
        return {"paper_id": "P01", "cwd": ".", "run_id": "clean",
                "argv": ["python", "analysis/data_cleaning_runtime.py", "--contract", "data/contracts/fixture.json",
                         "--dataset-id", "fixture", "--output", "data/processed/fixture.csv", "--receipt", "reports/data-cleaning/fixture.json"],
                "expected_outputs": ["data/processed/fixture.csv", "reports/data-cleaning/fixture.json"],
                "inputs": [*data_contracts.audit(self.project, "fixture")["inputs"], {"path": "analysis/data_cleaning_runtime.py", "sha256": sha(runtime)}]}

    def test_native_cleaning_preflight_requires_exact_command_runtime_inputs_and_outputs(self):
        run = self.cleaning_run()
        workflow.preflight_run(self.project, run)
        self.assertTrue(workflow.cloud_outputs_allowed(self.project, run))
        for mutate in (lambda r:r["argv"].append("--arbitrary"), lambda r:r.update(inputs=[]),
                       lambda r:r.update(expected_outputs=["data/raw/fixture.csv"]), lambda r:r.update(cwd="analysis")):
            changed = copy.deepcopy(run); mutate(changed)
            with self.assertRaises(ValueError):
                workflow.preflight_run(self.project, changed)
        (self.project/"analysis/data_cleaning_runtime.py").write_text("different code")
        with self.assertRaisesRegex(ValueError, "reviewed"):
            workflow.preflight_run(self.project, run)

    def test_ordinary_custom_experiments_keep_existing_command_semantics(self):
        code = self.project/"analysis/custom.py"; code.parent.mkdir(); code.write_text("# ordinary frozen method")
        workflow.preflight_run(self.project, {"paper_id": "P01", "argv": ["python", "analysis/custom.py", "--design", "x", "--spec", "y", "--data", "z"]})
        self.assertTrue(workflow.cloud_outputs_allowed(self.project, {"expected_outputs": ["results/actual.json"]}))
        self.assertFalse(workflow.cloud_outputs_allowed(self.project, {"paper_id": "P01", "argv": [], "expected_outputs": ["data/raw/overwrite.csv"]}))

    def test_prepared_data_can_be_frozen_and_changed_preview_blocks(self):
        write(self.project/"state/run.json", {"stage": "experiment-design", "gate": "G3", "status": "awaiting_work"})
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            data_contracts.preview_cleaning(self.project, "fixture")
        paths = {p.relative_to(self.project).as_posix() for p in workflow.preregistration_inputs(self.project, "P01")}
        self.assertIn("data/processed-preview/fixture.csv", paths)
        (self.project/"data/processed-preview/fixture.csv").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "stale prepared"):
            workflow.preregistration_inputs(self.project, "P01")

    def test_new_outputs_are_protected_from_author_models(self):
        from scripts import cloud_checkpoint
        target = self.project/"data/processed-preview/fixture.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("id,value\na,1\n", encoding="utf-8")
        entry = next(row for row in cloud_checkpoint.inventory(self.project) if row["path"] == "data/processed-preview/fixture.csv")
        self.assertEqual(entry["storage"], "artifact")
        self.assertNotIn(target, cloud_checkpoint.git_files(self.project))
        for relative in ("reports/data-contracts/fixture.json", "reports/data-cleaning/fixture.json", "reports/empirical-reporting/P01.json",
                         "evidence/economic-data/fixture/latest.json", "data/raw/economic-data/fixture/source.json", "data/processed-preview/fixture.csv",
                         "papers/P01/reviews/empirical-design.json", "papers/P01/tables/empirical-estimates.csv"):
            self.assertTrue(artifact_ownership.executor_owned(self.project, relative), relative)
        self.assertFalse(artifact_ownership.executor_owned(self.project, "data/contracts/fixture.json"))

    def test_g3_preview_operation_and_audit_use_existing_queue(self):
        write(self.project/"state/run.json", {"stage": "experiment-design", "gate": "G3", "status": "awaiting_work"})
        write(self.project/"program/cloud-operations.json", {"operations": [
            {"stage": "experiment-design", "action": "data_contract", "dataset_id": "fixture"},
            {"stage": "experiment-design", "action": "data_cleaning_preview", "dataset_id": "fixture"}]})
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            report = cloud_research_steps.after_write(self.project, "experiment-design")
        self.assertEqual(report["operation_errors"], [])
        self.assertEqual(data_contracts.validate_preview(self.project, "fixture"), [])


class EconomicOwnerControlTests(unittest.TestCase):
    def test_existing_owner_control_can_bind_exact_api_scope_without_inventing_response_hash(self):
        fixture = economic_fixtures.EconomicDataTests("test_metadata_only_does_not_acquire_observations_or_assert_licence")
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.rights()
        (fixture.project/"state/data-authorizations.json").unlink()
        manifest = fixture.project/"data/manifests/synthetic-econ.json"
        result = cloud_research_steps.authorize_data(fixture.project, "data/manifests/synthetic-econ.json", sha(manifest), "Synthetic owner", "fixture-owner-action")
        self.assertTrue(result["cloud_use_confirmed"])
        self.assertEqual(result["sha256"], sha(manifest))
        # No request transport or scientific gate was invoked by authorization.
        self.assertEqual(fixture.urls, [])
        self.assertFalse((fixture.project/"experiments/registry.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
