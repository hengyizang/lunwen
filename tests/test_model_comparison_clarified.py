"""Clarified follow-up controls; every transport is fake and cloud CI runs tests."""
from __future__ import annotations

import base64
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import ai_providers, gateway_trial, model_comparison_clarified as trial, relay_billing


class ClarifiedComparisonTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        from tests.relay_guard_fixtures import install_fake_guard
        self.shared_guard=install_fake_guard(self.stack)
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
            return_value={"quote_sha256": "b" * 64}))
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

    def pending_closed(self, *, generation_status="completed"):
        self.settle.side_effect = relay_billing.BillingReconciliationError("unknown debit")
        trial.run_one(self.ledger, self.route, self.case_id, self.persist)
        self.ledger.update(status="closed_with_holds", closed_at="original close timestamp")
        self.ledger["entries"][0]["generation_status"] = generation_status
        self.settle.side_effect = None
        self.post.reset_mock()
        self.settle.reset_mock()
        for mocked in self.shared_guard.values():
            mocked.reset_mock()
        self.saved.clear()
        return copy.deepcopy(self.ledger)

    def test_reconcile_accounts_existing_call_without_touching_response_closed_state_or_isolation(self):
        for generation_status in ("completed", "response_failed"):
            with self.subTest(generation_status=generation_status):
                if self.ledger["entries"]:
                    self.ledger = trial.new_ledger(self.contract, self.parent)
                prior = self.pending_closed(generation_status=generation_status)
                trial.reconcile(self.ledger, self.contract, self.persist)
                self.assertEqual(self.ledger["status"], prior["status"])
                self.assertEqual(self.ledger["closed_at"], prior["closed_at"])
                self.assertEqual(self.ledger["scope"], prior["scope"])
                self.assertEqual(self.ledger["isolated_providers"], prior["isolated_providers"])
                self.assertEqual(self.ledger["quarantined_candidates"], prior["quarantined_candidates"])
                entry = self.ledger["entries"][0]
                for key, value in prior["entries"][0].items():
                    if key != "billing_status":
                        self.assertEqual(entry[key], value)
                self.assertEqual(entry["billing_status"], "settled")
                self.assertEqual(entry["actual_cost_cny"], self.debit["actual_cost_cny"])
                self.assertEqual(entry["debit_evidence"], self.debit["debit_evidence"])
                self.assertIs(entry["billing_reconciliation"]["generation_retried"], False)
                self.settle.assert_called_once_with(self.route["provider"], self.route["model"],
                    prior["entries"][0]["meter_before"])
                self.post.assert_not_called()
                self.shared_guard["begin"].assert_not_called()
                self.shared_guard["finish"].assert_not_called()
                self.assertEqual(len(self.saved), 1)
                trial.reconcile(self.ledger, self.contract, self.persist)
                self.assertEqual(self.settle.call_count, 1)

    def test_reconcile_failure_retains_full_hold_response_and_closed_state(self):
        prior = self.pending_closed()
        self.settle.side_effect = relay_billing.BillingReconciliationError("still ambiguous")
        with self.assertRaisesRegex(relay_billing.BillingReconciliationError, "ambiguous"):
            trial.reconcile(self.ledger, self.contract, self.persist)
        expected = copy.deepcopy(prior)
        expected["entries"][0]["billing_diagnostic"] = "still ambiguous"
        self.assertEqual(self.ledger, expected)
        self.assertEqual(self.saved, [expected])
        self.assertEqual(trial.cost(self.ledger), 2.0)
        self.post.assert_not_called()

    def test_reconcile_invalid_or_over_ceiling_debit_cannot_release_any_hold(self):
        prior = self.pending_closed()
        for settlement in ({"actual_cost_cny": 2.001, "debit_evidence": self.debit["debit_evidence"]},
                           {"actual_cost_cny": -1, "debit_evidence": self.debit["debit_evidence"]},
                           {"actual_cost_cny": float("nan"), "debit_evidence": self.debit["debit_evidence"]},
                           {"actual_cost_cny": 0.001, "debit_evidence": {}},
                           {"actual_cost_cny": True, "debit_evidence": self.debit["debit_evidence"]}):
            with self.subTest(settlement=settlement):
                self.settle.return_value = settlement
                with self.assertRaisesRegex(trial.ClarifiedError, "full_hold_retained"):
                    trial.reconcile(self.ledger, self.contract, self.persist)
                self.assertEqual(self.ledger, prior)
        self.assertEqual(self.saved, [])
        self.post.assert_not_called()

    def test_reconcile_persistence_failure_leaves_original_pending_ledger_untouched(self):
        prior = self.pending_closed()
        with self.assertRaisesRegex(OSError, "store unavailable"):
            trial.reconcile(self.ledger, self.contract, Mock(side_effect=OSError("store unavailable")))
        self.assertEqual(self.ledger, prior)
        self.assertEqual(trial.cost(self.ledger), 2.0)
        self.post.assert_not_called()

    def test_reconcile_validates_existing_contract_before_any_meter_read(self):
        prior = self.pending_closed()
        changed = copy.deepcopy(self.contract)
        changed["parent_blob_sha"] = "b" * 40
        with self.assertRaisesRegex(trial.ClarifiedError, "scope_changed_do_not_reset"):
            trial.reconcile(self.ledger, changed, self.persist)
        self.assertEqual(self.ledger, prior)
        self.assertEqual(self.saved, [])
        self.settle.assert_not_called()
        self.post.assert_not_called()

    def invoke_main(self, ledger, *, mode="reconcile", env_changes=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/model-comparison-20261020.json").write_text(json.dumps(self.plan), encoding="utf-8")
            env = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": gateway_trial.REPO,
                   "GITHUB_ACTOR": "hengyizang", "GITHUB_EVENT_NAME": "workflow_dispatch",
                   "GITHUB_REF": "refs/heads/main", "COMPARISON_AUTHORIZATION": trial.AUTHORIZATION,
                   "COMPARISON_EXPECTED_LEDGER_SHA": "a" * 40, "COMPARISON_GITHUB_TOKEN": "fake-nonsecret"}
            env.update(env_changes or {})
            state = Mock()
            state.load.return_value = ledger
            raw_parent = json.dumps(self.parent, ensure_ascii=False).encode()
            parent_sha = hashlib.sha1(b"blob " + str(len(raw_parent)).encode() + b"\0" + raw_parent).hexdigest()
            state.api.return_value = {"sha": parent_sha, "encoding": "base64",
                                      "content": base64.b64encode(raw_parent).decode()}
            if ledger is not None:
                ledger["scope"]["parent_blob_sha"] = parent_sha
            with (patch.dict(os.environ, env, clear=True), patch.object(trial, "ROOT", root),
                  patch.object(trial, "CloudState", return_value=state),
                  patch.object(trial, "current_parent", side_effect=AssertionError("no mutable parent in reconciliation")),
                  patch.object(trial, "new_ledger", side_effect=AssertionError("no initialization in reconciliation")),
                  patch.object(trial, "execute", side_effect=AssertionError("no generation in reconciliation"))):
                trial.main(["--mode", mode])
            return state

    def test_reconcile_main_requires_existing_ledger_and_never_initializes(self):
        with self.assertRaisesRegex(trial.ClarifiedError, "no_existing_clarified_trial_to_reconcile"):
            self.invoke_main(None)
        self.settle.assert_not_called()
        self.post.assert_not_called()

    def test_reconcile_main_dispatch_preserves_terminal_status_without_execute(self):
        self.pending_closed(generation_status="response_failed")
        with (patch.object(trial, "scope", side_effect=AssertionError("no new priced scope in reconciliation")),
              patch.object(trial.model_runtime, "pricing", side_effect=AssertionError("no current quote required"))):
            state = self.invoke_main(self.ledger,
                env_changes={"COMPARISON_AUTHORIZATION": "", "COMPARISON_EXPECTED_LEDGER_SHA": ""})
        self.assertEqual(self.ledger["status"], "closed_with_holds")
        self.assertEqual(self.ledger["entries"][0]["generation_status"], "response_failed")
        self.assertEqual(self.ledger["entries"][0]["billing_status"], "settled")
        state.save.assert_called_once()
        self.post.assert_not_called()

    def test_reconcile_main_retains_explicit_owner_cloud_authorization_guards(self):
        for env_changes in ({"GITHUB_ACTIONS": "false"}, {"GITHUB_ACTOR": "not-owner"},
                            {"GITHUB_EVENT_NAME": "push"}, {"GITHUB_REF": "refs/heads/unapproved"}):
            with self.subTest(env_changes=env_changes):
                with self.assertRaisesRegex(trial.ClarifiedError, "explicit_owner_cloud"):
                    self.invoke_main(self.ledger, env_changes=env_changes)
        self.settle.assert_not_called()
        self.post.assert_not_called()

    def test_execute_still_requires_separate_generation_authorization(self):
        with self.assertRaisesRegex(trial.ClarifiedError, "explicit_owner_cloud"):
            self.invoke_main(self.ledger, mode="execute", env_changes={"COMPARISON_AUTHORIZATION": ""})
        self.settle.assert_not_called()
        self.post.assert_not_called()

    def test_reconcile_original_parent_scope_cannot_be_rebound_to_changed_parent_or_allowance(self):
        prior = self.pending_closed()
        original = copy.deepcopy(prior["scope"])
        self.assertIs(trial.reconciliation_contract(self.plan, self.ledger, self.parent, "a" * 40),
                      self.ledger["scope"])
        changed_parent = copy.deepcopy(self.parent)
        changed_parent["entries"][0]["actual_cost_cny"] = 0.002
        with self.assertRaisesRegex(trial.ClarifiedError, "exact_original"):
            trial.reconciliation_contract(self.plan, self.ledger, changed_parent, "a" * 40)
        for field, value in (("ceiling_cny", 999), ("combined_ceiling_cny", 999),
                             ("parent_attempts", 0), ("fixture_sha256", "f" * 64)):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.ledger)
                changed["scope"][field] = value
                with self.assertRaisesRegex(trial.ClarifiedError, "scope_changed_do_not_reset"):
                    trial.reconciliation_contract(self.plan, changed, self.parent, "a" * 40)
        self.assertEqual(self.ledger["scope"], original)
        self.settle.assert_not_called()
        self.post.assert_not_called()


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

    def test_stale_parent_count_cannot_authorize_followup(self):
        state = trial.CloudState("fake-nonsecret-token")
        with (patch.object(trial.gateway_trial.CloudState, "read", return_value=({}, "b" * 40)),
              patch.object(state, "api") as api):
            with self.assertRaisesRegex(trial.ClarifiedError, "parent_is_not_current"):
                trial.current_parent(state, "a" * 40)
        api.assert_not_called()

    def test_conflict_or_bad_immutable_readback_cannot_confirm_persistence(self):
        ledger = {"entries": []}
        blob = self.blob(ledger)
        for responses in ([gateway_trial.TrialError("http_409")],
                          [{"content": {"sha": blob["sha"]}}, dict(blob, sha="b" * 40)],
                          [{"content": {"sha": blob["sha"]}},
                           dict(self.blob({"entries": ["changed"]}), sha=blob["sha"])]):
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
