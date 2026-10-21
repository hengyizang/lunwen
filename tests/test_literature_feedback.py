from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import literature_feedback as feedback
from scripts import literature_intelligence as intelligence
from scripts.research_artifacts import read, sha, write


class LiteratureFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cloud = patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"})
        self.cloud.start()
        self.addCleanup(self.cloud.stop)
        self.project = Path(self.temp.name) / "project"
        (self.project / "program").mkdir(parents=True)
        self.plan = {"schema_version": "1.0", "doctoral_question": "How can machinery predictions remain robust?",
                     "topic_keywords": ["machinery"], "exclude_keywords": ["clinical"], "max_requests": 1,
                     "as_of": "2026-10-21", "searches": [{"provider": "semantic-scholar", "query": "machinery"}]}
        write(self.project / intelligence.PLAN, self.plan)
        def fetch(url, **_kwargs):
            value = {"data": [{"paperId": name, "title": f"Machinery prediction {name}", "year": 2025,
                                "authors": [{"name": "Alice Researcher"}], "externalIds": {"DOI": "10.1000/" + name},
                                "abstract": "We propose a method. However, transfer remains challenging."}
                               for name in ("one", "two")]}
            return json.dumps(value).encode(), url, 200, "application/json"
        self.report = intelligence.discover(self.project, fetcher=fetch)
        self.leads_hash = sha(self.project / intelligence.OUTPUT)
        self.plan_hash = sha(self.project / intelligence.PLAN)
        self.note = self.project / "literature/notes/transfer.md"
        self.note.parent.mkdir(parents=True)
        self.note.write_text("A method used a distinct baseline.\nTransfer conditions need a matching data split.\n", encoding="utf-8")

    def binding(self):
        return {"path": "literature/notes/transfer.md", "sha256": sha(self.note), "locator": "baseline and transfer conditions",
                "start_line": 1, "end_line": 2, "quote": self.note.read_text().strip()}

    def event(self, identifier="feedback-one", **changes):
        candidate = self.report["candidates"][0]
        return {"event_id": identifier, "candidate_id": candidate["canonical_id"],
                "candidate_sha256": feedback.digest(candidate), "sources_sha256": feedback.digest(candidate["source_refs"]),
                "recorded_by": "Researcher", "recorded_at": "2020-01-01T08:00:00+08:00",
                "reason": "Located evidence supports this reading outcome; scientific support still needs review.",
                "outcomes": {"relevance": "relevant", "duplicates": "distinct", "source_accessibility": "accessible",
                             "evidence_sufficiency": "partial", "experiment_utility": "promising"},
                "evidence": [self.binding()], "suggested_keywords": ["distribution shift"], "paper_ids": ["P01"], **changes}

    def record(self, event=None):
        return feedback.record_feedback(self.project, event or self.event(), expected_leads_sha256=self.leads_hash)

    def proposal(self, **kwargs):
        return feedback.propose(self.project, event_ids=["feedback-one"], expected_plan_sha256=self.plan_hash, **kwargs)

    def review_args(self, proposed, **changes):
        path = self.project / feedback.ROOT / "proposals" / (proposed["proposal_id"] + ".json")
        return {"expected_proposal_sha256": sha(path), "expected_plan_sha256": self.plan_hash,
                "decision": "adopt", "reviewed_by": "Owner", "reason": "Reviewed exact sources and bounded discovery changes.",
                "authorization": "human", "owner_authorization": {"actor": "Owner", "source_issue_id": 123,
                    "request_sha256": "a" * 64}, **changes}

    def test_event_is_source_bound_and_idempotent_without_scientific_approval(self):
        first = self.record()
        second = self.record()
        self.assertEqual(first, second)
        self.assertFalse(first["scientific_inclusion_decided"])
        self.assertFalse(first["claim_support_verified"])
        self.assertFalse(first["gate_approved"])
        self.assertEqual(first["paid_model_calls"], 0)
        self.assertEqual(first["plan"]["sha256"], self.plan_hash)
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.record(self.event(reason="Changed observation under an existing event ID"))

    def test_all_five_dimensions_and_timezone_are_explicit(self):
        event = self.event()
        event["outcomes"].pop("experiment_utility")
        with self.assertRaisesRegex(ValueError, "all five"):
            self.record(event)
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.record(self.event(recorded_at="2020-01-01T00:00:00"))
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.record(self.event(recorded_at="2999-01-01T00:00:00Z"))

    def test_stale_candidate_report_and_source_hashes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "candidate"):
            self.record(self.event(candidate_sha256="f" * 64))
        with self.assertRaisesRegex(ValueError, "source bindings"):
            self.record(self.event(sources_sha256="f" * 64))
        candidate = self.report["candidates"][0]
        source = self.project / candidate["source_refs"][0]["raw_response_path"]
        source.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale candidate source"):
            self.record()

    def test_source_evidence_requires_exact_quote_lines_for_observed_outcomes(self):
        with self.assertRaisesRegex(ValueError, "source-bound evidence"):
            self.record(self.event(evidence=[]))
        fabricated = {**self.binding(), "quote": "An unsupported result"}
        with self.assertRaisesRegex(ValueError, "exact current quote"):
            self.record(self.event(evidence=[fabricated]))
        with self.assertRaisesRegex(ValueError, "research artifact"):
            self.record(self.event(evidence=[{**self.binding(), "path": "state/data-authorizations.json"}]))
        with self.assertRaisesRegex(ValueError, "exact current quote"):
            no_quote = {key: value for key, value in self.binding().items() if key != "quote"}
            self.record(self.event(evidence=[no_quote]))

    def test_duplicate_observation_retains_both_source_bindings(self):
        event = self.event()
        event["outcomes"]["duplicates"] = "version"
        with self.assertRaisesRegex(ValueError, "distinct current related"):
            self.record(event)
        event["related_candidate_id"] = self.report["candidates"][1]["canonical_id"]
        saved = self.record(event)
        self.assertEqual(saved["related_candidate"]["candidate_sha256"], feedback.digest(self.report["candidates"][1]))
        self.assertFalse(saved["scientific_inclusion_decided"])

    def test_actual_experiment_use_requires_registered_receipt_and_current_outputs(self):
        event = self.event()
        event["outcomes"]["experiment_utility"] = "used"
        with self.assertRaisesRegex(ValueError, "actual successful executor"):
            self.record(event)
        output = self.project / "experiments/results/value.json"
        write(output, {"observed_fixture": 1})
        receipt = {"attempt_id": "fixture-attempt", "run_id": "fixture-run", "paper_id": "P01", "status": "succeeded",
                   "input_integrity": {"passed": True}, "approved_plan_sha256": "c" * 64,
                   "outputs": [{"path": "experiments/results/value.json", "sha256": sha(output)}]}
        receipt_path = self.project / "experiments/runs/fixture-attempt/run.json"
        write(receipt_path, receipt)
        (self.project / "experiments/registry.jsonl").write_text(json.dumps(receipt) + "\n", encoding="utf-8")
        excerpt = {"path": "experiments/runs/fixture-attempt/run.json", "sha256": sha(receipt_path), "locator": "successful fixture executor record",
                   "start_line": 1, "end_line": len(receipt_path.read_text().splitlines()), "quote": receipt_path.read_text().strip()}
        event["evidence"].append(excerpt)
        saved = self.record(event)
        self.assertEqual(saved["outcomes"]["experiment_utility"], "used")
        self.assertFalse(saved["claim_support_verified"])
        proposed = self.proposal()
        write(output, {"tampered": 2})
        with self.assertRaisesRegex(ValueError, "output is missing or stale"):
            feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed))

    def test_proposal_records_before_after_scope_and_operational_followups_without_edit(self):
        event = self.event()
        event["outcomes"].update(relevance="irrelevant", source_accessibility="blocked", experiment_utility="not_useful")
        self.record(event)
        before_bytes = (self.project / intelligence.PLAN).read_bytes()
        proposed = self.proposal()
        self.assertEqual((self.project / intelligence.PLAN).read_bytes(), before_bytes)
        self.assertEqual(proposed["before"]["ranking_weights"]["topic_relevance"], 6)
        self.assertEqual(proposed["after"]["ranking_weights"]["topic_relevance"], 6.5)
        self.assertEqual(proposed["after"]["ranking_weights"]["abstract_rhetoric"], 0.75)
        self.assertEqual(proposed["after"]["topic_keywords"], ["machinery"])
        self.assertEqual(proposed["impacted_scope"]["paper_ids"], ["P01"])
        self.assertFalse(proposed["impacted_scope"]["doctoral_question_changed"])
        self.assertFalse(proposed["gate_approved"])
        self.assertEqual(proposed, self.proposal())
        self.assertIn("review_authorized_alternative_source", {row["action"] for row in proposed["operational_suggestions"]})
        self.assertIn("retrieve_fulltext_and_adjacent_counterevidence", {row["action"] for row in proposed["operational_suggestions"]})

    def test_external_proposal_cannot_alter_topic_exclusions_searches_or_budget(self):
        self.record()
        for name, value in (("doctoral_question", "A different question"), ("exclude_keywords", ["contrary"]),
                            ("max_requests", 20), ("searches", [])):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "only add keywords"):
                self.proposal(proposal={name: value})
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.proposal(proposal={"rationale": "A suggested retrieval improvement"})
        with self.assertRaisesRegex(ValueError, "finite"):
            self.proposal(proposal={"rationale": "A suggested retrieval improvement", "provenance": [self.binding()],
                                   "ranking_weights": {"recency": float("nan")}})
        proposed = self.proposal(proposal={"rationale": "Add a located mechanism term", "provenance": [self.binding()],
                                         "topic_keywords_add": ["distribution shift"], "ranking_weights": {"recency": 0.5}})
        self.assertEqual(proposed["origin"]["kind"], "validated_external_read_only_suggestion")
        self.assertFalse(proposed["automatic_adoption"])

    def test_adoption_requires_owner_review_and_preserves_all_other_plan_controls(self):
        self.record()
        proposed = self.proposal()
        with self.assertRaisesRegex(ValueError, "authenticated owner"):
            feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed, owner_authorization=None))
        result = feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed))
        updated = read(self.project / intelligence.PLAN)
        for name in ("doctoral_question", "exclude_keywords", "max_requests", "searches"):
            self.assertEqual(updated[name], self.plan[name])
        self.assertIn("distribution shift", updated["topic_keywords"])
        self.assertTrue(result["applied"])
        self.assertFalse(result["gate_approved"])
        self.assertFalse(result["budget_authorized"])
        self.assertEqual(result["plan_before"], self.plan)
        again = feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed))
        self.assertTrue(again["replayed"])
        self.assertEqual(again["plan_sha256_after"], result["plan_sha256_after"])

    def test_stale_plan_and_changed_evidence_block_adoption(self):
        self.record()
        proposed = self.proposal()
        write(self.project / intelligence.PLAN, {**self.plan, "max_requests": 0})
        with self.assertRaisesRegex(ValueError, "stale literature plan"):
            feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed))
        write(self.project / intelligence.PLAN, self.plan)
        self.note.write_text("Changed evidence", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "current hash"):
            feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed))
        self.assertEqual(read(self.project / intelligence.PLAN), self.plan)

    def test_rejected_proposal_preserves_plan_and_cannot_change_its_decision(self):
        self.record()
        proposed = self.proposal()
        result = feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed, decision="reject"))
        self.assertFalse(result["applied"])
        self.assertEqual(read(self.project / intelligence.PLAN), self.plan)
        with self.assertRaisesRegex(ValueError, "different immutable review"):
            feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed))

    def test_adopted_noop_batch_cannot_be_learned_twice(self):
        event = self.event(suggested_keywords=[])
        event["outcomes"]["evidence_sufficiency"] = "sufficient"
        self.record(event)
        proposed = self.proposal()
        self.assertFalse(proposed["configuration_changes"])
        feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed))
        with self.assertRaisesRegex(ValueError, "already adopted"):
            self.proposal()

    def test_interrupted_write_is_recoverable_from_same_immutable_owner_decision(self):
        self.record()
        proposed = self.proposal()
        actual_write = feedback.write
        def interrupted(path, value):
            if path == self.project / intelligence.PLAN:
                raise OSError("interrupted before atomic plan replace")
            return actual_write(path, value)
        with patch.object(feedback, "write", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "interrupted"):
                feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed))
        self.assertEqual(read(self.project / intelligence.PLAN), self.plan)
        recovered = feedback.review(self.project, proposed["proposal_id"], **self.review_args(proposed))
        self.assertTrue(recovered["recovered"])
        self.assertIn("distribution shift", read(self.project / intelligence.PLAN)["topic_keywords"])

    def test_local_execution_and_arbitrary_event_fields_are_rejected(self):
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "false", "DR_OS_CLOUD_EXECUTOR": "0"}):
            with self.assertRaisesRegex(RuntimeError, "cloud executor"):
                self.record()
        with self.assertRaisesRegex(ValueError, "unknown feedback"):
            self.record(self.event(gate_approved=True))


if __name__ == "__main__":
    unittest.main()
