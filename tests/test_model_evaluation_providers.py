"""Simulated candidate transports; never evidence of model quality or identity.

Generation and catalog IO are mocked. No API key, paid call or model promotion.
"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import Mock, patch

from scripts import ai_providers as providers, production_readiness


OPENAI_ROUTES = (
    "cheapai-gpt-pro", "cheapai-gpt-discount",
    "codekey-codex-pro", "codekey-codex-discount",
)


def chat_response(model):
    return {
        "model": model, "id": "candidate-fixture",
        "choices": [{"finish_reason": "stop", "message": {
            "content": "Evidence-bound final answer", "reasoning_content": "private reasoning"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 30,
                  "prompt_tokens_details": {"cached_tokens": 20},
                  "completion_tokens_details": {"reasoning_tokens": 10},
                  "cache_creation_input_tokens": 5},
    }


class ModelEvaluationProviderTests(unittest.TestCase):
    def invoke(self, provider, data=None, **kwargs):
        spec = providers.PRODUCTION_PROVIDERS[provider]
        model = kwargs.get("model", spec["model"])
        environment = {"GITHUB_ACTIONS": "true", spec["key_setting"]: "fixture-only-key"}
        with patch.dict(os.environ, environment, clear=True), patch.object(
                providers, "_production_request", return_value=data or chat_response(model)) as transport:
            result = providers.call(provider, "evidence fixture", system="read-only trial", **kwargs)
        return result, transport

    def test_terra_is_an_exact_candidate_without_changing_route_defaults(self):
        defaults = {"cheapai-gpt-pro": "gpt-6.1-sol", "cheapai-gpt-discount": "gpt-5.6-luna",
                    "codekey-codex-pro": "gpt-6.1-sol", "codekey-codex-discount": "gpt-6.1-sol"}
        for route in OPENAI_ROUTES:
            spec = providers.PRODUCTION_PROVIDERS[route]
            self.assertIn("gpt-6.1-terra", spec["models"])
            self.assertEqual(spec["model"], defaults[route])
            data = {"model": "gpt-6.1-terra", "status": "completed", "id": "terra-fixture",
                    "output_text": "Evidence-bound final answer",
                    "usage": {"input_tokens": 100, "output_tokens": 30}}
            with self.subTest(route=route):
                result, transport = self.invoke(route, data, model="gpt-6.1-terra", reasoning_effort="high")
                self.assertEqual(result.reported_model, "gpt-6.1-terra")
                self.assertEqual(result.protocol, "openai_responses")
                self.assertEqual(transport.call_args.args[2]["reasoning"], {"effort": "high"})
                transport.assert_called_once()

    def test_kimi_uses_its_own_key_family_and_thinking_required_payload(self):
        spec = providers.PRODUCTION_PROVIDERS["codekey-kimi"]
        self.assertEqual(spec["models"], ("kimi-k3.1-pro",))
        self.assertEqual(spec["key_setting"], "DR_OS_CODEKEY_KIMI_KEY")
        self.assertEqual(providers.provider_family("codekey-kimi"), "moonshot")
        result, transport = self.invoke("codekey-kimi", reasoning_effort="high")
        endpoint, headers, payload, _ = transport.call_args.args
        self.assertEqual(endpoint, "https://codekey.ai/v1/chat/completions")
        self.assertEqual(headers, {"Authorization": "Bearer fixture-only-key"})
        self.assertNotIn("thinking", payload)  # Exact K3.1 model always thinks.
        self.assertEqual(payload["max_completion_tokens"], 8000)
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(result.protocol, "openai_chat_completions")
        self.assertNotIn("private reasoning", result.text)
        self.assertEqual(result.usage["input_tokens"], 100)
        self.assertEqual(result.usage["output_tokens"], 30)
        self.assertEqual(result.usage["input_tokens_details"], {"cached_tokens": 20})
        self.assertEqual(result.usage["output_tokens_details"], {"reasoning_tokens": 10})
        self.assertEqual(result.usage["cache_creation_input_tokens"], 5)

    def test_kimi_does_not_alias_code_endpoint_ids_or_disable_thinking(self):
        spec = providers.PRODUCTION_PROVIDERS["codekey-kimi"]
        self.assertEqual(providers.production_supported_efforts("codekey-kimi", spec["model"]), ("high",))
        for options in ({"model": "k3.1-pro"}, {"model": "kimi-3.1-pro"},
                        {"reasoning_effort": "none"}, {"reasoning_effort": "low"}):
            with self.subTest(options=options), patch.object(providers, "_production_request") as transport:
                with self.assertRaises(providers.ProviderError):
                    providers.call("codekey-kimi", "fixture", **options)
                transport.assert_not_called()

    def test_gemini_chat_is_explicit_transport_with_shared_credential(self):
        native = providers.PRODUCTION_PROVIDERS["codekey-gemini"]
        chat = providers.PRODUCTION_PROVIDERS["codekey-gemini-chat"]
        self.assertEqual(native["key_setting"], chat["key_setting"])
        self.assertEqual(chat["family"], "google")
        self.assertEqual(native["protocol"], "gemini_generate_content")
        result, transport = self.invoke("codekey-gemini-chat", reasoning_effort="medium")
        endpoint, headers, payload, _ = transport.call_args.args
        self.assertEqual(endpoint, "https://codekey.ai/v1/chat/completions")
        self.assertIn("Authorization", headers)
        self.assertNotIn("x-goog-api-key", headers)
        self.assertEqual(payload["reasoning_effort"], "medium")
        self.assertNotIn("contents", payload)
        self.assertEqual(result.protocol, "openai_chat_completions")
        self.assertEqual(result.request_id, "candidate-fixture")
        self.assertEqual(result.usage["output_tokens"], 30)
        self.assertEqual(result.completion_status, "completed")

    def test_missing_or_mismatched_chat_identity_has_no_native_fallback(self):
        for route in ("codekey-kimi", "codekey-gemini-chat"):
            for reported in (None, "unverified-alias"):
                data = chat_response(reported)
                # Native modelVersion cannot satisfy an OpenAI-chat receipt.
                data["modelVersion"] = providers.PRODUCTION_PROVIDERS[route]["model"]
                with self.subTest(route=route, reported=reported), patch.dict(os.environ,
                        {"GITHUB_ACTIONS": "true", "UUAPI_STRICT_MODEL_ID": "false",
                         providers.PRODUCTION_PROVIDERS[route]["key_setting"]: "fixture-only-key"}, clear=True), \
                        patch.object(providers, "_production_request", return_value=data) as transport:
                    with self.assertRaisesRegex(providers.ProviderError, "model ID missing or mismatched"):
                        providers.call(route, "fixture")
                    transport.assert_called_once()

    def test_chat_candidate_rejects_truncation_tools_and_bad_usage(self):
        for route in ("codekey-kimi", "codekey-gemini-chat"):
            model = providers.PRODUCTION_PROVIDERS[route]["model"]
            cases = []
            partial = chat_response(model)
            partial["choices"][0]["finish_reason"] = "length"
            cases.append(partial)
            tool = chat_response(model)
            tool["choices"][0]["message"]["tool_calls"] = [{"id": "forbidden"}]
            cases.append(tool)
            for value in (None, {"prompt_tokens": True, "completion_tokens": 30},
                          {"prompt_tokens": 10, "completion_tokens": 30,
                           "prompt_tokens_details": {"cached_tokens": 11}}):
                bad_usage = chat_response(model)
                bad_usage["usage"] = value
                cases.append(bad_usage)
            for data in cases:
                with self.subTest(route=route, data=data), patch.dict(os.environ,
                        {"GITHUB_ACTIONS": "true",
                         providers.PRODUCTION_PROVIDERS[route]["key_setting"]: "fixture-only-key"}, clear=True), \
                        patch.object(providers, "_production_request", return_value=data) as transport:
                    with self.assertRaises(providers.ProviderError):
                        providers.call(route, "fixture")
                    transport.assert_called_once()

    def test_catalog_dispatch_follows_transport_not_model_family(self):
        for route in ("codekey-kimi", "codekey-gemini-chat", "codekey-gemini"):
            spec = providers.PRODUCTION_PROVIDERS[route]
            native = spec["protocol"] == "gemini_generate_content"
            data = {"models": [{"name": "models/gemini-4-argon"}]} if native else {
                "data": [{"id": spec["model"]}]}
            response = Mock()
            response.read.return_value = json.dumps(data).encode()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            opener = Mock()
            opener.open.return_value = response
            with self.subTest(route=route), patch.object(
                    production_readiness.urllib.request, "build_opener", return_value=opener):
                self.assertEqual(production_readiness.catalog(route, {spec["key_setting"]: "fixture-only-key"}),
                                 {spec["model"]})
                request = opener.open.call_args.args[0]
                expected = "/v1beta/models" if native else "/v1/models"
                self.assertEqual(request.full_url, "https://codekey.ai" + expected)
                headers = {name.lower(): value for name, value in request.header_items()}
                self.assertEqual("x-goog-api-key" in headers, native)
                self.assertEqual("authorization" in headers, not native)


if __name__ == "__main__":
    unittest.main()

