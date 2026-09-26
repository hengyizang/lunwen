from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.reporting_checklist import audit, atomic_json, validate_saved_report


class ReportingChecklistTests(unittest.TestCase):
    def test_checklist_is_complete_and_bound_to_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paper = Path(directory) / "papers" / "P01"
            (paper / "manuscript").mkdir(parents=True)
            (paper / "reviews").mkdir()
            manuscript = paper / "manuscript" / "main.tex"
            manuscript.write_text("\\documentclass{article}\\begin{document}Methods are reported.\\end{document}", encoding="utf-8")
            input_value = {
                "schema_version": "1.0",
                "study_design": "machine-learning benchmark",
                "guideline": "venue checklist plus project contract",
                "guideline_version": "2026",
                "official_url": "https://example.org/checklist",
                "reviewed_by": "Human Author",
                "reviewed_at": "2026-09-26T00:00:00+00:00",
                "items": [
                    {"item_id": "DATA-1", "status": "present", "location": "Methods",
                     "evidence_ids": ["dataset-1"], "rationale": ""},
                    {"item_id": "ETHICS-1", "status": "not_applicable", "location": "",
                     "evidence_ids": [], "rationale": "No human or animal subjects."},
                ],
            }
            (paper / "reviews" / "reporting-guideline-input.json").write_text(
                json.dumps(input_value), encoding="utf-8"
            )
            report = audit(paper)
            self.assertEqual(report["status"], "pass")
            atomic_json(paper / "reviews" / "reporting-guideline.json", report)
            self.assertEqual(validate_saved_report(paper), [])
            manuscript.write_text("changed", encoding="utf-8")
            self.assertTrue(any("stale" in item for item in validate_saved_report(paper)))


if __name__ == "__main__":
    unittest.main()
