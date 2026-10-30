"""Cloud-only control fixtures for a verified failure before generation."""
import copy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import model_evaluation_20261029 as trial, model_spend, relay_guard
from tests.relay_guard_fixtures import MemoryStore


class State:
    def __init__(self, value):
        self.value = copy.deepcopy(value)
        self.fail_save = False
        self.writes = []

    def load(self, name):
        return copy.deepcopy(self.value)

    def read(self, name):
        return copy.deepcopy(self.value), trial.UNSENT_REPAIR_BLOB

    def save(self, name, value):
        if self.fail_save:
            self.fail_save = False
            raise ValueError("synthetic ledger write interruption")
        self.value = copy.deepcopy(value)
        self.writes.append(copy.deepcopy(value))


class UnsentTrialRepairTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        model_spend.write(self.root, model_spend.initial())
        model_spend.grant(self.root, new_ceiling_cny=300, actor="Synthetic owner", run_id="fixture")
        model_spend.amend_ceiling(self.root, new_ceiling_cny=500, actor="Synthetic owner",
            run_id="fixture", authorization_note="Synthetic control fixture only.")
        control = model_spend.read(self.root)
        control["spent_cny"] = 1
        for identity, amount in ((trial.GEMINI_LEGACY_ID, trial.GEMINI_LEGACY_CNY),
                (trial.DEEPSEEK_LEGACY_ID, trial.DEEPSEEK_LEGACY_CNY),
                (trial.UNKNOWN_ARGON_ID, trial.UNKNOWN_ARGON_CNY),
                (trial.UNSENT_RESERVATION, .0605584)):
            control["reservations"][identity] = {"max_cost_cny": amount, "paper_id": None,
                "run_id": "41027978880", "writing_trial": trial.TRIAL,
                "call_id": "deepseek-high|discriminating-experiment"}
        model_spend.write(self.root, control)
        self.held = copy.deepcopy(control["reservations"])
        self.budget = SimpleNamespace(root=self.root, persist=Mock(),
            refresh=lambda: model_spend.read(self.root, required=True))
        scope = {"code_sha": trial.UNSENT_REPAIR_CODE, "authorization": trial.CONTINUATION_AUTHORIZATION,
            "max_calls": 12, "unchanged_test_binding": "synthetic"}
        row = {"call_id": "deepseek-high|discriminating-experiment", "generation_status": "not_sent",
            "billing_status": "reserved", "diagnostic": "shared relay write readback failed",
            "project_reservation_id": trial.UNSENT_RESERVATION, "code_sha": trial.UNSENT_REPAIR_CODE,
            "run_id": "41027978880", "reserved_ceiling_cny": .0605584}
        self.state = State({"scope": scope, "status": "stopped", "stop_reason": "Shared reservation failed before transport.",
            "entries": [{"call_id": "terra-high|discriminating-experiment", "billing_status": "settled"}, row]})
        self.context = SimpleNamespace(scope={**scope, "code_sha": "c" * 40})
        self.store, self.name = MemoryStore(), "fixture.json"
        self.store.put(relay_guard.BRANCH, "relay-guard", self.name, {"legacy_holds": {"keep": {"amount": 5}},
            "events": [], "active": {"id": trial.UNSENT_TICKET, "provider": "codekey-deepseek",
                "credential_sha256": "a" * 64, "max_cost_cny": .0605584, "run_id": "41027978880",
                "scope": {"project_reservation_id": trial.UNSENT_RESERVATION, "call_id": row["call_id"]}}})

    def repair(self):
        def load(*args, **kwargs):
            value, blob = self.store.read(relay_guard.BRANCH, "relay-guard", self.name)
            return self.store, self.name, value, blob
        with patch.dict(os.environ, {"GITHUB_SHA": "c" * 40, "GH_TOKEN": "synthetic-only"}), \
                patch.object(trial.relay_guard, "load", side_effect=load), \
                patch.object(trial.relay_guard, "fingerprint", return_value="a" * 64), \
                patch.object(trial.writing_comparison, "Budget", return_value=self.budget), \
                patch.object(trial.ai_providers, "call_production") as generate:
            result = trial.repair_unstarted({}, self.state, self.context)
        generate.assert_not_called()
        return result

    def test_only_verified_unsent_reservation_is_cancelled_and_attempt_history_is_retained(self):
        result = self.repair()
        control = model_spend.read(self.root)
        self.assertEqual(control["spent_cny"], 1)
        self.assertEqual(control["reservations"], {k: v for k, v in self.held.items() if k != trial.UNSENT_RESERVATION})
        self.assertEqual(control["unsent_events"][0]["receipt_id"], trial.UNSENT_RESERVATION)
        self.assertIs(control["unsent_events"][0]["generation_sent"], False)
        self.assertEqual(result["status"], "running")
        self.assertEqual(len(result["entries"]), 1)
        self.assertEqual(result["preflight_events"][0]["original_entry"]["project_reservation_id"], trial.UNSENT_RESERVATION)
        self.assertEqual(result["repair_amendments"][0]["previous_scope"]["code_sha"], trial.UNSENT_REPAIR_CODE)
        shared = self.store.read(relay_guard.BRANCH, "relay-guard", self.name)[0]
        self.assertIsNone(shared["active"])
        self.assertEqual(shared["legacy_holds"], {"keep": {"amount": 5}})
        self.assertEqual(shared["events"][0]["status"], "not_sent_recovered")

    def test_a_bound_meter_or_possibly_sent_response_can_never_be_cancelled(self):
        shared, _ = self.store.read(relay_guard.BRANCH, "relay-guard", self.name)
        shared["active_meter"] = {"before": "possible transport"}
        self.store.put(relay_guard.BRANCH, "relay-guard", self.name, shared)
        with self.assertRaisesRegex(ValueError, "meter-bound"):
            self.repair()
        self.assertEqual(model_spend.read(self.root)["reservations"], self.held)
        self.assertFalse(self.state.writes)
        shared.pop("active_meter")
        self.store.put(relay_guard.BRANCH, "relay-guard", self.name, shared)
        self.state.value["entries"][-1]["generation_status"] = "failed"
        with self.assertRaisesRegex(ValueError, "pre-transport"):
            self.repair()

    def test_interrupted_final_ledger_save_reuses_existing_unsent_cancellations_once(self):
        self.state.fail_save = True
        with self.assertRaisesRegex(ValueError, "ledger write interruption"):
            self.repair()
        self.assertEqual(len(model_spend.read(self.root)["unsent_events"]), 1)
        self.repair()
        self.assertEqual(len(model_spend.read(self.root)["unsent_events"]), 1)
        self.assertEqual(len(self.store.read(relay_guard.BRANCH, "relay-guard", self.name)[0]["events"]), 1)


if __name__ == "__main__":
    unittest.main()

