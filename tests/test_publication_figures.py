from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from scripts.output_provenance import current_origin
from scripts.publication_figures import FigureSpecError, render
from scripts import figure_layout


class PublicationFigureTests(unittest.TestCase):
    def panel_fixture(self, directory):
        project = Path(directory)
        folder = project / "papers/P01/figures"
        folder.mkdir(parents=True);(project / "results").mkdir()
        for name, values in (("left", "1,0.4\n2,0.7\n"), ("right", "1,0.3\n2,0.5\n")):
            (project / f"results/{name}.csv").write_text("epoch,score\n" + values)
        spec = {"schema_version": "1.0", "reuse_panels": True, "source_data_export": True,
                "output_stem": "papers/P01/figures/panels", "style": "technical",
                "formats": ["svg", "pdf", "png"], "dpi": 300,
                "caption": "Synthetic fixture.", "alt_text": "Recorded fixture values.", "claim_ids": ["FIXTURE"],
                "panels": [{"kind": "line", "data": f"results/{name}.csv", "x": "epoch", "y": "score",
                            "xlabel": "Epoch", "ylabel": "Score", "title": name.title()} for name in ("left", "right")]}
        path = folder / "panels.spec.json";path.write_text(json.dumps(spec))
        from jsonschema import validate
        validate(spec, json.loads((Path(__file__).resolve().parents[1] / "schemas/publication-figure-spec.schema.json").read_text()))
        return project, path, spec

    def test_retired_reuse_request_redraws_values_vectors_and_per_panel_source_exports(self):
        import fitz
        from scripts import publication_figures as figures
        with tempfile.TemporaryDirectory() as directory:
            project, path, _spec = self.panel_fixture(directory)
            observed = [];original = figures._draw_panel
            def draw(ax, panel, frame, np, pd, index):
                original(ax, panel, frame, np, pd, index)
                observed.append((ax.lines[0].get_ydata().tolist(), ax.get_xlabel(), ax.get_ylabel()))
            with patch.object(figures, "_draw_panel", side_effect=draw) as drawer:
                first = render(project, path);second = render(project, path)
                self.assertEqual(drawer.call_count, 4)
                self.assertEqual(observed, [([0.4, 0.7], "Epoch", "Score"), ([0.3, 0.5], "Epoch", "Score")] * 2)
                (project / "results/left.csv").write_text("epoch,score\n1,0.4\n2,0.9\n")
                changed = render(project, path)
                self.assertEqual(drawer.call_count, 6)
                self.assertEqual(observed[-2][0], [0.4, 0.9])
            self.assertEqual(second["panel_cache"], {"enabled": False, "status": "retired", "mode": "full_redraw"})
            self.assertFalse((project / "reports/figure-panel-cache").exists())
            self.assertEqual(changed["quality"]["output_qa"]["status"], "pass")
            self.assertEqual(figure_layout.validate_saved_figures(project / "papers/P01"), [])
            for name, row in zip(("left", "right"), changed["source_data_exports"]):
                self.assertEqual((project / row["path"]).read_bytes(), (project / f"results/{name}.csv").read_bytes())
            svg = ET.parse(project / first["outputs"][0]["path"]).getroot()
            self.assertFalse(any(node.tag.endswith("}image") for node in svg.iter()))
            self.assertIn("Left", " ".join(node.text or "" for node in svg.iter() if node.tag.endswith("}text")))
            with fitz.open(project / "papers/P01/figures/panels.pdf") as pdf:
                self.assertIn("Right", pdf[0].get_text());self.assertTrue(pdf[0].get_drawings())

    def test_legacy_cached_build_requires_rebuild_and_reuse_flag_stays_strict(self):
        from scripts.output_provenance import record_model_writes
        with tempfile.TemporaryDirectory() as directory:
            project, path, spec = self.panel_fixture(directory)
            report = render(project, path)
            build = path.with_name("panels.figure-build.json")
            report["panel_cache"] = {"enabled": True};build.write_text(json.dumps(report))
            record_model_writes(project, [build], family="other", provider="deterministic-local-renderer", model="scripts/publication_figures.py", role="fixture", run_id="fixture")
            self.assertTrue(any("panel cache is retired; rebuild" in issue for issue in figure_layout.validate_saved_figures(project / "papers/P01")))
            spec["reuse_panels"] = "yes";path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(FigureSpecError, "reuse_panels must be boolean"):
                render(project, path)

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
            qa = report["quality"]["output_qa"]
            self.assertEqual(qa["status"], "pass")
            svg = next(row for row in qa["outputs"] if row["path"].endswith(".svg"))
            pdf = next(row for row in qa["outputs"] if row["path"].endswith(".pdf"))
            self.assertGreater(svg["editable_text_nodes"], 0)
            self.assertGreater(pdf["minimum_text_points"], 0)
            self.assertTrue(pdf["physical_pages_mm"])
            for preview in pdf["grayscale_previews"]:
                self.assertTrue(preview["path"].startswith("reports/figure-output-qa/"))
                self.assertTrue((project / preview["path"]).is_file())
            wrapper = project / "papers" / "P01" / "figures" / "learning-curve.renderer.py"
            build_report = project / "papers" / "P01" / "figures" / "learning-curve.figure-build.json"
            self.assertIn("subprocess.run", wrapper.read_text(encoding="utf-8"))
            self.assertEqual(current_origin(project, wrapper)["status"], "tracked")
            self.assertEqual(current_origin(project, build_report)["status"], "tracked")
            self.assertTrue(report["quality"]["layout_audit"]["pass"])
            paper = project / "papers" / "P01"
            reads = []
            read_text = Path.read_text
            def count_build(path, *args, **kwargs):
                if path == build_report:
                    reads.append(path)
                return read_text(path, *args, **kwargs)
            with patch.object(Path, "read_text", count_build):
                self.assertEqual(figure_layout.validate_saved_figures(paper), [])
            self.assertEqual(len(reads), 1)
            audit_record = report["quality"]["layout_audit"]
            audit_path = project / audit_record["path"]
            audit = json.loads(audit_path.read_text())
            audit["human_visual_review_required"] = False
            audit_path.write_text(json.dumps(audit))
            self.assertTrue(any("stale" in error or "control provenance" in error
                                for error in figure_layout.validate_saved_figures(paper)))

    def test_rejects_non_english_labels(self):
        spec = {
            "schema_version": "1.0", "style": "technical", "formats": ["pdf", "svg"], "dpi": 300,
            "caption": "Valid caption.", "alt_text": "Valid text.", "claim_ids": ["C1"],
            "panels": [{"kind": "line", "x": "x", "y": "y", "xlabel": "时间", "ylabel": "Score"}],
        }
        from scripts.publication_figures import validate_spec
        with self.assertRaises(FigureSpecError):
            validate_spec(spec)
