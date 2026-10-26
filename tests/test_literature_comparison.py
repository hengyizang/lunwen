"""Cloud-only paired reading regressions; model fixtures are not quality evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import literature_comparison as comparison, literature_workbench as wb
from scripts import source_scope, review_packets
from scripts.ai_providers import ModelResult
from scripts.research_artifacts import read, sha, write


class LiteratureComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.config = {"schema_version": "1.0", "papers": []}
        self.add("a", "# Methods\nThe sample contains 120 adults.\nThe treatment failed under drift.\n")
        self.build()

    def add(self, name, text):
        target = self.project / ("evidence/sources/" + name + ".md")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        source = {"path": target.relative_to(self.project).as_posix(), "sha256": sha(target)}
        paper = {"id": name, "title": "Source " + name, "topic_id": "trial", "paper_ids": ["P01"],
            "source": source, "source_scope": "full_text"}
        self.config["papers"].append(paper)
        source_scope.record(self.project, source["path"], "full_text", "Synthetic fixture scope, not a real human approval")
        return paper

    def build(self):
        write(self.project / wb.CONFIG, self.config)
        wb.build(self.project)

    def case(self, name="case-a", paper="a", **options):
        p = next(p for p in self.config["papers"] if p["id"] == paper)
        return {"id": name, "request": {"schema_version": "1.0", "question": "What does the sample contain?",
            "paper_ids": [paper], "limit": 8}, "expected_abstain": False,
            "relevant": [{"paper_id": paper, **p["source"], "start_line": 2, "end_line": 2,
                "quote": "The sample contains 120 adults."}], **options}

    def spec(self, **options):
        return {"schema_version": "1.0", "id": "comparison-a", "annotation": {
            "kind": "synthetic_fixture", "by": "Synthetic software regression"},
            "cases": [self.case()], **options}

    def request(self, spec=None):
        relative = "program/literature-comparison.json"
        write(self.project / relative, spec or self.spec())
        return relative

    def fake_call(self, **options):
        """Return a labelled fixture and actual test ledger rows, never a gateway."""
        def call(project, **kwargs):
            blocks = json.loads(kwargs["prompt"].split("\nSOURCE_BLOCKS:\n", 1)[1])
            selected = next(b for b in blocks if "120 adults" in b["text"])
            response = {"answer": "The sample contains 120 adults.", "abstain": False,
                "statements": [{"text": "The sample contains 120 adults.", "citation_indices": [0]}],
                "citations": [{"source_id": selected["source_id"], "locator": selected["locator"],
                    "quote": "The sample contains 120 adults."}]}
            response = options.get("response", response)
            ledger = project / "state/model-usage.jsonl"
            ledger.parent.mkdir(parents=True, exist_ok=True)
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"run_id": kwargs["run_id"], "cost_cny": 0.01,
                    "cost_status": options.get("cost_status", "settled_usage_receipt"),
                    "input_tokens": 300, "output_tokens": 50}) + "\n")
            return ModelResult(provider="fixture-openai", model="fixture-reader", reported_model="fixture-reader",
                text=json.dumps(response), usage={"input_tokens": 300, "output_tokens": 50},
                request_id="fixture-request", completion_status="completed")
        return call

    def execute(self, spec=None, fake=None):
        request = self.request(spec)
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), \
                patch.object(comparison.model_runtime, "call", side_effect=fake or self.fake_call()) as call:
            result = comparison.refresh(self.project, request, execute=True)
        return result, call

    def test_preparation_is_free_complete_original_and_no_model_calls(self):
        with patch.object(comparison.model_runtime, "call", side_effect=AssertionError("no paid call")):
            result = comparison.refresh(self.project, self.request())
        self.assertEqual(result["status"], "prepared_no_model_calls")
        case = result["cases"][0]
        self.assertTrue(case["same_original_corpus"])
        self.assertEqual(case["routes"]["full_text"]["coverage"]["anchor_recall"], 1)
        self.assertFalse(case["routes"]["full_text"]["truncated"])
        self.assertFalse(result["labels_are_independent_scientific_review"])
        self.assertEqual(comparison.validate_saved_report(self.project)["status"], "current")

    def test_writable_full_text_label_cannot_replace_protected_scope(self):
        for path in (self.project / "evidence/source-scopes").glob("*.json"):
            path.unlink()
        with self.assertRaisesRegex(ValueError, "protected original full-text scope"):
            comparison.prepare(self.project, self.spec())

    def test_full_text_never_silently_truncates_or_automatically_chunks(self):
        self.add("long", "# Methods\nThe sample contains 120 adults.\n" + "An irrelevant detail is retained.\n" * 60)
        self.build()
        with self.assertRaisesRegex(ValueError, "no truncation"):
            comparison.prepare(self.project, self.spec(cases=[self.case(paper="long")], max_full_text_chars=1000))

    def test_same_context_reuses_one_call_and_preserves_cumulative_actual_cost(self):
        result, call = self.execute()
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["status"], "completed_awaiting_independent_semantic_review")
        self.assertEqual(result["routes"][1]["reused_identical_context"]["route"], "retrieval")
        self.assertFalse(result["routes"][1]["model_call_made"])
        self.assertEqual(result["costs"]["known_model_cost_cny"], 0.01)
        self.assertFalse(result["semantic_quality_validated"])
        self.assertFalse(result["costs"]["scope_confirmed_by_owner_record"])
        with patch.object(comparison.model_runtime, "call", side_effect=AssertionError("no duplicate")):
            replay = comparison.refresh(self.project, execute=True)
        self.assertTrue(replay["reused"])

    def test_two_arms_actually_call_when_whole_text_contains_omitted_blocks(self):
        p = self.config["papers"][0]
        source = self.project / p["source"]["path"]
        source.write_text("# Methods\nThe sample contains 120 adults.\n" + "Unrelated recorded details.\n" * 70, encoding="utf-8")
        p["source"]["sha256"] = sha(source)
        source_scope.record(self.project, p["source"]["path"], "full_text", "Synthetic scope fixture")
        self.build()
        result, call = self.execute()
        self.assertEqual(call.call_count, 2)
        self.assertLess(result["routes"][0]["source_chars"], result["routes"][1]["source_chars"])
        self.assertEqual(result["costs"]["known_model_cost_cny"], 0.02)
        self.assertTrue(all(k.kwargs["role"] == "reader-qa" for k in call.call_args_list))

    def test_gold_labels_and_route_names_never_enter_model_prompt(self):
        _, call = self.execute()
        prompt = call.call_args.kwargs["prompt"]
        self.assertNotIn("expected_abstain", prompt)
        self.assertNotIn("anchor_recall", prompt)
        self.assertNotIn("synthetic_fixture", prompt)
        self.assertNotIn("full_text", prompt)

    def test_bad_citations_are_preserved_and_stop_remaining_paid_arms(self):
        invalid = {"answer": "Invented answer.", "abstain": False, "citations": [], "statements": []}
        result, call = self.execute(fake=self.fake_call(response=invalid))
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["status"], "stopped_preserved_attempts")
        self.assertEqual(result["routes"][0]["status"], "model_response_rejected_do_not_use")
        self.assertNotIn("response", result["routes"][0])
        self.assertEqual(len(result["pending_routes"]), 1)
        self.assertEqual(result["costs"]["known_model_cost_cny"], 0.01)

    def test_unknown_charge_stops_new_paid_arms(self):
        result, call = self.execute(fake=self.fake_call(cost_status="unknown_reconcile_required"))
        self.assertEqual(call.call_count, 1)
        self.assertIn("reconcile", result["stop_reason"])
        self.assertFalse(result["costs"]["model_cost_coverage_complete"])

    def test_transport_failure_keeps_receipt_and_does_not_retry(self):
        result, call = self.execute(fake=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fixture gateway failure")))
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["routes"][0]["status"], "execution_failed_do_not_retry")
        self.assertFalse(result["costs"]["model_cost_coverage_complete"])
        self.assertEqual(result["routes"][0]["failure_type"], "RuntimeError")

    def test_execution_requires_cloud_and_explicit_boolean(self):
        request = self.request()
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "DR_OS_CLOUD_EXECUTOR": "0"}), \
                patch.object(comparison.model_runtime, "call") as call:
            with self.assertRaisesRegex(ValueError, "authorized cloud runner"):
                comparison.refresh(self.project, request, execute=True)
            call.assert_not_called()
        with self.assertRaisesRegex(ValueError, "explicit boolean"):
            comparison.refresh(self.project, request, execute="true")

    def test_forged_label_and_duplicate_label_are_rejected(self):
        spec = self.spec()
        spec["cases"][0]["relevant"][0]["quote"] = "Invented value."
        with self.assertRaisesRegex(ValueError, "quote"):
            comparison.prepare(self.project, spec)
        spec = self.spec()
        spec["cases"][0]["relevant"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicate anchor"):
            comparison.prepare(self.project, spec)

    def test_review_incompatible_identifiers_are_rejected_before_any_call(self):
        for value in ("UpperCase", "a" * 65, "../escape"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "lower-case identifier"):
                comparison.prepare(self.project, self.spec(id=value))

    def test_question_scope_and_original_bytes_cannot_drift_after_plan(self):
        request = self.request()
        comparison.refresh(self.project, request)
        spec = read(self.project / request)
        spec["cases"][0]["request"]["question"] = "How many adults?"
        write(self.project / request, spec)
        with self.assertRaisesRegex(ValueError, "new ID"):
            comparison.refresh(self.project, request)

    def test_saved_output_tamper_and_unregistered_file_are_rejected(self):
        result, _ = self.execute()
        directory = (self.project / result["report_path"]).parent
        unexpected = directory / "untracked.txt"
        unexpected.write_text("Not part of the original execution.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inventory"):
            comparison.validate_saved_report(self.project)
        unexpected.unlink()
        target = directory / "review/case-a-candidate-1.txt"
        target.write_text("An edited answer.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            comparison.validate_saved_report(self.project)

    def test_interrupted_execution_intent_prevents_automatic_retry(self):
        request = self.request()
        comparison.refresh(self.project, request)
        target = self.project / comparison.OUTPUT / "comparison-a/routes/case-a-retrieval.json"
        comparison._write(self.project, target, {"status": "started"})
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), \
                patch.object(comparison.model_runtime, "call") as call:
            with self.assertRaisesRegex(ValueError, "execution intent"):
                comparison.refresh(self.project, request, execute=True)
            call.assert_not_called()

    def test_blind_review_proposal_uses_existing_controller_and_unknown_ratings(self):
        result, _ = self.execute()
        proposal = read(self.project / result["review_proposal"]["path"])
        self.assertFalse(result["review_proposal"]["independent_ratings_present"])
        self.assertFalse(result["review_proposal"]["formal_calibration_protocol_available"])
        write(self.project / review_packets.INPUT, proposal)
        checked = review_packets.refresh(self.project)
        self.assertEqual(checked["status"], "pass", checked["errors"])
        self.assertFalse(checked["scientific_completion_verified"])

    def test_cross_partition_same_source_cannot_claim_holdout_calibration(self):
        spec = self.spec(cases=[self.case("calibration", partition="calibration"), self.case("holdout", partition="holdout")])
        result, _ = self.execute(spec)
        self.assertFalse(result["review_proposal"]["formal_calibration_protocol_available"])

    def test_disjoint_originals_can_propose_full_calibration_protocol_without_fake_ratings(self):
        self.add("b", "# Methods\nThe sample contains 120 adults.\nA separate registered source.\n")
        self.build()
        spec = self.spec(cases=[self.case("calibration", partition="calibration"),
            self.case("holdout", paper="b", partition="holdout")])
        result, _ = self.execute(spec)
        self.assertTrue(result["review_proposal"]["formal_calibration_protocol_available"])
        proposal = read(self.project / result["review_proposal"]["path"])
        write(self.project / review_packets.INPUT, proposal)
        checked = review_packets.refresh(self.project)
        self.assertEqual(checked["status"], "pass", checked["errors"])
        self.assertFalse(result["semantic_quality_validated"])

    def test_contrary_anchor_coverage_is_explicit(self):
        spec = self.spec()
        p = self.config["papers"][0]
        spec["cases"][0]["relevant"].append({"paper_id": "a", **p["source"], "start_line": 3,
            "end_line": 3, "quote": "The treatment failed under drift.", "stance": "contradicts"})
        case = comparison.prepare(self.project, spec)["cases"][0]
        self.assertEqual(case["routes"]["full_text"]["coverage"]["contrary_anchors"], 1)
        self.assertEqual(case["routes"]["full_text"]["coverage"]["located_contrary_anchors"], 1)

    def test_empty_retrieval_is_free_and_full_text_arm_still_runs(self):
        spec = self.spec()
        spec["cases"][0].update(expected_abstain=True, relevant=[])
        spec["cases"][0]["request"]["question"] = "Volcanology eruptions?"
        abstain = {"answer": "The selected original does not establish the requested volcanic facts.",
            "abstain": True, "statements": [], "citations": []}
        result, call = self.execute(spec, fake=self.fake_call(response=abstain))
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["routes"][0]["status"], "no_retrieved_evidence_abstained_without_model_call")
        self.assertFalse(result["routes"][0]["model_call_made"])
        self.assertEqual(result["costs"]["known_model_cost_cny"], 0.01)

    def test_original_changed_during_model_call_blocks_derived_output(self):
        original = self.fake_call()
        def changed(project, **kwargs):
            result = original(project, **kwargs)
            (self.project / "evidence/sources/a.md").write_text("Changed during request.", encoding="utf-8")
            return result
        with self.assertRaisesRegex(ValueError, "authorization changed"):
            self.execute(fake=changed)


if __name__ == "__main__":
    unittest.main()
