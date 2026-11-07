"""Scientific drafting keeps real checks and cannot replace final submission review."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import api_orchestrator as api, research_methods, research_phase as phases
from scripts import researchctl, review_receipts
from scripts.research_artifacts import read, write
from tests.research_cycle_fixtures import pending_decision
from tests import test_paper_execution as fixtures


class WritingPhaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project=Path(self.temp.name)/"project"
        self.state={"stage":"writing-and-review","gate":"G5","status":"awaiting_work",
                    "active_paper":"P01","paper_count":1,"approved_gates":[],"approvals":[],"history":[]}
        write(self.project/"state/run.json",self.state)
        write(self.project/"papers/P01/paper-contract.json",{"paper_id":"P01"})

    def test_default_scientific_and_explicit_submission_preserve_frozen_contract(self):
        contract=(self.project/"papers/P01/paper-contract.json").read_bytes()
        self.assertEqual(phases.writing_phase(self.project),"scientific")
        self.assertEqual(phases.disposition_stage(self.project,"writing-and-review"),"scientific-writing")
        self.assertFalse(phases.enter_submission(self.project,[phases.SUBMISSION_PENDING,"Unresolved result"]))
        self.assertTrue(phases.enter_submission(self.project,[phases.SUBMISSION_PENDING]))
        self.assertEqual(phases.writing_phase(self.project),"submission")
        self.assertEqual((self.project/"papers/P01/paper-contract.json").read_bytes(),contract)
        state=read(self.project/"state/run.json")
        self.assertEqual((state["gate"],state["status"],state["approvals"]),("G5","awaiting_work",[]))
        self.assertEqual(state["history"][-1]["event"],"submission_preparation_started")

    def test_legacy_sealed_paper_retains_submission_requirements(self):
        self.state["approved_gates"]=["G5:P01"]
        write(self.project/"state/run.json",self.state)
        self.assertTrue(phases.requires_submission(self.project))
        for invalid in ("unknown", [], {}):
            self.state["writing_phases"]={"P01":invalid}
            write(self.project/"state/run.json",self.state)
            with self.assertRaisesRegex(ValueError,"writing_phase"):
                phases.writing_phase(self.project)

    def test_scientific_guidance_retains_writer_reviewer_and_defers_submission_tables(self):
        with patch("scripts.model_runtime.call",side_effect=AssertionError("No paid calls")):
            science=research_methods.stage_context("writing-and-review","writer",project=self.project)
            critic=research_methods.stage_context("writing-and-review","critic",project=self.project)
        self.assertIn("SELECTED CCFA SOURCE ccf-paper-writer/SKILL.md",science)
        self.assertIn("SELECTED CCFA SOURCE ccf-paper-reviewer/SKILL.md",critic)
        self.assertNotIn("LOCAL COMPLETE COVERAGE",science)
        self.assertNotIn("Required criterion IDs and questions by article type",science)
        self.assertIn("facts, references, statistical interpretation and argument",science)
        self.state["writing_phases"]={"P01":"submission"}
        write(self.project/"state/run.json",self.state)
        submission=research_methods.stage_context("writing-and-review","writer",project=self.project)
        self.assertNotIn("LOCAL COMPLETE COVERAGE",submission)
        self.assertIn("CFH/H/AD, style/hygiene and numeric scores are C observations",submission)
        self.assertIn("submission-review",submission)

    def seal(self, *, decision):
        token="scientific-review-fixture"
        if decision:pending_decision(self.project,"writing-and-review",token,"P01")
        audit={"verdict":"pass-with-conditions",**{key:[] for key in review_receipts.FIELDS-{"verdict"}}}
        identity={"provider":"fixture","family":"anthropic","requested_model":"claude-fixture",
                  "reported_model":"claude-fixture","completion_status":"completed","cache_hit":False}
        with patch.dict(os.environ,{"DR_OS_CLOUD_EXECUTOR":"1"}):
            for phase in ("initial","final"):
                target=self.project/f"reviews/independent/{phase}.json"
                write(target,audit)
                review_receipts.seal_phase(self.project,stage="writing-and-review",run_id=token,phase=phase,
                    audit_path=target,prompt="Independently assess the actual source-bound scientific decision.",
                    identity=identity,writer_family="openai",materials=review_receipts.material_snapshot(self.project,"writing-and-review","P01"),
                    notes=[] if phase=="final" else None,cycle_required=True)

    def test_new_native_cycle_cannot_pass_without_its_decision(self):
        self.seal(decision=False)
        self.assertTrue(any("research-notebook" in error or "research cycle" in error
                            for error in review_receipts.validate_gate(self.project,"G5","P01")))
        self.assertTrue((self.project/"state/review-receipts/G5-P01/scientific-review-fixture/final.json").is_file())

    def test_scientific_receipts_do_not_approve_submission(self):
        self.seal(decision=True)
        self.assertEqual(review_receipts.validate_gate(self.project,"G5","P01"),[])
        self.state["writing_phases"]={"P01":"submission"}
        write(self.project/"state/run.json",self.state)
        self.assertTrue(review_receipts.validate_gate(self.project,"G5","P01"))
        self.assertFalse(api.remediation_required({"verdict":"pass-with-conditions",**{key:[] for key in review_receipts.FIELDS-{"verdict"}}},"writing-and-review",[]))

    def test_g5_never_accepts_resumed_exploratory_plan_or_preregistration(self):
        case=fixtures.IndependentPaperTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.enable()
        case.state.update(stage="writing-and-review",gate="G5",stage_index=5,status="awaiting_work")
        case.save()
        for source in ("plan","preregistration"):
            with self.subTest(source=source):
                write(case.project/"experiments/papers/P01/plan.json",{"research_phase":"exploratory" if source=="plan" else "confirmatory","runs":[]})
                write(case.project/"papers/P01/preregistration.json",{"research_phase":"exploratory" if source=="preregistration" else "confirmatory"})
                with patch.object(researchctl,"PROJECTS_ROOT",case.root):
                    errors=researchctl.gate_errors("demo","G5")
                self.assertTrue(any("exploratory observations cannot enter G5" in error for error in errors))
