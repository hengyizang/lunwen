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
        contract = json.loads((project / "papers" / "P01" / "paper-contract.json").read_text())
        self.assertEqual(contract["schema_version"], "2.0")
        self.assertEqual(contract["writing_language"], "en")
        self.assertTrue((project / "papers" / "P01" / "experiments").is_dir())

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

    def test_artifact_change_invalidates_approval(self) -> None:
        project = self.init_project()
        constraints_path = project / "intake" / "constraints.json"
        constraints = json.loads(constraints_path.read_text())
        constraints["status"] = "ready_for_review"
        researchctl.write_json(constraints_path, constraints)
        researchctl.mark_ready(types.SimpleNamespace(project="test-phd", note="ready"))
        researchctl.approve(
            types.SimpleNamespace(
                project="test-phd", gate="G0", actor="Human", note="approved"
            )
        )
        constraints["notes"].append("changed after approval")
        researchctl.write_json(constraints_path, constraints)
        with self.assertRaises(researchctl.ResearchCtlError):
            researchctl.advance(types.SimpleNamespace(project="test-phd"))

    def test_g5_advances_each_paper_before_finishing(self) -> None:
        self.init_project(paper_count=3)
        state = researchctl.load_state("test-phd")
        state.update(
            {
                "stage_index": 5,
                "stage": "writing-and-review",
                "gate": "G5",
                "status": "approved",
            }
        )
        state["approved_gates"].append("G5:P01")
        state["approvals"].append(
            {
                "gate": "G5",
                "paper_id": "P01",
                "artifact_sha256": researchctl.artifact_hash("test-phd", "G5"),
            }
        )
        researchctl.save_state("test-phd", state)

        researchctl.advance(types.SimpleNamespace(project="test-phd"))
        state = researchctl.load_state("test-phd")
        self.assertEqual(state["active_paper"], "P02")
        self.assertEqual(state["paper_statuses"]["P01"], "submission_ready")
        self.assertEqual(state["stage"], "writing-and-review")

        for paper_id in ("P02", "P03"):
            state["status"] = "approved"
            state["approved_gates"].append(f"G5:{paper_id}")
            state["approvals"].append(
                {
                    "gate": "G5",
                    "paper_id": paper_id,
                    "artifact_sha256": researchctl.artifact_hash("test-phd", "G5"),
                }
            )
            researchctl.save_state("test-phd", state)
            researchctl.advance(types.SimpleNamespace(project="test-phd"))
            state = researchctl.load_state("test-phd")

        self.assertEqual(state["stage"], "submission-ready")
        self.assertEqual(state["status"], "submission_ready")
        self.assertTrue(
            all(value == "submission_ready" for value in state["paper_statuses"].values())
        )

    def test_g3_malformed_nested_plan_reports_errors_instead_of_crashing(self) -> None:
        project = self.init_project(paper_count=1)
        state = researchctl.load_state("test-phd")
        state.update(
            {"stage_index": 3, "stage": "experiment-design", "gate": "G3"}
        )
        researchctl.save_state("test-phd", state)
        researchctl.write_json(
            project / "experiments" / "plan.json",
            {"schema_version": "1.0", "status": "ready_for_review", "runs": None},
        )
        errors = researchctl.gate_errors("test-phd", "G3")
        self.assertTrue(any("runs must be a non-empty array" in error for error in errors))
        self.assertTrue(any("experiments" in error and "*.json" in error for error in errors))

    def test_g3_detects_planned_runs_missing_from_paper_designs(self) -> None:
        project = self.init_project(paper_count=1)
        state = researchctl.load_state("test-phd")
        state.update(
            {"stage_index": 3, "stage": "experiment-design", "gate": "G3"}
        )
        researchctl.save_state("test-phd", state)
        runs = [
            {"run_id": f"run-{seed}", "paper_id": "P01", "argv": ["python3", "study.py"], "cwd": ".", "seed": seed, "timeout_seconds": 60, "estimated_cost_usd": 0, "inputs": [], "expected_outputs": []}
            for seed in (1, 2, 3)
        ]
        researchctl.write_json(
            project / "experiments" / "plan.json",
            {"schema_version": "1.0", "status": "ready_for_review", "runs": runs},
        )
        researchctl.write_json(
            project / "papers" / "P01" / "experiments" / "primary.json",
            {"schema_version": "1.0", "status": "ready_for_review", "paper_id": "P01", "design_id": "D1", "run_ids": ["run-1"]},
        )
        errors = researchctl.gate_errors("test-phd", "G3")
        self.assertTrue(any("omit planned runs: run-2, run-3" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
