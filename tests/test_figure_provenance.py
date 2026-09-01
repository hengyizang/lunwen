from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import output_provenance
from scripts.figure_provenance import record_figure,validate_figure_provenance


class FigureProvenanceTests(unittest.TestCase):
    def test_data_chart_requires_current_inputs_renderer_and_successful_run(self)->None:
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)/"study";paper=project/"papers"/"P01";(paper/"figures").mkdir(parents=True);(project/"analysis").mkdir();(project/"results").mkdir();(project/"experiments").mkdir()
            renderer=project/"analysis"/"chart.py";renderer.write_text("# deterministic renderer",encoding="utf-8");output_provenance.record_model_writes(project,[renderer],family="openai",provider="codex",model="test",role="analysis-code",run_id="r")
            data=project/"results"/"metrics.csv";data.write_text("x,y\n1,2\n",encoding="utf-8")
            figure=paper/"figures"/"result.png";figure.write_bytes(b"deterministic fixture")
            (project/"experiments"/"registry.jsonl").write_text(json.dumps({"run_id":"r1","paper_id":"P01","status":"succeeded"})+"\n",encoding="utf-8")
            record_figure(project,"P01","papers/P01/figures/result.png","data_chart","analysis/chart.py",["results/metrics.csv"],["r1"],language_checked_by="Researcher")
            self.assertEqual(validate_figure_provenance(project,paper),[])
            data.write_text("x,y\n1,3\n",encoding="utf-8")
            self.assertTrue(any("input hash is stale" in error for error in validate_figure_provenance(project,paper)))

    def test_figure_requires_named_english_label_check(self)->None:
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)/"study";paper=project/"papers"/"P01";(paper/"figures").mkdir(parents=True);(project/"analysis").mkdir();renderer=project/"analysis"/"chart.py";renderer.write_text("# chart",encoding="utf-8");figure=paper/"figures"/"chart.svg";figure.write_text("<svg/>",encoding="utf-8");output_provenance.record_model_writes(project,[renderer],family="openai",provider="codex",model="test",role="renderer",run_id="r")
            with self.assertRaisesRegex(ValueError,"language_checked_by"):record_figure(project,"P01","papers/P01/figures/chart.svg","conceptual_diagram","analysis/chart.py",[],[])


if __name__=="__main__":unittest.main()
