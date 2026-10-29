"""No credentials or paid calls: exact trial scope, all attempts and billing holds."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from scripts import ai_providers, relay_billing, model_evaluation_20261029 as trial


ROOT = Path(__file__).resolve().parents[1]
ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "hengyizang/lunwen",
    "GITHUB_REF": "refs/heads/" + trial.BRANCH, "GITHUB_ACTOR": "hengyizang", "GITHUB_EVENT_NAME": "workflow_dispatch",
    "MODEL_EVALUATION_AUTHORIZATION": trial.AUTHORIZATION, "GH_TOKEN": "synthetic-fixture-only",
    "GITHUB_RUN_ID": "123456", "GITHUB_SHA": "a" * 40}


def plan():
    value = json.loads((ROOT / trial.PLAN).read_text(encoding="utf-8"))
    # A finite subset lets control tests remain independent of live catalogs.
    value["routes"] = [{"id": "sol-high", "provider": "cheapai-gpt-pro", "model": "gpt-6.1-sol", "effort": "high"},
        {"id": "astra-high", "provider": "cheapai-gpt-pro", "model": "gpt-6-astra", "effort": "high"}]
    return value


def scope(value):
    with patch.dict(os.environ, {"GITHUB_SHA": ENV["GITHUB_SHA"]}), \
            patch.object(trial.billing_quotes, "select", return_value={"quote_sha256": "b" * 64}), \
            patch.object(trial.model_runtime, "reservation_bound", return_value=1.0):
        return trial.freeze_scope(value)


class MemoryState:
    def __init__(self, ledger=None):
        self.ledger = copy.deepcopy(ledger)
        self.writes = []

    def load(self, name):
        return copy.deepcopy(self.ledger)

    def save(self, name, value):
        self.ledger = copy.deepcopy(value)
        self.writes.append(copy.deepcopy(value))


class FakeBudget:
    def __init__(self):
        self.control = {"authorized_ceiling_cny": 500, "spent_cny": .0873256, "reservations": {
            trial.GEMINI_LEGACY_ID: {"kind": "retained_legacy", "max_cost_cny": trial.GEMINI_LEGACY_CNY,
                "writing_trial": "writing-comparison-20261027"}}}
        self.reserves, self.settlements = [], []

    def refresh(self):
        return copy.deepcopy(self.control)

    def reserve(self, amount, *, kind="new_call", call_id=None):
        identity = f"{len(self.reserves) + 1:032x}"
        self.reserves.append({"id": identity, "amount": amount, "kind": kind, "call_id": call_id})
        self.control["reservations"][identity] = {"max_cost_cny": amount, "kind": kind,
            "writing_trial": trial.TRIAL, "call_id": call_id}
        return identity

    def settle(self, identity, amount):
        self.control["reservations"].pop(identity)
        self.control["spent_cny"] += amount
        self.settlements.append((identity, amount))


class ModelEvaluationTrialTests(unittest.TestCase):
    def setUp(self):
        self.value = plan()

    def test_plan_queue_is_finite_source_bound_and_has_no_automatic_promotion(self):
        self.assertIs(trial.validate_plan(self.value), self.value)
        frozen = scope(self.value)
        self.assertEqual(len(frozen["queue"]), 12)
        self.assertEqual(len({c["call_id"] for c in frozen["queue"]}), 12)
        self.assertEqual(frozen["project_ceiling_cny"], 500)
        self.assertEqual(frozen["max_calls"], 40)
        self.assertEqual(frozen["code_sha"], ENV["GITHUB_SHA"])
        self.assertFalse(frozen["automatic_promotion"])
        self.assertFalse(frozen["scientific_equivalence_verified"])
        self.assertIn("BEGIN SOURCE DATA\n", trial.prompt(self.value["cases"][0]))

    def test_subset_effort_routes_keep_distinct_ids_and_exact_case_scope(self):
        self.value["routes"][1] = {"id": "sol-medium", "provider": "cheapai-gpt-pro", "model": "gpt-6.1-sol", "effort": "medium",
            "case_ids": [c["id"] for c in self.value["cases"] if c["partition"] == "calibration"]}
        frozen = scope(self.value)
        self.assertEqual(len(frozen["queue"]), 9)
        self.assertEqual(sum(c["route_id"] == "sol-medium" for c in frozen["queue"]), 3)

    def test_unscoped_route_unknown_model_duplicate_case_and_changed_budget_are_rejected(self):
        mutations = [lambda p: p.update(project_ceiling_cny=999), lambda p: p.update(max_calls=41),
            lambda p: p.update(automatic_promotion=True), lambda p: p["routes"][0].update(provider="uuapi-openai"),
            lambda p: p["routes"][0].update(model="unknown-model"), lambda p: p["routes"][0].update(effort="invented"),
            lambda p: p["routes"][0].update(case_ids=["source-extraction", "source-extraction"]),
            lambda p: p["routes"][0].update(endpoint="https://unapproved.invalid"), lambda p: p["routes"].append(copy.deepcopy(p["routes"][0]))]
        for mutate in mutations:
            value = copy.deepcopy(self.value)
            mutate(value)
            with self.subTest(value=value["routes"]), self.assertRaises(ValueError):
                trial.validate_plan(value)

    def test_actual_supplemental_quote_and_cache_bound_match_exact_registered_endpoints(self):
        with patch.dict(os.environ, {"GITHUB_SHA": ENV["GITHUB_SHA"]}):
            frozen = trial.freeze_scope(self.value)
        self.assertTrue(all(0 < c["reserved_ceiling_cny"] <= 500 for c in frozen["queue"]))
        self.assertTrue(all(q["quote_schema"] == "2.0" for q in frozen["quotes"].values()))
        self.assertEqual({q["provider"] for q in frozen["quotes"].values()}, {"cheapai-gpt-pro"})

    def test_scope_requires_valid_code_revision_and_changed_code_cannot_resume(self):
        for revision in ("", "main", "a" * 39, "G" * 40):
            with self.subTest(revision=revision), patch.dict(os.environ, {"GITHUB_SHA": revision}), \
                    self.assertRaisesRegex(ValueError, "valid cloud code revision"):
                trial.freeze_scope(self.value)
        frozen = scope(self.value)
        state = MemoryState({"trial_id": trial.TRIAL, "scope": frozen, "status": "running", "entries": []})
        with patch.dict(os.environ, {**ENV, "GITHUB_SHA": "c" * 40}, clear=True), \
                patch.object(trial.billing_quotes, "select", return_value={"quote_sha256": "b" * 64}), \
                patch.object(trial.model_runtime, "reservation_bound", return_value=1.0), \
                patch.object(trial.writing_comparison, "Budget") as budget, \
                patch.object(trial.ai_providers, "call_production") as generate:
            with self.assertRaisesRegex(ValueError, "scope changed"):
                trial.execute(self.value, state)
            budget.assert_not_called()
            generate.assert_not_called()
            self.assertFalse(state.writes)

    def test_unauthorized_execute_has_no_budget_catalog_guard_or_generation(self):
        for field in ("GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_REF", "GITHUB_ACTOR", "GITHUB_EVENT_NAME", "MODEL_EVALUATION_AUTHORIZATION"):
            with self.subTest(field=field), patch.dict(os.environ, {**ENV, field: "wrong"}, clear=True), \
                    patch.object(trial, "freeze_scope") as freeze, patch.object(trial.writing_comparison, "Budget") as budget, \
                    patch.object(trial.ai_providers, "call_production") as generate:
                with self.assertRaises(ValueError):
                    trial.execute(self.value, MemoryState())
                freeze.assert_not_called()
                budget.assert_not_called()
                generate.assert_not_called()

    def test_closed_or_stopped_trial_never_reopens_and_scope_changes_never_reset(self):
        frozen = scope(self.value)
        for status in ("closed", "stopped"):
            state = MemoryState({"trial_id": trial.TRIAL, "scope": frozen, "status": status, "entries": []})
            with patch.dict(os.environ, ENV, clear=True), patch.object(trial, "freeze_scope", return_value=frozen), \
                    patch.object(trial.writing_comparison, "Budget") as budget:
                self.assertEqual(trial.execute(self.value, state)["status"], status)
                budget.assert_not_called()
                self.assertFalse(state.writes)
        state.ledger["scope"]["plan_sha256"] = "f" * 64
        with patch.dict(os.environ, ENV, clear=True), patch.object(trial, "freeze_scope", return_value=frozen), self.assertRaisesRegex(ValueError, "scope changed"):
            trial.execute(self.value, state)

    def test_old_gemini_and_deepseek_holds_remain_reserved_exactly_once(self):
        budget = FakeBudget()
        original = copy.deepcopy(budget.control["reservations"][trial.GEMINI_LEGACY_ID])
        first = trial._legacy_budget(budget)
        self.assertEqual(trial._legacy_budget(budget), first)
        self.assertEqual(len(budget.reserves), 1)
        self.assertEqual(budget.reserves[0]["amount"], trial.DEEPSEEK_LEGACY_CNY)
        self.assertEqual(budget.control["reservations"][trial.GEMINI_LEGACY_ID], original)
        budget.control["reservations"]["unknown"] = {"max_cost_cny": 1, "kind": "unresolved"}
        with self.assertRaisesRegex(ValueError, "outstanding"):
            trial._legacy_budget(budget)

    def run_trial(self, *, failures=(), unknown_billing=False, omit_model=False):
        frozen = scope(self.value)
        state, budget = MemoryState(), FakeBudget()
        legacy = trial._legacy_budget(budget)
        calls = []

        def generate(provider, text, **kwargs):
            # Durable central/ledger reservation and shared ticket must precede transport.
            self.assertEqual(state.ledger["entries"][-1]["billing_status"], "reserved")
            self.assertIn(state.ledger["entries"][-1]["project_reservation_id"], budget.control["reservations"])
            calls.append(kwargs["model"])
            if kwargs["model"] in failures:
                error = ai_providers.ProviderError("production response model ID missing or mismatched; quarantine route and reconcile billing")
                error.reported_model = None
                raise error
            return ai_providers.ModelResult(provider, kwargs["model"], "Source-bound synthetic response.",
                {"input_tokens": 10, "output_tokens": 5}, reported_model=None if omit_model else kwargs["model"],
                completion_status="completed", endpoint="https://cheapai.info/v1/responses", protocol="openai_responses")

        settlement = {"actual_cost_cny": .001, "debit_evidence": {"exactly_one_new_gateway_request": True}}
        with patch.dict(os.environ, ENV, clear=True), patch.object(trial, "freeze_scope", return_value=frozen), \
                patch.object(trial.writing_comparison, "Budget", return_value=budget), \
                patch.object(trial.production_readiness, "catalog", return_value={"gpt-6.1-sol", "gpt-6-astra"}), \
                patch.object(trial.relay_billing, "read_meter", return_value={"provider": "cheapai-gpt-pro", "kind": "synthetic"}), \
                patch.object(trial.relay_guard, "begin", return_value={"id": "synthetic-ticket"}) as begin, \
                patch.object(trial.relay_guard, "bind_meter") as bind, patch.object(trial.relay_guard, "finish") as finish, \
                patch.object(trial.ai_providers, "call_production", side_effect=generate), \
                patch.object(trial.relay_billing, "settle", side_effect=relay_billing.BillingReconciliationError("unconfirmed debit") if unknown_billing else None,
                    return_value=settlement):
            result = trial.execute(self.value, state)
        return result, state, budget, calls, begin, bind, finish, legacy

    def test_every_success_is_single_attempt_settled_and_remaining_legacy_holds_untouched(self):
        result, state, budget, calls, begin, bind, finish, legacy = self.run_trial()
        self.assertEqual(result["status"], "closed")
        self.assertEqual(len(calls), 12)
        self.assertEqual(len(result["entries"]), 12)
        self.assertEqual(len({r["call_id"] for r in result["entries"]}), 12)
        self.assertTrue(all(r["billing_status"] == "settled" for r in result["entries"]))
        self.assertEqual(set(budget.control["reservations"]), set(legacy.values()))
        self.assertEqual(begin.call_count, 12)
        self.assertEqual(bind.call_count, 12)
        self.assertEqual(finish.call_count, 12)
        self.assertFalse(result["automatic_promotion"])

    def test_settled_identity_failure_is_charged_quarantines_only_exact_route_and_other_route_continues(self):
        result, _, budget, calls, *rest = self.run_trial(failures={"gpt-6.1-sol"})
        self.assertEqual(result["status"], "closed")
        self.assertEqual(calls.count("gpt-6.1-sol"), 1)
        self.assertEqual(calls.count("gpt-6-astra"), 6)
        first = result["entries"][0]
        self.assertEqual(first["generation_status"], "failed")
        self.assertEqual(first["billing_status"], "settled")
        self.assertEqual(first["actual_cost_cny"], .001)
        self.assertEqual(first["reported_model_unverified"], "missing")
        self.assertEqual(result["quarantined_routes"], ["sol-high"])
        self.assertEqual(len(result["unattempted_call_ids"]), 5)
        self.assertEqual(len(budget.settlements), 7)

    def test_missing_identity_cannot_be_accepted_even_when_transport_mock_returns_text(self):
        result, _, _, calls, *rest = self.run_trial(omit_model=True)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(r["generation_status"] == "failed" for r in result["entries"]))
        self.assertTrue(all("text" not in r for r in result["entries"]))

    def test_new_unknown_charge_stops_all_routes_and_retains_full_new_reservation(self):
        result, _, budget, calls, begin, bind, finish, legacy = self.run_trial(unknown_billing=True)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["entries"][0]["billing_status"], "reserved")
        self.assertEqual(len(budget.control["reservations"]), 3)
        self.assertFalse(budget.settlements)
        finish.assert_not_called()

    def test_interrupted_prior_attempt_is_never_replayed(self):
        frozen = scope(self.value)
        state = MemoryState({"trial_id": trial.TRIAL, "scope": frozen, "status": "running",
            "entries": [{"call_id": frozen["queue"][0]["call_id"], "billing_status": "reserved"}]})
        with patch.dict(os.environ, ENV, clear=True), patch.object(trial, "freeze_scope", return_value=frozen), \
                patch.object(trial.writing_comparison, "Budget") as budget, patch.object(trial.ai_providers, "call_production") as generate:
            self.assertEqual(trial.execute(self.value, state)["status"], "stopped")
            budget.assert_not_called()
            generate.assert_not_called()

    def test_resume_restores_failed_route_quarantine_before_any_new_transport(self):
        frozen = scope(self.value)
        budget = FakeBudget()
        legacy = trial._legacy_budget(budget)
        failed = {"call_id": frozen["queue"][0]["call_id"], "route_id": "sol-high",
            "case_id": self.value["cases"][0]["id"], "generation_status": "failed", "billing_status": "settled",
            "actual_cost_cny": .001, "reserved_ceiling_cny": 1.0}
        state = MemoryState({"trial_id": trial.TRIAL, "scope": frozen, "status": "running",
            "entries": [failed], "legacy_budget_reservations": legacy, "quarantined_routes": []})
        calls = []

        def generate(provider, text, **kwargs):
            self.assertEqual(state.ledger["quarantined_routes"], ["sol-high"])
            self.assertEqual(state.writes[0]["quarantined_routes"], ["sol-high"])
            self.assertEqual(state.writes[0]["entries"], [failed])
            calls.append(kwargs["model"])
            return ai_providers.ModelResult(provider, kwargs["model"], "Source-bound synthetic response.",
                {"input_tokens": 10, "output_tokens": 5}, reported_model=kwargs["model"],
                completion_status="completed", endpoint="https://cheapai.info/v1/responses", protocol="openai_responses")

        with patch.dict(os.environ, ENV, clear=True), patch.object(trial, "freeze_scope", return_value=frozen), \
                patch.object(trial.writing_comparison, "Budget", return_value=budget), \
                patch.object(trial.production_readiness, "catalog", return_value={"gpt-6.1-sol", "gpt-6-astra"}), \
                patch.object(trial.relay_billing, "read_meter", return_value={"provider": "cheapai-gpt-pro", "kind": "synthetic"}), \
                patch.object(trial.relay_guard, "begin", return_value={"id": "synthetic-ticket"}), \
                patch.object(trial.relay_guard, "bind_meter"), patch.object(trial.relay_guard, "finish"), \
                patch.object(trial.ai_providers, "call_production", side_effect=generate), \
                patch.object(trial.relay_billing, "settle", return_value={"actual_cost_cny": .001,
                    "debit_evidence": {"exactly_one_new_gateway_request": True}}):
            result = trial.execute(self.value, state)
        self.assertEqual(result["status"], "closed")
        self.assertEqual(calls, ["gpt-6-astra"] * 6)
        self.assertEqual(result["entries"][0], failed)
        self.assertEqual(len(result["unattempted_call_ids"]), 5)
        self.assertEqual(set(budget.control["reservations"]), set(legacy.values()))

    def test_fixture_checks_are_not_quality_scores_and_distinguish_false_from_zero(self):
        case = self.value["cases"][0]
        value = case["checks"]["expected_json"]
        text = json.dumps(value)
        checks = trial.mechanical_checks(case, text)
        self.assertTrue(all(checks["expected_json"].values()))
        self.assertNotIn("quality_score", checks)
        value = dict(value, causal_effect_established=0)
        self.assertFalse(trial.mechanical_checks(case, json.dumps(value))["expected_json"]["causal_effect_established"])


if __name__ == "__main__":
    unittest.main()

