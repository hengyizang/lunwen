"""Cloud-run synthetic primary recovery; host fixtures are not scientific evidence."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import cloud_research_steps, experiment_evidence, experiment_runner as runner
from scripts import primary_recovery as recovery, results_validation, study_routes, supplemental_experiments as supplemental


class PrimaryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "test-phd"
        self.project.mkdir()
        self.environment = patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "DR_OS_CLOUD_EXECUTOR": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.put("papers/P01/experiment-evidence-plan.json", {"comparisons": [{"analysis_phase": "confirmatory"}],
            "synthetic_unit_fixture": True})
        command = ("from pathlib import Path; import sys; p=Path('results/value.txt'); p.parent.mkdir(exist_ok=True); "
                   "ready=Path('infrastructure-ready.flag').exists(); p.write_text('complete' if ready else 'partial failure'); "
                   "sys.exit(0 if ready else 2)")
        self.plan = {"schema_version": "1.0", "status": "ready_for_review", "runs": [{
            "run_id": "primary", "paper_id": "P01", "argv": [sys.executable, "-c", command], "cwd": ".", "seed": 7,
            "timeout_seconds": 30, "estimated_cost_usd": 0.2, "isolation": {"kind": "host"}, "inputs": [],
            "expected_outputs": ["results/value.txt"]}]}
        self.put("experiments/plan.json", self.plan)
        self.put("experiments/budget.json", {"schema_version": "1.0", "status": "ready_for_review", "hard_ceiling_usd": 1.0})
        self.put("state/run.json", {"stage_index": 4, "stage": "experiment-execution", "gate": "G4", "status": "awaiting_work",
            "active_paper": "P01", "approved_gates": ["G0", "G1", "G2", "G3"], "approvals": []})
        from scripts.acceptance_scope import prepare_scope
        prepare_scope(self.project,self.read("state/run.json"))
        self.freeze()

    def put(self, relative, value):
        recovery.write(self.project / relative, value)

    def read(self, relative):
        return recovery.read(self.project / relative)

    def freeze(self):
        protocol = "papers/P01/experiment-evidence-plan.json"
        self.put("papers/P01/preregistration.json", {"status": "frozen", "files": [
            {"path": protocol, "sha256": recovery.sha(self.project / protocol)}]})
        state = self.read("state/run.json")
        state.update(stage_index=4, stage="experiment-execution", gate="G4", status="awaiting_work")
        if "G3" not in state["approved_gates"]:
            state["approved_gates"].append("G3")
        state["approvals"].append({"gate": "G3", "actor": "Synthetic Human", "experiment_plan_sha256": recovery.sha(self.project / "experiments/plan.json"),
            "experiment_budget_sha256": recovery.sha(self.project / "experiments/budget.json"),
            "frozen_protocol_sha256": {"papers/P01/preregistration.json": recovery.sha(self.project / "papers/P01/preregistration.json")}})
        self.put("state/run.json", state)

    def execute(self):
        return runner.execute(self.project.name, project_root=self.project)[0]

    def proposal(self, operation, **extra):
        relative = "program/primary-recovery.json"
        self.put(relative, {"schema_version": "1.0", "operation": operation,
            "plan_sha256": recovery.sha(self.project / "experiments/plan.json"),
            "budget_sha256": recovery.sha(self.project / "experiments/budget.json"),
            "reason": "Synthetic human inspected the original failure and unchanged frozen scientific inputs.", **extra})
        return relative

    def authorize_retry(self, failed):
        source = self.proposal("approve_primary_retry", failed_attempt_id=failed["attempt_id"], failure_category="infrastructure")
        recovery.apply(self.project, source, "Synthetic Human", "approve_primary_retry", "c" * 64, "123", "Inspected unchanged infrastructure recovery.")

    def retire(self, *, phase="exploratory", version="v001"):
        source = self.proposal("retire_primary_plan", version=version, prior_outcomes_seen=True, new_analysis_phase=phase)
        recovery.apply(self.project, source, "Synthetic Human", "retire_primary_plan", "d" * 64, "124", "Retire the observed protocol; approve no new experiment.")

    def amend(self, *, phase="exploratory", cost=0.2):
        plan = self.read("experiments/plan.json")
        plan["runs"][0].update(run_id="amended", expected_outputs=["results/amended.txt"], estimated_cost_usd=cost,
            argv=[sys.executable, "-c", "from pathlib import Path; Path('results').mkdir(exist_ok=True); Path('results/amended.txt').write_text('new protocol')"])
        self.put("experiments/plan.json", plan)
        self.put("papers/P01/experiment-evidence-plan.json", {"comparisons": [{"analysis_phase": phase}], "synthetic_unit_fixture": True})
        return plan

    def test_failed_attempt_needs_exact_owner_approval_then_preserves_failure_and_selects_success(self):
        plan_before = (self.project / "experiments/plan.json").read_bytes()
        failed = self.execute()
        self.assertEqual(failed["status"], "failed")
        failure_receipt = self.project / "experiments/runs/primary-attempt-001/run.json"
        preserved_receipt = failure_receipt.read_bytes()
        self.assertTrue(failed["input_integrity"]["passed"])
        with self.assertRaisesRegex(runner.ExperimentError, "owner authorization"):
            self.execute()
        paused = cloud_research_steps.resume_experiments(self.project)
        self.assertEqual(paused["blockers"][0]["kind"], "experiment_inspection")
        self.authorize_retry(failed)
        self.assertEqual((self.project / "experiments/plan.json").read_bytes(), plan_before)
        archive = recovery.preserved_output(self.project, failed, failed["outputs"][0])
        self.assertEqual(archive.read_text(), "partial failure")
        self.assertNotEqual(archive, self.project / failed["outputs"][0]["path"])
        # The synthetic host test cannot use the production Docker queue, but
        # the approved failed attempt is no longer a permanent inspection block.
        waiting = cloud_research_steps.resume_experiments(self.project)
        self.assertEqual(waiting["blockers"][0]["kind"], "cloud_experiment_plan")
        (self.project / "infrastructure-ready.flag").write_text("Synthetic infrastructure restored.", encoding="utf-8")
        success = self.execute()
        self.assertEqual(success["status"], "succeeded")
        self.assertEqual(success["attempt_id"], "primary-attempt-002")
        self.assertEqual(failure_receipt.read_bytes(), preserved_receipt)
        self.assertEqual(archive.read_text(), "partial failure")
        rows = recovery.records(self.project)
        self.assertEqual(results_validation.validate_registry(self.project, self.plan, rows), [])
        self.assertEqual(recovery.selected_attempt(self.project, "primary", rows)["attempt_id"], success["attempt_id"])
        source, binding = experiment_evidence._bound_output(self.project,
            {"run_id": "primary", "output": "results/value.txt"}, rows, recovery.sha(self.project / "experiments/plan.json"))
        self.assertEqual(source.read_text(), "complete")
        self.assertEqual(binding["attempt_id"], success["attempt_id"])
        completed = cloud_research_steps.resume_experiments(self.project)
        self.assertEqual(completed["pending_runs"], 0)
        self.assertEqual(completed["blockers"], [])
        with self.assertRaisesRegex(runner.ExperimentError, "cannot be rerun"):
            self.execute()

    def test_retry_proposals_reject_scientific_changes_repeated_approval_and_changed_archive(self):
        failed = self.execute()
        source = self.proposal("approve_primary_retry", failed_attempt_id=failed["attempt_id"], failure_category="method_bug")
        with self.assertRaisesRegex(recovery.RecoveryError, "infrastructure"):
            recovery.prepare(self.project, source, "Synthetic Human", "approve_primary_retry")
        self.authorize_retry(failed)
        with self.assertRaisesRegex(recovery.RecoveryError, "once"):
            recovery.prepare(self.project, source, "Synthetic Human", "approve_primary_retry")
        archive = recovery.preserved_output(self.project, failed, failed["outputs"][0])
        archive.write_text("Corrupted old evidence.", encoding="utf-8")
        with self.assertRaisesRegex(runner.ExperimentError, "preserved failed output changed"):
            self.execute()

    def test_study_report_selects_authorized_success_but_does_not_certify_host_isolation(self):
        failed = self.execute()
        self.authorize_retry(failed)
        (self.project / "infrastructure-ready.flag").write_text("Synthetic infrastructure restored.", encoding="utf-8")
        success = self.execute()
        # Isolate this handoff from the separately tested full Meta/theory
        # protocol schema, while retaining real registry/receipt validation.
        with patch.object(study_routes, "validate_protocol", return_value=({"execution_runs": ["primary"]}, [])), \
             patch("scripts.research_quality.validate_preregistration", return_value=[]), \
             patch.object(recovery, "selected_attempt", wraps=recovery.selected_attempt) as selected:
            report = study_routes.build_report(self.project, "P01")
        self.assertTrue(selected.called)
        self.assertEqual(selected.call_args.args[2][-1]["attempt_id"], success["attempt_id"])
        self.assertEqual(report["status"], "blocked")
        self.assertIn("isolated executor", " ".join(report["errors"]))
        self.assertFalse(report["scientific_completion_verified"])

    def test_retirement_returns_to_g3_preserves_evidence_and_requires_new_ids_paths_and_phase(self):
        failed = self.execute()
        registry_before = (self.project / "experiments/registry.jsonl").read_bytes()
        receipt_before = (self.project / "experiments/runs/primary-attempt-001/run.json").read_bytes()
        self.retire()
        state = self.read("state/run.json")
        self.assertEqual((state["stage"], state["gate"], state["status"]), ("experiment-design", "G3", "awaiting_work"))
        self.assertNotIn("G3", state["approved_gates"])
        self.assertEqual((self.project / "experiments/registry.jsonl").read_bytes(), b"")
        self.assertFalse((self.project / "papers/P01/preregistration.json").exists())
        self.assertEqual((self.project / "experiments/history/v001/files/experiments/registry.jsonl").read_bytes(), registry_before)
        self.assertEqual((self.project / "experiments/runs/primary-attempt-001/run.json").read_bytes(), receipt_before)
        self.assertEqual(recovery.histories(self.project)[0]["proposal"]["prior_outcomes_seen"], True)
        self.assertAlmostEqual(recovery.historical_cost(self.project), 0.2)
        self.assertIn("new run IDs", " ".join(recovery.gate_errors(self.project, "G3")))
        with self.assertRaisesRegex(runner.ExperimentError, "open G4"):
            self.execute()
        self.amend(phase="confirmatory")
        self.assertIn("phase", " ".join(recovery.gate_errors(self.project, "G3")))
        self.amend(phase="exploratory")
        self.assertEqual(recovery.gate_errors(self.project, "G3"), [])
        self.assertTrue(recovery.approved_exploration(self.project))
        self.freeze()
        amended = self.execute()
        self.assertEqual(amended["status"], "succeeded")
        self.assertEqual(amended["run_id"], "amended")
        self.assertEqual((self.project / failed["outputs"][0]["path"]).read_text(), "partial failure")
        self.assertAlmostEqual(recovery.historical_cost(self.project) + runner.prior_estimated_cost(self.project / "experiments/registry.jsonl"), 0.4)

    def test_retirement_cannot_reset_compute_allowance_or_mislabel_prospective_followup(self):
        self.execute()
        self.retire(phase="prospective_followup")
        self.amend(phase="exploratory", cost=0.9)
        self.assertIn("phase", " ".join(recovery.gate_errors(self.project, "G3")))
        self.amend(phase="confirmatory", cost=0.9)
        self.assertEqual(recovery.gate_errors(self.project, "G3"), [])
        self.put("experiments/budget.json", {"status": "ready_for_review", "hard_ceiling_usd": 2.0})
        self.assertIn("cannot reset or enlarge", " ".join(recovery.gate_errors(self.project, "G3")))
        self.put("experiments/budget.json", {"status": "ready_for_review", "hard_ceiling_usd": 1.0})
        self.freeze()
        with self.assertRaisesRegex(runner.ExperimentError, "Budget ceiling exceeded"):
            self.execute()
        self.assertEqual(recovery.records(self.project), [])

    def test_retired_history_tampering_blocks_reuse_instead_of_erasing_failed_runs(self):
        self.execute()
        self.retire()
        archive = self.project / "experiments/history/v001/files/experiments/plan.json"
        archive.write_text("{}", encoding="utf-8")
        self.assertIn("archive changed", " ".join(recovery.gate_errors(self.project, "G3")))
        with self.assertRaisesRegex(recovery.RecoveryError, "archive changed"):
            recovery.historical_cost(self.project)

    def test_retirement_archives_hash_declared_source_before_the_code_is_corrected(self):
        source = self.project / "experiments/source.py"
        original = ("from pathlib import Path\nPath('results').mkdir(exist_ok=True)\n"
                    "Path('results/value.txt').write_text('original failure')\nraise SystemExit(2)\n")
        source.write_text(original, encoding="utf-8")
        raw = self.project / "data/raw/original.txt"
        raw.parent.mkdir(parents=True)
        raw.write_text("Synthetic private fixture input.", encoding="utf-8")
        self.plan["runs"][0].update(argv=[sys.executable, "experiments/source.py"], inputs=[
            {"path": "experiments/source.py", "sha256": recovery.sha(source)},
            {"path": "data/raw/original.txt", "sha256": recovery.sha(raw)}])
        self.put("experiments/plan.json", self.plan)
        self.freeze()
        self.assertEqual(self.execute()["status"], "failed")
        self.retire()
        archive = self.project / "experiments/history/v001/files/experiments/source.py"
        self.assertEqual(archive.read_text(encoding="utf-8"), original)
        source.write_text("# Newly corrected protocol version.\n", encoding="utf-8")
        self.amend()
        rows = {row["path"]: row for row in recovery.histories(self.project)[0]["files"]}
        self.assertEqual(rows["experiments/source.py"]["sha256"], recovery.sha(archive))
        self.assertIsNone(rows["data/raw/original.txt"]["archive"])
        self.assertFalse((self.project / "experiments/history/v001/files/data/raw/original.txt").exists())
        self.assertEqual(archive.read_text(encoding="utf-8"), original)

    def test_retirement_rejects_mutated_hash_declared_source_before_archiving(self):
        source = self.project / "experiments/source.py"
        source.write_text("# Original frozen source.\n", encoding="utf-8")
        self.plan["runs"][0]["inputs"] = [{"path": "experiments/source.py", "sha256": recovery.sha(source)}]
        self.put("experiments/plan.json", self.plan)
        self.freeze()
        self.assertEqual(self.execute()["status"], "failed")
        source.write_text("# Changed before explicit retirement.\n", encoding="utf-8")
        with self.assertRaisesRegex(recovery.RecoveryError, "frozen input is missing or changed"):
            self.retire()
        self.assertFalse((self.project / "experiments/history/v001").exists())
        self.assertEqual(self.read("state/run.json")["gate"], "G4")

    def test_history_validates_failed_and_successful_outputs_after_a_retry_and_new_plan(self):
        failed = self.execute()
        self.authorize_retry(failed)
        failed_output = recovery.preserved_output(self.project, failed, failed["outputs"][0])
        (self.project / "infrastructure-ready.flag").write_text("Synthetic infrastructure restored.", encoding="utf-8")
        success = self.execute()
        self.retire()
        self.amend()
        self.assertAlmostEqual(recovery.historical_cost(self.project), 0.4)
        success_output = self.project / success["outputs"][0]["path"]
        for target in (failed_output, success_output):
            original = target.read_bytes()
            target.write_bytes(b"Corrupted retained executor output.")
            with self.assertRaisesRegex(recovery.RecoveryError, "executor output changed"):
                recovery.historical_cost(self.project)
            target.write_bytes(original)
        self.assertAlmostEqual(recovery.historical_cost(self.project), 0.4)

    def test_protocol_version_order_cannot_restore_an_older_analysis_phase(self):
        self.execute()
        self.retire(phase="prospective_followup", version="v010")
        plan = self.amend(phase="confirmatory")
        plan["runs"][0]["argv"] = [sys.executable, "-c", "raise SystemExit(2)"]
        self.put("experiments/plan.json", plan)
        self.freeze()
        self.assertEqual(self.execute()["status"], "failed")
        with self.assertRaisesRegex(recovery.RecoveryError, "increase monotonically"):
            self.retire(phase="exploratory", version="v001")
        self.assertFalse((self.project / "experiments/history/v001").exists())
        self.retire(phase="exploratory", version="v011")
        self.assertEqual(recovery.histories(self.project)[-1]["proposal"]["new_analysis_phase"], "exploratory")

    def test_supplemental_cap_counts_retired_primary_and_current_attempts_once(self):
        self.execute()
        self.retire()
        self.amend()
        self.freeze()
        self.assertEqual(self.execute()["status"], "succeeded")
        self.put("intake/constraints.json", {"cloud_compute_budget_usd": 1.0})
        child = self.project / "experiments/supplemental/P01/R001/s001"
        recovery.write(child / "experiments/plan.json", {"runs": [{"run_id": "extra", "estimated_cost_usd": 0.7}]})
        self.assertAlmostEqual(supplemental.all_compute_cost(self.project), 0.4)
        control = {"scope_root": child.relative_to(self.project).as_posix()}
        with patch.object(supplemental, "current", return_value=({"round_id": "R001"}, {})), \
             patch.object(supplemental, "controls", return_value=[(child / "control.json", control)]), \
             patch.object(supplemental, "checked_child", return_value=child), \
             patch.object(runner, "execute") as execute:
            with self.assertRaisesRegex(ValueError, "aggregate parent/supplemental compute budget exhausted"):
                supplemental.resume(self.project, "P01")
            execute.assert_not_called()
        (child / "experiments/registry.jsonl").write_text('{"estimated_cost_usd": 0.1}\n', encoding="utf-8")
        self.assertAlmostEqual(supplemental.all_compute_cost(self.project), 0.5)


if __name__ == "__main__":
    unittest.main()
