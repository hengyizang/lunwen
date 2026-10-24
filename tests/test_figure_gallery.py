"""Cloud-run regressions for pinned metadata references; synthetic paper leads only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import figure_gallery as gallery


class FigureGalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.rows = [
            {"id": "iclr2025-ts", "title": "An Attention Architecture for Time Series Prediction",
             "authors": ["Synthetic Example"], "venue": "iclr", "year": 2025,
             "pattern": "architecture", "tier": "oral", "image": "images/iclr/final/iclr2025-ts.jpg",
             "paper": "https://openreview.net/forum?id=synthetic-ts",
             "pdf_source": "https://openreview.net/pdf?id=synthetic-ts"},
            {"id": "icml2024-mm", "title": "Multimodal Contrastive Learning",
             "authors": ["Fixture Author"], "venue": "icml", "year": 2024,
             "pattern": "framework", "tier": "spotlight", "award": "best",
             "image": "images/icml/final/icml2024-mm.jpg",
             "paper": "https://proceedings.mlr.press/v000/fixture.html",
             "pdf_source": "https://proceedings.mlr.press/v000/fixture.pdf"},
            {"id": "acl2023-lm", "title": "Efficient Language Model Pipeline",
             "authors": ["Fixture Author"], "venue": "acl", "year": 2023,
             "pattern": "pipeline", "image": "images/acl/final/acl2023-lm.jpg",
             "paper": "https://aclanthology.org/2023.synthetic/",
             "pdf_source": "https://aclanthology.org/2023.synthetic.pdf"},
        ]
        self.lock = gallery._lock()
        self.env = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def seed(self, rows=None):
        raw = json.dumps(self.rows if rows is None else rows, ensure_ascii=False).encode()
        self.lock["metadata"] = {"path": "data/figures.json", "git_blob_sha": "0" * 40,
                                 "sha256": hashlib.sha256(raw).hexdigest(),
                                 "size_bytes": len(raw), "record_count": len(self.rows if rows is None else rows)}
        self.pinned = patch.object(gallery, "_lock", return_value=self.lock)
        self.pinned.start()
        self.addCleanup(self.pinned.stop)
        with patch.object(gallery, "_download", return_value=raw) as download:
            receipt = gallery.sync(self.project)
            self.assertEqual(download.call_count, 1)
        return receipt

    def test_sync_preserves_exact_bytes_source_and_never_downloads_images(self):
        receipt = self.seed()
        self.assertTrue(receipt["metadata_only"])
        self.assertEqual(receipt["record_count"], 3)
        self.assertEqual(receipt["paid_api_calls"], 0)
        self.assertEqual(receipt["images_downloaded"], 0)
        with patch.object(gallery, "_download", side_effect=AssertionError("cache should avoid GET")):
            self.assertEqual(gallery.sync(self.project), receipt)
        loaded = gallery.load_index(self.project)
        self.assertEqual(loaded["figures"][1]["tier"], "best_paper")
        self.assertEqual(loaded["figures"][2]["tier"], "unknown")
        self.assertFalse(loaded["figures"][0]["image_inspected"])
        self.assertIn(self.lock["commit"], loaded["figures"][0]["figure_url"])

    def test_chinese_and_english_concepts_find_same_relevant_reference(self):
        self.seed()
        with patch("scripts.model_runtime.call", side_effect=AssertionError("paid models forbidden")):
            zh = gallery.search(self.project, "时间序列预测的架构图", top_k=1)
            en = gallery.search(self.project, "time series prediction architecture", top_k=1)
        self.assertEqual(zh["candidates"][0]["id"], "iclr2025-ts")
        self.assertEqual(en["candidates"][0]["id"], "iclr2025-ts")
        self.assertFalse(zh["retrieval"]["semantic_image_search"])
        self.assertEqual(zh["retrieval"]["method"], "metadata_bm25_bilingual_concepts")
        self.assertIn("concept:time_series", zh["candidates"][0]["matched_terms"])
        self.assertFalse(zh["candidates"][0]["score_is_probability"])

    def test_every_filter_applies_and_unknown_tier_never_becomes_poster(self):
        self.seed()
        result = gallery.search(self.project, "多模态框架图", venues=["icml"], years=[2024],
                                tiers=["best_paper"], patterns=["framework"], topics=["multimodal"])
        self.assertEqual([r["id"] for r in result["candidates"]], ["icml2024-mm"])
        self.assertEqual(result["filtered_count"], 1)
        result = gallery.search(self.project, "language pipeline", tiers=["unknown"])
        self.assertEqual([r["id"] for r in result["candidates"]], ["acl2023-lm"])
        self.assertEqual(gallery.search(self.project, "nothingmatchesuniqueterm")["candidates"], [])

    def test_packet_preview_sources_and_rights_are_explicit(self):
        self.seed()
        result = gallery.search(self.project, "time series")
        packet = json.loads((self.project / result["output_paths"]["packet"]).read_text(encoding="utf-8"))
        preview = (self.project / result["output_paths"]["preview"]).read_text(encoding="utf-8")
        row = packet["references"][0]
        self.assertEqual(row["license"]["image_license"], "unknown")
        self.assertFalse(row["license"]["reuse_authorized"])
        self.assertEqual(row["metadata_sha256"], gallery.digest(self.rows[0]))
        self.assertEqual(packet["report_binding"], result["report_binding"])
        self.assertIn("no-referrer", preview)
        self.assertIn("Content-Security-Policy", preview)
        self.assertNotIn("<img", preview)
        self.assertNotIn("<script", preview)
        self.assertIn("Open reference image", preview)

    def test_metadata_and_receipt_tampering_stop_reuse(self):
        self.seed()
        target = self.project / gallery.INDEX
        original = target.read_bytes()
        target.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "stale or modified"):
            gallery.search(self.project, "time series")
        target.write_bytes(original)
        receipt = self.project / gallery.RECEIPT
        obj = json.loads(receipt.read_text(encoding="utf-8"))
        obj["source"]["commit"] = "0" * 40
        receipt.write_text(json.dumps(obj), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "receipt differs"):
            gallery.load_index(self.project)

    def test_download_hash_mismatch_never_overwrites_index(self):
        with patch.object(gallery, "_download", return_value=b"[]"):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                gallery.sync(self.project)
        self.assertFalse((self.project / gallery.INDEX).exists())

    def test_html_text_is_escaped_and_executable_links_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["title"] = '<script>alert("x")</script> Time Series'
        self.seed(rows)
        result = gallery.search(self.project, "time series")
        preview = (self.project / result["output_paths"]["preview"]).read_text(encoding="utf-8")
        self.assertNotIn('<script>', preview)
        self.assertIn('&lt;script&gt;', preview)
        for url in ("javascript:alert(1)", "http://openreview.net/foo", "https://127.0.0.1/foo",
                    "https://openreview.net@evil.example/foo", "https://openreview.net/foo\nbar"):
            bad = copy.deepcopy(self.rows)
            bad[0]["paper"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                gallery.normalize_figures(bad, self.lock)

    def test_bounds_duplicates_nonfinite_and_path_escape_rejected(self):
        self.seed()
        for top_k in (0, 21, True, 1.2):
            with self.subTest(top_k=top_k), self.assertRaises(ValueError):
                gallery.search(self.project, "time series", top_k=top_k)
        for query in (None, "", " " * 3, "a" * 2001):
            with self.subTest(query=query), self.assertRaises(ValueError):
                gallery.search(self.project, query)
        for filters in ({"years": [True]}, {"years": [2027]}, {"venues": "iclr"},
                        {"topics": ["fake"]}, {"paid": True}):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                gallery.normalize_filters(filters)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            gallery.normalize_figures([self.rows[0], self.rows[0]], self.lock)
        for raw in ('{"a":1,"a":2}', '{"a":NaN}'):
            with self.assertRaises(ValueError):
                gallery._json(raw)
        bad = copy.deepcopy(self.rows)
        bad[0]["image"] = "images/../secrets.png"
        with self.assertRaises(ValueError):
            gallery.normalize_figures(bad, self.lock)

    def test_forged_candidate_and_fake_semantic_label_are_rejected(self):
        self.seed()
        result = gallery.search(self.project, "time series")
        report = json.loads((self.project / result["output_paths"]["report"]).read_text(encoding="utf-8"))
        forged = copy.deepcopy(report)
        forged["candidates"][0]["license"]["reuse_authorized"] = True
        with self.assertRaisesRegex(ValueError, "candidate metadata"):
            gallery.write_report(self.project, forged)
        forged = copy.deepcopy(report)
        forged["retrieval"] = {"method": "semantic", "semantic_image_search": True}
        with self.assertRaisesRegex(ValueError, "semantic results"):
            gallery.write_report(self.project, forged)

    def test_consumers_replay_retrieval_and_require_current_source_provenance(self):
        self.seed()
        result = gallery.search(self.project, "时间序列架构图")
        relative = result["output_paths"]["report"]
        report = gallery.validate_search_report(self.project, relative)
        self.assertEqual(report["candidates"][0]["id"], "iclr2025-ts")
        again = gallery.search(self.project, "时间序列架构图")
        self.assertEqual(again["report_binding"], result["report_binding"])
        # A recomputed directory name does not make a forged score or ranking
        # an actually executed deterministic retrieval.
        forged = copy.deepcopy(report)
        forged["candidates"][0]["score"] += 42
        new_relative = "reports/figure-gallery/" + gallery.digest(forged)[:24] + "/search.json"
        target = self.project / new_relative
        gallery.write(target, forged)
        gallery.record(self.project, [target], "scripts/figure_gallery.py")
        with self.assertRaisesRegex(ValueError, "deterministic retrieval replay"):
            gallery.validate_search_report(self.project, new_relative)
        with self.assertRaisesRegex(ValueError, "controlled figure gallery"):
            gallery.validate_search_report(self.project, "state/run.json")

    def test_execution_requires_cloud_and_local_input_is_not_a_cloud_attestation(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "DR_OS_CLOUD_EXECUTOR": "0"}):
            with self.assertRaisesRegex(ValueError, "cloud runner"):
                gallery.sync(self.project)

    def test_vendored_license_bytes_and_pinned_count_match_lock(self):
        lock = gallery._lock()
        for item in lock["files"]:
            data = (gallery.ROOT / item["path"]).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(data).hexdigest(), item["canonical_lf_sha256"])
        self.assertEqual(lock["metadata"]["record_count"], 3449)


if __name__ == "__main__":
    unittest.main()
