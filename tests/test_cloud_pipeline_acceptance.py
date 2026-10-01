import tempfile
import unittest
from pathlib import Path
from scripts import cloud_pipeline_acceptance as acceptance, experiment_runner, requirements_trace

class PipelineContractTests(unittest.TestCase):
    def test_fixture_is_explicit_and_plan_approval_binds_executable_code(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)/'acceptance-fixture'
            acceptance.fixture(project)
            plan,_=experiment_runner.approved_plan(project,project/'experiments/plan.json',project/'experiments/budget.json')
            self.assertEqual(experiment_runner.validate_plan(plan),[])
            self.assertIn('synthetic_acceptance_only',(project/'state/run.json').read_text())
            self.assertTrue(all(r['isolation']['kind']=='container' for r in plan['runs']))
            (project/'experiments/plan.json').write_text((project/'experiments/plan.json').read_text()+'\n')
            with self.assertRaises(experiment_runner.ExperimentError):
                experiment_runner.approved_plan(project,project/'experiments/plan.json',project/'experiments/budget.json')

    def test_verified_trace_cannot_be_claimed_from_code_file_existence(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'trace.json'
            row={'id':'R1','implementation':'implemented','acceptance':'verified','remaining':'none',
                 'evidence':['scripts/cloud_checkpoint.py'],'tests':['tests/test_cloud_checkpoint.py']}
            path.write_text(json.dumps({'schema_version':'2.0','execution_mode':'cloud_only','requirements':[row]}))
            self.assertTrue(requirements_trace.validate(path))
