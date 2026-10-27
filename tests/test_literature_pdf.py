"""Actual cloud PDF tool acceptance plus bounded rendering contracts.

Generated multi-column/rotated/scanned fixtures are software tests, never real
scientific or human-reviewed evidence.
"""
import importlib.util
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import literature_matrix, literature_pdf as pdf, literature_workbench as wb, paper_reader
from scripts.research_artifacts import read, sha, write


class PdfContractTests(unittest.TestCase):
    def test_explicit_cloud_ocr_provisions_only_missing_fixed_tools(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), \
             patch.object(pdf.shutil, "which", return_value=None), patch.object(pdf, "_run", return_value=SimpleNamespace(stdout=b"")) as run:
            packages = pdf.provision(Path(directory), {"enabled": True, "language": "eng+chi_sim"})
            self.assertEqual(packages, ["poppler-utils", "tesseract-ocr", "tesseract-ocr-eng", "tesseract-ocr-chi-sim"])
            self.assertEqual(run.call_count, 3)
            self.assertEqual(run.call_args.args[0][-4:], packages)
            self.assertEqual(run.call_args.args[0][:5], ["sudo", "-n", "apt-get", "install", "-y"])

    def test_available_pdf_tools_need_no_install_and_provision_is_cloud_only(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), \
             patch.object(pdf.shutil, "which", return_value="/usr/bin/tool"), patch.object(pdf, "_run") as run:
            self.assertEqual(pdf.provision(Path(directory), {"enabled": False, "language": "eng"}), [])
            run.assert_not_called()
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}), patch.object(pdf, "_run") as run:
            with self.assertRaisesRegex(ValueError, "cloud"):
                pdf.provision(Path("unused"), {"enabled": True, "language": "eng"})
            run.assert_not_called()

    def test_cloud_guard_precedes_source_tools_or_writes(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "DR_OS_CLOUD_EXECUTOR": "0"}):
            with self.assertRaisesRegex(ValueError, "cloud runner"):
                pdf.refresh(Path("absent"))

    def test_ocr_tsv_retains_confidence_and_never_promotes_original_evidence(self):
        payload = "level\tleft\ttop\twidth\theight\tconf\ttext\n5\t10\t20\t30\t8\t92.3\tObserved\n1\t0\t0\t100\t100\t-1\t\n"
        rows = pdf._ocr_rows(payload)
        self.assertEqual(rows[0]["bbox_pixels"], [10, 20, 40, 28])
        self.assertEqual(rows[0]["confidence"], 92.3)
        self.assertFalse(rows[0]["semantic_verification"])
        with self.assertRaisesRegex(ValueError, "invalid OCR"):
            pdf._ocr_rows(payload.replace("92.3", "nan"))

    def test_html_contains_real_page_overlay_and_escaped_quote_navigation(self):
        report = {"id": "fixture", "source": {"path": "evidence/source.pdf", "sha256": "a" * 64}, "annotated_pdf": None,
            "pages": [{"pdf_page": 1, "page_size": [300, 400], "source_rotation": 0,
                "text_status": "positioned_original_text_available", "image": {"path": "reports/literature-pdf/fixture/page-1.png"}}],
            "sentences": [{"sentence_id": "sentence-abc", "pdf_page": 1, "quote": "<script>not code</script>",
                "position_status": "located_unique_normalized_word_sequence", "rects": [[10, 20, 100, 30]]}], "links": []}
        with patch("scripts.literature_workbench._href", return_value="../../source.pdf#page=1"):
            result = pdf.html_text(Path("."), report)
        self.assertIn('viewBox="0 0 300 400"', result)
        self.assertIn('<rect x="10" y="20" width="90" height="10"', result)
        self.assertIn('href="#text-sentence-abc"', result)
        self.assertIn('href="#box-sentence-abc"', result)
        self.assertIn("&lt;script&gt;", result)
        self.assertNotIn("<script>", result)

    def test_markdown_matrix_preserves_unknowns_and_escapes_table_syntax(self):
        report = {"question": "Does A | B differ?", "cells": [
            {"paper_id": "a", "field_id": "accuracy", "status": "unknown", "text": None, "evidence": []},
            {"paper_id": "b", "field_id": "accuracy", "status": "located_pending_semantic_review", "text": "A | B\n<script>",
             "numeric": {"original_value": "95.0", "original_unit": "%", "comparator": "<",
                         "uncertainty": {"lower": "90.0", "upper": "99.0", "label": "95% CI"}},
             "source_context": {"population": "Population A", "conditions": "fixed protocol", "row_header": "Method A",
                                "column_header": "accuracy", "footnotes": ["One held-out cohort."]},
             "inference_boundary": "A reported estimate, not an established benefit.",
             "evidence": [{"path": "evidence/source.md", "sha256": "a" * 64, "locator": "lines 1-2", "quote": "95.0 %"}]}]}
        result = literature_matrix.markdown_text(report)
        self.assertIn("unknown", result)
        self.assertIn("A &#124; B<br>&lt;script&gt;", result)
        self.assertIn("&lt; 95.0 %", result)
        self.assertIn("95.0 %", result)
        for value in ("a" * 64, "Population A", "fixed protocol", "Method A", "One held-out cohort.",
                      "95% CI", "90.0", "99.0", "not an established benefit"):
            self.assertIn(value, result)

    def test_rotated_page_table_uses_already_displayed_asset_coordinates(self):
        report = {"id": "fixture", "source": {"path": "evidence/source.pdf", "sha256": "a" * 64}, "annotated_pdf": None,
            "pages": [{"pdf_page": 1, "page_size": [420, 560], "source_rotation": 90,
                "text_status": "positioned_original_text_available", "image": {"path": "reports/literature-pdf/fixture/page-1.png"}}],
            "sentences": [], "links": [{"kind": "table_cell", "id": "cell-example", "pdf_page": 1,
                "target": "reports/literature-matrix/index.html#cell-example", "quote": "Located table",
                "asset": {"bbox": [30, 50, 100, 150]}}]}
        with patch("scripts.literature_workbench._href", return_value="../../source.pdf#page=1"):
            result = pdf.html_text(Path("."), report)
        self.assertIn('href="#cell-example"><rect x="30" y="50" width="70" height="100"', result)
        report["links"][0]["asset"]["bbox"] = [30, 50, 500, 150]
        with patch("scripts.literature_workbench._href", return_value="../../source.pdf#page=1"), self.assertRaisesRegex(ValueError, "displayed PDF page"):
            pdf.html_text(Path("."), report)


class PdfCloudAcceptanceTests(unittest.TestCase):
    def setUp(self):
        if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
            self.skipTest("actual PDF tools execute only on the authorized cloud runner")
        if any(shutil.which(x) is None for x in ("pdftotext", "pdftoppm")) or any(importlib.util.find_spec(x) is None for x in ("pypdf", "reportlab", "PIL")):
            self.skipTest("requires declared pypdf, reportlab, Pillow and Poppler")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.source = self.project / "data/raw/literature/sources/complex.pdf"
        self.source.parent.mkdir(parents=True)
        self._fixture()
        self.original_hash = sha(self.source)
        manifest = "data/manifests/complex.json"
        write(self.project / manifest, {"license": {"redistribution_allowed": True}, "download": {"sha256": self.original_hash}})
        write(self.project / "state/data-authorizations.json", {"manifests": {manifest: {"sha256": sha(self.project / manifest),
            "actor": "Synthetic fixture owner", "cloud_use_confirmed": True}}})
        reader = self.project / "evidence/readers/complex.md"
        paper_reader.build(self.project, self.source, reader, pages=[1, 2, 4])
        write(self.project / wb.CONFIG, {"schema_version": "1.0", "papers": [{"id": "complex", "title": "Synthetic complex PDF",
            "source": {"path": self.source.relative_to(self.project).as_posix(), "sha256": self.original_hash},
            "reader": {"path": reader.relative_to(self.project).as_posix(), "sha256": sha(reader)}, "manifest": manifest}]})
        self.assertEqual(wb.build(self.project)["errors"], [])
        self.request = {"schema_version": "1.0", "id": "complex", "paper_id": "complex", "pages": [1, 2, 3, 4], "annotate_pdf": True}
        write(self.project / pdf.REQUEST, self.request)

    def _fixture(self):
        from PIL import Image, ImageDraw, ImageFont
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from pypdf import PdfReader, PdfWriter
        document = canvas.Canvas(str(self.source), pagesize=(600, 500))
        document.setFont("Helvetica", 11)
        document.drawString(30, 450, "Column independent evidence remains.")
        document.drawString(30, 420, "Repeated outcome remains.")
        document.drawString(310, 420, "Repeated outcome remains.")
        document.drawString(310, 390, "Adverse result remains visible.")
        document.showPage()
        document.drawString(30, 400, "Rotation measurable evidence remains.")
        document.showPage()
        image = Image.new("RGB", (1200, 400), "white")
        font = ImageFont.truetype("DejaVuSans.ttf", 36)
        ImageDraw.Draw(image).text((30, 100), "Scanned source evidence remains.", fill="black", font=font)
        document.drawImage(ImageReader(image), 20, 200, width=560, height=180)
        document.showPage()
        document.drawString(30, 450, "Table 1 fixed protocol Population A accuracy 95.0 %.")
        document.line(30, 420, 400, 420)
        document.drawString(30, 400, "Method A")
        document.drawString(250, 400, "95.0 %")
        document.save()
        original = PdfReader(str(self.source))
        output = PdfWriter()
        for number, page in enumerate(original.pages):
            output.add_page(page)
            if number == 1:
                output.pages[-1].cropbox.lower_left = (20, 40)
                output.pages[-1].cropbox.upper_right = (580, 460)
                output.pages[-1].rotate(90)
        buffer = io.BytesIO()
        output.write(buffer)
        self.source.write_bytes(buffer.getvalue())

    def test_actual_multicolumn_rotated_duplicate_scan_view_and_annotation(self):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid API calls")):
            result = pdf.refresh(self.project)
            self.assertTrue(pdf.validate_saved_report(self.project)["valid"])
            again = pdf.refresh(self.project)
        self.assertTrue(again["cache_hit"])
        self.assertEqual(sha(self.source), self.original_hash)
        self.assertEqual(len(result["pages"]), 4)
        self.assertEqual(result["pages"][1]["source_rotation"], 90)
        self.assertEqual(result["pages"][2]["text_status"], "no_native_text_ocr_or_visual_review_required")
        repeated = [s for s in result["sentences"] if s["quote"] == "Repeated outcome remains."]
        self.assertEqual(len(repeated), 2)
        self.assertTrue(all(s["position_status"] == "ambiguous" for s in repeated))
        self.assertTrue(any(s["pdf_page"] == 2 and s["position_status"] == "located_unique_normalized_word_sequence" for s in result["sentences"]))
        self.assertGreater(len(result["annotations"]), 0)
        self.assertFalse({s["sentence_id"] for s in repeated} & {a["sentence_id"] for a in result["annotations"]})
        self.assertFalse(result["semantic_support_verified"])
        from pypdf import PdfReader
        annotated = PdfReader(str(self.project / result["annotated_pdf"]["path"]))
        self.assertTrue(all(p.rotation == 0 for p in annotated.pages))
        self.assertEqual(sum(str(a.get_object().get("/NM", "")).startswith("lunwen-sentence-") for p in annotated.pages for a in p.get("/Annots", [])), len(result["annotations"]))
        page = (self.project / result["html"]).read_text(encoding="utf-8")
        self.assertIn("<svg", page)
        self.assertIn("annotated.pdf", page)
        self.assertIn("page-3.png", page)

    def test_nonzero_cropbox_and_rotation_align_pdf_annotation_with_known_source_point(self):
        result = pdf.refresh(self.project)
        page = result["pages"][1]
        self.assertEqual(page["source_rotation"], 90)
        self.assertEqual(page["page_size"], [420, 560])
        sentence = next(s for s in result["sentences"] if s["pdf_page"] == 2 and
                        s["position_status"] == "located_unique_normalized_word_sequence")
        for x0, y0, x1, y1 in sentence["rects"]:
            self.assertTrue(0 <= x0 < x1 <= 420)
            self.assertTrue(0 <= y0 < y1 <= 560)
        annotation = next(a for a in result["annotations"] if a["sentence_id"] == sentence["sentence_id"])
        left, bottom, right, top = annotation["rect_pdf_points_bottom_left"]
        # The original baseline starts at (30,400). Transfer of the clockwise
        # rotation maps that baseline to (400,570) in normalized PDF coordinates.
        # This independent known source point detects a lost CropBox offset.
        self.assertLess(left, 400)
        self.assertGreater(right, 400)
        self.assertAlmostEqual(top, 570, delta=2)
        self.assertGreater(top, bottom)

    def test_actual_ocr_scan_is_assistance_never_native_evidence(self):
        if shutil.which("tesseract") is None:
            self.skipTest("explicit OCR acceptance requires cloud Tesseract")
        self.request.update(pages=[3], ocr={"enabled": True, "language": "eng"})
        write(self.project / pdf.REQUEST, self.request)
        result = pdf.refresh(self.project)
        words = result["pages"][0]["ocr"]["words"]
        self.assertIn("Scanned", " ".join(w["text"] for w in words))
        self.assertFalse(result["ocr_is_original_evidence"])
        self.assertFalse(result["pages"][0]["ocr"]["authoritative_original_text"])
        self.assertEqual(result["sentences"], [])
        self.assertEqual(result["annotations"], [])

    def test_changed_request_or_outputs_cannot_reuse_verified_report(self):
        result = pdf.refresh(self.project)
        report_path = self.project / result["report"]
        report = read(report_path)
        report["semantic_support_verified"] = True
        write(report_path, report)
        with self.assertRaisesRegex(ValueError, "output changed"):
            pdf.validate_saved_report(self.project)

    def test_invalid_pages_sentence_ids_and_unknown_ocr_languages_block(self):
        for changes in ({"pages": [True]}, {"pages": [[1]]}, {"pages": [1, 1]},
                        {"sentence_ids": ["sentence-invented"]}, {"ocr": {"enabled": True, "language": "../private"}}):
            request = {**self.request, **changes}
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                pdf._prepare(self.project, request)

    def test_revoked_source_rights_block_cached_view(self):
        pdf.refresh(self.project)
        write(self.project / "state/data-authorizations.json", {"manifests": {}})
        with self.assertRaises(ValueError):
            pdf.validate_saved_report(self.project)
