from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import figure_lineage as lineage,figure_provenance,output_provenance
from scripts.research_artifacts import read,write,record,sha
from tests.figure_lineage_fixtures import sealed_run


class FigureLineageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.project=Path(self.temp.name)/"fixture"
        self.run,self.approval,self.receipt=sealed_run(self.project)

    def test_direct_output_binds_exact_plan_attempt_and_recorded_bytes(self):
        result=lineage.lineage(self.project,"P01",["results/metrics.csv"],["r1"])
        seal=result["runs"][0]
        self.assertEqual(seal["attempt_id"],"r1-attempt-001")
        self.assertEqual(seal["plan_sha256"],sha(self.project/"experiments/plan.json"))
        self.assertEqual(seal["outputs"][0]["sha256"],sha(self.project/"results/metrics.csv"))
        (self.project/"results/fabricated.csv").write_text("group,value\nA,9000\n")
        with self.assertRaisesRegex(ValueError,"Unsealed"):
            lineage.lineage(self.project,"P01",["results/fabricated.csv"],["r1"])
        with self.assertRaisesRegex(ValueError,"approved run for this paper"):
            lineage.lineage(self.project,"P02",["results/metrics.csv"],["r1"])

    def test_registry_only_success_without_executor_receipt_is_rejected(self):
        (self.project/"experiments/runs/r1-attempt-001/run.json").unlink()
        with self.assertRaises(ValueError):lineage.lineage(self.project,"P01",["results/metrics.csv"],["r1"])

    def test_tampered_output_and_unapproved_plan_are_rejected(self):
        (self.project/"results/metrics.csv").write_text("group,value\nA,500\n")
        with self.assertRaisesRegex(ValueError,"Sealed plotted output changed"):
            lineage.lineage(self.project,"P01",["results/metrics.csv"],["r1"])
        sealed_run(self.project)
        plan=self.project/"experiments/plan.json";value=read(plan);value["unapproved"]=True;write(plan,value)
        with self.assertRaisesRegex(ValueError,"G3 plan approval"):
            lineage.lineage(self.project,"P01",["results/metrics.csv"],["r1"])

    def test_replayable_group_mean_receipt_and_tamper_detection(self):
        transform={"operation":"group_mean","sources":["results/metrics.csv"],"columns":["value"],"group_by":["group"]}
        output="papers/P01/figures/source-data/means.csv"
        with patch.dict(os.environ,{"DR_OS_CLOUD_EXECUTOR":"1"}):
            receipt=lineage.derive(self.project,"P01",output,transform,["r1"])
        self.assertEqual((self.project/output).read_text(),"group,value\nA,3\nB,8\n")
        self.assertEqual(lineage.lineage(self.project,"P01",[output],["r1"])["inputs"][0]["kind"],"derived_csv")
        (self.project/output).write_text("group,value\nA,30\nB,80\n")
        with self.assertRaisesRegex(ValueError,"stale"):
            lineage.lineage(self.project,"P01",[output],["r1"])
        receipt["output"]["sha256"]=sha(self.project/output)
        path=lineage.receipt_path(self.project,output);write(path,receipt);record(self.project,[path],lineage.MODULE)
        with self.assertRaisesRegex(ValueError,"deterministic recomputation"):
            lineage.lineage(self.project,"P01",[output],["r1"])

    def test_native_json_study_output_can_be_projected_without_inventing_values(self):
        sealed_run(self.project,output="results/meta.json",body=json.dumps({"outcomes":[{"id":"O1","summary":{"estimate":2.5,"ci_low":1.2}}]}))
        output="papers/P01/figures/source-data/meta.csv"
        transform={"operation":"json_rows","sources":["results/meta.json"],"columns":["id","summary.estimate","summary.ci_low"],"group_by":[],"record_path":"outcomes"}
        with patch.dict(os.environ,{"DR_OS_CLOUD_EXECUTOR":"1"}):lineage.derive(self.project,"P01",output,transform,["r1"])
        self.assertIn("O1,2.5,1.2",(self.project/output).read_text())
        self.assertEqual(len(lineage.lineage(self.project,"P01",[output],["r1"])["runs"]),1)

    def supplemental(self):
        namespace="experiments/supplemental/P01/R001/s001"
        child=self.project/namespace
        _,approval,_=sealed_run(child,run_id="review-run")
        control_path=self.project/"state/supplemental-experiments/P01/R001/s001.json"
        files={path.relative_to(child).as_posix():sha(path) for path in child.rglob("*") if path.is_file() and path.relative_to(child).parts[0] in {"experiments","results"}}
        control={"schema_version":"1.0","paper_id":"P01","round_id":"R001","scope_id":"s001","scope_root":namespace,
            "child_state_sha256":sha(child/"state/run.json"),"approval":approval,"proposal":{
                "original_plan_sha256":sha(self.project/"experiments/plan.json"),"original_preregistration_sha256":sha(self.project/"papers/P01/preregistration.json")},
            "confirmation":{"actor":"Synthetic reviewer","source_run_id":"123","cloud_review_sha256":"a"*64,"files":files}}
        write(control_path,control);record(self.project,[control_path],"scripts/supplemental_experiments.py")
        return child,control_path,control,namespace+"/results/metrics.csv","supplemental/P01/R001/s001/review-run"

    def test_confirmed_supplemental_namespace_passes_and_stale_or_unconfirmed_fails(self):
        child,path,control,data,run=self.supplemental()
        result=lineage.lineage(self.project,"P01",[data],[run])
        self.assertEqual(result["runs"][0]["scope"]["path"],path.relative_to(self.project).as_posix())
        with self.assertRaisesRegex(ValueError,"another paper"):
            lineage.lineage(self.project,"P02",[data],[run])
        control["confirmation"]=None;write(path,control);record(self.project,[path],"scripts/supplemental_experiments.py")
        with self.assertRaisesRegex(ValueError,"scientific confirmation"):
            lineage.lineage(self.project,"P01",[data],[run])
        child,path,control,data,run=self.supplemental()
        (child/"results/metrics.csv").write_text("group,value\nA,9\n")
        with self.assertRaisesRegex(ValueError,"Confirmed supplemental source changed"):
            lineage.lineage(self.project,"P01",[data],[run])

    def test_native_publication_renderer_registers_only_sealed_data(self):
        from scripts.publication_figures import render
        sealed_run(self.project,output="results/plot.csv",body="group,value\nA,2\nB,4\nC,8\n")
        paper=self.project/"papers/P01";(paper/"figures").mkdir(parents=True)
        spec=paper/"figures/result.spec.json"
        write(spec,{"schema_version":"1.0","data":"results/plot.csv","output_stem":"papers/P01/figures/result","style":"technical","formats":["svg","pdf"],"dpi":300,
            "caption":"Synthetic executor fixture.","alt_text":"Recorded group values.","claim_ids":["FIXTURE"],"panels":[{"kind":"bar","x":"group","y":"value","xlabel":"Group","ylabel":"Value"}]})
        report=render(self.project,spec)
        output_provenance.record_model_writes(self.project,[spec],family="openai",provider="codex",model="fixture",role="writer",run_id="fixture")
        self.assertEqual({output["format"] for output in report["outputs"]},{"svg","pdf"})
        for output in report["outputs"]:
            figure_provenance.record_figure(self.project,"P01",output["path"],"data_chart",report["renderer_wrapper"]["path"],["results/plot.csv"],["r1"],spec.relative_to(self.project).as_posix(),"Synthetic inspector")
        registry=read(paper/"figures/figure-provenance.json")
        self.assertEqual({row["figure_path"] for row in registry["figures"]},{output["path"] for output in report["outputs"]})
        for row in registry["figures"]:
            self.assertEqual(row["source_lineage"]["runs"][0]["attempt_id"],"r1-attempt-001")
            self.assertEqual(row["source_lineage"]["runs"][0]["plan_sha256"],sha(self.project/"experiments/plan.json"))
            self.assertEqual(row["inputs"],[{"path":"results/plot.csv","sha256":sha(self.project/"results/plot.csv")}])
        self.assertEqual(figure_provenance.validate_figure_provenance(self.project,paper),[])


if __name__=="__main__":unittest.main()
