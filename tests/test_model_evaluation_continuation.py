"""Synthetic cloud fixtures: isolated continuation never releases unknown debits."""
import copy
from contextlib import ExitStack
import json
import os
import unittest
from unittest.mock import patch

from scripts import ai_providers, relay_billing, model_evaluation_20261029 as trial


ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "hengyizang/lunwen",
    "GITHUB_REF": "refs/heads/" + trial.BRANCH, "GITHUB_ACTOR": "hengyizang",
    "GITHUB_EVENT_NAME": "workflow_dispatch", "MODEL_EVALUATION_MODE": "continue-isolated",
    "MODEL_EVALUATION_AUTHORIZATION": trial.CONTINUATION_AUTHORIZATION,
    "GH_TOKEN": "synthetic-fixture-only", "GITHUB_RUN_ID": "123456", "GITHUB_SHA": "c" * 40}


class MemoryState:
    def __init__(self, original):
        self.original = copy.deepcopy(original)
        self.blob = trial.ORIGINAL_BLOB
        self.continuation = None
        self.writes = []
        self.source_reads = 0

    def read(self, name):
        if name != "ledger.json":
            raise AssertionError("only immutable source reads expected")
        self.source_reads += 1
        return copy.deepcopy(self.original), self.blob

    def load(self, name):
        if name != trial.CONTINUATION_FILE:
            raise AssertionError("original ledger must not be opened for writing")
        return copy.deepcopy(self.continuation)

    def save(self, name, value):
        if name != trial.CONTINUATION_FILE:
            raise AssertionError("original ledger must never be modified")
        self.continuation = copy.deepcopy(value)
        self.writes.append((name, copy.deepcopy(value)))


class Budget:
    def __init__(self):
        self.control = {"authorized_ceiling_cny": 500, "spent_cny": 1.0, "reservations": {
            trial.GEMINI_LEGACY_ID: {"kind": "retained_legacy", "max_cost_cny": trial.GEMINI_LEGACY_CNY},
            trial.DEEPSEEK_LEGACY_ID: {"kind": trial.DEEPSEEK_LEGACY_KIND,
                "writing_trial": trial.TRIAL, "max_cost_cny": trial.DEEPSEEK_LEGACY_CNY},
            trial.UNKNOWN_ARGON_ID: {"kind": "new_call", "writing_trial": trial.TRIAL,
                "call_id": trial.UNKNOWN_ARGON_CALL, "max_cost_cny": trial.UNKNOWN_ARGON_CNY}}}
        self.reserves, self.settlements = [], []

    def refresh(self):
        return copy.deepcopy(self.control)

    def reserve(self, amount, *, kind="new_call", call_id=None):
        identity = f"{len(self.reserves) + 1:032x}"
        self.reserves.append((identity, amount, call_id))
        self.control["reservations"][identity] = {"kind": kind, "writing_trial": trial.TRIAL,
            "call_id": call_id, "max_cost_cny": amount}
        return identity

    def settle(self, identity, amount):
        self.control["reservations"].pop(identity)
        self.control["spent_cny"] += amount
        self.settlements.append((identity, amount))


def fixture():
    plan = json.loads((trial.ROOT / trial.PLAN).read_text(encoding="utf-8"))
    with patch.dict(os.environ, {"GITHUB_SHA": trial.ORIGINAL_CODE}):
        frozen = trial.freeze_scope(plan)
    entries = [{"call_id": row["call_id"], "billing_status": "settled", "generation_status": "completed"}
        for row in frozen["queue"][:21]]
    entries.append({"call_id": trial.UNKNOWN_ARGON_CALL, "billing_status": "reserved", "generation_status": "failed",
        "provider": "codekey-gemini", "project_reservation_id": trial.UNKNOWN_ARGON_ID,
        "reserved_ceiling_cny": trial.UNKNOWN_ARGON_CNY, "run_id": "previous-cloud-run"})
    original = {"trial_id": trial.TRIAL, "scope": frozen, "status": "stopped", "entries": entries,
        "legacy_budget_reservations": {"gemini": trial.GEMINI_LEGACY_ID, "deepseek": trial.DEEPSEEK_LEGACY_ID}}
    guard = {"provider": "codekey-gemini", "legacy_holds": [
        {"id": "44064d7e5133c1c82704269da0095f60541c12e8c24be1560eac5e67920f46e9", "reserved_ceiling_cny": .431508},
        {"id": "f6da77fa19739e14aedd1e040301f29d85ee7f899c840b2fd7138cc7dc44b5e9", "reserved_ceiling_cny": 9.1521024}],
        "active": {"id": trial.UNKNOWN_ARGON_TICKET,
        "provider": "codekey-gemini", "credential_sha256": "b" * 64, "run_id": "previous-cloud-run",
        "max_cost_cny": trial.UNKNOWN_ARGON_CNY, "scope": {"trial": trial.TRIAL,
            "call_id": trial.UNKNOWN_ARGON_CALL, "authorization": trial.AUTHORIZATION,
            "project_reservation_id": trial.UNKNOWN_ARGON_ID, "legacy_budget_reservation_id": trial.GEMINI_LEGACY_ID}}}
    return plan, original, guard


class ModelEvaluationContinuationTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.original, self.guard = fixture()
        self.state, self.budget = MemoryState(self.original), Budget()

    def preview(self, original=None, guard=None, blob=None):
        with patch.dict(os.environ, ENV, clear=True):
            return trial.continuation_plan(self.plan, original or self.original,
                blob or trial.ORIGINAL_BLOB, guard or self.guard)

    def test_preview_preserves_exact_twelve_original_rows_quotes_and_prompt_hashes(self):
        preview = self.preview()
        scope = preview["scope"]
        self.assertTrue(preview["authorization_is_not_granted_by_preview"])
        self.assertEqual(preview["new_request_count"], 12)
        self.assertEqual(preview["overall_attempts_if_all_sent"], 34)
        self.assertEqual(scope["code_sha"], ENV["GITHUB_SHA"])
        self.assertEqual(scope["original_binding"]["source_code_sha"], trial.ORIGINAL_CODE)
        self.assertEqual(scope["original_binding"]["source_sha256"], trial.gateway_trial.digest(self.original))
        original_rows = {row["call_id"]: row for row in self.original["scope"]["queue"]}
        for row in scope["queue"]:
            self.assertEqual(row, original_rows[row["call_id"]])
            self.assertNotIn(row["call_id"], {entry["call_id"] for entry in self.original["entries"]})
            self.assertIn(row["route_id"], trial.CONTINUATION_ROUTES)
            self.assertIn(row["case_id"], trial.CONTINUATION_CASES)
        for route in scope["routes"]:
            self.assertEqual(scope["quotes"][route["id"]], self.original["scope"]["quotes"][route["id"]])
            self.assertNotIn("gemini", route["provider"])

    def test_changed_source_blob_original_code_plan_unknown_hold_or_active_ticket_is_rejected(self):
        with self.assertRaises(ValueError):
            self.preview(blob="a" * 40)
        mutations = [lambda o: o.update(status="running"),
            lambda o: o["scope"].update(code_sha="a" * 40),
            lambda o: o["scope"].update(plan_sha256="b" * 64),
            lambda o: o["entries"][-1].update(reserved_ceiling_cny=0),
            lambda o: o["entries"][-1].update(billing_status="settled"),
            lambda o: o["entries"].append(copy.deepcopy(o["entries"][-1]))]
        for mutate in mutations:
            original = copy.deepcopy(self.original)
            mutate(original)
            with self.subTest(original=original["status"]), self.assertRaises(ValueError):
                self.preview(original=original)
        for field, value in (("id", "wrong"), ("provider", "codekey-kimi"),
                ("credential_sha256", "missing"), ("max_cost_cny", 0)):
            guard = copy.deepcopy(self.guard)
            guard["active"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.preview(guard=guard)
        changed = copy.deepcopy(self.plan)
        changed["cases"][-1]["instruction"] += " Changed."
        with patch.dict(os.environ, ENV, clear=True), self.assertRaises(ValueError):
            trial.continuation_plan(changed, self.original, trial.ORIGINAL_BLOB, self.guard)

    def test_original_authorization_does_not_authorize_continuation(self):
        with patch.dict(os.environ, {**ENV, "MODEL_EVALUATION_AUTHORIZATION": trial.AUTHORIZATION}, clear=True), \
                patch.object(trial.relay_guard, "inspect") as inspect, \
                patch.object(trial.writing_comparison, "Budget") as budget, \
                patch.object(trial.ai_providers, "call_production") as generate, self.assertRaises(ValueError):
            trial.continue_isolated(self.plan, self.state)
        inspect.assert_not_called()
        budget.assert_not_called()
        generate.assert_not_called()
        self.assertFalse(self.state.writes)

    def run_continuation(self, *, unknown=False, after_call=None, fail_first=False):
        calls, meters = [], []

        def generate(provider, text, **kwargs):
            self.assertNotIn("gemini", provider)
            self.assertEqual(self.state.continuation["entries"][-1]["billing_status"], "reserved")
            self.assertIn(trial.UNKNOWN_ARGON_ID, self.budget.control["reservations"])
            calls.append((provider, kwargs["model"]))
            if after_call is not None:
                after_call(len(calls))
            if fail_first and len(calls) == 1:
                raise ai_providers.ProviderError("synthetic identity failure")
            return ai_providers.ModelResult(provider, kwargs["model"], "Synthetic source-bound response.",
                {"input_tokens": 10, "output_tokens": 5}, reported_model=kwargs["model"],
                completion_status="completed", endpoint="https://fixture.invalid", protocol="synthetic")

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, ENV, clear=True))
            stack.enter_context(patch.object(trial.relay_guard, "inspect", side_effect=lambda p: copy.deepcopy(self.guard)))
            stack.enter_context(patch.object(trial.relay_guard, "fingerprint", return_value="a" * 64))
            stack.enter_context(patch.object(trial.writing_comparison, "Budget", return_value=self.budget))
            stack.enter_context(patch.object(trial.production_readiness, "catalog", side_effect=lambda p, e:
                {route["model"] for route in self.plan["routes"] if route["provider"] == p}))
            stack.enter_context(patch.object(trial.relay_billing, "read_meter", side_effect=lambda p:
                meters.append(p) or {"kind": "synthetic", "provider": p}))
            begin = stack.enter_context(patch.object(trial.relay_guard, "begin", return_value={"id": "synthetic-ticket"}))
            stack.enter_context(patch.object(trial.relay_guard, "bind_meter"))
            finish = stack.enter_context(patch.object(trial.relay_guard, "finish"))
            stack.enter_context(patch.object(trial.ai_providers, "call_production", side_effect=generate))
            stack.enter_context(patch.object(trial.relay_billing, "settle",
                side_effect=relay_billing.BillingReconciliationError("new unknown debit") if unknown else None,
                return_value={"actual_cost_cny": .001, "debit_evidence": {"exactly_one_new_gateway_request": True}}))
            result = trial.continue_isolated(self.plan, self.state)
        return result, calls, meters, begin, finish

    def test_all_twelve_are_single_attempt_old_unknown_hold_and_original_ledger_unchanged(self):
        held = copy.deepcopy(self.budget.control["reservations"])
        result, calls, meters, begin, _ = self.run_continuation()
        self.assertEqual(result["status"], "closed")
        self.assertEqual(len(calls), 12)
        self.assertEqual(len(self.budget.settlements), 12)
        self.assertTrue(all("gemini" not in provider for provider in meters))
        self.assertEqual(self.budget.control["reservations"], held)
        self.assertEqual(self.state.original, self.original)
        self.assertTrue(all(name == trial.CONTINUATION_FILE for name, _ in self.state.writes))
        self.assertGreaterEqual(self.state.source_reads, 14)
        for call in begin.call_args_list:
            scope = call.kwargs["scope"]
            self.assertEqual(scope["authorization"], trial.CONTINUATION_AUTHORIZATION)
            self.assertEqual(scope["continuation_source_blob"], trial.ORIGINAL_BLOB)
            self.assertEqual(scope["retained_unknown_reservation_id"], trial.UNKNOWN_ARGON_ID)

    def test_new_unknown_charge_stops_every_route_and_never_reopens(self):
        result, calls, _, _, finish = self.run_continuation(unknown=True)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self.budget.control["reservations"]), 4)
        self.assertEqual(result["entries"][0]["billing_status"], "reserved")
        finish.assert_not_called()
        resumed, repeated, *_ = self.run_continuation()
        self.assertEqual(resumed, result)
        self.assertFalse(repeated)

    def test_settled_identity_failure_quarantines_only_its_original_route(self):
        result, calls, *_ = self.run_continuation(fail_first=True)
        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["quarantined_routes"], ["terra-high"])
        self.assertEqual(sum(model == "gpt-6.1-terra" for _, model in calls), 1)
        self.assertEqual(len(calls), 10)
        self.assertEqual(result["entries"][0]["billing_status"], "settled")

    def test_original_blob_and_shared_ticket_rechecked_before_next_reservation(self):
        for mutate in (lambda: setattr(self.state, "blob", "e" * 40),
                lambda: self.guard["active"].update(credential_sha256="d" * 64),
                lambda: self.budget.control["reservations"][trial.UNKNOWN_ARGON_ID].update(max_cost_cny=.01)):
            self.state, self.budget = MemoryState(self.original), Budget()
            self.guard = fixture()[2]
            def after_call(count):
                if count == 1:
                    mutate()
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.run_continuation(after_call=after_call)
            self.assertEqual(len(self.budget.reserves), 1)

    def test_changed_continuation_code_or_closed_scope_never_resets_allowance(self):
        result, *_ = self.run_continuation()
        resumed, calls, *_ = self.run_continuation()
        self.assertEqual(resumed, result)
        self.assertFalse(calls)
        with patch.dict(os.environ, {**ENV, "GITHUB_SHA": "e" * 40}, clear=True), \
                patch.object(trial.relay_guard, "inspect", return_value=self.guard), \
                patch.object(trial.relay_guard, "fingerprint", return_value="a" * 64), \
                patch.object(trial.writing_comparison, "Budget") as budget, self.assertRaisesRegex(ValueError, "scope changed"):
            trial.continue_isolated(self.plan, self.state)
        budget.assert_not_called()

    def test_reusing_gemini_credential_or_discovering_another_old_charge_blocks_before_reservation(self):
        with patch.dict(os.environ, ENV, clear=True), \
                patch.object(trial.relay_guard, "inspect", return_value=self.guard), \
                patch.object(trial.relay_guard, "fingerprint", return_value="b" * 64), \
                patch.object(trial.writing_comparison, "Budget") as budget, self.assertRaisesRegex(ValueError, "cannot be reused"):
            trial.continue_isolated(self.plan, self.state)
        budget.assert_not_called()
        self.guard["legacy_holds"].append({"id": "c" * 64, "reserved_ceiling_cny": .01})
        with self.assertRaisesRegex(ValueError, "newly discovered"):
            self.preview()

    def test_standard_budget_path_still_rejects_the_unresolved_argon_charge(self):
        with self.assertRaisesRegex(ValueError, "outstanding"):
            trial._legacy_budget(self.budget)


if __name__ == "__main__":
    unittest.main()

