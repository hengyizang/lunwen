"""Pinned upstream CPU SDK bridge; fixture vectors never prove research quality."""
import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import literature_paperqa as bridge, literature_semantic as semantic
from scripts.research_artifacts import read, sha, write
from tests.test_literature_semantic import FakeEngine
from tests.test_literature_workbench import WorkbenchFixture


class PaperQABridgeTests(WorkbenchFixture):
    def setUp(self):
        super().setUp()
        self.a = self.add_paper("a", "A doctor provides medical care to patients.\n")
        self.b = self.add_paper("b", "Fresh vegetables grow in gardens.\n")
        self.build()
        self.retrieval = {"schema_version": "1.0", "question": "Who treats sick people?", "paper_ids": ["a", "b"], "limit": 2}
        write(self.project / "program/literature-semantic.json", {"schema_version": "1.0", "retrieval": self.retrieval, "rerank": False})
        self.cloud = patch.object(semantic, "_cloud")
        self.cloud.start()
        self.addCleanup(self.cloud.stop)
        with patch.object(semantic, "CpuEngine", FakeEngine):
            semantic.refresh(self.project)
        self.spec = {"schema_version": "1.0", "id": "fixture", "retrieval": self.retrieval,
            "semantic": {"path": semantic.OUTPUT + "/latest.json", "sha256": sha(self.project / semantic.OUTPUT / "latest.json")}}
        write(self.project / bridge.REQUEST, self.spec)

    def rank(self, query, chunks, dense):
        return [{"block_index": i, "cosine_similarity": 1.0 - i} for i in range(len(chunks))]

    def test_default_bridge_cannot_spend_and_reuses_current_result(self):
        with patch.object(bridge, "sdk_rank", side_effect=self.rank) as ranking, patch.object(bridge.model_runtime, "call", side_effect=AssertionError("no paid call")):
            result = bridge.refresh(self.project)
            again = bridge.refresh(self.project)
            checked = bridge.validate_saved_report(self.project)
        self.assertEqual(ranking.call_count, 1)
        self.assertTrue(again["cache_hit"])
        self.assertEqual(result["retrieval"], checked["retrieval"])
        self.assertFalse(result["upstream_agent_enabled"])
        self.assertEqual(result["upstream_model_calls"], 0)
        self.assertEqual(result["upstream_embedding_calls"], 0)
        self.assertFalse(result["model_call_made"])

    def test_explicit_answer_uses_only_existing_metered_role_and_quote_validator(self):
        quote = "A doctor provides medical care to patients."
        response = {"answer": "The source describes medical care.", "abstain": False,
            "statements": [{"text": "The source describes medical care.", "citation_indices": [0]}],
            "citations": [{"source_id": "SRC001", "locator": "lines 1-1", "quote": quote}]}
        model = SimpleNamespace(provider="cheapai-gpt-pro", model="gpt-6.1-sol", reported_model="gpt-6.1-sol",
            request_id="synthetic-request", cache_hit=False, text=json.dumps(response))
        with patch.object(bridge, "sdk_rank", side_effect=self.rank), patch.object(bridge.model_runtime, "call", return_value=model) as call, patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}):
            result = bridge.refresh(self.project, execute=True)
            again = bridge.refresh(self.project, execute=True)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.kwargs["role"], "reader-qa")
        self.assertEqual(call.call_args.kwargs["reasoning_effort"], "high")
        self.assertEqual(result["response"], response)
        self.assertFalse(result["semantic_support_verified"])
        self.assertTrue(again["cache_hit"])

    def test_rejected_answer_is_retained_without_automatic_retry(self):
        model = SimpleNamespace(provider="fixture", model="fixture", reported_model="fixture", request_id="fixture", cache_hit=False,
            text=json.dumps({"answer": "Invented result", "abstain": False, "statements": [], "citations": []}))
        with patch.object(bridge, "sdk_rank", side_effect=self.rank), patch.object(bridge.model_runtime, "call", return_value=model) as call:
            result = bridge.refresh(self.project, execute=True)
            again = bridge.refresh(self.project, execute=True)
        self.assertEqual(result["status"], "model_response_rejected_do_not_use")
        self.assertNotIn("response", result)
        self.assertEqual(call.call_count, 1)
        self.assertTrue(again["cache_hit"])

    def test_changed_query_semantic_binding_and_source_block_before_sdk(self):
        with patch.object(bridge, "sdk_rank", side_effect=AssertionError("invalid requests must not load SDK")):
            bad = copy.deepcopy(self.spec)
            bad["semantic"]["sha256"] = "0" * 64
            write(self.project / bridge.REQUEST, bad)
            with self.assertRaisesRegex(ValueError, "exact current semantic"):
                bridge.refresh(self.project)
            bad = copy.deepcopy(self.spec)
            bad["retrieval"]["question"] = "What grows in the garden?"
            write(self.project / bridge.REQUEST, bad)
            with self.assertRaisesRegex(ValueError, "exact current semantic"):
                bridge.refresh(self.project)
            write(self.project / bridge.REQUEST, self.spec)
            (self.project / self.a["source"]["path"]).write_text("A changed original.\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                bridge.refresh(self.project)

    def test_context_preserves_contrary_sources_and_fails_if_limit_cannot(self):
        prepared = bridge._prepare(self.project, self.spec)
        prepared["searched"][1]["stance"] = "contradicts"
        ranking = self.rank(None, prepared["chunks"], None)
        context = bridge._context(prepared, ranking, 24000, 1)
        self.assertEqual(context["blocks"][0]["source_id"], "SRC002")
        self.assertEqual(context["blocks"][0]["selection_reason"], "declared_counterevidence")
        prepared["searched"][0]["stance"] = "mixed"
        with self.assertRaisesRegex(ValueError, "cannot retain all"):
            bridge._context(prepared, ranking, 24000, 1)

    def test_tampered_output_or_semantic_cache_cannot_be_replayed(self):
        with patch.object(bridge, "sdk_rank", side_effect=self.rank):
            result = bridge.refresh(self.project)
        output = self.project / result["report"]
        payload = read(output)
        payload["semantic_support_verified"] = True
        write(output, payload)
        with self.assertRaisesRegex(ValueError, "output or implementation changed"):
            bridge.validate_saved_report(self.project)

    def test_sdk_version_mismatch_is_rejected_before_import(self):
        prepared = bridge._prepare(self.project, self.spec)
        with patch.object(bridge.importlib.metadata, "version", return_value="different"):
            with self.assertRaisesRegex(ValueError, "exact package version"):
                bridge.sdk_rank(prepared["prepared"]["question"], prepared["chunks"], prepared["dense"])

    def test_actual_pinned_sdk_uses_cached_vectors_without_any_network_or_model_call(self):
        try:
            if importlib.metadata.version("paper-qa") != bridge.SDK_VERSION:
                self.skipTest("actual SDK acceptance needs pinned optional paper-qa package")
        except importlib.metadata.PackageNotFoundError:
            self.skipTest("actual SDK acceptance needs pinned optional paper-qa package")
        prepared = bridge._prepare(self.project, self.spec)
        # Load imports before disabling transport; similarity search itself is
        # required to use only NumPy and the exact-bound query callback.
        from paperqa.llms import NumpyVectorStore
        self.assertTrue(callable(NumpyVectorStore.similarity_search))
        with patch("socket.socket.connect", side_effect=AssertionError("SDK may not open provider transport")), patch.object(bridge.model_runtime, "call", side_effect=AssertionError("no paid call")):
            ranking = bridge.sdk_rank(prepared["prepared"]["question"], prepared["chunks"], prepared["dense"])
            result = bridge.refresh(self.project)
        self.assertEqual(ranking[0]["block_index"], 0)
        self.assertAlmostEqual(ranking[0]["cosine_similarity"], 1.0)
        self.assertAlmostEqual(ranking[1]["cosine_similarity"], 0.0)
        self.assertIn("NumpyVectorStore", result["retrieval"]["method"])
        self.assertEqual(result["sdk_source_revision"], bridge.SDK_REVISION)
        self.assertEqual(result["retrieval"]["sources"][0]["path"], self.a["source"]["path"])
