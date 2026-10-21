"""Exact native endpoint identities with fake future alias coexistence only."""
from __future__ import annotations

from contextlib import ExitStack
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import ai_providers, billing_quotes, model_runtime


PROVIDER = "codekey-gemini"
BASE = "gemini-4-argon"
HIGH = "gemini-4-argon-high"


class RequestedModelEndpointTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        prices = json.loads((Path(__file__).resolve().parents[1]
            / "config/model-pricing.json").read_text(encoding="utf-8"))
        self.original_high_quote = next(copy.deepcopy(row) for row in prices["quotes"]
            if row["provider"] == PROVIDER and row["model"] == HIGH)
        self.identity = {"plan": "production", "group": PROVIDER, "mode": "standard"}
        self.original_high_digest = billing_quotes.select(prices, PROVIDER,
            self.original_high_quote["endpoint"], HIGH, self.identity)["quote_sha256"]
        # This fixture changes no repository registry or pricing file. It
        # exercises coexistence before any actual policy enables another ID.
        spec = copy.deepcopy(ai_providers.PRODUCTION_PROVIDERS[PROVIDER])
        spec.update(model=BASE, models=(BASE, HIGH))
        self.stack.enter_context(patch.dict(ai_providers.PRODUCTION_PROVIDERS, {PROVIDER: spec}))
        base_quote = copy.deepcopy(self.original_high_quote)
        base_quote.update(model=BASE,
            endpoint="https://codekey.ai/v1beta/models/" + BASE + ":generateContent",
            price_version=base_quote["price_version"] + "-test-only-base")
        prices["quotes"] = [row for row in prices["quotes"]
                            if (row["provider"], row["model"]) != (PROVIDER, BASE)] + [base_quote]
        self.stack.enter_context(patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true", "DR_OS_REQUIRE_MODEL_AUTH": "1",
            spec["key_setting"]: "fixture-only-no-real-key",
            "DR_OS_MODEL_PRICING_JSON": json.dumps(prices)}, clear=True))

    def test_requested_model_endpoint_does_not_follow_the_provider_default(self):
        self.assertEqual(ai_providers.production_endpoint(PROVIDER),
            "https://codekey.ai/v1beta/models/" + BASE + ":generateContent")
        self.assertEqual(ai_providers.production_endpoint(PROVIDER, HIGH),
            self.original_high_quote["endpoint"])
        self.assertEqual(ai_providers.configuration(PROVIDER)["model"], BASE)
        self.assertEqual(ai_providers.configuration(PROVIDER)["endpoint"],
            ai_providers.production_endpoint(PROVIDER, BASE))

    def test_frozen_high_quote_hash_is_unchanged_when_the_default_becomes_base(self):
        quote = model_runtime.pricing(PROVIDER, HIGH)
        self.assertEqual(quote["quote_sha256"], self.original_high_digest)
        self.assertEqual(quote["endpoint"], self.original_high_quote["endpoint"])
        base = model_runtime.pricing(PROVIDER, BASE)
        self.assertNotEqual(base["quote_sha256"], quote["quote_sha256"])
        self.assertEqual(base["endpoint"], ai_providers.production_endpoint(PROVIDER, BASE))
        self.assertEqual(model_runtime.preflight_route(PROVIDER, HIGH)["quote_sha256"],
            self.original_high_digest)

    def test_cache_identity_uses_the_same_exact_endpoint_as_its_quote(self):
        identities, keys = {}, {}
        for model in (BASE, HIGH):
            quote = model_runtime.pricing(PROVIDER, model)
            keys[model], identities[model] = model_runtime._cache_key(
                PROVIDER, "same fixture", None, 100, model, quote,
                reasoning_effort="high")
            self.assertEqual(identities[model]["model"], model)
            self.assertEqual(identities[model]["endpoint"], quote["endpoint"])
            self.assertEqual(identities[model]["billing_quote_sha256"], quote["quote_sha256"])
        self.assertNotEqual(keys[BASE], keys[HIGH])
        self.assertNotEqual(identities[BASE]["endpoint"], identities[HIGH]["endpoint"])

    def test_native_transport_receipt_and_failure_audit_configuration_agree(self):
        response = {"modelVersion": HIGH, "responseId": "fixture-response",
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "fixture"}]}}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1,
                              "thoughtsTokenCount": 0, "totalTokenCount": 2}}
        with patch.object(ai_providers, "_production_request", return_value=response) as transport:
            result = ai_providers.call_production(PROVIDER, "fixture", model=HIGH)
        endpoint = transport.call_args.args[0]
        self.assertEqual(endpoint, model_runtime.pricing(PROVIDER, HIGH)["endpoint"])
        self.assertEqual(endpoint, model_runtime._route_configuration(PROVIDER, HIGH)["endpoint"])
        self.assertEqual(result.endpoint, endpoint)
        self.assertEqual(result.reported_model, HIGH)
        self.assertEqual(transport.call_args.args[2]["generationConfig"]["thinkingConfig"],
            {"thinkingLevel": "HIGH"})
        transport.assert_called_once()

    def test_helper_never_authorizes_an_unlisted_id_or_cross_provider_model(self):
        with patch.object(ai_providers, "_production_request") as transport:
            for provider, model in ((PROVIDER, BASE + "-low"),
                                    (PROVIDER, HIGH + "/../" + BASE),
                                    (PROVIDER, "gpt-6.1-sol"),
                                    ("unconfigured-provider", HIGH)):
                with self.subTest(provider=provider, model=model):
                    with self.assertRaises(ai_providers.ProviderError):
                        ai_providers.production_endpoint(provider, model)
            transport.assert_not_called()

    def test_legacy_runtime_configuration_keeps_its_existing_endpoint(self):
        legacy = {"endpoint": "https://fixture.example/v1/responses", "model": "legacy-default"}
        with (patch.object(ai_providers, "configuration", return_value=legacy),
              patch.object(ai_providers, "production_endpoint") as endpoint):
            self.assertEqual(model_runtime._route_configuration("openai", "legacy-requested"), legacy)
        endpoint.assert_not_called()


if __name__ == "__main__":
    unittest.main()
