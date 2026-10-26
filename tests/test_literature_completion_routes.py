import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import cloud_job, literaturectl, artifact_ownership
from scripts.research_artifacts import write


class LiteratureCompletionRoutes(unittest.TestCase):
    def test_all_new_operations_follow_the_existing_nonpaid_cloud_entry(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(directory)
            for suffix in ("semantic", "pdf", "zotero", "roles", "comparison", "paperqa"):
                action = "literature_" + suffix
                relative = "program/literature-" + suffix + ".json"
                operation = {"action": action, "request_file": relative}
                write(project / "program/operation.json", operation)
                checked, _ = cloud_job.literature_operation(project, "program/operation.json")
                with patch("scripts." + action + ".refresh", return_value={"paid_calls": 0}) as call:
                    literaturectl.execute_operation(project, checked)
                    self.assertEqual(call.call_args.args[:2], (project, relative))
                    if suffix in {"comparison", "paperqa"}:
                        self.assertIs(call.call_args.kwargs["execute"], False)
                self.assertTrue(artifact_ownership.executor_owned(project, "reports/literature-" + suffix + "/report.json"))

    def test_nonpaid_owner_cannot_hide_paid_execution_in_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            for suffix in ("comparison", "paperqa"):
                write(project / "program/operation.json", {"action": "literature_" + suffix, "execute": True})
                with self.assertRaisesRegex(cloud_job.CloudJobError, "nonpaid"):
                    cloud_job.literature_operation(project, "program/operation.json")

    def test_cloud_required_before_any_new_operation(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}), \
             patch("scripts.literature_zotero.refresh") as call:
            with self.assertRaisesRegex(ValueError, "cloud"):
                literaturectl.execute_operation(Path("unused"), {"action": "literature_zotero"})
            call.assert_not_called()
