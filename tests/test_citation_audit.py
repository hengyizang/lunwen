from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.citation_audit import audit


class CitationAuditTests(unittest.TestCase):
    def test_crossref_match_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            bibliography = Path(temp) / "references.bib"
            bibliography.write_text(
                """@article{smith2025,
  title = {A Reliable Structural Model},
  year = {2025},
  doi = {10.1234/example}
}
""",
                encoding="utf-8",
            )

            def fetcher(url: str):
                return {
                    "message": {
                        "title": ["A Reliable Structural Model"],
                        "issued": {"date-parts": [[2025]]},
                        "type": "journal-article",
                        "URL": "https://doi.org/10.1234/example",
                    }
                }

            report = audit(bibliography, fetcher=fetcher)
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["verified_count"], 1)

    def test_missing_verification_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            bibliography = Path(temp) / "references.bib"
            bibliography.write_text(
                "@misc{unknown,\n  title = {Unknown source}\n}\n", encoding="utf-8"
            )
            report = audit(bibliography, offline=True)
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["unresolved_keys"], ["unknown"])

    def test_missing_tex_citation_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bibliography = root / "references.bib"
            bibliography.write_text(
                "@misc{known,\n  title = {Known source}\n}\n", encoding="utf-8"
            )
            (root / "main.tex").write_text(
                "Evidence \\cite{known,missing}.", encoding="utf-8"
            )
            manual = root / "manual.json"
            manual.write_text(
                """{
  "known": {
    "verified_by": "Human",
    "verified_at": "2026-08-17T00:00:00+00:00",
    "source_url": "https://example.org/known",
    "title": "Known source"
  }
}
""",
                encoding="utf-8",
            )
            report = audit(bibliography, manual_path=manual, offline=True)
            self.assertEqual(report["status"], "fail")
            self.assertEqual(
                report["citation_usage"]["missing_bibliography_keys"], ["missing"]
            )


if __name__ == "__main__":
    unittest.main()
