"""Offline controls for the one new native base contract; no live transport."""
from contextlib import ExitStack
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import argon_native_probe as probe


class NativeProbeTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.item = {"id": probe.CASE, "prompt": "Synthetic source test", "system": "Return JSON"}
        stack.enter_context(patch.object(probe.fixtures, "case", return_value=self.item))
        stack.enter_context(patch.object(probe.fixtures, "score", return_value={"passed": True, "score": 100}))
        stack.enter_context(patch.object(probe, "quote", return_value={"quote_sha256": "q" * 64}))
        stack.enter_context(patch.object(probe.model_runtime, "reservation_bound", return_value=0.5))
        self.parent = {"status": "closed_with_holds", "full_matrix_authorization": {
            "authorization_id": probe.parent_trial.FULL_AUTHORIZATION}, "entries": [{
                "provider": "codekey-gemini", "billing_status": "reserved", "reserved_ceiling_cny": 0.4}]}
        self.scope = probe.contract(self.parent, "a" * 40, 0)
        self.ledger = {"authorization_id": probe.AUTHORIZATION, "scope": copy.deepcopy(self.scope),
                       "entries": [], "status": "running"}
        self.saved = []
        self.meter = stack.enter_context(patch.object(probe.parent_trial, "read_meter", side_effect=[
            {"requests": 2, "cost_cny": 0.01}, {"requests": 3, "cost_cny": 0.02}]))
        self.post = stack.enter_context(patch.object(probe.ai_providers, "_production_request", return_value={
            "modelVersion": probe.MODEL, "candidates": [{"finishReason": "STOP",
            "content": {"parts": [{"text": "{}"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "totalTokenCount": 15}}))
        stack.enter_context(patch.dict(probe.os.environ, {
            probe.ai_providers.PRODUCTION_PROVIDERS["codekey-gemini"]["key_setting"]: "fake-probe-key"}))

    def persist(self, ledger):
        self.saved.append(copy.deepcopy(ledger))

    def test_exact_native_base_request_follows_confirmed_reservation(self):
        response = self.post.return_value
        def receive(endpoint, headers, payload, timeout):
            self.assertEqual(len(self.saved), 1)
            self.assertEqual(self.saved[0]["entries"][0]["generation_status"], "not_sent")
            self.assertEqual(endpoint, probe.ENDPOINT)
            self.assertEqual(headers, {"x-goog-api-key": "fake-probe-key"})
            self.assertEqual(payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "HIGH")
            self.assertEqual(timeout, 180)
            return response
        self.post.side_effect = receive
        probe.execute(self.ledger, self.scope, self.persist)
        self.assertEqual(self.ledger["entries"][0]["generation_status"], "completed")
        self.assertEqual(self.ledger["entries"][0]["reported_model"], probe.MODEL)

    def test_failed_durable_reservation_prevents_paid_call(self):
        with self.assertRaises(OSError):
            probe.execute(self.ledger, self.scope, lambda _: (_ for _ in ()).throw(OSError("offline")))
        self.post.assert_not_called()

    def test_prior_argon_hold_prevents_attributing_new_aggregate_delta(self):
        original = copy.deepcopy(self.parent)
        probe.execute(self.ledger, self.scope, self.persist)
        entry = self.ledger["entries"][0]
        self.assertEqual(self.parent, original)
        self.assertEqual(entry["billing_status"], "reserved")
        self.assertNotIn("actual_cost_cny", entry)
        self.assertEqual(self.ledger["status"], "closed_with_holds")

    def test_lost_or_completed_response_is_never_replayed(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                ledger = copy.deepcopy(self.ledger)
                ledger["entries"] = [{"generation_status": "response_failed" if failed else "completed"}]
                probe.execute(ledger, self.scope, self.persist)
        self.post.assert_not_called()

    def test_reported_high_alias_does_not_equal_requested_base(self):
        self.post.return_value["modelVersion"] = "gemini-4-argon-high"
        probe.execute(self.ledger, self.scope, self.persist)
        entry = self.ledger["entries"][0]
        self.assertEqual(entry["generation_status"], "response_failed")
        self.assertNotIn("grade", entry)
        self.assertEqual(entry["billing_status"], "reserved")

    def test_transport_failure_preserves_hold_and_never_retries(self):
        self.post.side_effect = probe.ai_providers.ProviderError("HTTP 503")
        probe.execute(self.ledger, self.scope, self.persist)
        probe.execute(self.ledger, self.scope, self.persist)
        self.post.assert_called_once()
        self.assertEqual(self.ledger["entries"][0]["generation_status"], "response_failed")
        self.assertEqual(self.ledger["status"], "closed_with_holds")

    def test_scope_requires_closed_parent_and_combined_call_cap(self):
        parent = copy.deepcopy(self.parent)
        parent["status"] = "running"
        with self.assertRaisesRegex(probe.ProbeError, "closed_authorized_parent"):
            probe.contract(parent, "a" * 40, 0)
        with self.assertRaisesRegex(probe.ProbeError, "combined_attempt_cap"):
            probe.contract(self.parent, "a" * 40, 127)
        self.post.assert_not_called()

    def test_changed_scope_cannot_reset_probe(self):
        changed = copy.deepcopy(self.scope)
        changed["endpoint"] = "https://example.invalid"
        with self.assertRaisesRegex(probe.ProbeError, "authorization_changed"):
            probe.execute(self.ledger, changed, self.persist)
        self.post.assert_not_called()
