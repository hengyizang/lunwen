"""Synthetic source-task contracts; executed only by cloud validation."""
import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from scripts import literature_source_tasks as tasks, literature_workbench as wb, paper_reader, systematic_review, literature_evidence, source_scope
from scripts.research_artifacts import read, record, sha, write
from tests.test_literature_workbench import WorkbenchFixture


class SourceTaskTests(WorkbenchFixture):
    def setUp(self):
        super().setUp()
        self.a = self.add_paper("a", "The reported effect applies only to adults under protocol A.", title="Study A")
        self.b = self.add_paper("b", "An earlier study reported a related mechanism with a different population.", title="Study B")
        self.a["source_scope"] = "full_text"
        self.build()
        self.trace = {"schema_version": "1.0", "id": "remembered-effect", "memory_statement": "A remembered intervention effect.",
            "search_leads": [{"query": "intervention effect adults", "provider": "crossref", "status": "planned"}],
            "candidates": [self.candidate(self.a), self.candidate(self.b)]}

    def candidate(self, paper):
        return {"paper_id": paper["id"], "state": "candidate", "reason": "Relevant candidate requiring inspection.",
            "evidence": [self.anchor(paper, (self.project / paper["source"]["path"]).read_text(encoding="utf-8"))],
            "premises": [], "scope": [], "inference_boundary": "Located text is not proof of semantic support or priority."}

    def seed(self):
        works = [literature_evidence.normalized_work("crossref", "a", "Study A", 2020, "10.1000/a", "https://doi.org/10.1000/a", ["Author A"]),
                 literature_evidence.normalized_work("crossref", "b", "Study B", 2019, "10.1000/b", "https://doi.org/10.1000/b", ["Author B"])]
        normalized = self.project / "evidence/literature/normalized/receipt-a.json"
        write(normalized, {"works": works})
        raw = self.project / "evidence/literature/raw/receipt-a.json"
        write(raw, {"synthetic_fixture": True, "works": works})
        ledger = self.project / "evidence/literature-api-ledger.jsonl"
        ledger.write_text(json.dumps({"receipt_id": "receipt-a", "status": "success", "provider": "crossref", "mode": "live_search",
            "query": "intervention effect adults", "normalized_results_path": normalized.relative_to(self.project).as_posix(),
            "normalized_results_sha256": sha(normalized), "raw_response_path": raw.relative_to(self.project).as_posix(),
            "response_sha256": sha(raw), "result_count": len(works)}) + "\n", encoding="utf-8")
        target = self.project / "evidence/systematic/screening.json"
        target.parent.mkdir(parents=True)
        systematic_review.seed(self.project, ["receipt-a"], "quick", "Adult participants; randomized design", "Synthetic owner", target)
        return {"schema_version": "1.0", "id": "screening-a", "screening": {"path": target.relative_to(self.project).as_posix(), "sha256": sha(target)},
            "criteria": [{"id": "adults", "text": "Adult participants"}, {"id": "randomized", "text": "randomized design"}],
            "study_papers": [{"study_id": "doi:10.1000/a", "paper_id": "a"}, {"study_id": "doi:10.1000/b", "paper_id": "b"}],
            "advice": []}

    def item(self, *, stage="title_abstract", suggestion="review", evidence=True):
        return {"study_id": "doi:10.1000/a", "stage": stage, "criterion_id": "adults", "suggestion": suggestion,
            "reason": "The source describes adult participants, but design details still need review.",
            "missing_information": ["Randomization details"], "evidence": self.trace["candidates"][0]["evidence"] if evidence else []}

    def save(self, operation, spec):
        path = "program/" + operation + ".json"
        write(self.project / path, spec)
        return tasks.refresh(self.project, operation, path), path

    def test_trace_distinguishes_memory_original_text_and_unverified_semantics(self):
        self.trace["candidates"][0]["premises"] = [{"text": "Adult population only", "evidence": self.trace["candidates"][0]["evidence"]}]
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no calls")):
            report = tasks.build(self.project, "source_trace", self.trace)
        row = report["candidates"][0]
        self.assertEqual(row["identity"]["state"], "metadata_not_checked")
        self.assertEqual(row["text_state"], "original_passages_located")
        self.assertEqual(row["semantic_state"], "pending_source_review")
        self.assertFalse(report["earliest_original_source_established"])
        self.assertFalse(row["premises"][0]["semantic_support_verified"])

    def test_trace_rejects_fabricated_quotes_or_source_substitution(self):
        self.trace["candidates"][0]["evidence"][0]["quote"] = "An invented universal result."
        with self.assertRaisesRegex(ValueError, "quote"):
            tasks.build(self.project, "source_trace", self.trace)
        self.trace["candidates"][0]["evidence"] = self.trace["candidates"][1]["evidence"]
        with self.assertRaisesRegex(ValueError, "original source"):
            tasks.build(self.project, "source_trace", self.trace)

    def test_trace_does_not_accept_verification_or_priority_flags(self):
        for field in ("verified", "earliest_original_source_established", "human_reviewed"):
            candidate = copy.deepcopy(self.trace)
            candidate["candidates"][0][field] = True
            with self.assertRaisesRegex(ValueError, "unsupported"):
                tasks.build(self.project, "source_trace", candidate)

    def test_trace_metadata_identity_uses_actual_receipt_without_claiming_pdf_identity(self):
        self.seed()
        self.trace["candidates"][0]["identity_evidence"] = {"receipt_id": "receipt-a", "study_id": "doi:10.1000/a"}
        self.trace["search_leads"][0].update(status="executed", receipt_id="receipt-a")
        report = tasks.build(self.project, "source_trace", self.trace)
        identity = report["candidates"][0]["identity"]
        self.assertEqual(identity["state"], "metadata_title_matched")
        self.assertEqual(identity["year"], 2020)
        self.assertFalse(identity["original_pdf_identity_verified"])
        self.trace["candidates"][0]["identity_evidence"]["study_id"] = "doi:10.1000/b"
        with self.assertRaisesRegex(ValueError, "title differs"):
            tasks.build(self.project, "source_trace", self.trace)

    def test_declared_search_is_not_an_execution_receipt(self):
        self.trace["search_leads"][0].update(status="executed", receipt_id="missing")
        with self.assertRaises((ValueError, FileNotFoundError)):
            tasks.build(self.project, "source_trace", self.trace)
        self.seed()
        self.trace["search_leads"][0]["receipt_id"] = "receipt-a"
        self.trace["search_leads"][0]["query"] = "A different search"
        with self.assertRaisesRegex(ValueError, "query/provider"):
            tasks.build(self.project, "source_trace", self.trace)

    def test_imported_metadata_cannot_be_reported_as_an_executed_search(self):
        self.seed()
        ledger = self.project / "evidence/literature-api-ledger.jsonl"
        receipt = json.loads(ledger.read_text(encoding="utf-8").strip())
        receipt["mode"] = "licensed_local_export"
        ledger.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
        self.trace["search_leads"][0].update(status="executed", receipt_id="receipt-a")
        with self.assertRaisesRegex(ValueError, "imported metadata"):
            tasks.build(self.project, "source_trace", self.trace)

    def test_candidate_history_is_preserved_with_exclusion_reason(self):
        _, path = self.save("source_trace", self.trace)
        self.trace["candidates"].pop()
        write(self.project / path, self.trace)
        with self.assertRaisesRegex(ValueError, "retain earlier"):
            tasks.refresh(self.project, "source_trace", path)
        self.trace["candidates"].append({**self.candidate(self.b), "state": "excluded", "reason": "Population differs; retained as an excluded lead."})
        write(self.project / path, self.trace)
        result = tasks.refresh(self.project, "source_trace", path)
        self.assertEqual(read(self.project / result["report"])["candidates"][1]["candidate_state"], "excluded")
        self.assertTrue(list((self.project / result["report"]).parent.glob("history/*.json")))

    def test_changed_source_or_report_invalidates_saved_trace(self):
        result, path = self.save("source_trace", self.trace)
        self.assertTrue(tasks.validate_saved_report(self.project, "source_trace", path)["valid"])
        report = self.project / result["report"]
        report.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside its controlled"):
            tasks.validate_saved_report(self.project, "source_trace", path)

    def test_changed_original_refuses_reuse(self):
        _, path = self.save("source_trace", self.trace)
        (self.project / self.a["source"]["path"]).write_text("Changed original evidence.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            tasks.validate_saved_report(self.project, "source_trace", path)

    def test_screening_advice_covers_all_studies_stages_criteria_without_decisions(self):
        spec = self.seed()
        original = (self.project / spec["screening"]["path"]).read_bytes()
        spec["advice"] = [self.item(suggestion="include")]
        report = tasks.build(self.project, "screening_advice", spec)
        self.assertEqual(len(report["advice"]), 8)
        self.assertEqual(sum(r["suggestion"] == "review" for r in report["advice"]), 7)
        self.assertTrue(all(r["formal_decision_snapshot"] == "pending" for r in report["advice"]))
        self.assertFalse(report["formal_decisions_modified"])
        self.assertEqual((self.project / spec["screening"]["path"]).read_bytes(), original)

    def test_screening_rules_and_criterion_ids_cannot_be_silently_changed(self):
        spec = self.seed()
        spec["criteria"][0]["text"] = "Exclude unfavorable results"
        with self.assertRaisesRegex(ValueError, "frozen screening criteria"):
            tasks.build(self.project, "screening_advice", spec)
        spec = self.existing_screening_request()
        spec["advice"] = [{**self.item(), "criterion_id": "new-rule"}]
        with self.assertRaisesRegex(ValueError, "out-of-scope"):
            tasks.build(self.project, "screening_advice", spec)

    def test_criterion_fragments_or_duplicate_text_cannot_skip_formal_rules(self):
        original = self.seed()
        for criteria in ([{"id": "fragment", "text": "participants"}],
                         [{"id": "one", "text": "Adult participants"}, {"id": "two", "text": "Adult participants"}],
                         [{"id": "one", "text": "Adult participants"}]):
            spec = copy.deepcopy(original)
            spec["criteria"] = criteria
            with self.assertRaisesRegex(ValueError, "criteria"):
                tasks.build(self.project, "screening_advice", spec)

    def test_whole_unstructured_criteria_can_be_one_complete_item(self):
        spec = self.seed()
        spec["criteria"] = [{"id": "all", "text": "Adult participants; randomized design"}]
        report = tasks.build(self.project, "screening_advice", spec)
        self.assertTrue(report["criterion_text_coverage_complete"])
        self.assertEqual(len(report["advice"]), 4)

    def test_criterion_mapping_cannot_drop_comparison_operators(self):
        spec = self.seed()
        target = self.project / spec["screening"]["path"]
        ledger = read(target)
        ledger["criteria"] = "Adult age >= 18; randomized design"
        write(target, ledger)
        spec["screening"]["sha256"] = sha(target)
        spec["criteria"] = [{"id": "age", "text": "Adult age"}, {"id": "threshold", "text": "18"},
                            {"id": "design", "text": "randomized design"}]
        with self.assertRaisesRegex(ValueError, "complete frozen"):
            tasks.build(self.project, "screening_advice", spec)

    def existing_screening_request(self):
        # Mutate neither formal decisions nor criteria: return the same bound
        # existing ledger through its input shape for a second isolated request.
        target = self.project / "evidence/systematic/screening.json"
        return {"schema_version": "1.0", "id": "screening-a", "screening": {"path": "evidence/systematic/screening.json", "sha256": sha(target)},
            "criteria": [{"id": "adults", "text": "Adult participants"}, {"id": "randomized", "text": "randomized design"}],
            "study_papers": [{"study_id": "doi:10.1000/a", "paper_id": "a"}], "advice": []}

    def test_full_text_unavailable_stays_review_and_does_not_become_exclusion(self):
        spec = self.seed()
        self.a["source_scope"] = "metadata_only"
        self.build()
        spec["advice"] = [self.item(stage="full_text", suggestion="exclude")]
        with self.assertRaisesRegex(ValueError, "unavailable full text"):
            tasks.build(self.project, "screening_advice", spec)
        spec["advice"] = [self.item(stage="full_text", suggestion="review", evidence=False)]
        report = tasks.build(self.project, "screening_advice", spec)
        row = next(r for r in report["advice"] if r["study_id"] == "doi:10.1000/a" and r["stage"] == "full_text" and r["criterion_id"] == "adults")
        self.assertTrue(row["missing_information"])
        self.assertEqual(row["suggestion"], "review")

    def test_writable_full_text_label_is_insufficient_without_protected_scope(self):
        spec = self.seed()
        spec["advice"] = [self.item(stage="full_text", suggestion="include")]
        with self.assertRaisesRegex(ValueError, "unavailable full text"):
            tasks.build(self.project, "screening_advice", spec)
        source_scope.record(self.project, self.a["source"]["path"], "full_text", "Synthetic scope reviewer")
        report = tasks.build(self.project, "screening_advice", spec)
        self.assertEqual(next(r for r in report["advice"] if r["study_id"] == "doi:10.1000/a" and r["stage"] == "full_text" and r["criterion_id"] == "adults")["suggestion"], "include")
        self.assertFalse(report["formal_decisions_modified"])

    def test_trace_rejects_changed_raw_receipt_even_when_normalized_metadata_unchanged(self):
        self.seed()
        self.trace["candidates"][0]["identity_evidence"] = {"receipt_id": "receipt-a", "study_id": "doi:10.1000/a"}
        (self.project / "evidence/literature/raw/receipt-a.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale literature receipt"):
            tasks.build(self.project, "source_trace", self.trace)

    def test_history_archives_are_inventoried_and_changed_or_deleted_files_block(self):
        result, request = self.save("source_trace", self.trace)
        self.trace["memory_statement"] += " An updated recollection."
        write(self.project / request, self.trace)
        tasks.refresh(self.project, "source_trace", request)
        directory = (self.project / result["report"]).parent
        manifest = read(directory / "manifest.json")
        self.assertEqual(len(manifest["history"]), 1)
        archive = self.project / manifest["history"][0]["path"]
        original = archive.read_bytes()
        archive.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "history archive changed"):
            tasks.validate_saved_report(self.project, "source_trace", request)
        archive.write_bytes(original)
        archive.unlink()
        with self.assertRaisesRegex(ValueError, "archive was deleted"):
            tasks.validate_saved_report(self.project, "source_trace", request)

    def test_ai_cannot_supply_formal_or_human_decision_fields(self):
        spec = self.seed()
        for field in ("formal_decision", "reviewer", "human_verified"):
            spec["advice"] = [{**self.item(), field: "include"}]
            with self.assertRaisesRegex(ValueError, "unsupported"):
                tasks.build(self.project, "screening_advice", spec)

    def test_missing_original_criterion_evidence_requires_review(self):
        spec = self.seed()
        spec["advice"] = [self.item(suggestion="exclude", evidence=False)]
        with self.assertRaisesRegex(ValueError, "need original criterion evidence"):
            tasks.build(self.project, "screening_advice", spec)

    def test_duplicate_advice_cannot_change_one_criterion_twice(self):
        spec = self.seed()
        spec["advice"] = [self.item(), self.item()]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            tasks.build(self.project, "screening_advice", spec)

    def test_duplicate_publication_leads_preserve_reports_without_merging(self):
        spec = self.seed()
        spec["duplicate_leads"] = [{"study_ids": ["doi:10.1000/a", "doi:10.1000/b"], "reason": "Possible shared study; verify participants and registration."}]
        report = tasks.build(self.project, "screening_advice", spec)
        self.assertFalse(report["duplicate_leads"][0]["same_study_verified"])
        self.assertFalse(report["duplicate_leads"][0]["records_merged"])
        self.assertEqual(len(report["advice"]), 8)

    def test_screening_protocol_change_invalidates_saved_advice(self):
        spec = self.seed()
        protocol = self.project / "evidence/systematic/protocol.json"
        write(protocol, {"status": "registered", "registration_id": "synthetic-protocol"})
        ledger_path = self.project / spec["screening"]["path"]
        ledger = read(ledger_path)
        ledger["protocol"] = {"path": "evidence/systematic/protocol.json", "sha256": sha(protocol), "status": "registered"}
        write(ledger_path, ledger)
        spec["screening"]["sha256"] = sha(ledger_path)
        _, request_path = self.save("screening_advice", spec)
        write(protocol, {"status": "registered", "registration_id": "changed"})
        with self.assertRaisesRegex(ValueError, "bound evidence changed"):
            tasks.validate_saved_report(self.project, "screening_advice", request_path)

    def test_current_screening_hash_and_metadata_receipts_are_required(self):
        spec = self.seed()
        _, path = self.save("screening_advice", spec)
        ledger = self.project / spec["screening"]["path"]
        value = read(ledger)
        value["criteria"] += "; a changed rule"
        write(ledger, value)
        with self.assertRaisesRegex(ValueError, "bound evidence changed"):
            tasks.validate_saved_report(self.project, "screening_advice", path)

    def test_source_notes_cannot_masquerade_as_original_candidate_quotes(self):
        note = self.source("evidence/notes/a.md", "A generated stronger interpretation.")
        self.a["notes"] = [note]
        self.build()
        self.trace["candidates"][0]["evidence"] = [{**note, "start_line": 1, "end_line": 1, "quote": "A generated stronger interpretation."}]
        with self.assertRaisesRegex(ValueError, "original source"):
            tasks.build(self.project, "source_trace", self.trace)

    def test_native_reader_translation_and_wrong_page_are_refused(self):
        original = "A source claim with a necessary condition."
        pdf = self.project / "evidence/sources/native.pdf"
        pdf.write_bytes(b"%PDF-1.4\nSynthetic source-binding fixture only.\n%%EOF\n")
        source = {"path": "evidence/sources/native.pdf", "sha256": sha(pdf)}
        reader = self.source("evidence/readers/native.md", "# Reader\n\n## PDF page 1\n\n### Original extracted text\n\n" + original +
            "\n\n### Chinese reading translation\n\nA generated translation claim.\n")
        mapping = self.project / "evidence/readers/native.source-map.json"
        write(mapping, {"source_sha256": source["sha256"], "reader_sha256": reader["sha256"],
            "source_blocks": [{"pdf_page": 1, "extracted_text_sha256": hashlib.sha256(original.encode()).hexdigest()}]})
        receipt = self.project / "evidence/readers/native.reader.json"
        write(receipt, {"pdf_sha256": source["sha256"], "reader_sha256": reader["sha256"],
            "reader_implementation_sha256": sha(Path(paper_reader.__file__)), "page_count": 1, "selected_pages": [1], "page_images": [],
            "source_map": {"path": mapping.relative_to(self.project).as_posix(), "sha256": sha(mapping)}})
        record(self.project, [self.project / reader["path"], receipt, mapping], "synthetic-fixture")
        self.config["papers"] = [{"id": "native", "title": "Native fixture", "source": source, "reader": reader}]
        self.build()
        anchor = {**reader, "start_line": 7, "end_line": 7, "quote": original, "pdf_page": 1}
        spec = {"schema_version": "1.0", "id": "native", "memory_statement": "Remembered claim", "candidates": [{
            "paper_id": "native", "reason": "Candidate", "inference_boundary": "Not source support proof.", "evidence": [anchor]}]}
        self.assertEqual(tasks.build(self.project, "source_trace", spec)["candidates"][0]["text_state"], "original_passages_located")
        spec["candidates"][0]["evidence"] = [{**reader, "start_line": 11, "end_line": 11, "quote": "A generated translation claim.", "pdf_page": 1}]
        with self.assertRaisesRegex(ValueError, "original text"):
            tasks.build(self.project, "source_trace", spec)
        current_paper = tasks._library(self.project)[0]["native"]
        self.assertTrue(tasks._full_text_available(self.project, current_paper))
        partial = read(receipt)
        partial["page_count"] = 2
        write(receipt, partial)
        record(self.project, [receipt], "synthetic-fixture")
        self.build()
        current_paper = tasks._library(self.project)[0]["native"]
        self.assertFalse(tasks._full_text_available(self.project, current_paper))

    def test_html_escapes_source_text_and_saved_report_recomputes(self):
        self.trace["memory_statement"] = "<script>alert('untrusted')</script> remembered claim"
        result, path = self.save("source_trace", self.trace)
        text = (self.project / result["html"]).read_text(encoding="utf-8")
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertTrue(tasks.validate_saved_report(self.project, "source_trace", path)["valid"])
