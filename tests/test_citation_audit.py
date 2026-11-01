from __future__ import annotations

import tempfile
import unittest
import zipfile
import json
from pathlib import Path

from scripts.citation_audit import audit, parse_bibtex, docx_citation_keys, validate_provider_identities


class CitationAuditTests(unittest.TestCase):
    def test_docx_explicit_keys_need_no_human_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"references.bib").write_text('@article{abc, title={Example}, year=2024, doi={10.1234/test}}', encoding="utf-8")
            docx=root/"main.docx"
            with zipfile.ZipFile(docx,"w") as package:
                package.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Evidence [@abc].</w:t></w:r></w:p></w:body></w:document>')
            report=audit(root/"references.bib", fetcher=lambda url: {"message":{"title":["Example"],"issued":{"date-parts":[[2024]]}}})
            self.assertEqual(report["citation_usage"]["status"], "checked_automatically")
            self.assertEqual(report["status"],"pass")
            with zipfile.ZipFile(docx,"w") as package:
                package.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Evidence [1].</w:t></w:r></w:p></w:body></w:document>')
            self.assertTrue(docx_citation_keys(docx)[1])
    def test_single_line_bibtex_preserves_nested_and_quoted_fields(self) -> None:
        entries = parse_bibtex('@article{abc, title={A {Nested}, Title}, year=2024, doi="10.1234/test"}')
        self.assertTrue(entries[0]["balanced"])
        self.assertEqual(entries[0]["fields"], {"title": "A {Nested}, Title", "year": "2024", "doi": "10.1234/test"})

    def test_unsupported_bibtex_macro_is_not_treated_as_valid_metadata(self) -> None:
        self.assertFalse(parse_bibtex('@article{abc, title=journalname, year=2024}')[0]["balanced"])

    def test_extra_citation_commands_and_verified_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bib = root / "references.bib"
            bib.write_text('@article{abc, title={Example}, year={2024}, doi={10.1234/test}}', encoding="utf-8")
            (root / "main.tex").write_text(r'\citeauthor{missing1} \citeyear{missing2} \footcite{missing3}', encoding="utf-8")
            report = audit(bib, fetcher=lambda url: {"message": {"title": ["Example"], "issued": {"date-parts": [[2024]]}}})
            self.assertEqual(report["citation_usage"]["missing_bibliography_keys"], ["missing1", "missing2", "missing3"])
            self.assertEqual(report["verified_count"], 1)
            self.assertEqual(report["status"], "fail")
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

    def test_unsupported_docx_mapping_cannot_be_bypassed_by_a_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            import zipfile
            root=Path(temp);bibliography=root/"references.bib";bibliography.write_text("@misc{known,\n title={Known}\n}\n",encoding="utf-8")
            with zipfile.ZipFile(root/"main.docx","w") as archive:archive.writestr("word/document.xml",'<w:document xmlns:w="urn:w"><w:t>Known 2026</w:t></w:document>')
            self.assertEqual(audit(bibliography,offline=True)["citation_usage"]["status"],"mapping_required")
            self.assertEqual(audit(bibliography,offline=True,docx_verified_by="Researcher")["citation_usage"]["status"],"mapping_required")


class ProviderIdentityTests(unittest.TestCase):
    """Real metadata normalizer/controller receipts using offline synthetic bytes."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)/"fixture"
        self.bib = self.project/"papers/P01/manuscript/references.bib"
        self.bib.parent.mkdir(parents=True)
        self.source = {"paperId": "synthetic1", "title": "A Reliable Structural Model", "year": 2024,
            "url": "https://example.org/paper", "authors": [{"name": "Ada Lovelace"}, {"name": "Grace Hopper"}]}
        self.save_bib()

    def save_bib(self, *, title="A Reliable Structural Model", year="2024", author="Lovelace, Ada and Hopper, Grace", url="https://example.org/paper", extra=""):
        self.bib.write_text("@misc{known, title={"+title+"}, year={"+year+"}, author={"+author+"}, url={"+url+"}"+extra+"}", encoding="utf-8")

    def search(self, works=None, *, provider="semantic-scholar", payload=None):
        from scripts import literature_evidence as evidence
        payload = payload or json.dumps({"data": works or [self.source]}).encode()
        return evidence.execute_search(self.project, provider, "synthetic fixture only", query_family="fixture",
            date_range="2024", filters="none", limit=10,
            fetcher=lambda url, **kwargs: (payload, url, 200, "application/json"))

    def checked(self):
        return audit(self.bib, offline=True, fetcher=lambda *_: self.fail("identity verification must make no network call"))

    def test_actual_executed_metadata_verifies_identity_without_human_or_claim_support(self):
        from scripts.output_provenance import current_origin
        receipt = self.search()
        for relative in (receipt["raw_response_path"], receipt["normalized_results_path"], "evidence/literature-api-ledger.jsonl"):
            self.assertEqual(current_origin(self.project, self.project/relative)["model"], "scripts/literature_evidence.py")
        report = self.checked()
        self.assertEqual(report["status"], "pass")
        identity = report["findings"][0]["provider_identity"]
        self.assertFalse(identity["human_verification"])
        self.assertFalse(identity["claim_support_verified"])
        self.assertFalse(identity["rights_verified"])
        self.assertEqual(validate_provider_identities(self.bib, report), [])
        # A genuine later controller append must not make the old selected row
        # lose provenance or alter its immutable identity bindings.
        self.search()
        self.assertEqual(validate_provider_identities(self.bib, report), [])
        from scripts import literature_evidence as evidence
        def unavailable(*_args, **_kwargs):
            raise OSError("Synthetic provider unavailable; no actual request")
        with self.assertRaises(evidence.LiteratureEvidenceError):
            evidence.execute_search(self.project, "semantic-scholar", "unrelated failed fixture", query_family="fixture",
                date_range="2024", filters="none", limit=10, fetcher=unavailable)
        self.assertEqual(validate_provider_identities(self.bib, report), [])

    def test_title_year_authors_and_url_mismatches_remain_unverified(self):
        self.search()
        for change in ({"title": "A Different Structural Model"}, {"year": "2023"},
                       {"author": "Lovelace, Ada"}, {"author": "Hopper, Grace and Lovelace, Ada"},
                       {"url": "https://example.org/other"}):
            with self.subTest(change=change):
                self.save_bib(**change)
                self.assertEqual(self.checked()["status"], "fail")

    def test_missing_or_modified_controller_provenance_cannot_verify_identity(self):
        receipt = self.search()
        registry = self.project/"state/output-provenance.json"
        original = registry.read_bytes()
        registry.unlink()
        self.assertEqual(self.checked()["status"], "fail")
        registry.write_bytes(original)
        raw = self.project/receipt["raw_response_path"]
        raw.write_bytes(raw.read_bytes()+b" ")
        self.assertEqual(self.checked()["status"], "fail")

    def test_forged_normalized_metadata_fails_raw_replay_even_with_controller_origin(self):
        from scripts import output_provenance
        receipt = self.search()
        normalized = self.project/receipt["normalized_results_path"]
        value = json.loads(normalized.read_text(encoding="utf-8"))
        value["works"][0]["publication_year"] = 2023
        normalized.write_text(json.dumps(value), encoding="utf-8")
        from scripts.citation_audit import sha256_file
        ledger = self.project/"evidence/literature-api-ledger.jsonl"
        row = json.loads(ledger.read_text(encoding="utf-8"))
        row["normalized_results_sha256"] = sha256_file(normalized)
        ledger.write_text(json.dumps(row)+"\n", encoding="utf-8")
        output_provenance.record_model_writes(self.project, [normalized, ledger], family="other",
            provider="deterministic-control-plane", model="scripts/literature_evidence.py", role="fixture", run_id="fixture")
        self.save_bib(year="2023")
        report = self.checked()
        self.assertEqual(report["status"], "fail")
        self.assertIn("replay", report["findings"][0]["issues"][0])

    def test_ambiguous_records_require_exact_existing_receipt_and_work_selection(self):
        receipt = self.search([self.source, {**self.source, "paperId": "synthetic2"}])
        self.assertEqual(self.checked()["status"], "fail")
        self.save_bib(extra=", evidence_receipt_id={"+receipt["receipt_id"]+"}, evidence_work_id={semantic-scholar:synthetic2}")
        report = self.checked()
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["findings"][0]["provider_identity"]["work_id"], "semantic-scholar:synthetic2")
        self.save_bib(extra=", evidence_receipt_id={"+receipt["receipt_id"]+"}, evidence_work_id={semantic-scholar:missing}")
        self.assertEqual(self.checked()["status"], "fail")

    def test_saved_report_is_invalidated_by_changed_original_source(self):
        receipt = self.search()
        report = self.checked()
        normalized = self.project/receipt["normalized_results_path"]
        normalized.write_bytes(normalized.read_bytes()+b" ")
        self.assertTrue(validate_provider_identities(self.bib, report))

    def test_arxiv_identifier_is_exact_and_cannot_hide_a_different_url(self):
        payload = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2401.12345v2</id><title>A Reliable Structural Model</title><published>2024-01-02T00:00:00Z</published><author><name>Ada Lovelace</name></author><author><name>Grace Hopper</name></author></entry></feed>'''
        self.search(provider="arxiv", payload=payload)
        self.save_bib(url="https://arxiv.org/abs/2401.12345v2", extra=", eprint={2401.12345v2}")
        self.assertEqual(self.checked()["status"], "pass")
        self.save_bib(url="https://arxiv.org/abs/2401.99999v2", extra=", eprint={2401.12345v2}")
        self.assertEqual(self.checked()["status"], "fail")
        self.save_bib(url="https://arxiv.org/abs/2401.12345v2", extra=", eprint={2401.12345v1}")
        self.assertEqual(self.checked()["status"], "fail")


if __name__ == "__main__":
    unittest.main()
