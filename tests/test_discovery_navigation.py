"""Large synthetic discovery leads stay complete and explicitly navigable."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator as api, context_efficiency as context, artifact_ownership


class DiscoveryNavigationTests(unittest.TestCase):
    relative = "data/discovery-broad-auto-20261101T080436670556Z.json"

    def fixture(self):
        return {"schema_version": "1.0", "candidate_count": 500,
            "automatic_screening_summary": {"method": "deterministic_metadata_screening", "shortlist_count": 80},
            "candidates": [{"provider": "synthetic", "provider_id": str(i), "doi": None,
                "landing_url": f"https://example.org/dataset/{i}", "title": f"Synthetic dataset {i}",
                "description": "Synthetic unassessed discovery description. " * 75,
                "license_status": "unknown", "fitness_status": "requires_review",
                "automatic_screening": {"status": "shortlisted" if i < 80 else "deprioritized"}}
                for i in range(500)]}

    def test_all_candidates_unknowns_and_original_line_locations_survive_large_snapshot(self):
        text = json.dumps(self.fixture(), indent=2)
        self.assertGreater(len(text.encode()), 1_500_000)
        digest = hashlib.sha256(text.encode()).hexdigest()
        index = json.loads(context.discovery_navigation_index(self.relative, text, digest))
        self.assertEqual(index["candidate_count"], 500)
        self.assertEqual(index["omitted_candidate_count"], 0)
        self.assertEqual(index["source"]["sha256"], digest)
        self.assertIn("unknown", index["value_table"])
        self.assertIn("deprioritized", index["value_table"])
        self.assertIn(None, index["value_table"])
        lines = text.splitlines()
        expected = self.fixture()["candidates"]
        for row in index["candidate_rows"]:
            original = json.loads("\n".join(lines[row[1]-1:row[2]]).rstrip().rstrip(","))
            self.assertEqual(original, expected[row[0]])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); project = root / "projects/demo"
            source = project / self.relative
            source.parent.mkdir(parents=True); source.write_text(text, encoding="utf-8", newline="\n")
            with patch.object(api, "ROOT", root):
                snapshot = api.project_snapshot("demo", stage="topic-intelligence")
            self.assertIn("complete_dataset_discovery_navigation_index", snapshot)
            self.assertIn(digest, snapshot)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
            # The existing context plan exposes a selected complete original candidate.
            row = index["candidate_rows"][499]
            plan = project / "program/context-plan.json"; plan.parent.mkdir()
            plan.write_text(json.dumps({"schema_version": "1.0", "stages": {"topic-intelligence": {
                "question": "Inspect this complete synthetic candidate before any fitness judgement",
                "items": [{"path": self.relative, "reason": "Read complete selected discovery lead", "stance": "neutral",
                           "start_line": row[1], "end_line": row[2]}]}}}), encoding="utf-8")
            with patch.object(api, "ROOT", root):
                selected = api.project_snapshot("demo", stage="topic-intelligence")
            self.assertIn("Synthetic dataset 499", selected)
            self.assertIn("Synthetic unassessed discovery description.", selected)

    def test_scientific_source_overflow_still_blocks_and_no_writer_can_forge_auto_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); project = root / "projects/demo"
            source = project / "evidence/negative.md"; source.parent.mkdir(parents=True)
            source.write_text("Contrary scientific result. " * 8000, encoding="utf-8")
            with patch.object(api, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "source ranges"):
                    api.project_snapshot("demo", stage="topic-intelligence")
            self.assertTrue(artifact_ownership.executor_owned(project, self.relative))
            with patch.object(api, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "protected|controller|Automatic"):
                    api.safe_target("demo", self.relative)

    def test_wrong_kind_and_incomplete_candidate_count_cannot_create_navigation(self):
        report = self.fixture()
        report["candidate_count"] = 499
        with self.assertRaisesRegex(ValueError, "candidate count"):
            context.discovery_navigation_index(self.relative, json.dumps(report), "a"*64)
        self.assertIsNone(context.discovery_navigation_index("papers/P01/result.json", json.dumps(self.fixture()), "a"*64))
        report["automatic_screening_summary"] = None
        self.assertIsNone(context.discovery_navigation_index(self.relative, json.dumps(report), "a"*64))
