"""Cloud-run synthetic primary recovery; host fixtures are not scientific evidence."""
import json
import errno
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
        # This test executes synthetic local subprocesses, not a live Actions
        # runner with authenticated remote state. Production reservation failure
        # behavior is covered by test_experiment_runner's cloud tests.
        self.environment = patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "DR_OS_CLOUD_EXECUTOR": "1",
                                                   "DR_OS_REQUIRE_REMOTE_RESERVATION": "0"})
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
        with self.assertRaisesRegex(runner.ExperimentError, "recovery authorization"):
            self.execute()
        self.assertFalse((self.project / "state/experiment-execution-lease.json").exists())

        paused = cloud_research_steps.resume_experiments(self.project)
        self.assertEqual(paused["blockers"][0]["kind"], "experiment_failure_diagnosis")
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

    def test_changed_frozen_input_prevents_machine_recovery_without_leaking_a_lease(self):
        source = self.project / "analysis/input.json"
        source.parent.mkdir()
        source.write_text('{"fixture":1}', encoding="utf-8")
        self.plan["runs"][0]["inputs"] = [{"path": "analysis/input.json", "sha256": recovery.sha(source)}]
        self.put("experiments/plan.json", self.plan)
        self.freeze()
        failed = self.launch_failure()
        source.write_text('{"fixture":2}', encoding="utf-8")
        result = recovery.automatic_retry(self.project, failed)
        self.assertFalse(result["retry_authorized"])
        self.assertFalse((self.project / "state/experiment-execution-lease.json").exists())
        with self.assertRaises(runner.ExperimentError):
            self.execute()
        self.assertFalse((self.project / "state/experiment-execution-lease.json").exists())

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

    def launch_failure(self):
        original = runner.subprocess.Popen
        def unavailable(command, *args, **kwargs):
            if command[0] == sys.executable:
                raise FileNotFoundError(errno.ENOENT, "Synthetic unavailable executor")
            return original(command, *args, **kwargs)
        with patch.object(runner.subprocess, "Popen", side_effect=unavailable):
            return self.execute()

    def test_executor_proven_no_start_allows_one_honest_machine_recovery(self):
        failed = self.launch_failure()
        self.assertFalse(failed["launch"]["process_started"])
        self.assertEqual(failed["launch"]["os_error_errno"], errno.ENOENT)
        receipt = self.project / f"experiments/runs/{failed['attempt_id']}/run.json"
        original = receipt.read_bytes()
        decision = recovery.automatic_retry(self.project, failed)
        self.assertTrue(decision["retry_authorized"])
        authority = recovery._approval(self.project, failed)
        self.assertFalse(authority["human_confirmation"])
        self.assertEqual(authority["actor"], "deterministic_control_plane")
        self.assertEqual(authority["next_attempt_number"], 2)
        (self.project / "infrastructure-ready.flag").write_text("Synthetic restored fixture environment.", encoding="utf-8")
        success = self.execute()
        self.assertEqual(success["status"], "succeeded")
        self.assertEqual(receipt.read_bytes(), original)
        self.assertEqual(recovery.selected_attempt(self.project, "primary", recovery.records(self.project)), success)
        self.assertEqual(results_validation.validate_registry(self.project, self.plan, recovery.records(self.project)), [])

    def test_machine_recovery_refuses_scientific_failure_unknown_lease_and_budget_overrun(self):
        scientific = self.execute()
        self.assertTrue(scientific["launch"]["process_started"])
        self.assertFalse(recovery.automatic_retry(self.project, scientific)["retry_authorized"])
        self.assertFalse((self.project / recovery.CONTROL / "retries" / (scientific["attempt_id"] + ".json")).exists())

    def test_unknown_cost_reservation_is_not_cleared_by_machine_recovery(self):
        failed = self.launch_failure()
        lease = self.project / "state/experiment-execution-lease.json"
        lease.write_text('{"status":"running","synthetic_fixture":true}', encoding="utf-8")
        original = lease.read_bytes()
        result = recovery.automatic_retry(self.project, failed)
        self.assertFalse(result["retry_authorized"])
        self.assertIn("unresolved", result["blocker"])
        self.assertEqual(lease.read_bytes(), original)

    def test_machine_retry_budget_counts_the_failed_attempt_conservatively(self):
        self.put("experiments/budget.json", {"status": "ready_for_review", "hard_ceiling_usd": 0.2})
        self.freeze()
        failed = self.launch_failure()
        result = recovery.automatic_retry(self.project, failed)
        self.assertFalse(result["retry_authorized"])
        self.assertIn("compute budget", result["blocker"])

    def test_second_no_start_failure_cannot_start_an_automatic_retry_loop(self):
        first = self.launch_failure()
        self.assertTrue(recovery.automatic_retry(self.project, first)["retry_authorized"])
        second = self.launch_failure()
        self.assertEqual(second["attempt_id"], "primary-attempt-002")
        self.assertFalse(recovery.automatic_retry(self.project, second)["retry_authorized"])
        with self.assertRaisesRegex(runner.ExperimentError, "recovery authorization"):
            self.execute()

    def free_failed_protocol(self):
        self.plan["runs"][0]["estimated_cost_usd"] = 0
        self.put("experiments/plan.json", self.plan)
        self.freeze()
        failed = self.execute()
        self.assertEqual(failed["status"], "failed")
        return failed

    def machine_retirement_proposal(self):
        context = recovery.diagnosis_context(self.project)
        self.assertEqual(context["status"], "eligible", context)
        value = {"schema_version": "1.0", "operation": "retire_primary_plan",
                 "prior_outcomes_seen": True, "observed_prior_results": True,
                 "new_analysis_phase": "exploratory", "failure_category": "implementation_failure",
                 "reason": "Synthetic observed implementation failure; retain original logs and design a distinct exploratory repair.",
                 **{key: context[key] for key in ("plan_sha256", "budget_sha256", "version", "failed_attempt_ids", "diagnostic_evidence")}}
        self.put(recovery.AUTOMATIC_PROPOSAL, value)
        from scripts.output_provenance import record_model_writes
        record_model_writes(self.project, [self.project / recovery.AUTOMATIC_PROPOSAL], family="openai",
                            provider="synthetic-writer-fixture", model="synthetic-no-model-call", role="writer", run_id="machine-diagnosis")
        return value

    def test_free_failed_protocol_uses_actual_same_cycle_reviews_before_machine_retirement(self):
        failed = self.free_failed_protocol()
        state_before = self.read("state/run.json")
        proposal = self.machine_retirement_proposal()
        before = (self.project / "experiments/registry.jsonl").read_bytes()
        blocked = recovery.automatic_retirement(self.project, run_id="machine-diagnosis")
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual((self.project / "experiments/registry.jsonl").read_bytes(), before)
        from tests.review_scope_fixtures import seal_review
        seal_review(self.project, state_before, gate="G4", run_id="machine-diagnosis")
        wrong = recovery.automatic_retirement(self.project, run_id="another-cycle")
        self.assertEqual(wrong["status"], "blocked")
        self.assertIn("exact writer/critic cycle", wrong["blocker"])
        result = recovery.automatic_retirement(self.project, run_id="machine-diagnosis")
        self.assertTrue(result["retired"], result)
        current = self.read("state/run.json")
        self.assertEqual((current["gate"], current["status"]), ("G3", "awaiting_work"))
        self.assertEqual([a for a in current["approvals"] if a.get("gate") in {"G1", "G2"}],
                         [a for a in state_before["approvals"] if a.get("gate") in {"G1", "G2"}])
        history = recovery.histories(self.project)[0]
        self.assertEqual(history["decision_kind"], "automated")
        self.assertFalse(history["human_confirmation"])
        self.assertNotIn("cloud_review_sha256", history)
        self.assertEqual(history["proposal"], proposal)
        self.assertEqual(len(history["review_evidence"]), 4)
        archive = self.project / "experiments/history/v001/files/experiments/registry.jsonl"
        self.assertEqual(archive.read_bytes(), before)
        self.assertEqual((self.project / failed["outputs"][0]["path"]).read_text(), "partial failure")
        self.assertTrue((self.project / "experiments/history/v001/files" / failed["logs"]["stderr"]).is_file())
        self.assertFalse((self.project / "papers/P01/preregistration.json").exists())
        self.assertEqual(recovery.historical_cost(self.project), 0)
        plan = self.amend(phase="exploratory", cost=0)
        plan["runs"][0]["argv"] = [sys.executable, "-c", "raise SystemExit(2)"]
        self.put("experiments/plan.json", plan)
        self.freeze()
        self.assertEqual(self.execute()["status"], "failed")
        capped = recovery.diagnosis_context(self.project)
        self.assertEqual(capped["status"], "blocked")
        self.assertIn("hard limit", capped["blocker"])

    def test_paid_failure_is_accounted_without_extra_approval_but_running_lease_blocks_duplicate_work(self):
        failed = self.execute()
        self.assertEqual(failed["status"], "failed")
        paid = recovery.diagnosis_context(self.project)
        self.assertEqual(paid["status"], "eligible")
        self.assertEqual(paid["committed_compute_usd"], 0.2)
        self.assertIn("conservative_plan_estimate", paid["cost_accounting_basis"])
        self.assertIsNone(failed["reported_cost_usd"])
        self.put("state/experiment-execution-lease.json", {"status": "running", "synthetic_fixture": True})
        unknown = recovery.diagnosis_context(self.project)
        self.assertEqual(unknown["status"], "blocked")
        self.assertIn("unresolved", unknown["blocker"])

    def test_failed_compute_estimate_cannot_disappear_at_total_limit(self):
        self.execute()
        self.put("intake/constraints.json", {"cloud_compute_budget_usd": 0.1})
        result = recovery.diagnosis_context(self.project)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("cumulative compute budget", result["blocker"])

    def test_complete_failure_logs_cannot_forward_configured_credentials_to_models(self):
        failed = self.free_failed_protocol()
        secret = "synthetic-fixture-secret-never-send"
        log = self.project / failed["logs"]["stderr"]
        log.write_text("Synthetic error containing " + secret, encoding="utf-8")
        with patch.dict(os.environ, {"SYNTHETIC_API_KEY": secret}):
            result = recovery.diagnosis_context(self.project)
        self.assertEqual(result["status"], "blocked")
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn("credential", result["blocker"])
        self.assertIn(secret, log.read_text(encoding="utf-8"))

    def test_failed_runs_may_reach_normal_diagnosis_cycle_without_human_pause(self):
        self.free_failed_protocol()
        from scripts import cloud_progress
        self.put("state/research-steps.json", {"blockers": [{"kind": "experiment_inspection"}]})
        self.assertEqual(cloud_progress.external_blockers(self.project, []), [])
        with patch.object(cloud_research_steps, "acquire_data", return_value={"blockers": []}):
            result = cloud_research_steps.before_cycle(self.project, "experiment-execution")
        self.assertFalse(result["control_only"])
        self.assertEqual(result["failure_diagnosis"]["status"], "eligible")
        self.assertFalse((self.project / "experiments/history/v001/manifest.json").exists())

    def test_first_no_start_failure_reaches_controller_retry_after_scheduled_checkpoint(self):
        failed = self.launch_failure()
        from scripts import cloud_progress
        self.put("state/research-steps.json", {"blockers": [{"kind": "experiment_inspection"}]})
        self.assertEqual(recovery.failure_control_status(self.project)["status"], "retry_pending")
        self.assertEqual(cloud_progress.external_blockers(self.project, []), [])
        self.assertIsNone(recovery._approval(self.project, failed))
        self.put("state/experiment-execution-lease.json", {"status": "running", "synthetic_fixture": True})
        self.assertTrue(cloud_progress.external_blockers(self.project, []))

    def test_successful_negative_outcome_never_becomes_automatic_failed_protocol(self):
        self.plan["runs"][0].update(estimated_cost_usd=0, argv=[sys.executable, "-c",
            "from pathlib import Path; Path('results').mkdir(exist_ok=True); Path('results/value.txt').write_text('valid negative outcome')"])
        self.put("experiments/plan.json", self.plan)
        self.freeze()
        self.assertEqual(self.execute()["status"], "succeeded")
        self.assertEqual(recovery.diagnosis_context(self.project)["status"], "not_needed")
        self.assertEqual(recovery.automatic_retirement(self.project, run_id="synthetic")["status"], "not_configured")

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
        self.assertEqual(recovery.gate_errors(self.project, "G3"), [])
        self.assertEqual(runner.project_compute_ceiling(self.project, self.read("experiments/budget.json")), 1.0)
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
