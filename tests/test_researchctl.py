from __future__ import annotations

import json
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

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
        value["preferred_domains"]=["Fixture mechanical engineering"]
        value["candidate_application_routes"]=["Fixture doctoral programme"]
        value.update({"status":"ready_for_review","research_goal":"Develop a rigorous doctoral research programme.","researcher_background":"Mechanical engineering and data/AI.","available_skills":["Python","machine learning","mechanical engineering"],"time_horizon_years":3,"weekly_hours":30,"cash_budget_usd":1000,"cloud_compute_budget_usd":200,"local_compute":{"gpu":"none","ram_gb":16,"storage_gb":512},"ranking_weights":{"funded_position_supply":0.25,"job_market_and_salary":0.25,"future_growth_potential":0.15,"phd_position_competition":0.075,"job_market_competition":0.075,"background_fit":0.10,"application_route_fit":0.10}})
        researchctl.write_json(path,value)

    def test_gate_check_and_ready_group_repeated_checks_and_keep_original_json_details(self):
        state = {"project": "test-phd", "stage": "topic-intelligence", "gate": "G1", "status": "awaiting_work"}
        errors = [f"record {index} requires a recorded screening decision" for index in range(118)]
        with patch.object(researchctl, "load_state", return_value=state), \
             patch.object(researchctl, "gate_errors", return_value=errors), \
             patch.object(researchctl, "save_state") as save:
            for command in ("gate-check", "ready"):
                with self.subTest(command=command):
                    output, error_output = io.StringIO(), io.StringIO()
                    with redirect_stdout(output), redirect_stderr(error_output):
                        code = researchctl.main([command, "--project", "test-phd"])
                    self.assertEqual(code, 2)
                    self.assertEqual(output.getvalue().count("  - "), 1)
                    self.assertIn("118 check messages", output.getvalue())
                    self.assertIn("集中核对检索结果", output.getvalue())
                    self.assertNotIn("record 117", output.getvalue())
                    self.assertIn("1 issue group(s), 118 check messages", error_output.getvalue())
                    self.assertNotIn("requirement", error_output.getvalue())
                    self.assertIn("status --project test-phd --json", error_output.getvalue())
            save.assert_not_called()
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(researchctl.main(["status", "--project", "test-phd", "--json"]), 0)
            details = json.loads(output.getvalue())
            self.assertFalse(details["gate_ready"])
            self.assertEqual(details["gate_errors"], errors)
            self.assertEqual(len(details["gate_error_groups"]), 1)
            self.assertEqual(details["gate_error_groups"][0]["checks"], errors)

    def test_advance_rechecks_expired_evidence_after_approval(self) -> None:
        project = self.init_project()
        self.complete_constraints(project)
        researchctl.mark_ready(types.SimpleNamespace(project="test-phd", note="ready"))
        with patch.object(researchctl, "gate_errors", return_value=["evidence expired"]):
            with self.assertRaisesRegex(researchctl.ResearchCtlError, "no longer pass"):
                researchctl.advance(types.SimpleNamespace(project="test-phd"))
        self.assertEqual(researchctl.load_state("test-phd")["gate"], "G0")

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
        self.assertEqual(contract["target_jcr_quartile"], "Q1")
        self.assertFalse(contract["cloud_feasibility"]["current_paper_cloud_executable"])
        spending = json.loads((project / "state" / "model-spend-control.json").read_text())
        self.assertEqual(spending["authorized_ceiling_cny"], 0)
        self.assertTrue((project / "papers" / "P01" / "experiments").is_dir())

    def test_new_project_exposes_current_contracts_without_inventing_evidence(self) -> None:
        project = self.init_project(paper_count=6)
        state = researchctl.load_state("test-phd")
        self.assertEqual(state["approved_gates"], [])
        shortlist = researchctl.read_json(project / "program/topic-shortlist.json")
        self.assertEqual(shortlist["candidates"], [])
        self.assertEqual(shortlist["selection_decision"]["chosen_candidate_id"], "")
        feasibility = shortlist["selected_direction_cloud_feasibility"]
        self.assertFalse(feasibility["current_papers_feasible"])
        self.assertEqual(feasibility["feasibility_evidence"]["data_access"], [])
        self.assertEqual(feasibility["feasibility_evidence"]["pilot"]["status"], "not_run")
        matrix = researchctl.read_json(project / "program/novelty-claim-matrix.json")
        self.assertEqual((matrix["schema_version"], matrix["status"], matrix["claims"]), ("1.1", "draft", []))
        self.assertEqual(matrix["search_saturation"]["retrieval_dispositions"], [])
        self.assertEqual(matrix["search_saturation"]["search_rounds"], [])
        synthesis = researchctl.read_json(project / "program/paper-map.json")["thesis_synthesis"]
        self.assertEqual(synthesis["argument_links"], [])
        self.assertEqual(synthesis["evidence_alignment"], [])
        for relative in ("program/core-thesis.json", "program/extension-thesis.json", "papers/P01/paper-contract.json"):
            record = researchctl.read_json(project / relative)
            self.assertEqual(set(record["negative_result_plan"]),
                             {"informative_if_unsupported", "precision_limitations", "stop_rule", "claim_boundary"})
            self.assertFalse(any(record["negative_result_plan"].values()))
        contract = researchctl.read_json(project / "papers/P01/paper-contract.json")
        self.assertEqual(contract["scientific_bindings"],
                         {"schema_version": "1.0", "hypotheses": [], "falsification_conditions": []})
        self.assertEqual(contract["dependency_bindings"], [])
        self.assertIn("comparison_ids", (project / "claims/claim-evidence.csv").read_text(encoding="utf-8").splitlines()[0].split(","))
        self.assertEqual((project / "experiments/registry.jsonl").stat().st_size, 0)
        self.assertEqual((project / "evidence/literature-api-ledger.jsonl").stat().st_size, 0)
        self.assertTrue(researchctl.gate_errors("test-phd", "G1"))

    def test_each_paper_topic_needs_a_separate_current_approval(self) -> None:
        project = self.init_project(paper_count=3)
        state = researchctl.load_state("test-phd")
        state.update(gate="G2", stage="paper-architecture", stage_index=2)
        researchctl.save_state("test-phd", state)
        with patch.object(researchctl, "gate_errors", return_value=[]), patch("scripts.scientific_scope.seal_approval") as seal:
            researchctl.mark_ready(types.SimpleNamespace(project="test-phd", note=""))
            for paper in ("P01", "P02"):
                researchctl.approve(types.SimpleNamespace(project="test-phd", gate="G2", paper=paper, actor="Human", note=""))
            self.assertEqual(researchctl.load_state("test-phd")["status"], "awaiting_approval")
            contract = project / "papers/P01/paper-contract.json"
            value = json.loads(contract.read_text(encoding="utf-8")); value["research_question"] = "A changed topic?"
            researchctl.write_json(contract, value)
            with self.assertRaisesRegex(researchctl.ResearchCtlError, "changed after ready"):
                researchctl.approve(types.SimpleNamespace(project="test-phd", gate="G2", paper="P03", actor="Human", note=""))
            researchctl.mark_ready(types.SimpleNamespace(project="test-phd", note=""))
            for paper in ("P01", "P02", "P03"):
                researchctl.approve(types.SimpleNamespace(project="test-phd", gate="G2", paper=paper, actor="Human", note=""))
            state = researchctl.load_state("test-phd")
            self.assertEqual(state["status"], "approved")
            self.assertEqual({v["paper_id"] for v in state["approvals"][-1]["paper_topic_approvals"]}, {"P01", "P02", "P03"})
            seal.assert_called_once()

    def prepare_automatic_g3_compute(self, project: Path) -> None:
        self.complete_constraints(project)
        state = researchctl.load_state("test-phd")
        state.update(gate="G3", stage="experiment-design", stage_index=3,
                     approved_gates=["G0"], approvals=[{"gate": "G0", "actor": "Owner", "artifact_sha256": "a" * 64}])
        researchctl.save_state("test-phd", state)
        researchctl.write_json(project / "state/continuation.json", {
            "schema_version": "1.0", "actor": "Owner",
            "constraints_sha256": researchctl.file_sha256(project / "intake/constraints.json"),
            "g0_approval_artifact_sha256": "a" * 64})
        researchctl.write_json(project / "experiments/plan.json", {"schema_version": "1.0", "status": "ready_for_review", "runs": [{
            "run_id": "baseline", "paper_id": "P01", "argv": [sys.executable, "-c", "print('fixture')"],
            "cwd": ".", "seed": 1, "timeout_seconds": 30, "estimated_cost_usd": 10,
            "isolation": {"kind": "host"}, "inputs": [], "expected_outputs": ["results/fixture.json"]}]})
        researchctl.write_json(project / "experiments/budget.json", {
            "schema_version": "1.0", "status": "ready_for_review", "hard_ceiling_usd": 100})

    def test_automatic_g3_seals_existing_compute_authority_without_increasing_it(self) -> None:
        project = self.init_project()
        self.prepare_automatic_g3_compute(project)
        before = (project / "intake/constraints.json").read_bytes()
        with patch.object(researchctl, "gate_errors", return_value=[]):
            researchctl.mark_ready(types.SimpleNamespace(project="test-phd", note="Deterministic test fixture"))
        state = researchctl.load_state("test-phd")
        self.assertEqual(state["status"], "approved")
        approval = state["approvals"][-1]
        self.assertEqual(approval["decision_type"], "deterministic")
        self.assertEqual(approval["compute_budget_authority"]["cloud_compute_budget_usd"], 200)
        self.assertEqual(approval["compute_budget_authority"]["actor"], "project-total-cost-control")
        self.assertEqual((project / "intake/constraints.json").read_bytes(), before)

    def test_g3_checks_actual_estimates_against_total_without_another_budget_confirmation(self) -> None:
        project = self.init_project()
        self.prepare_automatic_g3_compute(project)
        researchctl.write_json(project / "experiments/budget.json", {
            "schema_version": "1.0", "status": "ready_for_review", "hard_ceiling_usd": 201})
        plan = researchctl.read_json(project / "experiments/plan.json")
        plan["runs"][0]["estimated_cost_usd"] = 201
        researchctl.write_json(project / "experiments/plan.json", plan)
        errors = researchctl.gate_errors("test-phd", "G3")
        self.assertTrue(any("exceed the project total" in error for error in errors))
        with self.assertRaises(researchctl.ResearchCtlError):
            researchctl.mark_ready(types.SimpleNamespace(project="test-phd", note=""))
        self.assertNotIn("G3", researchctl.load_state("test-phd")["approved_gates"])
        (project / "state/continuation.json").unlink()
        plan["runs"][0]["estimated_cost_usd"] = 10
        researchctl.write_json(project / "experiments/plan.json", plan)
        errors = researchctl.gate_errors("test-phd", "G3")
        self.assertFalse(any("experiment compute authority" in error for error in errors))

    def test_six_paper_initialization_assigns_three_q1_and_three_q2_targets(self) -> None:
        project = self.init_project(paper_count=6)
        targets = [
            json.loads((project / "papers" / f"P{index:02d}" / "paper-contract.json").read_text())["target_jcr_quartile"]
            for index in range(1, 7)
        ]
        self.assertEqual(targets, ["Q1", "Q1", "Q1", "Q2", "Q2", "Q2"])

    def test_cloud_only_g0_requires_no_local_machine_resources(self) -> None:
        project = self.init_project()
        path = project / "intake" / "constraints.json"
        value = json.loads(path.read_text())
        self.assertEqual(value["execution_mode"], "cloud_only")
        self.assertIsNone(value["cloud_compute_budget_usd"])
        capabilities = json.loads((project / "intake" / "capabilities.json").read_text())
        self.assertEqual(capabilities["os"], "GitHub Actions Linux runner")

        self.complete_constraints(project)
        value = json.loads(path.read_text())
        value["local_compute"] = {"gpu": None, "ram_gb": None, "storage_gb": None}
        researchctl.write_json(path, value)
        self.assertEqual(researchctl.gate_errors("test-phd", "G0"), [])

        value["execution_mode"] = "hybrid"
        researchctl.write_json(path, value)
        errors = researchctl.gate_errors("test-phd", "G0")
        self.assertTrue(any("local_compute.ram_gb" in error for error in errors))

    def test_short_submission_deadline_and_topic_quality_gates(self) -> None:
        project = self.init_project()
        self.complete_constraints(project)
        path = project / "intake" / "constraints.json"
        value = json.loads(path.read_text())
        value["time_horizon_years"] = None
        value["target_submission_ready_date"] = "2026-10-07"
        value["cash_budget_usd"] = None
        value["model_api_budget_cny"] = 300
        value["cloud_compute_budget_usd"] = 0
        value["local_compute"] = {"gpu": None, "ram_gb": None, "storage_gb": None}
        researchctl.write_json(path, value)
        self.assertEqual(researchctl.gate_errors("test-phd", "G0"), [])

        value["topic_quality_requirements"]["current_papers_cloud_feasible_required"] = False
        researchctl.write_json(path, value)
        self.assertTrue(any("current_papers_cloud_feasible_required" in error for error in researchctl.gate_errors("test-phd", "G0")))
        value["topic_quality_requirements"]["current_papers_cloud_feasible_required"] = True

        value["topic_quality_requirements"]["original_contribution_required"] = False
        researchctl.write_json(path, value)
        self.assertTrue(any("original_contribution_required" in error for error in researchctl.gate_errors("test-phd", "G0")))
        value["topic_quality_requirements"]["original_contribution_required"] = True
        value["target_submission_ready_date"] = "2026-13-07"
        researchctl.write_json(path, value)
        self.assertTrue(any("target_submission_ready_date" in error for error in researchctl.gate_errors("test-phd", "G0")))

    def test_duplicate_project_is_rejected(self) -> None:
        self.init_project()
        with self.assertRaises(researchctl.ResearchCtlError):
            self.init_project()

    def test_cloud_system_hours_do_not_fabricate_human_weekly_availability(self) -> None:
        project = self.init_project()
        self.complete_constraints(project)
        path = project / "intake/constraints.json"
        value = json.loads(path.read_text())
        value.update({"human_review_mode": "on_request", "weekly_hours": None,
                      "system_execution_hours_per_day": 24})
        researchctl.write_json(path, value)
        self.assertEqual(researchctl.gate_errors("test-phd", "G0"), [])
        value["weekly_hours"] = 168
        researchctl.write_json(path, value)
        self.assertTrue(any("weekly_hours" in x for x in researchctl.gate_errors("test-phd", "G0")))
        value["weekly_hours"] = None
        value["execution_mode"] = "local"
        researchctl.write_json(path, value)
        self.assertTrue(any("on_request" in x for x in researchctl.gate_errors("test-phd", "G0")))
        value["execution_mode"] = "cloud_only"
        value["system_execution_hours_per_day"] = 25
        researchctl.write_json(path, value)
        self.assertTrue(any("system_execution_hours" in x for x in researchctl.gate_errors("test-phd", "G0")))

    def test_gate_requires_readiness_and_human_approval(self) -> None:
        project = self.init_project()
        with self.assertRaises(researchctl.ResearchCtlError):
            researchctl.advance(types.SimpleNamespace(project="test-phd"))

        self.complete_constraints(project)

        researchctl.mark_ready(
            types.SimpleNamespace(project="test-phd", note="prepared")
        )
        state = researchctl.load_state("test-phd")
        self.assertEqual(state["status"], "approved")
        self.assertEqual(state["approvals"][-1]["decision_type"], "deterministic")
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
        constraints["notes"].append("changed after approval")
        researchctl.write_json(constraints_path, constraints)
        with self.assertRaises(researchctl.ResearchCtlError):
            researchctl.advance(types.SimpleNamespace(project="test-phd"))

    def test_g0_rejects_status_only_with_unknown_constraints(self) -> None:
        project=self.init_project()
        path=project/"intake"/"constraints.json";value=json.loads(path.read_text());value["status"]="ready_for_review";researchctl.write_json(path,value)
        errors=researchctl.gate_errors("test-phd","G0")
        self.assertTrue(any("weekly_hours" in error for error in errors))

    def test_g5_observes_academic_style_without_blocking_scientific_work(self) -> None:
        self.init_project()
        state = researchctl.load_state("test-phd")
        state.update(
            {
                "stage_index": 5,
                "stage": "writing-and-review",
                "gate": "G5",
                "status": "awaiting_work",
                "active_paper": "P01",
                "writing_phases":{"P01":"submission"},
            }
        )
        researchctl.save_state("test-phd", state)
        warnings=[]
        errors = researchctl.gate_errors("test-phd", "G5",warnings=warnings)
        self.assertFalse(any("academic style audit" in error for error in errors))
        self.assertTrue(any("academic style audit" in warning for warning in warnings))

    def test_g5_does_not_use_planning_quartiles_as_scientific_thresholds(self) -> None:
        project = self.init_project(paper_count=6)
        paper_map = {
            "papers": [
                {
                    "paper_id": f"P{index:02d}",
                    "target_jcr_quartile": "Q1" if index <= 3 else "Q2",
                }
                for index in range(1, 7)
            ]
        }
        researchctl.write_json(project / "program" / "paper-map.json", paper_map)
        contract_path = project / "papers" / "P03" / "paper-contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["target_jcr_quartile"] = "Q2"
        researchctl.write_json(contract_path, contract)
        state = researchctl.load_state("test-phd")
        state.update(
            {
                "stage_index": 5,
                "stage": "writing-and-review",
                "gate": "G5",
                "active_paper": "P01",
                "writing_phases":{"P01":"submission"},
            }
        )
        researchctl.save_state("test-phd", state)
        errors = researchctl.gate_errors("test-phd", "G5")
        self.assertFalse(any("P03 target JCR quartile" in item for item in errors))
        self.assertFalse(any("at least 3 Q1" in item for item in errors))

    def test_change_after_ready_requires_fresh_human_review(self) -> None:
        project=self.init_project();self.complete_constraints(project)
        researchctl.mark_ready(types.SimpleNamespace(project="test-phd",note="ready"))
        path=project/"intake"/"constraints.json";value=json.loads(path.read_text());value["notes"].append("changed");researchctl.write_json(path,value)
        with self.assertRaisesRegex(researchctl.ResearchCtlError,"changed after approval"):
            researchctl.advance(types.SimpleNamespace(project="test-phd"))

    def test_reopen_returns_gate_to_model_editable_work(self) -> None:
        self.init_project();state=researchctl.load_state("test-phd");state.update(gate="G1",stage="topic-intelligence",stage_index=1);researchctl.save_state("test-phd",state)
        with patch.object(researchctl,"gate_errors",return_value=[]):researchctl.mark_ready(types.SimpleNamespace(project="test-phd",note="ready"))
        researchctl.reopen(types.SimpleNamespace(project="test-phd",note="Needs another model revision"))
        state=researchctl.load_state("test-phd");self.assertEqual(state["status"],"awaiting_work");self.assertNotIn("ready_artifact_sha256",state)

    def test_legacy_stage_review_is_observational_instead_of_a_second_stage_gate(self) -> None:
        project=self.init_project();review_dir=project/"reviews"/"independent";review_dir.mkdir(parents=True,exist_ok=True)
        base={"verdict":"revise","fatal_findings":[],"major_findings":[],"minor_findings":[],"missing_evidence":[],"remediation_steps":[],"uncertainty":[]}
        initial=review_dir/"G1-run-initial.json";final=review_dir/"G1-run-final.json";researchctl.write_json(initial,base)
        bad={**base,"verdict":"pass-with-conditions","major_findings":["weak baseline"]};researchctl.write_json(final,bad)
        (project/"reviews"/"decision-log.md").write_text("# Review decision log\n\n## latest\n- Initial independent audit: `reviews/independent/G1-run-initial.json`\n- Final independent audit: `reviews/independent/G1-run-final.json`\n  - unresolved: baseline remains\n",encoding="utf-8")
        errors=[];warnings=[];researchctl.independent_audit_errors(project,"G1",errors,warnings=warnings)
        self.assertEqual(errors,[])
        self.assertTrue(any("source-bound independent review" in warning for warning in warnings))
        # Bare legacy verdicts/logs cannot stand in for a current controller
        # receipt. Detailed final-verdict/notes tests live in test_review_receipts.

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

        with patch.object(researchctl, "gate_errors", return_value=[]):
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
            with patch.object(researchctl, "gate_errors", return_value=[]):
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

    def test_g3_malformed_dataset_manifest_does_not_crash_quality_validator(self) -> None:
        project = self.init_project(paper_count=1)
        state = researchctl.load_state("test-phd")
        state.update({"stage_index": 3, "stage": "experiment-design", "gate": "G3"})
        researchctl.save_state("test-phd", state)
        (project / "data" / "datasets.jsonl").write_text("{not-json}\n", encoding="utf-8")
        errors = researchctl.gate_errors("test-phd", "G3")
        self.assertTrue(any("invalid JSONL" in error for error in errors))
        self.assertTrue(any("research-quality evidence is invalid" in error for error in errors))

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
