"""Read-only production readiness tests; catalogs use mocked GET transport."""
from __future__ import annotations

import io
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

from scripts import ai_providers, catalog_diagnostic, model_routing, model_spend, production_readiness as readiness


class FakeResponse:
    def __init__(self, payload):
        self.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit=-1):
        return self.body if limit < 0 else self.body[:limit]


class ProductionReadinessTests(unittest.TestCase):
    def test_cloud_catalog_diagnostic_reads_both_protocols_and_exact_native_descriptor(self):
        opener = Mock()
        opener.open.side_effect = [
            FakeResponse({"data": [{"id": "gemini-3.8-flash"}]}),
            FakeResponse({"models": [{"name": "models/gemini-4-argon-high"}], "nextPageToken": "private-cursor"}),
            FakeResponse({"name": "models/gemini-4-argon-high", "private": "must-not-record"}),
        ]
        env = {**self.environment(), "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "hengyizang/lunwen"}
        with patch.object(readiness.urllib.request, "build_opener", return_value=opener), \
             patch.object(ai_providers, "call") as generate, patch.object(model_spend, "reserve") as reserve:
            value = catalog_diagnostic.report(env)
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(value["endpoints"][0]["model_ids"], ["gemini-3.8-flash"])
        self.assertEqual(value["endpoints"][1]["model_ids"], ["gemini-4-argon-high"])
        self.assertTrue(value["endpoints"][1]["additional_pages_advertised"])
        self.assertEqual(value["endpoints"][2]["model_ids"], ["gemini-4-argon-high"])
        for index, row in enumerate(opener.open.call_args_list):
            request = row.args[0]
            self.assertEqual(request.get_method(), "GET")
            headers = {key.lower(): val for key, val in request.header_items()}
            expected_header = "authorization" if index == 0 else "x-goog-api-key"
            self.assertIn(expected_header, headers)
            self.assertNotIn("fixture-secret", request.full_url)
        serialized = json.dumps(value)
        for private in ("private-cursor", "must-not-record", "fixture-secret"):
            self.assertNotIn(private, serialized)
        self.assertEqual(value["model_generation_calls"], 0)
        self.assertFalse(value["inference_access_verified"])
        generate.assert_not_called()
        reserve.assert_not_called()

    def test_catalog_diagnostic_refuses_local_execution_before_transport(self):
        with patch.object(readiness.urllib.request, "build_opener") as opener:
            with self.assertRaises(ValueError):
                catalog_diagnostic.report(self.environment())
        opener.assert_not_called()

    def test_catalog_diagnostic_controls_errors_and_rejects_partial_or_malformed_model_names(self):
        payloads = [b"private-non-json", {"models": [{"name": "publishers/gemini-4-argon-high"}]},
                    {"models": [{"name": "models/gemini-4-argon-high/extra"}]},
                    {"models": [{"name": "models/gemini-4-argon-high\n"}]}]
        for payload in payloads:
            opener = Mock()
            opener.open.return_value = FakeResponse(payload)
            with patch.object(readiness.urllib.request, "build_opener", return_value=opener):
                value = catalog_diagnostic._inspect("https://codekey.ai", "/v1beta/models", "fixture-secret", schema="google-list")
            self.assertFalse(value["metadata_access_verified"])
            self.assertEqual(value["model_ids"], [])
            self.assertNotIn("private-non-json", json.dumps(value))
            opener.open.assert_called_once()

    def test_billing_readiness_uses_explicit_keys_without_recording_wallet_values(self):
        env = self.environment()
        def meter(provider, environment):
            self.assertIs(environment, env)
            return {"provider":provider,"kind":"fixture-read-only-meter","cost_cny":123.456,
                    "private":"never-persist-wallet-detail"}
        with patch.object(readiness.relay_billing,"read_meter",side_effect=meter) as get, \
             patch.object(ai_providers,"call") as generate, patch.object(model_spend,"grant") as grant:
            value = readiness.report(env,check_billing=True)
        self.assertTrue(value["configuration_ready"])
        self.assertEqual(get.call_count,5)
        self.assertEqual(len(value["billing_meters"]),5)
        self.assertNotIn("123.456",json.dumps(value))
        self.assertNotIn("never-persist-wallet-detail",json.dumps(value))
        generate.assert_not_called()
        grant.assert_not_called()

    def test_billing_metadata_failure_is_not_zero_cost_or_ready_and_has_no_retry(self):
        with patch.object(readiness.relay_billing,"read_meter",side_effect=
                readiness.relay_billing.BillingReconciliationError("fixture key must not echo")) as get:
            value = readiness.report(self.environment(),check_billing=True)
        self.assertFalse(value["configuration_ready"])
        self.assertEqual(get.call_count,5)
        self.assertEqual(len(value["configuration_errors"]),5)
        self.assertTrue(all(not row["metadata_access_verified"] for row in value["billing_meters"].values()))
        self.assertNotIn("fixture key must not echo",json.dumps(value))

    def environment(self):
        return {spec["key_setting"]: "fixture-secret-" + provider
                for provider, spec in ai_providers.PRODUCTION_PROVIDERS.items()}

    def test_billing_failure_does_not_hide_independent_catalog_diagnostics(self):
        with patch.object(readiness.relay_billing,"read_meter",side_effect=readiness.relay_billing.BillingReconciliationError("private")), \
             patch.object(readiness,"catalog",side_effect=self.advertised) as catalog:
            value=readiness.report(self.environment(),check_billing=True,check_models=True)
        self.assertFalse(value["configuration_ready"])
        self.assertEqual(catalog.call_count,5)
        self.assertEqual(len(value["model_inventory"]),5)
        self.assertTrue(all(row["metadata_access_verified"] for row in value["model_inventory"].values()))

    def advertised(self, provider, environment):
        return {
            "cheapai-gpt-pro": {"gpt-6.1-sol", "gpt-6-astra"},
            "cheapai-gpt-discount": {"gpt-5.6-luna"},
            "codekey-kiro-enterprise": {"claude-sonnet-5-5", "claude-opus-5-5"},
            "codekey-deepseek": {"deepseek-v4.1-flash"},
            "codekey-gemini": {"gemini-4-argon-high"},
        }[provider]

    def test_offline_report_describes_five_credentials_and_seven_quoted_routes(self):
        with (patch.object(readiness, "catalog") as inventory,
                patch.object(ai_providers, "call") as generate,
                patch.object(model_spend, "grant") as grant,
                patch.object(model_spend, "reserve") as reserve):
            value = readiness.report(self.environment())
        self.assertTrue(value["configuration_ready"])
        self.assertEqual(value["configuration_errors"], [])
        self.assertEqual(len(value["model_routes"]), 7)
        self.assertEqual(len({row["provider"] for row in value["model_routes"]}), 5)
        self.assertEqual({row["model_key"] for row in value["model_routes"]},
                         {"sol", "astra", "luna", "sonnet", "opus", "deepseek", "argon"})
        self.assertTrue(all(len(row["quote_sha256"]) == 64 for row in value["model_routes"]))
        self.assertEqual(len(value["policy_sha256"]), 64)
        self.assertEqual(value["model_generation_calls"], 0)
        self.assertIs(value["new_spending_authority"], False)
        self.assertIs(value["scientific_completion"], False)
        self.assertIs(value["inference_access_and_effort_passthrough_verified"], False)
        for transport in (inventory, generate, grant, reserve):
            transport.assert_not_called()

    def test_missing_production_key_stops_catalog_inspection(self):
        env = self.environment()
        env.pop("DR_OS_CODEKEY_GEMINI_KEY")
        with patch.object(readiness, "catalog") as inventory:
            value = readiness.report(env, check_models=True)
        self.assertFalse(value["configuration_ready"])
        self.assertTrue(any("DR_OS_CODEKEY_GEMINI_KEY" in error for error in value["configuration_errors"]))
        self.assertEqual(value["model_inventory"], {})
        inventory.assert_not_called()

    def test_whitespace_only_keys_are_missing_and_never_echoed(self):
        env = self.environment()
        env["DR_OS_CHEAPAI_GPT_PRO_KEY"] = "fixture secret with whitespace"
        value = readiness.report(env)
        self.assertFalse(value["configuration_ready"])
        self.assertNotIn("fixture secret with whitespace", json.dumps(value))

    def test_exact_billing_quote_is_required_for_each_channel_and_model(self):
        prices = json.loads((readiness.ROOT / "config/model-pricing.json").read_text(encoding="utf-8"))
        prices["quotes"] = [row for row in prices["quotes"] if row["model"] != "gpt-6-astra"]
        env = {**self.environment(), "DR_OS_MODEL_PRICING_JSON": json.dumps(prices)}
        with patch.object(readiness, "catalog") as inventory:
            value = readiness.report(env, check_models=True)
        self.assertFalse(value["configuration_ready"])
        self.assertIsNone(value["policy_sha256"])
        self.assertTrue(any("exact billing contract" in error for error in value["configuration_errors"]))
        inventory.assert_not_called()

    def test_authenticated_catalog_success_is_metadata_only_and_queried_once_per_key(self):
        with (patch.object(readiness, "catalog", side_effect=self.advertised) as inventory,
                patch.object(ai_providers, "call") as generate,
                patch.object(model_spend, "grant") as grant):
            value = readiness.report(self.environment(), check_models=True)
        self.assertTrue(value["configuration_ready"])
        self.assertEqual(inventory.call_count, 5)
        self.assertEqual(len(value["model_inventory"]), 5)
        self.assertTrue(all(row["metadata_access_verified"] for row in value["model_inventory"].values()))
        self.assertFalse(value["inference_access_and_effort_passthrough_verified"])
        self.assertFalse(value["scientific_completion"])
        generate.assert_not_called()
        grant.assert_not_called()

    def test_missing_catalog_model_blocks_only_with_explicit_missing_model_evidence(self):
        def absent(provider, environment):
            result = self.advertised(provider, environment)
            return result - {"gpt-5.6-luna"}
        with patch.object(readiness, "catalog", side_effect=absent):
            value = readiness.report(self.environment(), check_models=True)
        self.assertFalse(value["configuration_ready"])
        row = value["model_inventory"]["cheapai-gpt-discount"]
        self.assertTrue(row["metadata_access_verified"])
        self.assertEqual(row["required_models_missing"], ["gpt-5.6-luna"])
        self.assertTrue(any("gpt-5.6-luna" in error for error in value["configuration_errors"]))

    def test_catalog_http_failure_is_controlled_and_never_claims_metadata_access(self):
        def unavailable(provider, environment):
            if provider == "codekey-deepseek":
                raise ValueError("catalog HTTP 429")
            return self.advertised(provider, environment)
        with patch.object(readiness, "catalog", side_effect=unavailable):
            value = readiness.report(self.environment(), check_models=True)
        self.assertFalse(value["configuration_ready"])
        self.assertFalse(value["model_inventory"]["codekey-deepseek"]["metadata_access_verified"])
        self.assertEqual(value["model_inventory"]["codekey-deepseek"]["diagnostic"], "catalog HTTP 429")

    def test_report_never_contains_production_secrets_or_grants_research_authority(self):
        env = {**self.environment(), "DR_OS_AUTOMATIC_RESEARCH_ENABLED": "true"}
        with patch.object(readiness, "catalog", side_effect=self.advertised):
            value = readiness.report(env, check_models=True)
        serialized = json.dumps(value)
        for secret in self.environment().values():
            self.assertNotIn(secret, serialized)
        self.assertTrue(value["automatic_research_enabled"])
        self.assertFalse(value["new_spending_authority"])
        self.assertEqual(value["model_generation_calls"], 0)

    def test_catalog_uses_get_header_credentials_and_refuses_redirects(self):
        opener = Mock()
        opener.open.return_value = FakeResponse({"data": [{"id": "gpt-6.1-sol"}, {"id": "gpt-6-astra"}]})
        with patch.object(readiness.urllib.request, "build_opener", return_value=opener):
            values = readiness.catalog("cheapai-gpt-pro", self.environment())
        self.assertEqual(values, {"gpt-6.1-sol", "gpt-6-astra"})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, "https://cheapai.info/v1/models")
        self.assertNotIn("fixture-secret", request.full_url)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["authorization"], "Bearer fixture-secret-cheapai-gpt-pro")
        self.assertEqual(headers["user-agent"], "lunwen-production-research/1.0")
        self.assertEqual(headers["accept"], "application/json")
        self.assertNotIn("Python", headers["user-agent"])
        self.assertNotIn("fixture-secret", headers["user-agent"])
        opener.open.assert_called_once()
        with self.assertRaises(ValueError):
            readiness.NoRedirect().redirect_request(None, None, 307, "redirect", {}, "https://other.example")

    def test_google_catalog_uses_native_auth_and_preserves_exact_high_identifier(self):
        opener = Mock()
        opener.open.return_value = FakeResponse({"models": [{"name": "models/gemini-4-argon-high"}]})
        with patch.object(readiness.urllib.request, "build_opener", return_value=opener):
            values = readiness.catalog("codekey-gemini", self.environment())
        self.assertEqual(values, {"gemini-4-argon-high"})
        self.assertNotIn("gemini-4-argon", values)
        self.assertNotIn("gemini-4-argon-medium", values)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://codekey.ai/v1beta/models")
        self.assertEqual(request.get_method(), "GET")
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["x-goog-api-key"], "fixture-secret-codekey-gemini")
        self.assertNotIn("authorization", headers)
        opener.open.assert_called_once()

    def test_google_catalog_rejects_non_native_names_and_does_not_fall_back_or_generate(self):
        for name in ("gemini-4-argon-high", "publishers/gemini-4-argon-high", "models/gemini-4-argon-high/extra"):
            opener = Mock()
            opener.open.return_value = FakeResponse({"models": [{"name": name}]})
            with patch.object(readiness.urllib.request, "build_opener", return_value=opener), \
                    patch.object(ai_providers, "call") as generate:
                with self.assertRaises(ValueError):
                    readiness.catalog("codekey-gemini", self.environment())
            opener.open.assert_called_once()
            generate.assert_not_called()

    def test_http_error_body_and_secret_are_not_in_catalog_diagnostic(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://codekey.ai/v1/models", 503,
            "fixture-secret-in-error", {}, io.BytesIO(b"private response token"))
        with patch.object(readiness.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(ValueError) as error:
                readiness.catalog("codekey-gemini", self.environment())
        self.assertEqual(str(error.exception), "catalog HTTP 503")
        opener.open.assert_called_once()

    def test_catalog_oversize_and_invalid_json_fail_without_retries(self):
        for response in (b"not JSON", b" " * 2_000_001):
            opener = Mock()
            opener.open.return_value = FakeResponse(response)
            with patch.object(readiness.urllib.request, "build_opener", return_value=opener):
                with self.assertRaises(ValueError):
                    readiness.catalog("codekey-gemini", self.environment())
            opener.open.assert_called_once()

    def test_malformed_catalog_is_not_treated_as_successful_empty_inventory(self):
        for data in ({}, {"data": "not a list"}, [], {"data": [{"id": None}]},
                     {"data": [{"id": "gpt invalid model"}]}, {"success": False, "data": []}):
            opener = Mock()
            opener.open.return_value = FakeResponse(data)
            with patch.object(readiness.urllib.request, "build_opener", return_value=opener):
                with self.assertRaises(ValueError):
                    readiness.catalog("cheapai-gpt-pro", self.environment())
            opener.open.assert_called_once()

    def test_unknown_provider_or_missing_credential_never_sends_a_request(self):
        with patch.object(readiness.urllib.request, "build_opener") as opener:
            for provider, env in (("unapproved-route", self.environment()), ("cheapai-gpt-pro", {})):
                with self.assertRaises(ValueError):
                    readiness.catalog(provider, env)
            opener.assert_not_called()

    def test_explicit_environment_selects_policy_and_ignores_global_policy_override(self):
        policy = json.loads(model_routing.DEFAULT_POLICY.read_text(encoding="utf-8"))
        policy["policy_version"] = "fixture-explicit-policy"
        raw = json.dumps(policy).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture-policy.json"
            path.write_bytes(raw)
            env = {**self.environment(), "DR_OS_ROUTING_CONFIG": str(path)}
            with patch.dict("os.environ", {"DR_OS_ROUTING_CONFIG": str(Path(directory) / "missing-global-policy.json")}, clear=True):
                value = readiness.report(env)
                default_value = readiness.report(self.environment())
        self.assertTrue(value["configuration_ready"])
        self.assertEqual(value["policy_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertTrue(default_value["configuration_ready"])

    def test_invalid_policy_reports_only_controlled_diagnostic(self):
        with patch.object(model_routing, "load_policy", side_effect=ValueError("fixture-private-policy-content")):
            value = readiness.report(self.environment())
        self.assertFalse(value["configuration_ready"])
        self.assertNotIn("fixture-private-policy-content", json.dumps(value))


if __name__ == "__main__":
    unittest.main()
