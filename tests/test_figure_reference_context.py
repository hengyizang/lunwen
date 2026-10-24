"""Bounded reference context and cloud checkpoint regressions, no paid calls.

Synthetic paper leads test source binding only; they are not scientific data or
evidence that a reference layout improves a manuscript.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import cloud_checkpoint as checkpoint
from scripts import context_efficiency, figure_gallery as gallery, figure_reference_context
from scripts.research_artifacts import sha, write


class FigureReferenceContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        cloud = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"})
        cloud.start()
        self.addCleanup(cloud.stop)
        rows = [{"id": "iclr2025-fixture-" + str(i),
                 "title": "Time Series Prediction Architecture " + str(i),
                 "authors": ["Synthetic Author"], "venue": "iclr", "year": 2025,
                 "pattern": "architecture", "tier": "oral",
                 "image": "images/iclr/final/iclr2025-fixture-" + str(i) + ".jpg",
                 "paper": "https://openreview.net/forum?id=synthetic-" + str(i),
                 "pdf_source": "https://openreview.net/pdf?id=synthetic-" + str(i)}
                for i in range(6)]
        raw = json.dumps(rows, ensure_ascii=False).encode()
        fixed = gallery._lock()
        fixed["metadata"] = {"path": "data/figures.json", "git_blob_sha": "0" * 40,
                             "sha256": hashlib.sha256(raw).hexdigest(),
                             "size_bytes": len(raw), "record_count": len(rows)}
        pinned = patch.object(gallery, "_lock", return_value=fixed)
        pinned.start()
        self.addCleanup(pinned.stop)
        with patch.object(gallery, "_download", return_value=raw):
            gallery.sync(self.project)
        self.result = gallery.search(self.project, "时间序列预测的架构图", top_k=8)
        self.ids = [row["id"] for row in self.result["candidates"]]

    def select(self, ids=None, binding=None):
        value = {"report": self.result["report_binding"] if binding is None else binding,
                 "figure_ids": self.ids[:2] if ids is None else ids}
        write(self.project / "program/figure-reference-context.json", value)

    def test_chinese_reference_context_preserves_sources_rights_and_boundary(self):
        self.select()
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid provider")):
            result = json.loads(figure_reference_context.context(self.project))
        self.assertEqual(result["kind"], "untrusted_layout_references")
        self.assertEqual(result["query"], "时间序列预测的架构图")
        self.assertEqual(result["report"], self.result["report_binding"])
        self.assertEqual(len(result["references"]), 2)
        source = result["references"][0]
        expected = self.result["candidates"][0]
        for key in ("id", "paper_url", "figure_url", "metadata_sha256"):
            self.assertEqual(source[key], expected[key])
        self.assertEqual(source["license"]["image_license"], "unknown")
        self.assertFalse(source["license"]["reuse_authorized"])
        self.assertEqual(result["boundary"], gallery.BOUNDARY)
        self.assertNotIn("scientific_completion_verified", result)

    def test_selecting_a_reference_outside_bound_report_is_rejected(self):
        self.select(ids=["not-in-this-report"])
        with self.assertRaisesRegex(ValueError, "not in the bound search results"):
            figure_reference_context.context(self.project)

    def test_changed_selector_hash_and_changed_report_are_rejected(self):
        binding = {**self.result["report_binding"], "sha256": "0" * 64}
        self.select(binding=binding)
        with self.assertRaisesRegex(ValueError, "selection changed"):
            figure_reference_context.context(self.project)
        self.select()
        target = self.project / self.result["report_binding"]["path"]
        report = json.loads(target.read_text(encoding="utf-8"))
        report["candidates"][0]["title"] = "Changed after reference selection"
        write(target, report)
        # Updating the selector hash alone does not forge a valid current search.
        self.select(binding={"path": self.result["report_binding"]["path"], "sha256": sha(target)})
        with self.assertRaisesRegex(ValueError, "content hash differs"):
            figure_reference_context.context(self.project)

    def test_at_most_five_unique_references_and_no_implicit_full_gallery(self):
        self.select(ids=self.ids[:5])
        self.assertEqual(len(json.loads(figure_reference_context.context(self.project))["references"]), 5)
        for ids in (self.ids, [], [self.ids[0], self.ids[0]], [17]):
            with self.subTest(ids=ids):
                self.select(ids=ids)
                with self.assertRaisesRegex(ValueError, "one to five unique"):
                    figure_reference_context.context(self.project)
        (self.project / "program/figure-reference-context.json").unlink()
        self.assertIn("No figure-reference selection", figure_reference_context.context(self.project))

    def test_context_filters_remove_gallery_bulk_duplicates_but_keep_science(self):
        excluded = ("literature/figure-gallery/index.json",
                    "literature/figure-gallery/index.receipt.json",
                    "reports/figure-gallery/abc/search.json",
                    "reports/figure-gallery/abc/packet.json",
                    "reports/figure-gallery-semantic/abc.json",
                    ".cache/figure-gallery-models/pinned/forge/data/image_emb.bin",
                    ".cache/figure-gallery-models/pinned/forge/data/text_emb.bin")
        for relative in excluded:
            for critic in (False, True):
                with self.subTest(path=relative, critic=critic):
                    self.assertTrue(context_efficiency.operational_path(relative, exclude_reviews=critic))
        retained = ("claims/claim-evidence.csv", "papers/P01/methods.md",
                    "papers/P01/paper-contract.json", "analysis/protocol.json",
                    "experiments/config.yaml", "program/core-thesis.json")
        for relative in retained:
            for critic in (False, True):
                with self.subTest(path=relative, critic=critic):
                    self.assertFalse(context_efficiency.operational_path(relative, exclude_reviews=critic))

    def test_checkpoint_retains_editable_formats_and_excludes_rehydratable_models(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as package:
            package.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            package.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>')
        pptx = "papers/P01/figures/method-overview.pptx"
        drawio = "papers/P01/figures/method-overview.drawio"
        files = {pptx: buffer.getvalue(), drawio: b'<mxfile><diagram><mxGraphModel/></diagram></mxfile>'}
        for relative, data in files.items():
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        caches = (".cache/figure-gallery-models/pinned/forge/models/text_model.onnx",
                  ".cache/figure-gallery-models/pinned/forge/data/image_emb.bin",
                  ".cache/figure-gallery-models/pinned/forge/models/tokenizer.json")
        for relative in caches:
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"re-download fixed reviewed asset; not checkpoint payload")
        entries = {entry["path"]: entry for entry in checkpoint.inventory(self.project)}
        for relative, data in files.items():
            self.assertFalse(checkpoint.excluded(relative))
            self.assertIn(relative, entries)
            self.assertEqual(entries[relative]["sha256"], hashlib.sha256(data).hexdigest())
        for relative in caches:
            self.assertTrue(checkpoint.excluded(relative))
            self.assertNotIn(relative, entries)
        artifact = self.project / "checkpoint-transfer"
        checkpoint.prepare(self.project, artifact, "123456")
        # Replay the controller's small-Git-files plus optional archive route on
        # a fresh project directory, checking binary source bytes after restore.
        fresh = self.project / "fresh-cloud-runner"
        for source in checkpoint.git_files(self.project):
            destination = fresh / source.relative_to(self.project)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        checkpoint.restore(fresh, artifact / "checkpoint.zip")
        for relative, data in files.items():
            self.assertEqual((fresh / relative).read_bytes(), data)
        for relative in caches:
            self.assertFalse((fresh / relative).exists())


if __name__ == "__main__":
    unittest.main()
