"""Offline acceptance for production task coverage and non-downgrade boundaries."""
from __future__ import annotations

import json
import copy
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from scripts import ai_providers, api_orchestrator, model_routing, task_router


class ProductionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_local_model_override_restores_defaults_and_keeps_transport_ids_scoped(self):
        baseline, baseline_hash = model_routing.load_policy()
        approved = dict(model_routing.APPROVED_MODELS)
        providers = copy.deepcopy(ai_providers.PRODUCTION_PROVIDERS)
        model = "fixture-local-astra"
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "models.json"
            local.write_text(json.dumps({"models": {"astra": {
                "provider": "codekey-codex-pro", "model": model, "family": "openai"}}}))
            with patch.object(model_routing, "LOCAL_MODEL_OVERRIDES", local):
                route = model_routing.select("topic-intelligence", "persistent-writer")
                self.assertEqual((route["provider"], route["model"]), ("codekey-codex-pro", model))
                self.assertEqual(ai_providers.production_endpoint(route["provider"], model),
                                 "https://codekey.ai/v1/responses")
                self.assertIn(model, ai_providers.configuration(route["provider"])["allowed_models"])
                self.assertIn("high", ai_providers.production_supported_efforts(route["provider"], model))
                self.assertEqual(model_routing.APPROVED_MODELS, approved)
                self.assertEqual(ai_providers.PRODUCTION_PROVIDERS, providers)
                local.unlink()
                self.assertEqual(model_routing.load_policy(), (baseline, baseline_hash))
                self.assertEqual(ai_providers.production_endpoint("codekey-codex-pro", model), "https://codekey.ai/v1/responses")

    def test_local_model_override_hash_tracks_effective_identity(self):
        _, baseline_hash = model_routing.load_policy()
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "models.json"
            with patch.object(model_routing, "LOCAL_MODEL_OVERRIDES", local):
                value = {"models": {"astra": {"model": "fixture-local-a"}}}
                local.write_text(json.dumps(value))
                _, first = model_routing.load_policy()
                self.assertNotEqual(first, baseline_hash)
                local.write_text(json.dumps(value, indent=4))
                self.assertEqual(model_routing.load_policy()[1], first)
                value["models"]["astra"]["model"] = "fixture-local-b"
                local.write_text(json.dumps(value))
                self.assertNotEqual(model_routing.load_policy()[1], first)
                self.assertNotIn("fixture-local-a", ai_providers.production_models("cheapai-gpt-pro"))

    def test_invalid_local_model_override_does_not_poison_defaults(self):
        baseline = model_routing.load_policy()
        providers = copy.deepcopy(ai_providers.PRODUCTION_PROVIDERS)
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "models.json"
            local.write_text(json.dumps({"models": {"astra": {
                "model": "fixture-invalid-family", "family": "anthropic"}}}))
            with patch.object(model_routing, "LOCAL_MODEL_OVERRIDES", local):
                with self.assertRaisesRegex(ValueError, "family"):
                    model_routing.load_policy()
                self.assertEqual(ai_providers.PRODUCTION_PROVIDERS, providers)
                local.unlink()
                self.assertEqual(model_routing.load_policy(), baseline)

    def test_stage_routes_only_recommend_writer_and_requested_roles_are_optional(self):
        policy, digest = model_routing.load_policy()
        self.assertEqual(len(digest), 64)
        for stage, configured in policy["stage_routes"].items():
            self.assertEqual(set(configured), {"persistent-writer"})
            routes = model_routing.cycle_routes(stage, roles=["persistent-writer"])
            self.assertEqual(set(routes), {"persistent-writer"})
        self.assertTrue(model_routing.select("any-context", "independent-critic-final")["fresh_required"])

    def test_stage_defaults_do_not_restrict_explicit_writer_family(self):
        for stage in model_routing.APPROVED_STAGES:
            route = model_routing.select(stage, "persistent-writer", requested_provider="codekey-kiro-enterprise")
            self.assertEqual(route["family"], "anthropic")
            self.assertTrue(route["persistent_output"])

    def test_task_label_does_not_override_selected_model_or_add_roles(self):
        ordinary = model_routing.cycle_routes("writing-and-review", roles=["persistent-writer"])
        critical = model_routing.cycle_routes("writing-and-review", "core-story", roles=["persistent-writer"])
        self.assertEqual(critical["persistent-writer"]["model"], ordinary["persistent-writer"]["model"])
        self.assertEqual(set(critical), {"persistent-writer"})

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

    def test_calibration_scope_is_cloud_only_fresh_and_cannot_change_production_routes(self):
        original = model_routing.select("auxiliary", "independent-critique")
        with self.assertRaisesRegex(ValueError, "cloud executor"):
            with model_routing.public_review_calibration_route("editorial", "a" * 64):
                pass
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            for seat, family in (("domain", "anthropic"), ("editorial", "google"), ("statistics", "deepseek")):
                with self.subTest(seat=seat), model_routing.public_review_calibration_route(seat, "a" * 64):
                    route = model_routing.select("auxiliary", "independent-critique")
                    self.assertEqual((route["family"], route["reasoning_effort"]), (family, "high"))
                    self.assertTrue(route["fresh_required"])
                    self.assertFalse(route["persistent_output"])
                    self.assertEqual(route["task_kind"], "scientific-judgment")
                    self.assertEqual(model_routing.select("topic-intelligence", "persistent-writer")["provider"], "cheapai-gpt-pro")
                    with self.assertRaisesRegex(ValueError, "one exact"):
                        with model_routing.public_review_calibration_route(seat, "b" * 64):
                            pass
        self.assertEqual(model_routing.select("auxiliary", "independent-critique"), original)

    def test_g1_transport_scope_changes_only_same_astra_and_restores_threads_and_exceptions(self):
        original = model_routing.cycle_routes("topic-intelligence", "scientific-judgment")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(directory)
            state = project / "state/run.json"; state.parent.mkdir()
            state.write_text(json.dumps({"stage": "topic-intelligence", "gate": "G1", "status": "awaiting_work", "approved_gates": ["G0"]}))
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                with model_routing.g1_transport_validation_route(project, "a" * 64):
                    selected = model_routing.cycle_routes("topic-intelligence", "scientific-judgment")
                    for role, route in selected.items():
                        self.assertEqual(route["model"], "gpt-6-astra" if role in model_routing.WRITER_ROLES else "claude-opus-5-5")
                        self.assertEqual(route["reasoning_effort"], "high")
                        self.assertEqual(route["validation_scope"]["production_route"]["stage"], "topic-intelligence")
                        self.assertTrue(route["temporary_validation_only"])
                    self.assertEqual(selected["persistent-writer"]["provider"], "codekey-codex-pro")
                    self.assertEqual(selected["independent-critic-initial"]["provider"], original["independent-critic-initial"]["provider"])
                    self.assertEqual(model_routing.select("writing-and-review", "persistent-writer")["provider"], "cheapai-gpt-pro")
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        thread = pool.submit(model_routing.select, "topic-intelligence", "persistent-writer").result()
                    self.assertEqual(thread["provider"], "cheapai-gpt-pro")
                    with self.assertRaisesRegex(ValueError, "actual project"):
                        model_routing.resolve_call("topic-intelligence", "persistent-writer", "openai", project_root=project / "other")
                    self.assertEqual(model_routing.resolve_call("topic-intelligence", "persistent-writer", "openai", project_root=project)["provider"], "codekey-codex-pro")
                    for extra in (("topic-intelligence", "persistent-writer"), ("auxiliary", "reader-qa")):
                        with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "additional paid helpers or retries"):
                            model_routing.resolve_call(*extra, "openai", project_root=project)
                    raise RuntimeError("synthetic failure")
            self.assertEqual(model_routing.cycle_routes("topic-intelligence", "scientific-judgment"), original)
            for changes in ({"status": "awaiting_review"}, {"approved_gates": ["G0", "G1"]}, {"stage": "paper-architecture"}):
                invalid = {"stage": "topic-intelligence", "gate": "G1", "status": "awaiting_work", "approved_gates": ["G0"], **changes}
                state.write_text(json.dumps(invalid))
                with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "actual awaiting-work G1"):
                    with model_routing.g1_transport_validation_route(project, "a" * 64):
                        pass

    def test_new_context_and_task_roles_use_configured_defaults(self):
        for args in (("new-topic", "persistent-writer"), ("intake", "new-role"),
                     ("intake", "persistent-writer", "new-task")):
            self.assertIn(model_routing.select(*args)["provider"], ai_providers.PROVIDERS)

    def test_explicit_g1_roster_keeps_critical_identities_scoped_and_source_bound(self):
        providers = ("codekey-codex-pro", "codekey-codex-pro", "codekey-gemini")
        api_orchestrator.validate_roles(*providers)
        original = model_routing.cycle_routes("topic-intelligence", "scientific-judgment")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(directory)
            state = project / "state/run.json"; state.parent.mkdir()
            state.write_text(json.dumps({"stage": "topic-intelligence", "gate": "G1", "status": "awaiting_work", "approved_gates": ["G0"]}))
            source = project / "manifest.json"; source.write_text("frozen sample scope")
            def unchanged():
                if source.read_text() != "frozen sample scope":
                    raise ValueError("source changed before provider")
            with self.assertRaisesRegex(RuntimeError, "sample failure"):
                with model_routing.g1_transport_validation_route(project, "b" * 64, check_inputs=unchanged,
                        max_output_tokens=12000, validation_roster="astra-argon", response_streaming=True):
                    api_orchestrator.validate_roles(*providers)
                    selected = model_routing.cycle_routes("topic-intelligence", "scientific-judgment")
                    for role, route in selected.items():
                        critic = role.startswith("independent-critic")
                        self.assertEqual((route["provider"], route["model"], route["family"]),
                            ("codekey-gemini", "gemini-4-argon", "google") if critic else ("codekey-codex-pro", "gpt-6-astra", "openai"))
                        self.assertEqual(route["reasoning_effort"], "high")
                        self.assertEqual(route["task_kind"], "scientific-judgment")
                        self.assertEqual(route["validation_scope"]["production_route"]["stage"], "topic-intelligence")
                        self.assertEqual(route["validation_scope"]["validation_roster"], "astra-argon")
                        self.assertEqual(route["persistent_output"], role in model_routing.WRITER_ROLES)
                        self.assertEqual(route["fresh_required"], critic)
                        self.assertEqual(route.get("response_streaming", False), not critic)
                        self.assertTrue(route["validation_scope"]["response_streaming"])
                    api_orchestrator.validate_roles("openai", "codekey-codex-pro", "codekey-gemini")
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        self.assertIsNone(pool.submit(model_routing.g1_transport_validation_roster).result())
                        self.assertFalse(pool.submit(model_routing.g1_response_streaming_active).result())
                        self.assertEqual(pool.submit(model_routing.cycle_routes, "topic-intelligence", "scientific-judgment").result(), original)
                        pool.submit(api_orchestrator.validate_roles, *providers).result()
                    model_routing.resolve_call("topic-intelligence", "semantic-planner", "openai", project_root=project)
                    with self.assertRaisesRegex(ValueError, "additional paid helpers"):
                        model_routing.resolve_call("topic-intelligence", "semantic-planner", "openai", project_root=project)
                    source.write_text("changed source")
                    with self.assertRaisesRegex(ValueError, "source changed"):
                        model_routing.resolve_call("topic-intelligence", "independent-critic-initial", "google", project_root=project)
                    raise RuntimeError("sample failure")
        self.assertIsNone(model_routing.g1_transport_validation_roster())
        self.assertFalse(model_routing.g1_response_streaming_active())
        self.assertEqual(model_routing.cycle_routes("topic-intelligence", "scientific-judgment"), original)
        api_orchestrator.validate_roles(*providers)

    def test_explicit_model_and_effort_are_recorded_as_requested(self):
        route = model_routing.resolve_call("experiment-design", "persistent-writer", "cheapai-gpt-discount",
                                          model="gpt-5.6-luna", reasoning_effort="low")
        self.assertEqual((route["provider"], route["model"], route["reasoning_effort"]),
                         ("cheapai-gpt-discount", "gpt-5.6-luna", "low"))
        self.assertTrue(route["explicit_selection"])

    def test_probe_preserves_exact_identity_without_role_or_catalog_allowlist(self):
        route = model_routing.select("intake", "endpoint-health", requested_provider="cheapai-gpt-discount", requested_model="future-exact-model")
        self.assertEqual((route["provider"], route["model"]), ("cheapai-gpt-discount", "future-exact-model"))
        self.assertLessEqual(route["max_output_tokens"], 256)

    def test_small_model_may_be_selected_for_writing_or_screening(self):
        policy, _ = model_routing.load_policy()
        policy["stage_routes"]["intake"]["persistent-writer"] = "luna"
        policy["auxiliary_routes"]["screening-assist"]["model_key"] = "luna"
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"policy.json"; source.write_text(json.dumps(policy))
            with patch.dict(os.environ, {"DR_OS_ROUTING_CONFIG":str(source)}):
                self.assertEqual(model_routing.select("intake","persistent-writer")["model_key"],"luna")
                self.assertEqual(model_routing.select("auxiliary","screening-assist")["model_key"],"luna")

    def test_false_family_and_unknown_alias_still_fail_configuration_validation(self):
        baseline, _ = model_routing.load_policy()
        for change in ("family", "alias", "cap"):
            policy=copy.deepcopy(baseline)
            if change=="family":policy["models"]["sonnet"]["family"]="openai"
            if change=="alias":policy["default_routes"]["writer"]="missing-alias"
            if change=="cap":policy["models"]["sol"]["max_output_tokens"]=True
            with tempfile.TemporaryDirectory() as folder:
                source=Path(folder)/"policy.json";source.write_text(json.dumps(policy))
                with patch.dict(os.environ,{"DR_OS_ROUTING_CONFIG":str(source)}),self.assertRaises(ValueError):
                    model_routing.load_policy()

    def test_same_family_panel_and_arbitrary_model_roster_are_valid(self):
        policy={"schema_version":"1.0","models":{"one":{"provider":"anthropic","model":"actual-model",
                "family":"anthropic","reasoning_effort":None,"max_output_tokens":2000}},"default_model":"one",
                "panel_routes":{"independent-critic-panel-domain":"one","independent-critic-panel-editorial":"one"}}
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"policy.json";source.write_text(json.dumps(policy))
            with patch.dict(os.environ,{"DR_OS_ROUTING_CONFIG":str(source)}):
                self.assertEqual(len(model_routing.load_policy()[0]["models"]),1)
                for role in ("persistent-writer","independent-critic-panel-domain","independent-critic-panel-editorial"):
                    self.assertEqual(model_routing.select("arbitrary",role)["model"],"actual-model")

    def test_local_model_alias_may_be_added_without_changing_global_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"models.json"
            source.write_text(json.dumps({"models":{"new-alias":{"provider":"codekey-kimi","model":"actual-new-id"}}}))
            with patch.object(model_routing,"LOCAL_MODEL_OVERRIDES",source):
                policy,_=model_routing.load_policy()
                self.assertEqual(policy["models"]["new-alias"]["family"],"moonshot")
            self.assertNotIn("actual-new-id",ai_providers.PRODUCTION_PROVIDERS["codekey-kimi"]["models"])

    def test_optional_stage_and_auxiliary_mappings_can_be_removed_or_extended(self):
        policy,_=model_routing.load_policy()
        policy["stage_routes"]={}
        policy["auxiliary_routes"]={"custom-task":{"model_key":"deepseek","max_output_tokens":1000}}
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"policy.json";source.write_text(json.dumps(policy))
            with patch.dict(os.environ,{"DR_OS_ROUTING_CONFIG":str(source)}):
                self.assertEqual(model_routing.select("new-context","custom-task")["family"],"deepseek")
                self.assertEqual(model_routing.select("new-context","writer")["model_key"],"sol")

    def test_unknown_or_missing_profile_does_not_silently_activate_production(self):
        with patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "legacy"}, clear=True):
            self.assertFalse(model_routing.production_enabled())
            self.assertEqual(model_routing.resolve_call("any", "any", "openai"),
                             {"provider": "openai", "model": None, "reasoning_effort": None})
        with patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "typo"}, clear=True), self.assertRaises(ValueError):
            model_routing.production_enabled()


class ProductionAuxiliaryTests(unittest.TestCase):
    def test_only_requested_optional_routes_are_preflighted(self):
        checked=[]
        def preflight(provider,model=None):
            checked.append(model)
            if model=="claude-opus-5-5":raise ValueError("requested final critic quote is missing")
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{"DR_OS_ROUTING_PROFILE":"production"},clear=True), \
             patch.object(api_orchestrator,"ROOT",Path(folder)), \
             patch("scripts.cloud_research_steps.before_cycle",return_value={"control_only":False}), \
             patch("scripts.cloud_research_steps.after_write",return_value={}), \
             patch("scripts.model_runtime.preflight_route",side_effect=preflight), \
             patch("scripts.model_runtime.call") as paid:
            state=Path(folder)/"projects/fixture/state/run.json"
            state.parent.mkdir(parents=True);state.write_text(json.dumps({"stage":"research"}))
            with self.assertRaisesRegex(ValueError,"final critic quote"):
                api_orchestrator.run_cycle("fixture","research",planning=True,review=True,remediate=True)
            paid.assert_not_called()
            self.assertIn("claude-opus-5-5",checked)

    def test_screening_never_uses_cheap_price_sort_or_luna(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True), \
                patch("scripts.task_router.model_runtime.cost_cny", return_value=0.3), \
                patch("scripts.task_router.model_runtime.budget_status", return_value={"project_remaining": 1, "paper_remaining": None}):
            info = task_router.plan(Path(directory), "screening-assist", None, "Keep all supplied source records")
            self.assertEqual(info["model"], "gpt-6.1-sol")
            self.assertEqual(info["reasoning_effort"], "high")
            self.assertEqual(info["candidate_count"], 1)
            self.assertFalse(info["automatic_acceptance"])

    def test_failed_production_route_blocks_without_automatic_paid_fallback(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True), \
                patch("scripts.task_router._health", return_value={("cheapai-gpt-discount", "gpt-5.6-luna"): "failed"}), \
                patch("scripts.task_router.model_runtime.call") as paid_call:
            with self.assertRaisesRegex(ValueError, "recently failed"):
                task_router.run(Path(directory), "metadata-extraction", None, "Source S1: sample size unknown",
                                source_contract={"sources": [{"source_id": "S1", "text": "sample size unknown", "locator": "p2"}], "fields": ["n"]})
            paid_call.assert_not_called()

    def test_auxiliary_run_passes_effort_and_marks_output_unaccepted(self):
        result = ai_providers.ModelResult(provider="cheapai-gpt-discount",model="gpt-5.6-luna",
            text='{"records":[{"source_id":"S1","fields":{"n":{"value":null,"quote":"","locator":""}}}]}',
            usage={},reported_model="gpt-5.6-luna",requested_effort="medium")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True), \
                patch("scripts.task_router.model_runtime.cost_cny", return_value=0.01), \
                patch("scripts.task_router.model_runtime.budget_status", return_value={"project_remaining": 1, "paper_remaining": None}), \
                patch("scripts.task_router.model_runtime.call", return_value=result) as call:
            contract = {"sources": [{"source_id": "S1", "text": "sample size unknown", "locator": "p2"}], "fields": ["n"]}
            response = task_router.run(Path(directory), "metadata-extraction", None, "Source S1: sample size unknown", source_contract=contract)
            request = call.call_args.kwargs
            self.assertEqual(request["provider"], "cheapai-gpt-discount")
            self.assertEqual(request["reasoning_effort"], "medium")
            self.assertEqual(request["source_contract"], contract)
            self.assertIn("Task boundary:", request["prompt"])
            receipt = json.loads((Path(directory) / response["result"]).read_text(encoding="utf-8"))
            self.assertFalse(receipt["automatic_acceptance"])
            self.assertFalse(receipt["scientific_completion_verified"])

    def test_multimodal_requires_attachments_before_a_paid_request(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.task_router.plan", return_value={}), \
                patch("scripts.task_router.model_runtime.call") as paid_call:
            with self.assertRaisesRegex(ValueError, "requires explicit source attachments"):
                task_router.run(Path(directory), "multimodal-inspection", "codekey-gemini", "Inspect supplied figure")
            paid_call.assert_not_called()
