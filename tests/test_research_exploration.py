"""Native exploration integration using local synthetic scripts, never real science."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import automated_quality, experiment_evidence, experiment_runner as runner
from scripts import paper_execution, research_phase, research_quality, researchctl, review_receipts
from scripts import api_orchestrator, autopilot
from scripts import cloud_research_steps as steps, results_validation
from scripts.acceptance_scope import prepare_scope
from scripts.research_artifacts import read, sha, write
from scripts.supplemental_experiments import all_compute_cost
from tests import test_research_identity as identity_fixtures


class NativeExplorationTests(unittest.TestCase):
    def setUp(self):
        self.identity = identity_fixtures.ResearchIdentityTests()
        self.identity.setUp()
        self.addCleanup(self.identity.doCleanups)
        self.project = self.identity.project
        self.slug = self.project.name
        state = read(self.project / "state/run.json")
        state.update(stage_index=3, stage="experiment-design", gate="G3", status="awaiting_work",
                     paper_execution_mode="independent", history=[])
        contract = read(self.project / "papers/P01/paper-contract.json")
        contract["datasets"] = []
        write(self.project / "papers/P01/paper-contract.json", contract)
        prepare_scope(self.project, state)
        write(self.project / "intake/constraints.json", {"cloud_compute_budget_usd": 1, "cash_budget_usd": 1})
        write(paper_execution.artifact_path(self.project, "experiments/budget.json"),
              {"status": "ready_for_review", "hard_ceiling_usd": 1})
        script = self.project / "analysis/probe.py"
        script.parent.mkdir(parents=True)
        script.write_text("from pathlib import Path\nimport sys\np=Path('results/P01/probe.json')\n"
                          "p.parent.mkdir(parents=True,exist_ok=True)\np.write_text('{\"synthetic\":true,\"value\":-1}')\n"
                          "sys.exit(0)\n", encoding="utf-8")
        self.plan = {"schema_version": "1.0", "status": "ready_for_review", "research_phase": "exploratory",
            "exploration": {"unknown": "Whether the synthetic probe produces a readable negative observation.",
                "discriminating_test": "Execute one small synthetic script and retain its exact observation.",
                "continue_if": "The synthetic output is readable.", "revise_if": "The script fails with preserved diagnostics.",
                "stop_if": "The synthetic probe cannot distinguish the stated alternatives.",
                "claim_limit": "Software fixture only; no population or scientific support is established.",
                "prior_outcomes_seen": False},
            "runs": [{"run_id": "P01-probe", "paper_id": "P01", "argv": [sys.executable, "analysis/probe.py"],
                "cwd": ".", "seed": 0, "timeout_seconds": 20, "estimated_cost_usd": .25,
                "isolation": {"kind": "host"}, "inputs": [{"path": "analysis/probe.py", "sha256": sha(script)}],
                "expected_outputs": ["results/P01/probe.json"]}]}
        self.plan_path = paper_execution.artifact_path(self.project, "experiments/plan.json")
        write(self.plan_path, self.plan)
        for target, name, value in ((researchctl, "PROJECTS_ROOT", self.project.parent),
                                   (runner, "PROJECTS_ROOT", self.project.parent)):
            patched = patch.object(target, name, value); patched.start(); self.addCleanup(patched.stop)
        api_project = patch.object(api_orchestrator, "project_root", return_value=self.project)
        api_project.start(); self.addCleanup(api_project.stop)
        env = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1", "GITHUB_ACTIONS": "false",
                                     "DR_OS_REQUIRE_REMOTE_RESERVATION": "0"})
        env.start(); self.addCleanup(env.stop)

    def audit(self, gate):
        stage = {"G3": "experiment-design", "G4": "experiment-execution"}[gate]
        identity = {"provider": "synthetic-anthropic", "family": "anthropic", "requested_model": "synthetic-critic",
                    "reported_model": "synthetic-critic", "completion_status": "completed", "cache_hit": False}
        audit = {"verdict": "pass-with-conditions", "fatal_findings": [], "major_findings": [], "minor_findings": [],
                 "missing_evidence": [], "remediation_steps": [], "uncertainty": ["Synthetic software review receipt only."]}
        token = "software-" + gate + "-" + sha(self.plan_path)[:12]
        for phase in ("initial", "final"):
            path = self.project / f"reviews/independent/{token}-{phase}.json"
            write(path, audit)
            review_receipts.seal_phase(self.project, stage=stage, run_id=token, phase=phase,
                audit_path=path, prompt="Software fixture; assess this exact exploratory protocol/evidence only.",
                identity=identity, writer_family="openai", materials=review_receipts.material_snapshot(self.project, stage, "P01"),
                notes=[] if phase == "final" else None)
        from scripts.api_orchestrator import append_decision_log
        append_decision_log(self.slug, stage, token,
            self.project / f"reviews/independent/{token}-initial.json",
            self.project / f"reviews/independent/{token}-final.json", [], audit)

    def start(self):
        checked = automated_quality.run(self.project)
        self.assertEqual(checked["blockers"], [], checked)
        self.audit("G3")
        self.assertEqual(researchctl.gate_errors(self.slug, "G3"), [])
        researchctl.mark_ready(SimpleNamespace(project=self.slug, note="Synthetic exploratory protocol check."))
        researchctl.advance(SimpleNamespace(project=self.slug))

    def complete(self):
        experiment_evidence.refresh(self.project)
        self.audit("G4")
        self.assertEqual(researchctl.gate_errors(self.slug, "G4"), [])
        researchctl.mark_ready(SimpleNamespace(project=self.slug, note="Retain actual synthetic exploratory observations."))
        researchctl.advance(SimpleNamespace(project=self.slug))

    def add_probe(self, run_id, *, dependencies=(), failed=False):
        """A real local script; cloud tests adapt only Docker eligibility."""
        output = f"results/P01/{run_id}.json"
        script = self.project / "analysis" / (run_id + ".py")
        script.write_text("from pathlib import Path\nimport sys\n"
            f"p=Path({output!r})\np.parent.mkdir(parents=True,exist_ok=True)\np.write_text('{{\"synthetic\":true}}')\n"
            f"sys.exit({4 if failed else 0})\n", encoding="utf-8")
        self.plan["runs"].append({"run_id": run_id, "paper_id": "P01", "argv": [sys.executable, script.relative_to(self.project).as_posix()],
            "cwd": ".", "seed": 0, "timeout_seconds": 20, "estimated_cost_usd": .1,
            "isolation": {"kind": "host"}, "inputs": [{"path": script.relative_to(self.project).as_posix(), "sha256": sha(script)}],
            "expected_outputs": [output], "depends_on": list(dependencies)})
        write(self.plan_path, self.plan)

    def fail_first_probe(self):
        script = self.project / "analysis/probe.py"
        script.write_text(script.read_text().replace("sys.exit(0)", "sys.exit(4)"), encoding="utf-8")
        self.plan["runs"][0]["inputs"][0]["sha256"] = sha(script)
        write(self.plan_path, self.plan)

    def test_failed_prerequisite_stops_descendants_and_returns_actual_incomplete_execution_to_review(self):
        self.fail_first_probe()
        self.add_probe("P01-child", dependencies=["P01-probe"])
        self.add_probe("P01-grandchild", dependencies=["P01-child"])
        self.start()
        self.assertEqual(runner.execute(self.slug, ["P01-probe"])[0]["status"], "failed")
        controlled = steps.before_cycle(self.project, "experiment-execution")
        self.assertFalse(controlled["control_only"])
        self.assertEqual(controlled["blockers"], [])
        self.assertEqual(controlled["experiments"]["pending_runs"], 0)
        self.assertEqual({row["run_id"] for row in controlled["experiments"]["unexecuted_runs"]}, {"P01-child", "P01-grandchild"})
        report = read(self.project / "papers/P01/experiment-evidence.json")
        self.assertEqual(report["status"], "complete")
        self.assertFalse(report["all_planned_runs_executed"])
        self.assertFalse(report["confirmatory_evidence"])
        self.assertEqual(report["execution_status"], "stopped_after_dependency_failure")
        self.assertEqual([row["status"] for row in report["observations"]], ["failed"])
        self.assertTrue(all(row["status"] == "not_executed" and row["failed_run_ids"] == ["P01-probe"] for row in report["unexecuted_runs"]))
        self.complete()
        archive = research_phase.histories(self.project)[0]
        archived_report = next(row for row in archive["files"] if row["source"] == "papers/P01/experiment-evidence.json")
        self.assertFalse(read(self.project / archived_report["archive_path"])["all_planned_runs_executed"])
        rows = [json.loads(line) for line in (self.project / archive["registry_path"]).read_text().splitlines()]
        self.assertEqual([row["run_id"] for row in rows], ["P01-probe"])
        self.assertEqual(all_compute_cost(self.project), .25)
        self.assertEqual(read(self.project / "state/run.json")["gate"], "G3")

    def test_cloud_schedules_independent_branches_without_launching_blocked_descendants(self):
        self.fail_first_probe()
        self.add_probe("P01-blocked", dependencies=["P01-probe"])
        self.add_probe("P01-independent")
        self.add_probe("P01-independent-child", dependencies=["P01-independent"])
        self.add_probe("P01-join", dependencies=["P01-blocked", "P01-independent-child"])
        self.start()
        # Native host execution remains labeled host; this only bypasses Docker
        # availability at the cloud boundary. No gate, runner, receipt or output is mocked.
        with patch.object(steps, "_cloud_run_eligible", return_value=True):
            cycles = [steps.before_cycle(self.project, "experiment-execution") for _ in range(4)]
        self.assertTrue(all(cycle["control_only"] for cycle in cycles[:3]))
        self.assertFalse(cycles[-1]["control_only"])
        registry = research_quality._registry(self.project)
        self.assertEqual([row["run_id"] for row in registry], ["P01-probe", "P01-independent", "P01-independent-child"])
        self.assertEqual([row["status"] for row in registry], ["failed", "succeeded", "succeeded"])
        self.assertTrue(all(row["executor_isolation"]["kind"] == "host" for row in registry))
        report = research_phase.build_report(self.project, "P01")
        self.assertEqual(report["status"], "complete", report)
        self.assertEqual({row["run_id"] for row in report["unexecuted_runs"]}, {"P01-blocked", "P01-join"})
        self.assertFalse(report["all_planned_runs_executed"])
        self.assertFalse((self.project / "results/P01/P01-blocked.json").exists())
        self.assertFalse((self.project / "results/P01/P01-join.json").exists())
        self.complete()
        self.assertAlmostEqual(all_compute_cost(self.project), .45)

    def test_missing_unrelated_run_is_not_excused_by_an_exploratory_failure(self):
        self.fail_first_probe()
        self.add_probe("P01-blocked", dependencies=["P01-probe"])
        self.add_probe("P01-unattempted")
        self.start(); runner.execute(self.slug, ["P01-probe"])
        report = research_phase.build_report(self.project, "P01")
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("P01-unattempted" in error for error in report["errors"]))
        self.assertFalse(any("P01-blocked" in error for error in report["errors"]))
        # Formal validation is unchanged: every planned run still requires a receipt.
        errors = results_validation.validate_registry(self.project, self.plan, research_quality._registry(self.project))
        self.assertTrue(any("P01-blocked" in error and "P01-unattempted" in error for error in errors))

    def missing_runtime(self):
        executable = self.project / "restored-runtime/python3"
        self.plan["runs"][0]["argv"][0] = str(executable)
        write(self.plan_path, self.plan)
        return executable

    def restore_runtime(self, executable):
        executable.parent.mkdir()
        executable.symlink_to(sys.executable)

    def test_cloud_reuses_authorized_no_start_retry_without_erasing_the_diagnostic(self):
        executable = self.missing_runtime()
        self.add_probe("P01-after-retry", dependencies=["P01-probe"])
        self.start()
        with patch.object(steps, "_cloud_run_eligible", return_value=True):
            first = steps.before_cycle(self.project, "experiment-execution")
            self.assertTrue(first["control_only"])
            first_report = research_phase.build_report(self.project, "P01")
            self.assertEqual(first_report["status"], "blocked")
            self.assertEqual(first_report["observations"][0]["observation_kind"], "execution_diagnostic")
            self.assertFalse(first_report["all_planned_runs_executed"])
            self.restore_runtime(executable)
            retried = steps.before_cycle(self.project, "experiment-execution")
            dependent = steps.before_cycle(self.project, "experiment-execution")
            ready = steps.before_cycle(self.project, "experiment-execution")
        self.assertTrue(retried["control_only"])
        self.assertTrue(dependent["control_only"])
        self.assertFalse(ready["control_only"])
        registry = research_quality._registry(self.project)
        self.assertEqual([row["status"] for row in registry], ["failed", "succeeded", "succeeded"])
        self.assertEqual([row["launch"]["process_started"] for row in registry], [False, True, True])
        report = research_phase.build_report(self.project, "P01")
        self.assertEqual(report["status"], "complete", report)
        self.assertTrue(report["all_planned_runs_executed"])
        self.assertFalse(report["confirmatory_evidence"])
        self.complete()
        self.assertAlmostEqual(all_compute_cost(self.project), .6)
        archive = research_phase.histories(self.project)[0]
        self.assertTrue(any(row["source"] == "state/primary-recovery/retries/P01-probe-attempt-001.json"
                            for row in archive["files"]))

    def test_authorized_retry_that_really_fails_returns_to_review_without_a_third_attempt(self):
        self.fail_first_probe()
        executable = self.missing_runtime()
        self.add_probe("P01-blocked-after-retry", dependencies=["P01-probe"])
        self.start()
        with patch.object(steps, "_cloud_run_eligible", return_value=True):
            steps.before_cycle(self.project, "experiment-execution")
            self.restore_runtime(executable)
            steps.before_cycle(self.project, "experiment-execution")
            ready = steps.before_cycle(self.project, "experiment-execution")
        self.assertFalse(ready["control_only"])
        registry = research_quality._registry(self.project)
        self.assertEqual(len(registry), 2)
        self.assertEqual([row["status"] for row in registry], ["failed", "failed"])
        self.assertEqual([row["launch"]["process_started"] for row in registry], [False, True])
        report = research_phase.build_report(self.project, "P01")
        self.assertEqual(report["status"], "complete", report)
        self.assertEqual(report["unexecuted_runs"][0]["run_id"], "P01-blocked-after-retry")
        self.assertTrue(results_validation.validate_registry(self.project, self.plan, registry))
        self.complete()
        self.assertEqual(all_compute_cost(self.project), .5)

    def test_no_start_retry_cannot_spend_beyond_the_unchanged_total(self):
        executable = self.missing_runtime()
        write(self.project / "intake/constraints.json", {"cloud_compute_budget_usd": .25, "cash_budget_usd": .25})
        self.start()
        with patch.object(steps, "_cloud_run_eligible", return_value=True):
            steps.before_cycle(self.project, "experiment-execution")
            self.restore_runtime(executable)
            blocked = steps.before_cycle(self.project, "experiment-execution")
        self.assertTrue(blocked["control_only"])
        self.assertTrue(blocked["blockers"])
        self.assertIn("budget", str(blocked["blockers"]).lower())
        self.assertEqual(len(research_quality._registry(self.project)), 1)
        self.assertEqual(all_compute_cost(self.project), .25)
        self.assertEqual(research_phase.build_report(self.project, "P01")["status"], "blocked")

    def test_cycles_duplicate_attempts_and_changed_receipts_never_authorize_exploration(self):
        self.add_probe("P01-child", dependencies=["P01-probe"])
        self.plan["runs"][0]["depends_on"] = ["P01-child"]
        write(self.plan_path, self.plan)
        self.assertTrue(automated_quality.run(self.project)["blockers"])
        self.assertEqual(all_compute_cost(self.project), 0)
        self.plan["runs"][0]["depends_on"] = []
        write(self.plan_path, self.plan)
        self.start()
        entry = runner.execute(self.slug, ["P01-probe"])[0]
        registry_path = paper_execution.artifact_path(self.project, "experiments/registry.jsonl")
        original = registry_path.read_text()
        registry_path.write_text(original + original, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate executor attempts"):
            steps.resume_experiments(self.project)
        registry_path.write_text(original, encoding="utf-8")
        receipt = self.project / "experiments/runs" / entry["attempt_id"] / "run.json"
        write(receipt, {**entry, "status": "failed"})
        blocked = steps.before_cycle(self.project, "experiment-execution")
        self.assertTrue(blocked["control_only"])
        self.assertIn("differs", str(blocked["blockers"]))
        self.assertEqual(len(research_quality._registry(self.project)), 1)

    def test_small_probe_runs_without_power_or_formal_baselines_and_returns_to_new_g3(self):
        self.start()
        frozen = read(self.project / "papers/P01/preregistration.json")
        self.assertFalse(frozen["confirmatory_lock"])
        self.assertTrue(frozen["protocol_lock"])
        self.assertEqual(frozen["research_phase"], "exploratory")
        self.assertFalse((self.project / "papers/P01/power-analysis.json").exists())
        self.assertEqual(runner.execute(self.slug)[0]["status"], "succeeded")
        self.complete()
        state = read(self.project / "state/run.json")
        self.assertEqual((state["gate"], state["active_paper"], state["status"]), ("G3", "P01", "awaiting_work"))
        self.assertNotIn("G3:P01", state["approved_gates"])
        self.assertNotIn("G4:P01", state["approved_gates"])
        self.assertEqual(all_compute_cost(self.project), .25)
        history = research_phase.histories(self.project, "P01")
        self.assertEqual(len(history), 1)
        self.assertFalse(history[0]["confirmatory_evidence"])
        next_plan = read(self.plan_path)
        self.assertTrue(next_plan["prior_outcomes_seen"])
        self.assertEqual(next_plan["prior_exploration"], [history[0]["binding"]])
        self.assertEqual(next_plan["runs"], [])
        self.assertEqual(json.loads((self.project / "results/P01/probe.json").read_text())["value"], -1)

    def test_failed_probe_remains_failed_in_archived_evidence_and_total_cost(self):
        script = self.project / "analysis/probe.py"
        script.write_text(script.read_text().replace("sys.exit(0)", "sys.exit(4)"), encoding="utf-8")
        self.plan["runs"][0]["inputs"][0]["sha256"] = sha(script)
        write(self.plan_path, self.plan)
        self.start()
        self.assertEqual(runner.execute(self.slug)[0]["status"], "failed")
        report = research_phase.build_report(self.project, "P01")
        self.assertEqual(report["status"], "complete", report)
        self.assertEqual(report["observations"][0]["status"], "failed")
        self.assertFalse(report["confirmatory_evidence"])
        self.complete()
        self.assertEqual(all_compute_cost(self.project), .25)
        archived = research_phase.histories(self.project)[0]
        rows = [json.loads(line) for line in (self.project / archived["registry_path"]).read_text().splitlines()]
        self.assertEqual(rows[0]["status"], "failed")

    def test_new_protocol_cannot_hide_exposure_or_relabel_old_run_and_output(self):
        self.start(); runner.execute(self.slug); self.complete()
        plan = {**read(self.plan_path), "status": "ready_for_review", "runs": copy.deepcopy(self.plan["runs"])}
        self.assertTrue(any("new run IDs" in error for error in research_phase.exposure_errors(self.project, plan)))
        plan["runs"][0].update(run_id="P01-new", expected_outputs=["results/P01/new.json"])
        self.assertEqual(research_phase.exposure_errors(self.project, plan), [])
        plan["prior_outcomes_seen"] = False
        self.assertTrue(any("prior_outcomes_seen" in error for error in research_phase.exposure_errors(self.project, plan)))

    def test_changed_inputs_or_unknown_rights_block_exploratory_freezing(self):
        (self.project / "analysis/probe.py").write_text("changed", encoding="utf-8")
        self.assertTrue(any("input changed" in error for error in research_phase.design_errors(self.project)))
        raw = self.project / "data/raw/unlicensed.csv"; raw.parent.mkdir(parents=True)
        raw.write_text("synthetic\n", encoding="utf-8")
        self.plan["runs"][0]["inputs"] = [{"path": "data/raw/unlicensed.csv", "sha256": sha(raw)}]
        write(self.plan_path, self.plan)
        self.assertTrue(any("licensed dataset manifest" in error for error in research_phase.design_errors(self.project)))

    def test_cli_design_writer_uses_the_same_native_operations_and_dataset_snapshot_as_api(self):
        from tests.test_dataset_fetch import valid_manifest
        raw = self.project / "data/raw/fixture.csv"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("value\n-1\n0\n1\n", encoding="utf-8")
        manifest = valid_manifest()
        manifest.update(dataset_id="fixture")
        manifest["download"].update(sha256=sha(raw), filename=raw.name, expected_bytes=raw.stat().st_size)
        (self.project / "data/datasets.jsonl").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        contract_path = self.project / "papers/P01/paper-contract.json"
        contract = read(contract_path)
        contract["datasets"] = ["fixture"]
        write(contract_path, contract)
        write(self.project / "program/cloud-operations.json", {"operations": [{
            "stage": "experiment-design", "action": "data_quality", "dataset_id": "fixture",
            "path": "data/raw/fixture.csv"}]})
        snapshot = paper_execution.dataset_snapshot(self.project)
        report = self.project / "data/quality/fixture.json"
        for controller in (autopilot, api_orchestrator):
            with self.subTest(controller=controller.__name__):
                snapshot.unlink(missing_ok=True)
                report.unlink(missing_ok=True)
                result = controller.refresh_post_write_evidence(self.slug, "experiment-design", "software-cli-design", "initial")
                self.assertIsNotNone(result["controlled_steps"])
                self.assertTrue(snapshot.is_file())
                self.assertTrue(report.is_file(), result["controlled_steps"])
                self.assertEqual(result["controlled_steps"]["operation_errors"], [])
                self.assertEqual(read(self.project / "state/run.json")["gate"], "G3")
        self.assertFalse(paper_execution.artifact_path(self.project, "experiments/registry.jsonl").exists())

    def test_invalid_phase_is_a_repairable_gate_error_and_never_selects_a_valid_phase(self):
        invalid = [json.dumps({**self.plan, "research_phase": value}) for value in ("invalid", [], {})]
        for contents in invalid:
            self.assertTrue(research_phase.plan_errors(json.loads(contents)))
        for contents in (*invalid, "[]", "{"):
            with self.subTest(contents=contents[:60]):
                self.plan_path.write_text(contents, encoding="utf-8")
                errors = researchctl.gate_errors(self.slug, "G3")
                self.assertTrue(any(error.startswith("research phase:") for error in errors), errors)
                with self.assertRaises(ValueError):
                    research_phase.phase(self.project)

    def test_selected_original_data_needs_source_version_not_license_approval(self):
        from tests.test_dataset_fetch import valid_manifest
        raw = self.project / "data/raw/fixture.csv"; raw.parent.mkdir(parents=True)
        raw.write_text("synthetic,value\na,1\n", encoding="utf-8")
        manifest = valid_manifest(); manifest.update(dataset_id="fixture")
        manifest["download"]["sha256"] = sha(raw)
        contract = read(self.project / "papers/P01/paper-contract.json"); contract["datasets"] = ["fixture"]
        write(self.project / "papers/P01/paper-contract.json", contract)
        snapshot = paper_execution.dataset_snapshot(self.project)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        self.plan["runs"][0]["inputs"].append({"path": "data/raw/fixture.csv", "sha256": sha(raw)})
        write(self.plan_path, self.plan)
        self.assertEqual(research_phase.design_errors(self.project), [])
        manifest.pop("license")
        snapshot.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        self.assertEqual(research_phase.design_errors(self.project), [])
        manifest["version"] = ""
        snapshot.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        self.assertTrue(research_phase.design_errors(self.project))

    def test_archive_tampering_cannot_erase_actual_cost(self):
        self.start(); runner.execute(self.slug); self.complete()
        archived = research_phase.histories(self.project)[0]
        (self.project / archived["registry_path"]).write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "archived exploratory evidence changed"):
            all_compute_cost(self.project)

    def test_next_probe_cannot_reset_the_cumulative_budget(self):
        self.start(); runner.execute(self.slug); self.complete()
        plan = {**read(self.plan_path), "status": "ready_for_review", "research_phase": "exploratory",
                "exploration": {**self.plan["exploration"], "prior_outcomes_seen": True},
                "runs": copy.deepcopy(self.plan["runs"])}
        script = self.project / "analysis/probe.py"
        script.write_text(script.read_text().replace("probe.json", "next.json"), encoding="utf-8")
        plan["runs"][0].update(run_id="P01-next", estimated_cost_usd=.8, expected_outputs=["results/P01/next.json"],
                                inputs=[{"path": "analysis/probe.py", "sha256": sha(script)}])
        write(self.plan_path, plan)
        self.start()
        with self.assertRaisesRegex(runner.ExperimentError, "Budget ceiling exceeded"):
            runner.execute(self.slug)
        self.assertEqual(all_compute_cost(self.project), .25)
        self.assertFalse((self.project / "results/P01/next.json").exists())


if __name__ == "__main__":
    unittest.main()
