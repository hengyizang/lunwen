"""Regression checks for the October cloud audit's actual failure boundaries."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ai_providers, api_orchestrator, model_runtime, model_spend


class CloudReadinessBoundaries(unittest.TestCase):
    def test_author_cannot_create_executor_facts_or_change_declared_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "projects/demo"
            (project / "experiments").mkdir(parents=True)
            (project / "experiments/plan.json").write_text(json.dumps({
                "runs": [{"expected_outputs": ["reports/measured.csv"]}]}))
            with patch.object(api_orchestrator, "ROOT", root):
                for path in ("experiments/registry.jsonl", "experiments/runs/a/stdout.txt",
                             "experiments/runs/a/metrics.csv", "results/value.csv",
                             "reports/measured.csv"):
                    with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Executor-owned"):
                        api_orchestrator.apply_bundle("demo", {"stage": "experiment-execution", "artifacts": [
                            {"path": path, "content": "unexecuted"}]}, "experiment-execution")
                api_orchestrator.apply_bundle("demo", {"stage": "experiment-design", "artifacts": [
                    {"path": "experiments/code/analysis.py", "content": "print('planned code')"}]})
            self.assertFalse((project / "experiments/registry.jsonl").exists())
            self.assertTrue((project / "experiments/code/analysis.py").exists())

    def test_lost_generation_response_keeps_reservation_and_blocks_second_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            model_spend.write(project, model_spend.initial())
            model_spend.grant(project, new_ceiling_cny=300, actor="fixture", run_id="grant")
            env = {"UUAPI_API_KEY": "test-credential", "UUAPI_BASE_URL": "https://gateway.example/v1",
                   "UUAPI_OPENAI_MODEL": "gpt-test", "DR_OS_REQUIRE_MODEL_AUTH": "1",
                   "DR_OS_MODEL_PRICING_JSON": '{"gpt-test":{"input_per_million":2.2,"output_per_million":11}}'}
            with patch.dict(os.environ, env, clear=True), patch(
                "scripts.ai_providers.urllib.request.urlopen", side_effect=TimeoutError("response lost")
            ) as transport:
                args = dict(run_id="fixture", stage="intake", role="writer", provider="uuapi-openai",
                            prompt="fixture", max_output_tokens=100)
                with self.assertRaises(ai_providers.ProviderError):
                    model_runtime.call(project, **args)
                with self.assertRaisesRegex(model_runtime.ModelBudgetError, "reconciliation"):
                    model_runtime.call(project, **args)
            self.assertEqual(transport.call_count, 1)
            control = model_spend.read(project)
            self.assertEqual(len(control["reservations"]), 1)
            self.assertEqual(control["spent_cny"], 0)

    def test_non_json_response_is_not_silently_retried(self):
        from tests.test_uuapi_provider import FakeResponse
        with patch("scripts.ai_providers.urllib.request.urlopen", return_value=FakeResponse([])) as transport:
            with self.assertRaises(ai_providers.ProviderError):
                ai_providers._request("https://gateway.example/v1/responses", {}, {})
        self.assertEqual(transport.call_count, 1)

    def test_failed_remote_budget_checkpoint_blocks_transport(self):
        from scripts import cloud_checkpoint
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);model_spend.write(project,model_spend.initial())
            model_spend.grant(project,new_ceiling_cny=300,actor='Fixture',run_id='grant')
            env={'UUAPI_API_KEY':'fixture-key','UUAPI_BASE_URL':'https://example.invalid/v1','UUAPI_OPENAI_MODEL':'gpt-test',
                 'DR_OS_REQUIRE_MODEL_AUTH':'1','DR_OS_MODEL_PRICING_JSON':'{"gpt-test":{"input_per_million":2.2,"output_per_million":11}}'}
            with patch.dict(os.environ,env,clear=True),patch.object(cloud_checkpoint,'sync_billing',side_effect=cloud_checkpoint.CheckpointError('push failed')),patch.object(ai_providers,'call') as transport:
                with self.assertRaises(cloud_checkpoint.CheckpointError):
                    model_runtime.call(project,run_id='fixture',stage='intake',role='writer',provider='uuapi-openai',prompt='fixture',max_output_tokens=100)
                transport.assert_not_called()
            self.assertEqual(len(model_spend.read(project)['reservations']),1)

    def test_api_cannot_rewrite_inputs_of_a_g3_approved_experiment(self):
        from scripts.cloud_pipeline_acceptance import fixture
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project=root/'projects/acceptance-fixture';fixture(project)
            with patch.object(api_orchestrator,'ROOT',root):
                for path in ('experiments/plan.json','experiments/budget.json','experiments/code/measure.py'):
                    with self.subTest(path=path),self.assertRaisesRegex(ValueError,'Executor-owned'):
                        api_orchestrator.safe_target('acceptance-fixture',path)
