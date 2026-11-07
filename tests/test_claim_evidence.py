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
        with self.assertRaisesRegex(ValueError, "DOI differs"):
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
