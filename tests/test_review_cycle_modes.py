"""Actual observation and protocol receipts from synthetic read-only callbacks."""
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts import research_cycle, review_receipts
from scripts.research_artifacts import read, write
from tests.research_cycle_fixtures import pending_decision


class AdapterCycleParityTests(unittest.TestCase):
    """Exercise direct API and its compatibility commands with the same source-bound cycle."""

    def run_adapter(self, adapter, stage, gate, *, repair=False):
        from scripts import api_orchestrator as api
        from scripts import autopilot
        from scripts.ai_providers import ModelResult
        with ExitStack() as stack:
            root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            project = root / "projects/demo"
            write(root / "config/stages.json", {"stages": {stage: {"gate": gate}}})
            original = {"stage": stage, "gate": gate, "stage_index": 0 if gate == "G0" else 1,
                        "status": "awaiting_work", "approved_gates": [], "approvals": [],
                        "paper_statuses": {"P01": "active"}}
            write(project / "state/run.json", original)
            write(project / "intake/constraints.json", {"research_goal": "Synthetic adapter parity fixture"})
            plan = {"schema_version": "1.0", "stage": stage, **{key: [] for key in (
                "objectives", "artifact_specs", "evidence_requirements", "figure_specs", "risks", "open_questions")}}
            bundle = {"schema_version": "1.0", "stage": stage, "artifacts": [], "notes": []}
            clean = {"verdict": "pass-with-conditions", **{key: [] for key in (
                "fatal_findings", "major_findings", "minor_findings", "missing_evidence", "remediation_steps")},
                "uncertainty": ["Synthetic transport cannot validate scientific merit."]}
            finding = {**clean, "verdict": "revise", "major_findings": ["Missing comparison"],
                       "remediation_steps": ["Add the comparison"]} if repair else clean
            roles = []
            stack.enter_context(patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}, clear=True))
            stack.enter_context(patch.object(api, "ROOT", root))
            stack.enter_context(patch.object(autopilot.researchctl, "PROJECTS_ROOT", root / "projects"))
            for target, value in {
                "scripts.model_routing.production_enabled": False,
                "scripts.scientific_scope.validate": [],
                "scripts.cloud_research_steps.before_cycle": {"control_only": False, "blockers": []},
                "scripts.model_runtime.budget_status": {},
                "scripts.api_orchestrator.prepare_discovery_evidence": (
                    json.dumps({"literature": {"receipts": [{"fixture_only": True}], "pending_searches": 0}}), None),
                "scripts.api_orchestrator.prepare_revision_baseline": None,
                "scripts.api_orchestrator.refresh_post_write_evidence": {"academic_style_audit": None, "controlled_steps": {}},
                "scripts.api_orchestrator.refresh_research_method_audits": None,
                "scripts.research_increments.freeze_plans": None,
                "scripts.research_increments.record_editing_attempt": None,
                "scripts.automated_quality.checked_run": None,
                "scripts.literature_model_screening.cycle_input": None,
                "scripts.cost_audit.refresh": {},
                "scripts.researchctl.gate_errors": ["Synthetic evidence is incomplete"],
            }.items():
                stack.enter_context(patch(target, return_value=value))

            from scripts import model_spend
            write(project / model_spend.FILE, model_spend.initial())
            preflight = stack.enter_context(patch("scripts.model_runtime.preflight_route", return_value={}))
            for name in ("planning_prompt", "writer_prompt", "critic_prompt", "remediation_prompt"):
                stack.enter_context(patch.object(api, name, return_value="Synthetic source-bound request"))

            def call(_project, *, role, **kwargs):
                roles.append(role)
                payload = {"semantic-planner": plan, "persistent-writer": bundle,
                    "independent-critic-initial": finding, "independent-critic-final": clean,
                    "persistent-remediator": {**bundle, "notes": ["fixed: added comparison"]}}[role]
                provider = kwargs["provider"]
                model = "gpt-test" if provider == "uuapi-openai" else "claude-test"
                return ModelResult(provider, model, json.dumps(payload), {}, reported_model=model,
                    completion_status="completed", request_id=role)
            stack.enter_context(patch("scripts.model_runtime.call", side_effect=call))
            critic = "codekey-deepseek" if gate == "G0" else "uuapi-anthropic"
            if adapter == "api":
                result = api.run_cycle("demo", stage, "uuapi-anthropic", "uuapi-openai", critic, "", "", automatic_data=False)
            else:
                result = autopilot.run_stage("demo", planner_provider="uuapi-anthropic",
                    writer_provider="uuapi-openai", critic_provider=critic)
            self.assertEqual([call.args[0] for call in preflight.call_args_list], ["uuapi-anthropic", "uuapi-openai"])
            if gate == "G0":
                self.assertEqual(result["provider_audit"]["critic_1"], {"status": "not_called", "reason": "administrative_intake"})
            mode = result["cost_controls"]["review_mode"]
            self.assertEqual(read(project / "state/run.json"), original)
            if gate == "G0":
                self.assertFalse((project / review_receipts.PREFIX).exists())
                self.assertEqual(result["research_decision"]["status"], "not_applicable")
            else:
                observation = review_receipts.observation(project, stage)["receipt"]
                self.assertFalse(observation["gate_authority"])
                self.assertFalse(observation["scientific_completion_verified"])
            return roles, mode

    def test_G0_adapters_use_only_planner_writer(self):
        for adapter in ("api", "cli"):
            with self.subTest(adapter=adapter):
                roles, mode = self.run_adapter(adapter, "intake", "G0")
                self.assertEqual(roles, ["semantic-planner", "persistent-writer"])
                self.assertEqual(mode, "administrative_intake")

    def test_G1_adapters_use_one_actual_source_bound_critic(self):
        for adapter in ("api", "cli"):
            with self.subTest(adapter=adapter):
                roles, mode = self.run_adapter(adapter, "topic-intelligence", "G1")
                self.assertEqual(roles, ["semantic-planner", "persistent-writer", "independent-critic-initial"])
                self.assertEqual(mode, "scientific_review")

    def test_G1_adapters_add_repair_and_fresh_review_only_for_actual_findings(self):
        for adapter in ("api", "cli"):
            with self.subTest(adapter=adapter):
                roles, _mode = self.run_adapter(adapter, "topic-intelligence", "G1", repair=True)
                self.assertEqual(roles, ["semantic-planner", "persistent-writer", "independent-critic-initial",
                    "persistent-remediator", "independent-critic-final"])


class ReviewCycleModeTests(unittest.TestCase):
    def test_current_scientific_decision_survives_C_only_refresh_after_actual_review(self):
        from tests.test_quality_gate import report
        write(self.project / "state/run.json", {"stage": "topic-intelligence", "gate": "G1", "active_paper": "P01"})
        pending_decision(self.project, "topic-intelligence", "actual")
        quality = report("G1")
        write(self.project / "program/quality-G1.json", quality)
        def refresh_C(*args):
            quality["scores"]["publication_potential"] = 1
            quality["assessments"] = {"publication_potential": {"status": "unresolved"}}
            write(self.project / "program/quality-G1.json", quality)
        result = research_cycle.review_cycle(self.project, "topic-intelligence", "actual", writer_family="openai",
            prompt=lambda: "Inspect current synthetic sources", invoke=self.invoke, remediate=lambda *args: self.fail("No repair"),
            refresh=lambda phase: ({}, {}), writer_notes=[], log=refresh_C)
        self.assertEqual(result["research_decision"]["status"], "independently_observed")
        self.assertEqual(research_cycle.decision_errors(result["research_decision"]), [])
        self.assertEqual(self.calls, ["initial"])

    def test_independent_assessment_errors_prevent_submission_transition(self):
        decision = {"errors": [], "review_errors": ["the latest critic assessed a different cycle"]}
        with patch("scripts.supplemental_experiments.automatic_approval", return_value={}) as approve, patch(
            "scripts.research_phase.enter_submission"
        ) as transition:
            result = research_cycle.after_reviews(self.project, "writing-and-review", "actual", decision, list)
        transition.assert_not_called()
        approve.assert_not_called()
        self.assertNotIn("writing_phase_transition", result)
        self.assertEqual(research_cycle.decision_errors(decision),
                         ["research decision: the latest critic assessed a different cycle"])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.project = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        write(self.project / "state/run.json", {"stage":"writing-and-review", "gate":"G5", "active_paper":"P01"})
        write(self.project / "papers/P01/paper-contract.json", {"paper_id":"P01", "writing_phase":"scientific"})
        self.stack.enter_context(patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR":"1"}))
        self.stack.enter_context(patch("scripts.automated_quality.checked_run", return_value=None))
        pending_decision(self.project, "writing-and-review", "actual", "P01")
        self.calls = []

    def invoke(self, phase, request):
        self.calls.append(phase)
        audit = {"verdict":"pass-with-conditions", "fatal_findings":[], "major_findings":[], "minor_findings":[],
                 "missing_evidence":[], "remediation_steps":[], "uncertainty":["Synthetic fixture cannot establish scientific validity."]}
        path = self.project / ("reviews/independent/actual-" + phase + ".json")
        write(path, audit)
        return audit, path, {"provider":"synthetic-anthropic", "family":"anthropic", "requested_model":"synthetic-critic",
            "reported_model":"synthetic-critic", "completion_status":"completed", "cache_hit":False, "request_id":phase}

    def cycle(self, invoke=None):
        return research_cycle.review_cycle(self.project, "writing-and-review", "actual", writer_family="openai",
            prompt=lambda: "Inspect current synthetic sources", invoke=invoke or self.invoke,
            remediate=lambda *args: self.fail("A clean observation does not justify repair"),
            refresh=lambda phase: ({}, {}), writer_notes=[], log=lambda *args: None)

    def test_pending_supplemental_protocol_keeps_two_real_authority_receipts_without_repair(self):
        with patch("scripts.supplemental_experiments.proposal_pending", return_value=True):
            result = self.cycle()
            self.assertEqual(self.calls, ["initial", "final"])
            self.assertTrue(result["remediation_skipped"])
            self.assertEqual(review_receipts.validate_gate(self.project, "G5", "P01", expected_purpose="supplemental_protocol"), [])
            self.assertTrue(review_receipts.validate_gate(self.project, "G5", "P01", expected_purpose="stage"))
        directory = self.project / review_receipts.PREFIX / "G5-P01/actual"
        first, last = read(directory / "initial.json"), read(directory / "final.json")
        self.assertNotEqual(first["identity"]["request_id"], last["identity"]["request_id"])
        self.assertEqual(last["materials"]["review_purpose"], "supplemental_protocol")
        self.assertFalse(read(directory / "observation.json")["gate_authority"])
        self.assertFalse((self.project / "experiments/registry.jsonl").exists())

    def test_ordinary_clean_cycle_has_only_one_protected_advisory_observation(self):
        self.cycle()
        self.assertEqual(self.calls, ["initial"])
        observed = review_receipts.observation(self.project, "writing-and-review", "P01")["receipt"]
        self.assertFalse(observed["gate_authority"])
        self.assertTrue(review_receipts.validate_gate(self.project, "G5", "P01", expected_purpose="scientific_writing"))

    def test_failed_invocation_id_is_never_replayed_or_overwritten(self):
        def broken(phase, request):
            self.calls.append(phase)
            raise ValueError("Synthetic response failure")
        with self.assertRaisesRegex(ValueError, "response failure"):
            self.cycle(broken)
        attempt = self.project / review_receipts.PREFIX / "G5-P01/actual/attempt.json"
        before = attempt.read_bytes()
        with self.assertRaises(FileExistsError):
            self.cycle()
        self.assertEqual(self.calls, ["initial"])
        self.assertEqual(attempt.read_bytes(), before)
