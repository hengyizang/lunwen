"""The normal entry executes tasks without manufacturing stage approvals."""
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import io
import tempfile
import unittest

from scripts import api_orchestrator as api, autopilot, model_runtime, model_spend, researchctl
from scripts.research_artifacts import read, write


class AutopilotTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(researchctl,"PROJECTS_ROOT",self.root/"projects"))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        researchctl.initialize(SimpleNamespace(project="demo",paper_count=1,venue=None,question="A real open research question"))
        self.project=researchctl.project_dir("demo")

    def state(self,index,status="awaiting_work"):
        state=researchctl.load_state("demo")
        state.update(stage_index=index,stage=researchctl.STAGES[index]["name"],gate=researchctl.STAGES[index]["gate"],status=status)
        state.pop("current_work",None);researchctl.save_state("demo",state)
        return state

    def cycle(self, result=None):
        return patch.object(api,"run_cycle",return_value=result or {"run_id":"synthetic-cycle","research_decision":{"errors":[],"review_errors":[]}})

    def test_plan_is_read_only_and_defaults_to_one_writer(self):
        before={p:p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        with patch.object(model_runtime,"call",side_effect=AssertionError("no model")),patch.object(model_spend,"grant",side_effect=AssertionError("no grant")):
            plan=autopilot.show_plan("demo","Investigate the weakest assumption")
        self.assertEqual(plan["planned_model_calls"],1)
        self.assertEqual(plan["paid_model_calls"],0)
        self.assertEqual(before,{p:p.read_bytes() for p in self.project.rglob("*") if p.is_file()})
        self.assertEqual(autopilot.show_plan("demo",planning=True,review=True,remediate=True)["with_repair_model_calls"],5)

    def test_pending_topics_and_missing_portfolio_do_not_block_the_selected_task(self):
        for index in (1,2):
            original=self.state(index,"awaiting_approval")
            with self.cycle() as cycle,patch.object(researchctl,"gate_errors",side_effect=AssertionError("legacy checks are optional")):
                result=autopilot.run_stage("demo","Read the source and refine the argument")
            self.assertEqual(result["status"],"work_completed")
            self.assertEqual(cycle.call_count,1)
            current=researchctl.load_state("demo")
            self.assertEqual(current["approvals"],original["approvals"])
            self.assertEqual(current["approved_gates"],original["approved_gates"])

    def test_explicit_work_can_revise_a_previously_completed_project(self):
        old=self.state(6,"submission_ready")
        with self.cycle() as cycle:
            result=autopilot.run_stage("demo","Revise the limitations after new evidence")
        self.assertEqual(result["status"],"work_completed")
        self.assertEqual(cycle.call_args.args[1],"writing-and-review")
        self.assertEqual(researchctl.load_state("demo")["approvals"],old["approvals"])

    def test_start_defaults_to_one_paper_and_resume_preserves_existing_material(self):
        with self.cycle() as cycle:
            self.assertEqual(autopilot.main(["start","--project","new-project","--context","Investigate a question"]),0)
            project=researchctl.project_dir("new-project")
            self.assertEqual(researchctl.load_state("new-project")["paper_count"],1)
            write(project/"results/retained.json",{"negative_result":True})
            before=(project/"results/retained.json").read_bytes()
            self.assertEqual(autopilot.main(["resume","--project","new-project"]),0)
        self.assertEqual(cycle.call_count,2)
        self.assertEqual((project/"results/retained.json").read_bytes(),before)
        self.assertEqual(model_spend.read(project)["authorized_ceiling_cny"],0)

    def test_selecting_another_paper_does_not_touch_first_paper_results(self):
        researchctl.add_paper(SimpleNamespace(project="demo",question="Another related question",select=False))
        (self.project/"papers/P01/manuscript/draft.md").write_text("retained")
        with self.cycle() as cycle:
            autopilot.run_stage("demo","Develop a counterexample",paper_id="P02",stage="experiment-design")
        self.assertEqual(researchctl.load_state("demo")["active_paper"],"P02")
        self.assertEqual((self.project/"papers/P01/manuscript/draft.md").read_text(),"retained")
        self.assertEqual(cycle.call_args.args[1],"experiment-design")

    def test_optional_review_and_planning_are_explicit(self):
        with self.cycle() as cycle:
            autopilot.run_stage("demo","Review this proof",planning=True,review=True,remediate=True,source_paths=["program/topic.md"])
        self.assertTrue(cycle.call_args.kwargs["planning"])
        self.assertTrue(cycle.call_args.kwargs["review"])
        self.assertTrue(cycle.call_args.kwargs["remediate"])
        self.assertEqual(cycle.call_args.kwargs["source_paths"],["program/topic.md"])

    def test_operation_and_review_findings_do_not_create_gate_decisions(self):
        for manifest in ({"paid_model_cycle":False},{"research_decision":{"errors":["A claim lacks support"],"review_errors":[]}}):
            with self.cycle(manifest):result=autopilot.run_stage("demo","Inspect the evidence")
            self.assertIn(result["status"],{"controlled_step","needs_work"})
            self.assertEqual(researchctl.load_state("demo")["approvals"],[])

    def test_transport_failure_has_one_attempt_and_retains_project_budget(self):
        original=(self.project/model_spend.FILE).read_bytes()
        with patch.object(api,"run_cycle",side_effect=RuntimeError("ambiguous response")) as cycle:
            with self.assertRaisesRegex(RuntimeError,"ambiguous response"):autopilot.run_stage("demo","A bounded task")
        self.assertEqual(cycle.call_count,1)
        self.assertEqual((self.project/model_spend.FILE).read_bytes(),original)
        self.assertEqual(researchctl.load_state("demo")["approved_gates"],[])
