"""The standing controller cannot invent human approval or billing authority."""
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_continuation as continuation, cloud_job, model_spend, researchctl
from tests import test_researchctl


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.projects = patch.object(researchctl, "PROJECTS_ROOT", self.root / "projects")
        self.projects.start()
        researchctl.initialize(types.SimpleNamespace(project="my-phd", paper_count=3, venue="ijssd"))
        self.project = researchctl.project_dir("my-phd")
        test_researchctl.ResearchCtlTests.complete_constraints(self, self.project)
        self.constraints = self.project / "intake/constraints.json"
        value = json.loads(self.constraints.read_text())
        value.update(human_review_mode="on_request", weekly_hours=None, system_execution_hours_per_day=24)
        researchctl.write_json(self.constraints, value)
        researchctl.mark_ready(types.SimpleNamespace(project="my-phd", note="Reviewed dossier"))
        researchctl.approve(types.SimpleNamespace(project="my-phd", gate="G0", actor="Owner", note="Confirmed"))
        approval = researchctl.load_state("my-phd")["approvals"][0]
        researchctl.advance(types.SimpleNamespace(project="my-phd"))
        self.policy = {"schema_version": "1.0", "enabled": True, "actor": "Owner",
                       "confirmed_at": "2026-09-30T00:00:00+00:00", "confirmation_note": "Run continuously",
                       "system_execution_hours_per_day": 24, "resume_interval_minutes": 15,
                       "constraints_sha256": continuation._sha(self.constraints),
                       "g0_approval_artifact_sha256": approval["artifact_sha256"],
                       "stop_when": "all_papers_submission_ready"}
        researchctl.write_json(self.project / continuation.POLICY, self.policy)
        model_spend.grant(self.project, new_ceiling_cny=300, actor="Owner", run_id="test-owner-grant")
        self.env = {"UUAPI_API_KEY": "synthetic-fixture-only", "UUAPI_BASE_URL": "https://example.invalid",
                    "UUAPI_ANTHROPIC_MODEL": "critic-model", "UUAPI_OPENAI_MODEL": "writer-model",
                    "DR_OS_MODEL_PRICING_JSON": json.dumps({m: {"input_per_million": 2, "output_per_million": 10}
                                                            for m in ("writer-model", "critic-model")})}

    def tearDown(self):
        self.projects.stop()
        self.temp.cleanup()

    def decision(self, env=None):
        return continuation.evaluate("my-phd", self.env if env is None else env)

    def test_allowed_evaluation_does_not_mutate_authority_or_advance(self):
        paths = [self.project / "state/run.json", self.project / model_spend.FILE]
        before = [p.read_bytes() for p in paths]
        for _ in range(2):
            self.assertTrue(self.decision()["should_run"])
        self.assertEqual(before, [p.read_bytes() for p in paths])
        self.assertEqual(len(model_spend.read(self.project)["authorization_events"]), 1)
        self.assertEqual(researchctl.load_state("my-phd")["gate"], "G1")

    def test_confirmation_binds_exact_constraints_and_actual_g0_approval(self):
        self.constraints.write_text(self.constraints.read_text() + "\n")
        self.assertEqual(self.decision()["reason"], "constraints_changed_since_confirmation")
        self.policy["constraints_sha256"] = continuation._sha(self.constraints)
        self.policy["g0_approval_artifact_sha256"] = "0" * 64
        researchctl.write_json(self.project / continuation.POLICY, self.policy)
        self.assertEqual(self.decision()["reason"], "g0_confirmation_pending")

    def test_completed_stage_or_awaiting_review_never_advances_a_gate(self):
        with patch.object(researchctl, "gate_errors", return_value=[]):
            self.assertEqual(self.decision()["reason"], "human_gate_pending")
        state = researchctl.load_state("my-phd")
        state["status"] = "awaiting_approval"
        researchctl.write_json(self.project / "state/run.json", state)
        self.assertEqual(self.decision()["reason"], "human_gate_pending")
        self.assertEqual(researchctl.load_state("my-phd")["approved_gates"], ["G0"])

    def test_missing_configuration_is_a_successful_idle_job_without_model_transport(self):
        self.assertEqual(self.decision({})["reason"], "configuration_pending")
        request = cloud_job.validate_request({"schema_version": "1.0", "action": "continuation",
                                             "project": "my-phd", "actor": "Owner", "allow_paid": True})
        runtime = self.root / ".runtime"
        with patch.dict(os.environ, {}, clear=True), patch.object(cloud_job, "ROOT", self.root), \
                patch.object(cloud_job, "RUNTIME", runtime), patch.object(cloud_job, "ARTIFACT", runtime / "cloud-artifact"), \
                patch.object(cloud_job, "restore_state", return_value=(self.root / "dummy-worktree", "cloud-state/my-phd")), \
                patch.object(cloud_job, "persist_state", return_value=[]), patch.object(cloud_job, "git"), \
                patch.object(cloud_job, "run_command") as transport:
            self.assertEqual(cloud_job.run_job(request, "123456"), 0)
            transport.assert_not_called()
        followup = json.loads((runtime / "continuation-followup.json").read_text())
        self.assertFalse(followup["should_run"])
        self.assertEqual(model_spend.read(self.project)["spent_cny"], 0)

    def test_gateway_and_exact_rates_fail_closed_without_disclosing_values(self):
        variants = [{"UUAPI_BASE_URL": "http://example.invalid"},
                    {"UUAPI_BASE_URL": "https://private-value@example.invalid"},
                    {"UUAPI_ANTHROPIC_MODEL": "writer-model"},
                    {"DR_OS_MODEL_PRICING_JSON": "{}"}]
        for change in variants:
            value = self.decision({**self.env, **change})
            self.assertEqual(value["reason"], "configuration_pending")
            self.assertNotIn("private-value", json.dumps(value))
            self.assertNotIn(self.env["UUAPI_API_KEY"], json.dumps(value))

    def test_cumulative_paper_and_unsettled_call_boundaries_block_calls(self):
        value = model_spend.read(self.project)
        value["spent_cny"] = 300
        model_spend.write(self.project, value)
        self.assertEqual(self.decision()["reason"], "cumulative_budget_boundary")
        value["spent_cny"] = 60
        value["paper_spent_cny"] = {"P01": 60}
        model_spend.write(self.project, value)
        self.assertEqual(self.decision()["reason"], "paper_budget_boundary")
        value["spent_cny"] = 0
        value["paper_spent_cny"] = {}
        model_spend.write(self.project, value)
        model_spend.reserve(self.project, max_cost_cny=5, paper_id="P01", paper_limit_cny=60, run_id="ambiguous")
        self.assertEqual(self.decision()["reason"], "billing_reconciliation_pending")

    def test_failed_cycle_requires_inspection_and_unchanged_idle_checkpoint_is_stable(self):
        continuation.checkpoint("my-phd", self.decision(), "failed-run", cycle_exit_code=124)
        value = self.decision()
        self.assertEqual(value["reason"], "previous_cycle_failed_requires_inspection")
        continuation.checkpoint("my-phd", value, "idle-1")
        before = (self.project / continuation.STATUS).read_bytes()
        continuation.checkpoint("my-phd", value, "idle-2")
        self.assertEqual(before, (self.project / continuation.STATUS).read_bytes())

    def test_all_papers_need_individual_human_approval_of_current_bytes(self):
        state = researchctl.load_state("my-phd")
        state.update(stage_index=6, stage="submission-ready", gate=None, status="submission_ready")
        for index in range(1, 5):
            state["approved_gates"].append(f"G{index}")
            state["approvals"].append({"gate": f"G{index}", "actor": "Owner"})
        state["paper_statuses"] = {}
        for index in range(1, 4):
            paper = f"P{index:02d}"
            state["paper_statuses"][paper] = "submission_ready"
            state["approved_gates"].append(f"G5:{paper}")
            state["approvals"].append({"gate": "G5", "paper_id": paper, "actor": "Owner",
                                       "paper_artifact_sha256": researchctl.paper_artifact_hash("my-phd", paper)})
        researchctl.write_json(self.project / "state/run.json", state)
        self.assertEqual(self.decision()["reason"], "all_papers_submission_ready")
        manuscript = self.project / "papers/P02/main.md"
        manuscript.write_text("Changed after approval.\n")
        self.assertEqual(self.decision()["reason"], "incomplete_or_changed_paper_approval")

    def test_wakeup_trust_and_followup_commands_have_fixed_scope(self):
        event = {"repository": {"full_name": cloud_job.REPOSITORY, "owner": {"id": cloud_job.OWNER_ID}},
                 "sender": {"id": cloud_job.OWNER_ID}}
        env = {"GITHUB_REPOSITORY": cloud_job.REPOSITORY, "GITHUB_REF": "refs/heads/main",
               "GITHUB_EVENT_NAME": "workflow_dispatch"}
        self.assertEqual(continuation.scheduled_request(event, env)["action"], "continuation")
        event["sender"]["id"] = 42
        with self.assertRaises(continuation.ContinuationError):
            continuation.scheduled_request(event, env)
        event["sender"]["id"] = cloud_job.OWNER_ID
        with self.assertRaises(continuation.ContinuationError):
            continuation.scheduled_request(event, {**env, "GITHUB_REF": "refs/heads/other"})
        path = self.root / "followup.json"
        with patch.object(continuation.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as command:
            researchctl.write_json(path, {"project": "my-phd", "should_run": False, "reason": "configuration_pending"})
            self.assertEqual(continuation.enqueue_followup(path), 0)
            command.assert_not_called()
            researchctl.write_json(path, self.decision())
            self.assertEqual(continuation.enqueue_followup(path), 0)
            self.assertEqual(command.call_args.args[0], ["gh", "workflow", "run", "research-continuation.yml",
                                                        "--ref", "main", "--repo", cloud_job.REPOSITORY])
            researchctl.write_json(path, {"project": "my-phd", "should_run": False, "reason": "all_papers_submission_ready"})
            continuation.enqueue_followup(path)
            self.assertEqual(command.call_args.args[0], ["gh", "api", "--method", "PUT",
                                                        f"repos/{cloud_job.REPOSITORY}/actions/workflows/research-continuation.yml/disable"])

    def test_prose_churn_stops_and_reviewed_resume_does_not_grant_a_gate(self):
        from scripts import cloud_progress
        researchctl.write_json(self.project/'state/research-steps.json',{'paid_model_cycle':True,'blockers':[]})
        with patch.object(researchctl,'gate_errors',return_value=['Missing controlled evidence']):
            for index in range(2):
                before=cloud_progress.snapshot('my-phd')
                (self.project/'program/topic.md').write_text('Rephrased draft '+str(index))
                cloud_progress.record('my-phd',before,str(index),0)
            self.assertEqual(self.decision()['reason'],'no_semantic_progress')
            continuation.checkpoint('my-phd',self.decision(),'123')
            status=self.project/continuation.STATUS
            with self.assertRaises(ValueError):
                cloud_progress.resume('my-phd','0'*64,'Owner','Inspected the evidence problem','124')
            cloud_progress.resume('my-phd',continuation._sha(status),'Owner','Inspected the evidence problem','124')
            self.assertTrue(self.decision()['should_run'])
        self.assertEqual(researchctl.load_state('my-phd')['approved_gates'],['G0'])
        self.assertEqual(model_spend.read(self.project)['authorized_ceiling_cny'],300)

    def test_external_blocker_pauses_after_draft_and_new_owner_input_allows_recheck(self):
        from scripts import cloud_progress
        before=cloud_progress.snapshot('my-phd')
        researchctl.write_json(self.project/'state/research-steps.json',{'paid_model_cycle':True,'blockers':[{'kind':'data_rights_review'}]})
        cloud_progress.record('my-phd',before,'123',0)
        self.assertEqual(self.decision()['reason'],'external_input_required')
        researchctl.write_json(self.project/'state/data-authorizations.json',{'manifests':{'fixture':{'actor':'Owner'}}})
        self.assertTrue(self.decision()['should_run'])
