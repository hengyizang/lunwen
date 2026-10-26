"""Cloud validation fixtures for source navigation; no scientific reading claim."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import literature_reading as reading, literature_reasoning as reasoning
from scripts import literature_workbench as wb, paper_reader
from scripts.research_artifacts import read, record, sha, write


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.config = {"schema_version": "1.0", "papers": []}

    def source(self, relative, text):
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return {"path": relative, "sha256": sha(target)}

    def add(self, identifier="a", text=None, **extra):
        source = self.source("evidence/sources/" + identifier + ".md", text or
            "# Abstract\nCalibration may transfer.\n# Methods\nWhole devices are held out.\n# Results\nThe transfer fails under drift.\n")
        paper = {"id": identifier, "title": identifier, "topic_id": "calibration", "paper_ids": ["P01"],
                 "source": source, **extra}
        self.config["papers"].append(paper)
        return paper

    def build(self):
        write(self.project / wb.CONFIG, self.config)
        return wb.build(self.project)

    def anchor(self, paper, line):
        return {"paper_id": paper["id"], **paper["source"], "start_line": line, "end_line": line,
                "quote": (self.project / paper["source"]["path"]).read_text(encoding="utf-8").splitlines()[line - 1]}

    def progress(self, paper, question, line=4):
        plan = reasoning.itinerary(self.project, question)
        step = next(s for s in plan["steps"] if s["paper_id"] == paper["id"] and s["phase"] == "mechanism")
        return reasoning.record_progress(self.project, {"step_id": step["step_id"],
            "expected_step_sha256": step["step_sha256"], "answer": "Device independence is explicitly reported.",
            "outcome": "supports", "evidence": [self.anchor(paper, line)], "kind": "human_interpretation",
            "recorded_by": "Synthetic fixture reader", "recorded_at": "2026-10-25T08:00:00+00:00",
            "inference_boundary": "A recorded interpretation, not causal or human full-text verification."})

    def test_index_stable_exact_source_navigation_and_cached_without_model(self):
        self.add(text="One mechanism transfers.\nAn adverse outcome remains.\n")
        self.build()
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid call")):
            index = reading.build_index(self.project, "a")
            again = reading.build_index(self.project, "a")
        self.assertFalse(index["cache_hit"])
        self.assertTrue(again["cache_hit"])
        self.assertEqual(index["sentences"], again["sentences"])
        self.assertEqual(index["sentences"][1]["start_line"], 2)
        self.assertEqual(index["sentences"][1]["quote"], "An adverse outcome remains.")
        page = (self.project / index["html_path"]).read_text(encoding="utf-8")
        self.assertIn('id="' + index["sentences"][1]["sentence_id"] + '"', page)
        self.assertIn("../../", page)
        self.assertFalse(index["semantic_support_verified"])

    def test_sentence_anchor_rejects_quote_hash_line_and_page_substitution(self):
        self.add()
        self.build()
        sentence = reading.build_index(self.project, "a")["sentences"][0]
        exact = {k: sentence[k] for k in ("sentence_id", "path", "sha256", "start_line", "end_line", "quote", "pdf_page")}
        resolved = reading.validate_sentence(self.project, "a", exact)
        self.assertIn("#sentence-", resolved["href"])
        for key, wrong in (("quote", "A made-up statement."), ("sha256", "0" * 64),
                           ("start_line", 99), ("pdf_page", 1), ("start_line", True)):
            with self.subTest(key=key, wrong=wrong), self.assertRaisesRegex(ValueError, "differs"):
                reading.validate_sentence(self.project, "a", {**exact, key: wrong})
        with self.assertRaisesRegex(ValueError, "actual current PDF positioning"):
            reading.validate_sentence(self.project, "a", {**exact, "bbox": [0, 0, 10, 10]})

    def test_changed_source_invalidates_index_instead_of_reusing_old_sentences(self):
        paper = self.add()
        self.build()
        reading.build_index(self.project, "a")
        (self.project / paper["source"]["path"]).write_text("A different version.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            reading.build_index(self.project, "a")

    def test_two_registered_versions_remain_separate_evidence_sources(self):
        self.add("preprint", "Preprint reports a gain.")
        self.add("published", "Published version reports no gain.")
        self.build()
        preprint = reading.build_index(self.project, "preprint")
        published = reading.build_index(self.project, "published")
        self.assertNotEqual(preprint["sentences"][0]["sentence_id"], published["sentences"][0]["sentence_id"])
        report = reading.coverage(self.project, {"question": "Does gain transfer?"})
        self.assertEqual({p["paper_id"] for p in report["papers"]}, {"preprint", "published"})
        self.assertTrue(report["versions_not_substituted"])

    def test_metadata_only_never_becomes_a_full_text_sentence_index(self):
        self.add(source_scope="metadata_only")
        self.build()
        index = reading.build_index(self.project, "a")
        self.assertEqual(index["sentences"], [])
        report = reading.coverage(self.project, {"question": "Does calibration transfer?"})
        dimensions = {d["dimension"]: d for d in report["papers"][0]["dimensions"]}
        self.assertEqual(dimensions["metadata"]["status"], "metadata_available_not_full_text_read")
        self.assertEqual(dimensions["methods"]["status"], "not_located")

    def test_native_original_ranges_exclude_translation_generated_headings(self):
        paper = {"id": "a", "source": {"path": "evidence/sources/a.pdf", "sha256": "a" * 64},
                 "reader": self.source("evidence/readers/a.md",
                    "## PDF page 2\n### Original extracted text\nA measured result.\n"
                    "### Chinese reading translation\nAn invented extra result.\n"), "source_scope": "full_text"}
        paper["reader"]["page_ranges"] = {"2": [3, 3]}
        sentences, omitted = reading._sentence_rows(self.project, paper)
        self.assertEqual(omitted, 0)
        self.assertEqual([s["quote"] for s in sentences], ["A measured result."])
        self.assertEqual((sentences[0]["start_line"], sentences[0]["pdf_page"]), (3, 2))

    def test_bound_native_reader_index_excludes_translation_and_checks_physical_page(self):
        # A synthetic source/receipt tests bindings; it does not establish that
        # an actual scientific paper was read or that an extraction is correct.
        original = "A measured source result."
        pdf = self.project / "evidence/sources/native.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF-1.4\nSynthetic provenance fixture, not an experiment.\n%%EOF\n")
        source = {"path": "evidence/sources/native.pdf", "sha256": sha(pdf)}
        reader = self.source("evidence/readers/native.md", "# Reader\n\n## PDF page 1\n\n"
            "### Original extracted text\n\n" + original +
            "\n\n### Chinese reading translation\n\nA different invented statement.\n")
        mapping = self.project / "evidence/readers/native.source-map.json"
        write(mapping, {"source_sha256": source["sha256"], "reader_sha256": reader["sha256"],
            "source_blocks": [{"pdf_page": 1, "extracted_text_sha256": hashlib.sha256(original.encode()).hexdigest()}]})
        receipt = self.project / "evidence/readers/native.reader.json"
        write(receipt, {"pdf_sha256": source["sha256"], "reader_sha256": reader["sha256"],
            "reader_implementation_sha256": sha(Path(paper_reader.__file__)), "page_count": 1,
            "selected_pages": [1], "page_images": [],
            "source_map": {"path": mapping.relative_to(self.project).as_posix(), "sha256": sha(mapping)}})
        record(self.project, [self.project / reader["path"], receipt, mapping], "synthetic-fixture")
        self.config["papers"] = [{"id": "native", "title": "Native fixture", "source": source, "reader": reader}]
        self.build()
        index = reading.build_index(self.project, "native")
        self.assertEqual([s["quote"] for s in index["sentences"]], [original])
        sentence = index["sentences"][0]
        self.assertEqual(sentence["pdf_page"], 1)
        self.assertIn("native.pdf#page=1", (self.project / index["html_path"]).read_text(encoding="utf-8"))
        anchor = {k: sentence[k] for k in ("sentence_id", "path", "sha256", "start_line", "end_line", "quote", "pdf_page")}
        with self.assertRaisesRegex(ValueError, "differs"):
            reading.validate_sentence(self.project, "native", {**anchor, "pdf_page": 2})
        with self.assertRaisesRegex(ValueError, "differs"):
            reading.validate_sentence(self.project, "native", {**anchor, "quote": "A different invented statement."})

    def test_real_cloud_pdf_reader_and_poppler_preserve_physical_page_coordinates(self):
        # This is an actual tool integration on synthetic software-test text,
        # not evidence that a research paper was read or scientifically verified.
        if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
            self.skipTest("actual PDF tool integration belongs on the authorized cloud runner")
        if (shutil.which("pdftotext") is None or importlib.util.find_spec("reportlab") is None
                or importlib.util.find_spec("pypdf") is None):
            self.skipTest("actual PDF integration requires declared reader, reportlab and Poppler tools")
        from reportlab.pdfgen import canvas

        pdf = self.project / "data/raw/literature/sources/position-fixture.pdf"
        pdf.parent.mkdir(parents=True)
        document = canvas.Canvas(str(pdf), pagesize=(300, 400))
        document.setFont("Helvetica", 12)
        document.drawString(36, 350, "A first-page measurement remains bounded.")
        document.showPage()
        document.setFont("Helvetica", 12)
        original = "A second-page adverse result is retained."
        document.drawString(36, 300, original)
        document.save()

        manifest = "data/manifests/position-fixture.json"
        write(self.project / manifest, {"license": {"redistribution_allowed": True},
            "download": {"sha256": sha(pdf)}})
        write(self.project / "state/data-authorizations.json", {"manifests": {manifest: {
            "sha256": sha(self.project / manifest), "actor": "Synthetic fixture owner",
            "cloud_use_confirmed": True}}})
        reader = self.project / "evidence/readers/position-fixture.md"
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid request")):
            paper_reader.build(self.project, pdf, reader, max_pages=2, pages=[2])
            self.config["papers"] = [{"id": "position-fixture", "title": "Synthetic positioned PDF",
                "source": {"path": pdf.relative_to(self.project).as_posix(), "sha256": sha(pdf)},
                "reader": {"path": reader.relative_to(self.project).as_posix(), "sha256": sha(reader)},
                "manifest": manifest}]
            self.assertEqual(self.build()["errors"], [])
            index = reading.build_index(self.project, "position-fixture", locate_pdf=True)

        self.assertEqual([s["quote"] for s in index["sentences"]], [original])
        sentence = index["sentences"][0]
        self.assertEqual(sentence["pdf_page"], 2)
        self.assertEqual(sentence["position_status"], "located_unique_normalized_word_sequence")
        self.assertEqual(sentence["coordinate_system"], "cropbox_points_top_left")
        self.assertEqual(sentence["page_size"], [300.0, 400.0])
        self.assertTrue(sentence["rects"])
        left, top, right, bottom = sentence["bbox"]
        self.assertTrue(35 <= left <= 37 and 80 <= top < bottom <= 110)
        self.assertTrue(left < right <= 300)
        self.assertTrue(index["source_positions_verified"])
        self.assertFalse(index["semantic_support_verified"])
        self.assertIn("position-fixture.pdf#page=2", (self.project / index["html_path"]).read_text(encoding="utf-8"))

    def test_positioned_boxes_use_actual_unique_word_sequence_and_keep_ambiguity(self):
        payload = b'<html><page width="100" height="200"><word xMin="1" yMin="2" xMax="10" yMax="9">Measured</word><word xMin="12" yMin="2" xMax="30" yMax="9">gain.</word></page></html>'
        page = reading._positioned_pages(payload)[0]
        result = reading._locate_sentence({"quote": "Measured gain."}, page)
        self.assertEqual(result["bbox"], [1.0, 2.0, 30.0, 9.0])
        self.assertEqual(result["position_status"], "located_unique_normalized_word_sequence")
        page["words"] *= 2
        ambiguous = reading._locate_sentence({"quote": "Measured gain.", "bbox": None}, page)
        self.assertEqual(ambiguous["position_status"], "ambiguous")
        self.assertIsNone(ambiguous["bbox"])
        missing = reading._locate_sentence({"quote": "A different result.", "bbox": None}, page)
        self.assertEqual(missing["position_status"], "not_found")

    def test_invalid_pdf_boxes_and_entities_are_refused(self):
        bad = b'<page width="100" height="200"><word xMin="-1" yMin="0" xMax="10" yMax="2">x</word></page>'
        with self.assertRaisesRegex(ValueError, "word box"):
            reading._positioned_pages(bad)
        with self.assertRaisesRegex(ValueError, "entities"):
            reading._positioned_pages(b'<!ENTITY x "unsafe"><page/>')

    def test_pdf_positioning_requires_explicit_cloud_execution(self):
        paper = {"reader": {"path": "evidence/readers/a.md"}, "source": {"path": "evidence/sources/a.pdf"}}
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "", "GITHUB_ACTIONS": ""}):
            with self.assertRaisesRegex(ValueError, "authorized cloud runner"):
                reading._pdf_positions(self.project, paper, [])

    def test_located_material_is_not_attributed_reading_and_missing_appendix_is_retained(self):
        self.add()
        self.build()
        report = reading.coverage(self.project, {"question": "Does calibration transfer?"})
        dimensions = {d["dimension"]: d for d in report["papers"][0]["dimensions"]}
        self.assertEqual(dimensions["methods"]["status"], "located_not_read")
        self.assertEqual(dimensions["appendix"]["status"], "not_located")
        self.assertEqual(report["reusable_evidence"], [])
        self.assertFalse(report["read_counts_prove_coverage"])
        self.assertFalse(report["human_full_text_reading_verified"])

    def test_current_progress_is_reused_only_for_matching_question_and_source(self):
        paper = self.add()
        self.build()
        question = "Does calibration transfer?"
        self.progress(paper, question)
        report = reading.coverage(self.project, {"question": question})
        methods = next(d for d in report["papers"][0]["dimensions"] if d["dimension"] == "methods")
        self.assertEqual(methods["status"], "attributed_answer_pending_semantic_review")
        self.assertEqual(len(methods["reusable_evidence"]), 1)
        self.assertEqual(methods["reusable_evidence"][0]["recorded_by"], "Synthetic fixture reader")
        again = reading.coverage(self.project, {"question": question})
        self.assertEqual(again["reusable_evidence"], report["reusable_evidence"])
        self.assertEqual(len(read(self.project / reasoning.PROGRESS)["events"]), 1)
        different = reading.coverage(self.project, {"question": "What is a different question?"})
        self.assertEqual(different["reusable_evidence"], [])

    def test_tampered_progress_and_report_are_not_silently_adopted(self):
        paper = self.add()
        self.build()
        self.progress(paper, "Question")
        progress = read(self.project / reasoning.PROGRESS)
        progress["events"][0]["answer"] = "Silently replaced."
        write(self.project / reasoning.PROGRESS, progress)
        with self.assertRaisesRegex(ValueError, "append-only provenance"):
            reading.coverage(self.project, {"question": "Question"})
        index = reading.build_index(self.project, "a")
        (self.project / index["html_path"]).write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "controlled builder"):
            reading.build_index(self.project, "a")

    def test_html_escapes_paper_content_and_no_external_scripts(self):
        self.add(text='<script>alert("external")</script> remains source text.')
        self.build()
        index = reading.build_index(self.project, "a")
        page = (self.project / index["html_path"]).read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn('<script>', page)
        self.assertIn("default-src 'none'", page)

    def test_request_scope_and_unknown_dimension_are_rejected(self):
        self.add()
        self.build()
        for request in ({"question": "Q", "dimensions": ["all"]}, {"question": "Q", "paper_ids": ["missing"]},
                        {"question": "Q", "approve_G1": True}, {"question": "Q", "dimensions": ["methods", "methods"]}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                reading.coverage(self.project, request)

    def test_different_coverage_scopes_do_not_overwrite_each_other(self):
        self.add("a")
        self.add("b")
        self.build()
        a = reading.coverage(self.project, {"question": "Question", "paper_ids": ["a"]})
        b = reading.coverage(self.project, {"question": "Question", "paper_ids": ["b"]})
        self.assertEqual(a["question_sha256"], b["question_sha256"])
        self.assertNotEqual(a["report_path"], b["report_path"])
        self.assertEqual(read(self.project / a["report_path"])["papers"][0]["paper_id"], "a")

    def test_unnumbered_original_headings_populate_supported_dimensions(self):
        self.add(text="Materials and methods\nWhole devices are held out.\nExperimental setup\nA fixed sensor is used.\n"
            "Experiments\nAll registered seeds are retained.\nEvaluation\nUncertainty is reported.\n"
            "Appendix A\nAdditional controls are described.\nSupplementary Materials\nThe protocol is supplied.\n")
        self.build()
        report = reading.coverage(self.project, {"question": "Which methods and supplementary evidence are available?"})
        dimensions = {d["dimension"]: d for d in report["papers"][0]["dimensions"]}
        for dimension in ("methods", "results", "appendix"):
            self.assertEqual(dimensions[dimension]["status"], "located_not_read")
            self.assertEqual(len(dimensions[dimension]["locations"]), 2)
        self.assertEqual(dimensions["methods"]["locations"][0]["end_line"], 2)
        self.assertEqual(dimensions["appendix"]["locations"][0]["start_line"], 9)

    def caption_paper(self, *, original=None, caption="Figure 1. Measured gain remains bounded.", page=2):
        original = original or "Measured body text.\nFigure 1. Measured gain remains bounded.\nUnrelated body text."
        reader = self.source("evidence/readers/caption.md", "## PDF page 2\n### Original extracted text\n" +
            original + "\n### Chinese reading translation\nAppendix A\nOnly translated supplementary text.\n")
        reader["page_ranges"] = {"2": [3, 2 + len(original.splitlines())]}
        return {"id": "caption", "source": {"path": "evidence/sources/caption.pdf", "sha256": "a" * 64},
            "reader": reader, "figure_manifest": {"assets": [{"path": "evidence/figures/caption.png", "sha256": "b" * 64,
                "occurrences": [{"pdf_page": page, "caption": caption}]}]}}

    def test_matching_figure_caption_binds_reader_lines_and_reuses_only_its_quote(self):
        paper = self.caption_paper(original="Measured body text.\nFigure 1. Measured gain remains bounded. Another observation.\nUnrelated body text.")
        location = reading._dimension_locations(self.project, paper)["figures"][0]
        self.assertEqual(location["path"], paper["reader"]["path"])
        self.assertEqual((location["start_line"], location["end_line"], location["pdf_page"]), (4, 4, 2))
        self.assertEqual(location["caption_attribution"], "exact_original_reader_caption")
        anchor = {**paper["reader"], "start_line": 4, "end_line": 4, "pdf_page": 2,
                  "quote": "Figure 1. Measured gain remains bounded."}
        self.assertTrue(reading._overlaps(anchor, location))
        self.assertFalse(reading._overlaps({**anchor, "quote": "Another observation."}, location))
        self.assertFalse(reading._overlaps({**anchor, "start_line": 3, "end_line": 3,
                                          "quote": "Measured body text."}, location))
        self.assertFalse(reading._overlaps({**anchor, "pdf_page": 1}, location))
        self.assertFalse(location["visual_understanding_verified"])

    def test_caption_wrapping_maps_exact_original_range_and_translation_headings_are_excluded(self):
        paper = self.caption_paper(original="Measured body text.\nFigure 1. Measured gain\nremains bounded.\nUnrelated body text.")
        locations = reading._dimension_locations(self.project, paper)
        caption = locations["figures"][0]
        self.assertEqual((caption["start_line"], caption["end_line"]), (4, 5))
        self.assertEqual(caption["quote"], "Figure 1. Measured gain\nremains bounded.")
        self.assertEqual(locations["appendix"], [])
        self.assertTrue(reading._overlaps({**paper["reader"], "start_line": 4, "end_line": 5,
                                          "pdf_page": 2, "quote": caption["quote"]}, caption))

    def test_unmatched_ambiguous_or_wrong_page_captions_are_explicitly_not_attributable(self):
        for arguments, expected in (({"caption": "Absent original caption."}, "caption_not_found_in_original_reader"),
            ({"original": "Figure 1. Measured gain remains bounded.\nFigure 1. Measured gain remains bounded."},
             "ambiguous_original_caption"), ({"page": 3}, "original_reader_page_unavailable"),
            ({"caption": None}, "missing_caption")):
            with self.subTest(expected=expected):
                paper = self.caption_paper(**arguments)
                location = reading._dimension_locations(self.project, paper)["figures"][0]
                self.assertEqual(location["caption_attribution"], "not_attributable")
                self.assertEqual(location["caption_match_status"], expected)
                self.assertNotIn("start_line", location)
                self.assertFalse(reading._overlaps({**paper["reader"], "start_line": 4, "end_line": 4,
                    "pdf_page": location["pdf_page"], "quote": "Unrelated body text."}, location))


if __name__ == "__main__":
    unittest.main()
