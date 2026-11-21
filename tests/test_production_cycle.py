"""Task-selected production calls on temporary fixtures and mocked gateways.

This exercises real routing, runtime reservations, artifact writes and writer
provenance. Scientific retrieval/builders are replaced by fixture receipts;
the fixture is not a completed study and creates no real spending authority.
"""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
import json
import re
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import ai_providers, api_orchestrator, model_routing, model_runtime, model_spend, relay_billing


class ProductionCycleTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        from tests.relay_guard_fixtures import install_fake_guard
        self.shared_guard=install_fake_guard(self.stack)
        temporary = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(temporary)
        self.project = self.root / "projects" / "demo"
        (self.root / "config").mkdir()
        (self.root / "config" / "stages.json").write_text(json.dumps({"stages": {
            "experiment-execution": {"gate": "G4", "contract": "Fixture G4", "author_task": "Fixture only"},
            "topic-intelligence": {"gate": "G1", "contract": "Fixture G1", "author_task": "Fixture only"}}}),
            encoding="utf-8")
        self.env = {"DR_OS_ROUTING_PROFILE": "production", "DR_OS_REQUIRE_MODEL_AUTH": "1",
                    "GITHUB_ACTIONS":"true", "DR_OS_REQUIRE_REMOTE_RESERVATION":"1"}
        self.env.update({spec["key_setting"]: "fixture-provider-key-" + provider
                         for provider, spec in ai_providers.PRODUCTION_PROVIDERS.items()})
        self.stack.enter_context(patch.dict("os.environ", self.env, clear=True))
        self.stack.enter_context(patch("scripts.production_readiness.catalog",
            side_effect=lambda provider, environment: set(ai_providers.PRODUCTION_PROVIDERS[provider]["models"])))
        self.stack.enter_context(patch.object(api_orchestrator, "ROOT", self.root))
        self.stack.enter_context(patch("scripts.cloud_checkpoint.sync_billing", return_value=None))
        self.stack.enter_context(patch("scripts.cloud_research_steps.before_cycle", return_value={
            "control_only": False, "blockers": [], "fixture_only": True}))
        self.stack.enter_context(patch.object(api_orchestrator, "prepare_discovery_evidence", return_value=(
            json.dumps({"literature": {"receipts": [{"fixture_only": True}], "pending_searches": 0}}), None)))
        self.stack.enter_context(patch.object(api_orchestrator, "planning_prompt", return_value="Fixture planning task"))
        self.stack.enter_context(patch.object(api_orchestrator, "writer_prompt", return_value="Fixture writing task"))
        self.real_critic_prompt = api_orchestrator.critic_prompt
        self.critic_prompt = self.stack.enter_context(patch.object(api_orchestrator, "critic_prompt", return_value="Fixture scientific audit"))
        self.stack.enter_context(patch.object(api_orchestrator, "remediation_prompt", return_value="Fixture remediation task"))
        self.stack.enter_context(patch.object(api_orchestrator, "refresh_post_write_evidence", return_value={
            "controlled_steps": {"fixture_only": True}, "academic_style_audit": None}))
        self.stack.enter_context(patch.object(api_orchestrator, "refresh_research_method_audits", return_value=None))
        self.stack.enter_context(patch("scripts.research_increments.freeze_plans", return_value=None))
        self.stack.enter_context(patch("scripts.research_increments.record_editing_attempt", return_value=None))
        self.stack.enter_context(patch.object(relay_billing, "read_meter", return_value={"fixture_only": True}))
        self.stack.enter_context(patch.object(relay_billing, "settle", return_value={"actual_cost_cny": 0.001,
            "debit_evidence": {"source": "fixture-only", "exactly_one_new_gateway_request": True}}))
        model_spend.write(self.project, model_spend.initial())
        model_spend.grant(self.project, new_ceiling_cny=300, actor="Fake Owner", run_id="fixture-owner-grant")
        self.index = 0
        self.stage = "experiment-execution"

    def payloads(self):
        plan = {"schema_version": "1.0", "stage": self.stage, "objectives": ["fixture objective"],
                "artifact_specs": [], "evidence_requirements": [], "figure_specs": [], "risks": [], "open_questions": []}
        writer = {"schema_version": "1.0", "stage": self.stage,
                  "artifacts": [{"path": "program/fixture.md", "content": "Fixture draft without scientific results."}], "notes": []}
        initial = {"verdict": "revise", "fatal_findings": [], "major_findings": ["Missing located source."],
                   "minor_findings": [], "missing_evidence": [], "remediation_steps": ["Locate the supplied fixture."], "uncertainty": []}
        remediation = {"schema_version": "1.0", "stage": self.stage,
                       "artifacts": [{"path": "program/fixture.md", "content": "Revised fixture with a source locator; no study was conducted."}],
                       "notes": ["fixed: Added the supplied fixture locator."]}
        final = {"verdict": "pass-with-conditions", "fatal_findings": [], "major_findings": [],
                 "minor_findings": [], "missing_evidence": [], "remediation_steps": [],
                 "uncertainty": ["Fixture only; scientific and human verification remain."]}
        return [plan, writer, initial, remediation, final]

    def transport(self, provider, prompt, **kwargs):
        spec = ai_providers.PRODUCTION_PROVIDERS[provider]
        model = kwargs["model"]
        body = self._response_sequence[self.index]
        self.index += 1
        return ai_providers.ModelResult(provider, model, json.dumps(body), {"input_tokens": 100, "output_tokens": 20},
            f"fixture-request-{self.index}", model, spec["protocol"], spec["root"] + spec["path"].format(model=model),
            "fixture-only-gateway", completion_status="completed", requested_effort=kwargs["reasoning_effort"])

    def run_cycle(self, stage="experiment-execution", task_kind=None, task_profile=None, *, routine=True, validation_roster=None, planning=False, review=False, remediate=False, writer_provider=None, critic_provider=None, clean_review=False):
        self.stage = stage
        gate = "G1" if stage == "topic-intelligence" else "G4"
        state = {"stage": stage, "gate": gate, "status": "awaiting_work", "paper_count": 1, "active_paper": "P01"}
        if validation_roster:
            state["approved_gates"] = ["G0"]
        (self.project / "state" / "run.json").write_text(json.dumps(state), encoding="utf-8")
        (self.project / "intake").mkdir(exist_ok=True)
        (self.project / "intake/constraints.json").write_text(json.dumps({"research_goal":"Synthetic route fixture; no research was conducted."}), encoding="utf-8")
        (self.project / "papers/P01").mkdir(parents=True, exist_ok=True)
        payloads = self.payloads()
        if clean_review:
            payloads[2] = payloads[4]
        order = ([0] if planning else []) + [1] + ([2] if review else [])
        if remediate and not clean_review:
            order += [3, 4]
        self._response_sequence = [payloads[index] for index in order]
        self.index = 0
        if task_profile is None and routine:
            task_profile = {"task_class": "routine-implementation", "science_risk": "routine"}
        with (model_routing.g1_transport_validation_route(self.project, "d" * 64, validation_roster=validation_roster)
              if validation_roster else nullcontext()):
            return api_orchestrator.run_cycle("demo", stage, None, writer_provider, critic_provider, "Synthetic task", "",
                max_output_tokens=300, control_max_output_tokens=100, automatic_data=False, task_kind=task_kind,
                task_profile=task_profile, planning=planning, review=review, remediate=remediate)

    def test_default_cycle_runs_one_writer_and_records_real_spend_and_origin(self):
        with patch.object(ai_providers, "call", side_effect=self.transport) as post:
            manifest = self.run_cycle()
        self.assertEqual(post.call_count, 1)
        self.assertEqual([row["role"] for row in manifest["calls"]], ["persistent-writer"])
        self.assertEqual(manifest["reviews"], [])
        self.assertFalse(manifest["scientific_completion_verified"])
        self.assertAlmostEqual(model_spend.read(self.project)["spent_cny"], .001)
        self.assertEqual(model_spend.read(self.project)["reservations"], {})
        provenance=json.loads((self.project/"state/output-provenance.json").read_text())
        self.assertEqual(provenance["files"]["program/fixture.md"]["model"],"gpt-6.1-sol")

    def test_explicit_plan_review_and_repair_make_five_actual_source_bound_calls(self):
        with patch.object(ai_providers,"call",side_effect=self.transport) as post, \
             patch.object(model_runtime,"call",wraps=model_runtime.call) as runtime:
            manifest=self.run_cycle(planning=True,review=True,remediate=True)
        self.assertEqual([row.kwargs["role"] for row in runtime.call_args_list],list(model_routing.CYCLE_ROLES))
        self.assertEqual([row.kwargs["max_output_tokens"] for row in post.call_args_list],[100,300,100,300,100])
        self.assertFalse(runtime.call_args_list[2].kwargs["use_cache"])
        self.assertFalse(runtime.call_args_list[4].kwargs["use_cache"])
        self.assertEqual(len(manifest["reviews"]),2)
        self.assertNotEqual(manifest["reviews"][0]["sources"],manifest["reviews"][1]["sources"])
        provenance=json.loads((self.project/"state/output-provenance.json").read_text())
        self.assertEqual(provenance["files"]["program/fixture.md"]["role"],"persistent-remediator")
        self.assertAlmostEqual(model_spend.read(self.project)["spent_cny"],.005)
        self.assertEqual(model_spend.read(self.project)["reservations"],{})
        self.assertEqual(json.loads((self.project/"state/run.json").read_text())["status"],"awaiting_work")

    def test_same_family_can_write_and_review_without_automatic_repair(self):
        with patch.object(ai_providers,"call",side_effect=self.transport) as post:
            manifest=self.run_cycle(review=True,writer_provider="codekey-kiro-enterprise",critic_provider="codekey-kiro-enterprise")
        self.assertEqual(post.call_count,2)
        self.assertTrue(all(row["family"]=="anthropic" for row in manifest["actual_routes"].values()))
        self.assertEqual(manifest["independent_audit"]["verdict"],"revise")
        self.assertEqual((self.project/"program/fixture.md").read_text(),"Fixture draft without scientific results.")

    def test_clean_review_does_not_make_an_unused_repair_call(self):
        with patch.object(ai_providers,"call",side_effect=self.transport) as post:
            manifest=self.run_cycle(review=True,remediate=True,clean_review=True)
        self.assertEqual(post.call_count,2)
        self.assertEqual(len(manifest["reviews"]),1)
        self.assertNotIn("persistent-remediator",manifest["actual_routes"])

    def test_task_label_does_not_force_other_models_or_roles(self):
        with patch.object(ai_providers,"call",side_effect=self.transport) as post:
            manifest=self.run_cycle(task_kind="core-story")
        self.assertEqual(post.call_count,1)
        self.assertEqual(manifest["actual_routes"]["persistent-writer"]["model"],"gpt-6.1-sol")

    def test_optional_critic_price_is_not_needed_for_default_writer(self):
        prices=json.loads((model_runtime.ROOT/"config/model-pricing.json").read_text())
        prices["quotes"]=[row for row in prices["quotes"] if row["model"]!="claude-opus-5-5"]
        with patch.dict("os.environ",{"DR_OS_MODEL_PRICING_JSON":json.dumps(prices)}), \
             patch.object(ai_providers,"call",side_effect=self.transport) as post:
            self.run_cycle()
        self.assertEqual(post.call_count,1)

    def test_requested_later_critic_price_is_checked_before_the_first_paid_call(self):
        prices=json.loads((model_runtime.ROOT/"config/model-pricing.json").read_text())
        prices["quotes"]=[row for row in prices["quotes"] if row["model"]!="claude-opus-5-5"]
        with patch.dict("os.environ",{"DR_OS_MODEL_PRICING_JSON":json.dumps(prices)}), \
             patch.object(ai_providers,"call") as post:
            with self.assertRaises(model_runtime.ModelBudgetError):
                self.run_cycle(planning=True,review=True,remediate=True)
        post.assert_not_called()
        self.assertEqual(model_spend.read(self.project)["spent_cny"],0)

    def test_explicit_g1_validation_keeps_its_selected_transport_sample(self):
        self.critic_prompt.side_effect=self.real_critic_prompt
        with patch.dict("os.environ",{"DR_OS_CLOUD_COMMAND_DEADLINE_EPOCH":str(time.time()+3600)}), \
             patch.object(ai_providers,"call",side_effect=self.transport) as post:
            manifest=self.run_cycle(stage="topic-intelligence",validation_roster="astra-argon",planning=True,review=True,remediate=True)
        self.assertEqual([row.kwargs["model"] for row in post.call_args_list],
                         ["gpt-6-astra","gpt-6-astra","gemini-4-argon","gpt-6-astra","gemini-4-argon"])
        self.assertIn("Fixture draft",post.call_args_list[2].args[1])
        self.assertIn("Revised fixture",post.call_args_list[4].args[1])
        self.assertEqual(manifest["reviews"][-1]["identity"]["reported_model"],"gemini-4-argon")
