from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.venue_adapter import sha256_file
from scripts.venue_compliance import compliance_report


class VenueComplianceTests(unittest.TestCase):
    def test_latex_manuscript_and_template_inventory_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paper = Path(temp) / "P01"
            manuscript = paper / "manuscript"
            template = paper / "venue-template"
            manuscript.mkdir(parents=True)
            template.mkdir()
            (manuscript / "main.tex").write_text(
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "\\begin{abstract}Evidence.\\end{abstract}\n"
                "\\section{Introduction}Text.\n"
                "\\end{document}\n",
                encoding="utf-8",
            )
            style = template / "journal.cls"
            style.write_text("fixture", encoding="utf-8")
            (template / "template-inventory.json").write_text(
                json.dumps(
                    {
                        "archive_sha256": "a" * 64,
                        "extracted_file_sha256": {"journal.cls": sha256_file(style)},
                    }
                ),
                encoding="utf-8",
            )
            (paper / "venue.json").write_text(
                json.dumps(
                    {
                        "venue_id": "fixture",
                        "requirements": {"original_article_max_word_equivalents": 1000},
                    }
                ),
                encoding="utf-8",
            )
            report = compliance_report(paper, no_compile=False)
            self.assertEqual(report["status"], "pass")
            self.assertIn(
                report["compile"]["status"], {"pass", "skipped_tool_missing"}
            )


if __name__ == "__main__":
    unittest.main()
