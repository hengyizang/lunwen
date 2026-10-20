"""New CNY30 cloud trial controls, using fake transports and no credentials."""
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

from scripts import ai_providers, gateway_trial, model_comparison as comparison, relay_billing


class ModelComparisonTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((Path(__file__).resolve().parents[1]
            / "config/model-comparison-20261020.json").read_text(encoding="utf-8"))
        self.route = copy.deepcopy(self.plan["candidates"][0])
        self.case_id = self.route["screening_cases"][0]
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        definitions = [{"id": name, "prompt": "Synthetic fixture: " + name,
                        "system": "Return bounded synthetic output."}
                       for name in self.plan["screening_cases"] + self.plan["focused_cases"]]
        self.definitions = {item["id"]: item for item in definitions}
        self.stack.enter_context(patch.object(comparison.fixtures, "cases", return_value=definitions))
        self.stack.enter_context(patch.object(comparison.fixtures, "case",
            side_effect=lambda name: copy.deepcopy(self.definitions[name])))
        self.grade = self.stack.enter_context(patch.object(comparison.fixtures, "score",
            return_value={"score": 100, "passed": True}))
        self.pricing = self.stack.enter_context(patch.object(comparison.model_runtime, "pricing",
            return_value={"quote_sha256": "q" * 64}))
        self.bound = self.stack.enter_context(patch.object(comparison.model_runtime, "reservation_bound",
            return_value=2.0))
        self.read_meter_impl = comparison.read_meter
        self.meter = self.stack.enter_context(patch.object(comparison, "read_meter",
            return_value={"provider": self.route["provider"], "requests": 10, "cost_cny": 1.0}))
        self.post = self.stack.enter_context(patch.object(ai_providers, "call_production",
            return_value=SimpleNamespace(reported_model=self.route["model"], request_id="fake-request",
                text="{}", usage={"input_tokens": 25, "output_tokens": 15},
                completion_status="completed", protocol="openai_responses")))
        self.settlement = {"actual_cost_cny": 0.12,
            "debit_evidence": {"source": "https://cheapai.info/api/log/token",
                               "exactly_one_new_gateway_request": True}}
        self.settle = self.stack.enter_context(patch.object(relay_billing, "settle",
            return_value=self.settlement))
        self.saved = []

    def persist(self, ledger):
        self.saved.append(copy.deepcopy(ledger))

    def ledger(self, plan=None):
        return comparison.new_ledger(self.plan if plan is None else plan)

    def entry(self, *, amount=2.0, case_id=None):
        case_id = self.case_id if case_id is None else case_id
        return {"call_id": self.route["id"] + "|" + case_id,
                "candidate_id": self.route["id"], "provider": self.route["provider"],
                "model": self.route["model"], "effort": self.route["effort"],
                "case_id": case_id, "case_sha256": comparison.digest(self.definitions[case_id]),
                "phase": "screening", "reserved_ceiling_cny": amount,
                "generation_status": "not_sent"}

    def test_new_authorization_does_not_reopen_or_write_original_trial(self):
        ledger = self.ledger()
        self.assertEqual(ledger["limit_cny"], 30.0)
        self.assertNotEqual(ledger["trial_id"], gateway_trial.TRIAL)
        self.assertNotEqual(comparison.STATE, gateway_trial.STATE)
        self.assertEqual(ledger["authorization_id"], comparison.AUTHORIZATION)
        self.assertEqual(ledger["production_routing_changed"], False)
        self.assertEqual(ledger["scientific_completion"], False)
        self.assertEqual(ledger["paid_model_judges"], 0)

    def test_failed_reservation_persistence_prevents_generation(self):
        ledger = self.ledger()
        def fail(_):
            raise OSError("durable store unavailable")
        with self.assertRaises(OSError):
            comparison.run_one(ledger, self.route, self.case_id, "screening", fail)
        self.post.assert_not_called()
        self.settle.assert_not_called()
        self.assertEqual(ledger["entries"][0]["billing_status"], "reserved")

    def test_reservation_is_durable_before_the_only_generation_call(self):
        ledger = self.ledger()
        def receive(*args, **kwargs):
            self.assertEqual(len(self.saved), 1)
            prior = self.saved[0]["entries"][0]
            self.assertEqual(prior["billing_status"], "reserved")
            self.assertEqual(prior["generation_status"], "not_sent")
            self.assertIn("meter_before", prior)
            return SimpleNamespace(reported_model=self.route["model"], request_id="fake-request",
                text="{}", usage={"input_tokens": 25, "output_tokens": 15},
                completion_status="completed", protocol="openai_responses")
        self.post.side_effect = receive
        self.assertEqual(comparison.run_one(ledger, self.route, self.case_id,
            "screening", self.persist), "completed")
        self.post.assert_called_once()

    def test_unknown_hold_counts_at_full_bound_and_blocks_new_work(self):
        ledger = self.ledger()
        first = self.entry(amount=29.9)
        self.assertTrue(comparison.reserve(ledger, first, self.persist))
        first["generation_status"] = "response_failed"
        first["actual_cost_cny"] = 0.001  # An unverified receipt cannot release the hold.
        self.assertEqual(comparison.cost(ledger), 29.9)
        with self.assertRaisesRegex(comparison.ComparisonError, "unknown_charge"):
            comparison.reserve(ledger, self.entry(amount=0.01,
                case_id=self.route["screening_cases"][1]), self.persist)
        self.assertEqual(len(ledger["entries"]), 1)

    def test_settled_cumulative_cny30_cap_applies_across_phases(self):
        ledger = self.ledger()
        first = self.entry(amount=29.9)
        comparison.reserve(ledger, first, self.persist)
        comparison.settle_entry(ledger, first,
            {"actual_cost_cny": 29.9, "debit_evidence": {"source": "fake independent meter"}}, self.persist)
        self.assertFalse(comparison.reserve(ledger, self.entry(amount=0.2,
            case_id=self.route["screening_cases"][1]), self.persist))
        self.assertEqual(comparison.cost(ledger), 29.9)
        self.assertEqual(len(ledger["entries"]), 1)

    def test_only_independent_debit_releases_the_reservation(self):
        ledger = self.ledger()
        entry = self.entry(amount=29.0)
        comparison.reserve(ledger, entry, self.persist)
        with self.assertRaisesRegex(comparison.ComparisonError, "independent_debit"):
            comparison.settle_entry(ledger, entry, {"actual_cost_cny": 0.1}, self.persist)
        self.assertEqual(comparison.cost(ledger), 29.0)
        comparison.settle_entry(ledger, entry, self.settlement, self.persist)
        self.assertEqual(comparison.cost(ledger), 0.12)
        self.assertTrue(comparison.reserve(ledger, self.entry(amount=29.0,
            case_id=self.route["screening_cases"][1]), self.persist))

    def test_actual_debit_is_recorded_instead_of_token_estimate(self):
        ledger = self.ledger()
        comparison.run_one(ledger, self.route, self.case_id, "screening", self.persist)
        entry = ledger["entries"][0]
        self.settle.assert_called_once_with(self.route["provider"], self.route["model"], entry["meter_before"])
        self.assertEqual(entry["billing_status"], "settled")
        self.assertEqual(entry["actual_cost_cny"], 0.12)
        self.assertEqual(entry["debit_evidence"], self.settlement["debit_evidence"])
        self.assertEqual(comparison.cost(ledger), 0.12)

    def test_untrusted_usage_fields_and_account_strings_are_not_persisted(self):
        self.post.return_value.usage = {"input_tokens": 25, "output_tokens": 15,
            "account_name": "private-account", "api_key": "relay-secret-value",
            "cache_creation_input_tokens": "credential-in-typed-field",
            "input_tokens_details": {"cached_tokens": 3,
                                     "account_name": "another-private-account"}}
        ledger = self.ledger()
        comparison.run_one(ledger, self.route, self.case_id, "screening", self.persist)
        self.assertEqual(ledger["entries"][0]["usage"], {
            "input_tokens": 25, "output_tokens": 15,
            "input_tokens_details": {"cached_tokens": 3}})
        self.assertNotIn("private-account", json.dumps(self.saved))
        self.assertNotIn("relay-secret-value", json.dumps(self.saved))

    def test_unknown_post_call_bill_stops_all_subsequent_generation(self):
        plan = self.plan
        ledger = self.ledger(plan)
        self.settle.side_effect = relay_billing.BillingReconciliationError("unknown debit")
        with self.assertRaisesRegex(comparison.ComparisonError, "unknown_charge_reconciliation_required"):
            comparison.execute(plan, ledger, self.persist)
        self.assertEqual(ledger["status"], "stopped")
        self.assertEqual(comparison.cost(ledger), 2.0)
        self.assertEqual(ledger["entries"][0]["billing_status"], "reserved")
        self.assertEqual(self.post.call_count, 1)
        comparison.execute(plan, ledger, self.persist)
        self.assertEqual(self.post.call_count, 1)

    def test_failed_generation_is_not_retried_and_is_still_reconciled(self):
        ledger = self.ledger()
        self.post.side_effect = ai_providers.ProviderError("response lost; reconcile billing")
        result = comparison.run_one(ledger, self.route, self.case_id, "screening", self.persist)
        self.assertEqual(result, "response_failed")
        self.post.assert_called_once()
        self.settle.assert_called_once()
        self.assertEqual(ledger["entries"][0]["actual_cost_cny"], 0.12)
        self.assertIn(self.route["id"], ledger["quarantined_candidates"])
        self.assertEqual(comparison.run_one(ledger, self.route, self.case_id,
            "screening", self.persist), "quarantined_no_generation")
        self.post.assert_called_once()

    def test_quarantine_blocks_every_later_phase_and_setting_screen(self):
        ledger = self.ledger()
        ledger["quarantined_candidates"] = [self.route["id"]]
        for phase, case_id in (("screening", self.case_id),
                ("focused-setting-screen", self.route["screening_cases"][1]),
                ("focused", self.route["focused_cases"][0])):
            with self.subTest(phase=phase):
                self.assertEqual(comparison.run_one(ledger, self.route, case_id,
                    phase, self.persist), "quarantined_no_generation")
        self.assertEqual(ledger["entries"], [])
        self.pricing.assert_not_called()
        self.meter.assert_not_called()
        self.post.assert_not_called()

    def test_failed_response_persistence_never_replays_the_attempt(self):
        ledger = self.ledger()
        def fail_second(value):
            if self.saved:
                raise OSError("store unavailable after generation")
            self.persist(value)
        with self.assertRaises(OSError):
            comparison.run_one(ledger, self.route, self.case_id, "screening", fail_second)
        self.post.assert_called_once()
        self.settle.assert_not_called()
        self.assertEqual(comparison.run_one(ledger, self.route, self.case_id,
            "screening", self.persist), "already_attempted")
        self.post.assert_called_once()
        self.assertEqual(comparison.cost(ledger), 2.0)

    def test_no_generation_when_pre_call_meter_is_unavailable(self):
        ledger = self.ledger()
        self.meter.side_effect = relay_billing.BillingReconciliationError("metadata unavailable")
        result = comparison.run_one(ledger, self.route, self.case_id, "screening", self.persist)
        self.assertEqual(result, "metadata_unavailable_no_generation")
        self.assertEqual(ledger["entries"], [])
        self.post.assert_not_called()
        self.settle.assert_not_called()

    def test_closed_trial_is_not_reset_or_reopened_by_execute(self):
        ledger = self.ledger()
        ledger["status"] = "closed"
        before = copy.deepcopy(ledger)
        comparison.execute(self.plan, ledger, self.persist)
        self.assertEqual(ledger, before)
        self.assertEqual(self.saved, [])
        self.post.assert_not_called()

    def stopped_settled_ledger(self, amount=0.12):
        ledger = self.ledger()
        entry = self.entry(amount=max(2.0, amount))
        comparison.reserve(ledger, entry, self.persist)
        comparison.settle_entry(ledger, entry,
            {"actual_cost_cny": amount, "debit_evidence": {"source": "fake independent meter"}},
            self.persist)
        ledger.update(status="stopped", stop_reason="unknown_charge_reconciliation_required")
        return ledger

    def test_reviewed_resume_requires_the_exact_settled_ledger_blob(self):
        for expected in (None, "", "different-blob"):
            with self.subTest(expected=expected):
                ledger = self.stopped_settled_ledger()
                prior = copy.deepcopy(ledger)
                with self.assertRaisesRegex(comparison.ComparisonError, "exact_settled_stopped"):
                    comparison.reviewed_resume(ledger, expected, "reviewed-blob", self.persist)
                self.assertEqual(ledger, prior)
        self.post.assert_not_called()

    def test_reviewed_resume_cannot_release_unknown_charges_or_resume_empty_ledger(self):
        unsettled = self.ledger()
        comparison.reserve(unsettled, self.entry(), self.persist)
        unsettled.update(status="stopped", stop_reason="unknown_charge_reconciliation_required")
        empty = self.ledger()
        empty.update(status="stopped", stop_reason="unknown_charge_reconciliation_required")
        for ledger in (unsettled, empty):
            with self.assertRaisesRegex(comparison.ComparisonError, "exact_settled_stopped"):
                comparison.reviewed_resume(ledger, "reviewed-blob", "reviewed-blob", self.persist)
        self.post.assert_not_called()

    def test_reviewed_resume_preserves_attempt_ids_cost_and_the_original_cap(self):
        ledger = self.stopped_settled_ledger(amount=29.9)
        entries = copy.deepcopy(ledger["entries"])
        authorization = ledger["authorization_id"]
        comparison.reviewed_resume(ledger, "reviewed-blob", "reviewed-blob", self.persist)
        self.assertEqual(ledger["status"], "running")
        self.assertEqual(ledger["entries"], entries)
        self.assertEqual(ledger["authorization_id"], authorization)
        self.assertEqual(ledger["limit_cny"], 30.0)
        self.assertEqual(comparison.cost(ledger), 29.9)
        self.assertNotIn("stop_reason", ledger)
        review = ledger["operator_reviews"][-1]
        self.assertEqual(review["reviewed_ledger_blob_sha"], "reviewed-blob")
        self.assertIs(review["generation_retry_authorized"], False)
        self.assertEqual(comparison.run_one(ledger, self.route, self.case_id,
            "screening", self.persist), "already_attempted")
        self.assertFalse(comparison.reserve(ledger, self.entry(amount=0.2,
            case_id=self.route["screening_cases"][1]), self.persist))
        self.post.assert_not_called()

    def test_reviewed_resume_does_not_reopen_closed_trials_or_other_stop_reasons(self):
        for status, reason in (("closed", "unknown_charge_reconciliation_required"),
                               ("stopped", "actual_debit_exceeded_reserved_bound"),
                               ("running", "unknown_charge_reconciliation_required")):
            with self.subTest(status=status, reason=reason):
                ledger = self.stopped_settled_ledger()
                ledger.update(status=status, stop_reason=reason)
                prior = copy.deepcopy(ledger)
                with self.assertRaisesRegex(comparison.ComparisonError, "exact_settled_stopped"):
                    comparison.reviewed_resume(ledger, "reviewed-blob", "reviewed-blob", self.persist)
                self.assertEqual(ledger, prior)
        self.post.assert_not_called()

    def test_outstanding_reservation_blocks_resumed_execute(self):
        ledger = self.ledger()
        comparison.reserve(ledger, self.entry(), self.persist)
        with self.assertRaisesRegex(comparison.ComparisonError, "unknown_charge"):
            comparison.execute(self.plan, ledger, self.persist)
        self.post.assert_not_called()

    def test_actual_debit_above_hold_stops_and_preserves_full_debit(self):
        ledger = self.ledger()
        entry = self.entry(amount=1.0)
        comparison.reserve(ledger, entry, self.persist)
        with self.assertRaisesRegex(comparison.ComparisonError, "actual_debit_exceeded"):
            comparison.settle_entry(ledger, entry,
                {"actual_cost_cny": 1.2, "debit_evidence": {"source": "fake meter"}}, self.persist)
        self.assertEqual(ledger["status"], "stopped")
        self.assertEqual(entry["actual_cost_cny"], 1.2)
        self.assertEqual(comparison.cost(ledger), 1.2)

    def test_malformed_actual_debits_cannot_release_reservations(self):
        for amount in (-1, float("nan"), float("inf"), True):
            with self.subTest(amount=amount):
                ledger = self.ledger()
                entry = self.entry()
                comparison.reserve(ledger, entry, self.persist)
                with self.assertRaises(comparison.ComparisonError):
                    comparison.settle_entry(ledger, entry,
                        {"actual_cost_cny": amount, "debit_evidence": {"source": "fake meter"}}, self.persist)
                self.assertEqual(entry["billing_status"], "reserved")

    def test_changed_plan_cannot_create_a_fresh_allowance_on_resume(self):
        ledger = self.ledger()
        changed = copy.deepcopy(self.plan)
        changed["authorization"] += " modified"
        with self.assertRaisesRegex(comparison.ComparisonError, "authorization_mismatch"):
            comparison.execute(changed, ledger, self.persist)
        self.post.assert_not_called()

    def test_authorization_and_route_limits_are_validated(self):
        self.assertIs(comparison.validate_plan(self.plan), self.plan)
        mutations = (("budget_cny", 31.0), ("trial_id", gateway_trial.TRIAL),
                     ("execution", "local"), ("closed_prior_trial_id", "replacement"))
        for field, value in mutations:
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan)
                plan[field] = value
                with self.assertRaises(comparison.ComparisonError):
                    comparison.validate_plan(plan)
        for field, value in (("max_output_tokens", 32768), ("timeout", 600),
                             ("model", "unapproved-model"), ("effort", "unsupported")):
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan)
                plan["candidates"][0][field] = value
                with self.assertRaises(comparison.ComparisonError):
                    comparison.validate_plan(plan)

    def test_fixture_drift_invalidates_existing_ledger(self):
        ledger = self.ledger()
        definitions = list(copy.deepcopy(self.definitions).values())
        definitions[0]["prompt"] += " changed fixture"
        with patch.object(comparison.fixtures, "cases", return_value=definitions):
            with self.assertRaisesRegex(comparison.ComparisonError, "authorization_mismatch"):
                comparison.validate_ledger(ledger, self.plan)

    def test_attempt_id_case_and_case_hash_cannot_be_rebound(self):
        for field, value in (("call_id", "another-candidate|" + self.case_id),
                             ("case_id", "unknown_fixture"),
                             ("case_sha256", "0" * 64)):
            with self.subTest(field=field):
                ledger = self.ledger()
                entry = self.entry()
                comparison.reserve(ledger, entry, self.persist)
                entry[field] = value
                with self.assertRaisesRegex(comparison.ComparisonError, "fixture_binding"):
                    comparison.validate_ledger(ledger, self.plan)

    def test_duplicate_attempts_and_changed_route_are_rejected(self):
        ledger = self.ledger()
        entry = self.entry()
        comparison.reserve(ledger, entry, self.persist)
        ledger["entries"].append(copy.deepcopy(entry))
        with self.assertRaisesRegex(comparison.ComparisonError, "duplicate_or_unknown"):
            comparison.validate_ledger(ledger, self.plan)
        ledger["entries"].pop()
        entry["model"] = "unapproved-model"
        with self.assertRaisesRegex(comparison.ComparisonError, "route_changed"):
            comparison.validate_ledger(ledger, self.plan)

    def test_phase_lists_and_route_fixture_scope_are_bound(self):
        for field, value in (("screening_cases", ["unknown"]),
                             ("focused_cases", ["code_statistics", "code_statistics"])):
            with self.subTest(field=field):
                plan = copy.deepcopy(self.plan)
                plan[field] = value
                with self.assertRaisesRegex(comparison.ComparisonError, "phase_scope"):
                    comparison.validate_plan(plan)
        for field, value in (("screening_cases", []),
                             ("focused_cases", ["code_statistics", "code_statistics"]),
                             ("focused_cases", ["unknown"])):
            with self.subTest(route_field=field, value=value):
                plan = copy.deepcopy(self.plan)
                plan["candidates"][0][field] = value
                with self.assertRaisesRegex(comparison.ComparisonError, "unknown_fixture"):
                    comparison.validate_plan(plan)

    def test_read_only_metadata_retry_never_retries_generation(self):
        with (patch.object(relay_billing, "read_meter", side_effect=[
                relay_billing.BillingReconciliationError("HTTP 429"), {"ok": True}]) as read,
              patch.object(comparison.time, "sleep") as sleep):
            result = self.read_meter_impl(self.route["provider"])
        self.assertEqual(result, {"ok": True})
        self.assertEqual(read.call_count, 2)
        sleep.assert_called_once_with(20)
        self.post.assert_not_called()

    def test_summary_does_not_promote_routes_or_claim_scientific_equivalence(self):
        report = comparison.summary(self.ledger(), self.plan)
        self.assertEqual(report["attempts"], 0)
        self.assertIs(report["production_routing_changed"], False)
        self.assertIs(report["scientific_equivalence_verified"], False)
        self.assertIs(report["unattempted_are_unknown_not_failed"], True)

    def authorize_full(self, ledger=None):
        ledger = self.ledger() if ledger is None else ledger
        comparison.authorize_complete(self.plan, ledger, "reviewed-blob", "reviewed-blob",
            comparison.FULL_AUTHORIZATION, self.persist)
        return ledger

    def test_full_matrix_authorization_requires_new_id_and_exact_existing_blob(self):
        for authorization, expected in ((comparison.AUTHORIZATION, "reviewed-blob"),
                                        (comparison.FULL_AUTHORIZATION, "different-blob"),
                                        (comparison.FULL_AUTHORIZATION, None)):
            with self.subTest(authorization=authorization, expected=expected):
                ledger = self.ledger()
                before = copy.deepcopy(ledger)
                with self.assertRaisesRegex(comparison.ComparisonError, "explicit_authorization_and_exact"):
                    comparison.authorize_complete(self.plan, ledger, expected, "reviewed-blob",
                        authorization, self.persist)
                self.assertEqual(ledger, before)
        self.post.assert_not_called()

    def test_full_matrix_appends_finite_derived_scope_without_resetting_original_trial(self):
        ledger = self.stopped_settled_ledger(amount=29.9)
        original = copy.deepcopy(ledger["entries"])
        plan = copy.deepcopy(self.plan)
        self.authorize_full(ledger)
        extension = ledger["full_matrix_authorization"]
        contract = extension["scope_contract"]
        self.assertEqual(ledger["limit_cny"], 30.0)
        self.assertEqual(ledger["authorization_id"], comparison.AUTHORIZATION)
        self.assertEqual(ledger["entries"], original)
        self.assertEqual(self.plan, plan)
        self.assertEqual(extension["original_entries_sha256"], comparison.digest(original))
        self.assertEqual(contract["max_calls"], 128)
        self.assertLessEqual(contract["task_count"], 128)
        self.assertEqual(contract["ceiling_cny"], round(sum(contract["task_ceiling_cny"].values()), 8))
        self.assertGreater(comparison.effective_limit(ledger), 30.0)
        comparison.validate_ledger(ledger, self.plan)
        snapshot = copy.deepcopy(ledger)
        self.assertFalse(comparison.authorize_complete(self.plan, ledger,
            "new-current-blob", "new-current-blob", comparison.FULL_AUTHORIZATION, self.persist))
        self.assertEqual(ledger, snapshot)
        self.post.assert_not_called()

    def test_full_scope_cannot_accept_arbitrary_ceiling_quote_or_frozen_prefix_changes(self):
        ledger = self.authorize_full(self.stopped_settled_ledger())
        for change in ("ceiling", "quote", "prefix", "max_calls"):
            with self.subTest(change=change):
                changed = copy.deepcopy(ledger)
                extension = changed["full_matrix_authorization"]
                if change == "ceiling":
                    extension["scope_contract"]["ceiling_cny"] = 999999.0
                elif change == "quote":
                    extension["scope_contract"]["quote_sha256_by_candidate"][self.route["id"]] = "other"
                elif change == "max_calls":
                    extension["scope_contract"]["max_calls"] = 100000
                else:
                    changed["entries"][0]["actual_cost_cny"] = 0.01
                with self.assertRaises(comparison.ComparisonError):
                    comparison.validate_ledger(changed, self.plan)

    def test_existing_unknown_charge_is_retained_and_only_its_provider_is_isolated(self):
        ledger = self.ledger()
        entry = self.entry()
        comparison.reserve(ledger, entry, self.persist)
        ledger.update(status="stopped", stop_reason="unknown_charge_reconciliation_required")
        before = copy.deepcopy(ledger["entries"])
        self.authorize_full(ledger)
        self.assertEqual(ledger["entries"], before)
        self.assertEqual(comparison.cost(ledger), 2.0)
        self.assertIn(self.route["provider"], ledger["isolated_providers"])
        other = next(route for route in self.plan["candidates"] if route["provider"] != self.route["provider"])
        self.assertEqual(comparison.run_one(ledger, self.route, self.route["screening_cases"][1],
            "screening", self.persist), "quarantined_no_generation")
        self.assertEqual(comparison.run_one(ledger, other, self.case_id,
            "screening", self.persist), "completed")
        self.post.assert_called_once()
        self.assertEqual(comparison.cost(ledger), 2.12)
        comparison.validate_ledger(ledger, self.plan)

    def test_new_unknown_bill_is_held_without_retry_and_other_providers_continue(self):
        ledger = self.authorize_full()
        self.settle.side_effect = [relay_billing.BillingReconciliationError("unknown debit"), self.settlement]
        self.assertEqual(comparison.run_one(ledger, self.route, self.case_id,
            "screening", self.persist), "unknown_charge_isolated_full_hold_retained")
        self.assertEqual(ledger["status"], "running")
        self.assertEqual(comparison.cost(ledger), 2.0)
        self.assertEqual(ledger["entries"][0]["billing_status"], "reserved")
        same_provider = next(route for route in self.plan["candidates"]
            if route["provider"] == self.route["provider"] and route["id"] != self.route["id"])
        self.assertEqual(comparison.run_one(ledger, same_provider, self.case_id,
            "screening", self.persist), "isolated_provider_no_generation")
        self.assertEqual(comparison.run_one(ledger, self.route, self.case_id,
            "screening", self.persist), "quarantined_no_generation")
        other = next(route for route in self.plan["candidates"] if route["provider"] != self.route["provider"])
        self.assertEqual(comparison.run_one(ledger, other, self.case_id,
            "screening", self.persist), "completed")
        self.assertEqual(self.post.call_count, 2)
        self.assertEqual(comparison.cost(ledger), 2.12)
        comparison.validate_ledger(ledger, self.plan)

    def test_authorization_persistence_failure_prevents_any_generation(self):
        ledger = self.ledger()
        def fail(_):
            raise OSError("scope approval was not persisted")
        with self.assertRaises(OSError):
            comparison.authorize_complete(self.plan, ledger, "reviewed-blob", "reviewed-blob",
                comparison.FULL_AUTHORIZATION, fail)
        self.post.assert_not_called()

    def test_full_scope_skips_unsupported_media_in_derived_task_count(self):
        item = self.definitions["visual_chart"]
        item["attachments"] = [{"mime_type": "image/png", "sha256": "fake", "data_base64": "fake"}]
        ledger = self.authorize_full()
        tasks = ledger["full_matrix_authorization"]["scope_contract"]["task_ceiling_cny"]
        for route in self.plan["candidates"]:
            if "visual_chart" not in route["focused_cases"]:
                continue
            present = route["id"] + "|visual_chart" in tasks
            self.assertEqual(present, ai_providers.provider_family(route["provider"]) in {"openai", "google"})

    def test_full_scope_runs_diagnostic_focus_despite_failed_screen_and_closes_with_holds(self):
        ledger = self.ledger()
        entry = self.entry()
        comparison.reserve(ledger, entry, self.persist)
        ledger.update(status="stopped", stop_reason="unknown_charge_reconciliation_required")
        self.authorize_full(ledger)
        with (patch.object(comparison, "qualified", return_value=False),
              patch.object(comparison, "run_one", return_value="diagnostic-fixture") as run):
            comparison.execute(self.plan, ledger, self.persist)
        self.assertEqual(ledger["status"], "closed_with_holds")
        self.assertTrue(any(call.args[3] == "focused" for call in run.call_args_list))
        self.assertEqual(comparison.cost(ledger), 2.0)
        report = comparison.summary(ledger, self.plan)
        self.assertEqual(report["outstanding_held_cny"], 2.0)
        self.assertIs(report["scientific_equivalence_verified"], False)
        self.assertIs(report["production_routing_changed"], False)

    def test_full_matrix_rejects_attempts_outside_pinned_task_and_quote_scope(self):
        ledger = self.authorize_full()
        entry = self.entry()
        entry["quote_sha256"] = "wrong-quote"
        with self.assertRaisesRegex(comparison.ComparisonError, "outside_approved_full_matrix"):
            comparison.reserve(ledger, entry, self.persist)
        entry["quote_sha256"] = "q" * 64
        entry["reserved_ceiling_cny"] = 1000.0
        with self.assertRaisesRegex(comparison.ComparisonError, "outside_approved_full_matrix"):
            comparison.reserve(ledger, entry, self.persist)
        self.post.assert_not_called()


class ComparisonCloudStateTests(unittest.TestCase):
    OLD_SHA = "a" * 40

    def state(self, *, sha=OLD_SHA):
        state = comparison.CloudState("fake-nonsecret-token")
        with patch.object(gateway_trial.CloudState, "read", return_value=({"entries": []}, sha)):
            state.load()
        return state

    def blob(self, ledger):
        raw = (json.dumps(ledger, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
        sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        return {"sha": sha, "encoding": "base64", "size": len(raw),
                "content": base64.b64encode(raw).decode()}

    def test_cas_conflict_is_terminal_without_generation(self):
        state = self.state()
        with (patch.object(state, "api", side_effect=gateway_trial.TrialError("http_409")) as api,
              patch.object(ai_providers, "call_production") as post):
            with self.assertRaises(gateway_trial.TrialError):
                state.save({"entries": []})
        self.assertEqual(api.call_args.args[2], "PUT")
        self.assertEqual(api.call_args.args[1]["sha"], self.OLD_SHA)
        post.assert_not_called()

    def test_write_requires_prior_read_and_durable_exact_readback(self):
        state = comparison.CloudState("fake-nonsecret-token")
        with self.assertRaisesRegex(comparison.ComparisonError, "ledger_read_required"):
            state.save({"entries": []})
        state = self.state()
        ledger = {"entries": [{"call_id": "fixture", "reserved_ceiling_cny": 1.0}]}
        wrong = self.blob({"entries": []})
        with patch.object(state, "api", side_effect=[{"content": {"sha": wrong["sha"]}}, wrong]):
            with self.assertRaisesRegex(comparison.ComparisonError, "readback_mismatch"):
                state.save(ledger)
        self.assertEqual(state.expected_sha, self.OLD_SHA)

    def test_successful_cas_save_targets_only_new_trial_namespace(self):
        state = self.state()
        ledger = {"entries": []}
        blob = self.blob(ledger)
        with (patch.object(state, "api", side_effect=[{"content": {"sha": blob["sha"]}}, blob]) as api,
              patch.object(gateway_trial.CloudState, "read", side_effect=AssertionError("mutable tree readback forbidden"))):
            state.save(ledger)
        path, payload, method = api.call_args_list[0].args
        self.assertEqual(path, "contents/trial-state/" + comparison.FILE)
        self.assertEqual(payload["branch"], comparison.STATE)
        self.assertNotEqual(payload["branch"], gateway_trial.STATE)
        self.assertEqual(method, "PUT")
        self.assertEqual(json.loads(base64.b64decode(payload["content"])), ledger)
        self.assertEqual(api.call_args_list[1].args, ("git/blobs/" + blob["sha"],))
        self.assertEqual(state.expected_sha, blob["sha"])

    def test_missing_or_unreadable_immutable_blob_keeps_the_prior_expected_sha(self):
        ledger = {"entries": []}
        blob = self.blob(ledger)
        for response in (gateway_trial.TrialError("http_404"),
                         {"sha": blob["sha"], "encoding": "base64", "content": "not-base64!"}):
            with self.subTest(response_type=type(response).__name__):
                state = self.state()
                with (patch.object(state, "api", side_effect=[{"content": {"sha": blob["sha"]}}, response]),
                      patch.object(ai_providers, "call_production") as post):
                    with self.assertRaises((comparison.ComparisonError, gateway_trial.TrialError)):
                        state.save(ledger)
                self.assertEqual(state.expected_sha, self.OLD_SHA)
                post.assert_not_called()

    def test_immutable_blob_must_match_the_sha_returned_by_the_successful_put(self):
        state = self.state()
        ledger = {"entries": []}
        blob = self.blob(ledger)
        bad = dict(blob, sha="b" * 40)
        with patch.object(state, "api", side_effect=[{"content": {"sha": blob["sha"]}}, bad]):
            with self.assertRaisesRegex(comparison.ComparisonError, "readback_mismatch"):
                state.save(ledger)
        self.assertEqual(state.expected_sha, self.OLD_SHA)


if __name__ == "__main__":
    unittest.main()
