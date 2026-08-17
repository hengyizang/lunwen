from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import experiment_runner


class ExperimentRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_root = experiment_runner.PROJECTS_ROOT
        experiment_runner.PROJECTS_ROOT = Path(self.temp.name) / "projects"

    def tearDown(self) -> None:
        experiment_runner.PROJECTS_ROOT = self.old_root
        self.temp.cleanup()

    def project(self) -> Path:
        project = experiment_runner.PROJECTS_ROOT / "test-phd"
        (project / "state").mkdir(parents=True)
        (project / "experiments").mkdir()
        plan = {
            "schema_version": "1.0",
            "status": "ready_for_review",
            "runs": [
                {
                    "run_id": "baseline",
                    "paper_id": "P01",
                    "argv": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('result.txt').write_text('ok')",
                    ],
                    "cwd": ".",
                    "seed": 7,
                    "timeout_seconds": 30,
                    "estimated_cost_usd": 0,
                    "inputs": [],
                    "expected_outputs": ["result.txt"],
                }
            ],
        }
        budget = {
            "schema_version": "1.0",
            "status": "ready_for_review",
            "hard_ceiling_usd": 1,
        }
        plan_path = project / "experiments" / "plan.json"
        budget_path = project / "experiments" / "budget.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        budget_path.write_text(json.dumps(budget), encoding="utf-8")
        state = {
            "stage": "experiment-execution",
            "gate": "G4",
            "status": "awaiting_work",
            "approvals": [
                {
                    "gate": "G3",
                    "experiment_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                    "experiment_budget_sha256": hashlib.sha256(
                        budget_path.read_bytes()
                    ).hexdigest(),
                }
            ]
        }
        (project / "state" / "run.json").write_text(json.dumps(state), encoding="utf-8")
        return project

    def test_approved_run_executes_and_is_registered(self) -> None:
        project = self.project()
        results = experiment_runner.execute("test-phd")
        self.assertEqual(results[0]["status"], "succeeded")
        self.assertTrue((project / "result.txt").is_file())
        registry = (project / "experiments" / "registry.jsonl").read_text()
        self.assertIn('"run_id": "baseline"', registry)

    def test_changed_plan_is_rejected(self) -> None:
        project = self.project()
        plan_path = project / "experiments" / "plan.json"
        plan_path.write_text(plan_path.read_text() + "\n", encoding="utf-8")
        with self.assertRaises(experiment_runner.ExperimentError):
            experiment_runner.execute("test-phd")


if __name__ == "__main__":
    unittest.main()
