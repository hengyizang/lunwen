from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.venue_adapter import sha256_file
from scripts.venue_compliance import compliance_report


class VenueComplianceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.paper = Path(temporary.name) / "P01"
        manuscript = self.paper / "manuscript"
        template = self.paper / "venue-template"
        manuscript.mkdir(parents=True)
        template.mkdir()
        (manuscript / "main.tex").write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "\\begin{abstract}Evidence.\\end{abstract}\n"
            "\\section{Introduction}Text.\n\\end{document}\n", encoding="utf-8")
        style = template / "journal.cls"
        style.write_text("fixture", encoding="utf-8")
        (template / "template-inventory.json").write_text(json.dumps({
            "archive_sha256": "a" * 64,
            "extracted_file_sha256": {"journal.cls": sha256_file(style)}}), encoding="utf-8")
        (self.paper / "venue.json").write_text(json.dumps({"venue_id": "fixture",
            "requirements": {"original_article_max_word_equivalents": 1000}}), encoding="utf-8")

    def test_missing_latex_tool_is_an_actionable_nonpassing_check(self):
        with patch("scripts.venue_compliance.shutil.which", return_value=None):
            report = compliance_report(self.paper)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["template"]["status"], "pass")
        self.assertEqual(report["manuscript"]["status"], "pass")
        self.assertEqual(report["compile"]["status"], "skipped_tool_missing")
        self.assertTrue(report["compile"]["required"])
        self.assertTrue(any("install" in gap for gap in report["gaps"]))

    def test_explicit_no_compile_cannot_claim_final_compliance(self):
        report = compliance_report(self.paper, no_compile=True)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["compile"]["status"], "not_requested")
        self.assertTrue(report["compile"]["required"])
        self.assertTrue(report["gaps"])

    def test_success_requires_executed_build_and_hashes_its_actual_output(self):
        # This native subprocess is an inert compiler boundary fixture, not an
        # actual publisher LaTeX build or evidence of manuscript quality.
        compiler = self.paper.parent / "synthetic-latexmk"
        compiler.write_text(f"#!{sys.executable}\n"
            "import sys\nfrom pathlib import Path\n"
            "out = Path(next(arg[8:] for arg in sys.argv if arg.startswith('-outdir=')))\n"
            "(out / 'main.pdf').write_bytes(b'%PDF-1.4 synthetic software fixture')\n", encoding="utf-8")
        compiler.chmod(0o700)
        with patch("scripts.venue_compliance.shutil.which", return_value=str(compiler)):
            report = compliance_report(self.paper)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["compile"]["status"], "pass")
        self.assertEqual(report["compile"]["pdf_sha256"], sha256_file(self.paper / "build/main.pdf"))
        self.assertEqual(report["gaps"], [])

    def test_docx_marks_only_latex_compilation_not_applicable(self):
        (self.paper / "manuscript/main.tex").unlink()
        with zipfile.ZipFile(self.paper / "manuscript/main.docx", "w") as archive:
            archive.writestr("word/document.xml", '<document xmlns:w="urn:synthetic-word"><w:t>Abstract Introduction synthetic study.</w:t></document>')
        report = compliance_report(self.paper)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["compile"]["status"], "not_applicable")
        self.assertFalse(report["compile"]["required"])


if __name__ == "__main__":
    unittest.main()
