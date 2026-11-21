"""Regressions for retaining source coverage and observed missingness."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import paper_reader, figure_recipes


class ReaderCoverageTests(unittest.TestCase):
    def test_long_pdf_keeps_every_page_and_marks_unextractable_pages(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            pdf = project / "source.pdf"
            pdf.write_bytes(b"%PDF fixture")
            texts = ["A long original page " + "x" * 45000, ""] + [f"Original page {i}" for i in range(3, 122)]
            fake = SimpleNamespace(is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda text=text: text) for text in texts])
            output = project / "evidence/readers/source.md"
            with patch.dict("sys.modules", {"pypdf": SimpleNamespace(PdfReader=lambda *a, **kw: fake)}):
                result = paper_reader.build(project, pdf, output, max_pages=30)
            receipt = json.loads((project / result["receipt"]).read_text())
            self.assertEqual(receipt["selected_pages"], list(range(1, 122)))
            self.assertEqual([len(b) for b in receipt["page_batches"]], [30, 30, 30, 30, 1])
            self.assertEqual(receipt["missing_text_pages"], [2])
            self.assertFalse(receipt["all_selected_pages_extracted"])
            self.assertIn(texts[0], output.read_text())
            self.assertIn("Original page 121", output.read_text())
            self.assertTrue(paper_reader.reusable_reader(project, pdf, output))

    def test_translation_resume_reuses_completed_fragments_after_interruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            pdf = project / "source.pdf"
            pdf.write_bytes(b"%PDF fixture")
            text = "source word " * 2500
            fake = SimpleNamespace(is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda: text)])
            response = SimpleNamespace(text="中文", provider="openai", model="fixture", reported_model="fixture",
                                       request_id="fixture", completion_status="completed", cache_hit=False)
            output = project / "evidence/readers/source.md"
            with patch.dict("sys.modules", {"pypdf": SimpleNamespace(PdfReader=lambda *a, **kw: fake)}), \
                 patch.object(paper_reader.model_runtime, "call", side_effect=[response, RuntimeError("interrupted")]):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    paper_reader.build(project, pdf, output, translate=True)
            self.assertFalse(output.exists())
            with patch.dict("sys.modules", {"pypdf": SimpleNamespace(PdfReader=lambda *a, **kw: fake)}), \
                 patch.object(paper_reader.model_runtime, "call", return_value=response) as call:
                result = paper_reader.build(project, pdf, output, translate=True)
            receipt = json.loads((project / result["receipt"]).read_text())
            self.assertEqual(call.call_count, 2)
            self.assertTrue(receipt["translation_calls"][0]["cache_hit"])
            self.assertEqual(receipt["translation_calls"][-1]["character_end"], len(text.strip()))
            self.assertTrue(receipt["translation_complete"])


class FigureMissingnessTests(unittest.TestCase):
    def test_stacked_bar_missing_cells_are_not_imputed_and_observed_zero_survives(self):
        import numpy as np
        import pandas as pd
        panel = {"kind": "stacked_bar", "x": "category", "y": "value", "hue": "group"}
        for rows in ([['a', 'one', 1], ['b', 'two', 2]], [['a', 'one', None]]):
            frame = pd.DataFrame(rows, columns=["category", "group", "value"])
            with self.assertRaisesRegex(ValueError, "missing cells"):
                figure_recipes.draw(Mock(), panel, frame, np, pd, ("red", "blue"))
        frame = pd.DataFrame([['a', 'one', 0], ['a', 'two', 2]], columns=["category", "group", "value"])
        ax = Mock()
        figure_recipes.draw(ax, panel, frame, np, pd, ("red", "blue"))
        self.assertEqual(ax.bar.call_args_list[0].args[1].tolist(), [0])
