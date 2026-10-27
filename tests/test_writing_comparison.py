"""Bounded writing evaluation authority and source controls; no external calls."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import relay_guard, writing_comparison as trial


ROOT = Path(__file__).resolve().parents[1]


def source_plan():
    return json.loads((ROOT / "config/writing-comparison-20261027.json").read_text(encoding="utf-8"))


def scope_for(plan):
    with patch.object(trial.model_runtime, "pricing", return_value={"quote_sha256": "a" * 64}), \
            patch.object(trial.model_runtime, "reservation_bound", return_value=1.0):
        return trial.freeze_scope(plan)


class WritingComparisonTests(unittest.TestCase):
    def setUp(self):
        self.plan = source_plan()

    def test_real_cases_have_six_independent_sources_and_three_holdouts(self):
        self.assertIs(trial.validate_plan(self.plan), self.plan)
        self.assertEqual(len({case["source"]["doi"] for case in self.plan["cases"]}), 6)
        self.assertEqual(len({case["source"]["id"] for case in self.plan["cases"]}), 6)
        self.assertEqual(sum(case["partition"] == "calibration" for case in self.plan["cases"]), 3)
        self.assertEqual(sum(case["partition"] == "holdout" for case in self.plan["cases"]), 3)
        self.assertFalse(self.plan["scope"]["automatic_routing_promotion"])

    def test_changed_excerpt_duplicate_paper_and_invalid_partition_are_rejected(self):
        mutations = (
            lambda p: p["cases"][0]["source"].update(text="Changed source without updating its evidence seal."),
            lambda p: p["cases"][1]["source"].update(doi=p["cases"][0]["source"]["doi"]),
            lambda p: p["cases"][1]["source"].update(id=p["cases"][0]["source"]["id"]),
            lambda p: p["cases"][0].update(partition="unclassified"),
            lambda p: p["cases"][0].update(partition="holdout"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(self.plan)
                mutate(changed)
                with self.assertRaises(ValueError):
                    trial.validate_plan(changed)

    def test_source_text_is_data_with_exact_citation_label_and_same_prompt(self):
        case = self.plan["cases"][0]
        prompt = trial.prompt(self.plan, case)
        self.assertIn("SOURCE LABEL: [" + case["source"]["id"] + "]", prompt)
        self.assertIn("BEGIN SOURCE DATA\n" + case["source"]["text"] + "\nEND SOURCE DATA", prompt)
        self.assertNotIn("advisory_checks", prompt)
        self.assertIn("untrusted data", self.plan["common_instruction"])

    def test_frozen_scope_has_eighteen_unique_calls_within_thirty_and_no_promotion(self):
        scope = scope_for(self.plan)
        self.assertEqual(len(scope["call_ceilings_cny"]), 18)
        self.assertEqual(scope["max_calls"], 18)
        self.assertEqual(scope["new_call_limit_cny"], 30)
        self.assertEqual(scope["project_ceiling_cny"], 500)
        self.assertEqual(scope["retained_legacy_hold_cny"], 9.5836104)
        self.assertFalse(scope["automatic_promotion"])
        self.assertFalse(scope["production_routing_changed"])
        self.assertEqual({route["model"] for route in scope["routes"]},
                         {"gemini-4-argon-high", "gpt-6.1-sol", "gpt-6-astra"})
        with patch.object(trial.model_runtime, "pricing", return_value={"quote_sha256": "a" * 64}), \
                patch.object(trial.model_runtime, "reservation_bound", return_value=2.0):
            with self.assertRaisesRegex(ValueError, "CNY30"):
                trial.freeze_scope(self.plan)

    def test_unauthorized_execution_stops_before_scope_budget_catalog_or_transport(self):
        cases = ({"GITHUB_ACTOR": "not-the-owner", "WRITING_COMPARISON_AUTHORIZATION": trial.AUTHORIZATION},
                 {"GITHUB_ACTOR": "hengyizang", "WRITING_COMPARISON_AUTHORIZATION": "old-authorization"})
        for environment in cases:
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True), \
                    patch.object(trial, "freeze_scope") as scope, \
                    patch.object(trial, "Budget") as budget, \
                    patch.object(trial.production_readiness, "catalog") as catalog, \
                    patch.object(trial.ai_providers, "call_production") as generate:
                with self.assertRaisesRegex(ValueError, "authorization"):
                    trial.execute(self.plan, Mock())
                scope.assert_not_called()
                budget.assert_not_called()
                catalog.assert_not_called()
                generate.assert_not_called()

    def test_closed_scope_does_not_reopen_reserve_or_generate(self):
        scope = scope_for(self.plan)
        ledger = {"trial_id": trial.TRIAL, "scope": json.loads(json.dumps(scope)),
                  "status": "closed", "entries": []}
        state = Mock()
        state.load.return_value = ledger
        with patch.dict(os.environ, {"GITHUB_ACTOR": "hengyizang", "GH_TOKEN": "synthetic-only",
                "WRITING_COMPARISON_AUTHORIZATION": trial.AUTHORIZATION}, clear=True), \
                patch.object(trial, "freeze_scope", return_value=scope), \
                patch.object(trial, "Budget") as budget, \
                patch.object(trial.production_readiness, "catalog") as catalog, \
                patch.object(trial.ai_providers, "call_production") as generate:
            self.assertIs(trial.execute(self.plan, state), ledger)
            budget.return_value.reserve.assert_not_called()
            catalog.assert_not_called()
            generate.assert_not_called()
            state.save.assert_not_called()

    def test_scope_drift_does_not_reset_existing_allowance(self):
        scope = scope_for(self.plan)
        old_scope = json.loads(json.dumps(scope))
        old_scope["plan_sha256"] = "f" * 64
        state = Mock()
        state.load.return_value = {"trial_id": trial.TRIAL, "scope": old_scope,
                                   "status": "running", "entries": []}
        with patch.dict(os.environ, {"GITHUB_ACTOR": "hengyizang", "GH_TOKEN": "synthetic-only",
                "WRITING_COMPARISON_AUTHORIZATION": trial.AUTHORIZATION}, clear=True), \
                patch.object(trial, "freeze_scope", return_value=scope), \
                patch.object(trial, "Budget") as budget, \
                patch.object(trial.ai_providers, "call_production") as generate:
            with self.assertRaisesRegex(ValueError, "scope changed"):
                trial.execute(self.plan, state)
            budget.return_value.reserve.assert_not_called()
            state.save.assert_not_called()
            generate.assert_not_called()


class WritingTransportAmendmentTests(unittest.TestCase):
    def test_only_exact_reviewed_settled_failure_can_change_transport_without_replay(self):
        scope = scope_for(source_plan())
        original = {"plan_sha256": scope["plan_sha256"], "original_marker": True}
        entry = {"call_id": "argon-high|intro-seaborn", "billing_status": "settled",
                 "generation_status": "failed", "actual_cost_cny": 0.0073388,
                 "diagnostic": "production response model ID missing or mismatched; quarantine route and reconcile billing"}
        ledger = {"scope": original, "entries": [entry], "status": "stopped"}
        saved = copy.deepcopy(entry)
        trial.reviewed_transport_amendment(ledger, scope, trial.REVIEWED_BASE_FAILURE)
        self.assertEqual(ledger["entries"], [saved])
        self.assertEqual(ledger["original_scope"], original)
        self.assertEqual(ledger["status"], "running")
        self.assertEqual(len(scope["call_ceilings_cny"]), 18)
        self.assertNotIn("astra-high|intro-seaborn", scope["call_ceilings_cny"])
        self.assertIn("argon-high|intro-seaborn", scope["call_ceilings_cny"])
        self.assertIn("argon-native-high|intro-seaborn", scope["call_ceilings_cny"])
        with self.assertRaises(ValueError):
            trial.reviewed_transport_amendment(ledger, scope, trial.REVIEWED_BASE_FAILURE)
        ledger["status"] = "stopped"
        ledger["entries"][0]["billing_status"] = "reserved"
        with self.assertRaises(ValueError):
            trial.reviewed_transport_amendment(ledger, scope, trial.REVIEWED_BASE_FAILURE)


class IndependentContinuationTests(unittest.TestCase):
    def ledger(self):
        return {"status": "stopped", "stop_reason": "retained identity failures",
            "entries": [{"call_id": key, "billing_status": "settled", "generation_status": "failed",
                "diagnostic": "production response model ID missing or mismatched"}
                for key in ("argon-high|intro-seaborn", "argon-native-high|intro-seaborn")]}

    def test_settled_identity_failures_only_quarantine_argon_and_preserve_attempts(self):
        ledger = self.ledger()
        original = copy.deepcopy(ledger["entries"])
        trial.continue_independent_routes(ledger, trial.REVIEWED_HIGH_FAILURE)
        self.assertEqual(ledger["entries"], original)
        self.assertEqual(ledger["quarantined_providers"], ["codekey-gemini"])
        self.assertEqual(ledger["status"], "running")
        self.assertNotIn("stop_reason", ledger)

    def test_unknown_charge_or_another_ledger_cannot_resume(self):
        ledger = self.ledger()
        ledger["entries"][1]["billing_status"] = "reserved"
        with self.assertRaises(ValueError):
            trial.continue_independent_routes(ledger, trial.REVIEWED_HIGH_FAILURE)
        with self.assertRaises(ValueError):
            trial.continue_independent_routes(self.ledger(), "f" * 40)


class WritingTrialLegacyExceptionTests(unittest.TestCase):
    def setUp(self):
        self.environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": relay_guard.REPOSITORY,
            "GITHUB_ACTOR": "hengyizang", "GITHUB_REF": "refs/heads/" + trial.BRANCH,
            "GITHUB_EVENT_NAME": "push", "GITHUB_RUN_ID": "test-only",
            "WRITING_COMPARISON_AUTHORIZATION": trial.AUTHORIZATION}
        self.scope = {"trial": trial.TRIAL, "authorization": trial.AUTHORIZATION,
            "call_id": "argon-high|intro-seaborn", "project_reservation_id": "a" * 32,
            "legacy_budget_reservation_id": "b" * 32}
        self.held = {
            "44064d7e5133c1c82704269da0095f60541c12e8c24be1560eac5e67920f46e9":
                {"reserved_ceiling_cny": 0.431508},
            "f6da77fa19739e14aedd1e040301f29d85ee7f899c840b2fd7138cc7dc44b5e9":
                {"reserved_ceiling_cny": 9.1521024}}
        self.value = {"credential_sha256": "c" * 64, "legacy_holds": copy.deepcopy(self.held),
                      "active": None, "events": []}
        self.store = Mock()
        relay_guard._TICKET.set(None)
        self.addCleanup(lambda: relay_guard._TICKET.set(None))

    def begin(self, **kwargs):
        return relay_guard.begin("codekey-gemini", scope=self.scope,
            max_cost_cny=0.5, writing_trial_exception=True, **kwargs)

    def loaded(self):
        return patch.object(relay_guard, "load", return_value=(self.store, "fixture.json", self.value, "old-sha"))

    def test_exact_exception_retains_both_old_holds_and_only_opens_a_new_ticket(self):
        with patch.dict(os.environ, self.environment, clear=True), self.loaded():
            ticket = self.begin()
            self.assertEqual(self.value["legacy_holds"], self.held)
            self.assertEqual(self.value["active"], ticket)
            self.assertFalse(relay_guard._TICKET.get()["sent"])
            self.store.write.assert_called_once()

    def test_exception_never_authorizes_other_owner_branch_or_auth(self):
        for field, value in (("GITHUB_ACTOR", "another-owner"), ("GITHUB_REF", "refs/heads/main"),
                             ("WRITING_COMPARISON_AUTHORIZATION", "old-authority")):
            environment = dict(self.environment, **{field: value})
            with self.subTest(field=field), patch.dict(os.environ, environment, clear=True), self.loaded():
                with self.assertRaisesRegex(relay_guard.RelayGuardError, "exact owner authorization"):
                    self.begin()
                self.assertIsNone(self.value["active"])
        self.store.write.assert_not_called()

    def test_additional_unknown_hold_or_changed_reserved_amount_rejects_exception(self):
        for change in ("new-hold", "changed-amount"):
            self.value["legacy_holds"] = copy.deepcopy(self.held)
            if change == "new-hold":
                self.value["legacy_holds"]["new-unknown"] = {"reserved_ceiling_cny": 0.1}
            else:
                next(iter(self.value["legacy_holds"].values()))["reserved_ceiling_cny"] = 0.5
            with self.subTest(change=change), patch.dict(os.environ, self.environment, clear=True), self.loaded():
                with self.assertRaisesRegex(relay_guard.RelayGuardError, "exact owner authorization"):
                    self.begin()
                self.assertIsNone(self.value["active"])

    def test_exception_does_not_clear_active_request_and_ordinary_calls_stay_blocked(self):
        with patch.dict(os.environ, self.environment, clear=True), self.loaded():
            self.value["active"] = {"id": "outstanding-request"}
            with self.assertRaisesRegex(relay_guard.RelayGuardError, "concurrent"):
                self.begin()
            self.assertEqual(self.value["active"], {"id": "outstanding-request"})
            self.value["active"] = None
            with self.assertRaisesRegex(relay_guard.RelayGuardError, "historical"):
                relay_guard.begin("codekey-gemini", scope=self.scope, max_cost_cny=0.5)
            self.assertEqual(self.value["legacy_holds"], self.held)


class WritingTrialBudgetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.budget = object.__new__(trial.Budget)
        self.budget.root = Path(temporary.name)
        control = trial.model_spend.initial()
        trial.model_spend.write(self.budget.root, control)
        trial.model_spend.grant(self.budget.root, new_ceiling_cny=300, actor="synthetic owner", run_id="fixture")
        trial.model_spend.amend_ceiling(self.budget.root, new_ceiling_cny=500, actor="synthetic owner",
                                       run_id="fixture", authorization_note="Synthetic approved ceiling fixture.")
        self.budget.refresh = Mock(side_effect=lambda: trial.model_spend.read(self.budget.root, required=True))
        self.budget.persist = Mock()

    def test_retained_legacy_reservation_survives_restart_without_double_occupancy(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "fixture"}, clear=True):
            first = self.budget.reserve(trial.OLD_HOLD, kind="retained_legacy")
            second = self.budget.reserve(trial.OLD_HOLD, kind="retained_legacy")
        self.assertEqual(first, second)
        control = trial.model_spend.read(self.budget.root, required=True)
        self.assertEqual(len(control["reservations"]), 1)
        self.assertEqual(trial.model_spend.reserved(control), trial.OLD_HOLD)
        self.assertEqual(control["spent_cny"], 0)

    def test_actual_debit_above_bound_is_persisted_before_stopping(self):
        receipt = trial.model_spend.reserve(self.budget.root, max_cost_cny=0.25,
            paper_id=None, paper_limit_cny=500, run_id="fixture")
        with self.assertRaises(trial.model_spend.SpendControlError):
            self.budget.settle(receipt, 0.5)
        self.budget.persist.assert_called_once()
        control = trial.model_spend.read(self.budget.root, required=True)
        self.assertEqual(control["spent_cny"], 0.5)
        self.assertNotIn(receipt, control["reservations"])


if __name__ == "__main__":
    unittest.main()
