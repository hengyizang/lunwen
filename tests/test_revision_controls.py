from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.revision_integrity import audit as integrity_audit
from scripts.revision_trace import audit as trace_audit


class RevisionControlTests(unittest.TestCase):
    def make_paper(self, root: Path) -> Path:
        paper = root / "papers" / "P01"
        (paper / "manuscript").mkdir(parents=True)
        (paper / "reviews").mkdir()
        base = "\\documentclass{article}\\begin{document}The model may improve accuracy by 10 percent \\cite{old}.\\end{document}"
        (paper / "reviews" / "revision-base.tex").write_text(base, encoding="utf-8")
        (paper / "manuscript" / "main.tex").write_text(base, encoding="utf-8")
        return paper

    def test_trace_confirms_promised_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paper = self.make_paper(Path(directory))
            with (paper / "reviews" / "response-matrix.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "comment_id", "commitment_id", "fulfillment_status",
                        "location", "revised_text", "unfulfilled_rationale",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "comment_id": "R1-C1",
                        "commitment_id": "K1",
                        "fulfillment_status": "fulfilled",
                        "location": "Results",
                        "revised_text": "The model may improve accuracy by 10 percent",
                        "unfulfilled_rationale": "",
                    }
                )
            self.assertEqual(trace_audit(paper)["status"], "pass")
            (paper / "manuscript" / "main.tex").write_text("No promised result.", encoding="utf-8")
            self.assertEqual(trace_audit(paper)["status"], "fail")

    def test_integrity_requires_exact_human_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paper = self.make_paper(Path(directory))
            (paper / "manuscript" / "main.tex").write_text(
                "\\documentclass{article}\\begin{document}The model proves accuracy improved by 12 percent \\cite{new}.\\end{document}",
                encoding="utf-8",
            )
            first = integrity_audit(paper)
            self.assertEqual(first["status"], "fail")
            changes = first["changes"]
            authorization = {
                "schema_version": "1.0",
                "approved_by": "Human Author",
                "approved_at": "2026-09-26T00:00:00+00:00",
                **changes,
                "claim_language_rationale": "The revised experiment supports the changed wording.",
            }
            (paper / "reviews" / "revision-authorizations.json").write_text(
                json.dumps(authorization), encoding="utf-8"
            )
            self.assertEqual(integrity_audit(paper)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
