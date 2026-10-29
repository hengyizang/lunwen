"""Native research-tool increments share existing cloud and review authority."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import artifact_ownership, cloud_job, context_efficiency, literaturectl, research_toolkit


class ResearchToolIncrementIntegrationTests(unittest.TestCase):
    def test_useful_mechanisms_for_all_catalog_tools_have_native_and_test_paths(self):
        root = research_toolkit.ROOT
        coverage = json.loads((root / "integrations/research-automation-coverage.json").read_text(encoding="utf-8"))
        self.assertEqual({row["id"] for row in coverage["tools"]}, set(research_toolkit.catalog()))
        self.assertIn("ai-scientist", {row["id"] for row in coverage["tools"]})
        for tool in coverage["tools"]:
            self.assertTrue(tool["mechanisms"])
            self.assertTrue(tool["native_implementations"] and tool["verification"])
            for relative in tool["native_implementations"] + tool["verification"]:
                self.assertTrue((root / relative).is_file(), relative)

    def test_every_declared_native_operation_has_existing_owner_cloud_dispatch(self):
        catalog = research_toolkit.catalog()
        self.assertIn("ai-scientist", catalog)
        for tool in catalog.values():
            self.assertTrue(set(tool["native_operations"]).issubset(cloud_job.LITERATURE_OPERATIONS), tool["id"])
        self.assertEqual(set(catalog["mirothinker"]["stages"]), research_toolkit.STAGES)

    def test_current_nonpaid_operations_dispatch_without_execution_options(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(directory)
            (project / "program").mkdir()
            for action in ("research_iteration", "research_frontier", "research_search_tree"):
                operation = {"action": action, "request_file": "program/current-request.json"}
                (project / "program/operation.json").write_text(json.dumps(operation), encoding="utf-8")
                checked, _ = cloud_job.literature_operation(project, "program/operation.json")
                with patch("scripts." + action + ".refresh", return_value={"paid_calls": 0}) as prepare:
                    self.assertEqual(literaturectl.execute_operation(project, checked), {"paid_calls": 0})
                    prepare.assert_called_once_with(project, operation["request_file"])
                for extra in ("execute", "approve", "model"):
                    (project / "program/operation.json").write_text(json.dumps({**operation, extra: True}), encoding="utf-8")
                    with self.assertRaises(cloud_job.CloudJobError):
                        cloud_job.literature_operation(project, "program/operation.json")

    def test_generated_history_and_custom_request_envelopes_do_not_enter_independent_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "program").mkdir()
            for name in ("research_iteration", "research_frontier", "research_search_tree"):
                relative = "program/custom-" + name + ".json"
                (project / relative).write_text(json.dumps({"kind": name, "task": "AUTHOR_PREFERRED_OUTCOME"}), encoding="utf-8")
                self.assertIn(relative, context_efficiency.instruction_paths(project))
                report = "reports/" + name.replace("_", "-") + "/old.json"
                self.assertTrue(context_efficiency.operational_path(report, exclude_reviews=True))
                self.assertTrue(artifact_ownership.executor_owned(project, report))
            self.assertFalse(context_efficiency.operational_path("evidence/contrary-observation.txt", exclude_reviews=True))
