"""Dynamic selection reaches the bounded runtime; no real model or HTTP calls."""
from __future__ import annotations

import json
import math
import unittest
from unittest.mock import patch

from scripts import ai_providers, dynamic_routing, metadata_contract, model_runtime, model_spend, relay_billing
from tests import test_production_runtime as fixtures


class DynamicRuntimeTests(unittest.TestCase):
    # Reuse only fixture setup/helpers. Inheriting the source TestCase would
    # collect its entire test suite again under this module.
    setUp = fixtures.ProductionRuntimeTests.setUp
    call = fixtures.ProductionRuntimeTests.call
    result = fixtures.ProductionRuntimeTests.result
    debit = fixtures.ProductionRuntimeTests.debit
    contract = fixtures.ProductionRuntimeTests.contract
    extracted = fixtures.ProductionRuntimeTests.extracted

    def profile(self, risk="routine"):
        return {"task_class": "bounded-code-implementation", "science_risk": risk,
                "priority": "cost", "min_output_tokens": 32, "deadline_seconds": 120}

    def selected(self, project, baseline, **kwargs):
        route = {**baseline, "provider": "codekey-codex-pro", "model": "gpt-6.1-sol",
                 "family": "openai", "reasoning_effort": "low", "max_output_tokens": 64,
                 "timeout": 73, "route_id": "fixture-selected-route", "policy_sha256": "d" * 64}
        decision = {"mode": "production", "selected_candidate_id": "fixture-accepted-codex-sol-low",
                    "task_profile": kwargs.get("task_profile"), "policy_sha256": "c" * 64,
                    "selected_policy_sha256": route["policy_sha256"]}
        return {"route": route, "decision": decision}

    def unchanged(self, project, baseline, **kwargs):
        route = {**baseline, "max_output_tokens": kwargs["max_output_tokens"], "timeout": kwargs["timeout"]}
        return {"route": route, "decision": {"mode": "production", "selected_candidate_id": "fixture-same-route",
                 "task_profile": kwargs.get("task_profile"), "policy_sha256": "c" * 64}}

    def decisions(self):
        target = self.project / "state/model-route-decisions.jsonl"
        return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_selected_channel_effort_limits_and_audit_reach_the_single_paid_call(self):
        profile = self.profile()
        with (patch.object(dynamic_routing, "choose", side_effect=self.selected) as choose,
                patch.object(ai_providers, "call", side_effect=self.result) as post,
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}) as meter,
                patch.object(relay_billing, "settle", return_value=self.debit(0.0004)) as settle):
            first = self.call(task_profile=profile, timeout=100)
            replay = self.call(task_profile=profile, timeout=100, run_id="exact-selected-cache-replay")
        self.assertFalse(first.cache_hit)
        self.assertTrue(replay.cache_hit)
        self.assertEqual(choose.call_count, 2)
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "codekey-codex-pro")
        self.assertEqual(post.call_args.kwargs["model"], "gpt-6.1-sol")
        self.assertEqual(post.call_args.kwargs["reasoning_effort"], "low")
        self.assertEqual(post.call_args.kwargs["max_output_tokens"], 64)
        self.assertEqual(post.call_args.kwargs["timeout"], 73)
        meter.assert_called_once_with("codekey-codex-pro")
        settle.assert_called_once_with("codekey-codex-pro", "gpt-6.1-sol", {"fixture": "before"})
        state = model_spend.read(self.project)
        self.assertEqual(state["spent_cny"], 0.0004)
        self.assertEqual(state["reservations"], {})
        rows = model_runtime.ledger_entries(self.project)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row["cost_cny"] for row in rows), 0.0004)
        for row in rows:
            self.assertEqual(row["provider"], "codekey-codex-pro")
            self.assertEqual(row["task_profile"], profile)
            self.assertEqual(row["dynamic_candidate_id"], "fixture-accepted-codex-sol-low")
            self.assertEqual(row["requested_reasoning_effort"], "low")
            self.assertEqual(row["routing_policy_sha256"], "d" * 64)
        self.assertTrue(math.isfinite(rows[0]["duration_seconds"]))
        self.assertGreaterEqual(rows[0]["duration_seconds"], 0)
        decisions = self.decisions()
        self.assertEqual(len(decisions), 2)
        self.assertEqual(decisions[0]["dynamic_decision"]["policy_sha256"], "c" * 64)
        self.assertEqual(decisions[0]["timeout_seconds"], 73)
        self.assertTrue(decisions[0]["not_scientific_evidence"])

    def test_selected_transport_failure_keeps_unknown_debit_and_blocks_second_post(self):
        with (patch.object(dynamic_routing, "choose", side_effect=self.selected),
                patch.object(ai_providers, "call", side_effect=ai_providers.ProviderError("API HTTP 502")) as post,
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}) as meter,
                patch.object(relay_billing, "settle") as settle):
            with self.assertRaises(ai_providers.ProviderError):
                self.call(task_profile=self.profile())
            with self.assertRaisesRegex(model_runtime.ModelBudgetError, "reconciliation"):
                self.call(task_profile=self.profile(), run_id="must-not-fallback", prompt="different uncached work")
        post.assert_called_once()
        meter.assert_called_once_with("codekey-codex-pro")
        settle.assert_not_called()
        state = model_spend.read(self.project)
        self.assertEqual(state["spent_cny"], 0)
        self.assertEqual(len(state["reservations"]), 1)
        self.assertGreater(model_spend.reserved(state), 0)
        rows = model_runtime.ledger_entries(self.project)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provider"], "codekey-codex-pro")
        self.assertEqual(rows[0]["cost_status"], "unknown_reconcile_required")
        self.assertTrue(rows[0]["zero_cost_not_confirmed"])
        self.assertEqual(rows[0]["dynamic_candidate_id"], "fixture-accepted-codex-sol-low")
        self.assertGreaterEqual(rows[0]["duration_seconds"], 0)

    def test_complete_bound_sources_are_present_before_selection_and_match_transport(self):
        contract = self.contract()
        contract["sources"].append({"source_id": "S2", "text": "Complete second source: measured value β = 17.",
                                    "locator": "fixture:p2:lines1-9"})
        events = []
        observed = {}
        def choose(project, baseline, **kwargs):
            events.append("selection")
            observed["prompt"] = kwargs["prompt"]
            for source in contract["sources"]:
                self.assertIn(source["text"], kwargs["prompt"])
                self.assertIn(source["locator"], kwargs["prompt"])
            self.assertIn("SOURCE_CONTRACT_JSON:", kwargs["prompt"])
            return self.unchanged(project, baseline, **kwargs)
        def meter(provider):
            self.assertEqual(events, ["selection"])
            events.append("meter")
            return {"fixture": "before"}
        def post(provider, prompt, **kwargs):
            self.assertEqual(events, ["selection", "meter"])
            self.assertEqual(prompt, observed["prompt"])
            events.append("generation")
            value = self.result(provider, prompt, **kwargs)
            value.text = json.dumps({"records": [{"source_id": source["source_id"],
                 "fields": {"title": {"value": None, "quote": "", "locator": ""}}}
                 for source in contract["sources"]]})
            return value
        with (patch.object(dynamic_routing, "choose", side_effect=choose) as selector,
                patch.object(ai_providers, "call", side_effect=post) as transport,
                patch.object(relay_billing, "read_meter", side_effect=meter),
                patch.object(relay_billing, "settle", return_value=self.debit(0.0001))):
            self.call(stage="auxiliary", role="metadata-extraction", source_contract=contract)
        selector.assert_called_once()
        transport.assert_called_once()
        self.assertEqual(events, ["selection", "meter", "generation"])

    def test_invalid_source_contract_cannot_reach_selection_meter_or_reservation(self):
        with (patch.object(dynamic_routing, "choose") as choose,
                patch.object(ai_providers, "call") as post,
                patch.object(relay_billing, "read_meter") as meter,
                patch.object(model_spend, "reserve", wraps=model_spend.reserve) as reserve):
            with self.assertRaises(metadata_contract.MetadataContractError):
                self.call(stage="auxiliary", role="metadata-extraction",
                          source_contract={"sources": [], "fields": ["title"]})
        choose.assert_not_called()
        post.assert_not_called()
        meter.assert_not_called()
        reserve.assert_not_called()
        self.assertEqual(model_spend.read(self.project)["reservations"], {})

    def test_dynamic_decisions_never_turn_fresh_critics_into_cache_replays(self):
        profile = {"task_class": "scientific-final-audit", "science_risk": "critical", "priority": "quality"}
        with (patch.object(dynamic_routing, "choose", side_effect=self.unchanged) as choose,
                patch.object(ai_providers, "call", side_effect=self.result) as post,
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit(0.0005))):
            for index in (1, 2):
                result = self.call(role="independent-critic-final", provider="anthropic",
                                   task_profile=profile, run_id=f"fresh-critic-{index}")
                self.assertFalse(result.cache_hit)
        self.assertEqual(choose.call_count, 2)
        self.assertEqual(post.call_count, 2)
        self.assertFalse(list((self.project / ".cache/model-responses").glob("*.json")))
        rows = model_runtime.ledger_entries(self.project)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["cache_policy"] == "fresh_required_or_explicit" for row in rows))
        self.assertEqual(model_spend.read(self.project)["spent_cny"], 0.001)

    def test_explicit_off_preserves_static_stage_route_without_candidate_loading(self):
        with (patch.dict("os.environ", {"DR_OS_DYNAMIC_ROUTING": "off"}),
                patch.object(dynamic_routing, "load_policy") as registry,
                patch.object(ai_providers, "call", side_effect=self.result) as post,
                patch.object(relay_billing, "read_meter", return_value={"fixture": "before"}),
                patch.object(relay_billing, "settle", return_value=self.debit(0.0005))):
            self.call(stage="writing-and-review")
        registry.assert_not_called()
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "cheapai-gpt-pro")
        self.assertEqual(post.call_args.kwargs["model"], "gpt-6.1-sol")
        self.assertEqual(post.call_args.kwargs["reasoning_effort"], "high")
        row = model_runtime.ledger_entries(self.project)[0]
        self.assertEqual(row["dynamic_candidate_id"], "baseline")
        self.assertEqual(row["dynamic_decision"]["mode"], "off")
        self.assertEqual(model_spend.read(self.project)["spent_cny"], 0.0005)


if __name__ == "__main__":
    unittest.main()
