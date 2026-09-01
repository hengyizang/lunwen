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

    def complete_constraints(self, project: Path) -> None:
        path=project/"intake"/"constraints.json"
        value=json.loads(path.read_text())
        value.update({"status":"ready_for_review","research_goal":"Develop a rigorous doctoral research programme.","researcher_background":"Mechanical engineering and data/AI.","available_skills":["Python","machine learning","mechanical engineering"],"time_horizon_years":3,"weekly_hours":30,"cash_budget_usd":1000,"cloud_compute_budget_usd":200,"local_compute":{"gpu":"none","ram_gb":16,"storage_gb":512},"ranking_weights":{"novelty_and_doctoral_depth":0.3,"feasibility_without_lab":0.2,"funded_position_supply":0.1,"competition":0.1,"job_market_and_salary":0.1,"background_fit":0.2}})
        researchctl.write_json(path,value)

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

        self.complete_constraints(project)

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
        self.complete_constraints(project)
        constraints = json.loads(constraints_path.read_text())
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

    def test_g0_rejects_status_only_with_unknown_constraints(self) -> None:
        project=self.init_project()
        path=project/"intake"/"constraints.json";value=json.loads(path.read_text());value["status"]="ready_for_review";researchctl.write_json(path,value)
        errors=researchctl.gate_errors("test-phd","G0")
        self.assertTrue(any("weekly_hours" in error for error in errors))

    def test_change_after_ready_requires_fresh_human_review(self) -> None:
        project=self.init_project();self.complete_constraints(project)
        researchctl.mark_ready(types.SimpleNamespace(project="test-phd",note="ready"))
        path=project/"intake"/"constraints.json";value=json.loads(path.read_text());value["notes"].append("changed");researchctl.write_json(path,value)
        with self.assertRaisesRegex(researchctl.ResearchCtlError,"changed after ready"):
            researchctl.approve(types.SimpleNamespace(project="test-phd",gate="G0",actor="Human",note="old review"))

    def test_reopen_returns_gate_to_model_editable_work(self) -> None:
        project=self.init_project();self.complete_constraints(project);researchctl.mark_ready(types.SimpleNamespace(project="test-phd",note="ready"))
        researchctl.reopen(types.SimpleNamespace(project="test-phd",note="Needs another model revision"))
        state=researchctl.load_state("test-phd");self.assertEqual(state["status"],"awaiting_work");self.assertNotIn("ready_artifact_sha256",state)

    def test_final_audit_blocks_major_findings_and_unresolved_dispositions(self) -> None:
        project=self.init_project();review_dir=project/"reviews"/"independent";review_dir.mkdir(parents=True,exist_ok=True)
        base={"verdict":"revise","fatal_findings":[],"major_findings":[],"minor_findings":[],"missing_evidence":[],"remediation_steps":[],"uncertainty":[]}
        initial=review_dir/"G1-run-initial.json";final=review_dir/"G1-run-final.json";researchctl.write_json(initial,base)
        bad={**base,"verdict":"pass-with-conditions","major_findings":["weak baseline"]};researchctl.write_json(final,bad)
        (project/"reviews"/"decision-log.md").write_text("# Review decision log\n\n## latest\n- Initial independent audit: `reviews/independent/G1-run-initial.json`\n- Final independent audit: `reviews/independent/G1-run-final.json`\n  - unresolved: baseline remains\n",encoding="utf-8")
        errors=[];researchctl.independent_audit_errors(project,"G1",errors)
        self.assertTrue(any("no fatal/major" in error for error in errors));self.assertTrue(any("unresolved" in error for error in errors))

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
