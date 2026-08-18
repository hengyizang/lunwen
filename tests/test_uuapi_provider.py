from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from scripts import ai_providers, api_orchestrator


class FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class UuapiProviderTests(unittest.TestCase):
    def environment(self) -> dict[str, str]:
        return {
            "UUAPI_API_KEY": "sk-test-not-real",
            "UUAPI_BASE_URL": "https://gateway.example/v1",
            "UUAPI_ANTHROPIC_MODEL": "claude-test",
            "UUAPI_OPENAI_MODEL": "gpt-test",
        }

    def test_openai_responses_endpoint_headers_and_audit(self) -> None:
        captured: list[object] = []

        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            captured.append(request)
            return FakeResponse(
                {
                    "id": "resp_1",
                    "model": "gpt-test",
                    "output_text": "OK",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            )

        with patch.dict(os.environ, self.environment(), clear=True), patch(
            "scripts.ai_providers.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = ai_providers.call("uuapi-openai", "hello")

        request = captured[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://gateway.example/v1/responses")
        self.assertEqual(headers["authorization"], "Bearer sk-test-not-real")
        self.assertIn("codex_cli_rs", headers["user-agent"])
        self.assertFalse(payload["store"])
        self.assertEqual(result.reported_model, "gpt-test")
        audit = api_orchestrator.result_audit(result)
        self.assertEqual(audit["gateway"], "uuapi")
        self.assertNotIn("sk-test-not-real", json.dumps(audit))

    def test_anthropic_messages_endpoint_and_headers(self) -> None:
        captured: list[object] = []

        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            captured.append(request)
            return FakeResponse(
                {
                    "id": "msg_1",
                    "model": "claude-test",
                    "content": [{"type": "text", "text": "OK"}],
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            )

        with patch.dict(os.environ, self.environment(), clear=True), patch(
            "scripts.ai_providers.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = ai_providers.call("uuapi-anthropic", "hello")

        request = captured[0]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(request.full_url, "https://gateway.example/v1/messages")
        self.assertEqual(headers["x-api-key"], "sk-test-not-real")
        self.assertIn("claude-cli", headers["user-agent"])
        self.assertEqual(result.protocol, "anthropic_messages")

    def test_usage_endpoint_is_get_and_contains_no_key_in_url(self) -> None:
        captured: list[object] = []

        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            captured.append(request)
            return FakeResponse({"balance": 12.5, "unit": "USD"})

        with patch.dict(os.environ, self.environment(), clear=True), patch(
            "scripts.ai_providers.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            value = ai_providers.uuapi_usage()

        request = captured[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, "https://gateway.example/v1/usage")
        self.assertNotIn("sk-test-not-real", request.full_url)
        self.assertEqual(value["balance"], 12.5)

    def test_rejects_insecure_or_credentialed_base_urls(self) -> None:
        for value in (
            "http://gateway.example",
            "https://user:pass@gateway.example",
            "https://gateway.example?key=secret",
        ):
            with self.subTest(value=value), patch.dict(
                os.environ,
                {**self.environment(), "UUAPI_BASE_URL": value},
                clear=True,
            ):
                status = ai_providers.configuration("uuapi-openai")
                self.assertFalse(status["configured"])
                self.assertIsNotNone(status["configuration_error"])

    def test_strict_model_identity_rejects_mismatch(self) -> None:
        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            return FakeResponse(
                {
                    "id": "resp_1",
                    "model": "different-model",
                    "output_text": "OK",
                }
            )

        with patch.dict(os.environ, self.environment(), clear=True), patch(
            "scripts.ai_providers.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            with self.assertRaises(ai_providers.ProviderError):
                ai_providers.call("uuapi-openai", "hello")

    def test_strict_model_identity_rejects_missing_model(self) -> None:
        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            return FakeResponse({"id": "resp_1", "output_text": "OK"})

        with patch.dict(os.environ, self.environment(), clear=True), patch(
            "scripts.ai_providers.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            with self.assertRaises(ai_providers.ProviderError):
                ai_providers.call("uuapi-openai", "hello")

    def test_configuration_never_exposes_key(self) -> None:
        with patch.dict(os.environ, self.environment(), clear=True):
            value = ai_providers.configuration("uuapi-anthropic")
        self.assertTrue(value["configured"])
        self.assertNotIn("sk-test-not-real", json.dumps(value))

    def test_custom_endpoint_audit_strips_credentials_and_query(self) -> None:
        environment = {
            "OPENAI_API_KEY": "official-test-key",
            "OPENAI_BASE_URL": (
                "https://user:password@gateway.example/v1/responses?api_key=secret"
            ),
        }
        with patch.dict(os.environ, environment, clear=True):
            value = ai_providers.configuration("openai")
        self.assertEqual(
            value["endpoint"], "https://gateway.example/v1/responses"
        )
        self.assertNotIn("secret", json.dumps(value))

    def test_cycle_rejects_same_author_and_critic_provider(self) -> None:
        with self.assertRaises(ValueError):
            api_orchestrator.run_cycle(
                "demo",
                "intake",
                "uuapi-openai",
                "uuapi-openai",
                "",
                "",
            )

    def test_cycle_rejects_same_model_family_across_gateways(self) -> None:
        with self.assertRaises(ValueError):
            api_orchestrator.run_cycle(
                "demo",
                "intake",
                "anthropic",
                "uuapi-anthropic",
                "",
                "",
            )


if __name__ == "__main__":
    unittest.main()
