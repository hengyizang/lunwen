"""Synthetic contracts exercise source boundaries, never scientific judgments."""
import copy
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import claim_evidence as claims, citation_audit, literature_source_tasks as tasks
from scripts import output_provenance as provenance, literature_workbench as wb
from scripts import review_receipts
from scripts.research_artifacts import read, write, record, sha
from tests import test_literature_controls as control_fixtures


class ClaimEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = control_fixtures.LiteratureControlTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.project = self.fixture.project
        pdf, self.reader, _, _, manifest = self.fixture.authorized_pdf()
        grant = read(manifest)
        grant["license"].update(url="https://creativecommons.org/licenses/by/4.0/", research_use_allowed=True)
        write(manifest, grant)
        authority = self.project / "state/data-authorizations.json"
        value = read(authority); value["manifests"][manifest.relative_to(self.project).as_posix()]["sha256"] = sha(manifest)
        write(authority, value)
        self.fixture.paper.update(source_scope="full_text", url="https://doi.org/10.1000/fixture")
        self.fixture.save_config()
        primary = self.fixture.paper["source"]
        acquisition = self.project / "evidence/literature/assets/original.json"
        write(acquisition, {"pdfs": [primary]})
        record(self.project, [acquisition], "scripts/literature_assets.py")
        metadata = self.project / "literature/metadata/W1.json"
        write(metadata, {"acquisition_receipt": {"path": acquisition.relative_to(self.project).as_posix(), "sha256": sha(acquisition)}})
        record(self.project, [metadata, self.project / wb.CONFIG], "scripts/literature_registration.py")
        wb.build(self.project)
        self.paper = self.project / "papers/P01/manuscript"
        write(self.paper / "unused.json", {})
        (self.paper / "references.bib").write_text('@article{known,doi={10.1000/fixture},title={Controlled source}}', encoding="utf-8")
        self.spec = {"schema_version": "1.0", "id": "source-check", "paper_id": "P01", "claims": []}
        source_text = "The original PDF reports a controlled method."
        line = self.reader.read_text().splitlines().index(source_text) + 1
        self.anchor = {"path": self.reader.relative_to(self.project).as_posix(), "sha256": sha(self.reader),
            "start_line": line, "end_line": line, "pdf_page": 1, "quote": source_text}
        self.population(1)

    def population(self, count):
        self.spec["claims"] = [{"claim_id": "C" + str(i), "claim": f"Recorded mechanism statement {i}.",
            "citation_key": "known", "library_id": "W1", "evidence": [self.anchor]} for i in range(count)]
        (self.paper / "main.tex").write_text("\n".join(r["claim"] + r"\cite{known}" for r in self.spec["claims"]), encoding="utf-8")

    def response(self, outcome, *, role="domain"):
        return {"receipt": {"role": role, "response": {"path": "reviews/actual-fixture.json", "sha256": "a" * 64},
                "identity": {"family": "anthropic", "requested_model": "fixture", "reported_model": "fixture"}},
            "response": {"claim_evidence": [{"claim_id": "C0", "outcome": outcome,
                "rationale": "Synthetic located evidence interpretation, not an actual scientific result.",
                "evidence": [self.anchor], "missing_evidence": ["A matched population comparison remains unavailable."] if outcome == "insufficient" else []}]}}

    def test_lawful_full_text_prepares_but_never_invents_a_judgment(self):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid call")):
            packet = claims.prepare(self.project, self.spec)
            report = claims.assess(self.project, packet, [])
            self.assertEqual(claims.build(self.project, self.spec), report)
            write(self.project / "program/claim-evidence.json", self.spec)
            tasks.refresh(self.project, "claim_evidence", "program/claim-evidence.json")
            self.assertTrue(tasks.validate_saved_report(self.project, "claim_evidence", "program/claim-evidence.json")["valid"])
        self.assertTrue(packet["claims"][0]["full_text_ready"])
        self.assertEqual(report["claims"][0]["outcome"], "insufficient")
        self.assertIsNone(report["spot_check"]["agreement"])
        self.assertFalse(report["semantic_support_verified"])

    def test_selected_panel_task_is_pure_and_binds_request_originals_and_manuscript(self):
        self.spec["sample_labels"] = "evidence/annotations/later-human-check.json"
        path = "program/claim-evidence.json"; write(self.project / path, self.spec)
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid call")):
            prepared = tasks.prepare_panel_task(self.project, "claim_evidence", path)
        paths = {r["path"] for r in prepared["sources"]}
        self.assertIn(path, paths)
        self.assertIn(self.anchor["path"], paths)
        self.assertIn("papers/P01/manuscript/main.tex", paths)
        self.assertIn("state/data-authorizations.json", paths)
        self.assertNotIn("judgments", prepared["packet"]["claims"][0])
        labels = self.project / self.spec["sample_labels"]
        write(labels, {"claim_fingerprint": prepared["packet"]["claim_fingerprint"], "labels": []})
        # Later human annotations do not force paid reviewers to reread unchanged science.
        self.assertEqual(tasks.prepare_panel_task(self.project, "claim_evidence", path), prepared)

    def test_support_contradiction_and_insufficient_are_retained_without_votes(self):
        packet = claims.prepare(self.project, self.spec)
        for outcome in claims.OUTCOMES:
            report = claims.assess(self.project, packet, [self.response(outcome)])
            self.assertEqual(report["claims"][0]["outcome"], outcome)
            self.assertFalse(report["scientific_completion_verified"])
        report = claims.assess(self.project, packet, [self.response("supports"), self.response("contradicts", role="statistics")])
        self.assertTrue(report["claims"][0]["disagreement"])
        self.assertEqual(report["claims"][0]["outcome"], "insufficient")
        self.assertEqual(len(report["claims"][0]["judgments"]), 2)

    def test_selected_integrity_checks_preserve_preparation_and_block_actual_contradiction(self):
        request = "program/claim-evidence.json"
        write(self.project / request, self.spec)
        write(self.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "claim_evidence",
            "request_file": request, "paper_id": "P01", "stages": ["writing-and-review"]}]})
        self.assertEqual(tasks.integrity_errors(self.project, "P01"), [])
        with patch.object(tasks, "judgment_responses", return_value=[self.response("supports"), self.response("contradicts", role="statistics")]):
            self.assertTrue(any("contradiction" in issue for issue in tasks.integrity_errors(self.project, "P01")))
            self.assertEqual(tasks.integrity_errors(self.project, "P02"), [])
        with patch.object(tasks, "judgment_responses", side_effect=ValueError("protected source is stale")):
            self.assertIn("stale", tasks.integrity_errors(self.project, "P01")[0])

    def test_final_submission_needs_current_full_text_judgments_for_every_cited_key(self):
        self.assertEqual(tasks.integrity_errors(self.project, "P01"), [])
        self.assertTrue(any("covering cited keys: known" in issue
            for issue in tasks.integrity_errors(self.project, "P01", require_support=True)))
        request = "program/claim-evidence.json"
        write(self.project / request, self.spec)
        write(self.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "claim_evidence",
            "request_file": request, "paper_id": "P01", "stages": ["writing-and-review"]}]})
        self.assertTrue(any("unverified or insufficient: C0" in issue
            for issue in tasks.integrity_errors(self.project, "P01", require_support=True)))
        for outcome in claims.OUTCOMES:
            with self.subTest(outcome=outcome), patch.object(tasks, "judgment_responses", return_value=[self.response(outcome)]):
                errors = tasks.integrity_errors(self.project, "P01", require_support=True)
                self.assertEqual(not errors, outcome == "supports", errors)
        with (self.paper / "references.bib").open("a", encoding="utf-8") as target:
            target.write('\n@article{unverified,doi={10.1000/other}}')
        with (self.paper / "main.tex").open("a", encoding="utf-8") as target:
            target.write(r"An additional source claim.\cite{unverified}")
        with patch.object(tasks, "judgment_responses", return_value=[self.response("supports")]):
            self.assertTrue(any("covering cited keys: unverified" in issue
                for issue in tasks.integrity_errors(self.project, "P01", require_support=True)))

    def test_claim_task_reuses_domain_panel_by_default_without_exposing_other_views(self):
        request = "program/claim-evidence.json"
        write(self.project / request, self.spec)
        write(self.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "claim_evidence",
            "request_file": request, "paper_id": "P01", "stages": ["writing-and-review"]}]})
        with patch("scripts.model_runtime.call", side_effect=AssertionError("reuse the existing panel")):
            domain = tasks.selected_context(self.project, "writing-and-review", "P01", seat="domain")
            editorial = tasks.selected_context(self.project, "writing-and-review", "P01", seat="editorial")
        self.assertEqual(len(domain["tasks"]), 1)
        self.assertEqual(domain["tasks"][0]["operation"], "claim_evidence")
        self.assertEqual(editorial["tasks"], [])

    def test_every_distinct_use_of_the_same_reference_needs_its_own_source_judgment(self):
        request = "program/claim-evidence.json"
        write(self.project / request, self.spec)
        write(self.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "claim_evidence",
            "request_file": request, "paper_id": "P01", "stages": ["writing-and-review"]}]})
        with (self.paper / "main.tex").open("a", encoding="utf-8") as target:
            target.write(r" A different independent assertion.\cite{known}")
        packet = claims.prepare(self.project, self.spec)
        self.assertEqual(len(packet["citation_usages"]), 2)
        self.assertEqual(len(packet["uncovered_usages"]), 1)
        with patch.object(tasks, "judgment_responses", return_value=[self.response("supports")]):
            self.assertTrue(any("uncovered citation use: known" in issue
                for issue in tasks.integrity_errors(self.project, "P01", require_support=True)))
        self.spec["claims"].append({**self.spec["claims"][0], "claim_id": "C1", "claim": "A different independent assertion."})
        write(self.project / request, self.spec)
        response = self.response("supports")
        response["response"]["claim_evidence"].append({**response["response"]["claim_evidence"][0], "claim_id": "C1"})
        with patch.object(tasks, "judgment_responses", return_value=[response]):
            self.assertEqual(tasks.integrity_errors(self.project, "P01", require_support=True), [])

    def test_citation_elsewhere_cannot_support_an_unrelated_uncited_statement(self):
        statement = self.spec["claims"][0]["claim"]
        (self.paper / "main.tex").write_text(statement + "\n\n" + r"Another assertion.\cite{known}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "same complete current manuscript citation scope"):
            claims.prepare(self.project, self.spec)

    def test_partial_clause_cannot_stand_in_for_the_complete_cited_assertion(self):
        (self.paper / "main.tex").write_text(r"Recorded mechanism statement 0 and an unsupported second effect.\cite{known}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "same complete current manuscript citation scope"):
            claims.prepare(self.project, self.spec)

    def test_unsupported_citation_syntax_cannot_be_mistaken_for_no_citations(self):
        (self.paper / "main.tex").write_text(r"The source claim.\autocites{known}", encoding="utf-8")
        with self.assertRaisesRegex(citation_audit.CitationAuditError, "explicit literal citation-key"):
            claims.prepare(self.project, self.spec)

    def test_tex_includes_and_prefix_citations_keep_exact_source_locations(self):
        (self.paper / "main.tex").write_text(r"\begin{document}\input{results}\end{document}", encoding="utf-8")
        (self.paper / "results.tex").write_text(r"\citet{known} Recorded mechanism statement 0." + "\n"
            + r"% A fake citation.\cite{comment}" + "\n" + r"\begin{verbatim}\cite{code}\end{verbatim}", encoding="utf-8")
        packet = claims.prepare(self.project, self.spec)
        self.assertEqual(len(packet["citation_usages"]), 1)
        self.assertEqual(packet["uncovered_usages"], [])
        self.assertEqual(packet["citation_usages"][0]["source"]["path"], "papers/P01/manuscript/results.tex")
        self.assertEqual(citation_audit.tex_citation_keys(self.paper / "main.tex"), {"known"})

    def test_word_split_fields_keep_repeated_reference_uses_distinct(self):
        import zipfile
        (self.paper / "main.tex").unlink()
        def paragraph(statement):
            return ('<w:p><w:r><w:t>' + statement + '</w:t></w:r>'
                '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                '<w:r><w:instrText>CITA</w:instrText></w:r><w:r><w:instrText>TION known</w:instrText></w:r>'
                '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>[1]</w:t></w:r>'
                '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + paragraph(self.spec["claims"][0]["claim"]) + paragraph("Another independent assertion.") + '</w:body></w:document>')
        with zipfile.ZipFile(self.paper / "main.docx", "w") as archive:
            archive.writestr("word/document.xml", xml)
        packet = claims.prepare(self.project, self.spec)
        self.assertEqual(len(packet["uncovered_usages"]), 1)
        self.assertEqual([row["source"]["paragraph"] for row in packet["citation_usages"]], [1, 2])
        self.assertEqual(citation_audit.docx_citation_keys(self.paper / "main.docx"), ({"known"}, []))

    def test_incomplete_scope_cannot_manufacture_a_passing_human_agreement_score(self):
        with (self.paper / "main.tex").open("a", encoding="utf-8") as target:
            target.write(r" A separate unchecked assertion.\cite{known}")
        packet = claims.prepare(self.project, self.spec)
        labels = self.project / "evidence/annotations/incomplete-scope.json"
        write(labels, {"claim_fingerprint": packet["claim_fingerprint"], "labels": [
            {"claim_id": "C0", "outcome": "supports", "rationale": "Synthetic label for the single declared claim only."}]})
        provenance.attest_human_files(self.project, [labels], actor="Fixture owner", note="Synthetic software fixture, not a real check")
        report = claims.assess(self.project, packet, [self.response("supports")],
            {"path": labels.relative_to(self.project).as_posix(), "sha256": sha(labels)})
        self.assertIsNone(report["spot_check"]["agreement"])
        self.assertIsNone(report["spot_check"]["target_met"])
        self.assertFalse(report["spot_check"]["coverage_complete"])

    def test_original_https_source_without_doi_uses_the_same_rights_and_support_checks(self):
        url = "https://primary.example.org/open-book"
        self.fixture.paper["url"] = url
        self.fixture.save_config()
        record(self.project, [self.project / wb.CONFIG], "scripts/literature_registration.py")
        wb.build(self.project)
        (self.paper / "references.bib").write_text('@book{known,url={' + url + '}}', encoding="utf-8")
        packet = claims.prepare(self.project, self.spec)
        self.assertEqual(packet["claims"][0]["doi"], "")
        self.assertEqual(packet["claims"][0]["source_identity_url"], url)
        self.assertTrue(packet["claims"][0]["full_text_ready"])
        self.assertEqual(claims.assess(self.project, packet, [self.response("supports")])["claims"][0]["outcome"], "supports")
        (self.paper / "references.bib").write_text('@book{known,url={https://other.example.org/book}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source DOI/URL differs"):
            claims.prepare(self.project, self.spec)
        (self.paper / "references.bib").write_text('@book{known,title={An unidentified source}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "original HTTPS source URL"):
            claims.prepare(self.project, self.spec)

    def test_later_human_sample_does_not_leak_into_or_invalidate_protected_model_judgment(self):
        self.spec["sample_labels"] = "evidence/annotations/human-labels.json"
        write(self.project / "state/run.json", {"stage": "writing-and-review", "gate": "G5", "active_paper": "P01"})
        write(self.project / "program/claim-evidence.json", self.spec)
        write(self.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "claim_evidence",
            "request_file": "program/claim-evidence.json", "paper_id": "P01", "stages": ["writing-and-review"]}]})
        audit_path = self.project / "reviews/independent/source-observation.json"
        audit = {"verdict": "pass-with-conditions", **{k: [] for k in review_receipts.FIELDS - {"verdict"}},
            **self.response("supports")["response"]}
        write(audit_path, audit)
        identity = {"provider": "synthetic-critic", "family": "anthropic", "requested_model": "fixture",
            "reported_model": "fixture", "completion_status": "completed", "cache_hit": False}
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            review_receipts.seal_phase(self.project, stage="writing-and-review", run_id="sample-cycle", phase="observation",
                audit_path=audit_path, prompt="Synthetic source packet without answer labels", identity=identity,
                writer_family="openai", materials=review_receipts.material_snapshot(self.project, "writing-and-review", "P01"))
        before = claims.build(self.project, self.spec)
        self.assertIsNone(before["spot_check"]["agreement"])
        labels = self.project / self.spec["sample_labels"]
        write(labels, {"claim_fingerprint": before["claim_fingerprint"], "labels": [
            {"claim_id": "C0", "outcome": "supports", "rationale": "Synthetic independent spot check."}]})
        provenance.record_model_writes(self.project, [labels], family="other", provider="human-attestation",
            model="human", role="spot-check", run_id="synthetic-human-label")
        after = claims.build(self.project, self.spec)
        self.assertEqual(after["spot_check"]["agreement"], 1)
        self.assertFalse(after["spot_check"]["scientific_validity_verified"])
        self.assertEqual(after["claims"], before["claims"])

    def test_unknown_rights_remain_insufficient_and_cannot_support_a_claim(self):
        authority = self.project / "state/data-authorizations.json"
        write(authority, {"manifests": {}})
        # Rebuild detects rights changes instead of treating a writable full-text label as authority.
        with self.assertRaises((ValueError, RuntimeError)):
            claims.prepare(self.project, self.spec)

    def test_changed_registered_acquisition_receipt_is_an_error_not_missing_evidence(self):
        receipt = self.project / "evidence/literature/assets/original.json"
        receipt.write_bytes(receipt.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "receipt is stale"):
            claims.prepare(self.project, self.spec)

    def test_unavailable_original_full_text_is_a_valid_insufficient_result(self):
        self.spec["claims"][0].update(library_id="not-acquired", evidence=[])
        packet = claims.prepare(self.project, self.spec)
        self.assertFalse(packet["claims"][0]["full_text_ready"])
        self.assertEqual(packet["claims"][0]["outcome"], "insufficient")
        self.assertTrue(packet["claims"][0]["missing_evidence"])
        response = self.response("insufficient"); response["response"]["claim_evidence"][0]["evidence"] = []
        self.assertEqual(claims.assess(self.project, packet, [response])["claims"][0]["outcome"], "insufficient")

    def test_forged_quote_wrong_doi_or_renamed_claim_cannot_be_admitted(self):
        bad = copy.deepcopy(self.spec)
        bad["claims"][0]["evidence"][0]["quote"] = "Invented source statement."
        with self.assertRaisesRegex(ValueError, "quote"):
            claims.prepare(self.project, bad)
        bad = copy.deepcopy(self.spec)
        bad["claims"].append({**bad["claims"][0], "claim_id": "renamed"})
        with self.assertRaisesRegex(ValueError, "duplicate claims"):
            claims.prepare(self.project, bad)
        (self.paper / "references.bib").write_text('@article{known,doi={10.1000/other}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "DOI/URL differs"):
            claims.prepare(self.project, self.spec)

    def test_fifteen_percent_sample_is_reproducible_and_needs_actual_labels(self):
        self.population(20)
        packet = claims.prepare(self.project, self.spec)
        self.assertEqual(len(packet["sample_claim_ids"]), 3)
        self.assertEqual(packet["sample_claim_ids"], claims.prepare(self.project, self.spec)["sample_claim_ids"])
        report = claims.assess(self.project, packet, [])
        self.assertIsNone(report["spot_check"]["target_met"])
        labels_path = self.project / "evidence/annotations/spot-check.json"
        write(labels_path, {"claim_fingerprint": packet["claim_fingerprint"], "labels": [
            {"claim_id": key, "outcome": "insufficient", "rationale": "Synthetic human label fixture."} for key in packet["sample_claim_ids"]]})
        provenance.attest_human_files(self.project, [labels_path], actor="Fixture owner", note="Synthetic sampling test, not a real scientific check")
        binding = {"path": labels_path.relative_to(self.project).as_posix(), "sha256": sha(labels_path)}
        # Human labels without model judgments do not manufacture agreement.
        self.assertIsNone(claims.assess(self.project, packet, [], binding)["spot_check"]["agreement"])
        changed = read(labels_path); changed["labels"][0]["outcome"] = "supports"; write(labels_path, changed)
        binding["sha256"] = sha(labels_path)
        with self.assertRaisesRegex(ValueError, "human-review provenance"):
            claims.assess(self.project, packet, [], binding)

    def extraction(self, name, doi):
        source = {"path": "papers/P01/manuscript/references.bib", "sha256": sha(self.paper / "references.bib"), "locator": "whole bibliography"}
        target = self.project / f"evidence/extractions/{name}.json"
        write(target, {"source": source, "extractor": name, "records": [{"citation_key": "known", "doi": doi,
            "title": "Controlled source", "year": 2025, "authors": ["Fixture Author"]}]})
        record(self.project, [target], "fixture-independent-extractor")
        return source, {"path": target.relative_to(self.project).as_posix(), "sha256": sha(target), "locator": "whole extraction"}

    def test_dual_extraction_diff_runs_in_existing_immutable_source_task(self):
        source, first = self.extraction("one", "10.1000/fixture")
        _, second = self.extraction("two", "10.1000/wrong")
        request = {"schema_version": "1.0", "id": "dual", "source": source, "extractions": [first, second]}
        path = "program/crosscheck.json"; write(self.project / path, request)
        result = tasks.refresh(self.project, "citation_crosscheck", path)
        report = read(self.project / result["report"])
        self.assertEqual(report["differences"][0]["field"], "doi")
        self.assertFalse(report["blindness_verified"])
        self.assertTrue(tasks.validate_saved_report(self.project, "citation_crosscheck", path)["valid"])
        independent = tasks.model_context(self.project, "citation_crosscheck", path, "critic")
        self.assertNotIn("differences", independent)
        self.assertNotIn("extractions", independent)
        self.assertEqual(independent["source"], source)
        (self.project / second["path"]).write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            tasks.validate_saved_report(self.project, "citation_crosscheck", path)


if __name__ == "__main__":
    unittest.main()
