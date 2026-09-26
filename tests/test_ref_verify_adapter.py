from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.ref_verify_adapter import (
    RefVerifyAdapterError,
    atomic_write,
    load_claims,
    run,
    validate_saved_report,
)


class RefVerifyAdapterTests(unittest.TestCase):
    def make_paper(self, root: Path) -> tuple[Path, Path]:
        paper = root / "papers" / "P01"
        (paper / "manuscript").mkdir(parents=True)
        (paper / "reviews").mkdir()
        (paper / "manuscript" / "main.tex").write_text(
            "\\documentclass{article}\\begin{document}The measured result was 12 percent \\cite{x}.\\end{document}",
            encoding="utf-8",
        )
        (paper / "manuscript" / "references.bib").write_text(
            "@article{x,title={Verified},doi={10.1000/example}}", encoding="utf-8"
        )
        claims = paper / "reviews" / "citation-claims.jsonl"
        claims.write_text(
            json.dumps(
                {
                    "id": "C1",
                    "doi": "https://doi.org/10.1000/example",
                    "claim": "The measured result was 12 percent.",
                    "claim_type": "numeric",
                    "evidence_depth": "abstract",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return paper, claims

    def test_pass_report_is_hash_bound_and_stales_after_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paper, claims = self.make_paper(Path(directory))

            def runner(command: list[str], **_: object) -> SimpleNamespace:
                rows = load_claims(claims)
                payload = {
                    "summary": {"total": 1, "accept": 1, "failed": 0},
                    "results": [
                        {
                            **rows[0],
                            "verdict": "ACCEPT",
                            "status": "SUPPORTED",
                            "evidence": "Abstract reports the measured result.",
                        }
                    ],
                }
                return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

            report = run(
                paper,
                claims,
                executable="ref-verify",
                engine_version="1.2.0",
                runner=runner,
            )
            self.assertEqual(report["status"], "pass")
            atomic_write(paper / "reviews" / "ref-verify.json", report)
            self.assertEqual(validate_saved_report(paper), [])
            (paper / "manuscript" / "main.tex").write_text("changed", encoding="utf-8")
            self.assertTrue(any("stale" in item for item in validate_saved_report(paper)))

    def test_mechanism_claim_is_rejected_from_abstract_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paper, claims = self.make_paper(Path(directory))
            value = json.loads(claims.read_text(encoding="utf-8"))
            value["claim_type"] = "mechanism"
            claims.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RefVerifyAdapterError, "full-text"):
                load_claims(claims)


if __name__ == "__main__":
    unittest.main()
