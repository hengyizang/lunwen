"""Production startup must match tested transport, billing and budget boundaries."""
import copy
import json
import os
import unittest
from unittest.mock import patch

from scripts import ai_providers, model_runtime, production_gateway

class ProductionGatewayTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(production_gateway.PROFILE.read_text(encoding="utf-8"))
        self.secrets = {route["secret_name"]: "synthetic-fixture-only-" + route["provider"]
                        for route in self.profile["routes"]}
        self.env = production_gateway.prepare_environment(self.profile, self.secrets)

    def test_profile_binds_separate_keys_models_groups_and_high_effort(self):
        self.assertEqual(self.env["UUAPI_OPENAI_BASE_URL"], "https://cheapai.info")
        self.assertEqual(self.env["UUAPI_ANTHROPIC_BASE_URL"], "https://codekey.ai")
        self.assertNotEqual(self.env["UUAPI_OPENAI_API_KEY"], self.env["UUAPI_ANTHROPIC_API_KEY"])
        self.assertTrue(all(key not in self.env for key in self.secrets))
        self.assertEqual(self.env["UUAPI_OPENAI_REASONING_EFFORT"], "high")
        self.assertEqual(self.env["UUAPI_ANTHROPIC_EFFORT"], "high")
        self.assertEqual(self.env["UUAPI_STRICT_MODEL_ID"], "true")

    def test_missing_or_conflicting_configuration_fails_before_transport(self):
        for source in ({}, {**self.secrets, "UUAPI_OPENAI_BASE_URL": "https://wrong.invalid"}):
            with self.subTest(source=sorted(source)), patch.object(ai_providers, "_request") as call:
                with self.assertRaises(ValueError):
                    production_gateway.prepare_environment(self.profile, source)
                call.assert_not_called()

    def test_foreign_family_or_quote_cannot_reuse_selected_key(self):
        for field, value in (("family", "anthropic"), ("root", "https://wrong.invalid"), ("group", "other")):
            profile = copy.deepcopy(self.profile)
            profile["routes"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                production_gateway.prepare_environment(profile, self.secrets)

    def test_openai_actual_payload_preserves_high_and_no_storage(self):
        response = {"id": "fixture", "model": "gpt-6-astra", "output_text": "OK",
                    "status": "completed", "usage": {"input_tokens": 10, "output_tokens": 2}}
        with patch.dict(os.environ, self.env, clear=True), patch.object(ai_providers, "_request", return_value=response) as call:
            ai_providers.call("uuapi-openai", "fixture")
            payload = call.call_args.args[2]
            self.assertEqual(payload["reasoning"], {"effort": "high"})
            self.assertIs(payload["store"], False)
            self.assertEqual(call.call_args.args[0], "https://cheapai.info/v1/responses")
            self.assertEqual(call.call_count, 1)

    def test_anthropic_actual_payload_preserves_adaptive_high(self):
        response = {"id": "fixture", "model": "claude-opus-5-5", "content": [{"type": "text", "text": "OK"}],
                    "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 2}}
        with patch.dict(os.environ, self.env, clear=True), patch.object(ai_providers, "_request", return_value=response) as call:
            ai_providers.call("uuapi-anthropic", "fixture")
            payload = call.call_args.args[2]
            self.assertEqual(payload["thinking"], {"type": "adaptive"})
            self.assertEqual(payload["output_config"], {"effort": "high"})
            self.assertEqual(call.call_args.args[0], "https://codekey.ai/v1/messages")
            self.assertEqual(call.call_count, 1)

    def test_effort_is_in_exact_request_cache_identity(self):
        with patch.dict(os.environ, self.env, clear=True):
            high, identity = model_runtime._cache_key("uuapi-openai", "same", None, 100)
            os.environ["UUAPI_OPENAI_REASONING_EFFORT"] = "medium"
            medium, _ = model_runtime._cache_key("uuapi-openai", "same", None, 100)
        self.assertNotEqual(high, medium)
        self.assertEqual(identity["generation_options"], {"reasoning": {"effort": "high"}})

    def test_invalid_effort_blocks_before_request_and_legacy_default_is_unchanged(self):
        env = {**self.env, "UUAPI_OPENAI_REASONING_EFFORT": "invalid"}
        with patch.dict(os.environ, env, clear=True), patch.object(ai_providers, "_request") as call:
            with self.assertRaises(ai_providers.ProviderError):
                ai_providers.call("uuapi-openai", "fixture")
            call.assert_not_called()
            self.assertFalse(ai_providers.configuration("uuapi-openai")["configured"])
        self.assertEqual(ai_providers.generation_options("uuapi-openai", {}), {})
        self.assertEqual(ai_providers.generation_options("uuapi-openai",
            {"UUAPI_OPENAI_PROTOCOL": "chat_completions", "UUAPI_OPENAI_REASONING_EFFORT": "high"}),
            {"reasoning_effort": "high"})

    def test_scoped_quotes_are_accepted_by_cloud_preflight_without_network(self):
        from scripts import cloud_continuation
        with patch.object(ai_providers, "_request") as call:
            self.assertEqual(cloud_continuation.configuration_errors(self.env), [])
            call.assert_not_called()
        with patch.dict(os.environ, self.env, clear=True):
            for provider in production_gateway.PREFIXES:
                quote = model_runtime.preflight_route(provider)
                self.assertTrue(quote["quote_sha256"])

    def test_wrong_group_and_missing_cache_ttl_quote_block_preflight(self):
        from scripts import cloud_continuation
        wrong_group = json.loads(self.env["DR_OS_MODEL_BILLING_IDENTITY_JSON"])
        wrong_group["uuapi-openai"]["group"] = "wrong"
        self.assertTrue(cloud_continuation.configuration_errors({
            **self.env, "DR_OS_MODEL_BILLING_IDENTITY_JSON": json.dumps(wrong_group)}))
        prices = json.loads(self.env["DR_OS_MODEL_PRICING_JSON"])
        del prices["quotes"][1]["cache_write_1h_per_million"]
        self.assertTrue(cloud_continuation.configuration_errors({
            **self.env, "DR_OS_MODEL_PRICING_JSON": json.dumps(prices)}))

if __name__ == "__main__":
    unittest.main()
