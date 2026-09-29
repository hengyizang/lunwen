"""The free trial cannot make a model call without a zero-credit server cap."""
import unittest

from scripts import free_jev_probe


KEY = "test-only-key"


class FakeTransport:
    def __init__(self, *, limit=0, cost=0, actual="openai/gpt-6-sol", byok=False):
        self.calls = []
        self.limit, self.cost, self.actual, self.byok = limit, cost, actual, byok

    def __call__(self, method, path, payload, key):
        self.calls.append((method, path, payload))
        assert key == KEY
        if path == "/key":
            return {"data": {"limit": self.limit, "limit_remaining": self.limit,
                             "is_free_tier": True, "include_byok_in_limit": True, "usage": 0}}
        if path == "/chat/completions":
            return {"id": "gen-123", "model": free_jev_probe.ROUTER,
                    "choices": [{"message": {"content": "uncertain"}}]}
        if path == "/generation?id=gen-123":
            return {"data": {"total_cost": self.cost, "model": self.actual,
                             "provider_name": "Moonshot AI", "is_byok": self.byok}}
        raise AssertionError(path)


class FreeJevProbeTests(unittest.TestCase):
    def test_no_model_call_without_zero_limit(self):
        transport = FakeTransport(limit=1)
        with self.assertRaisesRegex(free_jev_probe.ProbeError, "nonzero"):
            free_jev_probe.probe(KEY, transport)
        self.assertEqual([path for _, path, _ in transport.calls], ["/key"])

    def test_request_enforces_free_prices_and_records_actual_model(self):
        transport = FakeTransport()
        receipt = free_jev_probe.probe(KEY, transport)
        self.assertEqual(receipt["total_cost_usd"], 0)
        self.assertEqual(receipt["actual_model"], "openai/gpt-6-sol")
        self.assertEqual(receipt["provider"], "Moonshot AI")
        self.assertEqual(receipt["triage_label"], "uncertain")
        self.assertNotIn(KEY, str(receipt))
        post = transport.calls[1][2]
        self.assertEqual(post["provider"]["max_price"],
                         {"prompt": 0, "completion": 0, "request": 0, "image": 0})
        self.assertEqual(post["model"], "typesafe/jev-router")
        self.assertEqual([method for method, _, _ in transport.calls], ["GET", "POST", "GET", "GET"])

    def test_cost_or_identity_mismatch_fails_closed(self):
        for config in ({"cost": 0.0001}, {"actual": free_jev_probe.ROUTER}, {"byok": True}):
            with self.subTest(config=config), self.assertRaises(free_jev_probe.ProbeError):
                free_jev_probe.probe(KEY, FakeTransport(**config))


if __name__ == "__main__":
    unittest.main()
