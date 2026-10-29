"""Cloud software fixtures, never scientific saturation or independent review."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import literature_evidence as evidence
from scripts import literature_reading as reading
from scripts import literature_reasoning as reasoning
from scripts import literature_workbench as wb
from scripts import research_frontier as frontier
from scripts.research_artifacts import read, sha, write


class ResearchFrontierTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        environment = patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"})
        environment.start()
        self.addCleanup(environment.stop)
        source = self.project / "evidence/sources/a.md"
        source.parent.mkdir(parents=True)
        source.write_text("# Abstract\nCalibration may transfer.\n# Methods\nWhole devices are held out.\n"
                          "# Results\nThe transfer fails under drift.\n", encoding="utf-8")
        self.source = {"path": "evidence/sources/a.md", "sha256": sha(source)}
        write(self.project / wb.CONFIG, {"schema_version": "1.0", "papers": [
            {"id": "a", "title": "Synthetic source A", "source": self.source}]})
        wb.build(self.project)
        self.question = {"id": "Q1", "question": "Does calibration transfer?", "evidence": [
            {"id": "E1", "stance": "contradicts", "read_scope": "fulltext",
             "observation": "The synthetic source reports drift failure.",
             "source": {**self.source, "locator": "Results, line 6"}}],
            "decisions": [{"id": "D1", "phase": "planned", "decision": "Audit transportability",
                "rationale": "AUTHOR_PREFERRED_RATIONALE", "evidence_ids": ["E1"],
                "failure_condition": "Failure under a shift", "stop_rule": "Review before experiments"}],
            "missing_evidence": ["Independent contrary comparison"]}
        write(self.project / frontier.NOTEBOOK, {"questions": [self.question]})
        write(self.project / frontier.HYPOTHESES, {"hypotheses": [{"hypothesis_id": "H1"}]})
        self.request = {"schema_version": "1.0", "kind": "research_frontier", "id": "frontier-fixture",
            "questions": [{"question_id": "Q1", "paper_ids": ["a"], "dimensions": ["methods", "results", "appendix"],
                "hypothesis_ids": ["H1"]}], "query_rounds": [], "relations": [], "max_actions": 2}
        self.coverage()

    def coverage(self):
        scope = self.request["questions"][0]
        report = reading.coverage(self.project, {"question": self.question["question"],
            "paper_ids": scope["paper_ids"], "dimensions": scope["dimensions"]})
        scope["coverage"] = {"path": report["report_path"], "sha256": sha(self.project / report["report_path"])}
        self.save()
        return report

    def save(self):
        write(self.project / frontier.DEFAULT, self.request)

    def search(self, query="calibration transfer", dois=("10.1000/one",)):
        def fetch(url, **_kwargs):
            data = [{"paperId": str(i), "title": "Synthetic machinery paper " + doi,
                "year": 2025, "authors": [{"name": "Fixture Author"}],
                "externalIds": {"DOI": doi}} for i, doi in enumerate(dois)]
            return json.dumps({"data": data}).encode(), url, 200, "application/json"
        return evidence.execute_search(self.project, "semantic-scholar", query,
            query_family="counterevidence", date_range="all years", filters="none", limit=10, fetcher=fetch)

    def round(self, identity, receipts, **extra):
        self.request["query_rounds"].append({"id": identity, "question_id": "Q1", "dimension": "results",
            "receipt_ids": [r["receipt_id"] for r in receipts], **extra})
        self.save()

    def relation(self, kind="supersedes"):
        self.request["relations"] = [{"id": "relation-a", "kind": kind,
            "from": {"question_id": "Q1", "kind": "evidence", "id": "E1"},
            "to": {"question_id": "Q1", "kind": "decision", "id": "D1"},
            "reason": "RELATION_AUTHOR_PREFERENCE", "applicability": "Only this explicitly located fixture"}]
        self.save()

    def test_native_coverage_creates_bounded_gap_linked_worklist_preserving_contrary(self):
        with patch.object(evidence, "execute_search", side_effect=AssertionError("must not search")):
            report = frontier.refresh(self.project)
        self.assertEqual(report["paid_calls"], 0)
        self.assertEqual(report["network_calls"], 0)
        self.assertEqual(len(report["worklist"]), 2)
        self.assertGreater(report["deferred_action_count"], 0)
        first = report["worklist"][0]
        self.assertEqual(first["kind"], "compare_contrary_evidence")
        self.assertEqual(first["evidence_id"], "E1")
        self.assertEqual(first["hypothesis_ids"], ["H1"])
        self.assertTrue(first["gap_id"])
        self.assertFalse(report["scientific_completion_verified"])
        self.assertEqual(report["questions"][0]["notebook"]["evidence"][0]["source"]["sha256"], self.source["sha256"])

    def test_immutable_reuse_context_is_read_only_and_critic_omits_author_proposals(self):
        self.relation()
        self.request["proposed_queries"] = [{"question_id": "Q1", "dimension": "results",
            "query": "PREFERRED_PROPOSED_QUERY", "reason": "PREFERRED_QUERY_REASON"}]
        self.save()
        first = frontier.refresh(self.project)
        before = {p.relative_to(self.project).as_posix(): p.read_bytes()
                  for p in self.project.rglob("*") if p.is_file()}
        second = frontier.refresh(self.project)
        self.assertFalse(second["changed"])
        self.assertEqual(first["report_path"], second["report_path"])
        critic = frontier.model_context(self.project, first["report_path"], "critic")
        writer = frontier.model_context(self.project, first["report_path"], "writer")
        self.assertTrue(writer["relations"])
        self.assertTrue(writer["proposed_queries"])
        text = json.dumps(critic)
        for forbidden in ("PREFERRED_PROPOSED_QUERY", "PREFERRED_QUERY_REASON", "AUTHOR_PREFERRED_RATIONALE",
                          "RELATION_AUTHOR_PREFERENCE", '"relations"', '"worklist"', '"next_action"'):
            self.assertNotIn(forbidden, text)
        after = {p.relative_to(self.project).as_posix(): p.read_bytes()
                 for p in self.project.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_actual_receipts_canonical_dedup_and_new_paper_yield(self):
        first = self.search(dois=("10.1000/one", "10.1000/ONE"))
        # The native provider normalizer already joins duplicate stable DOI IDs.
        # Frontier observation counts must use its sealed normalized receipt,
        # while canonical dedup also joins the same paper across actual calls.
        raw = read(self.project / first["raw_response_path"])
        normalized = read(self.project / first["normalized_results_path"])
        self.assertEqual(len(raw["data"]), 2)
        self.assertEqual(len(normalized["works"]), 1)
        self.assertEqual(first["result_count"], len(normalized["works"]))
        self.assertEqual(normalized["works"][0]["id"], "doi:10.1000/one")
        duplicate = self.search("independent repeated metadata", ("10.1000/one",))
        second = self.search("calibration adverse transfer", ("10.1000/one", "10.1000/two"))
        self.round("round-one", [first, duplicate])
        self.round("round-two", [second])
        self.round("round-cache", [second])
        report = frontier.refresh(self.project)
        one, two, cache = report["query_rounds"]
        self.assertEqual(one["normalized_observation_count"], first["result_count"] + duplicate["result_count"])
        self.assertEqual((one["normalized_observation_count"], one["canonical_paper_count"], one["new_paper_count"]), (2, 1, 1))
        self.assertEqual(two["new_canonical_ids"], ["doi:10.1000/two"])
        self.assertEqual(cache["new_paper_count"], 0)
        self.assertEqual(cache["advice"], "stop_repeating_cached_round")
        self.assertFalse(cache["scientific_saturation_verified"])
        self.assertFalse(cache["absence_of_evidence_proven"])

    def test_prior_native_receipts_and_failed_attempts_remain_visible(self):
        self.search(dois=("10.1000/one",))
        current = self.search("narrowed query", ("10.1000/one",))
        self.round("round-narrow", [current])
        failed = {"receipt_id": "fixture-failed", "status": "failed", "provider": "semantic-scholar",
                  "query": "failure query", "error": "Synthetic provider failure"}
        with (self.project / frontier.LEDGER).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(failed) + "\n")
        self.round("round-failed", [failed])
        self.request["proposed_queries"] = [{"question_id": "Q1", "dimension": "results",
            "query": "failure query", "reason": "Inspect the existing failure before any retry"}]
        self.save()
        report = frontier.refresh(self.project)
        self.assertEqual(report["query_rounds"][0]["new_paper_count"], 0)
        self.assertEqual(report["query_rounds"][0]["advice"], "reword_or_extend_source_scope")
        self.assertEqual(report["query_rounds"][1]["failed_attempt_count"], 1)
        self.assertEqual(report["query_rounds"][1]["advice"], "resolve_failed_attempts")
        self.assertEqual(report["proposed_queries"][0]["existing_attempt_ids"], ["fixture-failed"])
        self.assertFalse(report["proposed_queries"][0]["executed"])

    def test_noncontiguous_round_does_not_claim_an_intervening_native_discovery(self):
        first = self.search("first empty query", ())
        self.search("other native discovery", ("10.1000/intervening",))
        last = self.search("last duplicate query", ("10.1000/intervening",))
        self.round("noncontiguous", [first, last])
        report = frontier.refresh(self.project)
        self.assertEqual(report["query_rounds"][0]["canonical_paper_count"], 1)
        self.assertEqual(report["query_rounds"][0]["new_paper_count"], 0)

    def test_dimension_yield_requires_actual_current_answer_and_remains_attributed(self):
        receipt = self.search()
        self.round("round-one", [receipt], evidence_ids=["E1"])
        report = frontier.refresh(self.project)
        self.assertEqual(report["query_rounds"][0]["new_attributed_evidence_dimension_count"], 0)
        plan = reasoning.itinerary(self.project, self.question["question"])
        step = next(row for row in plan["steps"] if row["phase"] == "challenge")
        reasoning.record_progress(self.project, {"step_id": step["id"], "expected_step_sha256": step["step_sha256"],
            "answer": "The fixture reports a drift failure.", "outcome": "contradicts",
            "evidence": [{"paper_id": "a", **self.source, "start_line": 6, "end_line": 6,
                "quote": "The transfer fails under drift."}], "kind": "human_interpretation",
            "recorded_by": "Synthetic software fixture", "recorded_at": "2026-10-28T00:00:00+00:00",
            "inference_boundary": "Fixture only; no scientific endorsement"})
        self.coverage()
        report = frontier.refresh(self.project)
        actual = report["query_rounds"][0]
        self.assertEqual(actual["source_matched_dimension_evidence_ids"], ["E1"])
        self.assertFalse(actual["notebook_locator_overlap_verified"])
        self.assertEqual(actual["new_attributed_evidence_dimension_count"], 1)
        self.assertEqual(actual["evidence_round_association"], "declared_pending_semantic_review")
        self.assertFalse(report["semantic_support_verified"])

    def test_relations_reference_actual_notebook_records_and_never_replace_them(self):
        original = (self.project / frontier.NOTEBOOK).read_bytes()
        for kind in ("supersedes", "complements", "contradicts"):
            self.relation(kind)
            report = frontier.refresh(self.project)
            relation = report["relations"][0]
            self.assertFalse(relation["automatic_truth_or_supersession"])
            self.assertEqual(relation["to"]["source_evidence_ids"], ["E1"])
            self.assertTrue(relation["originals_retained"])
        self.assertEqual(original, (self.project / frontier.NOTEBOOK).read_bytes())
        self.request["relations"][0]["to"]["id"] = "invented-decision"
        self.save()
        with self.assertRaisesRegex(ValueError, "unknown notebook"):
            frontier.refresh(self.project)

    def test_sources_request_coverage_and_report_provenance_are_revalidated(self):
        report = frontier.refresh(self.project)
        self.request["max_actions"] = 3
        self.save()
        with self.assertRaisesRegex(ValueError, "stale or changed"):
            frontier.model_context(self.project, report["report_path"], "critic")
        new = frontier.refresh(self.project)
        self.assertNotEqual(report["report_path"], new["report_path"])
        target = self.project / new["report_path"]
        target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "provenance"):
            frontier.refresh(self.project)
        (self.project / self.source["path"]).write_text("Changed original.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "notebook is blocked"):
            frontier.refresh(self.project)

    def test_missing_current_progress_and_module_changes_block_context(self):
        report = frontier.refresh(self.project)
        write(self.project / reasoning.PROGRESS, {"schema_version": "1.0", "events": []})
        with self.assertRaisesRegex(ValueError, "progress changed"):
            frontier.model_context(self.project, report["report_path"], "writer")
        self.coverage()
        report = frontier.refresh(self.project)
        real = frontier.sha
        with patch.object(frontier, "sha", side_effect=lambda p: "0" * 64 if Path(p) == Path(frontier.__file__) else real(p)):
            with self.assertRaisesRegex(ValueError, "stale or changed"):
                frontier.model_context(self.project, report["report_path"], "critic")

    def test_unknown_receipts_raw_bytes_and_normalized_counts_cannot_be_claimed(self):
        self.request["query_rounds"] = [{"id": "unexecuted", "question_id": "Q1", "dimension": "results",
                                        "receipt_ids": ["invented-receipt"]}]
        self.save()
        with self.assertRaisesRegex(ValueError, "unexecuted or unknown"):
            frontier.refresh(self.project)
        self.request["query_rounds"] = []
        receipt = self.search()
        self.round("round-real", [receipt])
        raw_path = self.project / receipt["raw_response_path"]
        original_raw = raw_path.read_bytes()
        raw_path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "stale literature receipt"):
            frontier.refresh(self.project)
        raw_path.write_bytes(original_raw)
        ledger_path = self.project / frontier.LEDGER
        ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        ledger[0]["result_count"] += 1
        ledger_path.write_text("".join(json.dumps(row) + "\n" for row in ledger), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "result count differs from its source"):
            frontier.refresh(self.project)

    def test_coverage_wrong_question_and_undeclared_hypotheses_are_rejected(self):
        self.request["questions"][0]["hypothesis_ids"] = ["unknown-hypothesis"]
        self.save()
        with self.assertRaisesRegex(ValueError, "hypothesis IDs"):
            frontier.refresh(self.project)
        self.request["questions"][0]["hypothesis_ids"] = ["H1"]
        self.question["question"] = "A different actual notebook question?"
        write(self.project / frontier.NOTEBOOK, {"questions": [self.question]})
        self.save()
        with self.assertRaisesRegex(ValueError, "coverage question"):
            frontier.refresh(self.project)

    def test_cloud_only_and_strict_request_boundary(self):
        with patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(ValueError, "cloud runner"):
                frontier.refresh(self.project)
        self.request["execute"] = True
        self.save()
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            frontier.refresh(self.project)
        self.request.pop("execute")
        self.request["kind"] = "run_search"
        self.save()
        with self.assertRaisesRegex(ValueError, "kind research_frontier"):
            frontier.refresh(self.project)
