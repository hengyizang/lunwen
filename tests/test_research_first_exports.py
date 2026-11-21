"""Actual local files exercise selection, draft export and conversion boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import manuscript_docx, submission_package, tex_sources, venue_compliance
from scripts.research_artifacts import write


class ResearchFirstExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "study"
        self.paper = self.project / "papers/P01"
        self.manuscript = self.paper / "manuscript"
        self.manuscript.mkdir(parents=True)

    def test_draft_exports_without_state_venue_provenance_or_reviews(self):
        (self.manuscript / "main.md").write_text("# Draft\nAn unresolved research question.\n")
        (self.paper / "figures").mkdir()
        (self.paper / "figures/unused.txt").write_text("Unselected working material")
        with patch.object(submission_package, "project_dir", return_value=self.project), \
                patch.object(submission_package, "submission_checks", side_effect=AssertionError("No final checks for a draft")):
            archive = submission_package.build_package("study", "P01", draft=True)
            original = archive.read_bytes()
            self.assertEqual(submission_package.build_package("study", "P01", draft=True).read_bytes(), original)
        with zipfile.ZipFile(archive) as saved:
            self.assertEqual(set(saved.namelist()), {"manuscript/main.md", "DRAFT-MANIFEST.json", "DRAFT-README.txt"})
            manifest = json.loads(saved.read("DRAFT-MANIFEST.json"))
        self.assertEqual(manifest["submission_mode"], "draft_unreviewed")
        self.assertFalse(manifest["submission_ready"])
        self.assertFalse((self.project / "state").exists())

    def test_selected_outputs_exclude_unused_variants_recipes_and_supplements(self):
        source = self.manuscript / "main.tex"
        source.write_text("\\documentclass{article}\n\\graphicspath{{../figures/}}\n\\includegraphics{chart}\n")
        (self.paper / "figures").mkdir()
        for name in ("chart.pdf", "chart.svg", "chart.figure-build.json", "unused.pdf"):
            (self.paper / "figures" / name).write_text("Synthetic locator content")
        (self.paper / "supplement").mkdir()
        (self.paper / "supplement/table.csv").write_text("item,value\na,1\n")
        before = venue_compliance.manuscript_tree_sha256(source)
        selected = {path.relative_to(self.paper).as_posix() for path in submission_package.select_files(self.paper)}
        self.assertEqual(selected, {"manuscript/main.tex", "figures/chart.pdf"})
        (self.paper / "figures/unused.pdf").write_text("Changed unused working draft")
        self.assertEqual(venue_compliance.manuscript_tree_sha256(source), before)
        write(self.paper / "submission-files.json", {"files": ["supplement/table.csv"]})
        selected = {path.relative_to(self.paper).as_posix() for path in submission_package.select_files(self.paper)}
        self.assertEqual(selected, {"manuscript/main.tex", "figures/chart.pdf", "supplement/table.csv"})

    def test_graphic_extension_order_and_safe_nested_relative_input(self):
        parts = self.manuscript / "sections"; parts.mkdir()
        source = self.manuscript / "main.tex"
        source.write_text("\\input{sections/part}\n")
        (parts / "part.tex").write_text("\\input{../sections/evidence}\n")
        (parts / "evidence.tex").write_text("Actual included evidence.\n")
        self.assertIn("Actual included evidence.", tex_sources.expand(source).text)
        for suffix in ("pdf", "png", "svg"):
            (self.manuscript / ("chart." + suffix)).write_text("synthetic image locator")
        self.assertEqual(tex_sources.resolve_graphic("chart", working=self.manuscript, paper=self.paper).suffix, ".pdf")
        self.assertEqual(tex_sources.resolve_graphic("chart", working=self.manuscript, paper=self.paper,
            text="\\DeclareGraphicsExtensions{.png,.pdf}").suffix, ".png")

    def test_plain_docx_converter_refuses_math_before_replacing_previous_output(self):
        source = self.manuscript / "source.md"; source.write_text("# Results\nPlain observation.\n")
        metadata = self.manuscript / "metadata.json"
        write(metadata, {"schema_version": "1.0", "title": "Draft study", "abstract": "A bounded observation.",
                         "authors": [{"name": "Researcher"}], "keywords": ["observation"]})
        output = self.manuscript / "main.docx"
        manuscript_docx.build(self.project, source, metadata, output, prefer_pandoc=False)
        self.assertEqual(manuscript_docx.validate_saved_report(self.paper, include_visual=False), [])
        original = output.read_bytes()
        source.write_text("# Results\nThe estimate is $x^2$.\n")
        with self.assertRaisesRegex(ValueError, "cannot preserve mathematical"):
            manuscript_docx.build(self.project, source, metadata, output, prefer_pandoc=False)
        self.assertEqual(output.read_bytes(), original)

    def test_native_word_manuscript_needs_no_invented_conversion_receipt(self):
        from docx import Document
        output = self.manuscript / "main.docx"
        document = Document(); document.add_paragraph("Native Word manuscript."); document.save(output)
        self.assertEqual(manuscript_docx.validate_saved_report(self.paper, include_visual=False), [])
        self.assertFalse((self.paper / "reviews/docx-build.json").exists())

    def test_selected_internal_or_credential_material_is_rejected_for_drafts(self):
        (self.manuscript / "main.md").write_text("Draft")
        for relative in ("../private.csv", "reviews/internal.json", "submission-materials/portal.key"):
            write(self.paper / "submission-files.json", {"files": [relative]})
            with self.subTest(relative=relative), self.assertRaises(submission_package.ResearchCtlError):
                submission_package.select_files(self.paper, draft=True)
