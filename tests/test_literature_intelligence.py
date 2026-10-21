from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import literature_evidence as evidence
from scripts import literature_intelligence as intelligence


class LiteratureIntelligenceTests(unittest.TestCase):
    def work(self, **changes):
        return {"id": "s2:one", "provider": "Semantic Scholar", "provider_id": "one", "title": "Robust machinery prediction",
                "authors": ["Alice Researcher"], "doi": None, "publication_year": 2025, "citation_count": None,
                "abstract": None, "source_refs": [], **changes}

    def project(self, root, plan=None, *, core=None):
        project = root / "project"
        (project / "program").mkdir(parents=True)
        value = {"schema_version": "1.0", "doctoral_question": "How can machinery predictions remain robust?",
                 "topic_keywords": ["machinery", "robust"], "exclude_keywords": [], "as_of": "2026-10-21",
                 "max_requests": 4, "searches": [{"provider": "semantic-scholar", "query": "robust machinery", "limit": 10}], **(plan or {})}
        (project / intelligence.PLAN).write_text(json.dumps(value), encoding="utf-8")
        if core is not None:
            (project / "program/core-thesis.json").write_text(json.dumps(core), encoding="utf-8")
        return project

    @staticmethod
    def fetch(url, **_kwargs):
        return json.dumps({"data": [{"paperId": "one", "title": "Robust machinery prediction", "year": 2025,
            "authors": [{"name": "Alice Researcher"}], "externalIds": {"DOI": "10.1000/one"}, "citationCount": 10,
            "abstract": "However, distribution changes remain challenging. We propose robust prediction. We evaluate a benchmark."}]}).encode(), url, 200, "application/json"

    def test_identity_requires_more_than_title_and_preserves_arxiv_versions(self):
        one = self.work(arxiv_id="2501.00001v1")
        two = self.work(arxiv_id="2501.00001v2", provider_id="two", publication_year=2026)
        result = intelligence.deduplicate([one, two])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["arxiv_versions"], ["2501.00001v1", "2501.00001v2"])
        self.assertTrue(any(row["field"] == "publication_year" for row in result[0]["metadata_conflicts"]))
        self.assertFalse(intelligence.canonical_match(self.work(authors=[]), self.work(authors=[], provider_id="two")))
        self.assertFalse(intelligence.canonical_match(self.work(authors=["Alice Researcher"]), self.work(authors=["Bob Researcher"])))
        self.assertTrue(intelligence.canonical_match(self.work(doi="https://doi.org/10.1000/ONE"), self.work(doi="10.1000/one")))

    def test_conflicting_dois_never_merge_on_identical_title_and_author(self):
        result = intelligence.deduplicate([self.work(doi="10.1000/one"), self.work(doi="10.1000/two")])
        self.assertEqual(len(result), 2)
        self.assertTrue(all(row["metadata_conflicts"][0]["field"] == "identity" for row in result))
        self.assertFalse(intelligence.canonical_match(result[0], result[1]))

    def test_ranking_explains_rhetoric_and_keeps_declared_exclusions_and_unknowns(self):
        plan = {"topic_keywords": ["machinery"], "exclude_keywords": ["clinical"], "as_of": "2026-10-21"}
        rhetoric = "However, a limitation remains. We propose a method. We evaluate a benchmark."
        rows = intelligence.rank_candidates(intelligence.deduplicate([
            self.work(doi="10.1000/one", abstract=rhetoric, citation_count=10),
            self.work(doi="10.1000/two", title="Clinical machinery prediction", abstract="clinical trial", citation_count=100000),
            self.work(doi="10.1000/three", title="Unrelated topic", publication_year=None)]), plan)
        self.assertEqual(rows[0]["doi"], "10.1000/one")
        self.assertEqual(len(rows[0]["rhetoric_indicators"]), 5)
        self.assertEqual(rows[0]["score_components"]["abstract_rhetoric"], 0.75)
        for marker in rows[0]["rhetoric_indicators"]:
            self.assertEqual(rhetoric[marker["start_char"]:marker["end_char"]], marker["quote"])
        excluded = next(row for row in rows if row["doi"] == "10.1000/two")
        self.assertFalse(excluded["reading_candidate"])
        self.assertEqual(excluded["exclusion_matches"], ["clinical"])
        self.assertEqual(excluded["ranking_meaning"], "DISCOVERY_HEURISTIC_NOT_RESEARCH_QUALITY")
        self.assertIn("citation_count_unknown", rows[-1]["unknowns"])
        self.assertFalse(rows[0]["novelty_verified"])

    def test_sota_first_and_performance_words_are_located_weak_discovery_signals(self):
        abstract = "Our first novel method reports SOTA accuracy and outperforms a baseline; an ablation is included."
        plan = {"topic_keywords": ["machinery"], "as_of": "2026-10-21"}
        result = intelligence.rank_candidates([self.work(abstract=abstract)], plan)[0]
        markers = result["rhetoric_indicators"]
        self.assertEqual({row["kind"] for row in markers}, {"reported_novelty_or_performance"})
        self.assertTrue({"first", "novel", "SOTA", "accuracy", "outperforms", "ablation"}.issubset({row["marker"] for row in markers}))
        for marker in markers:
            self.assertEqual(abstract[marker["start_char"]:marker["end_char"]], marker["quote"])
        self.assertEqual(result["score_components"]["abstract_rhetoric"], 0.25)
        self.assertEqual(result["ranking_meaning"], "DISCOVERY_HEURISTIC_NOT_RESEARCH_QUALITY")
        self.assertFalse(result["novelty_verified"])

    def test_discovery_reuses_current_hash_bound_receipts_and_never_approves_proposed_scope(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}), \
             patch.object(evidence, "utc_now", return_value="2026-10-21T00:00:00+00:00"):
            project = self.project(Path(directory))
            first = intelligence.discover(project, fetcher=self.fetch)
            self.assertEqual(first["scope_status"], "proposed_requires_G1_review")
            self.assertEqual(first["metadata_requests"], 1)
            self.assertFalse(first["gate_approved"])
            self.assertFalse(first["topic_leads"][0]["gap_proven"])
            self.assertEqual(first["paid_model_calls"], 0)
            self.assertTrue(first["changed"])
            self.assertTrue((project / first["history_path"]).is_file())
            self.assertTrue(first["sources_sha256"])
            self.assertTrue(first["topic_leads"][0]["source_refs"][0]["normalized_results_sha256"])
            with patch.object(evidence, "execute_search", side_effect=AssertionError("cache should be reused")):
                second = intelligence.discover(project)
            self.assertEqual(second["metadata_requests"], 0)
            self.assertFalse(second["changed"])
            self.assertEqual(second["recommendation_delta"]["added"], [])
            self.assertEqual(first["candidates"], second["candidates"])
            raw = project / first["source_receipts"][0]["raw_response_path"]
            raw.write_text("tampered", encoding="utf-8")
            plan = json.loads((project / intelligence.PLAN).read_text())
            plan.update(searches=[], receipts=[first["source_receipts"][0]["receipt_id"]])
            (project / intelligence.PLAN).write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale literature receipt"):
                intelligence.discover(project)

    def test_current_question_cannot_drift_and_local_execution_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.project(Path(directory), core={"doctoral_question": "A different approved question"})
            with patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}), \
                 patch.object(evidence, "execute_search") as call:
                with self.assertRaisesRegex(ValueError, "differs from the current doctoral question"):
                    intelligence.discover(project)
                call.assert_not_called()
            with patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}):
                with self.assertRaisesRegex(RuntimeError, "cloud executor"):
                    intelligence.discover(project)

    def test_conference_enrichment_rejects_title_only_match_and_records_missing_identity(self):
        def fetch(url, **_kwargs):
            if "sparql.dblp.org" in url:
                row = {key: {"value": value} for key, value in {"publ": "https://dblp.org/rec/conf/icml/one",
                    "title": "Robust machinery prediction", "year": "2025", "venue": "https://dblp.org/streams/conf/icml"}.items()}
                return json.dumps({"results": {"bindings": [row]}}).encode(), url, 200, "application/json"
            return self.fetch(url)
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = self.project(Path(directory), {"searches": [], "conferences": [{"venue": "conf/icml", "year": 2025, "enrich_limit": 1}]})
            result = intelligence.discover(project, fetcher=fetch)
            self.assertEqual(result["enrichment"][0]["status"], "unresolved_no_canonical_match")
            self.assertEqual(len(result["candidates"]), 1)
            self.assertIsNone(result["candidates"][0]["abstract"])
            self.assertEqual(result["metadata_requests"], 2)

    def test_request_ceiling_and_failed_searches_remain_visible(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}), \
             patch.object(evidence, "execute_search") as call:
            project = self.project(Path(directory), {"max_requests": 0})
            result = intelligence.discover(project)
            call.assert_not_called()
            self.assertEqual(result["status"], "partial_requires_review")
            self.assertIn("ceiling", result["errors"][0]["error"])
            self.assertFalse(result["coverage_complete"])

    def test_conference_doi_enrichment_joins_only_the_hash_bound_canonical_source(self):
        def fetch(url, **_kwargs):
            if "sparql.dblp.org" in url:
                row = {key: {"value": value} for key, value in {"publ": "https://dblp.org/rec/conf/icml/one",
                    "title": "Robust machinery prediction", "year": "2025", "venue": "https://dblp.org/streams/conf/icml",
                    "doi": "https://doi.org/10.1000/one"}.items()}
                payload = {"results": {"bindings": [row]}}
            else:
                self.assertIn("DOI%3A10.1000%2Fone", url)
                payload = json.loads(self.fetch(url)[0])["data"][0]
            return json.dumps(payload).encode(), url, 200, "application/json"
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = self.project(Path(directory), {"searches": [], "conferences": [{"venue": "conf/icml", "year": 2025, "enrich_limit": 1}]})
            report = intelligence.discover(project, fetcher=fetch)
            self.assertEqual(report["enrichment"][0]["status"], "canonical_match")
            self.assertEqual(len(report["candidates"]), 1)
            self.assertEqual(len(report["candidates"][0]["source_refs"]), 2)
            self.assertTrue(report["candidates"][0]["abstract"])

    def test_explicit_user_feedback_changes_reading_preferences_without_scientific_exclusion(self):
        plan = {"topic_keywords": ["machinery"], "as_of": "2026-10-21", "ranking_weights": {"interest_feedback": 2, "abstract_rhetoric": 0},
                "feedback": [{"candidate_id": "doi:10.1000/one", "interest": "not_interested", "reason": "Outside my current reading priority",
                              "recorded_by": "Researcher", "recorded_at": "2026-10-21T08:00:00+08:00"}]}
        result = intelligence.rank_candidates(intelligence.deduplicate([self.work(doi="10.1000/one")]), plan)[0]
        self.assertFalse(result["reading_candidate"])
        self.assertEqual(result["score_components"]["interest_feedback"], -2)
        self.assertFalse(result["scientific_inclusion_decided"])
        self.assertEqual(plan["feedback"][0]["interest"], "not_interested")
        with self.assertRaisesRegex(ValueError, "finite"):
            intelligence.rank_candidates([], {**plan, "ranking_weights": {"recency": float("nan")}})

    def test_delta_preserves_previous_snapshot_and_records_explicit_preference_change(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}), \
             patch.object(evidence, "utc_now", return_value="2026-10-21T00:00:00+00:00"):
            project = self.project(Path(directory))
            first = intelligence.discover(project, fetcher=self.fetch)
            original = (project / first["history_path"]).read_bytes()
            plan = json.loads((project / intelligence.PLAN).read_text())
            plan["exclude_keywords"] = ["machinery"]
            (project / intelligence.PLAN).write_text(json.dumps(plan), encoding="utf-8")
            second = intelligence.discover(project, fetcher=self.fetch)
            self.assertTrue(second["recommendation_delta"]["preferences_changed"])
            self.assertEqual(second["recommendation_delta"]["changed"], ["doi:10.1000/one"])
            self.assertEqual(second["reading_recommendations"], [])
            self.assertEqual(second["metadata_requests"], 0)
            self.assertEqual((project / first["history_path"]).read_bytes(), original)

    def test_metadata_ceiling_is_cumulative_for_one_plan_even_after_cache_expiry(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = self.project(Path(directory), {"max_requests": 1, "cache_max_age_days": 0})
            with patch.object(evidence, "utc_now", return_value="2026-10-21T00:00:00+00:00"):
                first = intelligence.discover(project, fetcher=self.fetch)
            self.assertEqual(first["metadata_requests_total_for_plan"], 1)
            with patch.object(evidence, "utc_now", return_value="2026-10-29T00:00:00+00:00"), \
                 patch.object(evidence, "execute_search") as call:
                second = intelligence.discover(project)
                call.assert_not_called()
            self.assertEqual(second["metadata_requests"], 0)
            self.assertEqual(second["metadata_requests_total_for_plan"], 1)
            self.assertIn("ceiling", second["errors"][0]["error"])

    def test_implementation_change_invalidates_saved_report_without_refetching_metadata(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}), \
             patch.object(evidence, "utc_now", return_value="2026-10-21T00:00:00+00:00"):
            project = self.project(Path(directory))
            first = intelligence.discover(project, fetcher=self.fetch)
            actual_sha = intelligence.sha
            def changed_implementation(path):
                return "f" * 64 if path == Path(intelligence.__file__) else actual_sha(path)
            with patch.object(intelligence, "sha", side_effect=changed_implementation), \
                 patch.object(evidence, "execute_search") as call:
                second = intelligence.discover(project)
                call.assert_not_called()
            self.assertTrue(second["changed"])
            self.assertEqual(second["implementation_sha256"], "f" * 64)
            self.assertNotEqual(first["input_fingerprint"], second["input_fingerprint"])

    def test_failed_provider_is_not_retried_by_the_next_stage_during_cooldown(self):
        def unavailable(*_args, **_kwargs):
            raise OSError("provider unavailable")
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}), \
             patch.object(evidence, "utc_now", return_value="2026-10-21T00:00:00+00:00"):
            project = self.project(Path(directory))
            first = intelligence.discover(project, fetcher=unavailable)
            self.assertEqual(first["metadata_requests"], 1)
            with patch.object(evidence, "execute_search") as call:
                second = intelligence.discover(project)
                call.assert_not_called()
            self.assertEqual(second["metadata_requests"], 0)
            self.assertIn("cooldown", second["errors"][0]["error"])
            self.assertEqual(second["metadata_requests_total_for_plan"], 1)


if __name__ == "__main__":
    unittest.main()
