from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import output_provenance
from scripts.figure_provenance import record_figure,validate_figure_provenance,register_rendered_figures


class FigureProvenanceTests(unittest.TestCase):
    def test_data_chart_requires_current_inputs_renderer_and_successful_run(self)->None:
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)/"study";paper=project/"papers"/"P01";(paper/"figures").mkdir(parents=True);(project/"analysis").mkdir();(project/"results").mkdir();(project/"experiments").mkdir()
            renderer=project/"analysis"/"chart.py";renderer.write_text("# deterministic renderer",encoding="utf-8");output_provenance.record_model_writes(project,[renderer],family="openai",provider="codex",model="test",role="analysis-code",run_id="r")
            data=project/"results"/"metrics.csv";data.write_text("x,y\n1,2\n",encoding="utf-8")
            figure=paper/"figures"/"result.png";figure.write_bytes(b"deterministic fixture")
            from tests.figure_lineage_fixtures import sealed_run
            sealed_run(project)
            record_figure(project,"P01","papers/P01/figures/result.png","data_chart","analysis/chart.py",["results/metrics.csv"],["r1"],language_checked_by="Researcher")
            self.assertEqual(validate_figure_provenance(project,paper),[])
            self.assertEqual(output_provenance.current_origin(project,paper/"figures"/"figure-provenance.json")["status"],"tracked")
            data.write_text("x,y\n1,3\n",encoding="utf-8")
            self.assertTrue(any("input hash is stale" in error for error in validate_figure_provenance(project,paper)))

    def test_figure_without_human_label_uses_machine_review(self)->None:
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)/"study";paper=project/"papers"/"P01";(paper/"figures").mkdir(parents=True);(project/"analysis").mkdir();renderer=project/"analysis"/"chart.py";renderer.write_text("# chart",encoding="utf-8");figure=paper/"figures"/"chart.svg";figure.write_text("<svg/>",encoding="utf-8");output_provenance.record_model_writes(project,[renderer],family="openai",provider="codex",model="test",role="renderer",run_id="r")
            record_figure(project,"P01","papers/P01/figures/chart.svg","conceptual_diagram","analysis/chart.py",[],[])
            registry=json.loads((paper/"figures/figure-provenance.json").read_text())
            self.assertEqual(registry["figures"][0]["review_kind"],"automated")
            self.assertNotIn("language_checked_by",registry["figures"][0])
            self.assertTrue(any("automated visual" in error for error in validate_figure_provenance(project,paper)))

    def test_native_render_registers_only_executor_sealed_data_without_human_name(self)->None:
        from scripts.research_artifacts import write,sha
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)/"study";paper=project/"papers/P01";figures=paper/"figures";figures.mkdir(parents=True)
            from tests.figure_lineage_fixtures import sealed_run
            sealed_run(project)
            renderer=project/"analysis/chart.py";renderer.write_text("# synthetic renderer\n",encoding="utf-8")
            figure=figures/"chart.png";figure.write_bytes(b"synthetic rendered pixels")
            spec=figures/"chart.json";write(spec,{"synthetic":True})
            output_provenance.record_model_writes(project,[renderer,spec],family="other",provider="fixture",model="fixture",role="fixture",run_id="fixture")
            ref=lambda path:{"path":path.relative_to(project).as_posix(),"sha256":sha(path)}
            receipt=figures/"chart.render-receipt.json"
            write(receipt,{"status":"pass","execution":{"mode":"cloud"},"outputs":[ref(figure)]})
            output_provenance.record_model_writes(project,[receipt],family="other",provider="publication-figure-renderer",model="scripts/publication_figures.py",role="render-receipt",run_id="fixture")
            report={"render_receipt":ref(receipt),"renderer_wrapper":ref(renderer),"outputs":[ref(figure)],"spec":ref(spec),"data":[ref(project/"results/metrics.csv")]}
            self.assertEqual(register_rendered_figures(project,report),["papers/P01/figures/chart.png"])
            row=json.loads((figures/"figure-provenance.json").read_text())["figures"][0]
            self.assertEqual(row["review_kind"],"automated");self.assertEqual(row["source_run_ids"],["r1"])
            self.assertNotIn("language_checked_by",row)
            (project/"results/metrics.csv").write_text("changed\n",encoding="utf-8")
            with self.assertRaises(ValueError):register_rendered_figures(project,report)


if __name__=="__main__":unittest.main()
