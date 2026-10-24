"""Nonpaid owner/queue dispatch stays on the controlled figure tools."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import cloud_job, literaturectl


class FigureOperationTests(unittest.TestCase):
    def test_all_owner_actions_accept_exact_envelopes_and_forbid_paid_extensions(self):
        examples = [{"action": "figure_gallery_sync"},
                    {"action": "figure_gallery_search", "query": "时间序列架构图", "semantic": False},
                    {"action": "figure_story", "operation": "prepare", "request_file": "program/brief.json"},
                    {"action": "editable_figure_export", "request_file": "program/export.json"},
                    {"action": "editable_figure_verify", "receipt": "papers/P01/figures/main.editable-export.json"}]
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            target = project / "program/operation.json"
            target.parent.mkdir()
            for operation in examples:
                with self.subTest(action=operation["action"]):
                    target.write_text(json.dumps(operation), encoding="utf-8")
                    self.assertEqual(cloud_job.literature_operation(project, "program/operation.json")[0], operation)
                    target.write_text(json.dumps({**operation, "allow_paid": True}), encoding="utf-8")
                    with self.assertRaises(cloud_job.CloudJobError):
                        cloud_job.literature_operation(project, "program/operation.json")

    def test_metadata_dispatch_never_provisions_semantic_model(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with patch("scripts.figure_gallery.search", return_value={"paid_api_calls": 0}) as search, patch("scripts.figure_gallery_semantic.provision", side_effect=AssertionError("not needed")):
                self.assertEqual(literaturectl.execute_operation(project, {"action": "figure_gallery_search", "query": "architecture"})["paid_api_calls"], 0)
                search.assert_called_once_with(project, "architecture")
            with self.assertRaisesRegex(ValueError, "explicit boolean"):
                literaturectl.execute_operation(project, {"action": "figure_gallery_search", "query": "architecture", "semantic": "true"})

    def test_semantic_dispatch_provisions_before_execution(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            calls = []
            with patch("scripts.figure_gallery_semantic.provision", side_effect=lambda _: calls.append("provision")), patch("scripts.figure_gallery_semantic.search", side_effect=lambda *a, **kw: calls.append("actual_search") or {}):
                literaturectl.execute_operation(project, {"action": "figure_gallery_search", "query": "architecture", "semantic": True, "top_k": 3})
            self.assertEqual(calls, ["provision", "actual_search"])

    def test_verify_dispatch_uses_a_confined_path(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            target = project / "papers/P01/figures/main.editable-export.json"
            target.parent.mkdir(parents=True)
            target.write_text("{}")
            with patch("scripts.editable_figures.verify_export", return_value={}) as verify:
                literaturectl.execute_operation(project, {"action": "editable_figure_verify", "receipt": target.relative_to(project).as_posix()})
                verify.assert_called_once_with(project, target)
            with self.assertRaises(ValueError):
                literaturectl.execute_operation(project, {"action": "editable_figure_verify", "receipt": "../receipt.json"})


if __name__ == "__main__":
    unittest.main()
