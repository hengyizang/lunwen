from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.journal_screening import build, validate_saved_report


class JournalScreeningTests(unittest.TestCase):
    def test_weighted_screening_is_registry_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            (project / "program").mkdir(parents=True)
            registry = {
                "papers": [
                    {
                        "paper_id": "P01",
                        "target_jcr_quartile": "Q1",
                        "selected_venue_id": "target",
                        "candidates": [
                            {"venue_id": "challenge", "name": "Challenge Journal"},
                            {"venue_id": "target", "name": "Target Journal"},
                            {"venue_id": "safety", "name": "Safety Journal"},
                        ],
                    }
                ]
            }
            evidence = [
                {"category": category, "url": f"https://example.org/{category}", "accessed_at": "2026-09-26", "note": "Official current evidence"}
                for category in ("scope", "article_type", "audience", "practicality", "access", "reputation")
            ]
            spec = {
                "reviewed_by": "Human Author",
                "reviewed_at": "2026-09-26T00:00:00+00:00",
                "papers": [
                    {
                        "paper_id": "P01",
                        "candidates": [
                            {
                                "venue_id": role,
                                "strategy": role,
                                "scores": {
                                    "scope_fit": 5, "article_type_fit": 4, "audience_fit": 4,
                                    "impact_and_tier": 5, "practicality": 3,
                                    "access_and_cost": 3, "reputation_and_risk": 4,
                                },
                                "risk_flags": [],
                                "evidence": evidence,
                            }
                            for role in ("challenge", "target", "safety")
                        ],
                    }
                ]
            }
            input_path = project / "program" / "journal-screening-input.json"
            registry_path = project / "program" / "venue-candidates.json"
            input_path.write_text(json.dumps(spec), encoding="utf-8")
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            report = build(project, input_path, registry_path)
            self.assertEqual(report["papers"][0]["candidates"][0]["weighted_score"], 86.0)
            (project / "program" / "journal-screening.json").write_text(
                json.dumps(report), encoding="utf-8"
            )
            self.assertEqual(validate_saved_report(project), [])
            self.assertFalse(report["human_review_required"])
            self.assertFalse(report["scientific_validation"])
            self.assertFalse(report["assessment"]["human_review_verified"])
            self.assertNotIn("human_review", report)
            target = project / "program/journal-screening.json"
            legacy = {key: value for key, value in report.items()
                      if key not in {"assessment", "scientific_validation"}}
            legacy.update(human_review_required=True, human_review={
                "reviewed_by": spec["reviewed_by"], "reviewed_at": spec["reviewed_at"]})
            target.write_text(json.dumps(legacy))
            original = target.read_bytes()
            self.assertEqual(validate_saved_report(project), [])
            self.assertEqual(target.read_bytes(), original)
            spec["recorded_by"] = spec.pop("reviewed_by")
            spec["recorded_at"] = spec.pop("reviewed_at")
            input_path.write_text(json.dumps(spec))
            report = build(project, input_path, registry_path)
            target.write_text(json.dumps(report))
            self.assertEqual(validate_saved_report(project), [])
            report["assessment"]["human_review_verified"] = True
            target.write_text(json.dumps(report))
            self.assertTrue(validate_saved_report(project))
            report["assessment"]["human_review_verified"] = False
            target.write_text(json.dumps(report))
            registry["papers"][0]["candidates"][0]["name"] = "Changed"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            self.assertTrue(validate_saved_report(project))
