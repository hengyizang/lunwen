"""Cloud-runner regressions for bounded literature retrieval, without model calls."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import evidence_retrieval


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class LiteratureRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name)

    def source(self, name, text, stance="neutral"):
        path = self.project / ("evidence/" + name + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return {"path": path.relative_to(self.project).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "stance": stance}

    def plan(self, sources, query="cross device generalization", **options):
        return {"schema_version": "1.0", "sources": sources, "query": query, **options}

    def dense(self, spec, vectors, query_vector=None):
        blocks = []
        for source in spec["sources"]:
            text = (self.project / source["path"]).read_text(encoding="utf-8")
            lines = text.splitlines(keepends=True)
            for selected in source.get("ranges", [{"start_line": 1, "end_line": len(lines)}]):
                for start in range(selected["start_line"] - 1, selected["end_line"], 20):
                    end = min(start + 20, selected["end_line"])
                    blocks.append({"path": source["path"], "sha256": source["sha256"],
                                   "start_line": start + 1, "end_line": end,
                                   "excerpt_sha256": digest("".join(lines[start:end])), "vector": vectors[len(blocks)]})
        cache = {"schema_version": "1.0", "model": {"id": "synthetic-test-embedding", "revision": "fixture-v1"},
                 "dimension": 2, "query": {"text": spec["query"], "sha256": digest(spec["query"]),
                 "vector": [1, 0] if query_vector is None else query_vector},
                 "sources": [{key: row[key] for key in ("path", "sha256", "ranges") if key in row} for row in spec["sources"]],
                 "blocks": blocks}
        self.save_dense(spec, cache)
        return cache

    def save_dense(self, spec, cache):
        path = self.project / "evidence/dense.json"
        path.write_text(json.dumps(cache), encoding="utf-8")
        spec["dense_cache"] = {"path": "evidence/dense.json", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_bm25_without_expansions_preserves_old_behavior(self):
        source = self.source("method", "Cross device generalization uses held-out devices.\n")
        result = evidence_retrieval.retrieve(self.project, self.plan([source]))
        self.assertTrue(result["algorithm"].startswith("BM25"))
        self.assertEqual(result["results"][0]["quote"], "Cross device generalization uses held-out devices.\n")
        self.assertEqual(result["results"][0]["score"], result["results"][0]["lexical_score"])
        self.assertFalse(result["automatic_source_exclusion"])
        self.assertEqual(result["paid_calls"], 0)

    def test_explicit_paraphrase_finds_originally_unmatched_evidence(self):
        source = self.source("transfer", "Transfer to unseen instruments was evaluated on held-out hardware.\n")
        spec = self.plan([source])
        baseline = evidence_retrieval.retrieve(self.project, spec)
        self.assertEqual(baseline["results"], [])
        spec["query_expansions"] = [{"query": "unseen instruments held-out hardware", "reason": "Terminology for the same declared question."}]
        result = evidence_retrieval.retrieve(self.project, spec)
        self.assertEqual(result["results"][0]["path"], source["path"])
        self.assertTrue(result["routes"][0]["no_match"])
        self.assertEqual(result["routes"][1]["returned_chunks"], 1)
        self.assertFalse(result["routes"][1]["semantic_expansion_verified"])

    def test_rrf_combines_ranks_instead_of_incomparable_raw_scores(self):
        both = self.source("both", "Robustness transfer.\n")
        first = self.source("first", "Robustness robustness robustness.\n")
        second = self.source("second", "Transfer transfer transfer.\n")
        spec = self.plan([both, first, second], query="robustness", query_expansions=[
            {"query": "transfer", "reason": "Alternate declared measurement wording."}])
        result = evidence_retrieval.retrieve(self.project, spec)
        selected = result["results"][0]
        self.assertEqual(selected["path"], both["path"])
        self.assertAlmostEqual(selected["score"], sum(1 / (60 + route["rank"]) for route in selected["retrieval_routes"].values()))

    def test_declared_counterevidence_survives_no_lexical_match(self):
        positive = self.source("positive", "Generalization improves.\n", "supports")
        negative = self.source("negative", "Transfer failed under sensor shift.\n", "contradicts")
        result = evidence_retrieval.retrieve(self.project, self.plan([positive, negative], query="generalization", limit=1))
        self.assertEqual(result["results"][0]["path"], negative["path"])
        self.assertEqual(result["results"][0]["score"], 0)
        self.assertEqual(result["routes"][0]["not_returned_matching_chunks"], 1)
        self.assertTrue(result["counterevidence_retention_is_not_full_reading"])

    def test_too_small_limit_cannot_silently_hide_counterevidence(self):
        sources = [self.source("a", "Adverse finding.\n", "contradicts"), self.source("b", "Mixed finding.\n", "mixed")]
        with self.assertRaisesRegex(ValueError, "counterevidence"):
            evidence_retrieval.retrieve(self.project, self.plan(sources, limit=1))

    def test_same_work_different_versions_remain_distinct_sources(self):
        sources = [self.source("preprint", "Transfer estimate was 0.2.\n"), self.source("published", "Transfer estimate was 0.1.\n")]
        result = evidence_retrieval.retrieve(self.project, self.plan(sources, query="transfer estimate"))
        self.assertEqual(len(result["searched_sources"]), 2)
        self.assertEqual({row["path"] for row in result["results"]}, {row["path"] for row in sources})

    def test_no_match_retains_explicit_search_inventory(self):
        source = self.source("unmatched", "A different mechanism.\n")
        result = evidence_retrieval.retrieve(self.project, self.plan([source], query="sensors"))
        self.assertEqual(result["results"], [])
        self.assertEqual(result["searched_sources"][0]["returned_chunks"], 0)
        self.assertEqual(result["not_returned_chunk_count"], 1)
        self.assertFalse(result["scientific_completeness_verified"])

    def test_chinese_expansion_is_searchable(self):
        source = self.source("chinese", "研究检验了未见设备上的迁移能力。\n")
        result = evidence_retrieval.retrieve(self.project, self.plan([source], query="cross device generalization", query_expansions=[
            {"query": "未见设备 迁移能力", "reason": "Chinese wording for the same research question."}]))
        self.assertEqual(result["results"][0]["path"], source["path"])

    def test_original_ranges_never_retrieve_translation_or_generated_headings(self):
        source = self.source("reader", "# Reader\n## Original text\nTransfer to unseen hardware.\n## Translation\nGeneralization was conclusively proved.\n")
        source["ranges"] = [{"start_line": 3, "end_line": 3, "pdf_page": 7}]
        spec = self.plan([source], query="generalization", query_expansions=[
            {"query": "transfer", "reason": "Alternate wording within the same source selection."}])
        result = evidence_retrieval.retrieve(self.project, spec)
        self.assertEqual(result["results"][0]["quote"], "Transfer to unseen hardware.\n")
        self.assertEqual(result["results"][0]["start_line"], 3)
        self.assertEqual(result["results"][0]["pdf_page"], 7)
        self.assertTrue(result["routes"][0]["no_match"])
        self.assertEqual(result["searched_sources"][0]["indexed_line_count"], 1)

    def test_ranges_must_be_nonempty_ordered_and_bounded(self):
        source = self.source("reader", "one\ntwo\nthree\n")
        invalid = [None, [], [{"start_line": 0, "end_line": 1}],
                   [{"start_line": 1, "end_line": 4}], [{"start_line": True, "end_line": 2}],
                   [{"start_line": 1, "end_line": 2}, {"start_line": 2, "end_line": 3}],
                   [{"start_line": 3, "end_line": 3}, {"start_line": 1, "end_line": 1}],
                   [{"start_line": 1, "end_line": 1, "pdf_page": False}]]
        for ranges in invalid:
            with self.subTest(ranges=ranges), self.assertRaises(ValueError):
                evidence_retrieval.retrieve(self.project, self.plan([{**source, "ranges": ranges}], query="one"))

    def test_dense_cache_recovers_zero_lexical_overlap_without_calls(self):
        a = self.source("a", "Held-out hardware transfer.\n")
        b = self.source("b", "Different clinical outcome.\n")
        spec = self.plan([a, b], query="cross device generalization")
        self.dense(spec, [[1, 0], [0, 1]])
        result = evidence_retrieval.retrieve(self.project, spec)
        self.assertEqual(result["results"][0]["path"], a["path"])
        self.assertEqual(result["dense_cache"]["embedding_calls_made"], 0)
        self.assertFalse(result["dense_cache"]["model_identity_independently_verified"])
        self.assertEqual(result["routes"][1]["method"], "cosine_similarity")

    def test_dense_cache_tamper_blocks_instead_of_silent_fallback(self):
        source = self.source("a", "Robustness finding.\n")
        spec = self.plan([source], query="robustness")
        self.dense(spec, [[1, 0]])
        (self.project / "evidence/dense.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cache changed"):
            evidence_retrieval.retrieve(self.project, spec)

    def test_dense_cache_binds_the_selected_original_ranges(self):
        source = self.source("reader", "Original hardware transfer.\nGenerated translation.\n")
        source["ranges"] = [{"start_line": 1, "end_line": 1, "pdf_page": 2}]
        spec = self.plan([source])
        self.dense(spec, [[1, 0]])
        result = evidence_retrieval.retrieve(self.project, spec)
        self.assertEqual(result["results"][0]["quote"], "Original hardware transfer.\n")
        spec["sources"][0]["ranges"][0]["end_line"] = 2
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            evidence_retrieval.retrieve(self.project, spec)

    def test_dense_cache_rejects_changed_query_source_or_block(self):
        source = self.source("a", "Robustness finding.\n")
        spec = self.plan([source], query="robustness")
        base = self.dense(spec, [[1, 0]])
        for mutate in (lambda c: c["query"].update(text="other"),
                       lambda c: c["sources"][0].update(sha256="0" * 64),
                       lambda c: c["blocks"][0].update(excerpt_sha256="0" * 64),
                       lambda c: c["blocks"][0].update(start_line=True)):
            changed = copy.deepcopy(base)
            mutate(changed)
            self.save_dense(spec, changed)
            with self.assertRaises(ValueError):
                evidence_retrieval.retrieve(self.project, spec)

    def test_dense_cache_rejects_partial_duplicate_zero_nonfinite_or_wrong_dimension(self):
        a = self.source("a", "Robustness finding.\n")
        b = self.source("b", "Adverse finding.\n")
        spec = self.plan([a, b], query="robustness")
        base = self.dense(spec, [[1, 0], [0, 1]])
        for mutate in (lambda c: c["blocks"].pop(),
                       lambda c: c["blocks"].__setitem__(1, c["blocks"][0]),
                       lambda c: c["blocks"][0].update(vector=[0, 0]),
                       lambda c: c["blocks"][0].update(vector=[True, 0]),
                       lambda c: c["blocks"][0].update(vector=[float("nan"), 0]),
                       lambda c: c["blocks"][0].update(vector=[1, 0, 0]),
                       lambda c: c.update(dimension=True),
                       lambda c: c.update(model={"id": "unversioned"})):
            changed = copy.deepcopy(base)
            mutate(changed)
            self.save_dense(spec, changed)
            with self.assertRaises(ValueError):
                evidence_retrieval.retrieve(self.project, spec)

    def test_plan_fingerprint_changes_with_query_expansion_or_source(self):
        source = self.source("a", "Robustness transfer.\n")
        spec = self.plan([source], query="robustness")
        baseline = evidence_retrieval.retrieve(self.project, spec)["input_fingerprint"]
        spec["query_expansions"] = [{"query": "transfer", "reason": "Same scope alternate wording."}]
        expanded = evidence_retrieval.retrieve(self.project, spec)["input_fingerprint"]
        self.assertNotEqual(baseline, expanded)
        self.assertEqual(expanded, evidence_retrieval.retrieve(self.project, spec)["input_fingerprint"])
        (self.project / source["path"]).write_text("Changed evidence.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            evidence_retrieval.retrieve(self.project, spec)

    def test_malformed_expansions_and_sources_rejected(self):
        source = self.source("a", "Robustness finding.\n")
        cases = [self.plan([source], query=""), self.plan([source], query_expansions="x"),
                 self.plan([source], query_expansions=[{"query": "x", "reason": ""}]),
                 self.plan([source], query_expansions=[{"query": "cross device generalization", "reason": "duplicate"}]),
                 self.plan([source], query_expansions=[{"query": "extra", "reason": "x"}] * 6),
                 self.plan([{**source, "stance": []}]), self.plan([source, source])]
        for spec in cases:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                evidence_retrieval.retrieve(self.project, spec)


if __name__ == "__main__":
    unittest.main()
