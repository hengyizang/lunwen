from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.venue_candidates import build_registry, validate_registry


class VenueCandidateTests(unittest.TestCase):
    def test_registry_is_ranked_and_bound_to_local_jcr_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            for paper in ("P01", "P02"):
                (project / "papers" / paper).mkdir(parents=True)
            (project / "private").mkdir(parents=True)
            export = project / "private" / "jcr.csv"
            export.write_text(
                "Journal Name,ISSN,JCR Category,JIF Quartile,Journal Impact Factor,Edition,JCR Year\n"
                f"Journal A,1234-5678,Engineering,Q1,3.2,SCIE,{date.today().year}\n"
                f"Journal B,8765-4321,Artificial Intelligence,Q1,2.4,SCI,{date.today().year}\n",
                encoding="utf-8",
            )
            papers = []
            for paper in ("P01", "P02"):
                papers.append(
                    {
                        "paper_id": paper,
                        "candidates": [
                            {"name": "Journal A", "issn": "1234-5678", "official_guidelines_url": "https://example.org/a/guidelines", "policy_source_url": "https://example.org/a/policy", "article_type": "Original Article", "scope_fit": "Direct methods fit.", "fit_score": 92, "selection_status": "selected" if paper == "P01" else "candidate"},
                            {"name": "Journal B", "issn": "8765-4321", "official_guidelines_url": "https://example.org/b/guidelines", "policy_source_url": "https://example.org/b/policy", "article_type": "Research Article", "scope_fit": "Strong application fit.", "fit_score": 80, "selection_status": "fallback"},
                        ],
                    }
                )
            spec = project / "private" / "candidate-spec.json"
            spec.write_text(json.dumps({"papers": papers}), encoding="utf-8")
            registry = build_registry(
                project,
                "private/candidate-spec.json",
                "private/jcr.csv",
                "Researcher",
                "https://jcr.clarivate.com/",
            )
            self.assertEqual(validate_registry(project, registry), [])
            self.assertEqual(registry["papers"][0]["candidates"][0]["rank"], 1)
            self.assertEqual(registry["papers"][0]["selected_venue_id"], "journal-a")
            registry["papers"][0]["candidates"][0]["fit_score"] = -1
            self.assertTrue(any("fit_score" in item for item in validate_registry(project, registry)))
            registry["papers"][0]["candidates"][0]["fit_score"] = 92.0
            export.write_text(export.read_text(encoding="utf-8").replace("3.2", "3.3"), encoding="utf-8")
            self.assertTrue(any("hash changed" in item for item in validate_registry(project, registry)))


if __name__ == "__main__":
    unittest.main()
