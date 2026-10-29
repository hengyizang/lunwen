"""Actual CPU drawing/composition tests; fixtures make no scientific claims."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from scripts import publication_figures as figures, figure_layout


class FigurePanelCacheTests(unittest.TestCase):
    def fixture(self, directory):
        project = Path(directory) / "panel-fixture"
        (project / "results").mkdir(parents=True)
        folder = project / "papers" / "P01" / "figures"
        folder.mkdir(parents=True)
        (project / "state").mkdir()
        (project / "state" / "output-provenance.json").write_text(
            '{"schema_version":"1.0","files":{}}', encoding="utf-8")
        for name, values in (("left", "1,0.4\n2,0.7\n3,0.6\n"),
                             ("right", "1,0.3\n2,0.5\n3,0.8\n")):
            (project / "results" / (name + ".csv")).write_text("epoch,score\n" + values)
        spec = {"schema_version": "1.0", "reuse_panels": True,
                "output_stem": "papers/P01/figures/two-panel", "style": "technical",
                "formats": ["svg", "pdf", "png"], "dpi": 300, "final_width_mm": 182.88,
                "caption": "Synthetic renderer fixture.", "alt_text": "Two synthetic lines.",
                "claim_ids": ["FIXTURE-ONLY"], "panels": [
                    {"kind": "line", "data": "results/left.csv", "x": "epoch", "y": "score",
                     "xlabel": "Epoch", "ylabel": "Score", "title": "Left fixture"},
                    {"kind": "line", "data": "results/right.csv", "x": "epoch", "y": "score",
                     "xlabel": "Epoch", "ylabel": "Score", "title": "Right fixture"}]}
        path = folder / "two-panel.spec.json"
        path.write_text(json.dumps(spec))
        return project, path, spec

    def test_actual_draw_is_skipped_and_only_changed_panel_redraws(self):
        import fitz
        with tempfile.TemporaryDirectory() as directory:
            project, path, spec = self.fixture(directory)
            with patch.object(figures, "_draw_panel", wraps=figures._draw_panel) as draw:
                first = figures.render(project, path)
                self.assertEqual(draw.call_count, 2)
                self.assertEqual(first["panel_cache"]["drawn"], 2)
                draw.reset_mock()
                second = figures.render(project, path)
                self.assertEqual(draw.call_count, 0)
                self.assertEqual(second["panel_cache"]["reused"], 2)
                self.assertEqual([row["key"] for row in first["panel_cache"]["panels"]],
                                 [row["key"] for row in second["panel_cache"]["panels"]])
                (project / "results" / "left.csv").write_text("epoch,score\n1,0.4\n2,0.7\n3,0.9\n")
                draw.reset_mock()
                changed = figures.render(project, path)
                self.assertEqual(draw.call_count, 1)
                self.assertEqual(draw.call_args.args[-1], 0)
                self.assertEqual([row["reused"] for row in changed["panel_cache"]["panels"]], [False, True])
                spec["panels"][1]["title"] = "Revised right fixture"
                path.write_text(json.dumps(spec))
                draw.reset_mock()
                revised = figures.render(project, path)
                self.assertEqual(draw.call_count, 1)
                self.assertEqual(draw.call_args.args[-1], 1)
            self.assertEqual(revised["quality"]["output_qa"]["status"], "pass")
            self.assertTrue(revised["quality"]["layout_audit"]["pass"])
            self.assertEqual(figure_layout.validate_saved_figures(project / "papers" / "P01"), [])
            svg = project / "papers/P01/figures/two-panel.svg"
            root = ET.parse(svg).getroot()
            children = [node for node in root if node.tag.endswith("}svg")]
            self.assertEqual(len(children), 2)
            self.assertEqual([(float(node.get("x")), float(node.get("width"))) for node in children],
                             [(0.0, 3.6*72), (3.6*72, 3.6*72)])
            text = " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}text"))
            self.assertIn("Revised right fixture", text)
            # Line charts remain vector shapes/text, never one opaque image.
            self.assertFalse(any(node.tag.endswith("}image") for node in root.iter()))
            ids = [node.get("id") for node in root.iter() if node.get("id")]
            self.assertEqual(len(ids), len(set(ids)))
            with fitz.open(project / "papers/P01/figures/two-panel.pdf") as document:
                self.assertIn("Revised right fixture", document[0].get_text())
                self.assertTrue(document[0].get_drawings())
                self.assertAlmostEqual(document[0].rect.width, 7.2*72, places=3)
            self.assertTrue(all((project / row["receipt"]["path"]).is_file()
                                for row in revised["panel_cache"]["panels"]))

    def test_style_and_renderer_dependency_changes_invalidate_panels(self):
        from scripts import figure_panel_cache
        with tempfile.TemporaryDirectory() as directory:
            project, path, spec = self.fixture(directory)
            first = figures.render(project, path)
            with patch.object(figures, "PALETTE", ("#123456", *figures.PALETTE[1:])), \
                    patch.object(figures, "_draw_panel", wraps=figures._draw_panel) as draw:
                style = figures.render(project, path)
                self.assertEqual(draw.call_count, 2)
                self.assertNotEqual(first["panel_cache"]["panels"][0]["key"], style["panel_cache"]["panels"][0]["key"])
            original = figure_panel_cache.renderer_dependencies
            def changed_dependency(*args):
                dependencies = original(*args)
                dependencies["sources"]["scripts/figure_recipes.py"] = "0"*64
                return dependencies
            with patch.object(figure_panel_cache, "renderer_dependencies", side_effect=changed_dependency), \
                    patch.object(figures, "_draw_panel", wraps=figures._draw_panel) as draw:
                changed = figures.render(project, path)
                self.assertEqual(draw.call_count, 2)
                self.assertEqual(changed["panel_cache"]["drawn"], 2)

    def test_tampered_svg_and_resigned_receipt_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            project, path, _spec = self.fixture(directory)
            report = figures.render(project, path)
            receipt = project / report["panel_cache"]["panels"][0]["receipt"]["path"]
            svg = receipt.with_name("panel.svg")
            svg.write_bytes(svg.read_bytes() + b"\n<!-- changed -->")
            with patch.object(figures, "_draw_panel") as draw:
                with self.assertRaisesRegex(figures.FigureSpecError, "bytes changed"):
                    figures.render(project, path)
                draw.assert_not_called()
            record = json.loads(receipt.read_text())
            import hashlib
            record["files"]["svg"] = hashlib.sha256(svg.read_bytes()).hexdigest()
            receipt.write_text(json.dumps(record))
            with self.assertRaisesRegex(figures.FigureSpecError, "executor provenance"):
                figures.render(project, path)

    def test_reuse_flag_is_strict_boolean(self):
        with tempfile.TemporaryDirectory() as directory:
            project, path, spec = self.fixture(directory)
            spec["reuse_panels"] = "yes"
            path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(figures.FigureSpecError, "reuse_panels must be boolean"):
                figures.render(project, path)


if __name__ == "__main__":
    unittest.main()
