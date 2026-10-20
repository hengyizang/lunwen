"""Offline acceptance for production task coverage and non-downgrade boundaries."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import ai_providers, api_orchestrator, model_routing, task_router


class ProductionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_all_six_stages_have_exactly_five_separated_roles(self):
        policy, digest = model_routing.load_policy()
        self.assertEqual(len(policy["stage_routes"]), 6)
        self.assertEqual(len(digest), 64)
        for stage in policy["stage_routes"]:
            routes = model_routing.cycle_routes(stage)
            self.assertEqual(set(routes), set(model_routing.CYCLE_ROLES))
            self.assertEqual(routes["persistent-writer"]["family"], "openai")
            self.assertEqual(routes["persistent-remediator"]["family"], "openai")
            for role in model_routing.READ_ONLY_ROLES:
                self.assertEqual(routes[role]["family"], "anthropic")
                self.assertFalse(routes[role]["persistent_output"])
            self.assertEqual(routes["independent-critic-final"]["model_key"], "opus")
            self.assertTrue(routes["independent-critic-initial"]["fresh_required"])
            self.assertTrue(routes["independent-critic-final"]["fresh_required"])

    def test_core_scientific_stages_use_astra_and_opus(self):
        for stage in ("topic-intelligence", "paper-architecture", "experiment-design"):
            with self.subTest(stage=stage):
                routes = model_routing.cycle_routes(stage)
                self.assertEqual(routes["persistent-writer"]["model"], "gpt-6-astra")
                self.assertEqual(routes["persistent-remediator"]["model"], "gpt-6-astra")
                self.assertEqual(routes["semantic-planner"]["model"], "claude-opus-5-5")

    def test_normal_writing_uses_sol_but_core_story_escalates_existing_roles(self):
        self.assertEqual(model_routing.select("writing-and-review", "persistent-writer")["model_key"], "sol")
        routes = model_routing.cycle_routes("writing-and-review", "core-story")
        self.assertEqual(len(routes), 5)
        self.assertEqual(routes["persistent-writer"]["model_key"], "astra")
        self.assertEqual(routes["semantic-planner"]["model_key"], "opus")

    def test_luna_is_medium_source_extraction_only(self):
        route = model_routing.select("auxiliary", "metadata-extraction")
        self.assertEqual((route["model"], route["reasoning_effort"]), ("gpt-5.6-luna", "medium"))
        self.assertFalse(route["persistent_output"])
        self.assertIn("source IDs", route["quality_boundary"])
        for role in ("screening-assist", "format-conversion", "evidence-synthesis", "reader-translation", "reader-qa"):
            self.assertEqual(model_routing.select("auxiliary", role)["model_key"], "sol")

    def test_deepseek_and_argon_are_internal_auxiliary_routes(self):
        self.assertEqual(model_routing.select("auxiliary", "engineering-diagnosis")["family"], "deepseek")
        route = model_routing.select("auxiliary", "multimodal-inspection")
        self.assertEqual((route["family"], route["model"]), ("google", "gemini-4-argon"))
        self.assertFalse(route["persistent_output"])

    def test_unknown_stage_role_or_critical_task_fails_closed(self):
        for args in (("unknown-stage", "persistent-writer"), ("intake", "unknown-role"),
                     ("intake", "persistent-writer", "undocumented-cheap-task")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                model_routing.select(*args)

    def test_explicit_model_or_effort_cannot_mislabel_the_route(self):
        with self.assertRaisesRegex(ValueError, "model conflicts"):
            model_routing.resolve_call("experiment-design", "persistent-writer", "openai", model="gpt-5.6-luna")
        with self.assertRaisesRegex(ValueError, "effort conflicts"):
            model_routing.resolve_call("auxiliary", "metadata-extraction", "openai", reasoning_effort="high")

    def test_probe_accepts_only_exact_production_provider_model_pair(self):
        route = model_routing.select("health", "endpoint-health", requested_provider="cheapai-gpt-pro", requested_model="gpt-6-astra")
        self.assertEqual(route["model_key"], "astra")
        with self.assertRaisesRegex(ValueError, "outside the approved"):
            model_routing.select("health", "endpoint-health", requested_provider="cheapai-gpt-discount", requested_model="gpt-6-astra")
        with self.assertRaises(ValueError):
            model_routing.select("intake", "endpoint-health", requested_provider="cheapai-gpt-pro")

    def test_policy_cannot_promote_luna_to_scientific_writer_or_screening(self):
        policy, _ = model_routing.load_policy()
        for mutation in ("writer", "screening"):
            changed = json.loads(json.dumps(policy))
            if mutation == "writer":
                changed["stage_routes"]["intake"]["persistent-writer"] = "luna"
            else:
                changed["auxiliary_routes"]["screening-assist"]["model_key"] = "luna"
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "policy.json"
                source.write_text(json.dumps(changed), encoding="utf-8")
                with patch.dict(os.environ, {"DR_OS_ROUTING_CONFIG": str(source)}), self.assertRaises(ValueError):
                    model_routing.load_policy()

    def test_declared_family_or_named_model_key_cannot_hide_a_downgrade(self):
        policy, _ = model_routing.load_policy()
        invalid = []
        value = json.loads(json.dumps(policy)); value["models"]["astra"] = dict(value["models"]["luna"]); invalid.append(value)
        value = json.loads(json.dumps(policy)); value["models"]["astra"]["model"] = "gpt-6.1-sol"; invalid.append(value)
        value = json.loads(json.dumps(policy)); value["models"]["astra"]["provider"] = "codekey-kiro-enterprise"; invalid.append(value)
        value = json.loads(json.dumps(policy)); value["models"]["astra"]["provider"] = "openai"; invalid.append(value)
        value = json.loads(json.dumps(policy)); value["models"]["sonnet"]["family"] = "openai"; invalid.append(value)
        value = json.loads(json.dumps(policy)); value["models"]["astra"]["reasoning_effort"] = "medium"; invalid.append(value)
        value = json.loads(json.dumps(policy)); value["stage_routes"]["topic-intelligence"]["persistent-writer"] = "sol"; invalid.append(value)
        value = json.loads(json.dumps(policy)); value["stage_routes"]["experiment-design"]["semantic-planner"] = "sonnet"; invalid.append(value)
        value = json.loads(json.dumps(policy)); value["stage_routes"]["intake"]["independent-critic-final"] = "sonnet"; invalid.append(value)
        for index, value in enumerate(invalid):
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "policy.json"; source.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(index=index), patch.dict(os.environ, {"DR_OS_ROUTING_CONFIG": str(source)}), self.assertRaises(ValueError):
                    model_routing.load_policy()

    def test_auxiliary_role_cannot_be_downgraded_or_repurposed_through_custom_policy(self):
        policy, _ = model_routing.load_policy()
        assignments = {"scientific-judgment": "deepseek", "evidence-synthesis": "deepseek",
                       "independent-critique": "argon", "reader-translation": "luna",
                       "metadata-extraction": "sol", "multimodal-inspection": "astra"}
        for role, replacement in assignments.items():
            changed = json.loads(json.dumps(policy))
            changed["auxiliary_routes"][role]["model_key"] = replacement
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "policy.json"; source.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(role=role, replacement=replacement), patch.dict(os.environ, {"DR_OS_ROUTING_CONFIG": str(source)}), self.assertRaises(ValueError):
                    model_routing.load_policy()

    def test_critical_and_health_task_boundaries_are_fixed_even_in_custom_policy(self):
        policy, _ = model_routing.load_policy()
        mutations = [
            ("critical_tasks", policy["critical_tasks"] + ["metadata-extraction"]),
            ("critical_tasks", [item for item in policy["critical_tasks"] if item != "core-story"]),
            ("health_roles", policy["health_roles"] + ["persistent-writer"]),
            ("health_roles", ["endpoint-health", "endpoint-health", "model-signature"]),
            ("health_roles", "endpoint-health"),
            ("health_stages", policy["health_stages"] + ["writing-and-review"]),
            ("auxiliary_stages", policy["auxiliary_stages"] + ["health"]),
        ]
        for field, replacement in mutations:
            changed = json.loads(json.dumps(policy)); changed[field] = replacement
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "policy.json"; source.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(field=field, replacement=replacement), patch.dict(os.environ, {"DR_OS_ROUTING_CONFIG": str(source)}), self.assertRaises(ValueError):
                    model_routing.load_policy()

    def test_no_stage_or_auxiliary_role_can_be_added_or_silently_removed(self):
        policy, _ = model_routing.load_policy()
        invalid = []
        value = json.loads(json.dumps(policy)); value["stage_routes"].pop("intake"); invalid.append(value)
        value = json.loads(json.dumps(policy)); value["auxiliary_routes"].pop("reader-qa"); invalid.append(value)
        value = json.loads(json.dumps(policy)); value["auxiliary_routes"]["unreviewed-task"] = dict(value["auxiliary_routes"]["metadata-extraction"]); invalid.append(value)
        for index, changed in enumerate(invalid):
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "policy.json"; source.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(index=index), patch.dict(os.environ, {"DR_OS_ROUTING_CONFIG": str(source)}), self.assertRaises(ValueError):
                    model_routing.load_policy()

    def test_unknown_or_missing_profile_does_not_silently_activate_production(self):
        with patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "legacy"}, clear=True):
            self.assertFalse(model_routing.production_enabled())
            self.assertEqual(model_routing.resolve_call("any", "any", "openai"),
                             {"provider": "openai", "model": None, "reasoning_effort": None})
        with patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "typo"}, clear=True), self.assertRaises(ValueError):
            model_routing.production_enabled()


class ProductionAuxiliaryTests(unittest.TestCase):
    def test_missing_final_opus_quote_blocks_before_planner_spend(self):
        checked = []

        def preflight(provider, model=None):
            checked.append((provider, model))
            if model == "claude-opus-5-5":
                raise ValueError("final critic quote is missing")
            return {"provider": provider, "model": model}

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True), \
                patch("scripts.api_orchestrator.require_current_stage"), \
                patch("scripts.api_orchestrator.project_root", return_value=Path(directory)), \
                patch("scripts.cloud_research_steps.before_cycle", return_value={"control_only": False}), \
                patch("scripts.api_orchestrator.prepare_discovery_evidence", return_value=("", {})), \
                patch("scripts.api_orchestrator.model_runtime.preflight_route", side_effect=preflight), \
                patch("scripts.api_orchestrator.model_runtime.call") as paid_call:
            with self.assertRaisesRegex(ValueError, "final critic quote is missing"):
                api_orchestrator.run_cycle("fixture", "intake", "anthropic", "openai", "anthropic", "", "")
            paid_call.assert_not_called()
            self.assertIn(("codekey-kiro-enterprise", "claude-opus-5-5"), checked)

    def test_screening_never_uses_cheap_price_sort_or_luna(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True), \
                patch("scripts.task_router.model_runtime.cost_cny", return_value=0.3), \
                patch("scripts.task_router.model_runtime.budget_status", return_value={"project_remaining": 1, "paper_remaining": None}):
            info = task_router.plan(Path(directory), "screening-assist", "openai", "Keep all supplied source records")
            self.assertEqual(info["model"], "gpt-6.1-sol")
            self.assertEqual(info["reasoning_effort"], "high")
            self.assertEqual(info["candidate_count"], 1)
            self.assertFalse(info["automatic_acceptance"])

    def test_failed_production_route_blocks_without_automatic_paid_fallback(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True), \
                patch("scripts.task_router._health", return_value={("cheapai-gpt-discount", "gpt-5.6-luna"): "failed"}), \
                patch("scripts.task_router.model_runtime.call") as paid_call:
            with self.assertRaisesRegex(ValueError, "recently failed"):
                task_router.run(Path(directory), "metadata-extraction", "openai", "Source S1: sample size unknown",
                                source_contract={"sources": [{"source_id": "S1", "text": "sample size unknown", "locator": "p2"}], "fields": ["n"]})
            paid_call.assert_not_called()

    def test_auxiliary_run_passes_effort_and_marks_output_unaccepted(self):
        result = SimpleNamespace(text='{"records":[{"source_id":"S1","fields":{"n":{"value":null,"quote":"","locator":""}}}]}', reported_model="gpt-5.6-luna", model="gpt-5.6-luna", cache_hit=False)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True), \
                patch("scripts.task_router.model_runtime.cost_cny", return_value=0.01), \
                patch("scripts.task_router.model_runtime.budget_status", return_value={"project_remaining": 1, "paper_remaining": None}), \
                patch("scripts.task_router.model_runtime.call", return_value=result) as call:
            contract = {"sources": [{"source_id": "S1", "text": "sample size unknown", "locator": "p2"}], "fields": ["n"]}
            response = task_router.run(Path(directory), "metadata-extraction", "openai", "Source S1: sample size unknown", source_contract=contract)
            request = call.call_args.kwargs
            self.assertEqual(request["provider"], "cheapai-gpt-discount")
            self.assertEqual(request["reasoning_effort"], "medium")
            self.assertEqual(request["source_contract"], contract)
            self.assertIn("Task boundary:", request["prompt"])
            receipt = json.loads((Path(directory) / response["result"]).read_text(encoding="utf-8"))
            self.assertFalse(receipt["automatic_acceptance"])
            self.assertTrue(receipt["not_manuscript_or_evidence"])

    def test_multimodal_requires_attachments_before_a_paid_request(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.task_router.plan", return_value={}), \
                patch("scripts.task_router.model_runtime.call") as paid_call:
            with self.assertRaisesRegex(ValueError, "requires explicit source attachments"):
                task_router.run(Path(directory), "multimodal-inspection", "codekey-gemini", "Inspect supplied figure")
            paid_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
