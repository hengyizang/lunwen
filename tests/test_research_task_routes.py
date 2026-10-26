"""New task entry points reuse the current nonpaid cloud controller."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import artifact_ownership, cloud_job, literaturectl
from scripts.research_artifacts import write


class ResearchTaskRouteTests(unittest.TestCase):
    def test_nonpaid_owner_requests_dispatch_to_the_existing_controller(self):
        cases = [
            ("data_row_provenance", "scripts.data_row_provenance.refresh", "program/rows.json"),
            ("literature_source_trace", "scripts.literature_source_tasks.refresh", "program/trace.json"),
            ("literature_screening_advice", "scripts.literature_source_tasks.refresh", "program/screen.json"),
            ("literature_search_strategy", "scripts.literature_search_strategy.refresh", "program/search.json"),
            ("literature_synthesis", "scripts.literature_synthesis.refresh", "program/synthesis.json"),
            ("diagram_mermaid", "scripts.diagram_mermaid.refresh", "program/mermaid.json"),
        ]
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(temporary)
            for action, target, request in cases:
                operation = {"action": action, "request_file": request}
                write(project / "program/operation.json", operation)
                checked, _ = cloud_job.literature_operation(project, "program/operation.json")
                with self.subTest(action=action), patch(target, return_value={"paid_calls": 0}) as execute:
                    result = literaturectl.execute_operation(project, checked)
                    self.assertEqual(result["paid_calls"], 0)
                    self.assertIn(request, execute.call_args.args)
                    if action == "literature_source_trace":
                        self.assertEqual(execute.call_args.args[1], "source_trace")
                    if action == "literature_screening_advice":
                        self.assertEqual(execute.call_args.args[1], "screening_advice")

    def test_preparation_receives_actual_dataset_identity_without_reading_secrets(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), \
             patch("scripts.data_row_provenance.prepare", return_value={"records": []}) as prepare:
            literaturectl.execute_operation(Path("unused"), {"action": "data_row_prepare", "dataset_id": "real-id", "key_columns": ["id"]})
        self.assertEqual(prepare.call_args.args[1], "real-id")
        self.assertEqual(prepare.call_args.kwargs["key_columns"], ["id"])

    def test_new_reports_are_executor_owned_and_cannot_author_human_approvals(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            for root in ("data-row-provenance", "literature-source-tasks", "literature-search-strategy", "literature-synthesis", "diagram-mermaid"):
                self.assertTrue(artifact_ownership.executor_owned(project, f"reports/{root}/report.json"))
            for action in ("data_row_provenance", "literature_source_trace", "literature_screening_advice", "literature_search_strategy", "literature_synthesis", "diagram_mermaid"):
                for key in ("execute", "approve", "model", "formal_decision"):
                    write(project / "program/op.json", {"action": action, key: True})
                    with self.subTest(action=action, key=key), self.assertRaises(cloud_job.CloudJobError):
                        cloud_job.literature_operation(project, "program/op.json")

    def test_research_task_execution_still_requires_cloud(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}), \
             patch("scripts.literature_synthesis.refresh") as execute:
            with self.assertRaisesRegex(ValueError, "cloud"):
                literaturectl.execute_operation(Path("unused"), {"action": "literature_synthesis"})
        execute.assert_not_called()
