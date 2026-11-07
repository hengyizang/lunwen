"""Paper isolation retains earlier evidence and global scientific issue integrity."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import incremental_evidence as evidence, research_increments as increments
from scripts import research_extensions as extensions
from scripts import literature_feedback as feedback, figure_story as story, writing_review_actions as actions
from scripts import data_cleaning_runtime as cleaning, data_contracts
from scripts import research_support as support
from scripts import empirical_workflow as empirical
from scripts.research_artifacts import read, sha, write
from tests import test_research_increments as increment_fixtures
from tests import test_research_iteration as iteration_fixtures
from tests import test_figure_story as figure_fixtures
from tests import test_writing_review_actions as writing_fixtures
from tests import test_ccfa_science as science_fixtures
from tests import test_data_cleaning_runtime as cleaning_fixtures
from tests import test_research_search_tree as tree_fixtures
from tests import test_research_support as support_fixtures
from tests import test_empirical_workflow as empirical_fixtures


class IndependentSupportReaderTests(unittest.TestCase):
    def fixture(self, kind="increments"):
        module, name = {"increments": (increment_fixtures, "IncrementTests"),
                        "iteration": (iteration_fixtures, "ResearchIterationTests"),
                        "figure": (figure_fixtures, "FigureStoryTests"),
                        "writing": (writing_fixtures, "WritingReviewActionTests"),
                        "science": (science_fixtures, "CCFAScienceTests"),
                        "cleaning": (cleaning_fixtures, "StandaloneCleaningTests"),
                        "tree": (tree_fixtures, "ResearchSearchTreeTests"),
                        "support": (support_fixtures, "ResearchSupportTests"),
                        "empirical": (empirical_fixtures, "EmpiricalWorkflowTests")}[kind]
        case = getattr(module, name)()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def independent(self, project, active="P02"):
        path = project / "state/run.json"
        state = read(path) if path.is_file() else {}
        state.update(paper_execution_mode="independent", paper_count=2, active_paper=active, gate="G5")
        write(path, state)
        for paper in ("P01", "P02"):
            (project / "papers" / paper).mkdir(parents=True, exist_ok=True)

    def failed_observation(self, case):
        project = case.project
        attempt = {"attempt_id": "P01-failed-001", "run_id": "P01-run", "paper_id": "P01", "status": "failed",
                   "input_integrity": {"passed": False}, "outputs": [], "error": "Recorded failed fixture"}
        receipt = project / "experiments/runs/P01-failed-001/run.json"
        write(receipt, attempt)
        case.put("experiments/papers/P01/registry.jsonl", json.dumps(attempt) + "\n")
        write(project / "experiments/papers/P01/plan.json", {"runs": [{"run_id": "P01-run", "paper_id": "P01"}]})
        line = next(i for i, value in enumerate(receipt.read_text().splitlines(), 1) if '"error"' in value)
        row = case.lineage()
        row["nodes"][0].update(kind="project_observation", research_state="failed", attempt_id=attempt["attempt_id"],
            evidence=[{"path": receipt.relative_to(project).as_posix(), "sha256": sha(receipt), "kind": "source_lines",
                       "start_line": line, "end_line": line, "quote": "Recorded failed fixture"}])
        return row, attempt, receipt

    def test_earlier_paper_failed_lineage_uses_its_own_plan_while_another_is_active(self):
        case = self.fixture()
        self.independent(case.project)
        row, attempt, _ = self.failed_observation(case)
        write(case.project / "experiments/papers/P02/plan.json", {"runs": []})
        self.assertEqual(evidence.lineage(case.project, row)["nodes"][0]["research_state"], "failed")
        case.put("experiments/papers/P02/registry.jsonl", json.dumps(attempt) + "\n")
        with self.assertRaisesRegex(ValueError, "one matching"):
            evidence.lineage(case.project, row)

    def test_dependency_and_handoff_keep_earlier_failed_attempts(self):
        case = self.fixture()
        self.independent(case.project)
        _, attempt, receipt = self.failed_observation(case)
        graph = {"id": "cross-paper", "nodes": [{"id": "old-failure", "kind": "failure",
            "meaning": "An earlier failed run remains visible", "paper_ids": ["P01"], "depends_on": [],
            "attempt_id": attempt["attempt_id"], "source": {"path": receipt.relative_to(case.project).as_posix(), "sha256": sha(receipt)}}]}
        self.assertEqual(increments.dependencies(case.project, graph)["status"], "current")
        self.assertEqual(increments.handoff(case.project, {})["registered_attempt_counts"]["failed"], 1)

    def test_feedback_matches_previous_paper_registry_and_rejects_duplicate_identity(self):
        case = self.fixture()
        self.independent(case.project)
        output = case.project / "results/P01/value.json"
        write(output, {"fixture_observation": 1})
        attempt = {"attempt_id": "P01-success", "paper_id": "P01", "status": "succeeded",
                   "input_integrity": {"passed": True}, "approved_plan_sha256": "a" * 64,
                   "outputs": [{"path": output.relative_to(case.project).as_posix(), "sha256": sha(output)}]}
        receipt = case.project / "experiments/runs/P01-success/run.json"
        write(receipt, attempt)
        case.put("experiments/papers/P01/registry.jsonl", json.dumps(attempt) + "\n")
        bindings = [{"path": receipt.relative_to(case.project).as_posix()}]
        feedback._experiment_evidence(case.project, bindings, ["P01"])
        case.put("experiments/papers/P02/registry.jsonl", json.dumps(attempt) + "\n")
        with self.assertRaisesRegex(ValueError, "registered same-paper"):
            feedback._experiment_evidence(case.project, bindings, ["P01"])

    def test_other_paper_increment_draft_does_not_block_current_paper(self):
        case = self.fixture()
        self.independent(case.project, "P01")
        case.spec["arguments"] = [case.argument(), {"id": "A2", "paper_id": "P02"}]
        case.spec["lineage"] = [case.lineage()]
        case.save()
        report = increments.refresh(case.project)
        self.assertTrue(report["errors"])
        self.assertEqual(increments.gate_errors(case.project, "G5", "P01"), [])
        self.assertTrue(increments.gate_errors(case.project, "G5", "P02"))
        case.spec["ingestion"] = [{"id": "broken-shared-source"}]
        case.save()
        increments.refresh(case.project)
        self.assertTrue(increments.gate_errors(case.project, "G5", "P01"))

    def test_increment_owner_relabel_cannot_hide_previously_recorded_error(self):
        case = self.fixture()
        self.independent(case.project, "P01")
        case.spec["arguments"] = [{"id": "inherited", "paper_id": "P01"}]
        case.save()
        increments.refresh(case.project)
        case.spec["arguments"][0]["paper_id"] = "P02"
        case.save()
        for _ in range(2):
            increments.refresh(case.project)
            self.assertIn("ownership stable", " ".join(increments.gate_errors(case.project, "G3", "P01")))

    def review_issue(self, case, paper="P02"):
        source = case.put("evidence/review.txt", "The recorded concern remains unresolved.\n")
        return {"id": "issue", "paper_id": paper, "perspective": "statistics", "severity": "major", "status": "open",
                "question": "Is the unit independent?", "required_action": "Verify actual unit identifiers",
                "evidence": [{**source, "locator": "line 1", "quote": "The recorded concern remains unresolved."}]}

    def test_extension_scopes_drafts_and_findings_but_keeps_shared_source_integrity(self):
        case = self.fixture()
        self.independent(case.project, "P01")
        issue = self.review_issue(case)
        spec = {"schema_version": "1.0", "methods": [{"id": "future-design", "paper_id": "P02"}], "review_findings": [issue]}
        write(case.project / extensions.INPUT, spec)
        report = extensions.refresh(case.project)
        self.assertTrue(report["errors"])
        self.assertEqual(extensions.gate_errors(case.project), [])
        spec["review_findings"] = []
        write(case.project / extensions.INPUT, spec)
        report = extensions.refresh(case.project)
        self.assertEqual(report["retained_review_findings"][0]["id"], "issue")
        self.assertEqual(extensions.gate_errors(case.project), [])
        spec["review_findings"] = [issue]
        write(case.project / extensions.INPUT, spec)
        case.put("evidence/review.txt", "Changed underlying evidence.\n")
        self.assertIn("hash", " ".join(extensions.gate_errors(case.project)))

    def test_extension_finding_owner_cannot_change_or_gain_a_narrow_scope(self):
        for owner in ("P01", None):
            with self.subTest(owner=owner):
                case = self.fixture()
                self.independent(case.project, "P01")
                issue = self.review_issue(case, owner)
                spec = {"schema_version": "1.0", "review_findings": [issue]}
                write(case.project / extensions.INPUT, spec)
                extensions.refresh(case.project)
                issue["paper_id"] = "P02"
                write(case.project / extensions.INPUT, spec)
                for _ in range(2):
                    report = extensions.refresh(case.project)
                    self.assertTrue(report["retained_review_findings"])
                    self.assertIn("paper scope stable", " ".join(extensions.gate_errors(case.project)))

    def test_iteration_request_binds_explicit_paper_canonical_files(self):
        case = self.fixture("iteration")
        case.attempt("one")
        for name in ("plan.json", "budget.json", "registry.jsonl"):
            source = case.project / "experiments" / name
            target = case.project / "experiments/papers/P01" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
        self.independent(case.project)
        write(case.project / "experiments/papers/P02/plan.json", {"runs": []})
        case.request["paper_id"] = "P01"
        write(case.project / case.relative, case.request)
        result = case.prepare()
        sources = {row["path"] for row in result["source_bindings"]}
        self.assertTrue({"experiments/papers/P01/plan.json", "experiments/papers/P01/budget.json", "experiments/papers/P01/registry.jsonl"} <= sources)
        self.assertNotIn("experiments/plan.json", sources)
        self.assertEqual(result["attempts"][0]["analysis_phase"], ["confirmatory"])
        self.assertEqual(read(case.project / "state/run.json")["active_paper"], "P02")

    def test_iteration_keeps_archived_scoped_plan_and_its_original_phase(self):
        case = self.fixture("iteration")
        old = case.attempt("one", status="failed", exit_code=1)
        for name in ("plan.json", "budget.json", "registry.jsonl"):
            target = case.project / "experiments/papers/P01" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            (case.project / "experiments" / name).rename(target)
        self.independent(case.project, "P01")
        frozen = ["experiments/papers/P01/plan.json", "experiments/papers/P01/registry.jsonl",
                  "data/development.csv", "experiments/model.py", "state/run.json", "papers/P01/preregistration.json",
                  "papers/P01/experiment-evidence-plan.json", "papers/P01/experiments/main.json"]
        files = []
        for relative in frozen:
            archive = "experiments/history/v001/files/" + relative
            target = case.project / archive
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((case.project / relative).read_bytes())
            files.append({"path": relative, "sha256": sha(target), "archive": archive})
        manifest = {"version": "v001", "files": files,
                    "attempt_receipts": [{"path": "experiments/runs/one-attempt-001/run.json",
                                          "sha256": sha(case.project / "experiments/runs/one-attempt-001/run.json")}],
                    "retained_outputs": []}
        write(case.project / "experiments/history/v001/manifest.json", manifest)
        write(case.project / "state/primary-recovery/versions/v001.json",
              {"manifest_sha256": sha(case.project / "experiments/history/v001/manifest.json")})
        (case.project / "experiments/papers/P01/registry.jsonl").write_text("")
        case.plan["runs"] = [run for run in case.plan["runs"] if run["run_id"] != "one"]
        write(case.project / "experiments/papers/P01/plan.json", case.plan)
        result = case.prepare()
        attempt = next(row for row in result["attempts"] if row["attempt_id"] == old["attempt_id"])
        self.assertEqual(attempt["history_version"], "v001")
        self.assertEqual(attempt["analysis_phase"], ["confirmatory"])
        self.assertIn("experiments/history/v001/files/experiments/papers/P01/plan.json",
                      {row["path"] for row in result["source_bindings"]})

    def test_figure_story_requires_the_explicit_papers_canonical_claim_matrix(self):
        case = self.fixture("figure")
        self.independent(case.project)
        request = case.request()
        request["claims"] = case.text("claims/papers/P01/claim-evidence.csv", (case.project / case.claims["path"]).read_text())
        report = story.build_report(case.project, request)
        self.assertIn("claims/papers/P01/claim-evidence.csv", {row["path"] for row in report["inputs"]})
        request["claims"] = case.claims
        with self.assertRaisesRegex(ValueError, "canonical"):
            story.build_report(case.project, request)

    def test_writing_action_binds_each_declared_papers_claims_with_canonical_paths(self):
        case = self.fixture("writing")
        self.independent(case.project)
        case.text("claims/papers/P01/claim-evidence.csv", "claim_id,paper_id,claim\nC1,P01,Scoped first claim\n")
        case.text("claims/papers/P02/claim-evidence.csv", "claim_id,paper_id,claim\nC2,P02,Scoped second claim\n")
        action = case.action()
        result = actions.assess(case.project, action)
        paths = {row["path"] for row in result["inputs"]}
        self.assertIn("claims/papers/P01/claim-evidence.csv", paths)
        self.assertNotIn("claims/claim-evidence.csv", paths)
        action["scope"].update(paper_ids=["P01", "P02"], claim_ids=["C1", "C2"])
        result = actions.assess(case.project, action)
        self.assertTrue({"claims/papers/P01/claim-evidence.csv", "claims/papers/P02/claim-evidence.csv"}
                        <= {row["path"] for row in result["inputs"]})

    def test_measured_candidate_binds_its_paper_plan_and_registry_while_another_is_active(self):
        case = self.fixture("science")
        self.independent(case.project)
        config = case.json("experiments/config-A.json", {"candidate_id": "A"})
        plan = case.json("experiments/papers/P01/plan.json", {"runs": [{"run_id": "P01-trial", "paper_id": "P01", "inputs": [config]}]})
        measured = case.json("results/P01/trial.json", {"fixture": True})
        run = {"run_id": "P01-trial", "attempt_id": "P01-trial-001", "paper_id": "P01", "status": "succeeded",
               "approved_plan_sha256": plan["sha256"], "input_integrity": {"passed": True}, "inputs": [config], "outputs": [measured]}
        receipt = case.json("experiments/runs/P01-trial-001/run.json", run)
        case.text("experiments/papers/P01/registry.jsonl", json.dumps(run) + "\n")
        candidate = case.seed()
        candidate.update(status="measured", measurement={"receipt": receipt, "run_id": "P01-trial", "configuration": config})
        result = case.run_op("lineage", {"candidates": [candidate]})["report"]
        self.assertEqual(result["result"]["measured_candidates"], ["A"])
        paths = {row["path"] for row in result["inputs"]}
        self.assertTrue({"experiments/papers/P01/plan.json", "experiments/papers/P01/registry.jsonl"} <= paths)
        self.assertNotIn("experiments/plan.json", paths)

    def test_search_tree_binds_the_iteration_reports_explicit_paper_plan(self):
        case = self.fixture("tree")
        for name in ("plan.json", "budget.json", "registry.jsonl"):
            target = case.project / "experiments/papers/P01" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            (case.project / "experiments" / name).rename(target)
        self.independent(case.project)
        write(case.project / "experiments/papers/P02/plan.json", {"runs": []})
        case.fixture.request["paper_id"] = "P01"
        write(case.project / case.fixture.relative, case.fixture.request)
        case.request["iteration_report"] = case.fixture.prepare()["report_path"]
        case.save()
        result = case.prepare()
        self.assertEqual(result["plan_binding"]["path"], "experiments/papers/P01/plan.json")
        self.assertEqual(result["plan_binding"]["sha256"], sha(case.project / result["plan_binding"]["path"]))
        self.assertEqual(result["all_attempt_count"], 3)

    def test_standalone_cleaning_uses_the_same_frozen_registry_as_controller_audit(self):
        case = self.fixture("cleaning")
        self.independent(case.project, "P01")
        snapshot = case.project / "experiments/papers/P01/datasets.jsonl"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_bytes((case.project / "data/datasets.jsonl").read_bytes())
        audit = data_contracts.audit(case.project, "fixture")
        self.assertTrue(audit["pass"], audit["errors"])
        (case.project / "data/datasets.jsonl").write_text('not the frozen registry\n')
        (case.project / "state/run.json").unlink()
        script = case.project / "analysis/data_cleaning_runtime.py"
        script.parent.mkdir()
        script.write_bytes(Path(cleaning.__file__).read_bytes())
        environment = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "RESEARCH_OS_RUN_ID"}}
        environment["RESEARCH_OS_RUN_ID"] = "P01-cleaning-fixture"
        result = subprocess.run([sys.executable, str(script), "--contract", "data/contracts/fixture.json", "--dataset-id", "fixture",
            "--output", case.output, "--receipt", case.receipt], cwd=case.project, env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = read(case.project / case.receipt)
        self.assertEqual(receipt["inputs"], audit["inputs"])
        self.assertEqual(receipt["inputs"][-1]["path"], "experiments/papers/P01/datasets.jsonl")

    def test_cleaning_does_not_fallback_to_mutable_registry_or_accept_another_paper_snapshot(self):
        case = self.fixture("cleaning")
        self.independent(case.project, "P01")
        with patch.dict(os.environ, {"RESEARCH_OS_RUN_ID": "P01-clean"}):
            with self.assertRaisesRegex(ValueError, "unavailable runtime path"):
                cleaning.execute(case.project, "data/contracts/fixture.json", "fixture", case.output, case.receipt)
            with self.assertRaisesRegex(ValueError, "different paper"):
                cleaning.execute(case.project, "data/contracts/fixture.json", "fixture", case.output, case.receipt,
                                 dataset_registry="data/datasets.jsonl")
        snapshot = case.project / "experiments/papers/P02/datasets.jsonl"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_bytes((case.project / "data/datasets.jsonl").read_bytes())
        with patch.dict(os.environ, {"RESEARCH_OS_RUN_ID": "P01-clean"}), self.assertRaisesRegex(ValueError, "different paper"):
            cleaning.execute(case.project, "data/contracts/fixture.json", "fixture", case.output, case.receipt,
                             dataset_registry="experiments/papers/P02/datasets.jsonl")

    def test_shared_fair_inventory_retains_future_paper_datasets(self):
        case = self.fixture("support")
        self.independent(case.project, "P01")
        (case.project / "data/datasets.jsonl").write_text(json.dumps({"dataset_id": "future-paper-dataset"}) + "\n")
        write(case.project / "experiments/papers/P01/datasets.jsonl", {})
        values, binding = support._datasets(case.project)
        self.assertIn("future-paper-dataset", values)
        self.assertEqual(binding["path"], "data/datasets.jsonl")

    def test_cleaning_preflight_accepts_only_the_hash_bound_explicit_paper_registry(self):
        case = self.fixture("empirical")
        self.independent(case.project, "P01")
        snapshot = case.project / "experiments/papers/P01/datasets.jsonl"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_bytes((case.project / "data/datasets.jsonl").read_bytes())
        run = case.cleaning_run()
        run["run_id"] = "P01-cleaning"
        self.independent(case.project, "P02")
        empirical.preflight_run(case.project, run)
        run["argv"].extend(["--dataset-registry", "experiments/papers/P01/datasets.jsonl"])
        empirical.preflight_run(case.project, run)
        for wrong_path in ("data/datasets.jsonl", "experiments/papers/P02/datasets.jsonl"):
            broken = copy.deepcopy(run)
            broken["argv"][-1] = wrong_path
            with self.assertRaisesRegex(ValueError, "canonical dataset snapshot"):
                empirical.preflight_run(case.project, broken)
        broken = copy.deepcopy(run)
        next(row for row in broken["inputs"] if row["path"] == "experiments/papers/P01/datasets.jsonl")["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "every frozen source"):
            empirical.preflight_run(case.project, broken)


if __name__ == "__main__":
    unittest.main()
