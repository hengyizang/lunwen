"""New scientific preparation uses the existing cloud boundary and preserves history."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import artifact_ownership, cloud_job, literaturectl


class CompendiumEntrypointTests(unittest.TestCase):
    def test_existing_cloud_request_accepts_only_the_declared_judgment_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / 'program').mkdir()
            source = project / 'program/operation.json'
            operation = {'action': 'scientific_judgment', 'task': 'claim_evidence',
                         'request_file': 'program/claims.json'}
            source.write_text(json.dumps(operation))
            accepted, binding = cloud_job.literature_operation(project, 'program/operation.json')
            self.assertEqual(accepted, operation)
            self.assertEqual(binding['path'], 'program/operation.json')
            source.write_text(json.dumps({**operation, 'override_rights': True}))
            with self.assertRaises(cloud_job.CloudJobError):
                cloud_job.literature_operation(project, 'program/operation.json')
            with patch.dict('os.environ', {'DR_OS_CLOUD_EXECUTOR': '1'}):
                with self.assertRaisesRegex(ValueError, 'unknown scientific judgment'):
                    literaturectl.execute_operation(project, {**operation, 'task': 'invent_support'})

    def test_preparation_with_missing_evidence_does_not_claim_scientific_completion(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'DR_OS_CLOUD_EXECUTOR': '1'}):
            project = Path(directory)
            (project / 'papers/P01').mkdir(parents=True)
            result = literaturectl.execute_operation(project, {'action': 'research_case', 'paper_id': 'P01'})
            self.assertEqual(result['status'], 'preparation')
            self.assertTrue(result['missing_evidence'])
            self.assertFalse(result['limits']['scientific_validity_verified'])
            self.assertFalse(result['limits']['external_publication'])
            self.assertEqual(result['limits']['paid_model_calls'], 0)
            with self.assertRaises(ValueError):
                literaturectl.execute_operation(project, {'action': 'research_case', 'paper_id': '../P01'})

    def test_author_cannot_overwrite_prepared_release_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ('papers/P01/release-preparation/old/README.md',
                             'experiments/supplemental/P01/I001/s001/papers/P01/release-preparation/old/README.md'):
                self.assertTrue(artifact_ownership.executor_owned(root, relative))
            self.assertFalse(artifact_ownership.executor_owned(root, 'papers/P01/research-case.json'))
