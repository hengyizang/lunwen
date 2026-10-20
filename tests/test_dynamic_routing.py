"""Synthetic cloud-only routing checks; no provider requests or science claims."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import calibration_analysis, dynamic_routing as routing, model_routing, model_spend, output_provenance, review_packets
from scripts.research_artifacts import read, sha, write
from tests.test_review_packets import RUBRIC, bound


class DynamicRoutingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        environment = patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production", "DR_OS_DYNAMIC_ROUTING": "production"}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.baseline = model_routing.select("auxiliary", "reader-qa")
        self.profile = {"task_class": "source-qa", "science_risk": "routine", "priority": "cost"}
        self.policy, _ = routing.load_policy()
        self.candidate = next(row for row in self.policy["candidates"] if row["candidate_id"] == "codekey-codex-discount--gpt-6.1-sol--medium--standard")

    def select(self, **options):
        return routing.choose(self.project, self.baseline, prompt="Read the supplied source.", system="Preserve evidence.",
                              max_output_tokens=options.pop("max_output_tokens", 5000), timeout=180,
                              task_profile=options.pop("task_profile", self.profile), **options)

    def ledger(self, rows):
        target = self.project / "state/model-usage.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def calibration(self, *, bad_quality=False, raters=2, holdouts=3, candidate_output=5000, repeated_source=False,
                    missing_task_profile=False, candidate_origin_model=None, omit_provenance=False):
        cases, ledger = [], []
        for index in range(6):
            source_index = 3 if repeated_source and index == 4 else index
            source = bound(self.project, f"evidence/source-{index}.md", f"Independent source {source_index} reports a fixed recorded quantity.")
            entries = []
            for channel, route, price in (("baseline", self.baseline, .02), (self.candidate["candidate_id"], self.candidate, .005)):
                run = f"case-{index}-{channel}"
                artifact = bound(self.project, f"api_runs/{run}.md", f"The source reports a fixed quantity for case {index}.")
                if not omit_provenance:
                    output_provenance.record_model_writes(self.project, [self.project / artifact["path"]], family="openai",
                        provider=route["provider"], model=candidate_origin_model if channel != "baseline" and candidate_origin_model else route["model"],
                        role=self.baseline["role"], run_id=run)
                entries.append({"id": "baseline" if channel == "baseline" else "candidate", "status": "success", "artifact": artifact,
                    "authorized_for_internal_review": True, "authorization_note": "Synthetic held-out test output",
                    "author_id": f"author-{channel}", "model": route["model"], "channel": channel,
                    "routing_identity": routing._id(route), "run_ids": [run]})
                ledger.append({"run_id": run, "provider": route["provider"], "model": route["model"],
                    "stage": self.baseline["stage"], "role": self.baseline["role"],
                    "requested_reasoning_effort": route["reasoning_effort"], "cost_cny": price,
                    **({} if missing_task_profile else {"task_profile": copy.deepcopy(self.profile)}),
                    "cost_status": "settled_usage_receipt", "usage_estimated": False,
                    "completion_status": "completed", "prompt_input_bytes": 30000,
                    "max_output_tokens": 5000 if channel == "baseline" else candidate_output, "duration_seconds": 4.0})
            cases.append({"id": f"case-{index}", "sources": [source], "candidates": entries})
        self.ledger(ledger)
        spec = {"minimum_raters": 2, "qualification_thresholds": {"fidelity": 3},
                "case_partitions": {case["id"]: "holdout" if index < holdouts else "calibration" for index, case in enumerate(cases)},
                "cost_run_ids": [row["run_id"] for row in ledger]}
        packet = {"id": "routing-paired", "kind": "calibration", "rubric": copy.deepcopy(RUBRIC), "cases": cases, "analysis": spec}
        write(self.project / review_packets.INPUT, {"schema_version": "1.0", "packets": [packet]})
        refreshed = review_packets.refresh(self.project)
        self.assertEqual(refreshed["status"], "pass", refreshed)
        snapshot = review_packets.review_snapshot(self.project, "routing-paired")
        answer = read(self.project / "reports/review-packets/routing-paired/answer-key.json")
        new_labels = {(row["case_label"], row["candidate_label"]) for row in answer["answer_key"] if row["candidate"]["channel"] != "baseline"}
        for index in range(raters):
            observations = [{"case_label": row["case_label"], "candidate_label": row["candidate_label"],
                             "rationale": "Synthetic independent observed comparison",
                             "ratings": {"fidelity": 3 if bad_quality and (row["case_label"], row["candidate_label"]) in new_labels else 4},
                             "critical_errors": {"invented-fact": False}} for row in snapshot["roster"]]
            judgments = {"rater_id": f"independent-rater-{index}", "independent": True,
                "independence_note": "Synthetic named rater independent of both candidate authors", "observations": observations,
                "cost_scope_confirmation": {"analysis_sha256": review_packets.digest(spec),
                    "all_calls_retries_tools_compute_and_validation_included": True,
                    "ledger_sha256": sha(self.project / "state/model-usage.jsonl"), "no_double_counting": True}}
            target, value = review_packets.create_confirmation(self.project, "routing-paired", f"Owner-{index}", judgments)
            write(target, value)
        calibration_analysis.refresh(self.project, "routing-paired")
        return ledger

    def accept(self):
        with patch.object(routing, "_available"):
            return routing.record_acceptance(self.project, self.candidate["candidate_id"], self.baseline,
                task_profile=self.profile, packet_id="routing-paired", actor="Codex manager synthetic fixture")

    def test_registry_covers_ten_groups_and_does_not_self_accept(self):
        self.assertEqual(len({row["provider"] for row in self.policy["candidates"]}), 10)
        self.assertEqual(len(self.policy["candidates"]), 92)
        self.assertEqual({row["status"] for row in self.policy["candidates"]}, {"candidate"})
        result = self.select()
        self.assertEqual(result["decision"]["selected_candidate_id"], "baseline")
        self.assertEqual(result["route"]["policy_sha256"], self.baseline["policy_sha256"])

    def test_profiles_reject_transport_budget_and_unsafe_values(self):
        for field in ("provider", "model", "budget", "reasoning_effort"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                routing.validate_profile({**self.profile, field: "override"})
        for value in ({**self.profile, "task_class": "free text please"}, {**self.profile, "min_output_tokens": True},
                      {**self.profile, "deadline_seconds": 900}, {**self.profile, "science_risk": "cheap"}):
            with self.assertRaises(ValueError):
                routing.validate_profile(value)
        self.assertEqual(routing.validate_profile(None, stage="writing-and-review", role="persistent-writer")["science_risk"], "critical")

    def test_off_preserves_static_route_and_validates_mode(self):
        with patch.dict(os.environ, {"DR_OS_DYNAMIC_ROUTING": "off"}):
            self.assertFalse(routing.enabled())
            self.assertEqual(self.select()["decision"]["mode"], "off")
        with patch.dict(os.environ, {"DR_OS_DYNAMIC_ROUTING": "auto-try-cheap"}), self.assertRaises(ValueError):
            routing.enabled()

    def test_unknown_cost_or_outstanding_hold_blocks_new_paid_selection(self):
        self.ledger([{"usage_estimated": True, "cost_cny": .01}])
        with self.assertRaisesRegex(ValueError, "unknown request"):
            self.select()
        self.ledger([{"cost_status": "unknown_reconcile_required", "reservation_id": "unknown"}])
        with self.assertRaisesRegex(ValueError, "unknown request"):
            self.select()
        state = model_spend.initial()
        state["reservations"]["pending"] = {"paper_id": None, "max_cost_cny": .1}
        model_spend.write(self.project, state)
        with self.assertRaisesRegex(ValueError, "reservations"):
            self.select()

    def test_explicit_receipt_reconciliation_removes_stale_unknown_block(self):
        self.ledger([{"cost_status": "unknown_reconcile_required", "reservation_id": "old"}])
        state = model_spend.initial()
        state["reconciliation_events"] = [{"receipt_id": "old"}]
        model_spend.write(self.project, state)
        self.assertEqual(self.select()["decision"]["selected_candidate_id"], "baseline")

    def test_hash_tracked_real_blind_review_can_enable_accepted_task_route(self):
        self.calibration()
        accepted = self.accept()
        self.assertEqual(accepted["statistics"][self.candidate["candidate_id"]]["accepted_tasks"], 6)
        with patch.object(routing, "_available"):
            result = self.select()
        self.assertEqual(result["route"]["provider"], "codekey-codex-discount")
        self.assertEqual(result["route"]["reasoning_effort"], "medium")
        self.assertFalse(result["decision"]["cache_transfer_assumed"])

    def test_unrelated_history_does_not_invalidate_acceptance_or_response_cache_identity(self):
        rows = self.calibration()
        self.accept()
        with patch.object(routing, "_available"):
            first = self.select()
            self.ledger(rows + [{"run_id": "unrelated-settled", "cost_status": "settled_usage_receipt", "cost_cny": .4}])
            second = self.select()
        self.assertEqual(first["route"]["policy_sha256"], second["route"]["policy_sha256"])
        self.assertNotEqual(first["decision"]["history_sha256"], second["decision"]["history_sha256"])
        self.assertEqual(second["decision"]["selected_candidate_id"], self.candidate["candidate_id"])

    def test_stale_sources_or_human_reviews_cannot_keep_route_enabled(self):
        self.calibration()
        self.accept()
        (self.project / "evidence/source-0.md").write_text("Changed evidence", encoding="utf-8")
        with patch.object(routing, "_available"):
            self.assertEqual(self.select()["decision"]["selected_candidate_id"], "baseline")

    def test_threshold_pass_alone_does_not_allow_quality_below_paired_baseline(self):
        self.calibration(bad_quality=True)
        with self.assertRaisesRegex(ValueError, "below its paired baseline"):
            self.accept()

    def test_one_human_or_insufficient_holdout_cannot_promote_candidate(self):
        self.calibration(raters=1)
        with self.assertRaises(ValueError):
            self.accept()

    def test_duplicate_source_content_cannot_inflate_independent_case_count(self):
        self.calibration(repeated_source=True)
        with self.assertRaisesRegex(ValueError, "cannot reuse the same source"):
            self.accept()

    def test_candidate_is_filtered_before_spend_when_actual_reservation_exceeds_budget(self):
        self.calibration()
        self.accept()
        for paper, remaining in ((None, {"project_remaining": .01, "paper_remaining": None}),
                                 ("P01", {"project_remaining": 10.0, "paper_remaining": .01})):
            with self.subTest(paper=paper), patch.object(routing, "_available"), \
                    patch("scripts.model_runtime.reservation_bound", return_value=.02) as bound_, \
                    patch("scripts.model_runtime.budget_status", return_value=remaining), \
                    patch("scripts.model_runtime._paper_for_stage", return_value=paper):
                result = self.select()
            self.assertEqual(result["decision"]["selected_candidate_id"], "baseline")
            self.assertTrue(any("reservation does not fit" in item["reason"] for item in result["decision"]["excluded"]))
            self.assertTrue(bound_.called)

    def test_arbitrary_pass_json_without_protected_manager_origin_is_rejected(self):
        write(self.project / routing.ACCEPTANCES, {"schema_version": "1.0", "acceptances": [{"status": "pass"}]})
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.select()

    def test_no_key_or_no_exact_quote_cannot_select_an_accepted_candidate(self):
        self.calibration()
        self.accept()
        result = self.select()
        self.assertEqual(result["decision"]["selected_candidate_id"], "baseline")
        self.assertTrue(any("key is not configured" in row["reason"] for row in result["decision"]["excluded"]))
        with patch.object(routing.ai_providers, "configuration", return_value={"configured": True}), patch("scripts.model_runtime.pricing", return_value={}):
            self.assertEqual(self.select()["decision"]["selected_candidate_id"], "baseline")

    def test_recorded_task_class_cannot_be_relabelled_for_acceptance(self):
        self.calibration()
        self.profile = {**self.profile, "task_class": "different-unverified-task"}
        with self.assertRaisesRegex(ValueError, "task class or science risk"):
            self.accept()

    def test_recorded_science_risk_cannot_be_relabelled_for_acceptance(self):
        self.calibration()
        self.profile = {**self.profile, "science_risk": "auxiliary"}
        with self.assertRaisesRegex(ValueError, "task class or science risk"):
            self.accept()

    def test_missing_runtime_task_profile_cannot_be_accepted(self):
        self.calibration(missing_task_profile=True)
        with self.assertRaisesRegex(ValueError, "missing its recorded task profile"):
            self.accept()

    def test_stronger_models_artifact_cannot_be_paired_with_cheap_models_bill(self):
        self.calibration(candidate_origin_model="gpt-6-astra")
        with self.assertRaisesRegex(ValueError, "scored artifact provenance"):
            self.accept()

    def test_untracked_artifact_cannot_be_accepted_as_a_model_result(self):
        self.calibration(omit_provenance=True)
        with self.assertRaisesRegex(ValueError, "scored artifact provenance"):
            self.accept()

    def test_changed_price_contract_cannot_reuse_old_cost_comparison(self):
        self.calibration()
        self.accept()
        from scripts import model_runtime
        original = model_runtime.pricing
        def changed(*args, **kwargs):
            return {**original(*args, **kwargs), "quote_sha256": "f" * 64}
        with patch.object(routing, "_available"), patch.object(model_runtime, "pricing", side_effect=changed):
            result = self.select()
        self.assertEqual(result["decision"]["selected_candidate_id"], "baseline")
        self.assertTrue(any("price quote changed" in item["reason"] for item in result["decision"]["excluded"]))

    def test_core_stage_and_explicit_critical_tasks_cannot_be_relabelled_routine(self):
        for baseline in (model_routing.select("topic-intelligence", "persistent-writer"),
                         model_routing.select("writing-and-review", "persistent-writer", "core-story")):
            self.baseline = baseline
            result = self.select()
            self.assertEqual(result["decision"]["task_profile"]["science_risk"], "critical")
            self.assertEqual(result["route"]["model"], "gpt-6-astra")
            self.assertTrue(any("floor cannot be lowered" in item["reason"] for item in result["decision"]["excluded"]))

    def test_input_bytes_include_unicode_system_and_actual_hashed_media(self):
        body = b"\x89PNG\r\n\x1a\nsynthetic image"
        media = {"mime_type": "image/png", "data_base64": base64.b64encode(body).decode(), "sha256": hashlib.sha256(body).hexdigest()}
        result = self.select(attachments=[media])
        expected = len("Read the supplied source.".encode()) + len("Preserve evidence.".encode()) + len(body)
        self.assertEqual(result["decision"]["input_bytes"], expected)

    def test_explicit_long_output_requires_accepted_envelope_and_caller_authority(self):
        self.profile = {**self.profile, "min_output_tokens": 8000}
        with self.assertRaisesRegex(ValueError, "caller's authorized"):
            self.select(max_output_tokens=5000)
        with self.assertRaisesRegex(ValueError, "no accepted route"):
            self.select(max_output_tokens=10000)
        self.candidate = next(row for row in self.policy["candidates"] if row["candidate_id"] == "codekey-codex-discount--gpt-6.1-sol--medium--long")
        self.calibration(candidate_output=10000)
        self.accept()
        with patch.object(routing, "_available"):
            result = self.select(max_output_tokens=10000)
        self.assertEqual(result["route"]["max_output_tokens"], 8000)
        self.assertLessEqual(result["route"]["max_output_tokens"], 10000)

    def test_verified_baseline_response_cache_avoids_another_paid_route(self):
        self.calibration()
        self.accept()
        with patch.object(routing, "_available") as available:
            result = self.select(baseline_cache_hit=True)
        self.assertEqual(result["decision"]["selected_candidate_id"], "baseline")
        self.assertIn("zero additional", result["decision"]["reason"])
        available.assert_not_called()

    def test_switching_cooldown_and_failed_candidate_require_review(self):
        rows = self.calibration()
        accepted = self.accept()
        at = datetime.now(timezone.utc).isoformat()
        self.ledger(rows + [{"run_id": "newer", "at": at, "stage": self.baseline["stage"], "role": self.baseline["role"],
                            "task_profile": self.profile, "dynamic_candidate_id": "baseline", "completion_status": "completed"}])
        with patch.object(routing, "_available"):
            result = self.select()
        self.assertEqual(result["decision"]["selected_candidate_id"], "baseline")
        self.assertTrue(any("cooldown" in item["reason"] for item in result["decision"]["excluded"]))
        self.ledger(rows + [{"run_id": "bad", "at": at, "stage": self.baseline["stage"], "role": self.baseline["role"],
                            "task_profile": self.profile, "dynamic_candidate_id": self.candidate["candidate_id"],
                            "validation_status": "source_contract_failed_no_retry", "completion_status": "completed"}])
        with patch.object(routing, "_available"):
            result = self.select()
        self.assertEqual(result["decision"]["selected_candidate_id"], "baseline")
        self.assertTrue(any("suspend" in item["reason"] for item in result["decision"]["excluded"]))
        self.ledger(rows + [{"run_id": "bad-transport", "at": at, "stage": self.baseline["stage"], "role": self.baseline["role"],
                            "task_profile": self.profile, "dynamic_candidate_id": self.candidate["candidate_id"],
                            "transport_error_type": "ProviderError"}])
        with patch.object(routing, "_available"):
            result = self.select()
        self.assertEqual(result["decision"]["selected_candidate_id"], "baseline")
        self.assertTrue(any("suspend" in item["reason"] for item in result["decision"]["excluded"]))


if __name__ == "__main__":
    unittest.main()
