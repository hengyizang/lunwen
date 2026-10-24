from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from scripts import editable_figures, output_provenance, research_diagrams
from scripts.publication_figures import FigureSpecError, sha256_file


class EditableFigureTests(unittest.TestCase):
    def fixture(self, directory: str, formats: list[str] | None = None):
        project=Path(directory)/"study"
        figures=project/"papers/P01/figures";figures.mkdir(parents=True)
        method=project/"papers/P01/method.md";method.write_text("# Method\nThe input passes through the model to the output.\n",encoding="utf-8")
        ir={"schema_version":"1.0","type":"workflow","title":"Method overview","caption":"Method flow from input to output.","alt_text":"Input data pass through a model to produce an output.","claim_ids":["C1"],"output_stem":"papers/P01/figures/method","nodes":[{"id":"input","label":"Input data","kind":"input","layer":0,"rank":0},{"id":"model","label":"Adaptive model","kind":"model","layer":1,"rank":0},{"id":"output","label":"Output values","kind":"output","layer":2,"rank":0}],"edges":[{"from":"input","to":"model","kind":"data","label":"observations"},{"from":"model","to":"output","kind":"control","label":"prediction"}]}
        source=figures/"method.spec.json";source.write_text(json.dumps(ir),encoding="utf-8")
        output_provenance.record_model_writes(project,[source],family="openai",provider="codex",model="fixture",role="method-spec",run_id="test")
        request={"schema_version":"1.0","diagram_spec":source.relative_to(project).as_posix(),"expected_source_sha256":sha256_file(source),"formats":formats or ["svg","drawio"],"evidence":[{"path":method.relative_to(project).as_posix(),"sha256":sha256_file(method),"locator":"L2"}],"reference_notes":[{"source_url":"https://example.org/paper","purpose":"layout_reference","rights_status":"unverified","note":"Compare visual hierarchy; no image or scientific content reused."}]}
        request_path=figures/"editable-request.json";request_path.write_text(json.dumps(request),encoding="utf-8")
        return project,source,request_path,ir,request

    def update_source(self,project,source,request_path,ir,request):
        source.write_text(json.dumps(ir),encoding="utf-8")
        output_provenance.record_model_writes(project,[source],family="openai",provider="codex",model="fixture",role="method-spec",run_id="changed")
        request["expected_source_sha256"]=sha256_file(source);request_path.write_text(json.dumps(request),encoding="utf-8")

    def test_svg_and_drawio_are_native_objects_with_original_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            project,source,request_path,ir,_=self.fixture(directory)
            report=editable_figures.export(project,request_path)
            svg_path=project/next(row["path"] for row in report["outputs"] if row["format"]=="svg")
            svg=ET.parse(svg_path).getroot();namespace={"s":"http://www.w3.org/2000/svg"}
            self.assertEqual(len(svg.findall(".//s:rect",namespace)),3)
            self.assertEqual(len(svg.findall(".//s:line",namespace)),2)
            self.assertGreaterEqual(len(svg.findall(".//s:text",namespace)),6)
            self.assertFalse(svg.findall(".//s:image",namespace));self.assertFalse(svg.findall(".//s:script",namespace))
            drawio=ET.parse(project/next(row["path"] for row in report["outputs"] if row["format"]=="drawio")).getroot()
            cells=drawio.findall(".//mxCell");edges=[row for row in cells if row.get("edge")=="1"]
            self.assertEqual([(row.get("source"),row.get("target")) for row in edges],[("node-input","node-model"),("node-model","node-output")])
            self.assertTrue(any(row.get("value")=="Adaptive model" and row.get("vertex")=="1" for row in cells))
            layout=json.loads((project/report["layout"]["path"]).read_text())
            self.assertEqual(layout["original_layout"],{key:list(value) for key,value in research_diagrams.layout(ir).items()})
            self.assertEqual((project/report["source_snapshot"]["path"]).read_bytes(),source.read_bytes())
            self.assertTrue(report["human_review_required"]);self.assertEqual(report["scientific_validation"],"not_established")
            self.assertEqual(report["paid_calls"],0);self.assertEqual(report["reference_notes"][0]["rights_status"],"unverified")
            self.assertFalse((project/"papers/P01/figures/figure-provenance.json").exists())
            self.assertEqual(output_provenance.current_origin(project,project/report["renderer"]["path"])["status"],"tracked")
            receipt=project/"papers/P01/figures/method.editable-export.json"
            self.assertEqual(editable_figures.verify_export(project,receipt),report)
            self.assertEqual(editable_figures.export(project,request_path),report)

    def test_pptx_contains_live_text_native_nodes_and_attached_connectors(self):
        with tempfile.TemporaryDirectory() as directory:
            project,_,request_path,_,_=self.fixture(directory,["pptx"])
            report=editable_figures.export(project,request_path)
            with ZipFile(project/report["outputs"][0]["path"]) as archive:
                slide=ET.fromstring(archive.read("ppt/slides/slide1.xml"))
                ns={"p":"http://schemas.openxmlformats.org/presentationml/2006/main","a":"http://schemas.openxmlformats.org/drawingml/2006/main"}
                self.assertEqual(len(slide.findall(".//p:cxnSp",ns)),2)
                self.assertEqual(len(slide.findall(".//a:stCxn",ns)),2)
                self.assertEqual(len(slide.findall(".//a:endCxn",ns)),2)
                self.assertEqual(len(slide.findall(".//a:tailEnd",ns)),2)
                self.assertIn("Adaptive model",[element.text for element in slide.findall(".//a:t",ns)])
                self.assertGreaterEqual(len(slide.findall(".//p:sp",ns)),6)
                self.assertFalse(slide.findall(".//p:pic",ns))
                self.assertFalse(any(name.startswith("ppt/media/") for name in archive.namelist()))

    def test_changed_source_hash_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            project,source,request_path,_,_=self.fixture(directory)
            source.write_text(source.read_text()+" ")
            with self.assertRaisesRegex(FigureSpecError,"source hash is stale"):editable_figures.export(project,request_path)
            self.assertFalse((project/"papers/P01/figures/method.editable.svg").exists())

    def test_current_claude_source_cannot_be_laundered_by_export(self):
        with tempfile.TemporaryDirectory() as directory:
            project,source,request_path,_,_=self.fixture(directory)
            output_provenance.record_model_writes(project,[source],family="anthropic",provider="claude",model="fixture",role="spec",run_id="c")
            with self.assertRaises(output_provenance.ProvenanceError):editable_figures.export(project,request_path)

    def test_invalid_edge_and_result_chart_are_rejected(self):
        for change in ("edge","chart"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                project,source,request_path,ir,request=self.fixture(directory)
                if change=="edge":ir["edges"][0]["to"]="missing"
                else:ir["type"]="data_chart"
                self.update_source(project,source,request_path,ir,request)
                with self.assertRaises(FigureSpecError):editable_figures.export(project,request_path)

    def test_invalid_or_stale_evidence_blocks_export(self):
        for change in ("stale","empty","escape"):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                project,_,request_path,_,request=self.fixture(directory)
                if change=="stale":request["evidence"][0]["sha256"]="0"*64
                elif change=="empty":request["evidence"]=[]
                else:request["evidence"][0]["path"]="../outside.md"
                request_path.write_text(json.dumps(request),encoding="utf-8")
                with self.assertRaises(FigureSpecError):editable_figures.export(project,request_path)

    def test_verification_rejects_changed_source_evidence_or_output(self):
        for change in ("source","evidence","output","receipt"):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                project,source,request_path,_,_=self.fixture(directory)
                report=editable_figures.export(project,request_path);receipt=project/"papers/P01/figures/method.editable-export.json"
                target={"source":source,"evidence":project/report["evidence"][0]["path"],"output":project/report["outputs"][0]["path"],"receipt":receipt}[change]
                target.write_bytes(target.read_bytes()+b" ")
                with self.assertRaises((FigureSpecError,output_provenance.ProvenanceError)):editable_figures.verify_export(project,receipt)

    def test_new_request_needs_exact_replacement_receipt_and_preserves_manual_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            project,source,request_path,ir,request=self.fixture(directory)
            report=editable_figures.export(project,request_path);receipt=project/"papers/P01/figures/method.editable-export.json"
            ir["nodes"][1]["label"]="Updated model";self.update_source(project,source,request_path,ir,request)
            with self.assertRaisesRegex(FigureSpecError,"replace_expected_export_sha256"):editable_figures.export(project,request_path)
            request["replace_expected_export_sha256"]=sha256_file(receipt);request_path.write_text(json.dumps(request),encoding="utf-8")
            path=project/report["outputs"][0]["path"];original=path.read_bytes();path.write_bytes(original+b" manual")
            with self.assertRaisesRegex(FigureSpecError,"existing export hash is stale"):editable_figures.export(project,request_path)
            path.write_bytes(original);updated=editable_figures.export(project,request_path)
            self.assertIn("Updated model",(project/updated["outputs"][0]["path"]).read_text())

    def test_markup_remains_plain_text_and_never_active_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            project,source,request_path,ir,request=self.fixture(directory)
            ir["nodes"][1]["label"]="<script> & data";self.update_source(project,source,request_path,ir,request)
            report=editable_figures.export(project,request_path)
            svg=(project/report["outputs"][0]["path"]).read_text()
            self.assertIn("&lt;script&gt;",svg);self.assertNotIn("<script>",svg)
            self.assertNotIn("http://example.org",svg)

    def test_xml_control_character_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project,source,request_path,ir,request=self.fixture(directory)
            ir["nodes"][1]["label"]="Model\u0000label";self.update_source(project,source,request_path,ir,request)
            with self.assertRaisesRegex(FigureSpecError,"control characters"):editable_figures.export(project,request_path)

    def test_export_formats_are_closed_and_unknown_fields_rejected(self):
        for change in ("format","unknown","duplicate"):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                project,_,request_path,_,request=self.fixture(directory)
                if change=="format":request["formats"]=["png"]
                elif change=="duplicate":request["formats"]=["svg","svg"]
                else:request["approve"]=True
                request_path.write_text(json.dumps(request),encoding="utf-8")
                with self.assertRaises(FigureSpecError):editable_figures.export(project,request_path)

    def test_shared_style_is_applied_to_real_objects_and_stale_style_is_rejected(self):
        from scripts import figure_story
        with tempfile.TemporaryDirectory() as directory:
            project,source,request_path,ir,request=self.fixture(directory,["svg","pptx","drawio"])
            style=figure_story.default_style();style["node_fills"]["model"]="#EECCAA";style["font_family"]="DejaVu Sans"
            figure_story.execute(project,"style_prepare",style)
            style_path=project/"program/figure-visual-style.json"
            ir["style_ref"]={"path":"program/figure-visual-style.json","sha256":sha256_file(style_path)}
            self.update_source(project,source,request_path,ir,request)
            report=editable_figures.export(project,request_path)
            svg=(project/report["outputs"][0]["path"]).read_text()
            self.assertIn("#EECCAA",svg);self.assertIn("DejaVu Sans",svg)
            with ZipFile(project/report["outputs"][1]["path"]) as archive:
                slide=archive.read("ppt/slides/slide1.xml").decode()
                self.assertIn("EECCAA",slide);self.assertIn("DejaVu Sans",slide)
            drawio=(project/report["outputs"][2]["path"]).read_text()
            self.assertIn("#EECCAA",drawio);self.assertIn("DejaVu Sans",drawio)
            style_path.write_text(style_path.read_text()+" ",encoding="utf-8")
            with self.assertRaises((FigureSpecError,ValueError,output_provenance.ProvenanceError)):
                editable_figures.verify_export(project,project/"papers/P01/figures/method.editable-export.json")

    def test_execution_refuses_an_undeclared_local_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            project,_,request_path,_,_=self.fixture(directory)
            with patch.dict(os.environ,{"GITHUB_ACTIONS":"false","DR_OS_CLOUD_EXECUTOR":"0"}):
                with self.assertRaisesRegex(FigureSpecError,"cloud executor"):editable_figures.export(project,request_path)

    def test_final_figure_validation_rechecks_auxiliary_export_without_auto_approval(self):
        from scripts.figure_provenance import record_figure,validate_figure_provenance
        with tempfile.TemporaryDirectory() as directory:
            project,source,request_path,_,_=self.fixture(directory,["svg"])
            report=editable_figures.export(project,request_path);paper=project/"papers/P01"
            self.assertTrue(any("unregistered final figures" in item for item in validate_figure_provenance(project,paper)))
            record_figure(project,"P01",report["outputs"][0]["path"],"conceptual_diagram",report["renderer"]["path"],
                          [row["path"] for row in report["evidence"]],[],report["source"]["path"],"Researcher")
            self.assertEqual(validate_figure_provenance(project,paper),[])
            # Even a newly recorded current output cannot hide changed source
            # evidence from the native final-figure check.
            evidence=project/report["evidence"][0]["path"];evidence.write_text(evidence.read_text()+"Changed method.\n")
            self.assertTrue(any("editable export is stale" in item for item in validate_figure_provenance(project,paper)))


if __name__=="__main__":unittest.main()
