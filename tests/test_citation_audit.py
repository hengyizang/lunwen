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

    def test_included_tex_is_hashed_and_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);bibliography=root/"references.bib";bibliography.write_text("@misc{known,\n title={Known}\n}\n",encoding="utf-8");(root/"main.tex").write_text("\\input{section}",encoding="utf-8");section=root/"section.tex";section.write_text("Evidence \\cite{missing}.",encoding="utf-8")
            report=audit(bibliography,offline=True);before=report["manuscript_sha256"]
            self.assertIn("missing",report["citation_usage"]["missing_bibliography_keys"])
            section.write_text("Changed evidence \\cite{missing}.",encoding="utf-8")
            self.assertNotEqual(before,audit(bibliography,offline=True)["manuscript_sha256"])

    def test_docx_citation_mapping_requires_named_human(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            import zipfile
            root=Path(temp);bibliography=root/"references.bib";bibliography.write_text("@misc{known,\n title={Known}\n}\n",encoding="utf-8")
            with zipfile.ZipFile(root/"main.docx","w") as archive:archive.writestr("word/document.xml",'<w:document xmlns:w="urn:w"><w:t>Known 2026</w:t></w:document>')
            self.assertEqual(audit(bibliography,offline=True)["citation_usage"]["status"],"human_check_required")
            self.assertEqual(audit(bibliography,offline=True,docx_verified_by="Researcher")["citation_usage"]["status"],"human_verified")


if __name__ == "__main__":
    unittest.main()
