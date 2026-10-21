from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import literature_assets as assets


HAS_PDF_TOOLS = bool(importlib.util.find_spec("pypdf") and
                     importlib.util.find_spec("PIL") and shutil.which("pdftoppm") and shutil.which("pdftotext"))


def synthetic_pdf(*, raster: bool = True) -> bytes:
    """A controlled two-page fixture with actual raster/vector/text content."""
    from pypdf import PdfWriter
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                               FloatObject, NameObject, NumberObject)
    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    font_ref = writer._add_object(font)
    image = DecodedStreamObject()
    image.set_data(bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0]))
    image.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"),
                  NameObject("/Width"): NumberObject(2), NameObject("/Height"): NumberObject(2),
                  NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
                  NameObject("/BitsPerComponent"): NumberObject(8)})
    image_ref = writer._add_object(image)
    for index in range(2):
        page = writer.add_blank_page(width=300, height=300)
        resources = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})})
        draws = b"0.2 0.4 0.9 rg 30 110 180 80 re f\n"
        if raster and index == 0:
            resources[NameObject("/XObject")] = DictionaryObject(
                {NameObject("/Im0"): image_ref, NameObject("/Im1"): image_ref})
            draws += b"q 60 0 0 60 30 210 cm /Im0 Do Q\nq 60 0 0 60 110 210 cm /Im1 Do Q\n"
        stream = DecodedStreamObject()
        stream.set_data(draws + b"BT /F1 12 Tf 20 70 Td (Figure 1. Controlled source caption.) Tj ET\n"
                        b"BT /F1 12 Tf 20 50 Td (Table 2. Recorded measurements.) Tj ET\n")
        page[NameObject("/Resources")] = resources
        page[NameObject("/Contents")] = writer._add_object(stream)
        # Test date is document construction metadata, not a publication date.
        page[NameObject("/MediaBox")] = ArrayObject([FloatObject(0), FloatObject(0),
                                                    FloatObject(300), FloatObject(300)])
    writer.add_metadata({"/CreationDate": "D:19990102000000", "/Title": "Controlled fixture"})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class LiteratureSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1",
            "DR_OS_CLOUD_EXECUTION_RECEIPT_ID": "unit-test"}, clear=False)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_refuses_local_execution_before_fetch(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "", "DR_OS_CLOUD_EXECUTOR": ""}), \
             patch.object(assets, "fetch_bytes") as fetch:
            with self.assertRaisesRegex(assets.LiteratureAssetError, "cloud"):
                assets.resolve(self.project, "https://papers.example/paper.pdf")
            fetch.assert_not_called()

    def test_raw_quarantine_hash_time_version_and_no_invented_publication_date(self):
        payload = b"%PDF-1.7\ncontrolled raw fixture"
        with patch.object(assets, "fetch_bytes", return_value=(
            payload, "https://arxiv.org/pdf/2401.12345v2", 200, "application/pdf")) as fetch:
            result = assets.resolve(self.project, "arxiv:2401.12345v2")
        self.assertEqual(result["status"], "acquired")
        self.assertEqual(result["original_input"], "arxiv:2401.12345v2")
        self.assertEqual(result["version"], "v2")
        self.assertIsNone(result["publication_date"])
        self.assertEqual(result["source_pdf_sha256"], assets.digest(payload))
        self.assertIn("+00:00", result["acquired_at"])
        self.assertTrue(result["local_pdf"].startswith("data/raw/literature/"))
        self.assertTrue(result["manifest_path"].startswith("evidence/"))
        self.assertEqual(result["permissions"]["license"], "unknown")
        self.assertEqual(result["permissions"]["reuse_permission"], "unknown")
        self.assertEqual(fetch.call_args.kwargs["max_bytes"], assets.MAX_BYTES)

    def test_hash_checked_cache_does_not_refetch_and_tampered_raw_does(self):
        payload = b"%PDF-1.7\nfirst"
        with patch.object(assets, "fetch_bytes", return_value=(
            payload, "https://papers.example/paper.pdf", 200, "application/pdf")) as fetch:
            first = assets.resolve(self.project, "https://papers.example/paper.pdf")
            second = assets.resolve(self.project, "https://papers.example/paper.pdf")
            self.assertEqual(fetch.call_count, 1)
            self.assertTrue(second["cache_hit"])
            (self.project / first["local_pdf"]).write_bytes(b"tampered")
            assets.resolve(self.project, "https://papers.example/paper.pdf")
            self.assertEqual(fetch.call_count, 2)

    def test_project_page_discovers_explicit_paper_link_and_preserves_raw_html(self):
        page = b"""<html><head><title>A research project</title>
        <meta name="citation_title" content="Actual source title">
        <meta name="citation_publication_date" content="2025-04-03">
        </head><body><a href="/real.pdf">Paper</a><a href="/reference.pdf">Other reference</a></body></html>"""
        calls = []

        def fetch(url, **kwargs):
            calls.append(url)
            return (page, url, 200, "text/html") if url.endswith("/project") else (
                b"%PDF-1.7\nactual source", url, 200, "application/pdf")

        with patch.object(assets, "fetch_bytes", side_effect=fetch):
            result = assets.resolve(self.project, "https://papers.example/project")
        self.assertEqual(calls, ["https://papers.example/project", "https://papers.example/real.pdf"])
        self.assertEqual(result["source_type"], "project_page")
        self.assertEqual(result["title"], "Actual source title")
        self.assertEqual(result["publication_date_basis"], "publisher-supplied HTML metadata")
        html = next(item for item in result["downloads"] if item["kind"] == "html")
        self.assertEqual((self.project / html["path"]).read_bytes(), page)
        self.assertTrue(html["text_path"].startswith("data/raw/literature/"))
        self.assertEqual(assets.digest((self.project / html["text_path"]).read_bytes()), html["text_sha256"])

    def test_inaccessible_pdf_is_failure_lead_not_fake_fulltext(self):
        with patch.object(assets, "fetch_bytes", side_effect=OSError("HTTP Error 403")):
            result = assets.resolve(self.project, "https://papers.example/unavailable.pdf")
        self.assertEqual(result["status"], "lead_only")
        self.assertEqual(result["pdf_status"], "not_acquired")
        self.assertEqual(result["pdfs"], [])
        self.assertNotIn("local_pdf", result)
        self.assertIn("403", result["failures"][0]["reason"])

    def test_private_network_denied_by_shared_fetcher_before_connection(self):
        with patch("urllib.request.build_opener") as opener:
            result = assets.resolve(self.project, "https://127.0.0.1/internal.pdf")
        opener.assert_not_called()
        self.assertEqual(result["status"], "lead_only")
        self.assertIn("non-public", result["failures"][0]["reason"])

    def test_credential_urls_traversal_and_output_protection_are_rejected(self):
        with patch.object(assets, "fetch_bytes") as fetch:
            for url in ("http://papers.example/a.pdf", "https://user:password@papers.example/a",
                        "https://papers.example/a?token=secret", "C:/private.pdf", "../private.pdf"):
                with self.subTest(url=url), self.assertRaises((RuntimeError, ValueError)):
                    assets.resolve(self.project, url)
            for output in ("../evidence", "evidence/../state", "state/gates", "evidence\\escape"):
                with self.subTest(output=output), self.assertRaises(assets.LiteratureAssetError):
                    assets.resolve(self.project, "https://papers.example/a.pdf", output)
            fetch.assert_not_called()

    def test_invalid_pdf_magic_and_oversized_download_fail_without_asset(self):
        for data, limit in ((b"not a pdf", 100), (b"%PDF-" + b"x" * 50, 20)):
            with self.subTest(limit=limit), patch.object(assets, "fetch_bytes", return_value=(
                data, "https://papers.example/a.pdf", 200, "application/pdf")):
                result = assets.resolve(self.project, "https://papers.example/a.pdf", max_bytes=limit, refresh=True)
            self.assertEqual(result["status"], "lead_only")
            self.assertEqual(result["pdfs"], [])

    def test_symlink_output_component_cannot_escape(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks unavailable")
        outside = self.project / "outside"
        outside.mkdir()
        (self.project / "evidence").mkdir()
        try:
            (self.project / "evidence" / "escape").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlink privileges unavailable")
        with self.assertRaises(assets.LiteratureAssetError):
            assets.resolve(self.project, "https://papers.example/a.pdf", "evidence/escape")

    def test_caption_and_number_require_actual_page_text(self):
        labels = assets._label({"figure_number": "1", "caption": "Actual caption"},
                               "Figure 1. Actual\ncaption")
        self.assertEqual(labels["figure_number"], "1")
        self.assertEqual(labels["caption"], "Actual caption")
        false = assets._label({"figure_number": "1", "table_number": "9", "caption": "Made up"},
                              "Figure 10. A source figure")
        self.assertIsNone(false["figure_number"])
        self.assertIsNone(false["table_number"])
        self.assertIsNone(false["caption"])

    def test_positioned_captions_rank_actual_labels_without_object_order(self):
        xml = b'''<html><body><doc><page width="300" height="400"><flow><block>
          <line><word xMin="20" yMin="110" xMax="68" yMax="121">Figure</word><word xMin="70" yMin="110" xMax="80" yMax="121">7:</word><word xMin="82" yMin="110" xMax="150" yMax="121">Calibration</word></line>
          <line><word xMin="20" yMin="123" xMax="150" yMax="134">error curves.</word></line>
          </block><block><line><word xMin="20" yMin="210" xMax="200" yMax="221">Table 3. Runtime measurements.</word></line></block>
          <block><line><word xMin="20" yMin="310" xMax="220" yMax="321">As Figure 2 shows, calibration improves.</word></line></block>
          </flow></page></doc></body></html>'''
        result = assets._caption_candidates(xml, question="calibration error", max_selected=1)
        self.assertEqual(len(result["candidates"]), 2)
        selected = [item for item in result["candidates"] if item["selection"]["selected"]]
        self.assertEqual(selected[0]["figure_number"], "7")
        self.assertEqual(selected[0]["pdf_page"], 1)
        self.assertEqual(selected[0]["caption_bbox"], [20, 110, 150, 134])
        self.assertIn("error curves", selected[0]["caption"])
        self.assertFalse(selected[0]["spatial_association_verified"])
        self.assertFalse(result["semantic_relevance_verified"])
        self.assertIsNone(result["candidates"][1]["figure_number"])
        self.assertEqual(result["candidates"][1]["table_number"], "3")
        self.assertEqual(assets._caption_candidates(xml, question="unrelated zirconium")["selected_candidate_ids"], [])

    def test_positioned_caption_parser_rejects_entities_and_bad_coordinates(self):
        for xml in (b'<!DOCTYPE html [<!ENTITY x "unsafe">]><html/>',
                    b'<doc><page width="nan" height="400"/></doc>',
                    b'<doc><page width="300" height="400"><block><line><word xMin="-1" yMin="3" xMax="200" yMax="20">Figure 2: bad</word></line></block></page></doc>'):
            with self.subTest(xml=xml), self.assertRaises(assets.LiteratureAssetError):
                assets._caption_candidates(xml)


@unittest.skipUnless(HAS_PDF_TOOLS, "cloud extraction needs pypdf, Pillow and pdftoppm")
class LiteraturePDFTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.pdf = self.project / "data/raw/literature/source.pdf"
        self.pdf.parent.mkdir(parents=True)
        self.pdf.write_bytes(synthetic_pdf())
        self.environment = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}, clear=False)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_real_raster_dedup_vector_page_render_and_source_crop(self):
        result = assets.extract(self.project, "data/raw/literature/source.pdf", figures=[
            {"pdf_page": 2, "bbox": [20, 100, 250, 240], "figure_number": "1",
             "caption": "Figure 1. Controlled source caption."},
            {"pdf_page": 1, "bbox": [20, 100, 250, 240], "figure_number": "9", "caption": "Fabricated"}])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["source_pdf_sha256"], assets.digest(self.pdf.read_bytes()))
        originals = [asset for asset in result["assets"] if asset["kind"] == "image_object"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(len(originals[0]["occurrences"]), 2)
        self.assertIsNone(originals[0]["figure_number"])
        pages = [asset for asset in result["assets"] if asset["kind"] == "page_render"]
        page_occurrences = [occ for asset in result["assets"] for occ in asset["occurrences"]
                            if occ["kind"] == "page_render"]
        self.assertTrue(pages)
        self.assertEqual({occ["pdf_page"] for occ in page_occurrences}, {1, 2})
        crops = [asset for asset in result["assets"] if asset["kind"] == "source_crop"]
        crop_occurrences = [occ for asset in result["assets"] for occ in asset["occurrences"]
                            if occ["kind"] == "source_crop"]
        self.assertTrue(crops)
        self.assertTrue(any(occ["figure_number"] == "1" and occ["pdf_page"] == 2 for occ in crop_occurrences))
        self.assertTrue(any(occ["figure_number"] is None and occ["pdf_page"] == 1 for occ in crop_occurrences))
        self.assertEqual(len(result["rejected_labels"]), 2)
        for item in result["assets"]:
            self.assertTrue(item["path"].startswith("data/raw/literature/"))
            self.assertEqual(item["sha256"], assets.digest((self.project / item["path"]).read_bytes()))
            self.assertEqual(item["permissions"]["license"], "unknown")
        self.assertTrue(result["manifest_path"].startswith("evidence/"))

    def test_vector_only_pdf_has_real_page_assets(self):
        self.pdf.write_bytes(synthetic_pdf(raster=False))
        result = assets.extract(self.project, "data/raw/literature/source.pdf")
        self.assertFalse(any(item["kind"] == "image_object" for item in result["assets"]))
        self.assertTrue(any(item["kind"] == "page_render" for item in result["assets"]))

    def test_automatic_caption_coordinates_and_question_selection_use_actual_pdf(self):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no model permitted")):
            result = assets.extract(self.project, "data/raw/literature/source.pdf",
                                    question="recorded measurements", max_selected=1)
        candidates = result["caption_discovery"]["candidates"]
        self.assertTrue(candidates)
        selected = [item for item in candidates if item["selection"]["selected"]]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["table_number"], "2")
        self.assertEqual(result["selected_pages"], [1])
        self.assertTrue(all(item["pdf_page"] == 1 for asset in result["assets"] for item in asset["occurrences"]))
        crops = [occ for asset in result["assets"] for occ in asset["occurrences"] if occ["kind"] == "caption_context_crop"]
        self.assertEqual(crops[0]["table_number"], "2")
        self.assertEqual(crops[0]["label_verification"]["status"], "positioned_caption_match")
        self.assertFalse(crops[0]["spatial_association_verified"])
        empty = assets.extract(self.project, "data/raw/literature/source.pdf", question="zirconium unrelated")
        self.assertEqual(empty["selected_pages"], [])
        self.assertEqual(empty["assets"], [])

    def test_unchanged_figure_extraction_reuses_assets_and_tampering_forces_rebuild(self):
        first = assets.extract(self.project, "data/raw/literature/source.pdf", question="recorded measurements", max_selected=1)
        with patch.object(assets, "discover_captions", side_effect=AssertionError("unchanged source must not be parsed again")):
            again = assets.extract(self.project, "data/raw/literature/source.pdf", question="recorded measurements", max_selected=1)
        self.assertTrue(again["cache_hit"])
        self.assertEqual(again["manifest_sha256"], first["manifest_sha256"])
        self.assertEqual(again["assets"], first["assets"])
        (self.project / first["assets"][0]["path"]).write_bytes(b"tampered")
        with patch.object(assets, "discover_captions", wraps=assets.discover_captions) as discover:
            repaired = assets.extract(self.project, "data/raw/literature/source.pdf", question="recorded measurements", max_selected=1)
        self.assertEqual(discover.call_count, 1)
        self.assertNotIn("cache_hit", repaired)
        self.assertEqual(assets.digest((self.project / repaired["assets"][0]["path"]).read_bytes()), repaired["assets"][0]["sha256"])

    def test_hash_mismatch_page_limit_and_bad_crops_fail_closed(self):
        with self.assertRaisesRegex(assets.LiteratureAssetError, "hash"):
            assets.extract(self.project, "data/raw/literature/source.pdf", source={"source_pdf_sha256": "0" * 64})
        with self.assertRaisesRegex(assets.LiteratureAssetError, "page count"):
            assets.extract(self.project, "data/raw/literature/source.pdf", max_pages=1)
        for item in ({"pdf_page": 0, "bbox": [1, 1, 2, 2]},
                     {"pdf_page": 1, "bbox": [-1, 0, 10, 10]},
                     {"pdf_page": 1, "bbox": [0, 0, float("nan"), 2]},
                     {"pdf_page": 1, "bbox": [0, 0, 500, 10]}):
            with self.subTest(item=item), self.assertRaises(assets.LiteratureAssetError):
                assets.extract(self.project, "data/raw/literature/source.pdf", figures=[item])


if __name__ == "__main__":
    unittest.main()
