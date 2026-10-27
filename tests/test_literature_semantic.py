"""Cloud-only semantic contracts; synthetic scores are not quality evidence."""
import copy
import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import evidence_retrieval, literature_review, literature_semantic as semantic
from scripts.research_artifacts import read, record, sha, write
from tests.test_literature_workbench import WorkbenchFixture


class FakeEngine:
    calls = []

    def __init__(self, project, kind):
        self.kind = kind
        self.executions = 0
        self.calls.append(("init", kind))

    def embed(self, text):
        self.executions += 1
        self.calls.append(("embed", text))
        vector = [1.0, 0.0] if "vegetables" not in text else [0.6, 0.8]
        return vector + [0.0] * 382, {"windows": 1, "all_windows_processed": True}

    def score(self, query, text):
        self.executions += 1
        self.calls.append(("score", text))
        return (-10.0 if "failed" in text else 10.0), {"windows": 1, "all_windows_processed": True}

    def receipt(self):
        model = semantic.lock()[self.kind]
        return {"id": model["id"], "revision": model["revision"], "provider": "CPUExecutionProvider",
                "onnx_executions": self.executions, "synthetic_fixture": True}


class SemanticTests(WorkbenchFixture):
    def setUp(self):
        super().setUp()
        self.a = self.add_paper("a", "A doctor provides medical care to patients.\n")
        self.b = self.add_paper("b", "Fresh vegetables grow in gardens.\n")
        self.build()
        self.request = {"schema_version": "1.0", "retrieval": {"schema_version": "1.0",
            "question": "Who treats sick people?", "paper_ids": ["a", "b"], "limit": 2}, "rerank": False}
        self.request_source = self.project / "program/literature-semantic.json"
        write(self.request_source, self.request)
        FakeEngine.calls = []
        self.cpu = patch.object(semantic, "CpuEngine", FakeEngine)
        self.cpu.start()
        self.addCleanup(self.cpu.stop)
        self.cloud = patch.object(semantic, "_cloud")
        self.cloud.start()
        self.addCleanup(self.cloud.stop)

    def refresh(self):
        write(self.request_source, self.request)
        return semantic.refresh(self.project)

    def test_default_lexical_route_does_not_load_a_model(self):
        result = literature_review.retrieve(self.project, self.request["retrieval"])
        self.assertEqual(result["results"], [])
        self.assertEqual(FakeEngine.calls, [])

    def test_generated_dense_cache_is_consumed_by_existing_retrieval(self):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid call")):
            report = self.refresh()
        self.assertEqual(report["result"]["results"][0]["path"], self.a["source"]["path"])
        self.assertEqual(report["baseline"]["results"], [])
        self.assertEqual(report["paid_calls"], 0)
        dense = read(self.project / report["dense_cache"]["path"])
        self.assertEqual(dense["dimension"], 384)
        self.assertEqual(len(dense["blocks"]), 2)
        self.assertFalse(report["semantic_quality_verified"])
        self.assertFalse(report["automatic_route_promotion"])
        again = literature_review.retrieve(self.project, report["retrieval_request"])
        self.assertEqual(again["results"], report["result"]["results"])

    def test_identical_request_reuses_complete_result_without_cpu(self):
        first = self.refresh()
        FakeEngine.calls = []
        again = self.refresh()
        self.assertTrue(again["complete_result_cache_hit"])
        self.assertEqual(again["result"], first["result"])
        self.assertEqual(FakeEngine.calls, [])

    def test_new_question_reuses_all_document_vectors(self):
        first = self.refresh()
        FakeEngine.calls = []
        self.request["retrieval"]["question"] = "Who supplies clinical treatment?"
        again = self.refresh()
        self.assertTrue(again["corpus_index_cache_hit"])
        self.assertFalse(again["query_cache_hit"])
        self.assertEqual(first["index"], again["index"])
        self.assertEqual([x for x in FakeEngine.calls if x[0] == "embed"],
                         [("embed", self.request["retrieval"]["question"])])

    def test_cache_tamper_is_rejected(self):
        report = self.refresh()
        target = self.project / report["dense_cache"]["path"]
        value = read(target)
        value["query"]["vector"] = [0.0, 1.0] + [0.0] * 382
        write(target, value)
        with self.assertRaisesRegex(ValueError, "cache changed"):
            semantic.validate_saved_report(self.project)

    def test_index_tamper_is_rejected(self):
        report = self.refresh()
        write(self.project / report["index"]["path"], {"blocks": []})
        with self.assertRaisesRegex(ValueError, "cache changed"):
            semantic.validate_saved_report(self.project)

    def test_source_change_is_rejected_before_model_loading(self):
        self.refresh()
        FakeEngine.calls = []
        (self.project / self.a["source"]["path"]).write_text("Changed original source.", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.refresh()
        self.assertEqual(FakeEngine.calls, [])

    def test_request_change_invalidates_saved_report(self):
        self.refresh()
        self.request["retrieval"]["question"] = "Different question?"
        write(self.request_source, self.request)
        with self.assertRaisesRegex(ValueError, "request"):
            semantic.validate_saved_report(self.project)

    def test_unregistered_sources_and_unbounded_requests_rejected(self):
        for mutate in (lambda r: r["retrieval"].update(paper_ids=["missing"]),
                       lambda r: r.update(rerank="yes"),
                       lambda r: r.update(extra=True),
                       lambda r: r["retrieval"].update(dense_cache={}),
                       lambda r: r["retrieval"].update(rerank_cache={})):
            request = copy.deepcopy(self.request)
            mutate(request)
            with self.subTest(request=request), self.assertRaises(ValueError):
                semantic.build(self.project, request)

    def test_cpu_ceiling_has_no_truncated_fallback(self):
        with patch.object(semantic, "MAX_BLOCKS", 1), self.assertRaisesRegex(ValueError, "smaller"):
            self.refresh()
        self.assertEqual(FakeEngine.calls, [])

    def test_rerank_is_independent_and_preserves_low_scoring_counterevidence(self):
        self.a["source"] = self.source(self.a["source"]["path"], "Treatment failed for all patients.\n")
        self.build()
        self.request["retrieval"]["stances"] = {"a": "contradicts"}
        self.request["rerank"] = True
        report = self.refresh()
        rows = report["result"]["results"]
        self.assertEqual(rows[0]["path"], self.b["source"]["path"])
        self.assertEqual({r["path"] for r in rows}, {self.a["source"]["path"], self.b["source"]["path"]})
        self.assertLess(rows[1]["reranker_score"], 0)
        self.assertTrue(rows[1]["reranker_coverage"]["all_windows_processed"])
        self.assertEqual(report["reranker_execution"]["onnx_executions"], 2)
        self.assertEqual(report["result"]["declared_counterevidence_sources"], [self.a["source"]["path"]])
        self.assertEqual(semantic.validate_saved_report(self.project)["result"], report["result"])

    def test_rerank_cache_is_exact_query_and_candidate_bound(self):
        self.request["rerank"] = True
        report = self.refresh()
        request = copy.deepcopy(report["retrieval_request"])
        request["limit"] = 1
        with self.assertRaisesRegex(ValueError, "scope changed"):
            literature_review.retrieve(self.project, request)

    def test_rerank_tamper_does_not_silently_fallback(self):
        self.request["rerank"] = True
        report = self.refresh()
        target = self.project / report["rerank_cache"]["path"]
        value = read(target)
        value["scores"][0] = 9999
        write(target, value)
        with self.assertRaisesRegex(ValueError, "rerank cache changed"):
            literature_review.retrieve(self.project, report["retrieval_request"])

    def test_arbitrary_rerank_cache_outside_controlled_tree_rejected(self):
        request = {**self.request["retrieval"], "rerank_cache": {"path": "evidence/scores.json", "sha256": "0" * 64}}
        with self.assertRaisesRegex(ValueError, "controlled CPU"):
            literature_review.retrieve(self.project, request)

    def test_model_lock_has_fixed_graph_hashes_and_distinct_language_scopes(self):
        value = semantic.lock()
        self.assertNotEqual(value["embedding"]["id"], value["reranker"]["id"])
        self.assertIn("multilingual", value["embedding"]["language_scope"])
        self.assertIn("English", value["reranker"]["language_scope"])
        self.assertEqual(value["embedding"]["dimension"], 384)

    def test_external_model_download_redirect_is_rejected(self):
        from urllib.request import Request
        with self.assertRaisesRegex(ValueError, "reviewed"):
            semantic._HubRedirect().redirect_request(Request("https://huggingface.co/a"), None, 302,
                "Found", {}, "https://untrusted.example/model.onnx")


@unittest.skipUnless(os.environ.get("DR_OS_LITERATURE_SEMANTIC_LIVE") == "1", "explicit cloud CPU model acceptance")
class RealCpuSemanticTests(WorkbenchFixture):
    def test_actual_embeddings_reranking_and_long_window_coverage(self):
        self.add_paper("a", "Berlin had a population of 3,520,031 registered inhabitants.\n")
        self.add_paper("b", "New York City is famous for the Metropolitan Museum of Art.\n")
        self.build()
        request = {"schema_version": "1.0", "retrieval": {"schema_version": "1.0",
            "question": "How many people live in Berlin?", "paper_ids": ["a", "b"], "limit": 2}, "rerank": True}
        report = semantic.build(self.project, request)
        self.assertEqual(report["result"]["results"][0]["path"], self.config["papers"][0]["source"]["path"])
        self.assertGreater(report["embedding_execution"]["onnx_executions"], 0)
        self.assertGreater(report["reranker_execution"]["onnx_executions"], 0)
        engine = semantic.CpuEngine(self.project, "embedding")
        vector, coverage = engine.embed("The complete paragraph describes a repeated measurement. " * 100)
        self.assertEqual(len(vector), 384)
        self.assertGreater(coverage["windows"], 1)
        self.assertTrue(coverage["all_windows_processed"])
        reranker = semantic.CpuEngine(self.project, "reranker")
        _, windows = reranker.score("What is measured?", "A measurement is recorded. " * 180)
        self.assertGreater(windows["windows"], 1)
        self.assertTrue(windows["all_windows_processed"])
