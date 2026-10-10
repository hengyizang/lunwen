"""Synthetic cloud-CI checks; no model/tool transport or paid calls."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from scripts import billing_quotes, model_runtime, model_spend
from scripts.ai_providers import ModelResult


PROVIDER = "uuapi-openai"
ENDPOINT = "https://gateway.example/v1/responses"
MODEL = "gpt-test"
CONFIG = {"model": MODEL, "protocol": "openai_responses", "endpoint": ENDPOINT}
IDENTITY = {"plan": "subscription", "group": "research", "mode": "standard-billing"}


def quote(**changes):
    value = {"provider": PROVIDER, "endpoint": ENDPOINT, "model": MODEL, **IDENTITY,
             "currency": "CNY", "price_version": "test-receipt-2026-10-09",
             "input_per_million": 2, "output_per_million": 10,
             "cache_read_per_million": 0.2, "cache_write_per_million": 3}
    value.update(changes)
    return value


def bracket_quote(**changes):
    value = quote()
    for field in billing_quotes.RATE_FIELDS:
        del value[field]
    value.update({"context_basis": "full_request_input_tokens", "context_brackets": [
        {"min_input_tokens": 0, "max_input_tokens": 100, "input_per_million": 2,
         "output_per_million": 10, "cache_read_per_million": 0.2, "cache_write_per_million": 3},
        {"min_input_tokens": 101, "max_input_tokens": None, "input_per_million": 4,
         "output_per_million": 20, "cache_read_per_million": 0.4, "cache_write_per_million": 6}]})
    value.update(changes)
    return value


def document(*quotes):
    return {"schema_version": "2.0", "quotes": list(quotes)}


def response(usage=None):
    return ModelResult(PROVIDER, MODEL, "answer", usage if usage is not None else {"input_tokens": 100, "output_tokens": 20},
                       "request-1", MODEL, "openai_responses", ENDPOINT, "test", completion_status="completed")


def tool_receipt(*items, **changes):
    value = {"schema_version": "1.0", "complete": True, "source": "gateway_billing",
             "receipt_id": "bill-1", "request_id": "request-1", "items": list(items)}
    value.update(changes)
    return value


def authorized(project):
    model_spend.write(project, model_spend.initial())
    model_spend.grant(project, new_ceiling_cny=300, actor="Synthetic CI owner", run_id="synthetic-approval")


@contextmanager
def runtime(prices, result=None, extra=None):
    environment = {"DR_OS_REQUIRE_MODEL_AUTH": "1", "DR_OS_MODEL_PRICING_JSON": json.dumps(prices)}
    environment.update(extra or {})
    with patch.dict(os.environ, environment, clear=True), \
         patch("scripts.model_runtime.ai_providers.configuration", return_value=CONFIG), \
         patch("scripts.model_runtime.ai_providers.call", return_value=result or response()) as transport, \
         patch("scripts.cloud_checkpoint.sync_billing"):
        yield transport


def call(project, **changes):
    values = {"run_id": "synthetic", "stage": "intake", "role": "writer", "provider": PROVIDER,
              "prompt": "identical prompt", "max_output_tokens": 100, "billing_identity": IDENTITY}
    values.update(changes)
    return model_runtime.call(project, **values)


class ConditionalQuoteTests(unittest.TestCase):
    def test_group_identity_changes_cache_and_ledger_without_changing_inference(self):
        other_identity = {**IDENTITY, "group": "premium"}
        prices = document(quote(), quote(group="premium", input_per_million=4))
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            authorized(project)
            with runtime(prices) as transport:
                first = call(project)
                first_key = first.cache_key
                second = call(project, billing_identity=other_identity)
                self.assertNotEqual(first_key, second.cache_key)
                third = call(project, billing_identity=other_identity)
                self.assertTrue(third.cache_hit)
                self.assertEqual(transport.call_count, 2)
                for invocation in transport.call_args_list:
                    self.assertEqual(invocation.kwargs["model"], None)
                    self.assertNotIn("billing_identity", invocation.kwargs)
                    self.assertNotIn("mode", invocation.kwargs)
                    self.assertNotIn("reasoning_effort", invocation.kwargs)
            entries = model_runtime.ledger_entries(project)
            self.assertEqual(entries[0]["billing_identity"], IDENTITY)
            self.assertEqual(entries[1]["billing_identity"], other_identity)
            self.assertEqual(entries[2]["billing_quote_sha256"], entries[1]["billing_quote_sha256"])
            with runtime(prices):
                self.assertEqual(len(model_runtime.usage_summary(project)["by_provider_model_role"]), 2)

    def test_full_context_threshold_is_checked_before_cache_discount(self):
        selected = billing_quotes.select(document(bracket_quote()), PROVIDER, ENDPOINT, MODEL, IDENTITY)
        value, unknown, detail = billing_quotes.bill(selected, {"input_tokens_details": {"cached_tokens": 100},
                                                              "output_tokens_details": {"reasoning_tokens": 10}},
                                                    101, 20, anthropic=False)
        self.assertFalse(unknown)
        self.assertEqual(detail["context_tier"]["min_input_tokens"], 101)
        self.assertEqual(detail["context_tier"]["input_tokens"], 101)
        self.assertEqual(detail["ordinary_input_tokens"], 1)
        self.assertAlmostEqual(value, (1 * 4 + 100 * 0.4 + 20 * 20) / 1_000_000)

    def test_uncached_context_basis_must_be_explicit_and_includes_new_cache_writes(self):
        selected = billing_quotes.select(document(bracket_quote(context_basis="uncached_input_tokens")), PROVIDER, ENDPOINT, MODEL, IDENTITY)
        _, _, detail = billing_quotes.bill(selected, {"cache_read_input_tokens": 500, "cache_creation_input_tokens": 2},
                                           100, 10, anthropic=True)
        self.assertEqual(detail["full_request_input_tokens"], 602)
        self.assertEqual(detail["uncached_input_tokens"], 102)
        self.assertEqual(detail["context_tier"]["min_input_tokens"], 101)

    def test_no_fallback_for_unknown_plan_group_or_mode(self):
        for field in ("plan", "group", "mode"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                authorized(project)
                with runtime(document(quote())) as transport, self.assertRaises(model_runtime.ModelBudgetError):
                    call(project, billing_identity={**IDENTITY, field: "unknown"})
                transport.assert_not_called()
                self.assertFalse(model_spend.read(project)["reservations"])

    def test_schema_tier_and_cache_rate_ambiguities_fail_before_transport(self):
        cases = []
        cases.append({"schema_version": "9.0", "quotes": [quote()]})
        cases.append(document(quote(), quote()))
        broken = bracket_quote()
        broken["context_brackets"][1]["min_input_tokens"] = 102
        cases.append(document(broken))
        broken = bracket_quote()
        broken["context_brackets"][-1]["max_input_tokens"] = 200
        cases.append(document(broken))
        broken = bracket_quote()
        broken["context_brackets"][0]["cache_read_per_million"] = "0.2"
        cases.append(document(broken))
        broken = quote()
        del broken["cache_write_per_million"]
        cases.append(document(broken))
        broken = quote()
        del broken["group"]
        cases.append(document(broken))
        cases.append(document(bracket_quote(context_basis="discounted_guess")))
        for index, prices in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                authorized(project)
                with runtime(prices) as transport, self.assertRaises(model_runtime.ModelBudgetError):
                    call(project)
                transport.assert_not_called()

    def test_scoped_legacy_price_prevents_a_cheap_model_only_route_fallback(self):
        prices = {MODEL: {"input_per_million": 1, "output_per_million": 1},
                  f"{PROVIDER}|https://other.example/v1/responses|{MODEL}": {"input_per_million": 20, "output_per_million": 40}}
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            authorized(project)
            with runtime(prices) as transport, self.assertRaises(model_runtime.ModelBudgetError):
                call(project, billing_identity={})
            transport.assert_not_called()

    def test_legacy_rates_still_settle_without_conditional_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            authorized(project)
            with runtime({MODEL: {"input_per_million": 2, "output_per_million": 10}}) as transport:
                call(project, billing_identity={})
            transport.assert_called_once()
            self.assertEqual(model_spend.read(project)["spent_cny"], 0.0004)

    def test_provider_environment_identity_and_price_version_are_cache_bound(self):
        prices = document(quote())
        extra = {"DR_OS_MODEL_BILLING_IDENTITY_JSON": json.dumps({PROVIDER: IDENTITY})}
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            authorized(project)
            with runtime(prices, extra=extra):
                first = call(project, billing_identity=None)
                first_key = first.cache_key
            changed = document(quote(price_version="new-receipt"))
            with runtime(changed, extra=extra) as transport:
                second = call(project, billing_identity=None)
                self.assertNotEqual(first_key, second.cache_key)
                transport.assert_called_once()


class ToolBillingTests(unittest.TestCase):
    FEES = {"web_search": {"billing": "per_unit", "unit": "query", "price_cny": 0.2},
            "retrieval": {"billing": "flat_per_call", "unit": "lookup", "price_cny": 0.3}}

    def test_tool_fees_need_explicit_bounded_authorization_before_transport(self):
        for limits in (None, {}, {"web_search": 1}, {"web_search": True, "retrieval": 1},
                       {"web_search": 1, "retrieval": 1, "unknown": 1}):
            with self.subTest(limits=limits), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                authorized(project)
                with runtime(document(quote(tool_fees=self.FEES))) as transport, self.assertRaises(model_runtime.ModelBudgetError):
                    call(project, declared_tool_limits=limits)
                transport.assert_not_called()

    def test_flat_and_per_unit_tools_settle_exact_typed_receipts(self):
        usage = {"input_tokens": 100, "output_tokens": 20,
                 "tool_usage": tool_receipt({"tool": "web_search", "unit": "query", "units": 2},
                                            {"tool": "retrieval", "unit": "lookup", "units": 4})}
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            authorized(project)
            with runtime(document(quote(tool_fees=self.FEES)), response(usage)) as transport:
                call(project, declared_tool_limits={"web_search": 3, "retrieval": 4})
            transport.assert_called_once()
            state = model_spend.read(project)
            self.assertAlmostEqual(state["spent_cny"], 0.7004)
            self.assertFalse(state["reservations"])
            entry = model_runtime.ledger_entries(project)[0]
            self.assertEqual(entry["billing"]["tool_cost_cny"], 0.7)
            self.assertEqual(len(entry["billing"]["tool_receipts"]), 2)

    def test_explicit_zero_tool_receipt_is_supported_and_never_executes_tools(self):
        usage = {"input_tokens": 100, "output_tokens": 20, "tool_usage": tool_receipt()}
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            authorized(project)
            extra = {"DR_OS_MODEL_TOOL_LIMITS_JSON": json.dumps({PROVIDER: {"web_search": 0, "retrieval": 0}})}
            with runtime(document(quote(tool_fees=self.FEES)), response(usage), extra) as transport:
                call(project)
            self.assertNotIn("tools", transport.call_args.kwargs)
            self.assertEqual(model_spend.read(project)["spent_cny"], 0.0004)

    def test_unpriced_malformed_or_unbound_tool_receipts_remain_reserved_and_block_retry(self):
        receipts = [None, [], tool_receipt(complete=False), tool_receipt(request_id="another-response"),
                    tool_receipt({"tool": "unknown", "unit": "query", "units": 1}),
                    tool_receipt({"tool": "web_search", "unit": "query", "units": 4}),
                    tool_receipt({"tool": "web_search", "unit": "other", "units": 1}),
                    tool_receipt({"tool": "web_search", "unit": "query", "units": True})]
        for index, receipt in enumerate(receipts):
            usage = {"input_tokens": 100, "output_tokens": 20}
            if receipt is not None:
                usage["tool_usage"] = receipt
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                authorized(project)
                with runtime(document(quote(tool_fees=self.FEES)), response(usage)) as transport:
                    with self.assertRaises(model_runtime.ModelBudgetError):
                        call(project, declared_tool_limits={"web_search": 3, "retrieval": 1})
                    with self.assertRaises(model_runtime.ModelBudgetError):
                        call(project, declared_tool_limits={"web_search": 3, "retrieval": 1})
                    self.assertEqual(transport.call_count, 1)
                state = model_spend.read(project)
                self.assertGreater(model_spend.reserved(state), 0)
                self.assertEqual(state["spent_cny"], 0)
                entry = model_runtime.ledger_entries(project)[0]
                self.assertEqual(entry["cost_status"], "unknown_reconcile_required")
                self.assertTrue(entry["reservation_id"])
                self.assertFalse(list((project / ".cache" / "model-responses").glob("*.json")))

    def test_worst_bracket_cache_premium_and_tools_reserve_before_transport(self):
        prices = bracket_quote(tool_fees=self.FEES)
        prices["context_brackets"][-1]["cache_write_per_million"] = 100
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            authorized(project)
            result = response({"input_tokens": 100, "output_tokens": 20, "tool_usage": tool_receipt()})
            reservations = []
            with runtime(document(prices), result) as transport:
                def observe(*args, **kwargs):
                    reservations.append(model_spend.reserved(model_spend.read(project)))
                    return result
                transport.side_effect = observe
                call(project, prompt="short", declared_tool_limits={"web_search": 3, "retrieval": 4})
            self.assertAlmostEqual(reservations[0], (1006 * 100 + 100 * 20) / 1_000_000 + 0.9)

    def test_high_tier_or_tool_maximum_cannot_cross_approved_budget(self):
        expensive = bracket_quote()
        expensive["context_brackets"][-1]["cache_write_per_million"] = 1_000_000
        fee_quote = quote(tool_fees={"web_search": {"billing": "per_unit", "unit": "query", "price_cny": 100}})
        for prices, limits in ((expensive, None), (fee_quote, {"web_search": 4})):
            with self.subTest(prices=prices), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                authorized(project)
                with runtime(document(prices)) as transport, self.assertRaises(model_runtime.ModelBudgetError):
                    call(project, declared_tool_limits=limits)
                transport.assert_not_called()
                self.assertFalse(model_spend.read(project)["reservations"])

    def test_malformed_token_usage_preserves_reconciliation_receipt(self):
        for usage in ({"input_tokens": "100", "output_tokens": 20},
                      {"input_tokens": 100, "prompt_tokens": 120, "output_tokens": 20},
                      {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": []},
                      {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 101}},
                      {"input_tokens": 100, "output_tokens": 20, "output_tokens_details": {"reasoning_tokens": 21}},
                      {"input_tokens": 100}):
            with self.subTest(usage=usage), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                authorized(project)
                with runtime(document(quote()), response(usage)) as transport:
                    with self.assertRaises(model_runtime.ModelBudgetError):
                        call(project)
                    with self.assertRaises(model_runtime.ModelBudgetError):
                        call(project)
                    self.assertEqual(transport.call_count, 1)
                self.assertGreater(model_runtime.budget_status(project)["reserved"], 0)
                self.assertEqual(model_runtime.ledger_entries(project)[0]["usage_receipt"], usage)


if __name__ == "__main__":
    unittest.main()
