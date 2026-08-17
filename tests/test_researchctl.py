from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path

from scripts import researchctl


class ResearchCtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_projects_root = researchctl.PROJECTS_ROOT
        researchctl.PROJECTS_ROOT = Path(self.temp.name) / "projects"

    def tearDown(self) -> None:
        researchctl.PROJECTS_ROOT = self.old_projects_root
        self.temp.cleanup()

    def init_project(self, slug: str = "test-phd", paper_count: int = 3) -> Path:
        researchctl.initialize(
            types.SimpleNamespace(
                project=slug,
                paper_count=paper_count,
                venue="ijssd",
            )
        )
        return researchctl.PROJECTS_ROOT / slug

    def test_initialize_creates_state_papers_and_trial_venue(self) -> None:
        project = self.init_project()
        state = json.loads((project / "state" / "run.json").read_text())
        self.assertEqual(state["stage"], "intake")
        self.assertEqual(state["gate"], "G0")
        self.assertEqual(state["status"], "awaiting_work")
        self.assertEqual(len(list((project / "papers").glob("P*"))), 3)
        venue = json.loads((project / "papers" / "P01" / "venue.json").read_text())
        self.assertEqual(venue["venue_id"], "ijssd")
        self.assertEqual(venue["selection_status"], "trial")

    def test_duplicate_project_is_rejected(self) -> None:
        self.init_project()
        with self.assertRaises(researchctl.ResearchCtlError):
            self.init_project()

    def test_gate_requires_readiness_and_human_approval(self) -> None:
        project = self.init_project()
        with self.assertRaises(researchctl.ResearchCtlError):
            researchctl.advance(types.SimpleNamespace(project="test-phd"))

        constraints_path = project / "intake" / "constraints.json"
        constraints = json.loads(constraints_path.read_text())
        constraints["status"] = "ready_for_review"
        researchctl.write_json(constraints_path, constraints)

        researchctl.mark_ready(
            types.SimpleNamespace(project="test-phd", note="prepared")
        )
        state = researchctl.load_state("test-phd")
        self.assertEqual(state["status"], "awaiting_approval")

        researchctl.approve(
            types.SimpleNamespace(
                project="test-phd",
                gate="G0",
                actor="Human Researcher",
                note="reviewed",
            )
        )
        state = researchctl.load_state("test-phd")
        self.assertIn("G0", state["approved_gates"])
        self.assertEqual(len(state["approvals"][0]["artifact_sha256"]), 64)

        researchctl.advance(types.SimpleNamespace(project="test-phd"))
        state = researchctl.load_state("test-phd")
        self.assertEqual(state["stage"], "topic-intelligence")
        self.assertEqual(state["gate"], "G1")
        self.assertEqual(state["status"], "awaiting_work")

    def test_invalid_slug_is_rejected(self) -> None:
        with self.assertRaises(researchctl.ResearchCtlError):
            researchctl.validate_slug("../escape")


if __name__ == "__main__":
    unittest.main()

