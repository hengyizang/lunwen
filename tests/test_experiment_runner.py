from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from scripts import experiment_runner


class ExperimentRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        environment = mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "DR_OS_REQUIRE_REMOTE_RESERVATION": "0"})
        environment.start()
        self.addCleanup(environment.stop)
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
                    "isolation": {"kind": "host"},
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
        paper = project / "papers/P01"
        paper.mkdir(parents=True)
        evidence_plan = paper / "experiment-evidence-plan.json"
        evidence_plan.write_text('{"synthetic_unit_fixture": true}', encoding="utf-8")
        prereg = paper / "preregistration.json"
        prereg.write_text(json.dumps({"status": "frozen", "files": [
            {"path": "papers/P01/experiment-evidence-plan.json", "sha256": hashlib.sha256(evidence_plan.read_bytes()).hexdigest()}
        ]}), encoding="utf-8")
        state = {
            "stage": "experiment-execution",
            "gate": "G4",
            "status": "awaiting_work",
            "approvals": [
                {
                    "gate": "G3",
                    "frozen_protocol_sha256": {"papers/P01/preregistration.json": hashlib.sha256(prereg.read_bytes()).hexdigest()},
                    "experiment_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                    "experiment_budget_sha256": hashlib.sha256(
                        budget_path.read_bytes()
                    ).hexdigest(),
                }
            ]
        }
        (project / "state" / "run.json").write_text(json.dumps(state), encoding="utf-8")
        from scripts.acceptance_scope import prepare_scope
        prepare_scope(project,state)
        return project

    def test_approved_run_executes_and_is_registered(self) -> None:
        project = self.project()
        results = experiment_runner.execute("test-phd")
        self.assertEqual(results[0]["status"], "succeeded")
        self.assertEqual(results[0]["executor_isolation"]["kind"], "host")
        self.assertFalse(results[0]["executor_isolation"]["isolated_executor"])
        self.assertTrue(results[0]["input_integrity"]["passed"])
        self.assertTrue((project / "result.txt").is_file())
        registry = (project / "experiments" / "registry.jsonl").read_text()
        self.assertIn('"run_id": "baseline"', registry)

    def automatic_compute_authority(self, project: Path) -> dict:
        constraints = project / "intake/constraints.json"
        constraints.parent.mkdir()
        constraints.write_text(json.dumps({"cloud_compute_budget_usd": 2, "cash_budget_usd": 5}), encoding="utf-8")
        state_path = project / "state/run.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["approved_gates"].append("G0")
        state["approvals"].insert(0, {"gate": "G0", "actor": "Owner", "artifact_sha256": "a" * 64})
        state_path.write_text(json.dumps(state), encoding="utf-8")
        policy = {"schema_version": "1.0", "actor": "Owner",
                  "constraints_sha256": experiment_runner.sha256_file(constraints),
                  "g0_approval_artifact_sha256": "a" * 64}
        (project / "state/continuation.json").write_text(json.dumps(policy), encoding="utf-8")
        authority = experiment_runner.compute_budget_authority(project,
            json.loads((project / "experiments/budget.json").read_text(encoding="utf-8")),
            json.loads((project / "experiments/plan.json").read_text(encoding="utf-8")))
        approval = next(row for row in state["approvals"] if row["gate"] == "G3")
        approval.update(decision_type="deterministic", actor="deterministic-control-plane",
                        compute_budget_authority=authority)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return authority

    def test_automatic_g3_respects_existing_owner_compute_budget(self) -> None:
        project = self.project()
        self.automatic_compute_authority(project)
        self.assertEqual(experiment_runner.execute("test-phd")[0]["status"], "succeeded")

    def test_project_total_blocks_costs_even_when_plan_budget_is_larger(self) -> None:
        project = self.project()
        self.automatic_compute_authority(project)
        budget_path = project / "experiments/budget.json"
        budget = json.loads(budget_path.read_text(encoding="utf-8"))
        budget["hard_ceiling_usd"] = 3
        budget_path.write_text(json.dumps(budget), encoding="utf-8")
        plan_path = project / "experiments/plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["runs"][0]["estimated_cost_usd"] = 3
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        state_path = project / "state/run.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        approval = next(row for row in state["approvals"] if row["gate"] == "G3")
        approval["experiment_budget_sha256"] = experiment_runner.sha256_file(budget_path)
        approval["experiment_plan_sha256"] = experiment_runner.sha256_file(plan_path)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with mock.patch.object(experiment_runner, "run_one") as run:
            with self.assertRaisesRegex(experiment_runner.ExperimentError, "Budget ceiling exceeded"):
                experiment_runner.execute("test-phd")
        run.assert_not_called()
        self.assertFalse((project / "state/experiment-execution-lease.json").exists())

    def test_current_project_total_is_used_without_another_budget_review(self) -> None:
        project = self.project()
        self.automatic_compute_authority(project)
        constraints = project / "intake/constraints.json"
        value = json.loads(constraints.read_text(encoding="utf-8"))
        value["cloud_compute_budget_usd"] = 100
        constraints.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(experiment_runner.execute("test-phd")[0]["status"], "succeeded")
        self.assertFalse((project / "state/experiment-execution-lease.json").exists())

    def test_changed_total_ceiling_does_not_require_resealing_unchanged_science(self) -> None:
        project = self.project()
        self.automatic_compute_authority(project)
        constraints = project / "intake/constraints.json"
        value = json.loads(constraints.read_text(encoding="utf-8"))
        value["cloud_compute_budget_usd"] = 1
        constraints.write_text(json.dumps(value), encoding="utf-8")
        policy_path = project / "state/continuation.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["constraints_sha256"] = experiment_runner.sha256_file(constraints)
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        self.assertEqual(experiment_runner.execute("test-phd")[0]["status"], "succeeded")

    def test_automatic_compute_plan_must_fit_project_total_not_plan_subcap(self) -> None:
        project = self.project()
        self.automatic_compute_authority(project)
        budget = json.loads((project / "experiments/budget.json").read_text(encoding="utf-8"))
        plan = json.loads((project / "experiments/plan.json").read_text(encoding="utf-8"))
        plan["runs"][0]["estimated_cost_usd"] = 1.5
        self.assertEqual(experiment_runner.compute_budget_authority(project, budget, plan)["cloud_compute_budget_usd"], 2)
        plan["runs"][0]["estimated_cost_usd"] = 2.5
        with self.assertRaisesRegex(experiment_runner.ExperimentError, "project total"):
            experiment_runner.compute_budget_authority(project, budget, plan)
        constraints = project / "intake/constraints.json"
        value = json.loads(constraints.read_text(encoding="utf-8"))
        value["cloud_compute_budget_usd"] = 10
        value["cash_budget_usd"] = 0.5
        constraints.write_text(json.dumps(value), encoding="utf-8")
        policy_path = project / "state/continuation.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["constraints_sha256"] = experiment_runner.sha256_file(constraints)
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        with self.assertRaisesRegex(experiment_runner.ExperimentError, "compute or cash"):
            experiment_runner.compute_budget_authority(project, budget, plan)

    def test_automatic_compute_authority_needs_only_numeric_total_not_gate_confirmation(self) -> None:
        project = self.project()
        self.automatic_compute_authority(project)
        (project / "state/continuation.json").unlink()
        budget = json.loads((project / "experiments/budget.json").read_text(encoding="utf-8"))
        plan = json.loads((project / "experiments/plan.json").read_text(encoding="utf-8"))
        self.assertEqual(experiment_runner.compute_budget_authority(project, budget, plan)["cloud_compute_budget_usd"], 2)
        constraints = project / "intake/constraints.json"
        constraints.write_text('{"cloud_compute_budget_usd": true}', encoding="utf-8")
        with self.assertRaisesRegex(experiment_runner.ExperimentError, "finite non-negative"):
            experiment_runner.compute_budget_authority(project, budget, plan)

    def test_total_cost_accounts_failed_attempts_and_higher_reported_charges(self) -> None:
        project = self.project()
        registry = project / "experiments/registry.jsonl"
        rows = [{"status": "failed", "estimated_cost_usd": 0.2, "reported_cost_usd": 0.8},
                {"status": "timed_out", "estimated_cost_usd": 0.3, "reported_cost_usd": None}]
        registry.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        self.assertAlmostEqual(experiment_runner.prior_estimated_cost(registry), 1.1)
        registry.write_text('{"estimated_cost_usd": -1}', encoding="utf-8")
        with self.assertRaises(experiment_runner.ExperimentError):
            experiment_runner.prior_estimated_cost(registry)

    def test_paid_estimate_executes_under_total_without_per_plan_subcap(self) -> None:
        project = self.project()
        self.automatic_compute_authority(project)
        (project / "state/continuation.json").unlink()
        plan_path = project / "experiments/plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["runs"][0]["estimated_cost_usd"] = 1.5
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        state_path = project / "state/run.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        next(row for row in state["approvals"] if row.get("gate") == "G3")["experiment_plan_sha256"] = experiment_runner.sha256_file(plan_path)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        result = experiment_runner.execute("test-phd")[0]
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["cost_accounting"]["accounted_cost_usd"], 1.5)
        self.assertFalse(result["cost_accounting"]["actual_cost_known"])
        self.assertIsNone(result["reported_cost_usd"])

    def test_parent_run_counts_failed_supplemental_cost_before_launch(self) -> None:
        project = self.project()
        child_registry = project / "experiments/supplemental/P01/R001/s001/experiments/registry.jsonl"
        child_registry.parent.mkdir(parents=True)
        child_registry.write_text('{"status":"failed","estimated_cost_usd":0.7,"reported_cost_usd":null}\n', encoding="utf-8")
        plan_path = project / "experiments/plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["runs"][0]["estimated_cost_usd"] = 0.5
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        state_path = project / "state/run.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        next(row for row in state["approvals"] if row.get("gate") == "G3")["experiment_plan_sha256"] = experiment_runner.sha256_file(plan_path)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with mock.patch.object(experiment_runner, "run_one") as process:
            with self.assertRaisesRegex(experiment_runner.ExperimentError, "Budget ceiling exceeded"):
                experiment_runner.execute("test-phd")
        process.assert_not_called()
        self.assertFalse((project / "state/experiment-execution-lease.json").exists())

    def test_concurrent_execution_rejected_before_budget_check(self) -> None:
        project = self.project()
        entered = threading.Event()
        release = threading.Event()
        errors = []
        original_run = experiment_runner.run_one

        def run(*args):
            entered.set()
            release.wait(10)
            return original_run(*args)

        def first():
            try:
                experiment_runner.execute("test-phd")
            except Exception as exc:
                errors.append(exc)

        with mock.patch.object(experiment_runner, "run_one", side_effect=run):
            thread = threading.Thread(target=first)
            thread.start()
            try:
                self.assertTrue(entered.wait(10))
                with self.assertRaisesRegex(experiment_runner.ExperimentError, "unresolved interrupted execution"):
                    experiment_runner.execute("test-phd")
            finally:
                release.set()
                thread.join(10)
        self.assertFalse(errors)
        self.assertFalse((project / "state/experiment-execution-lease.json").exists())

    def test_interrupted_attempt_preserves_cost_and_blocks_retry(self) -> None:
        project = self.project()
        with mock.patch.object(experiment_runner, "run_one", side_effect=RuntimeError("interrupted")):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                experiment_runner.execute("test-phd")
        lease = json.loads((project / "state/experiment-execution-lease.json").read_text())
        self.assertEqual(lease["status"], "running")
        self.assertEqual(lease["run_id"], "baseline")
        self.assertEqual(lease["estimated_cost_usd"], 0)
        with self.assertRaisesRegex(experiment_runner.ExperimentError, "unresolved interrupted execution"):
            experiment_runner.execute("test-phd")

    def test_prestart_rejection_does_not_create_an_unknown_cost_lease(self) -> None:
        project = self.project()
        experiment_runner.execute("test-phd")
        registry = project / "experiments/registry.jsonl"
        before = registry.read_bytes()
        with mock.patch("scripts.cloud_checkpoint.sync_experiment_reservation") as reserve, mock.patch.object(
            experiment_runner.subprocess, "Popen"
        ) as process:
            with self.assertRaises(experiment_runner.ExperimentError):
                experiment_runner.execute("test-phd")
        reserve.assert_not_called()
        process.assert_not_called()
        self.assertFalse((project / "state/experiment-execution-lease.json").exists())
        self.assertEqual(registry.read_bytes(), before)

    def test_cloud_reservation_failure_blocks_before_process_start(self) -> None:
        from scripts.cloud_checkpoint import CheckpointError
        project = self.project()
        with mock.patch("scripts.cloud_checkpoint.sync_experiment_reservation",
                        side_effect=CheckpointError("push failed")), mock.patch.object(
                            experiment_runner, "run_one") as run:
            with self.assertRaisesRegex(experiment_runner.ExperimentError, "push failed"):
                experiment_runner.execute("test-phd")
        run.assert_not_called()
        self.assertEqual(json.loads((project / "state/experiment-execution-lease.json").read_text())["status"], "running")

    def test_cloud_completion_failure_preserves_ledger_and_blocks_retry(self) -> None:
        from scripts.cloud_checkpoint import CheckpointError
        project = self.project()
        saved = []
        def sync(current, *, completed):
            if completed:
                raise CheckpointError("completion push failed")
            saved.append((current / "state/experiment-execution-lease.json").read_bytes())
        with mock.patch("scripts.cloud_checkpoint.sync_experiment_reservation", side_effect=sync):
            with self.assertRaisesRegex(experiment_runner.ExperimentError, "completion push failed"):
                experiment_runner.execute("test-phd")
        lease = json.loads((project / "state/experiment-execution-lease.json").read_text())
        self.assertEqual(lease["status"], "completed")
        self.assertEqual(lease["registry_sha256"], hashlib.sha256((project / "experiments/registry.jsonl").read_bytes()).hexdigest())
        # Simulate a fresh runner restoring the last durable remote reservation.
        (project / "state/experiment-execution-lease.json").write_bytes(saved[0])
        with self.assertRaisesRegex(experiment_runner.ExperimentError, "unresolved interrupted execution"):
            experiment_runner.execute("test-phd")

    def test_cloud_reservation_and_completed_ledger_are_committed_together(self) -> None:
        project = self.project()
        base = Path(self.temp.name)
        remote, checkout = base / "remote.git", base / "checkout"
        def git(*args, cwd=None):
            return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, text=True).stdout
        git("init", "--bare", str(remote))
        git("init", str(checkout))
        git("-c", "user.name=test", "-c", "user.email=test@example.invalid",
            "commit", "--allow-empty", "-m", "initial", cwd=checkout)
        git("remote", "add", "origin", str(remote), cwd=checkout)
        git("push", "origin", "HEAD:refs/heads/cloud-state/test-phd", cwd=checkout)
        env = {"GITHUB_ACTIONS": "true", "DR_OS_REQUIRE_REMOTE_RESERVATION": "1",
               "DR_OS_STATE_WORKTREE": str(checkout), "DR_OS_STATE_BRANCH": "cloud-state/test-phd"}
        with mock.patch.dict(os.environ, env):
            experiment_runner.execute("test-phd")
        ref = "refs/heads/cloud-state/test-phd"
        lease = json.loads(git("--git-dir", str(remote), "show", ref + ":projects/test-phd/state/experiment-execution-lease.json"))
        ledger = subprocess.run(["git", "--git-dir", str(remote), "show", ref + ":projects/test-phd/experiments/registry.jsonl"],
                                capture_output=True, check=True).stdout
        self.assertEqual(lease["status"], "completed")
        self.assertEqual(lease["registry_sha256"], hashlib.sha256(ledger).hexdigest())
        (project / "state/experiment-execution-lease.json").write_text(json.dumps(lease), encoding="utf-8")
        with self.assertRaisesRegex(experiment_runner.ExperimentError, "unresolved interrupted execution"):
            experiment_runner.execute("test-phd")

    def test_windows_timeout_terminates_tree(self) -> None:
        process = mock.Mock(pid=123)
        result = mock.Mock(returncode=0)
        with mock.patch.object(experiment_runner.os, "name", "nt"), mock.patch.object(
            experiment_runner.subprocess, "run", return_value=result
        ) as run:
            experiment_runner.terminate_process_tree(process)
        self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "123", "/T", "/F"])
        process.kill.assert_not_called()

    def test_windows_tree_termination_failure_is_not_silenced(self) -> None:
        process = mock.Mock(pid=123)
        process.poll.return_value = None
        with mock.patch.object(experiment_runner.os, "name", "nt"), mock.patch.object(
            experiment_runner.subprocess, "run", return_value=mock.Mock(returncode=1)
        ):
            with self.assertRaises(experiment_runner.ProcessTreeTerminationError):
                experiment_runner.terminate_process_tree(process)
        process.kill.assert_called_once()
        process.wait.assert_called_once()

    @unittest.skipUnless(os.name == "nt", "Windows process tree test")
    def test_windows_successful_parent_cannot_leave_a_background_writer(self) -> None:
        project = self.project()
        plan_path = project / "experiments/plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        child = "import pathlib,time; time.sleep(2); pathlib.Path('late-child.txt').write_text('late')"
        plan["runs"][0]["argv"] = [sys.executable, "-c",
            "import pathlib,subprocess,sys; subprocess.Popen([sys.executable,'-c',sys.argv[1]]); pathlib.Path('result.txt').write_text('ok')", child]
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        state_path = project / "state/run.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        next(row for row in state["approvals"] if row["gate"] == "G3")["experiment_plan_sha256"] = experiment_runner.sha256_file(plan_path)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(experiment_runner.execute("test-phd")[0]["status"], "succeeded")
        time.sleep(2.2)
        self.assertFalse((project / "late-child.txt").exists())

    @unittest.skipUnless(os.name == "nt", "Windows process tree test")
    def test_windows_process_waits_for_job_before_executing(self) -> None:
        marker = Path(self.temp.name) / "started-before-job.txt"
        process = subprocess.Popen([sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('started')", str(marker)],
                                   creationflags=0x00000004)
        job = None
        try:
            time.sleep(0.1)
            self.assertFalse(marker.exists())
            self.assertIsNone(process.poll())
            job = experiment_runner.WindowsProcessJob(process, suspended=True)
            self.assertEqual(process.wait(timeout=10), 0)
            self.assertEqual(marker.read_text(), "started")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if job is not None:
                job.close()

    @unittest.skipUnless(os.name == "nt", "Windows process tree test")
    def test_windows_process_tree_child_does_not_survive(self) -> None:
        folder = Path(self.temp.name)
        ready, child_output = folder / "ready", folder / "child-output"
        child = "import pathlib,sys,time; time.sleep(3); pathlib.Path(sys.argv[1]).write_text('alive')"
        parent = ("import pathlib,subprocess,sys,time; "
                  "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[3]]); "
                  "pathlib.Path(sys.argv[2]).write_text('ready'); time.sleep(30)")
        process = subprocess.Popen([sys.executable, "-c", parent, child, str(ready), str(child_output)], creationflags=0x00000004)
        job = experiment_runner.WindowsProcessJob(process, suspended=True)
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready.exists())
            experiment_runner.terminate_process_tree(process, job)
            process.wait(timeout=10)
            time.sleep(3.5)
            self.assertFalse(child_output.exists())
        finally:
            job.close()
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_relative_project_root_keeps_executor_receipts_relative(self) -> None:
        project = self.project()
        input_path = project / "input.txt"
        input_path.write_text("approved", encoding="utf-8")
        plan_path = project / "experiments" / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["runs"][0]["inputs"] = [
            {"path": "input.txt", "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest()}
        ]
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        state_path = project / "state" / "run.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["approvals"][0]["experiment_plan_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        state_path.write_text(json.dumps(state), encoding="utf-8")
        previous = Path.cwd()
        try:
            os.chdir(project.parent)
            result = experiment_runner.execute("test-phd", project_root=Path("test-phd"))[0]
        finally:
            os.chdir(previous)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["inputs"][0]["path"], "input.txt")
        self.assertEqual(result["outputs"][0]["path"], "result.txt")
        self.assertEqual(result["cwd"], ".")
        self.assertTrue(result["input_integrity"]["passed"])
        receipt = project / result["logs"]["stdout"]
        self.assertTrue(receipt.is_file())

    def test_changed_plan_is_rejected(self) -> None:
        project = self.project()
        plan_path = project / "experiments" / "plan.json"
        plan_path.write_text(plan_path.read_text() + "\n", encoding="utf-8")
        with self.assertRaises(experiment_runner.ExperimentError):
            experiment_runner.execute("test-phd")

    def test_plan_requires_command_file_arguments_to_be_hash_declared(self) -> None:
        plan = {
            "status": "ready_for_review",
            "runs": [
                {
                    "run_id": "audit", "paper_id": "P01",
                    "argv": ["python3", "analysis.py"], "cwd": ".", "seed": 1,
                    "timeout_seconds": 30, "estimated_cost_usd": 0,
                    "isolation": {"kind": "host"}, "inputs": [],
                    "expected_outputs": ["result.json"],
                }
            ],
        }
        self.assertTrue(
            any("hash-declared" in item for item in experiment_runner.validate_plan(plan))
        )
        plan["runs"][0]["inputs"] = [{"path": "analysis.py", "sha256": "a" * 64}]
        self.assertEqual(experiment_runner.validate_plan(plan), [])

    def test_run_that_mutates_an_approved_input_fails(self) -> None:
        project = self.project()
        input_path = project / "input.txt"
        input_path.write_text("approved", encoding="utf-8")
        plan_path = project / "experiments" / "plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["runs"][0]["inputs"] = [
            {"path": "input.txt", "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest()}
        ]
        plan["runs"][0]["argv"] = [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('input.txt').write_text('changed'); Path('result.txt').write_text('ok')",
        ]
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        state_path = project / "state" / "run.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["approvals"][0]["experiment_plan_sha256"] = hashlib.sha256(
            plan_path.read_bytes()
        ).hexdigest()
        state_path.write_text(json.dumps(state), encoding="utf-8")

        result = experiment_runner.execute("test-phd")[0]

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["input_integrity"]["passed"])
        self.assertEqual(
            result["input_integrity"]["mutated_or_missing"][0]["reason"],
            "hash_changed",
        )


if __name__ == "__main__":
    unittest.main()
