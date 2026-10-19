"""Offline payload, identity, billing and media contracts for native gateways."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import unittest
import urllib.error
from unittest.mock import Mock, patch

from scripts import ai_providers as providers


class ProductionProviderTests(unittest.TestCase):
    def env(self):
        return {spec["key_setting"]: f"fixture-only-{name}"
                for name, spec in providers.PRODUCTION_PROVIDERS.items()}

    def response(self, family="openai", model="gpt-6.1-sol"):
        if family == "google":
            return {"modelVersion": model, "responseId": "gemini-fixture",
                    "candidates": [{"finishReason": "STOP", "content": {"parts": [
                        {"text": "private thought", "thought": True}, {"text": "final text"}]}}],
                    "usageMetadata": {"promptTokenCount": 100, "cachedContentTokenCount": 30,
                                      "candidatesTokenCount": 10, "thoughtsTokenCount": 20,
                                      "totalTokenCount": 130}}
        if family == "deepseek":
            return {"model": model, "id": "ds-fixture", "choices": [{"finish_reason": "stop",
                    "message": {"content": "final text", "reasoning_content": "private thought"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 30,
                              "prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 60,
                              "completion_tokens_details": {"reasoning_tokens": 20}}}
        if family == "anthropic":
            return {"model": model, "id": "claude-fixture", "stop_reason": "end_turn",
                    "content": [{"type": "thinking", "thinking": "private thought"},
                                {"type": "text", "text": "final text"}],
                    "usage": {"input_tokens": 100, "output_tokens": 30,
                              "cache_read_input_tokens": 20,
                              "cache_creation_input_tokens": 10}}
        return {"model": model, "id": "openai-fixture", "status": "completed",
                "output_text": "final text", "usage": {"input_tokens": 100, "output_tokens": 30,
                    "input_tokens_details": {"cached_tokens": 20},
                    "output_tokens_details": {"reasoning_tokens": 10}}}

    def invoke(self, route, response=None, **kwargs):
        spec = providers.PRODUCTION_PROVIDERS[route]
        response = response or self.response(spec["family"], kwargs.get("model", spec["model"]))
        with patch.dict(os.environ, self.env(), clear=True), patch.object(
                providers, "_production_request", return_value=response) as transport:
            result = providers.call(route, "prompt fixture", system="system fixture", **kwargs)
        return result, transport

    def attachment(self, mime="application/pdf", content=b"%PDF-1.4\nfixture"):
        return {"mime_type": mime, "data_base64": base64.b64encode(content).decode(),
                "sha256": hashlib.sha256(content).hexdigest(), "filename": "fixture.pdf"}

    def test_production_configuration_is_offline_exact_and_secret_free(self):
        with patch.object(providers, "_production_request") as transport:
            for route, spec in providers.PRODUCTION_PROVIDERS.items():
                config = providers.configuration(route, self.env())
                self.assertTrue(config["configured"])
                self.assertEqual(config["family"], spec["family"])
                self.assertEqual(config["model"], spec["model"])
                self.assertTrue(config["strict_model_id"])
                self.assertEqual(config["billing_identity"],
                                 {"plan": "production", "group": route, "mode": "standard"})
                self.assertNotIn(self.env()[spec["key_setting"]], json.dumps(config))
                self.assertFalse(providers.configuration(route, {})["configured"])
            transport.assert_not_called()

    def test_four_families_never_infer_independence_from_endpoint(self):
        self.assertEqual({providers.provider_family(route) for route in providers.PRODUCTION_PROVIDERS},
                         {"openai", "anthropic", "deepseek", "google"})
        self.assertEqual(providers.provider_family("cheapai-gpt-pro"),
                         providers.provider_family("cheapai-gpt-discount"))

    def test_openai_reasoning_store_and_tools_are_explicit(self):
        result, transport = self.invoke("cheapai-gpt-pro", model="gpt-6-astra", reasoning_effort="high")
        endpoint, headers, payload, timeout = transport.call_args.args
        self.assertEqual(endpoint, "https://cheapai.info/v1/responses")
        self.assertEqual(headers["Authorization"], "Bearer fixture-only-cheapai-gpt-pro")
        self.assertEqual(payload["reasoning"], {"effort": "high"})
        self.assertEqual(payload["tools"], [])
        self.assertEqual(payload["service_tier"], "default")
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["input"][0]["role"], "developer")
        self.assertEqual(result.requested_effort, "high")
        self.assertEqual(result.reported_model, "gpt-6-astra")
        self.assertEqual(result.completion_status, "completed")

    def test_luna_uses_dedicated_discount_key_and_medium(self):
        result, transport = self.invoke("cheapai-gpt-discount")
        self.assertEqual(result.model, "gpt-5.6-luna")
        self.assertEqual(result.requested_effort, "medium")
        self.assertEqual(transport.call_args.args[2]["reasoning"], {"effort": "medium"})
        self.assertIn("fixture-only-cheapai-gpt-discount", transport.call_args.args[1]["Authorization"])

    def test_claude_adaptive_high_read_only_native_payload(self):
        result, transport = self.invoke("codekey-kiro-enterprise", model="claude-opus-5-5")
        endpoint, headers, payload, timeout = transport.call_args.args
        self.assertEqual(endpoint, "https://codekey.ai/v1/messages")
        self.assertIn("x-api-key", headers)
        self.assertNotIn("Authorization", headers)
        self.assertEqual(payload["thinking"], {"type": "adaptive"})
        self.assertEqual(payload["output_config"], {"effort": "high"})
        self.assertEqual(payload["tools"], [])
        self.assertNotIn("private thought", result.text)
        self.assertEqual(result.usage["cache_creation_input_tokens"], 10)

    def test_deepseek_thinking_cache_and_reasoning_are_counted_once(self):
        result, transport = self.invoke("codekey-deepseek")
        endpoint, headers, payload, timeout = transport.call_args.args
        self.assertEqual(endpoint, "https://codekey.ai/v1/chat/completions")
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(result.usage["input_tokens"], 100)
        self.assertEqual(result.usage["input_tokens_details"]["cached_tokens"], 40)
        self.assertEqual(result.usage["output_tokens"], 30)
        self.assertEqual(result.usage["output_tokens_details"]["reasoning_tokens"], 20)
        self.assertEqual(providers.provider_family(result.provider), "deepseek")
        self.assertNotIn("private thought", result.text)

    def test_google_native_auth_and_candidate_plus_thoughts_accounting(self):
        result, transport = self.invoke("codekey-gemini")
        endpoint, headers, payload, timeout = transport.call_args.args
        self.assertEqual(endpoint, "https://codekey.ai/v1beta/models/gemini-4-argon:generateContent")
        self.assertEqual(headers, {"x-goog-api-key": "fixture-only-codekey-gemini"})
        self.assertNotIn("key=", endpoint)
        self.assertEqual(payload["generationConfig"]["thinkingConfig"], {"thinkingLevel": "HIGH"})
        self.assertEqual(result.usage["output_tokens"], 30)
        self.assertEqual(result.usage["output_tokens_details"]["reasoning_tokens"], 20)
        self.assertEqual(result.usage["input_tokens_details"]["cached_tokens"], 30)
        self.assertEqual(result.text, "final text")

    def test_bad_cache_receipts_fail_without_generation_retry(self):
        for field, value in (("prompt_cache_hit_tokens", 101), ("prompt_cache_miss_tokens", 1)):
            response = self.response("deepseek", "deepseek-v4.1-flash")
            response["usage"][field] = value
            with self.subTest(field=field), patch.dict(os.environ, self.env(), clear=True), patch.object(
                    providers, "_production_request", return_value=response) as transport:
                with self.assertRaises(providers.ProviderError):
                    providers.call("codekey-deepseek", "fixture")
                transport.assert_called_once()

    def test_google_bad_total_or_cache_receipt_fails(self):
        for field, value in (("cachedContentTokenCount", 101), ("totalTokenCount", 100)):
            response = self.response("google", "gemini-4-argon")
            response["usageMetadata"][field] = value
            with patch.dict(os.environ, self.env(), clear=True), patch.object(
                    providers, "_production_request", return_value=response):
                with self.assertRaises(providers.ProviderError):
                    providers.call("codekey-gemini", "fixture")

    def test_unknown_usage_and_unexpected_tool_results_fail_closed(self):
        for usage in (None, {"prompt_tokens": True, "completion_tokens": 10},
                      {"prompt_tokens": 10, "completion_tokens": float("nan")}):
            response = self.response("deepseek", "deepseek-v4.1-flash")
            response["usage"] = usage
            with patch.dict(os.environ, self.env(), clear=True), patch.object(
                    providers, "_production_request", return_value=response):
                with self.assertRaises(providers.ProviderError):
                    providers.call("codekey-deepseek", "fixture")
        response = self.response("deepseek", "deepseek-v4.1-flash")
        response["choices"][0]["message"]["tool_calls"] = [{"id": "not-authorized"}]
        with patch.dict(os.environ, self.env(), clear=True), patch.object(
                providers, "_production_request", return_value=response):
            with self.assertRaises(providers.ProviderError):
                providers.call("codekey-deepseek", "fixture")

    def test_model_allowlists_stop_cross_family_and_unapproved_route_changes(self):
        with patch.dict(os.environ, self.env(), clear=True), patch.object(providers, "_production_request") as transport:
            for route, model in (("cheapai-gpt-pro", "deepseek-v4.1-flash"),
                                 ("cheapai-gpt-discount", "gpt-6-astra"),
                                 ("codekey-deepseek", "gpt-6.1-sol"),
                                 ("codekey-gemini", "gemini-4-argon-high")):
                with self.subTest(route=route), self.assertRaises(providers.ProviderError):
                    providers.call(route, "fixture", model=model)
            transport.assert_not_called()

    def test_missing_and_mismatched_identity_cannot_be_disabled(self):
        for route, spec in providers.PRODUCTION_PROVIDERS.items():
            for reported in (None, "unverified-alias"):
                response = self.response(spec["family"], spec["model"])
                response["modelVersion" if spec["family"] == "google" else "model"] = reported
                with self.subTest(route=route, reported=reported), patch.dict(os.environ,
                        {**self.env(), "UUAPI_STRICT_MODEL_ID": "false"}, clear=True), patch.object(
                        providers, "_production_request", return_value=response) as transport:
                    with self.assertRaises(providers.ProviderError):
                        providers.call(route, "fixture")
                    transport.assert_called_once()

    def test_incomplete_or_unknown_termination_never_becomes_an_artifact(self):
        examples = [("cheapai-gpt-pro", "status", "incomplete"),
                    ("codekey-kiro-enterprise", "stop_reason", "max_tokens")]
        for route, field, value in examples:
            spec = providers.PRODUCTION_PROVIDERS[route]
            response = self.response(spec["family"], spec["model"])
            response[field] = value
            with patch.dict(os.environ, self.env(), clear=True), patch.object(
                    providers, "_production_request", return_value=response):
                with self.assertRaises(providers.ProviderError):
                    providers.call(route, "fixture")

    def test_pdf_and_image_are_native_inputs_with_hashes(self):
        attachments = [self.attachment(), self.attachment("image/png", b"\x89PNG\r\n\x1a\nfixture")]
        result, transport = self.invoke("cheapai-gpt-pro", attachments=attachments)
        content = transport.call_args.args[2]["input"][-1]["content"]
        self.assertEqual([part["type"] for part in content], ["input_text", "input_file", "input_image"])
        self.assertTrue(content[1]["file_data"].startswith("data:application/pdf;base64,"))
        self.assertEqual(result.attachment_sha256, tuple(item["sha256"] for item in attachments))
        result, transport = self.invoke("codekey-gemini", attachments=attachments)
        parts = transport.call_args.args[2]["contents"][0]["parts"]
        self.assertEqual(parts[1]["inlineData"]["mimeType"], "application/pdf")
        self.assertEqual(parts[2]["inlineData"]["data"], attachments[1]["data_base64"])

    def test_utf8_text_attachment_is_decoded_for_openai(self):
        item = self.attachment("text/plain", "evidence α".encode())
        result, transport = self.invoke("cheapai-gpt-pro", attachments=[item])
        self.assertEqual(transport.call_args.args[2]["input"][-1]["content"][-1],
                         {"type": "input_text", "text": "evidence α"})
        self.assertEqual(providers.validate_attachments([item])[0]["decoded"], "evidence α".encode())

    def test_media_rejection_precedes_any_network_or_generation(self):
        wrong_hash = {**self.attachment(), "sha256": "0" * 64}
        wrong_signature = self.attachment("application/pdf", b"not a PDF")
        url_input = {"file_url": "https://private.example/file.pdf"}
        bad_base64 = {**self.attachment(), "data_base64": "not base64?"}
        for attachment in (wrong_hash, wrong_signature, url_input, bad_base64):
            with patch.dict(os.environ, self.env(), clear=True), patch.object(providers, "_production_request") as transport:
                with self.assertRaises(providers.ProviderError):
                    providers.call("cheapai-gpt-pro", "fixture", attachments=[attachment])
                transport.assert_not_called()
        for route in ("codekey-deepseek", "codekey-kiro-enterprise"):
            with patch.dict(os.environ, self.env(), clear=True), patch.object(providers, "_production_request") as transport:
                with self.assertRaises(providers.ProviderError):
                    providers.call(route, "fixture", attachments=[self.attachment()])
                transport.assert_not_called()

    def test_http_failure_never_retries_falls_back_or_leaks_error_body(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            "https://cheapai.info/v1/responses", 502, "gateway secret body", {}, None)
        with patch.dict(os.environ, self.env(), clear=True), patch.object(
                providers.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(providers.ProviderError) as error:
                providers.call("cheapai-gpt-pro", "fixture")
            self.assertIn("502", str(error.exception))
            self.assertNotIn("secret body", str(error.exception))
            opener.open.assert_called_once()

    def test_redirect_handler_refuses_credential_forwarding_and_post_replay(self):
        handler = providers._NoGenerationRedirect()
        for target in ("https://other.example/steal", "https://cheapai.info/another"):
            with self.assertRaises(providers.ProviderError):
                handler.redirect_request(None, None, 307, "redirect", {}, target)

    def test_production_transport_rejects_other_hosts_and_credential_urls(self):
        with patch.object(providers.urllib.request, "build_opener") as opener:
            for endpoint in ("http://cheapai.info/v1/responses", "https://other.example/v1/responses",
                             "https://cheapai.info@other.example/v1/responses",
                             "https://codekey.ai/v1/messages?key=secret"):
                with self.assertRaises(providers.ProviderError):
                    providers._production_request(endpoint, {}, {}, 10)
            opener.assert_not_called()

    def test_legacy_none_arguments_preserve_existing_call_signature(self):
        expected = providers.ModelResult("openai", "fixture", "OK", {})
        with patch.object(providers, "call_openai", return_value=expected) as legacy:
            self.assertIs(providers.call("openai", "fixture", reasoning_effort=None, attachments=None), expected)
            legacy.assert_called_once_with("fixture")
        with self.assertRaises(providers.ProviderError):
            providers.call("uuapi-openai", "fixture", reasoning_effort="high")


if __name__ == "__main__":
    unittest.main()
