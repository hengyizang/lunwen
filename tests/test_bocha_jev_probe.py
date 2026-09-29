"""The official Jev pilot stays bounded and does not expose credentials."""
import datetime as dt
import unittest

from scripts import bocha_jev_probe


KEY = "test-bocha-key"
TODAY = dt.date(2026, 9, 29)


class FakeTransport:
    def __init__(self, *, actual_model=bocha_jev_probe.MODEL):
        self.calls = []
        self.actual_model = actual_model

    def __call__(self, method, path, payload, key):
        self.calls.append((method, path, payload, key))
        if path == "/v1/models":
            return (200, {"models": [{"name": bocha_jev_probe.MODEL}]}) if key else (401, {})
        if path == "/v1/systemone":
            return 200, {"model": self.actual_model,
                         "answers": {"triage": {"type": "choice", "choice": "uncertain",
                                                "probabilities": {"prioritize": 0.1, "ordinary_review": 0.2,
                                                                  "uncertain": 0.7}}},
                         "usage": {"input_tokens": 123, "output_tokens": 0}}
        raise AssertionError(path)


class BochaJevProbeTests(unittest.TestCase):
    def test_unauthenticated_connectivity_never_calls_model(self):
        transport = FakeTransport()
        receipt = bocha_jev_probe.connectivity(transport)
        self.assertEqual(receipt["http_status"], 401)
        self.assertEqual(receipt["status"], "auth_required")
        self.assertEqual([path for _, path, _, _ in transport.calls], ["/v1/models"])
        self.assertFalse(receipt["model_call_made"])

    def test_live_trial_requires_key_and_current_policy_before_network(self):
        transport = FakeTransport()
        for key, checked in (("", TODAY.isoformat()), (KEY, "2026-09-28")):
            with self.subTest(key=bool(key)), self.assertRaises(bocha_jev_probe.ProbeError):
                bocha_jev_probe.trial(key, checked, transport, today=TODAY)
        self.assertEqual(transport.calls, [])

    def test_live_trial_checks_model_and_records_no_billing_claim(self):
        transport = FakeTransport()
        receipt = bocha_jev_probe.trial(KEY, TODAY.isoformat(), transport, today=TODAY)
        self.assertEqual(receipt["actual_model"], bocha_jev_probe.MODEL)
        self.assertFalse(receipt["billing_receipt_available"])
        self.assertNotIn(KEY, str(receipt))
        post = transport.calls[1]
        self.assertEqual(post[:2], ("POST", "/v1/systemone"))
        self.assertEqual(set(post[2]["questions"]["triage"]["criteria"]), bocha_jev_probe.LABELS)
        self.assertEqual([method for method, _, _, _ in transport.calls], ["GET", "POST"])
        with self.assertRaisesRegex(bocha_jev_probe.ProbeError, "actual serving model"):
            bocha_jev_probe.trial(KEY, TODAY.isoformat(), FakeTransport(actual_model="other"), today=TODAY)


if __name__ == "__main__":
    unittest.main()
