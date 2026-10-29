"""Optional relay groups: simulated native protocols and exact debit binding.

No test contacts a real endpoint or establishes model/channel quality.
"""
from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import ai_providers as providers, billing_quotes, relay_billing as billing


ROOT = Path(__file__).resolve().parents[1]
NEW_GROUPS = {
    "cheapai-kiro-discount": ("anthropic", "https://cheapai.info", "DR_OS_CHEAPAI_KIRO_DISCOUNT_KEY"),
    "cheapai-ccmax": ("anthropic", "https://cheapai.info", "DR_OS_CHEAPAI_CCMAX_KEY"),
    "codekey-codex-pro": ("openai", "https://codekey.ai", "DR_OS_CODEKEY_CODEX_PRO_KEY"),
    "codekey-codex-discount": ("openai", "https://codekey.ai", "DR_OS_CODEKEY_CODEX_DISCOUNT_KEY"),
    "codekey-kiro-standard": ("anthropic", "https://codekey.ai", "DR_OS_CODEKEY_KIRO_STANDARD_KEY"),
}


def response(family, model):
    if family == "google":
        return {"modelVersion": model, "responseId": "google-fixture",
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "fixture"}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}
    if family == "anthropic":
        return {"model": model, "id": "claude-fixture", "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "fixture"}],
                "usage": {"input_tokens": 10, "output_tokens": 5}}
    return {"model": model, "id": "openai-fixture", "status": "completed",
            "output_text": "fixture", "usage": {"input_tokens": 10, "output_tokens": 5}}


class DynamicProviderTests(unittest.TestCase):
    def test_new_group_ids_and_credentials_are_independent_and_offline(self):
        for name, (family, root, setting) in NEW_GROUPS.items():
            with self.subTest(provider=name):
                self.assertIn(name, providers.PROVIDERS)
                config = providers.configuration(name, {setting: "fixture-only-secret"})
                self.assertEqual((config["family"], config["root"], config["key_setting"]),
                                 (family, root, setting))
                self.assertTrue(config["configured"])
                self.assertNotIn("fixture-only-secret", json.dumps(config))
                self.assertEqual(config["billing_identity"]["group"], name)
                self.assertFalse(providers.configuration(name, {"OPENAI_API_KEY": "unrelated"})["configured"])
        shared = {}
        for name, spec in providers.PRODUCTION_PROVIDERS.items():
            shared.setdefault(spec["key_setting"], set()).add(name)
        self.assertEqual([names for names in shared.values() if len(names) > 1],
                         [{"codekey-gemini", "codekey-gemini-chat"}])

    def test_optional_missing_key_never_uses_another_groups_key(self):
        for name in NEW_GROUPS:
            with self.subTest(provider=name), patch.dict(os.environ,
                    {"DR_OS_CHEAPAI_GPT_PRO_KEY": "existing-key", "GITHUB_ACTIONS": "true"}, clear=True), \
                    patch.object(providers, "_production_request") as transport:
                with self.assertRaisesRegex(providers.ProviderError, "not configured"):
                    providers.call(name, "fixture")
                transport.assert_not_called()

    def test_openai_groups_keep_exact_allowlist_and_effort_payload(self):
        models = {"gpt-6.1-sol", "gpt-6-astra", "gpt-5.6-luna", "gpt-6.1-terra"}
        for name, spec in providers.PRODUCTION_PROVIDERS.items():
            if spec["family"] != "openai":
                continue
            self.assertEqual(set(spec["models"]), models)
            for model in models:
                self.assertEqual(providers.production_supported_efforts(name, model), ("low", "medium", "high"))
                for effort in ("low", "medium", "high"):
                    with self.subTest(provider=name, model=model, effort=effort), patch.dict(os.environ,
                            {spec["key_setting"]: "fixture-only-secret"}, clear=True), patch.object(
                            providers, "_production_request", return_value=response("openai", model)) as transport:
                        result = providers.call(name, "fixture", model=model, reasoning_effort=effort)
                        endpoint, headers, payload, _ = transport.call_args.args
                        self.assertEqual(endpoint, spec["root"] + "/v1/responses")
                        self.assertEqual(headers, {"Authorization": "Bearer fixture-only-secret"})
                        self.assertEqual(payload["reasoning"], {"effort": effort})
                        self.assertIs(payload["store"], False)
                        self.assertEqual(payload["tools"], [])
                        self.assertEqual(result.requested_effort, effort)
                        transport.assert_called_once()

    def test_all_claude_groups_use_messages_high_without_forging_lower_support(self):
        for name, spec in providers.PRODUCTION_PROVIDERS.items():
            if spec["family"] != "anthropic":
                continue
            for model in ("claude-sonnet-5-5", "claude-opus-5-5"):
                self.assertEqual(providers.production_supported_efforts(name, model), ("high",))
                with self.subTest(provider=name, model=model), patch.dict(os.environ,
                        {spec["key_setting"]: "fixture-only-secret"}, clear=True), patch.object(
                        providers, "_production_request", return_value=response("anthropic", model)) as transport:
                    providers.call(name, "fixture", model=model, reasoning_effort="high")
                    endpoint, headers, payload, _ = transport.call_args.args
                    self.assertEqual(endpoint, spec["root"] + "/v1/messages")
                    self.assertEqual(headers["x-api-key"], "fixture-only-secret")
                    self.assertNotIn("Authorization", headers)
                    self.assertEqual(payload["thinking"], {"type": "adaptive"})
                    self.assertEqual(payload["output_config"], {"effort": "high"})
                    self.assertEqual(payload["tools"], [])
                    transport.assert_called_once()
                for effort in ("low", "medium"):
                    with patch.object(providers, "_production_request") as transport:
                        with self.assertRaises(providers.ProviderError):
                            providers.call(name, "fixture", model=model, reasoning_effort=effort)
                        transport.assert_not_called()

    def test_google_high_id_requires_matching_high_native_thinking_level(self):
        name = "codekey-gemini"
        spec = providers.PRODUCTION_PROVIDERS[name]
        self.assertEqual(spec["model"], "gemini-4-argon")
        self.assertEqual(providers.production_supported_efforts(name, spec["model"]), ("low", "medium", "high"))
        self.assertEqual(providers.production_supported_efforts(name, "gemini-4-argon-high"), ("high",))
        for effort in ("high",):
            with self.subTest(effort=effort), patch.dict(os.environ,
                    {spec["key_setting"]: "fixture-only-secret"}, clear=True), patch.object(
                    providers, "_production_request", return_value=response("google", spec["model"])) as transport:
                result = providers.call(name, "fixture", reasoning_effort=effort)
                self.assertEqual(transport.call_args.args[2]["generationConfig"]["thinkingConfig"],
                                 {"thinkingLevel": effort.upper()})
                self.assertEqual(result.requested_effort, effort)
        for effort in ("low", "medium"):
            with self.subTest(effort=effort), patch.object(providers, "_production_request") as transport:
                with self.assertRaises(providers.ProviderError):
                    providers.call(name, "fixture", model="gemini-4-argon-high", reasoning_effort=effort)
                transport.assert_not_called()

    def test_unknown_effort_or_model_is_not_a_fallback_permission(self):
        for name, spec in providers.PRODUCTION_PROVIDERS.items():
            for kwargs in ({"reasoning_effort": "automatic"}, {"model": "unverified-alias"}):
                with self.subTest(provider=name, kwargs=kwargs), patch.object(providers, "_production_request") as transport:
                    with self.assertRaises(providers.ProviderError):
                        providers.call(name, "fixture", **kwargs)
                    transport.assert_not_called()
        with self.assertRaises(providers.ProviderError):
            providers.production_supported_efforts("not-configured", "gpt-6.1-sol")

    def test_new_group_identity_failure_stops_after_one_transport(self):
        for name in NEW_GROUPS:
            spec = providers.PRODUCTION_PROVIDERS[name]
            data = response(spec["family"], "unverified-alias")
            with self.subTest(provider=name), patch.dict(os.environ,
                    {spec["key_setting"]: "fixture-only-secret"}, clear=True), patch.object(
                    providers, "_production_request", return_value=data) as transport:
                with self.assertRaisesRegex(providers.ProviderError, "mismatched"):
                    providers.call(name, "fixture")
                transport.assert_called_once()

    def test_new_groups_use_their_exact_site_meter_and_own_key(self):
        old_denomination = billing._CHEAP_DENOMINATION
        try:
            for name, (_, root, setting) in NEW_GROUPS.items():
                billing._CHEAP_DENOMINATION = None
                if root == "https://codekey.ai":
                    values = [{"usage": {"total": {"requests": 1, "actual_cost": 0.01}}}]
                    expected = ["https://codekey.ai/v1/usage"]
                else:
                    values = [{"data": {"quota_per_unit": 500000, "quota_display_type": "USD"}}, {"data": []}]
                    expected = ["https://cheapai.info/api/status", "https://cheapai.info/api/log/token"]
                with self.subTest(provider=name), patch.object(billing, "_get_json", side_effect=values) as get:
                    meter = billing.read_meter(name, environment={setting: "fixture-only-secret"})
                    self.assertEqual(meter["provider"], name)
                    self.assertEqual([call.args[0] for call in get.call_args_list], expected)
                    self.assertEqual(get.call_args.args[1], {"Authorization": "Bearer fixture-only-secret"})
                    self.assertNotIn("fixture-only-secret", json.dumps(meter))
        finally:
            billing._CHEAP_DENOMINATION = old_denomination

    def test_new_groups_settle_only_their_bound_debit_and_record_own_site(self):
        for name, (_, root, _) in NEW_GROUPS.items():
            model = providers.PRODUCTION_PROVIDERS[name]["model"]
            if root == "https://codekey.ai":
                before = {"provider": name, "kind": "codekey_total_actual_cost", "requests": 1, "cost_cny": 0.01}
                after = {**before, "requests": 2, "cost_cny": 0.0102}
                source = root + "/v1/usage"
            else:
                before = {"provider": name, "kind": "cheapai_quota_history", "quota_per_unit": 500000, "rows": []}
                after = {**before, "rows": [{"id": 1, "model_name": model, "quota": 100, "created_at": 1}]}
                source = root + "/api/log/token"
            with self.subTest(provider=name), patch.object(billing, "read_meter", return_value=after) as read:
                result = billing.settle(name, model, before)
                self.assertAlmostEqual(result["actual_cost_cny"], 0.0002)
                self.assertEqual(result["debit_evidence"]["source"], source)
                read.assert_called_once_with(name)
            with patch.object(billing, "read_meter") as read:
                with self.assertRaises(billing.BillingReconciliationError):
                    billing.settle(name, model, {**before, "provider": "another-group"})
                read.assert_not_called()

    def test_meter_rejects_tampered_root_before_network_or_snapshot_branch(self):
        for root in ("https://other.example", "https://codekey.ai:443", "https://cheapai.info/extra"):
            spec = {**providers.PRODUCTION_PROVIDERS["codekey-codex-pro"], "root": root}
            with patch.dict(providers.PRODUCTION_PROVIDERS, {"codekey-codex-pro": spec}), \
                    patch.object(billing, "_get_json") as get, patch.object(billing, "read_meter") as read:
                with self.assertRaises(billing.BillingReconciliationError):
                    billing.settle("codekey-codex-pro", "gpt-6.1-sol", {})
                get.assert_not_called()
                read.assert_not_called()

    def test_optional_quotes_are_exact_scaled_upper_bounds_with_cache_write_rates(self):
        document = json.loads((ROOT / "config/model-pricing.json").read_text(encoding="utf-8"))
        raw = {(row["provider"], row["model"]): row for row in document["quotes"]}
        factors = {"cheapai-gpt-pro": Decimal("0.22"), "cheapai-gpt-discount": Decimal("0.08"),
                   "codekey-codex-pro": Decimal("0.2"), "codekey-codex-discount": Decimal("0.12"),
                   "cheapai-kiro-discount": Decimal("0.115"), "cheapai-ccmax": Decimal("1"),
                   "codekey-kiro-standard": Decimal("0.12")}
        for name, spec in providers.PRODUCTION_PROVIDERS.items():
            for model in spec["models"]:
                config = providers.configuration(name, {})
                if (name, model) not in raw:
                    # Evaluation-only candidates need a separately authorized
                    # exact quote; adding transport support never invents one.
                    self.assertTrue(model == "gpt-6.1-terra" or
                                    name in {"codekey-kimi", "codekey-gemini-chat"})
                    with self.assertRaises(ValueError):
                        billing_quotes.select(document, name,
                            spec["root"] + spec["path"].format(model=model), model, config["billing_identity"])
                    continue
                quote = billing_quotes.select(document, name, spec["root"] + spec["path"].format(model=model),
                                               model, config["billing_identity"])
                self.assertEqual(quote["billing_identity"]["group"], name)
                row = raw[(name, model)]
                if not row["price_version"].startswith("derived-"):
                    continue
                source = ("codekey-kiro-enterprise" if spec["family"] == "anthropic" else
                          "cheapai-gpt-discount" if model == "gpt-5.6-luna" else "cheapai-gpt-pro")
                source_factor = Decimal("0.35") if spec["family"] == "anthropic" else factors[source]
                original = raw[(source, model)]
                self.assertIn(source, row["price_version"])
                self.assertIn("owner-group-screenshot", row["price_version"])
                rows = row.get("context_brackets", [row])
                old_rows = original.get("context_brackets", [original])
                self.assertEqual(len(rows), len(old_rows))
                for current, prior in zip(rows, old_rows):
                    for field in (*billing_quotes.RATE_FIELDS, *billing_quotes.CACHE_WRITE_TTL_RATES):
                        if field in prior:
                            expected = Decimal(str(prior[field])) * factors[name] / source_factor
                            self.assertLessEqual(abs(Decimal(str(current[field])) - expected), Decimal("0.000000000001"))


if __name__ == "__main__":
    unittest.main()

