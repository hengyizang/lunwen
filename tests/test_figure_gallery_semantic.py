from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import figure_gallery_semantic as semantic
from scripts import artifact_ownership


class SemanticFigureTests(unittest.TestCase):
    def test_pinned_byte_identity_rejects_equal_length_mutation(self):
        data = b"source-data"
        pinned = {"path": "fixture", "bytes": len(data), "git_blob_sha1": hashlib.sha1(b"blob 11\0" + data).hexdigest()}
        self.assertEqual(semantic.verify_bytes(data, pinned), hashlib.sha256(data).hexdigest())
        with self.assertRaises(ValueError):
            semantic.verify_bytes(b"source-datb", pinned)

    def test_bilingual_expansion_preserves_query_and_scientific_terms(self):
        query = "时间序列预测的架构图"
        text = semantic.clip_text(query)
        self.assertIn("time series", text)
        self.assertIn("architecture", text)
        self.assertIn(query, text)

    def test_cloud_guard_precedes_download(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "DR_OS_CLOUD_EXECUTOR": "0"}), tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "cloud runner"):
                semantic.assets(Path(directory))

    def test_semantic_claim_requires_actual_protected_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "execution receipt"):
                semantic.validate_report(Path(directory), {"retrieval": {"method": "cpu_clip_bm25", "semantic_image_search": True, "semantic_evidence": {}}})

    def test_generated_reports_and_native_exports_are_executor_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            for relative in ("literature/figure-gallery/index.json", "reports/figure-gallery-semantic/id.json",
                             "reports/figure-story/demo.json", "papers/P01/figures/main.editable.pptx",
                             "papers/P01/figures/main.editable-export.json"):
                self.assertTrue(artifact_ownership.executor_owned(project, relative))
            self.assertFalse(artifact_ownership.executor_owned(project, "papers/P01/figures/main.spec.json"))


if __name__ == "__main__":
    unittest.main()
