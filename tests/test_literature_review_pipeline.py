"""Synthetic software acceptance; no scientific paper or paid model evaluation."""
import copy
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from scripts import cloud_job, evidence_retrieval, literature_benchmark, literature_matrix, literature_review, literaturectl, paper_qa
from scripts.research_artifacts import read, record, sha, write
from tests.test_literature_workbench import WorkbenchFixture


class LiteratureReviewPipelineTests(WorkbenchFixture):
    def setUp(self):
        super().setUp()
        self.a = self.add_paper("a", "Unseen hardware transfer improved under fixed conditions.\nThe original result requires source review.")
        self.b = self.add_paper("b", "Cross device generalization is an unresolved question in this synthetic note.")
        self.build()
        self.request = {"schema_version": "1.0", "question": "cross device generalization", "paper_ids": ["a", "b"],
            "query_expansions": [{"query": "unseen hardware transfer", "reason": "Alternative terminology for the same question"}], "limit": 8}

    def benchmark(self):
        return {"schema_version": "1.0", "annotation": {"kind": "synthetic_fixture", "by": "software acceptance fixture"},
            "cases": [{"id": "paraphrase", "request": self.request,
                "relevant": [{"paper_id": "a", **self.anchor(self.a, "Unseen hardware transfer improved under fixed conditions.")}]}]}

    def test_plain_text_scoped_query_fusion_and_same_corpus_benchmark(self):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid request")):
            result = literature_review.retrieve(self.project, self.request)
            report = literature_benchmark.evaluate(self.project, self.benchmark())
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(result["original_text_only"])
        self.assertEqual(report["cases"][0]["baseline"]["recall"], 0)
        self.assertEqual(report["cases"][0]["candidate"]["recall"], 1)
        self.assertTrue(report["cases"][0]["same_corpus"])
        self.assertFalse(report["automatic_route_promotion"])

    def test_stale_source_cannot_reuse_a_current_report(self):
        (self.project / self.a["source"]["path"]).write_text("Changed original", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            literature_review.retrieve(self.project, self.request)

    def test_unregistered_paper_or_expanded_scope_is_rejected(self):
        self.request["paper_ids"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "absent or stale"):
            literature_review.retrieve(self.project, self.request)
        self.request["paper_ids"] = ["a"]
        self.request["sources"] = [self.b["source"]]
        with self.assertRaisesRegex(ValueError, "unsupported"):
            literature_review.retrieve(self.project, self.request)

    def test_each_answer_statement_requires_a_valid_mapping(self):
        blocks = [{"source_id": "SRC001", "locator": "lines 1-1", "text": "The sample included 120 adults."}]
        answer = {"answer": "The sample included 120 adults.", "abstain": False,
            "citations": [{"source_id": "SRC001", "locator": "lines 1-1", "quote": "120 adults"}],
            "statements": [{"text": "The sample included 120 adults.", "citation_indices": [0]}]}
        self.assertEqual(paper_qa.validate_response(json.dumps(answer), blocks, require_statement_citations=True), answer)
        answer["answer"] += " The intervention is universally effective."
        with self.assertRaisesRegex(ValueError, "exactly"):
            paper_qa.validate_response(json.dumps(answer), blocks, require_statement_citations=True)
        answer["answer"] = answer["statements"][0]["text"]
        answer["statements"][0]["citation_indices"] = [True]
        with self.assertRaisesRegex(ValueError, "indices"):
            paper_qa.validate_response(json.dumps(answer), blocks)

    def test_advanced_qa_uses_current_source_scoped_plan_and_existing_model_role(self):
        spec = literature_review.prepare(self.project, self.request)["spec"]
        sources = [s["path"] for s in spec["sources"]]
        retrieval = paper_qa.retrieve(self.project, sources, self.request["question"], retrieval_plan=spec)
        self.assertIn("RRF", retrieval["method"])
        block = retrieval["blocks"][0]
        response = {"answer": "The supplied source reports this result.", "abstain": False,
            "citations": [{"source_id": block["source_id"], "locator": block["locator"], "quote": block["text"][:30]}],
            "statements": [{"text": "The supplied source reports this result.", "citation_indices": [0]}]}
        fake = SimpleNamespace(provider="cheapai-gpt-pro", model="gpt-6.1-sol", reported_model="gpt-6.1-sol",
            request_id="synthetic", cache_hit=False, text=json.dumps(response))
        with patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}), patch.object(paper_qa.model_runtime, "call", return_value=fake) as call:
            saved = paper_qa.answer(self.project, sources, self.request["question"], "evidence/qa/new.json", execute=True, retrieval_plan=spec)
        self.assertEqual(call.call_args.kwargs["role"], "reader-qa")
        self.assertTrue(read(self.project / saved["output"])["statement_citations_checked"])
        bench = self.benchmark()
        bench["cases"][0].update(qa_report={"path": saved["output"], "sha256": sha(self.project / saved["output"])}, expected_abstain=False)
        self.assertTrue(literature_benchmark.evaluate(self.project, bench)["cases"][0]["answer"]["citation_integrity"])

    def test_benchmark_rejects_answer_block_replaced_by_same_file_different_range(self):
        spec = literature_review.prepare(self.project, self.request)["spec"]
        sources = [s["path"] for s in spec["sources"]]
        retrieval = paper_qa.retrieve(self.project, sources, self.request["question"], retrieval_plan=spec)
        retrieval["blocks"][0]["locator"] = "lines 999-999"
        target = self.project / "evidence/qa/tampered.json"
        write(target, {"question": self.request["question"], "retrieval": retrieval, "response": {"answer": "Insufficient", "abstain": True, "citations": []}})
        record(self.project, [target], "test synthetic diagnostic")
        spec = self.benchmark()
        spec["cases"][0].update(qa_report={"path": "evidence/qa/tampered.json", "sha256": sha(target)}, expected_abstain=True)
        with self.assertRaisesRegex(ValueError, "outside current original"):
            literature_benchmark.evaluate(self.project, spec)

    def test_unknown_cost_scope_cannot_claim_index_or_total_cost_coverage(self):
        spec = self.benchmark()
        spec["cost_scope"] = {}
        result = literature_benchmark.evaluate(self.project, spec)
        self.assertFalse(result["precomputed_index_cost_included"])
        self.assertIsNone(result["recorded_costs"]["total_recorded_cash_cost_cny"])
        self.assertFalse(result["total_cost_verified"])

    def test_gold_quote_must_occur_in_current_original_source(self):
        spec = self.benchmark()
        spec["cases"][0]["relevant"][0]["quote"] = "A result that never existed."
        with self.assertRaisesRegex(ValueError, "quote"):
            literature_benchmark.evaluate(self.project, spec)

    def test_duplicate_gold_anchors_cannot_inflate_recall(self):
        spec = self.benchmark()
        spec["cases"][0]["relevant"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicate gold"):
            literature_benchmark.evaluate(self.project, spec)

    def test_all_new_routes_are_nonpaid_cloud_operations_and_outputs_are_protected(self):
        from scripts.artifact_ownership import executor_owned
        write(self.project / "program/literature-retrieval.json", self.request)
        write(self.project / "program/literature-coverage.json", {"question": self.request["question"], "paper_ids": ["a"], "dimensions": ["metadata", "methods"]})
        write(self.project / "program/literature-extraction.json", {"schema_version": "1.0", "question": self.request["question"],
            "paper_ids": ["a", "b"], "fields": [{"id": "method", "type": "text", "card_field": "methods"}], "cells": []})
        write(self.project / "program/literature-benchmark.json", self.benchmark())
        operations = [{"action": "literature_retrieve"}, {"action": "literature_reading_index", "paper_id": "a"},
            {"action": "literature_coverage"}, {"action": "literature_matrix"}, {"action": "literature_benchmark"}]
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), patch("scripts.model_runtime.call", side_effect=AssertionError("no paid calls")):
            for n, operation in enumerate(operations):
                path = f"program/operation-{n}.json"
                write(self.project / path, operation)
                validated, _ = cloud_job.literature_operation(self.project, path)
                literaturectl.execute_operation(self.project, validated)
        for directory in ("literature-retrieval", "literature-reading", "literature-matrix", "literature-benchmark"):
            self.assertTrue(executor_owned(self.project, "reports/" + directory + "/test.json"))
        operations[0]["execute"] = True
        write(self.project / "program/bad-operation.json", operations[0])
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.literature_operation(self.project, "program/bad-operation.json")

    def test_numeric_benchmark_revalidates_current_matrix_inputs(self):
        self.a["source"] = self.source(self.a["source"]["path"], "Population A under fixed conditions had accuracy 95.0 %.")
        self.build()
        request = {"schema_version": "1.0", "question": "Accuracy?", "paper_ids": ["a"],
            "fields": [{"id": "accuracy", "type": "number", "quantity": "accuracy", "unit": "proportion"}],
            "cells": [{"paper_id": "a", "field_id": "accuracy", "text": "Reported accuracy", "kind": "author_claim",
                "evidence": [self.anchor(self.a, "Population A under fixed conditions had accuracy 95.0 %.")],
                "numeric": {"raw_value": "95.0", "raw_unit": "%", "quantity": "accuracy"},
                "source_context": {"kind": "prose", "population": "Population A", "conditions": "fixed conditions"}}]}
        write(self.project / "program/literature-extraction.json", request)
        result = literature_matrix.refresh(self.project)
        spec = self.benchmark()
        spec["cases"][0]["relevant"] = []
        spec["numeric_cases"] = [{"id": "accuracy", "matrix": {"path": result["report"], "sha256": sha(self.project / result["report"])},
            "paper_id": "a", "field_id": "accuracy", "expected_value": "0.95", "expected_unit": "proportion"}]
        self.assertTrue(literature_benchmark.evaluate(self.project, spec)["numeric_cases"][0]["matches_gold_value_and_unit"])
        request["question"] = "Changed extraction scope"
        write(self.project / "program/literature-extraction.json", request)
        with self.assertRaisesRegex(ValueError, "request changed"):
            literature_benchmark.evaluate(self.project, spec)
