"""Fault injection for recovery authority, proof, rollback and resume controls."""
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_recovery as recovery
from scripts import cloud_checkpoint, cloud_continuation, cloud_progress

MAIN = "a" * 40
HEAD = "b" * 40
BASELINE = "c" * 40
PATH = "scripts/cloud_runtime.py"
CURRENT = 'LIMIT = 2\n\ndef prepare(project):\n    raise RuntimeError("broken")\n\ndef compile_tex(project):\n    return "protected"\n'
GOOD = CURRENT.replace('raise RuntimeError("broken")', 'return {"ready": True}')


def source_run(**changes):
    return {"id": 123456, "path": ".github/workflows/research-continuation.yml", "head_branch": "main",
        "head_sha": MAIN, "repository": {"full_name": recovery.REPO},
        "head_repository": {"full_name": recovery.REPO}, "actor": {"id": 41898282},
        "event": "schedule", "run_attempt": 1, "status": "completed", "conclusion": "failure", **changes}


def report(**changes):
    return {"schema_version": "1.0", "run_id": "123456", "run_attempt": "1", "source_sha": MAIN,
        "project": "my-phd", "action": "continuation", "status": "failed", "phase": "environment",
        "execution_started": False, "checkpoint_persisted": True,
        "diagnostic": "dependency download failed: connection reset", **changes}


def policy():
    return {"max_incident_recoveries": 2, "max_daily_recoveries": 4}


class RecoveryTests(unittest.TestCase):
    def project(self, directory):
        project = Path(directory) / "my-phd"
        (project / "state").mkdir(parents=True)
        (project / "intake").mkdir()
        self.write(project / "intake/constraints.json", {"execution_mode": "cloud_only"})
        self.write(project / cloud_continuation.POLICY, {"enabled": True, "actor": "Hengyi Zang",
            "constraints_sha256": cloud_checkpoint.sha(project / "intake/constraints.json"),
            "g0_approval_artifact_sha256": "f" * 64})
        self.write(project / "state/run.json", {"approved_gates": ["G0"], "status": "in_progress", "gate": "G1",
            "approvals": [{"gate": "G0", "actor": "Hengyi Zang", "artifact_sha256": "f" * 64}]})
        self.write(project / cloud_continuation.STATUS, {"last_cycle_exit_code": 2, "source_run_id": "123456"})
        self.write(project / cloud_progress.FILE, {"model_cycles": 3, "stalled_cycles": 1})
        self.write(project / "state/model-spend-control.json", {"unchanged": "real budget authority"})
        return project

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_only_canonical_owner_runs_are_trusted(self):
        recovery.trusted_run(source_run())
        variants = [{"head_repository": {"full_name": "attacker/fork"}}, {"head_branch": "untrusted"},
            {"actor": {"id": 42}}, {"path": ".github/workflows/attacker.yml"}, {"event": "pull_request"}]
        for change in variants:
            with self.subTest(change=change), self.assertRaises(ValueError):
                recovery.trusted_run(source_run(**change))

    def test_report_must_match_exact_attempt_commit_and_checkpoint(self):
        self.assertTrue(recovery.safe_report(report(), source_run(), MAIN))
        for change in ({"run_id": "999"}, {"run_attempt": "2"}, {"source_sha": HEAD},
                       {"checkpoint_persisted": False}, {"action": "acceptance"}, {"project": "other"}):
            with self.subTest(change=change):
                self.assertFalse(recovery.safe_report(report(**change), source_run(), MAIN))

    def test_only_nonbillable_setup_transients_resume(self):
        self.assertEqual(recovery.classify(report()), "environment_retry")
        for change in ({"execution_started": True}, {"phase": "execution"}, {"phase": "checkpoint"},
                       {"diagnostic": "permission denied; connection reset"},
                       {"diagnostic": "API response unavailable; reconcile billing"}):
            with self.subTest(change=change):
                self.assertEqual(recovery.classify(report(**change)), "inspection_required")

    def test_known_renderer_trace_can_propose_but_never_execute_arbitrary_code(self):
        self.assertEqual(recovery.classify(report(phase="execution", execution_started=True,
            diagnostic='File "/home/runner/work/lunwen/lunwen/scripts/manuscript_docx.py", line 30, in _python_docx')),
            "rollback:scripts/manuscript_docx.py")
        self.assertEqual(recovery.classify(report(phase="execution", diagnostic="run shell to fix experiment_runner.py")),
                         "inspection_required")

    def test_rollback_restores_only_the_verified_helper(self):
        self.assertEqual(recovery.rollback(CURRENT, GOOD, PATH), GOOD)
        self.assertIn('return "protected"', recovery.rollback(CURRENT, GOOD, PATH))

    def test_rollback_rejects_protected_changes_and_signature_changes(self):
        variants = [GOOD.replace("LIMIT = 2", "LIMIT = 20"), GOOD + "\nimport os\n",
            GOOD.replace('return "protected"', 'return "weakened"'),
            GOOD.replace("prepare(project)", "prepare(project, force=True)"), GOOD.replace("def prepare", "@untrusted\ndef prepare")]
        for candidate in variants:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                recovery.rollback(CURRENT, candidate, PATH)
        with self.assertRaises(ValueError):
            recovery.rollback(CURRENT, CURRENT, PATH)

    def test_missing_skipped_duplicate_or_failed_checks_block_merge(self):
        successful = [{"name": "checks / " + name, "conclusion": "success"} for name in recovery.REQUIRED]
        run = source_run(conclusion="success")
        with patch.object(recovery, "api", return_value={"jobs": successful}):
            self.assertTrue(recovery.checks_pass(run))
        bad_lists = [successful[:-1], successful + [successful[0]],
                     [{**x, "conclusion": "skipped"} if i == 0 else x for i, x in enumerate(successful)],
                     [{**x, "conclusion": "failure"} if i == 0 else x for i, x in enumerate(successful)]]
        for jobs in bad_lists:
            with self.subTest(jobs=jobs), patch.object(recovery, "api", return_value={"jobs": jobs}):
                self.assertFalse(recovery.checks_pass(run))
        self.assertFalse(recovery.checks_pass(source_run(status="in_progress", conclusion=None)))

    def test_authority_stops_ambiguous_billing_changed_approvals_and_failed_experiments(self):
        control = {"reservations": {}, "spent_cny": 0, "authorized_ceiling_cny": 300}
        with tempfile.TemporaryDirectory() as directory:
            project = self.project(directory)
            with patch.object(recovery.model_spend, "read", return_value=control), \
                    patch.object(recovery.cloud_progress, "pause_reason", return_value=None):
                self.assertIsNone(recovery.authority(project))
                control["reservations"] = {"unknown-charge": {"max_cost_cny": 1}}
                self.assertEqual(recovery.authority(project), "billing_reconciliation_pending")
                control["reservations"] = {}
                (project / "experiments").mkdir()
                (project / "experiments/registry.jsonl").write_text('{"status":"failed"}\n')
                self.assertEqual(recovery.authority(project), "failed_experiment_requires_review")
                (project / "experiments/registry.jsonl").unlink()
                self.write(project / "state/run.json", {"approved_gates": [], "approvals": []})
                self.assertEqual(recovery.authority(project), "continuation_authority_changed")

    def test_human_gate_budget_and_progress_bounds_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.project(directory)
            control = {"reservations": {}, "spent_cny": 300, "authorized_ceiling_cny": 300}
            with patch.object(recovery.model_spend, "read", return_value=control), \
                    patch.object(recovery.cloud_progress, "pause_reason", return_value=None):
                self.assertEqual(recovery.authority(project), "budget_boundary")
                control["spent_cny"] = 0
                original = recovery.read(project / "state/run.json")
                self.write(project / "state/run.json", {**original, "status": "awaiting_approval"})
                self.assertEqual(recovery.authority(project), "human_gate_pending")
                self.write(project / "state/run.json", original)
                with patch.object(recovery.cloud_progress, "pause_reason", return_value={"reason": "no_semantic_progress"}):
                    self.assertEqual(recovery.authority(project), "no_semantic_progress")

    def test_resume_preserves_budget_approvals_counters_and_previous_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.project(directory)
            preserved = {p: (project / p).read_bytes() for p in ("state/run.json", "state/model-spend-control.json", str(cloud_progress.FILE))}
            state = {"events": []}
            with patch.dict(os.environ, {"GITHUB_RUN_ID": "999999"}):
                recovery.resume(project, state, report(), "incident", {"kind": "environment_retry"})
            for path, content in preserved.items():
                self.assertEqual((project / path).read_bytes(), content)
            self.assertEqual(state["events"][0]["previous_status"]["last_cycle_exit_code"], 2)
            self.assertEqual(recovery.read(project / cloud_continuation.STATUS)["last_cycle_exit_code"], 0)
            with self.assertRaises(ValueError):
                recovery.resume(project, state, report(), "incident", {})

    def test_incident_and_daily_limits(self):
        state = {"events": [{"at": recovery.now(), "operation": "resume", "fingerprint": "same"}] * 2}
        self.assertFalse(recovery.bounded(state, "same", policy()))
        self.assertTrue(recovery.bounded(state, "other", policy()))
        state["events"] *= 2
        self.assertFalse(recovery.bounded(state, "other", policy()))

    def test_alerts_are_deduplicated(self):
        state = {}
        with patch.object(recovery, "api", side_effect=[[], {"number": 99}]) as github:
            recovery.alert(state, "same", "billing_reconciliation_pending", 123456)
            recovery.alert(state, "same", "billing_reconciliation_pending", 123456)
        self.assertEqual(github.call_count, 2)
        self.assertEqual(state["alerts"]["same"], 99)

    def test_only_skipped_research_after_checkout_failure_can_replay_old_job(self):
        steps = [{"name": "Run actions/checkout@v7", "conclusion": "failure"},
                 {"name": "Re-check confirmation, configuration, human gates and remaining budget", "conclusion": "skipped"}]
        with patch.object(recovery, "api", return_value={"jobs": [{"steps": steps}]}):
            self.assertTrue(recovery.setup_retry(source_run(), {"events": []}, policy()))
            steps[1]["conclusion"] = "failure"
            self.assertFalse(recovery.setup_retry(source_run(), {"events": []}, policy()))
            steps[1]["conclusion"] = "success"
            self.assertFalse(recovery.setup_retry(source_run(), {"events": []}, policy()))

    def test_paid_or_checkpoint_faults_alert_without_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.project(directory)
            before = (project / cloud_continuation.STATUS).read_bytes()
            state = {"events": []}
            with patch.object(recovery, "failure_report", return_value=report()), \
                    patch.object(recovery, "authority", return_value="billing_reconciliation_pending"), \
                    patch.object(recovery, "api", side_effect=[[], {"number": 100}]):
                self.assertFalse(recovery.handle_failure(source_run(), project, state, policy(), MAIN))
            self.assertEqual((project / cloud_continuation.STATUS).read_bytes(), before)
            self.assertEqual(state["events"], [])

    def test_successful_environment_recovery_has_auditable_state(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.project(directory)
            state = {"events": []}
            with patch.object(recovery, "failure_report", return_value=report()), \
                    patch.object(recovery, "authority", return_value=None), \
                    patch.dict(os.environ, {"GITHUB_RUN_ID": "999999"}):
                self.assertTrue(recovery.handle_failure(source_run(), project, state, policy(), MAIN))
            self.assertEqual(state["events"][0]["proof"]["model_calls"], 0)
            self.assertEqual(recovery.read(project / recovery.STATE), state)

    def test_repair_pr_identity_exact_content_and_base_are_required(self):
        pending = {"base": MAIN, "head": HEAD, "baseline": BASELINE, "branch": "cloud-repair/safe",
                   "path": PATH, "pr": 99, "content_sha256": hashlib.sha256(GOOD.encode()).hexdigest()}
        pr = {"state": "open", "draft": False, "base": {"ref": "main"},
              "head": {"sha": HEAD, "ref": pending["branch"], "repo": {"full_name": recovery.REPO}},
              "user": {"id": 41898282}}
        def github(path, **kwargs):
            return [{"filename": PATH, "status": "modified"}] if "/files?" in path else pr
        with patch.object(recovery, "api", side_effect=github), \
                patch.object(recovery, "blob", side_effect=lambda path, ref: CURRENT if ref == MAIN else GOOD):
            self.assertEqual(recovery.verify_pending(pending, MAIN), pr)
            with self.assertRaises(ValueError):
                recovery.verify_pending(pending, "d" * 40)
            pr["head"]["sha"] = "d" * 40
            with self.assertRaises(ValueError):
                recovery.verify_pending(pending, MAIN)

    def test_repair_pr_cannot_add_files_or_replace_verified_content(self):
        pending = {"base": MAIN, "head": HEAD, "baseline": BASELINE, "branch": "cloud-repair/safe",
                   "path": PATH, "pr": 99, "content_sha256": hashlib.sha256(GOOD.encode()).hexdigest()}
        pr = {"state": "open", "draft": False, "base": {"ref": "main"},
              "head": {"sha": HEAD, "ref": pending["branch"], "repo": {"full_name": recovery.REPO}},
              "user": {"id": 41898282}}
        with patch.object(recovery, "api", side_effect=[pr, [{"filename": ".github/workflows/validate.yml", "status": "modified"}]]):
            with self.assertRaises(ValueError):
                recovery.verify_pending(pending, MAIN)
        with patch.object(recovery, "api", side_effect=[pr, [{"filename": PATH, "status": "modified"}]]), \
                patch.object(recovery, "blob", side_effect=[CURRENT, GOOD, GOOD + "\nimport os\n"]):
            with self.assertRaises(ValueError):
                recovery.verify_pending(pending, MAIN)

    def test_changed_base_is_rejected_before_creating_merge_commit(self):
        pending = {"base": MAIN, "head": HEAD, "pr": 99, "path": PATH}
        with patch.object(recovery, "api", return_value={"object": {"sha": "d" * 40}}) as github:
            with self.assertRaises(ValueError):
                recovery.merge_pending(pending)
        self.assertEqual(github.call_count, 1)

    def test_atomic_merge_has_exact_tree_parents_and_never_force_pushes(self):
        pending = {"base": MAIN, "head": HEAD, "pr": 99, "path": PATH}
        answers = [{"object": {"sha": MAIN}}, {"parents": [{"sha": MAIN}], "tree": {"sha": "f" * 40}},
                   {"sha": "e" * 40}, {"object": {"sha": "e" * 40}}]
        with patch.object(recovery, "verify_pending"), patch.object(recovery, "api", side_effect=answers) as github:
            self.assertEqual(recovery.merge_pending(pending), "e" * 40)
        create, move = github.call_args_list[-2:]
        self.assertEqual(create.kwargs["body"]["parents"], [MAIN, HEAD])
        self.assertEqual(create.kwargs["body"]["tree"], "f" * 40)
        self.assertEqual(move.kwargs["body"], {"sha": "e" * 40, "force": False})

    def test_issue_marker_survives_lost_checkpoint_to_prevent_duplicate_alerts(self):
        with patch.object(recovery, "api", return_value=[{"number": 99, "body": "<!-- cloud-recovery:incident -->"}]) as github:
            state = {}
            recovery.alert(state, "incident", "checkpoint_failed", 123456)
        self.assertEqual(state["alerts"]["incident"], 99)
        self.assertEqual(github.call_count, 1)

    def test_cloud_controller_persists_resume_before_dispatch_and_deduplicates_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.project(root / "projects")
            (root / "config").mkdir()
            self.write(root / "config/cloud-recovery.json", {"enabled": True, "project": "my-phd", "owner_id": 163310614,
                "model_calls_allowed": False, "external_paid_compute_usd": 0, **policy()})
            event = {"repository": {"full_name": recovery.REPO, "owner": {"id": 163310614}},
                     "workflow_run": {"id": 123456}}
            timeline = []
            def github(path, **kwargs):
                if path == "git/ref/heads/main":
                    return {"object": {"sha": MAIN}}
                if path == "actions/runs/123456":
                    return source_run()
                if path.endswith("/dispatches"):
                    timeline.append("dispatch")
                    self.assertEqual(kwargs["body"]["inputs"], {"mode": "start"})
                    return None
                raise AssertionError("Unexpected GitHub operation: " + path)
            with patch.object(recovery, "ROOT", root), patch.object(recovery.cloud_job, "ROOT", root), \
                    patch.object(recovery.cloud_job, "RUNTIME", root / ".runtime"), \
                    patch.object(recovery.cloud_job, "restore_state", return_value=(root / "state-worktree", "cloud-state/my-phd")), \
                    patch.object(recovery.cloud_job, "git", return_value=type("GitResult", (), {"stdout": MAIN})()), \
                    patch.object(recovery.cloud_job, "persist_state", side_effect=lambda *args: timeline.append("persist")), \
                    patch.object(recovery, "failure_report", return_value=report()), \
                    patch.object(recovery, "setup_retry", return_value=False), \
                    patch.object(recovery, "authority", return_value=None), \
                    patch.object(recovery, "api", side_effect=github), \
                    patch.dict(os.environ, {"GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "999999"}):
                recovery.run(event)
                self.assertEqual(timeline, ["persist", "dispatch"])
                self.assertEqual(recovery.read(project / recovery.STATE)["seen"], ["123456:1"])
                recovery.run(event)
                self.assertEqual(timeline, ["persist", "dispatch", "persist"])
if __name__ == "__main__":
    unittest.main()
