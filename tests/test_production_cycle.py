"""Five-role production cycles on temporary fixtures and mocked gateways.

This exercises real routing, runtime reservations, artifact writes and writer
provenance. Scientific retrieval/builders are replaced by fixture receipts;
the fixture is not a completed study and creates no real spending authority.
"""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ai_providers, api_orchestrator, model_runtime, model_spend, relay_billing


class ProductionCycleTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
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
        self.stack.enter_context(patch.object(api_orchestrator, "critic_prompt", return_value="Fixture scientific audit"))
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
        body = self.payloads()[self.index]
        self.index += 1
        return ai_providers.ModelResult(provider, model, json.dumps(body), {"input_tokens": 100, "output_tokens": 20},
            f"fixture-request-{self.index}", model, spec["protocol"], spec["root"] + spec["path"].format(model=model),
            "fixture-only-gateway", completion_status="completed", requested_effort=kwargs["reasoning_effort"])

    def run_cycle(self, stage="experiment-execution", task_kind=None, task_profile=None, *, routine=True):
        self.stage = stage
        gate = "G1" if stage == "topic-intelligence" else "G4"
        (self.project / "state" / "run.json").write_text(json.dumps({
            "stage": stage, "gate": gate, "status": "awaiting_work"}), encoding="utf-8")
        if task_profile is None and routine:
            task_profile = {"task_class": "routine-implementation", "science_risk": "routine"}
        return api_orchestrator.run_cycle("demo", stage, "anthropic", "openai", "anthropic", "", "",
            max_output_tokens=300, control_max_output_tokens=100, automatic_data=False, task_kind=task_kind,
            task_profile=task_profile)

    def test_real_five_role_cycle_forwards_models_effort_and_fresh_independent_reviews(self):
        with (patch.object(ai_providers, "call", side_effect=self.transport) as post,
                patch.object(model_runtime, "call", wraps=model_runtime.call) as runtime):
            manifest = self.run_cycle()
        expected = ["claude-sonnet-5-5", "gpt-6.1-sol", "claude-sonnet-5-5", "gpt-6.1-sol", "claude-opus-5-5"]
        self.assertEqual([call.kwargs["model"] for call in post.call_args_list], expected)
        self.assertEqual([call.kwargs["reasoning_effort"] for call in post.call_args_list], ["high"] * 5)
        self.assertEqual([call.kwargs["max_output_tokens"] for call in post.call_args_list], [100, 300, 100, 300, 100])
        self.assertEqual([call.kwargs["role"] for call in runtime.call_args_list], [
            "semantic-planner", "persistent-writer", "independent-critic-initial", "persistent-remediator", "independent-critic-final"])
        self.assertFalse(runtime.call_args_list[2].kwargs["use_cache"])
        self.assertFalse(runtime.call_args_list[4].kwargs["use_cache"])
        self.assertEqual(manifest["output_policy"]["persistent_writer_family"], "openai")
        self.assertEqual(manifest["provider_audit"]["critic_1"]["requested_model"], "claude-sonnet-5-5")
        self.assertEqual(manifest["provider_audit"]["critic_final"]["requested_model"], "claude-opus-5-5")
        self.assertEqual(len(manifest["cost_controls"]["route_preflight"]), 3)
        provenance = json.loads((self.project / "state/output-provenance.json").read_text())
        self.assertEqual(provenance["files"]["program/fixture.md"]["family"], "openai")
        self.assertEqual(provenance["files"]["program/fixture.md"]["role"], "persistent-remediator")
        self.assertEqual(provenance["files"]["program/fixture.md"]["model"], "gpt-6.1-sol")
        reviews = list((self.project / "reviews/independent").glob("*.json"))
        self.assertEqual(len(reviews), 2)
        self.assertTrue(any(path.name.endswith("-initial.json") for path in reviews))
        self.assertTrue(any(path.name.endswith("-final.json") for path in reviews))
        self.assertAlmostEqual(model_spend.read(self.project)["spent_cny"], 0.005)
        self.assertEqual(model_spend.read(self.project)["reservations"], {})
        self.assertEqual(json.loads((self.project / "state/run.json").read_text())["status"], "awaiting_work")

    def test_core_stage_keeps_opus_and_astra_across_all_five_roles(self):
        with patch.object(ai_providers, "call", side_effect=self.transport) as post:
            manifest = self.run_cycle(stage="topic-intelligence")
        self.assertEqual([call.kwargs["model"] for call in post.call_args_list], [
            "claude-opus-5-5", "gpt-6-astra", "claude-opus-5-5", "gpt-6-astra", "claude-opus-5-5"])
        self.assertEqual(len(manifest["cost_controls"]["route_preflight"]), 2)
        self.assertEqual(manifest["output_policy"]["persistent_writer_family"], "openai")

    def test_explicit_core_task_changes_models_without_adding_paid_roles(self):
        with patch.object(ai_providers, "call", side_effect=self.transport) as post:
            manifest = self.run_cycle(task_kind="core-story")
        self.assertEqual(post.call_count, 5)
        self.assertEqual([call.kwargs["model"] for call in post.call_args_list], [
            "claude-opus-5-5", "gpt-6-astra", "claude-opus-5-5", "gpt-6-astra", "claude-opus-5-5"])
        self.assertEqual(manifest["task_kind"], "core-story")

    def test_missing_later_final_critic_quote_blocks_the_first_paid_request(self):
        prices = json.loads((model_runtime.ROOT / "config/model-pricing.json").read_text())
        prices["quotes"] = [quote for quote in prices["quotes"] if quote["model"] != "claude-opus-5-5"]
        with (patch.dict("os.environ", {"DR_OS_MODEL_PRICING_JSON": json.dumps(prices)}),
                patch.object(ai_providers, "call") as post,
                patch.object(relay_billing, "read_meter") as meter):
            with self.assertRaises(model_runtime.ModelBudgetError):
                self.run_cycle()
        post.assert_not_called()
        meter.assert_not_called()
        self.assertEqual(model_spend.read(self.project)["reservations"], {})
        self.assertEqual(model_spend.read(self.project)["spent_cny"], 0)

    def test_unneeded_optional_argon_quote_does_not_block_this_scientific_cycle(self):
        prices = json.loads((model_runtime.ROOT / "config/model-pricing.json").read_text())
        prices["quotes"] = [quote for quote in prices["quotes"] if quote["model"] != "gemini-4-argon-high"]
        with (patch.dict("os.environ", {"DR_OS_MODEL_PRICING_JSON": json.dumps(prices)}),
                patch.object(ai_providers, "call", side_effect=self.transport) as post):
            self.run_cycle()
        self.assertEqual(post.call_count, 5)


if __name__ == "__main__":
    unittest.main()
