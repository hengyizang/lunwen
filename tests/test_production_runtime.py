"""Production control-plane regression tests with fake transport and authority.

All files and owner grants belong to temporary fixtures. No credentials,
network calls, real spending approvals or live model requests are used.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ai_providers, metadata_contract, model_runtime, model_spend, relay_billing


class ProductionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        from tests.relay_guard_fixtures import install_fake_guard
        self.shared_guard=install_fake_guard(self.stack)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.project = Path(directory) / "fixture-project"
        (self.project / "state").mkdir(parents=True)
        (self.project / "state" / "run.json").write_text(json.dumps({"active_paper": "P01"}), encoding="utf-8")
        env = {"DR_OS_ROUTING_PROFILE": "production", "DR_OS_REQUIRE_MODEL_AUTH": "1",
               "GITHUB_ACTIONS":"true", "DR_OS_REQUIRE_REMOTE_RESERVATION":"1"}
        env.update({spec["key_setting"]: "fixture-no-real-key"
                    for spec in ai_providers.PRODUCTION_PROVIDERS.values()})
        self.stack.enter_context(patch.dict("os.environ", env, clear=True))
        self.catalog = self.stack.enter_context(patch("scripts.production_readiness.catalog",
            side_effect=lambda provider, environment: set(ai_providers.PRODUCTION_PROVIDERS[provider]["models"])))
        self.sync = self.stack.enter_context(patch("scripts.cloud_checkpoint.sync_billing", return_value=None))
        model_spend.write(self.project, model_spend.initial())
        model_spend.grant(self.project, new_ceiling_cny=300, actor="Fake Owner",
                          run_id="fixture-approval-not-real")

    def contract(self):
        return {"sources": [{"source_id": "S1", "text": "Study A was published in 2024.",
                             "locator": "fixture:p1"}], "fields": ["title"]}

    def extracted(self, value="Study A"):
        return json.dumps({"records": [{"source_id": "S1", "fields": {"title": {
            "value": value, "quote": "Study A", "locator": "fixture:p1"}}}]})

    def attachment(self):
        value = b"%PDF-1.4\nfixture evidence"
        return {"mime_type": "application/pdf", "data_base64": base64.b64encode(value).decode(),
                "sha256": hashlib.sha256(value).hexdigest(), "filename": "fixture.pdf"}

    def result(self, provider, prompt, **kwargs):
        spec = ai_providers.PRODUCTION_PROVIDERS[provider]
        model = kwargs.get("model", spec["model"])
        return ai_providers.ModelResult(provider, model,
            self.extracted() if model == "gpt-5.6-luna" else "fixture answer",
            {"input_tokens": 100, "output_tokens": 20}, "fixture-request", model,
            spec["protocol"], spec["root"] + spec["path"].format(model=model),
            "cheapai" if provider.startswith("cheapai") else "codekey",
            completion_status="completed", requested_effort=kwargs.get("reasoning_effort"))

    def debit(self, cost=0.001):
        return {"actual_cost_cny": cost, "debit_evidence": {
            "source": "https://codekey.ai/v1/usage", "exactly_one_new_gateway_request": True}}

    def call(self, **kwargs):
        options = {"run_id": "fixture-run", "stage": "intake", "role": "persistent-writer",
                   "provider": "openai", "prompt": "source-bound fixture", "max_output_tokens": 100}
        options.update(kwargs)
        return model_runtime.call(self.project, **options)

    def counter(self, requests=10, cost=0.02):
        return {"provider": "codekey-deepseek", "kind": "codekey_total_actual_cost",
                "requests": requests, "cost_cny": cost}

    def test_seven_models_forward_exact_channel_model_and_effort(self):
        cases = [
            ({}, "cheapai-gpt-pro", "gpt-6.1-sol", "high"),
            ({"stage": "topic-intelligence"}, "cheapai-gpt-pro", "gpt-6-astra", "high"),
            ({"stage": "auxiliary", "role": "metadata-extraction", "source_contract": self.contract()},
                "cheapai-gpt-discount", "gpt-5.6-luna", "medium"),
            ({"role": "semantic-planner", "provider": "anthropic"},
                "codekey-kiro-enterprise", "claude-sonnet-5-5", "high"),
            ({"role": "independent-critic-final", "provider": "anthropic"},
                "codekey-kiro-enterprise", "claude-opus-5-5", "high"),
            ({"stage": "auxiliary", "role": "engineering-diagnosis"},
                "codekey-deepseek", "deepseek-v4.1-flash", "high"),
            ({"stage": "auxiliary", "role": "multimodal-inspection", "attachments": [self.attachment()]},
                "codekey-gemini", "gemini-4-argon", "high"),
        ]
        with (patch.object(model_runtime.ai_providers, "call", side_effect=self.result) as post,
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit())):
            for options, provider, model, effort in cases:
                with self.subTest(model=model):
                    self.call(**options)
                    self.assertEqual(post.call_args.args[0], provider)
                    self.assertEqual(post.call_args.kwargs["model"], model)
                    self.assertEqual(post.call_args.kwargs["reasoning_effort"], effort)
        self.assertEqual(post.call_count, 7)

    def test_post_only_follows_persisted_owner_authority_and_synced_reservation(self):
        events = []
        def transport(provider, prompt, **kwargs):
            state = model_spend.read(self.project, required=True)
            self.assertEqual(state["authorized_ceiling_cny"], 300)
            self.assertEqual(len(state["reservations"]), 1)
            self.assertGreater(model_spend.reserved(state), 0)
            self.assertEqual(events, ["synced"])
            return self.result(provider, prompt, **kwargs)
        with (patch.object(model_runtime.ai_providers, "call", side_effect=transport),
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit()),
                patch("scripts.cloud_checkpoint.sync_billing", side_effect=lambda project: events.append("synced"))):
            self.call()
        self.assertEqual(model_spend.read(self.project)["spent_cny"], 0.001)

    def test_missing_or_zero_owner_ledger_never_grants_itself_or_calls_model(self):
        for missing in (False, True):
            model_spend.write(self.project, model_spend.initial())
            if missing:
                (self.project / model_spend.FILE).unlink()
            with (patch.object(model_runtime.ai_providers, "call") as post,
                    patch.object(relay_billing, "read_meter") as meter,
                    patch.object(model_spend, "grant", wraps=model_spend.grant) as grant):
                with self.assertRaises((model_runtime.ModelBudgetError, model_spend.SpendControlError)):
                    self.call()
                post.assert_not_called()
                meter.assert_not_called()
                grant.assert_not_called()

    def test_catalog_alias_does_not_add_a_payment_approval_gate(self):
        self.catalog.side_effect = None
        self.catalog.return_value = {"gemini-4-argon-high"}
        with (patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit()),
                patch.object(ai_providers, "call", side_effect=self.result) as post):
            result = self.call(stage="auxiliary", role="multimodal-inspection", attachments=[self.attachment()])
        self.assertEqual(result.reported_model, "gemini-4-argon")
        self.assertEqual(post.call_args.kwargs["model"], "gemini-4-argon")
        self.catalog.assert_not_called()

    def test_unavailable_catalog_does_not_block_a_configured_identity_bound_call(self):
        self.catalog.side_effect = ValueError("catalog unavailable")
        with (patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit()),
                patch.object(ai_providers, "call", side_effect=self.result) as post):
            self.call()
        post.assert_called_once()
        self.catalog.assert_not_called()
        self.assertEqual(model_spend.read(self.project)["spent_cny"], 0.001)

    def test_exact_cache_replay_needs_no_live_catalog_or_paid_request(self):
        with (patch.object(ai_providers, "call", side_effect=self.result) as post,
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}) as meter,
                patch.object(relay_billing, "settle", return_value=self.debit())):
            self.call()
            self.catalog.assert_not_called()
            self.catalog.reset_mock(side_effect=True)
            self.catalog.side_effect = ValueError("catalog unavailable")
            result = self.call(run_id="cached-offline")
            self.assertTrue(result.cache_hit)
            self.catalog.assert_not_called()
            post.assert_called_once()
            meter.assert_called_once()

    def test_unavailable_fee_read_uses_accounted_upper_bound_and_allows_work(self):
        with (patch.object(relay_billing, "read_meter", side_effect=relay_billing.BillingReconciliationError("HTTP 429")),
                patch.object(ai_providers, "call", side_effect=self.result) as post):
            self.call()
            self.call(prompt="different second request")
        self.assertEqual(post.call_count, 2)
        state = model_spend.read(self.project)
        self.assertEqual(state["reservations"], {})
        self.assertGreater(state["spent_cny"], 0)
        self.assertTrue(all(event["cost_basis"] == "conservative_upper_bound" for event in state["settlement_events"]))
        self.assertTrue(all("actual_cost_cny" not in event for event in state["settlement_events"]))
        self.assertTrue(all(row["cost_status"] == "estimated_upper_bound" for row in model_runtime.ledger_entries(self.project)))

    def test_execution_location_adds_no_extra_payment_permission(self):
        with (patch.dict("os.environ", {"GITHUB_ACTIONS": "", "DR_OS_REQUIRE_REMOTE_RESERVATION": ""}),
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit()),
                patch.object(ai_providers, "call", side_effect=self.result) as post):
            self.call()
        post.assert_called_once()
        self.assertEqual(model_spend.read(self.project)["spent_cny"], 0.001)

    def test_ambiguous_fee_is_counted_conservatively_without_an_approval_pause(self):
        with (patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(ai_providers, "call", side_effect=self.result) as post,
                patch.object(relay_billing, "settle", side_effect=relay_billing.BillingReconciliationError("concurrent debits"))):
            self.call()
            self.call(prompt="second bounded request")
        self.assertEqual(post.call_count, 2)
        state = model_spend.read(self.project)
        self.assertGreater(state["spent_cny"], 0)
        self.assertEqual(state["reservations"], {})
        self.assertLess(state["spent_cny"], state["authorized_ceiling_cny"])
        self.assertTrue(all(row["usage_estimated"] for row in model_runtime.ledger_entries(self.project)))

    def test_502_has_one_post_no_fallback_and_keeps_full_reservation(self):
        with (patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(model_runtime.ai_providers, "call", side_effect=ai_providers.ProviderError("API HTTP 502")) as post,
                patch.object(relay_billing, "settle") as settle):
            with self.assertRaises(ai_providers.ProviderError):
                self.call()
        post.assert_called_once()
        settle.assert_not_called()
        self.assertGreater(model_spend.reserved(model_spend.read(self.project)), 0)
        self.assertTrue(model_runtime.ledger_entries(self.project)[0]["zero_cost_not_confirmed"])
        held = model_spend.reserved(model_spend.read(self.project))
        with (patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(ai_providers, "call", side_effect=self.result) as next_post,
                patch.object(relay_billing, "settle", return_value=self.debit())):
            self.call(prompt="independent bounded work after the unresolved transport")
        next_post.assert_called_once()
        self.assertEqual(model_spend.reserved(model_spend.read(self.project)), held)
        self.assertGreater(model_spend.read(self.project)["spent_cny"], 0)

    def test_unresolved_reservation_only_blocks_when_remaining_total_is_insufficient(self):
        model_spend.reserve(self.project, max_cost_cny=299.999999, paper_id=None,
                            paper_limit_cny=1, run_id="unresolved-previous-request")
        with patch.object(ai_providers, "call") as post, patch.object(relay_billing, "read_meter") as meter:
            with self.assertRaises(model_runtime.ModelBudgetError):
                self.call()
        post.assert_not_called()
        meter.assert_not_called()

    def test_actual_charge_above_estimate_uses_remaining_total_without_extra_approval(self):
        authority = model_spend.read(self.project)["authorization_events"]
        charges = []
        def gateway_settlement(provider, model, before):
            pending = next(iter(model_spend.read(self.project)["reservations"].values()))
            charges.append(pending["max_cost_cny"] + 0.125)
            return self.debit(charges[-1])
        with (patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(ai_providers, "call", side_effect=self.result) as post,
                patch.object(relay_billing, "settle", side_effect=gateway_settlement),
                patch.object(model_spend, "grant", wraps=model_spend.grant) as grant):
            self.call()
            self.call(prompt="different request can use the remaining total")
        self.assertEqual(post.call_count, 2)
        grant.assert_not_called()
        state = model_spend.read(self.project)
        self.assertAlmostEqual(state["spent_cny"], sum(charges))
        self.assertEqual(state["reservations"], {})
        self.assertEqual(state["authorization_events"], authority)
        self.assertAlmostEqual(model_runtime.budget_status(self.project)["project_remaining"], 300-sum(charges))

    def test_independent_wallet_debit_settles_missing_cache_ttl_and_promotion(self):
        def cached_response(provider, prompt, **kwargs):
            result = self.result(provider, prompt, **kwargs)
            result.usage.update(cache_creation_input_tokens=20, cache_read_input_tokens=10)
            return result
        with (patch.object(model_runtime.ai_providers, "call", side_effect=cached_response),
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit(0.000123))):
            self.call(role="semantic-planner", provider="anthropic")
        state = model_spend.read(self.project)
        self.assertEqual(state["reservations"], {})
        self.assertEqual(state["spent_cny"], 0.000123)
        receipt = model_runtime.ledger_entries(self.project)[0]
        self.assertFalse(receipt["usage_estimated"])
        self.assertEqual(receipt["billing"]["independent_gateway_debit"]["actual_cost_cny"], 0.000123)

    def test_media_reservation_uses_declared_context_rates_without_arbitrary_multiplier(self):
        original = model_runtime.billing_quotes.reserve_cost
        ceilings = []
        def quote(*args, **kwargs):
            ceilings.append((args[1], args[2]))
            return original(*args, **kwargs)
        with (patch.object(model_runtime.ai_providers, "call", side_effect=self.result),
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit()),
                patch.object(model_runtime.billing_quotes, "reserve_cost", side_effect=quote),
                patch.object(model_spend, "reserve", wraps=model_spend.reserve) as reserve):
            self.call(stage="auxiliary", role="multimodal-inspection", attachments=[self.attachment()])
        self.assertEqual(ceilings[0][0], 1048576)
        production_quote = model_runtime.pricing("codekey-gemini", "gemini-4-argon")
        expected = round(original(production_quote, 1048576, 100, {}), 8)
        self.assertEqual(reserve.call_args.kwargs["max_cost_cny"], expected)

    def test_cache_identity_includes_effort_attachment_policy_and_billing_scope(self):
        base = {"provider": "cheapai-gpt-pro", "prompt": "identical", "system": None,
                "max_output_tokens": 100, "model": "gpt-6.1-sol", "role": "persistent-writer",
                "stage": "intake", "reasoning_effort": "high", "routing_policy_sha256": "a" * 64,
                "attachment_identity": [{"sha256": "b" * 64, "mime_type": "application/pdf", "size_bytes": 20}],
                "billing_quote": {"billing_identity": {"plan": "production", "group": "cheapai-gpt-pro", "mode": "standard"}}}
        key, identity = model_runtime._cache_key(**base)
        for changed in ({"reasoning_effort": "medium"}, {"routing_policy_sha256": "c" * 64},
                        {"attachment_identity": [{"sha256": "d" * 64, "mime_type": "application/pdf", "size_bytes": 20}]},
                        {"billing_quote": {"billing_identity": {"plan": "different"}}}):
            self.assertNotEqual(key, model_runtime._cache_key(**{**base, **changed})[0])
        self.assertEqual(identity["reasoning_effort"], "high")

    def test_caller_cannot_lower_scientific_effort(self):
        with (patch.object(model_runtime.ai_providers, "call") as post,
                patch.object(relay_billing, "read_meter") as meter):
            with self.assertRaises(ValueError):
                self.call(reasoning_effort="low")
            post.assert_not_called()
            meter.assert_not_called()

    def test_fresh_critics_never_replay_a_response_as_another_review(self):
        with (patch.object(model_runtime.ai_providers, "call", side_effect=self.result) as post,
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit())):
            for role in ("independent-critic-initial", "independent-critic-final", "independent-critique"):
                for index in (1, 2):
                    result = self.call(role=role, provider="anthropic", run_id=f"{role}-{index}")
                    self.assertFalse(result.cache_hit)
        self.assertEqual(post.call_count, 6)
        self.assertFalse(list((self.project / ".cache" / "model-responses").glob("*.json")))

    def test_metadata_input_contract_is_checked_before_any_meter_or_post(self):
        with (patch.object(model_runtime.ai_providers, "call") as post,
                patch.object(relay_billing, "read_meter") as meter):
            with self.assertRaises(metadata_contract.MetadataContractError):
                self.call(stage="auxiliary", role="metadata-extraction", source_contract={"sources": [], "fields": ["title"]})
            post.assert_not_called()
            meter.assert_not_called()

    def test_engineering_contract_is_required_before_meter_reservation_or_post(self):
        with patch.object(model_runtime.ai_providers,"call") as post, patch.object(relay_billing,"read_meter") as meter:
            for contract in (None,{"sources":[]}):
                with self.assertRaises((ValueError,model_runtime.ModelBudgetError)):
                    self.call(stage="auxiliary",role="engineering-test-design",source_contract=contract)
            post.assert_not_called();meter.assert_not_called()
            self.assertEqual(model_spend.read(self.project)["reservations"],{})

    def test_engineering_unsupported_quote_is_billed_once_and_not_cached(self):
        contract={"sources":[{"source_id":"S1","text":"return x[0]","locator":"snapshot:line1"}]}
        def invalid(provider,prompt,**kwargs):
            result=self.result(provider,prompt,**kwargs)
            result.text=json.dumps({"abstain":False,"findings":[{"source_id":"S1","locator":"snapshot:line1",
                "quote":"invented source","observation":"suspected defect","suggestion":"candidate fix","verification":"test it"}]})
            return result
        with patch.object(model_runtime.ai_providers,"call",side_effect=invalid) as post, \
             patch.object(relay_billing,"read_meter",return_value={"fixture":"before"}), \
             patch.object(relay_billing,"settle",return_value=self.debit()):
            with self.assertRaisesRegex(ValueError,"unsupported source"):
                self.call(stage="auxiliary",role="engineering-code-review",source_contract=contract)
        post.assert_called_once()
        self.assertEqual(model_spend.read(self.project)["spent_cny"],0.001)
        self.assertFalse(list((self.project/".cache/model-responses").glob("*.json")))
        self.assertEqual(model_runtime.ledger_entries(self.project)[-1]["validation_status"],"source_contract_failed_no_retry")

    def test_engineering_cache_reuses_same_request_but_not_changed_sources_or_roles(self):
        contract={"sources":[{"source_id":"S1","text":"return x[0]","locator":"snapshot:line1"}]}
        def abstain(provider,prompt,**kwargs):
            result=self.result(provider,prompt,**kwargs);result.text='{"findings":[],"abstain":true}'
            return result
        with patch.object(model_runtime.ai_providers,"call",side_effect=abstain) as post, \
             patch.object(relay_billing,"read_meter",return_value={"fixture":"before"}), \
             patch.object(relay_billing,"settle",return_value=self.debit()):
            self.call(stage="auxiliary",role="engineering-code-review",source_contract=contract)
            replay=self.call(stage="auxiliary",role="engineering-code-review",source_contract=contract)
            self.assertTrue(replay.cache_hit);post.assert_called_once()
            self.call(stage="auxiliary",role="engineering-test-design",source_contract=contract)
            contract["sources"][0]["text"]="return x[-1]"
            self.call(stage="auxiliary",role="engineering-code-review",source_contract=contract)
            self.assertEqual(post.call_count,3)
        self.assertAlmostEqual(model_spend.read(self.project)["spent_cny"],0.003)

    def test_invalid_metadata_output_is_billed_once_and_never_cached(self):
        def invalid(provider, prompt, **kwargs):
            result = self.result(provider, prompt, **kwargs)
            result.text = self.extracted("Invented title")
            return result
        with (patch.object(model_runtime.ai_providers, "call", side_effect=invalid) as post,
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit())):
            with self.assertRaises(metadata_contract.MetadataContractError):
                self.call(stage="auxiliary", role="metadata-extraction", source_contract=self.contract())
        post.assert_called_once()
        self.assertEqual(model_spend.read(self.project)["spent_cny"], 0.001)
        self.assertFalse(list((self.project / ".cache" / "model-responses").glob("*.json")))
        self.assertEqual(model_runtime.ledger_entries(self.project)[-1]["validation_status"], "source_contract_failed_no_retry")

    def test_metadata_exact_cache_is_free_and_corrupt_cached_fields_still_fail_validation(self):
        with (patch.object(model_runtime.ai_providers, "call", side_effect=self.result) as post,
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}) as meter,
                patch.object(relay_billing, "settle", return_value=self.debit())):
            self.call(stage="auxiliary", role="metadata-extraction", source_contract=self.contract())
            cached = self.call(stage="auxiliary", role="metadata-extraction", source_contract=self.contract(), run_id="cached")
            self.assertTrue(cached.cache_hit)
            post.assert_called_once()
            meter.assert_called_once()
            path = next((self.project / ".cache" / "model-responses").glob("*.json"))
            document = json.loads(path.read_text(encoding="utf-8"))
            document["text"] = self.extracted("Invented title")
            document["response_text_sha256"] = hashlib.sha256(document["text"].encode()).hexdigest()
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(metadata_contract.MetadataContractError):
                self.call(stage="auxiliary", role="metadata-extraction", source_contract=self.contract(), run_id="corrupt-cache")
            post.assert_called_once()

    def test_zero_actual_wallet_settlement_requires_an_independent_request_increment(self):
        with (patch.object(model_runtime.ai_providers, "call", side_effect=self.result),
                patch.object(relay_billing, "read_meter", side_effect=[self.counter(), self.counter(11, 0.02)])):
            self.call(stage="auxiliary", role="engineering-diagnosis")
        state = model_spend.read(self.project)
        self.assertEqual(state["spent_cny"], 0)
        self.assertEqual(state["reservations"], {})
        self.assertTrue(model_runtime.ledger_entries(self.project)[0]["billing"]["independent_gateway_debit"]["debit_evidence"]["exactly_one_new_gateway_request"])
        with (patch.object(model_runtime.ai_providers, "call", side_effect=self.result) as post,
                patch.object(relay_billing, "read_meter", return_value=self.counter()),
                patch.object(relay_billing.time, "sleep")):
            self.call(stage="auxiliary", role="engineering-diagnosis", prompt="unverified zero", use_cache=False)
        post.assert_called_once()
        self.assertGreater(model_spend.read(self.project)["spent_cny"], 0)
        self.assertEqual(model_spend.read(self.project)["reservations"], {})
        self.assertEqual(model_runtime.ledger_entries(self.project)[-1]["cost_status"], "estimated_upper_bound")
