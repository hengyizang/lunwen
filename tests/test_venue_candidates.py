from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.venue_candidates import VenueCandidateError, build_registry, validate_registry


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
            self.assertFalse(registry["human_review_required"])
            self.assertFalse(registry["human_review_verified"])
            self.assertFalse(registry["scientific_validation"])
            legacy = {key: value for key, value in registry.items()
                      if key not in {"human_review_verified", "scientific_validation"}}
            legacy["human_review_required"] = True
            before = json.dumps(legacy)
            self.assertEqual(validate_registry(project, legacy), [])
            self.assertEqual(json.dumps(legacy), before)
            registry["human_review_verified"] = True
            self.assertTrue(validate_registry(project, registry))
            registry["human_review_verified"] = False
            self.assertEqual(registry["papers"][0]["candidates"][0]["rank"], 1)
            self.assertEqual(registry["papers"][0]["selected_venue_id"], "journal-a")
            (project / "papers" / "P01" / "paper-contract.json").write_text(
                json.dumps({"target_jcr_quartile": "Q2"}), encoding="utf-8"
            )
            self.assertTrue(
                any(
                    "differs from paper-contract.json" in item
                    for item in validate_registry(project, registry)
                )
            )
            registry["papers"][0]["candidates"][0]["fit_score"] = -1
            self.assertTrue(any("fit_score" in item for item in validate_registry(project, registry)))
            registry["papers"][0]["candidates"][0]["fit_score"] = 92.0
            export.write_text(export.read_text(encoding="utf-8").replace("3.2", "3.3"), encoding="utf-8")
            self.assertTrue(any("hash changed" in item for item in validate_registry(project, registry)))
            source = export.read_text()
            for invalid in ("nan", "inf", "-inf"):
                with self.subTest(nonfinite_impact=invalid), self.assertRaises(VenueCandidateError):
                    export.write_text(source.replace("3.3", invalid))
                    build_registry(project, "private/candidate-spec.json", "private/jcr.csv",
                                   "Researcher", "https://jcr.clarivate.com/")
