"""Paper isolation and total-cost controls; synthetic software fixtures only."""
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts import artifact_ownership, paper_execution as execution, research_quality as quality, researchctl
from scripts.research_artifacts import write


class IndependentPaperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "demo"
        self.state = {"schema_version":"2.0", "project":"demo", "stage_index":2,
            "stage":"paper-architecture", "gate":"G2", "status":"approved", "paper_count":2,
            "active_paper":"P01", "paper_statuses":{"P01":"active","P02":"planned"},
            "approved_gates":["G1","G2"],"approvals":[],"history":[]}
        self.save()
        for paper in ("P01","P02"):
            write(self.project / "papers" / paper / "paper-contract.json",
                  {"paper_id":paper,"datasets":[],"independence":{"unique_claim_ids":[paper+"-C1"]}})
        self.plan={"schema_version":"1.0","status":"ready_for_review","runs":[
            {"run_id":paper+"-main","paper_id":paper,"expected_outputs":["results/"+paper+"/value.json"]}
            for paper in ("P01","P02")]}
        write(self.project / "experiments/plan.json",self.plan)
        write(self.project / "experiments/budget.json",{"status":"ready_for_review","hard_ceiling_usd":10})
        data=self.project/"data/datasets.jsonl"
        data.parent.mkdir(parents=True)
        data.write_text("",encoding="utf-8")

    def save(self):
        write(self.project/"state/run.json",self.state)

    def enable(self):
        execution.enable(self.project)
        self.state.update(paper_execution_mode="independent",stage_index=3,stage="experiment-design",gate="G3",status="awaiting_work")
        self.save()

    def test_g2_advance_starts_one_paper_with_lossless_separate_plans(self):
        original=(self.project/"experiments/plan.json").read_bytes()
        with patch.object(researchctl,"PROJECTS_ROOT",self.root):
            self.state["approvals"]=[{"gate":"G2","artifact_sha256":researchctl.artifact_hash("demo","G2")}]
            self.save()
            with patch.object(researchctl,"gate_errors",return_value=[]):
                researchctl.advance(types.SimpleNamespace(project="demo"))
        state=execution.state(self.project)
        self.assertEqual((state["gate"],state["active_paper"],state["paper_execution_mode"]),("G3","P01","independent"))
        self.assertEqual((self.project/"experiments/plan.json").read_bytes(),original)
        self.assertEqual(json.loads(execution.artifact_path(self.project,"experiments/plan.json").read_text())["runs"],[self.plan["runs"][0]])

    def test_enable_preserves_master_and_does_not_authorize_execution(self):
        original=(self.project/"experiments/plan.json").read_bytes()
        self.enable()
        self.assertEqual((self.project/"experiments/plan.json").read_bytes(),original)
        for paper in ("P01","P02"):
            plan=json.loads(execution.artifact_path(self.project,"experiments/plan.json",paper).read_text())
            self.assertEqual(plan["runs"],[r for r in self.plan["runs"] if r["paper_id"]==paper])
        self.assertIsNone(execution.approval(self.project,"G3"))
        self.assertEqual(quality._paper_ids(self.project),["P01"])

    def test_a_second_unready_paper_does_not_block_the_active_paper_quality_scope(self):
        self.enable()
        with patch("scripts.study_routes.route",return_value="empirical"),patch("scripts.experiment_evidence.validate_plan",return_value=[]):
            errors=quality.validate_g3_quality(self.project)
        self.assertTrue(any("P01" in issue for issue in errors))
        self.assertFalse(any("P02" in issue for issue in errors),errors)

    def test_native_empirical_and_cleaning_outputs_remain_isolated_and_executable(self):
        self.enable()
        base={"run_id":"P01-analysis","paper_id":"P01","argv":["python3","analysis/empirical_runtime.py"]}
        self.assertEqual(execution.plan_errors(self.project,{"runs":[{**base,"expected_outputs":["papers/P01/results/main.json"]}]}),[])
        cleaning={**base,"argv":["python3","analysis/data_cleaning_runtime.py"],
            "expected_outputs":["data/processed/P01/clean.csv","reports/data-cleaning/P01/clean.json"]}
        self.assertEqual(execution.plan_errors(self.project,{"runs":[cleaning]}),[])
        for outputs in (["papers/P02/results/main.json"],["data/processed/P02/clean.csv"],["data/processed/shared.csv"],
                        ["results/P01/../P02/value.json"]):
            self.assertTrue(execution.plan_errors(self.project,{"runs":[{**cleaning,"expected_outputs":outputs}]}))
        self.assertTrue(execution.plan_errors(self.project,{"runs":[{**base,"expected_outputs":cleaning["expected_outputs"]}]}))

    def test_explicit_paper_reads_survive_switching_the_active_paper(self):
        self.enable()
        execution.prepare_datasets(self.project)
        for name in ("power-analysis.json","experiment-evidence-plan.json"):
            write(self.project/"papers/P01"/name,{"synthetic_software_fixture_only":True})
        paths=quality._preregistration_inputs(self.project,"P01")
        report={"schema_version":"1.0","paper_id":"P01","status":"frozen",
                "generated_by":"deterministic_local_control_plane","confirmatory_lock":True,
                "frozen_by":"deterministic_control_plane","human_confirmation":False,"confirmation_kind":"automated",
                "deviation_policy":"Retain original outcomes and label every subsequent deviation.",
                "files":[{"path":p.relative_to(self.project).as_posix(),"sha256":quality.sha256_file(p)} for p in paths]}
        self.assertEqual(quality.validate_preregistration(report,"P01",self.project),[])
        self.state["active_paper"]="P02"
        self.save()
        write(execution.artifact_path(self.project,"experiments/plan.json"),{"runs":[],"changed":"P02 draft"})
        (self.project/"data/datasets.jsonl").write_text('{"dataset_id":"later-paper"}\n',encoding="utf-8")
        self.assertEqual(quality.validate_preregistration(report,"P01",self.project),[])
        write(execution.artifact_path(self.project,"experiments/plan.json","P01"),{"runs":[],"changed":"unauthorized P01 edit"})
        self.assertTrue(any("changed" in e for e in quality.validate_preregistration(report,"P01",self.project)))

    def test_budget_counts_failed_attempts_from_every_paper(self):
        from scripts.supplemental_experiments import all_compute_cost
        self.enable()
        for paper,cost in (("P01",4),("P02",7)):
            path=execution.artifact_path(self.project,"experiments/registry.jsonl",paper)
            path.write_text(json.dumps({"status":"failed","estimated_cost_usd":cost})+"\n",encoding="utf-8")
        self.assertEqual(all_compute_cost(self.project),11)
        from scripts import experiment_runner as runner
        plan={"runs":[{"run_id":"P01-next","estimated_cost_usd":1}]}
        with patch.object(runner,"approved_plan",return_value=(plan,10)),patch.object(runner,"run_one",side_effect=AssertionError("the exhausted total cannot authorize a new attempt")):
            with self.assertRaisesRegex(runner.ExperimentError,"Budget ceiling exceeded"):
                runner._execute_locked(self.project,None,self.project/"state/test-lease.json")
        self.state["active_paper"]="P02";self.save()
        self.assertEqual(all_compute_cost(self.project),11)

    def test_a_paper_budget_copy_cannot_increase_the_legacy_shared_total(self):
        from scripts import experiment_runner as runner
        self.enable()
        self.state["active_paper"]="P02";self.save()
        draft={"status":"ready_for_review","hard_ceiling_usd":500}
        write(execution.artifact_path(self.project,"experiments/budget.json"),draft)
        self.assertEqual(runner.project_compute_ceiling(self.project,draft),10)

    def test_raw_data_remains_controller_owned_without_an_active_preregistration(self):
        self.enable()
        self.assertTrue(artifact_ownership.executor_owned(self.project,"data/raw/dataset.csv"))
        self.assertFalse(artifact_ownership.executor_owned(self.project,"analysis/next_probe.py"))

    def test_previous_paper_approval_is_not_an_execution_authority_for_the_next(self):
        self.enable()
        approval={"gate":"G3","paper_id":"P01","experiment_plan_sha256":"a"*64}
        self.state["approvals"]=[approval]
        self.state["approved_gates"].append("G3:P01")
        self.save()
        self.assertEqual(execution.approval(self.project,"G3"),approval)
        self.state["active_paper"]="P02";self.save()
        self.assertIsNone(execution.approval(self.project,"G3"))
        self.assertEqual(execution.approval(self.project,"G3","P01"),approval)

    def test_later_paper_data_and_followups_do_not_invalidate_the_first_paper_review(self):
        from scripts.review_receipts import material_snapshot
        self.enable()
        write(self.project/"papers/P01/paper-contract.json",{"paper_id":"P01","datasets":["d1"]})
        write(self.project/"data/quality/d1.json",{"dataset_id":"d1","fixture_only":True})
        before=material_snapshot(self.project,"writing-and-review","P01")
        self.state["active_paper"]="P02";self.save()
        write(self.project/"data/quality/d2.json",{"dataset_id":"d2","fixture_only":True})
        write(self.project/"data/manifests/d2.json",{"dataset_id":"d2","fixture_only":True})
        write(self.project/"experiments/supplemental/P02/I001/s001/papers/P02/protocol.json",{"fixture_only":True})
        self.assertEqual(material_snapshot(self.project,"writing-and-review","P01"),before)
        write(execution.artifact_path(self.project,"experiments/plan.json","P01"),{"changed":"P01 scientific input"})
        self.assertNotEqual(material_snapshot(self.project,"writing-and-review","P01"),before)

    def test_g3_and_g4_reviews_are_bound_to_the_actual_paper(self):
        from scripts import review_receipts
        self.enable()
        identity={"provider":"uuapi-anthropic","family":"anthropic","requested_model":"claude-synthetic",
                  "reported_model":"claude-synthetic","completion_status":"completed","cache_hit":False}
        audit={"verdict":"pass-with-conditions","fatal_findings":[],"major_findings":[],"minor_findings":[],
               "missing_evidence":[],"remediation_steps":[],"uncertainty":["Synthetic software receipt; no real scientific review."]}
        for gate,stage,index in (("G3","experiment-design",3),("G4","experiment-execution",4)):
            self.state.update(gate=gate,stage=stage,stage_index=index,active_paper="P01");self.save()
            with patch.dict("os.environ",{"DR_OS_CLOUD_EXECUTOR":"1"}):
                for phase in ("initial","final"):
                    path=self.project/f"reviews/independent/{gate}-P01-{phase}.json";write(path,audit)
                    review_receipts.seal_phase(self.project,stage=stage,run_id="scope-"+gate,phase=phase,audit_path=path,
                        prompt="Review the actual active paper only.",identity=identity,writer_family="openai",
                        materials=review_receipts.material_snapshot(self.project,stage,"P01"),notes=[] if phase=="final" else None)
            self.assertEqual(review_receipts.validate_gate(self.project,gate),[])
            self.state["active_paper"]="P02";self.save()
            self.assertTrue(review_receipts.validate_gate(self.project,gate))
            self.assertEqual(review_receipts.validate_gate(self.project,gate,"P01"),[])

    def test_unfrozen_current_inputs_are_editable_and_earlier_frozen_files_are_protected(self):
        self.enable()
        plan=execution.artifact_path(self.project,"experiments/plan.json","P01")
        frozen=plan.relative_to(self.project).as_posix()
        write(self.project/"papers/P01/preregistration.json",{"files":[{"path":frozen,"sha256":quality.sha256_file(plan)}]})
        self.state["active_paper"]="P02";self.save()
        self.assertTrue(artifact_ownership.executor_owned(self.project,frozen))
        self.assertFalse(artifact_ownership.executor_owned(self.project,"experiments/papers/P02/plan.json"))
        self.assertTrue(artifact_ownership.executor_owned(self.project,"experiments/papers/P02/registry.jsonl"))
        self.assertTrue(artifact_ownership.executor_owned(self.project,"experiments/papers/P02/datasets.jsonl"))

    def test_already_frozen_or_executed_protocol_is_never_silently_migrated(self):
        (self.project/"experiments/registry.jsonl").write_text('{"status":"failed"}\n',encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"executed or frozen"):
            execution.enable(self.project)

    def test_next_paper_returns_to_design_after_an_independent_paper_finishes(self):
        self.enable()
        self.state.update(stage_index=5,stage="writing-and-review",gate="G5",status="approved")
        self.state["approved_gates"].append("G5:P01")
        self.save()
        with patch.object(researchctl,"PROJECTS_ROOT",self.root):
            self.state["approvals"].append({"gate":"G5","paper_id":"P01","artifact_sha256":researchctl.artifact_hash("demo","G5")})
            self.save()
            with patch.object(researchctl,"gate_errors",return_value=[]):
                researchctl.advance(types.SimpleNamespace(project="demo"))
        state=execution.state(self.project)
        self.assertEqual((state["active_paper"],state["gate"],state["stage"]),("P02","G3","experiment-design"))
        self.assertEqual(state["paper_statuses"]["P01"],"submission_ready")

