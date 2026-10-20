"""Clarified follow-up controls; every transport is fake and cloud CI runs tests."""
from __future__ import annotations

import base64
from contextlib import ExitStack
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import ai_providers, gateway_trial, model_comparison_clarified as trial, relay_billing


class ClarifiedComparisonTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.plan = json.loads((Path(__file__).resolve().parents[1]
            / "config/model-comparison-20261020.json").read_text())
        self.parent = {"trial_id": trial.parent_trial.TRIAL, "status": "closed_with_holds",
            "full_matrix_authorization": {"authorization_id": trial.parent_trial.FULL_AUTHORIZATION},
            "isolated_providers": ["codekey-gemini"], "quarantined_candidates": ["codekey-argon-high"],
            "entries": [{"call_id": "old-" + str(index), "billing_status": "settled",
                         "reserved_ceiling_cny": 0.5, "actual_cost_cny": 0.001}
                        for index in range(108)]}
        # Full parent validation already has its own tests; this fixture
        # isolates the follow-up's immutable binding and combined-call controls.
        self.parent_validator = self.stack.enter_context(patch.object(trial.parent_trial,
            "validate_ledger", return_value=self.parent))
        self.stack.enter_context(patch.object(trial.parent_trial, "fingerprint", return_value="f" * 64))
        self.definitions = {case_id: {"id": case_id, "prompt": "Synthetic clarified fixture " + case_id,
                                     "system": "Return bounded JSON."} for case_id in trial.CASE_IDS}
        self.stack.enter_context(patch.object(trial.fixtures, "cases", side_effect=lambda: list(
            copy.deepcopy(self.definitions).values())))
        self.stack.enter_context(patch.object(trial.fixtures, "case",
            side_effect=lambda case_id: copy.deepcopy(self.definitions[case_id])))
        self.stack.enter_context(patch.object(trial.fixtures, "score", return_value={"score": 100, "passed": True}))
        self.pricing = self.stack.enter_context(patch.object(trial.model_runtime, "pricing",
            return_value={"quote_sha256": "q" * 64}))
        self.bound = self.stack.enter_context(patch.object(trial.model_runtime, "reservation_bound", return_value=2.0))
        self.meter = self.stack.enter_context(patch.object(trial.parent_trial, "read_meter", return_value={"before": 1}))
        self.post = self.stack.enter_context(patch.object(ai_providers, "call_production", return_value=SimpleNamespace(
            reported_model="gpt-6.1-sol", request_id="fake-request", text="{}",
            usage={"input_tokens": 20, "output_tokens": 10}, completion_status="completed", protocol="fake-native")))
        self.debit = {"actual_cost_cny": 0.001, "debit_evidence": {"source": "fake independent meter"}}
        self.settle = self.stack.enter_context(patch.object(relay_billing, "settle", return_value=self.debit))
        self.contract = trial.scope(self.plan, self.parent, "a" * 40)
        self.ledger = trial.new_ledger(self.contract, self.parent)
        self.route = self.contract["configurations"][0]
        self.case_id = trial.CASE_IDS[0]
        self.saved = []

    def persist(self, value):
        self.saved.append(copy.deepcopy(value))

    def test_fixed_six_baselines_and_two_existing_settings_produce_only_sixteen_v2_tasks(self):
        selected = self.contract["configurations"]
        self.assertEqual(len(selected), 8)
        self.assertEqual(len(self.contract["task_ceiling_cny"]), 16)
        self.assertEqual(self.contract["max_calls"], 16)
        self.assertEqual(self.contract["max_combined_calls"], 128)
        self.assertTrue(all(route["provider"] != "codekey-gemini" for route in selected))
        self.assertEqual(selected[-2:], self.plan["focused_settings"])
        self.assertTrue(all(call_id.endswith(trial.CASE_IDS) for call_id in self.contract["task_ceiling_cny"]))
        self.assertEqual(self.contract["ceiling_cny"], 32.0)

    def test_parent_must_be_closed_and_have_explicit_full_matrix_authorization(self):
        for status, authorization in (("running", True), ("stopped", True), ("closed", False)):
            with self.subTest(status=status, authorization=authorization):
                parent = copy.deepcopy(self.parent)
                parent["status"] = status
                if not authorization:
                    parent.pop("full_matrix_authorization")
                with self.assertRaisesRegex(trial.ClarifiedError, "exact_closed_authorized_parent"):
                    trial.scope(self.plan, parent, "a" * 40)
        self.parent_validator.assert_called()

    def test_combined_parent_and_full_followup_scope_cannot_exceed_128_calls(self):
        parent = copy.deepcopy(self.parent)
        parent["entries"] += copy.deepcopy(parent["entries"][:4])
        with self.assertRaisesRegex(trial.ClarifiedError, "combined_fixed_task_limit"):
            trial.scope(self.plan, parent, "a" * 40)
        self.post.assert_not_called()

    def test_parent_holds_and_actual_cost_are_frozen_in_combined_accounting(self):
        parent = copy.deepcopy(self.parent)
        parent["entries"][0]["billing_status"] = "reserved"
        contract = trial.scope(self.plan, parent, "a" * 40)
        self.assertEqual(contract["parent_outstanding_holds_cny"], 0.5)
        self.assertAlmostEqual(contract["parent_actual_cost_cny"], 0.107)
        self.assertEqual(contract["parent_committed_upper_cny"], 0.607)
        self.assertEqual(contract["combined_ceiling_cny"], 32.607)

    def test_complete_followup_does_not_mutate_parent_results_or_plan(self):
        before_parent, before_plan = copy.deepcopy(self.parent), copy.deepcopy(self.plan)
        trial.execute(self.ledger, self.contract, self.persist)
        self.assertEqual(self.parent, before_parent)
        self.assertEqual(self.plan, before_plan)
        self.assertEqual(len(self.ledger["entries"]), 16)
        self.assertEqual(self.post.call_count, 16)
        self.assertEqual(trial.summary(self.ledger)["combined_attempts"], 124)
        self.assertEqual(self.ledger["status"], "closed")

    def test_durable_reservation_failure_prevents_generation(self):
        def fail(_):
            raise OSError("store unavailable")
        with self.assertRaises(OSError):
            trial.run_one(self.ledger, self.route, self.case_id, fail)
        self.post.assert_not_called()
        self.settle.assert_not_called()

    def test_saved_reservation_precedes_the_single_generation_call(self):
        result = self.post.return_value
        def receive(*args, **kwargs):
            self.assertEqual(len(self.saved), 1)
            entry = self.saved[0]["entries"][0]
            self.assertEqual(entry["billing_status"], "reserved")
            self.assertEqual(entry["generation_status"], "not_sent")
            self.assertEqual(entry["case_sha256"], trial.digest(self.definitions[self.case_id]))
            return result
        self.post.side_effect = receive
        trial.run_one(self.ledger, self.route, self.case_id, self.persist)
        self.post.assert_called_once()

    def test_unknown_bill_keeps_full_hold_isolates_provider_and_allows_independent_configuration(self):
        self.settle.side_effect = [relay_billing.BillingReconciliationError("unknown debit"), self.debit]
        self.assertEqual(trial.run_one(self.ledger, self.route, self.case_id, self.persist),
                         "unknown_charge_full_hold_retained")
        self.assertEqual(trial.cost(self.ledger), 2.0)
        self.assertIn(self.route["provider"], self.ledger["isolated_providers"])
        other = next(route for route in self.contract["configurations"] if route["provider"] != self.route["provider"])
        self.assertEqual(trial.run_one(self.ledger, other, self.case_id, self.persist), "completed")
        self.assertEqual(self.post.call_count, 2)
        self.assertEqual(trial.cost(self.ledger), 2.001)
        self.assertEqual(trial.run_one(self.ledger, self.route, self.case_id, self.persist), "already_attempted")
        self.assertEqual(self.post.call_count, 2)

    def test_failed_generation_is_reconciled_and_never_retried(self):
        self.post.side_effect = ai_providers.ProviderError("response lost")
        self.assertEqual(trial.run_one(self.ledger, self.route, self.case_id, self.persist), "response_failed")
        self.settle.assert_called_once()
        self.assertEqual(trial.run_one(self.ledger, self.route, trial.CASE_IDS[1], self.persist), "isolated_no_generation")
        self.post.assert_called_once()

    def test_parent_provider_isolation_cannot_be_removed(self):
        changed = copy.deepcopy(self.ledger)
        changed["isolated_providers"] = []
        with self.assertRaisesRegex(trial.ClarifiedError, "parent_route_isolation"):
            trial.validate(changed, self.contract)

    def test_closed_followup_never_resets_or_generates_again(self):
        for status in ("closed", "closed_with_holds"):
            with self.subTest(status=status):
                ledger = copy.deepcopy(self.ledger)
                ledger["status"] = status
                prior = copy.deepcopy(ledger)
                trial.execute(ledger, self.contract, self.persist)
                self.assertEqual(ledger, prior)
        self.post.assert_not_called()

    def test_crash_before_reconciliation_isolates_same_credential_before_new_work(self):
        for generation in ("not_sent", "completed"):
            with self.subTest(generation=generation):
                ledger = trial.new_ledger(self.contract, self.parent)
                trial.run_one(ledger, self.route, self.case_id, self.persist)
                entry = ledger["entries"][0]
                entry.update(billing_status="reserved", generation_status=generation)
                entry.pop("actual_cost_cny", None)
                entry.pop("debit_evidence", None)
                self.post.reset_mock()
                trial.execute(ledger, self.contract, self.persist)
                self.assertIn(self.route["provider"], ledger["isolated_providers"])
                self.assertFalse(any(call.args[0] == self.route["provider"] for call in self.post.call_args_list))
                self.assertEqual(entry["billing_status"], "reserved")

    def test_changed_parent_blob_case_or_quote_scope_cannot_reset_existing_followup(self):
        for field, value in (("parent_blob_sha", "b" * 40), ("fixture_sha256", "changed"),
                             ("ceiling_cny", 100000.0)):
            with self.subTest(field=field):
                contract = copy.deepcopy(self.contract)
                contract[field] = value
                with self.assertRaisesRegex(trial.ClarifiedError, "scope_changed_do_not_reset"):
                    trial.execute(self.ledger, contract, self.persist)
        self.post.assert_not_called()

    def test_v2_attempt_case_hash_route_and_quote_bindings_cannot_change(self):
        trial.run_one(self.ledger, self.route, self.case_id, self.persist)
        for field, value in (("case_id", "evidence_conflict"), ("case_sha256", "changed"),
                             ("model", "another-model"), ("quote_sha256", "another-quote")):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.ledger)
                changed["entries"][0][field] = value
                with self.assertRaisesRegex(trial.ClarifiedError, "attempt_binding_changed"):
                    trial.validate(changed, self.contract)

    def test_nonexistent_or_extra_v2_cases_are_not_authorized(self):
        with patch.object(trial.fixtures, "cases", return_value=[{"id": "ambiguous-old-case"}]):
            with self.assertRaisesRegex(trial.ClarifiedError, "fixture_scope_changed"):
                trial.scope(self.plan, self.parent, "a" * 40)

    def test_unavailable_pre_call_meter_sends_no_generation(self):
        self.meter.side_effect = relay_billing.BillingReconciliationError("metadata unavailable")
        self.assertEqual(trial.run_one(self.ledger, self.route, self.case_id, self.persist),
                         "metadata_unavailable_no_generation")
        self.assertEqual(self.ledger["entries"], [])
        self.post.assert_not_called()

    def test_unknown_holds_close_as_holds_without_scientific_or_production_claims(self):
        self.settle.side_effect = relay_billing.BillingReconciliationError("unknown debit")
        trial.execute(self.ledger, self.contract, self.persist)
        report = trial.summary(self.ledger)
        self.assertEqual(report["status"], "closed_with_holds")
        self.assertGreater(report["outstanding_holds_cny"], 0)
        self.assertIs(report["parent_unchanged"], True)
        self.assertIs(report["scientific_equivalence_verified"], False)
        self.assertIs(report["production_routing_changed"], False)


class ClarifiedCloudStateTests(unittest.TestCase):
    def blob(self, value):
        raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
        sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        return {"sha": sha, "encoding": "base64", "content": base64.b64encode(raw).decode()}

    def test_only_followup_file_is_written_with_cas_and_immutable_readback(self):
        state = trial.CloudState("fake-nonsecret-token")
        with patch.object(gateway_trial.CloudState, "read", return_value=({"entries": []}, "a" * 40)):
            state.load()
        ledger = {"entries": []}
        blob = self.blob(ledger)
        with (patch.object(state, "api", side_effect=[{"content": {"sha": blob["sha"]}}, blob]) as api,
              patch.object(gateway_trial.CloudState, "read", side_effect=AssertionError("mutable readback forbidden"))):
            state.save(ledger)
        path, payload, method = api.call_args_list[0].args
        self.assertEqual(path, "contents/trial-state/" + trial.FILE)
        self.assertNotIn(trial.parent_trial.FILE, path)
        self.assertEqual(payload["branch"], trial.parent_trial.STATE)
        self.assertEqual(payload["sha"], "a" * 40)
        self.assertEqual(method, "PUT")
        self.assertEqual(api.call_args_list[1].args, ("git/blobs/" + blob["sha"],))
        self.assertEqual(state.expected_sha, blob["sha"])

    def test_conflict_or_bad_immutable_readback_cannot_confirm_persistence(self):
        ledger = {"entries": []}
        blob = self.blob(ledger)
        for responses in ([gateway_trial.TrialError("http_409")],
                          [{"content": {"sha": blob["sha"]}}, dict(blob, sha="b" * 40)]):
            with self.subTest(responses=len(responses)):
                state = trial.CloudState("fake-nonsecret-token")
                with patch.object(gateway_trial.CloudState, "read", return_value=(ledger, "a" * 40)):
                    state.load()
                with patch.object(state, "api", side_effect=responses):
                    with self.assertRaises((gateway_trial.TrialError, trial.ClarifiedError)):
                        state.save(ledger)
                self.assertEqual(state.expected_sha, "a" * 40)


if __name__ == "__main__":
    unittest.main()
