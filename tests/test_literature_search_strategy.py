"""Synthetic search-plan contracts; no external requests or model calls."""
import copy
import json
from unittest.mock import patch

from scripts import literature_evidence, literature_search_strategy as strategy
from scripts.research_artifacts import read, sha, write
from tests.test_literature_workbench import WorkbenchFixture


class SearchStrategyTests(WorkbenchFixture):
    def setUp(self):
        super().setUp()
        self.spec = {"schema_version": "1.0", "version": 1, "change_reason": "Initial explicit search protocol",
            "doctoral_question": "Which protocols distinguish generalization mechanisms?", "question": "Does tuning exclude test devices?",
            "concepts": [
                {"id": "generalization", "zh": "跨设备泛化", "en": "cross device generalization", "aliases": ["unseen hardware transfer"],
                 "disciplinary_sense": "Evaluation on held-out devices, not tuning transfer"},
                {"id": "tuning", "zh": "超参数调整", "en": "hyperparameter tuning", "aliases": ["model selection"],
                 "disciplinary_sense": "Choice of hyperparameters before final testing"},
                {"id": "heldout", "zh": "测试设备", "en": "held out devices", "aliases": [],
                 "disciplinary_sense": "Units absent from training and tuning"}],
            "tiers": [
                {"level": "broad", "concept_ids": ["generalization"], "reason": "Locate the problem across methods"},
                {"level": "medium", "concept_ids": ["generalization", "tuning"], "reason": "Inspect the tuning condition"},
                {"level": "strict", "concept_ids": ["generalization", "tuning", "heldout"], "reason": "Locate the exact held-out protocol"}],
            "platforms": ["arxiv", "semantic-scholar", "wos", "cnki"], "exclusions": [], "trials": []}

    def query(self, identifier):
        return next(q for q in strategy.build(self.project, self.spec)["queries"] if q["id"] == identifier)

    def trial(self, *, total=200, metadata_variant=False):
        query = self.query("broad-semantic-scholar-1")["query"]
        work = {"paperId": "fixture-paper", "title": "A synthetic protocol paper", "year": 2025,
                "authors": [{"name": "Synthetic Author"}], "externalIds": {"DOI": "10.1234/fixture"},
                "url": "https://example.org/paper", "abstract": "A software fixture, not real research."}
        payload = {"data": [work, copy.deepcopy(work)]}
        if metadata_variant:
            payload["data"][1].update(paperId="fixture-second-report", externalIds={})
        if total is not None:
            payload["total"] = total
        def fetch(url, **_kwargs):
            return json.dumps(payload).encode(), url, 200, "application/json"
        receipt = literature_evidence.execute_search(self.project, "semantic-scholar", query,
            query_family="direct", date_range="2024-2026", filters={}, limit=5, fetcher=fetch)
        self.spec["trials"] = [{"id": "trial1", "query_id": "broad-semantic-scholar-1",
            "receipt_id": receipt["receipt_id"], "reason": "Inspect actual returned topic coverage before changing a query"}]
        return receipt

    def test_bilingual_concepts_render_bounded_boolean_and_native_plain_text(self):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid planning")):
            result = strategy.build(self.project, self.spec)
        arxiv = next(q for q in result["queries"] if q["id"] == "strict-arxiv-1")
        self.assertIn('all:"跨设备泛化"', arxiv["query"])
        self.assertIn(" AND ", arxiv["query"])
        self.assertEqual(arxiv["ast"]["op"], "and")
        self.assertEqual(arxiv["syntax_status"], "native_bounded_boolean")
        self.assertTrue(any(q["platform"] == "semantic-scholar" and "boolean_not_claimed" in q["syntax_status"] for q in result["queries"]))
        self.assertEqual(result["paid_calls"], 0)
        self.assertFalse(result["active_discovery_plan_modified"])

    def test_manual_platform_queries_cannot_claim_native_execution_or_verified_syntax(self):
        result = strategy.build(self.project, self.spec)
        for item in result["queries"]:
            if item["platform"] in {"wos", "cnki"}:
                self.assertTrue(item["manual_required"])
                self.assertIsNone(item["plan_entry"])
                self.assertEqual(item["syntax_status"], "syntax_unverified_manual_required")
                self.assertFalse(item["executed"])

    def test_non_nested_tiers_and_unknown_concepts_are_rejected(self):
        self.spec["tiers"][1]["concept_ids"] = ["tuning"]
        with self.assertRaisesRegex(ValueError, "nested"):
            strategy.build(self.project, self.spec)
        self.spec["tiers"][1]["concept_ids"] = ["unknown"]
        with self.assertRaises(ValueError):
            strategy.build(self.project, self.spec)

    def test_operator_injection_is_rejected_instead_of_executed(self):
        self.spec["concepts"][0]["aliases"] = ['x" OR all:*']
        with self.assertRaisesRegex(ValueError, "literal phrases"):
            strategy.build(self.project, self.spec)

    def test_exclusions_are_proposals_and_cannot_remove_counterevidence(self):
        self.spec["exclusions"] = [{"term": "editorial", "reason": "Potential document-type restriction, pending protocol review", "scope_category": "document_type"}]
        result = strategy.build(self.project, self.spec)
        self.assertFalse(result["proposed_exclusions"][0]["applied"])
        self.assertTrue(all("editorial" not in q["query"] for q in result["queries"]))
        self.spec["exclusions"][0]["scope_category"] = "negative_results"
        with self.assertRaisesRegex(ValueError, "counterevidence"):
            strategy.build(self.project, self.spec)

    def test_doctoral_scope_cannot_silently_change(self):
        write(self.project / "program/core-thesis.json", {"doctoral_question": "An approved different question"})
        with self.assertRaisesRegex(ValueError, "scope differs"):
            strategy.build(self.project, self.spec)

    def test_exact_concept_source_anchor_is_checked_and_changed_source_blocks_reuse(self):
        paper = self.add_paper("a", "Held-out devices are not included in tuning.")
        self.build()
        self.spec["concepts"][2]["evidence"] = [{"paper_id": "a", **self.anchor(paper, "Held-out devices are not included in tuning.")}]
        result = strategy.build(self.project, self.spec)
        self.assertFalse(result["concepts"][2]["terminology_semantics_verified"])
        (self.project / paper["source"]["path"]).write_text("Changed original", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            strategy.build(self.project, self.spec)

    def test_trial_counts_use_actual_total_returned_and_deduplicated_as_distinct_numbers(self):
        self.trial()
        result = strategy.build(self.project, self.spec)
        counts = result["trials"][0]["counts"]
        self.assertEqual(counts, {"platform_total": 200, "raw_response_returned": 2,
                                 "retrieved": 1, "deduplicated": 1, "screened_report_records": None})
        executed = [q for q in result["queries"] if q["executed"]]
        self.assertEqual([q["id"] for q in executed], ["broad-semantic-scholar-1"])
        self.assertFalse(result["trials"][0]["scientific_coverage_verified"])

    def test_unknown_platform_total_is_not_returned_limit_or_zero(self):
        self.trial(total=None)
        result = strategy.build(self.project, self.spec)
        self.assertIsNone(result["trials"][0]["counts"]["platform_total"])
        self.assertEqual(result["trials"][0]["counts"]["raw_response_returned"], 2)
        self.assertEqual(result["trials"][0]["counts"]["retrieved"], 1)

    def test_trial_cannot_reuse_old_query_or_another_platform(self):
        self.trial()
        self.spec["concepts"][0]["en"] = "a changed query"
        with self.assertRaisesRegex(ValueError, "exact current"):
            strategy.build(self.project, self.spec)

    def test_trial_source_tampering_is_rejected(self):
        receipt = self.trial()
        (self.project / receipt["raw_response_path"]).write_bytes(b"changed raw receipt")
        with self.assertRaisesRegex(ValueError, "stale literature receipt"):
            strategy.build(self.project, self.spec)

    def test_plan_bound_trial_cannot_certify_a_changed_active_discovery_plan(self):
        receipt = self.trial()
        plan = self.project / "program/literature-plan.json"
        write(plan, {"schema_version": "1.0", "doctoral_question": self.spec["doctoral_question"]})
        ledger = self.project / "evidence/literature-api-ledger.jsonl"
        rows = literature_evidence.read_jsonl(ledger)
        rows[0]["request_context"] = {"operation": "literature_intelligence", "plan_sha256": sha(plan)}
        literature_evidence.replace_jsonl(ledger, rows)
        self.assertEqual(strategy.build(self.project, self.spec)["trials"][0]["discovery_plan"]["plan_sha256"], sha(plan))
        write(plan, {"schema_version": "1.0", "doctoral_question": self.spec["doctoral_question"], "topic_keywords": ["changed"]})
        with self.assertRaisesRegex(ValueError, "discovery plan changed"):
            strategy.build(self.project, self.spec)

    def test_trial_platform_total_cannot_be_less_than_obtained_results(self):
        self.trial(total=0)
        with self.assertRaisesRegex(ValueError, "smaller"):
            strategy.build(self.project, self.spec)

    def test_licensed_wos_import_does_not_fabricate_platform_search_date(self):
        query = self.query("broad-wos-1")["query"]
        path = "evidence/literature/exports/wos.csv"
        self.source(path, 'Title,Year,DOI,Authors\nSynthetic imported study,2025,10.1234/imported,Synthetic Author\n')
        receipt = literature_evidence.execute_import(self.project, "wos", path, query=query,
            query_family="direct", date_range="2024-2026", filters="none", actor="Synthetic licensed exporter")
        self.spec["trials"] = [{"id": "imported", "query_id": "broad-wos-1", "receipt_id": receipt["receipt_id"],
            "reason": "Inspect a licensed export; its query and original search time need manual checking"}]
        report = strategy.build(self.project, self.spec)
        trial = report["trials"][0]
        self.assertIsNone(trial["searched_at"])
        self.assertEqual(trial["imported_at"], receipt["completed_at"])
        self.assertEqual(trial["source_mode"], "licensed_local_export")
        self.assertIn("search_time_unknown", trial["execution_basis"])
        row = next(q for q in report["queries"] if q["id"] == "broad-wos-1")
        self.assertFalse(row["executed"])
        self.assertEqual(row["imported_receipt_ids"], [receipt["receipt_id"]])

    def test_actual_formal_screening_count_is_read_without_modifying_decisions(self):
        receipt = self.trial()
        from scripts import systematic_review
        target = self.project / "evidence/systematic/screening.json"
        systematic_review.seed(self.project, [receipt["receipt_id"]], "quick", "Declared fixture criterion", "Fixture human", target)
        value = read(target)
        value["studies"][0]["title_abstract"].update(decision="exclude", reviewer="Fixture human", reason="Explicit fixture reason")
        write(target, value)
        before = target.read_bytes()
        self.spec["trials"][0]["screening"] = {"path": "evidence/systematic/screening.json", "sha256": sha(target)}
        report = strategy.build(self.project, self.spec)
        self.assertEqual(report["trials"][0]["counts"]["screened_report_records"], 1)
        self.assertEqual(before, target.read_bytes())

    def test_screened_report_records_can_exceed_intelligence_work_clusters(self):
        receipt = self.trial(metadata_variant=True)
        from scripts import systematic_review
        target = self.project / "evidence/systematic/screening.json"
        systematic_review.seed(self.project, [receipt["receipt_id"]], "quick", "Declared fixture criterion", "Fixture human", target)
        value = read(target)
        self.assertEqual(len(value["studies"]), 2)
        for item in value["studies"]:
            item["title_abstract"].update(decision="exclude", reviewer="Fixture human", reason="Explicit fixture reason")
        write(target, value)
        self.spec["trials"][0]["screening"] = {"path": "evidence/systematic/screening.json", "sha256": sha(target)}
        counts = strategy.build(self.project, self.spec)["trials"][0]["counts"]
        self.assertEqual(counts["retrieved"], 2)
        self.assertEqual(counts["deduplicated"], 1)
        self.assertEqual(counts["screened_report_records"], 2)

    def test_version_history_retains_initial_and_changed_strategy_without_editing_plan(self):
        write(self.project / strategy.REQUEST, self.spec)
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no model")):
            first = strategy.refresh(self.project)
            strategy.refresh(self.project)
        self.assertTrue(strategy.validate_saved_report(self.project)["valid"])
        self.spec.update(version=2, change_reason="Add adjacent terminology while retaining the same question")
        self.spec["concepts"][0]["aliases"].append("device transfer evaluation")
        write(self.project / strategy.REQUEST, self.spec)
        second = strategy.refresh(self.project)
        history = read(self.project / second["history"])
        self.assertEqual(len(history["versions"]), 2)
        self.assertTrue((self.project / strategy.OUTPUT / "versions/v0001.json").is_file())
        self.assertEqual(first["version"], 1)
        self.assertFalse((self.project / "program/literature-plan.json").exists())

    def test_same_version_cannot_rewrite_queries_or_old_history(self):
        write(self.project / strategy.REQUEST, self.spec)
        strategy.refresh(self.project)
        self.spec["question"] = "A different subquestion"
        write(self.project / strategy.REQUEST, self.spec)
        with self.assertRaisesRegex(ValueError, "immutable"):
            strategy.refresh(self.project)

    def test_history_tampering_and_version_skips_are_rejected(self):
        write(self.project / strategy.REQUEST, self.spec)
        result = strategy.refresh(self.project)
        history = read(self.project / result["history"])
        history["versions"] = []
        write(self.project / result["history"], history)
        with self.assertRaisesRegex(ValueError, "outside"):
            strategy.refresh(self.project)

    def test_latest_report_and_input_changes_invalidate_validation(self):
        write(self.project / strategy.REQUEST, self.spec)
        result = strategy.refresh(self.project)
        latest = self.project / result["report"]
        latest.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside"):
            strategy.validate_saved_report(self.project)
        self.spec.update(version=2, change_reason="Attempt a new query version after outside alteration")
        write(self.project / strategy.REQUEST, self.spec)
        with self.assertRaisesRegex(ValueError, "outside"):
            strategy.refresh(self.project)
        self.assertFalse((self.project / strategy.OUTPUT / "versions/v0002.json").exists())

    def test_html_escapes_untrusted_questions_without_external_scripts(self):
        self.spec["question"] = '<script>alert("fixture")</script>'
        write(self.project / strategy.REQUEST, self.spec)
        result = strategy.refresh(self.project)
        view = (self.project / result["html"]).read_text(encoding="utf-8")
        self.assertNotIn("<script>", view)
        self.assertIn("&lt;script&gt;", view)
