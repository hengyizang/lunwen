"""Explicit advisory API review through the normal autopilot; no real model calls."""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import api_orchestrator, autopilot, model_spend, output_provenance
from scripts.ai_providers import ModelResult
from scripts.research_artifacts import read, write


class CLICleanReviewTests(unittest.TestCase):
    def run_clean_cycle(self, stage="topic-intelligence", gate="G1", index=1, writer_notes=None):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);project=root/"projects/demo"
        state={"schema_version":"2.0","stage_index":index,"stage":stage,"gate":gate,
               "status":"awaiting_work","active_paper":"P01","paper_count":1,
               "paper_statuses":{"P01":"active"},"approved_gates":[],"approvals":[]}
        write(project/"state/run.json",state)
        write(project/"intake/constraints.json",{"research_goal":"Review the synthetic comparison."})
        write(project/"papers/P01/paper-contract.json",{"paper_id":"P01","writing_phase":"scientific"})
        write(project/model_spend.FILE,model_spend.initial())
        audit={"verdict":"pass-with-conditions","fatal_findings":[],"major_findings":[],
               "minor_findings":[],"missing_evidence":[],"remediation_steps":[],
               "uncertainty":["Software fixture; scientific validity is not established."]}
        calls=[]
        def response(_project,*,role,provider,**kwargs):
            calls.append(role)
            if role=="semantic-planner":
                value={"schema_version":"1.0","stage":stage,**{key:[] for key in
                    ("objectives","artifact_specs","evidence_requirements","figure_specs","risks","open_questions")}}
            elif role=="persistent-writer":
                value={"schema_version":"1.0","stage":stage,"notes":writer_notes or [],"artifacts":[
                    {"path":"program/scientific-notes.txt","content":"The comparison remains provisional.\n"}]}
            else:
                self.assertEqual(role,"independent-critic-initial")
                value=audit
            model="same-family-fixture"
            return ModelResult(provider,model,json.dumps(value),{},reported_model=model,
                               completion_status="completed",request_id=role+"-fixture")
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,{"DR_OS_ROUTING_PROFILE":"legacy"},clear=True))
            stack.enter_context(patch.object(api_orchestrator,"ROOT",root))
            stack.enter_context(patch.object(autopilot.researchctl,"PROJECTS_ROOT",root/"projects"))
            stack.enter_context(patch("scripts.model_runtime.preflight_route",return_value={}))
            stack.enter_context(patch("scripts.model_runtime.budget_status",return_value={}))
            stack.enter_context(patch("scripts.model_runtime.call",side_effect=response))
            result=autopilot.run_stage("demo",planning=True,review=True,remediate=True,
                                      planner_provider="anthropic",writer_provider="anthropic",critic_provider="anthropic")
        self.assertEqual(calls,["semantic-planner","persistent-writer","independent-critic-initial"])
        self.assertFalse(result["scientific_completion_verified"])
        self.assertEqual(result["notes"],writer_notes or [])
        receipt=read(project/"api_runs"/result["run_id"]/"initial-review-receipt.json")
        self.assertFalse(receipt["identity"]["cache_hit"])
        self.assertEqual(receipt["sources"][0]["path"],"program/scientific-notes.txt")
        self.assertEqual(receipt["identity"]["request_id"],"independent-critic-initial-fixture")
        self.assertFalse(receipt["scientific_completion_verified"])
        self.assertEqual(read(project/"state/run.json")["approved_gates"],[])
        self.assertEqual(read(project/"state/run.json")["approvals"],[])
        self.assertEqual(output_provenance.current_origin(project,project/"program/scientific-notes.txt")["family"],"anthropic")
        self.assertFalse((project/"papers/P01/submission").exists())
        return project,result,receipt

    def test_clean_initial_review_needs_only_one_actual_critic(self):
        self.run_clean_cycle()

    def test_plain_uncertainty_notes_survive_advisory_observation(self):
        self.run_clean_cycle(writer_notes=["The scientific interpretation remains provisional."])

    def test_scientific_writing_clean_review_keeps_actual_observation(self):
        self.run_clean_cycle("writing-and-review","G5",5)
