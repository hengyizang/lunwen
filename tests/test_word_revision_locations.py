from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree as ET

from scripts import docx_revision, revision_render, revision_trace
from scripts.scientific_editing import docx_citations, formula_tokens


def field(paragraph):
    nodes = []
    for kind in ("begin", "instruction", "separate", "display", "end"):
        run = OxmlElement("w:r")
        if kind in {"begin", "separate", "end"}:
            item = OxmlElement("w:fldChar")
            item.set(qn("w:fldCharType"), kind)
        else:
            item = OxmlElement("w:instrText" if kind == "instruction" else "w:t")
            item.text = " CITATION alpha2025 " if kind == "instruction" else "(Alpha, 2025)"
        run.append(item)
        paragraph._p.append(run)
        nodes.append(run)
    return nodes


def equation(paragraph):
    math = OxmlElement("m:oMath")
    run, text = OxmlElement("m:r"), OxmlElement("m:t")
    text.text = "x = 1"
    run.append(text)
    math.append(run)
    paragraph._p.append(math)
    return math


def image(paragraph):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (3, 3), "white").save(buffer, format="PNG")
    buffer.seek(0)
    paragraph.add_run().add_picture(buffer)


class WordComplexRevisionTests(unittest.TestCase):
    def round_trip(self, root, base, clean):
        old, new = docx_revision.package(base), docx_revision.package(clean)
        payload = docx_revision.track(old, new, "Doctoral Research OS", "2026-10-09T00:00:00Z")
        tracked = ET.fromstring(payload)
        self.assertTrue(set(ET.fromstring(new[docx_revision.DOCUMENT]).nsmap).issubset(tracked.nsmap))
        results = []
        for accept, expected in ((True, new), (False, old)):
            resolved = docx_revision.resolve(tracked, accept)
            self.assertEqual(docx_revision.canonical(resolved), docx_revision.canonical(ET.fromstring(expected[docx_revision.DOCUMENT])))
            target = root / ("accepted.docx" if accept else "rejected.docx")
            with zipfile.ZipFile(target, "w") as archive:
                for name, content in new.items():
                    archive.writestr(name, ET.tostring(resolved) if name == docx_revision.DOCUMENT else content)
            # A genuine Word package can be reopened, with all other parts
            # still byte-identical to the clean and baseline documents.
            Document(target)
            self.assertEqual({k: v for k, v in docx_revision.package(target).items() if k != docx_revision.DOCUMENT},
                             {k: v for k, v in new.items() if k != docx_revision.DOCUMENT})
            results.append(target)
        return tracked, results

    def test_text_and_table_cell_changes_keep_real_fields_math_and_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, clean = root / "base.docx", root / "clean.docx"
            doc = Document()
            paragraph = doc.add_paragraph()
            paragraph.add_run("The effect may improve. ")
            field(paragraph)
            equation(paragraph)
            image(paragraph)
            doc.add_paragraph("Unchanged anchor")
            doc.add_table(rows=1, cols=1).cell(0, 0).text = "Original table explanation"
            doc.save(base)
            changed = Document(base)
            changed.paragraphs[0].runs[0].text = "The effect might improve. "
            changed.tables[0].cell(0, 0).paragraphs[0].runs[0].text = "Revised table explanation"
            changed.save(clean)
            tracked, targets = self.round_trip(root, base, clean)
            self.assertIsNotNone(tracked.find(".//" + docx_revision.W + "delText"))
            for target, expected in zip(targets, (clean, base)):
                self.assertEqual(docx_citations(target), docx_citations(expected))
                self.assertEqual(formula_tokens(target), formula_tokens(expected))
                self.assertEqual(Document(target).tables[0].cell(0, 0).text, Document(expected).tables[0].cell(0, 0).text)
                self.assertEqual(len(Document(target).inline_shapes), 1)

    def test_paragraph_addition_and_removal_have_real_mark_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, clean = root / "base.docx", root / "clean.docx"
            doc = Document()
            for text in ("First paragraph", "Removed explanation", "Final unchanged anchor"):
                doc.add_paragraph(text)
            doc.save(base)
            changed = Document(base)
            changed.paragraphs[0].insert_paragraph_before("Inserted explanation")
            deleted = changed.paragraphs[2]._p
            deleted.getparent().remove(deleted)
            changed.save(clean)
            tracked, targets = self.round_trip(root, base, clean)
            for tag in ("ins", "del"):
                self.assertIsNotNone(tracked.find(".//" + docx_revision.W + "pPr/" + docx_revision.W + "rPr/" + docx_revision.W + tag))
            for target, expected in zip(targets, (clean, base)):
                self.assertEqual([p.text for p in Document(target).paragraphs], [p.text for p in Document(expected).paragraphs])

    def test_unchanged_citation_and_equation_can_move_without_flattening(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, clean = root / "base.docx", root / "clean.docx"
            doc = Document()
            paragraph = doc.add_paragraph("The effect may improve. ")
            field(paragraph)
            equation(paragraph)
            paragraph.add_run("Final interpretation.")
            doc.save(base)
            changed = Document(base)
            paragraph = changed.paragraphs[0]
            math = paragraph._p.find(qn("m:oMath"))
            paragraph._p.remove(math)
            paragraph._p.insert(0, math)
            citation = list(paragraph._p)[2:7]
            for node in citation:
                paragraph._p.remove(node)
                paragraph._p.append(node)
            changed.save(clean)
            _, targets = self.round_trip(root, base, clean)
            for target in targets:
                self.assertIn("CITATION alpha2025", docx_citations(target))
                self.assertEqual(len(formula_tokens(target)), 1)

    def test_changed_math_and_changed_style_are_explicitly_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, clean = root / "base.docx", root / "clean.docx"
            doc = Document()
            equation(doc.add_paragraph("The result may improve. "))
            doc.save(base)
            changed = Document(base)
            changed.paragraphs[0]._p.find(".//" + qn("m:t")).text = "x = 2"
            changed.save(clean)
            with self.assertRaisesRegex(ValueError, "changed fields, equations"):
                docx_revision.track(docx_revision.package(base), docx_revision.package(clean), "OS", "date")
            changed = Document(base)
            changed.paragraphs[0].runs[0].text = "The result might improve. "
            changed.paragraphs[0].runs[0].bold = True
            changed.save(clean)
            with self.assertRaisesRegex(ValueError, "formatting"):
                docx_revision.track(docx_revision.package(base), docx_revision.package(clean), "OS", "date")

    def test_image_moves_and_table_topology_changes_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, clean = root / "base.docx", root / "clean.docx"
            doc = Document()
            image(doc.add_paragraph("First"))
            doc.add_paragraph("Second")
            doc.add_table(rows=1, cols=1).cell(0, 0).text = "Preserved data"
            doc.save(base)
            changed = Document(base)
            run = changed.paragraphs[0].runs[-1]._r
            run.getparent().remove(run)
            changed.paragraphs[1]._p.append(run)
            changed.save(clean)
            with self.assertRaisesRegex(ValueError, "image moves duplicate"):
                docx_revision.track(docx_revision.package(base), docx_revision.package(clean), "OS", "date")
            changed = Document(base)
            changed.tables[0].add_row()
            changed.save(clean)
            with self.assertRaisesRegex(ValueError, "table topology"):
                docx_revision.track(docx_revision.package(base), docx_revision.package(clean), "OS", "date")


class RevisionLocationTests(unittest.TestCase):
    def paper(self, root):
        paper = root / "papers/P01"
        (paper / "manuscript").mkdir(parents=True)
        (paper / "reviews").mkdir()
        return paper

    def matrix(self, paper, location, excerpt="The effect may improve.", status="fulfilled"):
        with (paper / "reviews/response-matrix.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted(revision_trace.REQUIRED_COLUMNS))
            writer.writeheader()
            writer.writerow({"comment_id": "R1-C1", "commitment_id": "K1", "fulfillment_status": status,
                             "location": json.dumps(location) if isinstance(location, dict) else location,
                             "revised_text": excerpt, "unfulfilled_rationale": "Remaining exploratory check" if status == "partial" else ""})

    def source(self, paper):
        main = paper / "manuscript/main.tex"
        main.write_text("\\documentclass{article}\n\\begin{document}\n\\section{Results}\nThe effect may improve.\n\\end{document}\n", encoding="utf-8")
        return main

    def test_source_lines_are_current_actual_and_canonical(self):
        with tempfile.TemporaryDirectory() as directory:
            paper = self.paper(Path(directory))
            main = self.source(paper)
            location = {"kind": "source_lines", "path": "manuscript/main.tex", "sha256": revision_trace.sha256_file(main), "start_line": 4}
            self.matrix(paper, location)
            self.assertEqual(revision_trace.audit(paper)["status"], "pass")
            for altered in ({**location, "start_line": 3}, {**location, "start_line": 100}, {**location, "sha256": "0" * 64}):
                self.matrix(paper, altered)
                self.assertEqual(revision_trace.audit(paper)["status"], "fail")
            unused = paper / "manuscript/unused.tex"
            unused.write_text("The effect may improve.")
            self.matrix(paper, {**location, "path": "manuscript/unused.tex", "sha256": revision_trace.sha256_file(unused), "start_line": 1})
            self.assertEqual(revision_trace.audit(paper)["status"], "fail")

    def test_actual_include_lines_and_legacy_section_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            paper = self.paper(Path(directory))
            main = self.source(paper)
            source = paper / "manuscript/results.tex"
            source.write_text("\\section{Results}\nThe effect may improve.\n")
            main.write_text("\\documentclass{article}\n\\begin{document}\n\\input{results}\n\\end{document}\n")
            self.matrix(paper, {"kind": "source_lines", "path": "manuscript/results.tex", "sha256": revision_trace.sha256_file(source), "start_line": 2})
            self.assertEqual(revision_trace.audit(paper)["status"], "pass")
            self.matrix(paper, "Results")
            self.assertEqual(revision_trace.audit(paper)["status"], "pass")
            self.matrix(paper, "Discussion")
            self.assertEqual(revision_trace.audit(paper)["status"], "fail")
            source.write_text("\\section{Results}\nThe effect may improve.\n\\section{Results}\nThe effect may improve.\n")
            self.matrix(paper, "Results")
            self.assertEqual(revision_trace.audit(paper)["status"], "fail")

    def test_word_paragraph_and_real_table_cell_math_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            paper = self.paper(Path(directory))
            main = paper / "manuscript/main.docx"
            doc = Document()
            doc.add_heading("Results", level=1)
            doc.add_paragraph("The effect may improve.")
            table = doc.add_table(rows=1, cols=1)
            table.cell(0, 0).text = "Unchanged bound equation "
            equation(table.cell(0, 0).paragraphs[0])
            doc.save(main)
            location = {"kind": "docx_paragraph", "path": "manuscript/main.docx", "sha256": revision_trace.sha256_file(main), "paragraph": 2}
            self.matrix(paper, location)
            self.assertEqual(revision_trace.audit(paper)["status"], "pass")
            self.matrix(paper, {**location, "paragraph": 1})
            self.assertEqual(revision_trace.audit(paper)["status"], "fail")
            location.update(kind="docx_table_cell", table=1, row=1, column=1, paragraph=1)
            self.matrix(paper, location, "x = 1")
            self.assertEqual(revision_trace.audit(paper)["status"], "pass")
            self.matrix(paper, {**location, "row": 2}, "x = 1")
            self.assertEqual(revision_trace.audit(paper)["status"], "fail")

    def test_partial_commitments_and_invented_word_pages_do_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            paper = self.paper(Path(directory))
            self.source(paper)
            self.matrix(paper, "Page 1 lines 4-6", status="partial")
            self.assertEqual(revision_trace.audit(paper)["status"], "fail")
            self.matrix(paper, {"kind": "pdf_lines", "path": "manuscript/main.pdf", "sha256": "0" * 64, "page": 1, "start_line": 1})
            self.assertEqual(revision_trace.audit(paper)["status"], "fail")

    def test_real_pdf_page_lines_refuse_wrong_pages_stale_source_and_fabricated_lines(self):
        import fitz
        with tempfile.TemporaryDirectory() as directory:
            paper = self.paper(Path(directory))
            main = self.source(paper)
            pdf = paper / "manuscript/main.pdf"
            with fitz.open() as document:
                document.new_page().insert_text((72, 72), "Wrong-page excerpt")
                document.new_page().insert_text((72, 72), "The effect may improve.")
                document.save(pdf)
            # Synthetic protected receipt tests validation boundaries only.
            from scripts.output_provenance import record_model_writes
            receipt = paper / "reviews/cloud-tex-build.json"
            payload = {"schema_version": "1.0", "status": "pass",
                "inputs": [{"path": (paper / item["path"]).relative_to(paper.parents[1]).as_posix(), "sha256": item["sha256"]} for item in revision_render.source_hashes(paper)],
                "outputs": [{"path": pdf.relative_to(paper.parents[1]).as_posix(), "sha256": revision_trace.sha256_file(pdf)}],
                "renderer": {"name": "cloud_runtime", "implementation_sha256": revision_trace.sha256_file(Path(revision_render.__file__).resolve().parent / "cloud_runtime.py")},
                "execution": {"mode": "cloud", "receipt_id": "synthetic-render-fixture-1"}}
            receipt.write_text(json.dumps(payload))
            record_model_writes(paper.parents[1], [receipt], family="other", provider="cloud-tex-renderer", model="scripts/cloud_runtime.py", role="render-receipt", run_id="synthetic-render-fixture-1")
            with self.assertRaisesRegex(ValueError, "receipt"):
                revision_render.build_render_manifest(paper, pdf, "synthetic-test-renderer", "fixture-1")
            manifest = revision_render.build_render_manifest(paper, pdf, "synthetic-test-renderer", "fixture-1", rendering_receipt=receipt)
            location = {"kind": "pdf_lines", "path": "manuscript/main.pdf", "sha256": manifest["pdf"]["sha256"], "page": 2, "start_line": 1}
            self.matrix(paper, location)
            self.assertEqual(revision_trace.audit(paper)["status"], "pass")
            self.matrix(paper, {**location, "page": 1})
            self.assertEqual(revision_trace.audit(paper)["status"], "fail")
            self.matrix(paper, location)
            manifest["pages"][1]["lines"] = ["Fabricated passage"]
            (paper / "reviews/revision-render.json").write_text(json.dumps(manifest))
            self.assertEqual(revision_trace.audit(paper)["status"], "fail")
            revision_render.build_render_manifest(paper, pdf, "synthetic-test-renderer", "fixture-1", rendering_receipt=receipt)
            main.write_text(main.read_text() + "\nChanged scientific source\n")
            self.assertEqual(revision_trace.audit(paper)["status"], "fail")

    def test_saved_trace_is_stale_after_location_or_manuscript_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            paper = self.paper(Path(directory))
            self.source(paper)
            self.matrix(paper, "Results")
            report = revision_trace.audit(paper)
            (paper / "reviews/revision-trace.json").write_text(json.dumps(report))
            self.assertEqual(revision_trace.validate_saved_report(paper), [])
            self.matrix(paper, "Discussion")
            self.assertTrue(revision_trace.validate_saved_report(paper))


if __name__ == "__main__":
    unittest.main()
