from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.output_provenance import current_origin
from scripts.publication_figures import FigureSpecError, render


class PublicationFigureTests(unittest.TestCase):
    def test_renders_vector_and_high_resolution_outputs_from_real_table(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            (project / "results").mkdir(parents=True)
            (project / "papers" / "P01" / "figures").mkdir(parents=True)
            (project / "state").mkdir()
            (project / "state" / "output-provenance.json").write_text('{"schema_version":"1.0","files":{}}', encoding="utf-8")
            (project / "results" / "metrics.csv").write_text(
                "epoch,score,low,high,model\n1,0.70,0.67,0.73,A\n2,0.78,0.75,0.81,A\n1,0.68,0.65,0.71,B\n2,0.73,0.70,0.76,B\n",
                encoding="utf-8",
            )
            spec = {
                "schema_version": "1.0",
                "data": "results/metrics.csv",
                "output_stem": "papers/P01/figures/learning-curve",
                "style": "high-impact",
                "formats": ["png", "pdf", "svg"],
                "dpi": 450,
                "caption": "Learning curves with predeclared uncertainty intervals.",
                "alt_text": "Two model learning curves rise over two epochs with overlapping uncertainty.",
                "claim_ids": ["C-P01"],
                "panels": [
                    {
                        "kind": "line",
                        "x": "epoch",
                        "y": "score",
                        "hue": "model",
                        "xlabel": "Training epoch",
                        "ylabel": "Macro F1",
                        "title": "Held-out performance",
                        "uncertainty": {"lower": "low", "upper": "high"},
                    },
                    {
                        "kind": "bar",
                        "x": "epoch",
                        "y": "score",
                        "hue": "model",
                        "xlabel": "Training epoch",
                        "ylabel": "Macro F1",
                        "title": "Point estimates and intervals",
                        "uncertainty": {"lower": "low", "upper": "high"},
                    },
                ],
            }
            spec_path = project / "papers" / "P01" / "figures" / "learning-curve.spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            report = render(project, spec_path)
            self.assertEqual({item["format"] for item in report["outputs"]}, {"png", "pdf", "svg"})
            self.assertTrue(all((project / item["path"]).stat().st_size > 100 for item in report["outputs"]))
            self.assertTrue(report["quality"]["colorblind_safe_palette"])
            self.assertFalse(report["quality"]["three_dimensional_chart"])
            wrapper = project / "papers" / "P01" / "figures" / "learning-curve.renderer.py"
            build_report = project / "papers" / "P01" / "figures" / "learning-curve.figure-build.json"
            self.assertIn("subprocess.run", wrapper.read_text(encoding="utf-8"))
            self.assertEqual(current_origin(project, wrapper)["status"], "tracked")
            self.assertEqual(current_origin(project, build_report)["status"], "tracked")

    def test_rejects_non_english_labels(self):
        spec = {
            "schema_version": "1.0", "style": "technical", "formats": ["pdf", "svg"], "dpi": 300,
            "caption": "Valid caption.", "alt_text": "Valid text.", "claim_ids": ["C1"],
            "panels": [{"kind": "line", "x": "x", "y": "y", "xlabel": "时间", "ylabel": "Score"}],
        }
        from scripts.publication_figures import validate_spec
        with self.assertRaises(FigureSpecError):
            validate_spec(spec)


if __name__ == "__main__":
    unittest.main()
