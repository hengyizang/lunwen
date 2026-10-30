"""The new owner exception cannot reopen historical trials or ordinary production."""
import copy
import os
import unittest
from unittest.mock import patch

from scripts import relay_guard as guard
from tests.relay_guard_fixtures import MemoryStore


class ModelEvaluationAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": guard.REPOSITORY,
            "GITHUB_ACTOR": "hengyizang", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ID": "fixture",
            "GITHUB_REF": "refs/heads/codex/model-evaluation-20261029",
            "MODEL_EVALUATION_AUTHORIZATION": "model-evaluation-20261029-owner-paid-with-legacy-holds",
            "DR_OS_CODEKEY_GEMINI_KEY": "synthetic-fixture-key"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        guard._TICKET.set(None)
        self.addCleanup(lambda: guard._TICKET.set(None))
        self.store = MemoryStore()
        self.holds = {"44064d7e5133c1c82704269da0095f60541c12e8c24be1560eac5e67920f46e9": {"reserved_ceiling_cny": .431508},
                      "f6da77fa19739e14aedd1e040301f29d85ee7f899c840b2fd7138cc7dc44b5e9": {"reserved_ceiling_cny": 9.1521024}}
        self.credential = guard.fingerprint("codekey-gemini")
        self.name = self.credential + ".json"
        self.store.put(guard.BRANCH, "relay-guard", self.name, {"schema_version": "1.0", "credential_sha256": self.credential,
            "legacy_holds": copy.deepcopy(self.holds), "active": None, "events": []})
        self.scope = {"trial": "model-evaluation-20261029", "authorization": os.environ["MODEL_EVALUATION_AUTHORIZATION"],
            "project_reservation_id": "a" * 32, "legacy_budget_reservation_id": "2b9e5e82da8a4f0bb9bfb6520ba814d1"}

    def begin(self, **kw):
        return guard.begin("codekey-gemini", scope=self.scope, max_cost_cny=1, store=self.store, **kw)

    def test_only_exact_new_authorization_preserves_old_holds(self):
        with self.assertRaisesRegex(guard.RelayGuardError, "historical"):
            self.begin()
        ticket = self.begin(evaluation_trial_exception=True)
        current = self.store.read(guard.BRANCH, "relay-guard", self.name)[0]
        self.assertEqual(current["legacy_holds"], self.holds)
        self.assertEqual(current["active"], ticket)
        self.assertFalse(current["events"])

    def test_wrong_branch_or_reservation_never_reuses_the_exception(self):
        for replacement in ("refs/heads/main", "refs/heads/codex/writing-comparison-20261027"):
            with patch.dict(os.environ, {"GITHUB_REF": replacement}), self.assertRaisesRegex(guard.RelayGuardError, "exact owner"):
                self.begin(evaluation_trial_exception=True)
        self.scope["legacy_budget_reservation_id"] = "b" * 32
        with self.assertRaisesRegex(guard.RelayGuardError, "exact owner"):
            self.begin(evaluation_trial_exception=True)

    def test_a_new_unknown_hold_is_never_covered_by_the_old_exception(self):
        current, _ = self.store.read(guard.BRANCH, "relay-guard", self.name)
        current["legacy_holds"]["c" * 64] = {"reserved_ceiling_cny": .1}
        self.store.put(guard.BRANCH, "relay-guard", self.name, current)
        with self.assertRaisesRegex(guard.RelayGuardError, "exact owner"):
            self.begin(evaluation_trial_exception=True)

    def test_chat_transport_shares_native_credential_and_old_holds(self):
        ticket = guard.begin("codekey-gemini-chat", scope=self.scope, max_cost_cny=1,
            store=self.store, evaluation_trial_exception=True)
        self.assertEqual(guard.fingerprint("codekey-gemini-chat"), self.credential)
        current = self.store.read(guard.BRANCH, "relay-guard", self.name)[0]
        self.assertEqual(current["legacy_holds"], self.holds)
        self.assertEqual(current["active"], ticket)

    def test_wrong_authorization_or_an_active_ticket_blocks_new_generation(self):
        with patch.dict(os.environ, {"MODEL_EVALUATION_AUTHORIZATION": "wrong"}), \
                self.assertRaises(guard.RelayGuardError):
            self.begin(evaluation_trial_exception=True)
        self.begin(evaluation_trial_exception=True)
        with self.assertRaises(guard.RelayGuardError):
            self.begin(evaluation_trial_exception=True)

    def test_deepseek_requires_its_own_retained_legacy_binding_and_exact_hold(self):
        with patch.dict(os.environ, {"DR_OS_CODEKEY_DEEPSEEK_KEY": "synthetic-deepseek-key"}):
            identity = guard.fingerprint("codekey-deepseek")
            holds = {"09b68c08573ed0ebbd0abd6f9d2eedf402a1edfab5bcbccd8d0e3f19022f318c": {"reserved_ceiling_cny": .0625758}}
            self.store.put(guard.BRANCH, "relay-guard", identity + ".json", {"schema_version": "1.0", "credential_sha256": identity,
                "legacy_holds": holds, "active": None, "events": []})
            scope = {**self.scope, "legacy_budget_reservation_id": "b" * 32}
            ticket = guard.begin("codekey-deepseek", scope=scope, max_cost_cny=1, store=self.store, evaluation_trial_exception=True)
            saved = self.store.read(guard.BRANCH, "relay-guard", identity + ".json")[0]
            self.assertEqual(saved["legacy_holds"], holds)
            self.assertEqual(saved["active"], ticket)

    def test_isolated_continuation_never_reopens_gemini_and_binds_deepseek_remaining_cases(self):
        authorization = "model-evaluation-20261029-owner-isolated-continuation-retain-unknown-argon"
        scope = {**self.scope, "authorization": authorization,
            "continuation_source_blob": "65406a6cd6344c20ba4ec608ca12b0b8602c1a50",
            "retained_unknown_reservation_id": "f705e87ba4514cb99c961768f59f4278",
            "legacy_budget_reservation_id": "97bdea2e1dd64aaaaa68dfa390e9ec76",
            "call_id": "deepseek-high|writing-integrity"}
        with patch.dict(os.environ, {"MODEL_EVALUATION_AUTHORIZATION": authorization,
                "MODEL_EVALUATION_MODE": "continue-isolated", "DR_OS_CODEKEY_DEEPSEEK_KEY": "synthetic-deepseek-key"}):
            for provider in ("codekey-gemini", "codekey-gemini-chat"):
                with self.subTest(provider=provider), self.assertRaises(guard.RelayGuardError):
                    guard.begin(provider, scope=scope, max_cost_cny=1, store=self.store, evaluation_trial_exception=True)
            identity = guard.fingerprint("codekey-deepseek")
            holds = {"09b68c08573ed0ebbd0abd6f9d2eedf402a1edfab5bcbccd8d0e3f19022f318c": {"reserved_ceiling_cny": .0625758}}
            self.store.put(guard.BRANCH, "relay-guard", identity + ".json", {"schema_version": "1.0", "credential_sha256": identity,
                "legacy_holds": holds, "active": None, "events": []})
            for field in ("call_id", "continuation_source_blob", "retained_unknown_reservation_id", "legacy_budget_reservation_id"):
                with self.subTest(field=field), self.assertRaises(guard.RelayGuardError):
                    guard.begin("codekey-deepseek", scope={**scope, field: "wrong"}, max_cost_cny=1,
                        store=self.store, evaluation_trial_exception=True)
            ticket = guard.begin("codekey-deepseek", scope=scope, max_cost_cny=1,
                store=self.store, evaluation_trial_exception=True)
            self.assertEqual(ticket["scope"], scope)


if __name__ == "__main__":
    unittest.main()

