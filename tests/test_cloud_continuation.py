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

    def test_non_scientific_constraints_edit_does_not_withhold_existing_task_authority(self):
        held=(self.project/model_spend.FILE).read_bytes()
        self.constraints.write_text(self.constraints.read_text()+"\n")
        self.policy["g0_approval_artifact_sha256"]="0"*64
        researchctl.write_json(self.project/continuation.POLICY,self.policy)
        self.assertTrue(self.decision()["should_run"])
        self.assertEqual((self.project/model_spend.FILE).read_bytes(),held)
        self.policy["enabled"]=False
        researchctl.write_json(self.project/continuation.POLICY,self.policy)
        self.assertEqual(self.decision()["reason"],"not_enabled")

    def test_historical_gate_identity_does_not_control_current_task(self):
        state=researchctl.load_state("my-phd")
        state["approvals"][0]["actor"]="Legacy imported record"
        researchctl.save_state("my-phd",state)
        before=(self.project/"state/run.json").read_bytes()
        self.assertTrue(self.decision()["should_run"])
        self.assertEqual((self.project/"state/run.json").read_bytes(),before)

    def test_optional_legacy_checks_and_pending_review_do_not_advance_or_block(self):
        state=researchctl.load_state("my-phd");state["status"]="awaiting_approval"
        researchctl.save_state("my-phd",state)
        before=(self.project/"state/run.json").read_bytes()
        with patch.object(researchctl,"gate_errors",side_effect=AssertionError("legacy diagnostics are optional")):
            self.assertEqual(self.decision()["reason"],"current_task_work_allowed")
        self.assertEqual((self.project/"state/run.json").read_bytes(),before)

    def test_task_controller_never_synthesizes_a_topic_approval(self):
        before=researchctl.load_state("my-phd")
        decision=self.decision()
        self.assertFalse(continuation.transition_ready_gate("my-phd",decision))
        self.assertEqual(researchctl.load_state("my-phd"),before)

    def test_legacy_pending_design_can_continue_without_rewriting_its_history(self):
        state=researchctl.load_state("my-phd")
        state.update(stage_index=3,stage="experiment-design",gate="G3",status="awaiting_approval")
        researchctl.save_state("my-phd",state)
        self.assertTrue(self.decision()["should_run"])
        self.assertEqual(researchctl.load_state("my-phd"),state)

    def test_new_question_needs_existing_budget_but_no_g0_certificate(self):
        state=researchctl.load_state("my-phd")
        state.update(stage_index=0,stage="intake",gate="G0",status="awaiting_approval",approved_gates=[],approvals=[])
        researchctl.save_state("my-phd",state)
        self.assertTrue(self.decision()["should_run"])
        self.assertEqual(researchctl.load_state("my-phd"),state)
        control=model_spend.read(self.project);control["authorized_ceiling_cny"]=0
        model_spend.write(self.project,control)
        self.assertEqual(self.decision()["reason"],"cumulative_budget_boundary")

    def test_task_selection_does_not_require_other_papers_or_prior_stage_seals(self):
        for stage in ("experiment-execution","writing-and-review"):
            for paper in ("P01","P02"):
                with self.subTest(stage=stage,paper=paper):
                    work=researchctl.select_work("my-phd","Inspect actual evidence",paper,stage)
                    state=researchctl.load_state("my-phd");state["approvals"]=[];state["approved_gates"]=[]
                    researchctl.save_state("my-phd",state)
                    self.assertTrue(self.decision()["should_run"])
                    self.assertEqual(researchctl.current_work("my-phd")["paper_id"],paper)
                    self.assertEqual(researchctl.load_state("my-phd")["approvals"],[])

    def test_legacy_execution_keeps_global_prior_protocol_seals(self):
        state = researchctl.load_state("my-phd")
        state.update(stage_index=4, stage="experiment-execution", gate="G4")
        for gate in ("G1", "G2", "G3"):
            state["approved_gates"].append(gate)
            state["approvals"].append({"gate": gate, "actor": "Synthetic legacy fixture"})
        researchctl.save_state("my-phd", state)
        with patch.object(researchctl, "gate_errors", return_value=["Synthetic evidence pending"]):
            self.assertTrue(self.decision()["should_run"])

    def test_explicit_task_pause_is_respected_while_legacy_topic_state_is_compatible(self):
        state=researchctl.load_state("my-phd")
        state.update(stage_index=2,stage="paper-architecture",gate="G2",status="awaiting_approval")
        researchctl.save_state("my-phd",state)
        self.assertTrue(self.decision()["should_run"])
        state["current_work"]={"task":"Inspect a question","stage":"paper-architecture","paper_id":"P01","status":"paused"}
        researchctl.save_state("my-phd",state)
        self.assertFalse(self.decision()["should_run"])
        self.assertEqual(researchctl.load_state("my-phd")["current_work"]["status"],"paused")

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
                    {"UUAPI_OPENAI_MODEL": "unknown-unpriced-model"},
                    {"DR_OS_MODEL_PRICING_JSON": "{}"}]
        for change in variants:
            value = self.decision({**self.env, **change})
            self.assertEqual(value["reason"], "configuration_pending")
            self.assertNotIn("private-value", json.dumps(value))
            self.assertNotIn(self.env["UUAPI_API_KEY"], json.dumps(value))

    def test_startup_report_is_read_only_and_does_not_claim_live_authentication(self):
        before = {p: p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        with patch("scripts.ai_providers.urllib.request.urlopen") as transport:
            report = continuation.startup_report("my-phd", self.env)
            transport.assert_not_called()
        self.assertTrue(report["configuration_ready"])
        self.assertTrue(report["ready_to_continue"])
        self.assertFalse(report["provider_authentication_verified"])
        self.assertFalse(report["scientific_completion_verified"])
        self.assertEqual(report["budget"]["remaining_cny"], 300)
        self.assertEqual(before, {p: p.read_bytes() for p in self.project.rglob("*") if p.is_file()})
        state = researchctl.load_state("my-phd")
        state["status"] = "awaiting_approval"
        researchctl.write_json(self.project / "state/run.json", state)
        report = continuation.startup_report("my-phd", self.env)
        self.assertTrue(report["ready_to_continue"])
        self.assertEqual(report["continuation"]["reason"], "current_task_work_allowed")

    def test_separate_gateway_configuration_and_cycle_use_the_same_validation(self):
        env = {key: value for key, value in self.env.items() if key not in {"UUAPI_API_KEY", "UUAPI_BASE_URL"}}
        for family in ("OPENAI", "ANTHROPIC"):
            env[f"UUAPI_{family}_API_KEY"] = f"fixture-{family.lower()}-key"
            env[f"UUAPI_{family}_BASE_URL"] = f"https://{family.lower()}.example.invalid/v1"
        self.assertTrue(self.decision(env)["should_run"])
        with patch.dict(os.environ, env, clear=True), patch.object(cloud_job, "ROOT", self.root):
            command = cloud_job.cycle_command({"action": "cycle"}, "my-phd")
            self.assertNotIn("--writer-provider", command)
        for field, bad in (("UUAPI_OPENAI_PROTOCOL", "unknown"),
                           ("UUAPI_OPENAI_CHAT_TOKEN_FIELD", "unbounded"),
                           ("UUAPI_STRICT_MODEL_ID", "false"),
                           ("UUAPI_OPENAI_BASE_URL", "https://example.invalid/v1/responses"),
                           ("UUAPI_OPENAI_API_KEY", "")):
            invalid = {**env, field: bad}
            self.assertEqual(self.decision(invalid)["reason"], "configuration_pending")
            with patch.dict(os.environ, invalid, clear=True), patch("scripts.ai_providers.urllib.request.urlopen") as transport:
                self.assertFalse(continuation.startup_report("my-phd",invalid)["configuration_ready"])
                transport.assert_not_called()

    def test_preflight_cloud_job_restores_state_without_paid_calls_or_followup(self):
        runtime = self.root / ".runtime"
        request = cloud_job.validate_request({"schema_version": "1.0", "action": "preflight",
                                              "project": "my-phd", "actor": "Owner", "allow_paid": False})
        before = (self.project / model_spend.FILE).read_bytes()
        with patch.dict(os.environ, self.env, clear=True), patch.object(cloud_job, "ROOT", self.root), \
                patch.object(cloud_job, "RUNTIME", runtime), patch.object(cloud_job, "ARTIFACT", runtime / "cloud-artifact"), \
                patch.object(cloud_job, "restore_state", return_value=(self.root / "worktree", "cloud-state/my-phd")) as restore, \
                patch.object(cloud_job, "persist_state", return_value=[]), patch.object(cloud_job, "git"), \
                patch.object(cloud_job, "run_command") as command, \
                patch("scripts.ai_providers.urllib.request.urlopen") as transport:
            self.assertEqual(cloud_job.run_job(request, "123456"), 0)
            restore.assert_called_once_with("my-phd")
            command.assert_not_called()
            transport.assert_not_called()
        report = json.loads((runtime / "cloud-artifact/gateway-startup.json").read_text())
        self.assertTrue(report["ready_to_continue"])
        self.assertEqual(before, (self.project / model_spend.FILE).read_bytes())
        self.assertFalse((runtime / "continuation-followup.json").exists())
        self.assertNotIn(self.env["UUAPI_API_KEY"], json.dumps(report))

    def test_only_cumulative_remaining_cost_capacity_blocks_calls(self):
        value = model_spend.read(self.project)
        value["spent_cny"] = 300
        model_spend.write(self.project, value)
        self.assertEqual(self.decision()["reason"], "cumulative_budget_boundary")
        value["spent_cny"] = 60
        value["paper_spent_cny"] = {"P01": 60}
        model_spend.write(self.project, value)
        self.assertTrue(self.decision()["should_run"])
        value["spent_cny"] = 0
        value["paper_spent_cny"] = {}
        model_spend.write(self.project, value)
        model_spend.reserve(self.project, max_cost_cny=5, paper_id="P01", paper_limit_cny=60, run_id="ambiguous")
        self.assertTrue(self.decision()["should_run"])
        self.assertEqual(self.decision()["remaining_cny"], 295)
        model_spend.reserve(self.project, max_cost_cny=295, paper_id="P01", paper_limit_cny=60, run_id="remaining")
        self.assertEqual(self.decision()["reason"], "cumulative_budget_boundary")

    def test_one_failed_checkpoint_does_not_create_a_permanent_task_lock(self):
        continuation.checkpoint("my-phd",self.decision(),"failed-run",cycle_exit_code=124)
        self.assertTrue(self.decision()["should_run"])
        idle={**self.decision(),"should_run":False,"reason":"cumulative_budget_boundary"}
        continuation.checkpoint("my-phd",idle,"idle-1")
        before=(self.project/continuation.STATUS).read_bytes()
        continuation.checkpoint("my-phd",idle,"idle-2")
        self.assertEqual(before,(self.project/continuation.STATUS).read_bytes())

    def test_requested_completion_target_stops_without_inventing_publication_approval(self):
        state=researchctl.load_state("my-phd")
        state.update(stage_index=6,stage="submission-ready",gate=None,status="submission_ready")
        state["paper_statuses"]={f"P{index:02d}":"submission_ready" for index in range(1,4)}
        researchctl.save_state("my-phd",state)
        self.assertEqual(self.decision()["reason"],"all_papers_submission_ready")
        self.assertNotIn("G5",state["approved_gates"])
        self.policy["stop_when"]="manual"
        researchctl.write_json(self.project/continuation.POLICY,self.policy)
        researchctl.select_work("my-phd","Revise the discussion",stage="writing-and-review")
        self.assertTrue(self.decision()["should_run"])

    def test_wakeup_trust_and_followup_commands_have_fixed_scope(self):
        event = {"repository": {"full_name": cloud_job.REPOSITORY, "owner": {"id": cloud_job.OWNER_ID}},
                 "sender": {"id": cloud_job.OWNER_ID}}
        env = {"GITHUB_REPOSITORY": cloud_job.REPOSITORY, "GITHUB_REF": "refs/heads/main",
               "GITHUB_EVENT_NAME": "workflow_dispatch"}
        self.assertEqual(continuation.scheduled_request(event, env)["action"], "preflight")
        self.assertFalse(continuation.scheduled_request(event, env)["allow_paid"])
        event["inputs"] = {"mode": "start"}
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
                                                        "--ref", "main", "--repo", cloud_job.REPOSITORY, "-f", "mode=start"])
            researchctl.write_json(path, {"project": "my-phd", "should_run": False, "reason": "all_papers_submission_ready"})
            continuation.enqueue_followup(path)
            self.assertEqual(command.call_args.args[0], ["gh", "api", "--method", "PUT",
                                                        f"repos/{cloud_job.REPOSITORY}/actions/workflows/research-continuation.yml/disable"])

    def model_attempt(self, run_id, *, failed=False):
        # Synthetic transport ledger, not scientific evidence or a real charge.
        with (self.project / "state/model-usage.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"run_id": run_id, "role": "semantic-planner", "cache_hit": False,
                "transport_error_type": "ProviderError" if failed else None,
                "cost_status": "accounted_upper_bound", "cost_cny": None}) + "\n")

    def test_actual_writer_failures_count_once_and_scheduled_task_stops(self):
        from scripts import api_orchestrator, ai_providers, autopilot, cloud_progress
        stages=json.loads((api_orchestrator.ROOT/"config/stages.json").read_text())
        researchctl.write_json(self.root/"config/stages.json",stages)
        with patch.dict(os.environ,{**self.env,"DR_OS_REQUIRE_MODEL_AUTH":"1","DR_OS_REQUIRE_REMOTE_RESERVATION":"0"},clear=True), patch.object(api_orchestrator,"ROOT",self.root), patch.object(ai_providers,"call",side_effect=[ai_providers.ProviderError("Synthetic transport failure"),KeyboardInterrupt("Synthetic canceled transport")]) as transport:
            for index in range(2):
                with self.assertRaises((ai_providers.ProviderError,KeyboardInterrupt)):
                    autopilot.run_stage("my-phd",writer_provider="uuapi-openai")
                report=cloud_progress.read(self.project/cloud_progress.FILE)
                self.assertEqual(report["stalled_cycles"],index+1)
                self.assertEqual(report["model_cycles"],index+1)
                self.assertFalse(report["scientific_progress_verified"])
            held=(self.project/model_spend.FILE).read_bytes()
            with self.assertRaisesRegex(ValueError,"no_new_research_inputs"):
                autopilot.run_stage("my-phd",writer_provider="uuapi-openai")
            self.assertEqual(transport.call_count,2)
            self.assertEqual((self.project/model_spend.FILE).read_bytes(),held)
            self.assertEqual(len(model_spend.read(self.project)["reservations"]),2)
            self.assertEqual(self.decision()["reason"],"no_new_research_inputs")
            researchctl.select_work("my-phd","Examine a newly identified limitation")
            self.assertTrue(self.decision()["should_run"])
            self.assertEqual((self.project/model_spend.FILE).read_bytes(),held)

    def test_interrupted_cycle_is_recovered_before_another_request_and_report_flags_do_not_count(self):
        from scripts import cloud_progress
        before = cloud_progress.snapshot('my-phd')
        researchctl.write_json(self.project / 'state/research-steps.json', {'paid_model_cycle': True})
        report = cloud_progress.record('my-phd', before, 'no-transport', 1)
        self.assertEqual(report['model_cycles'], 0)
        for index in range(2):
            before = cloud_progress.snapshot('my-phd')
            prior = cloud_progress.read(self.project / cloud_progress.FILE)
            researchctl.write_json(self.project / cloud_progress.FILE, {**prior, 'pending_cycle': before})
            self.model_attempt('interrupted-' + str(index), failed=True)
            # Recover the same durable marker the API reads after a killed process.
            if index == 0:
                cloud_progress.record(self.project, before, 'interrupted-api-cycle', 1)
        @cloud_progress.track_cycle(lambda slug: self.project)
        def transport(slug):
            self.fail('A clock retry must not enter another model request')
        with self.assertRaisesRegex(ValueError, 'no_new_research_inputs'):
            transport('my-phd')
        self.assertEqual(cloud_progress.read(self.project / cloud_progress.FILE)['stalled_cycles'], 2)

    def test_bookkeeping_format_and_fewer_errors_cannot_reset_paid_stall(self):
        from scripts import cloud_progress
        plan = self.project / 'program/literature-search-plan.json'
        dataset = self.project / 'evidence/datasets.jsonl'
        original = {'generated_at': 'old', 'queries': ['mechanism A', 'counter evidence'],
                    'hypothesis': 'The actual first mechanism predicts higher error.'}
        researchctl.write_json(plan, original)
        dataset.write_text('{"id":"fixture","source":"primary"}\n', encoding='utf-8')
        for index in range(2):
            with patch.object(researchctl, 'gate_errors', return_value=['A', 'B']):
                before = cloud_progress.snapshot('my-phd')
            self.model_attempt('unchanged-' + str(index), failed=True)
            with patch.object(researchctl, 'gate_errors', return_value=['A']):
                report = cloud_progress.record('my-phd', before, str(index), 1)
                self.assertFalse(report['control_progress'])
                self.assertEqual(report['stalled_cycles'], index + 1)
        researchctl.write_json(plan, {**original, 'generated_at': 'new'})
        dataset.write_text('\n{ "source": "primary", "id": "fixture" }\n\n', encoding='utf-8')
        state = researchctl.load_state('my-phd')
        state.setdefault('history', []).append({'event': 'mechanical_check', 'at': 'later'})
        researchctl.save_state('my-phd', state)
        researchctl.write_json(self.project / 'reports/c-audit.json', {'generated_at': 'later', 'pass': True})
        with patch.object(researchctl, 'gate_errors', return_value=[]):
            self.assertEqual(cloud_progress.pause_reason('my-phd')['reason'], 'no_new_research_inputs')
        researchctl.write_json(plan, {**original, 'hypothesis': 'A different mechanism predicts lower error.'})
        self.assertIsNone(cloud_progress.pause_reason('my-phd'))

    def test_failed_attempt_ids_and_billing_changes_remain_activity_until_actual_new_results(self):
        from scripts import cloud_progress
        from scripts.research_artifacts import sha
        rows = []
        for index in range(2):
            before = cloud_progress.snapshot('my-phd')
            self.model_attempt('failed-science-' + str(index), failed=True)
            row = {'attempt_id': 'synthetic-failure-' + str(index), 'paper_id': 'P01',
                   'status': 'failed', 'estimated_cost_usd': 0.2, 'outputs': []}
            rows.append(row)
            researchctl.write_json(self.project / f"experiments/runs/{row['attempt_id']}/run.json", row)
            (self.project / 'experiments/registry.jsonl').write_text(
                ''.join(json.dumps(item) + '\n' for item in rows), encoding='utf-8')
            report = cloud_progress.record('my-phd', before, str(index), 1)
            self.assertEqual(report['stalled_cycles'], index + 1)
            self.assertEqual(report['new_experiment_attempts'], 1)
            self.assertFalse(report['scientific_progress_verified'])
        rows[-1].update(reported_cost_usd=0.3, runtime_seconds=10, completed_at='later')
        researchctl.write_json(self.project / f"experiments/runs/{rows[-1]['attempt_id']}/run.json", rows[-1])
        (self.project / 'experiments/registry.jsonl').write_text(
            ''.join(json.dumps(item) + '\n' for item in rows), encoding='utf-8')
        self.assertEqual(cloud_progress.pause_reason('my-phd')['reason'], 'no_new_research_inputs')
        source = self.project / 'results/actual-negative.json'
        researchctl.write_json(source, {'synthetic_fixture_only': True, 'effect': -0.2})
        result = {'attempt_id': 'synthetic-negative-result', 'paper_id': 'P01', 'status': 'succeeded',
                  'estimated_cost_usd': 0.2, 'outputs': [{'path': 'results/actual-negative.json', 'sha256': sha(source)}]}
        researchctl.write_json(self.project / f"experiments/runs/{result['attempt_id']}/run.json", result)
        with (self.project / 'experiments/registry.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(result) + '\n')
        self.assertIsNone(cloud_progress.pause_reason('my-phd'))
        before = cloud_progress.snapshot('my-phd')
        self.model_attempt('inspect-new-negative')
        report = cloud_progress.record('my-phd', before, 'new-evidence', 0)
        self.assertEqual(report['stalled_cycles'], 1)
        self.assertFalse(report['scientific_progress_verified'])

    def test_new_source_content_resumes_but_the_same_search_serialization_does_not(self):
        from scripts import cloud_progress
        from scripts.research_artifacts import sha
        result = self.project / 'evidence/search/normalized.json'
        researchctl.write_json(result, {'works': [{'id': 'source-A', 'title': 'Counterevidence'}]})
        ledger = self.project / 'evidence/literature-api-ledger.jsonl'
        receipt = {'status': 'success', 'normalized_results_path': 'evidence/search/normalized.json',
                   'normalized_results_sha256': sha(result), 'response_sha256': 'a' * 64}
        ledger.write_text(json.dumps(receipt) + '\n', encoding='utf-8')
        for index in range(2):
            before = cloud_progress.snapshot('my-phd')
            self.model_attempt('same-source-' + str(index))
            cloud_progress.record('my-phd', before, str(index), 0)
        result.write_text('{"works": [{"title": "Counterevidence", "id": "source-A"}]}\n\n', encoding='utf-8')
        receipt.update(normalized_results_sha256=sha(result), response_sha256='b' * 64)
        ledger.write_text(json.dumps(receipt) + '\n', encoding='utf-8')
        self.assertEqual(cloud_progress.pause_reason('my-phd')['reason'], 'no_new_research_inputs')
        researchctl.write_json(result, {'works': [{'id': 'source-A', 'title': 'Counterevidence'},
                                                {'id': 'source-B', 'title': 'New primary evidence'}]})
        receipt['normalized_results_sha256'] = sha(result)
        ledger.write_text(json.dumps(receipt) + '\n', encoding='utf-8')
        self.assertIsNone(cloud_progress.pause_reason('my-phd'))

    def test_repeated_source_screening_receipts_do_not_manufacture_new_inputs(self):
        from scripts import cloud_progress, literature_evidence, literature_model_screening as screening, ai_providers
        from tests.test_literature_model_screening import ModelScreeningTests
        with tempfile.TemporaryDirectory() as directory:
            project = ModelScreeningTests().fixture(directory)
            researchctl.write_json(project / 'state/run.json', {'stage': 'topic-intelligence', 'active_paper': 'P01'})
            previous = None
            for index in range(2):
                if index:
                    receipt = literature_evidence.read_jsonl(project / 'evidence/literature-api-ledger.jsonl')[0]
                    receipt['receipt_id'] = 'search2'
                    literature_evidence.append_jsonl(project / 'evidence/literature-api-ledger.jsonl', receipt)
                    literature_evidence.append_jsonl(project / 'evidence/search-log.jsonl', {'evidence_receipt_id': 'search2'})
                selected = screening.cycle_input(project, 'Which source distinguishes the mechanism?')
                prompt = selected['packet_prompt']
                content = json.dumps({'decisions': [{'id': key, 'decision': 'include',
                    'reason': 'Related source; wording version ' + str(index)} for key in ('a', 'b')]})
                bundle = {'artifacts': [{'path': selected['artifact_path'], 'content': content}]}
                result = ai_providers.ModelResult(provider='openai', model='synthetic-writer', reported_model='synthetic-writer',
                    text=json.dumps(bundle), usage={}, request_id='fixture-' + str(index), completion_status='completed')
                run = 'fixture-screening-' + str(index)
                literature_evidence.append_jsonl(project / 'state/model-usage.jsonl', {'run_id': run,
                    'prompt_sha256': screening._digest(prompt), 'request_id': result.request_id,
                    'model': result.model, 'completion_status': 'completed'})
                screening.accept_cycle_result(project, selected, prompt, result, run, bundle)
                current = cloud_progress.snapshot(project)['receipts']
                if previous is not None:
                    self.assertEqual(current, previous)
                previous = current

    def legacy_pause(self):
        from scripts import cloud_progress
        checkpoint = {**cloud_progress.snapshot('my-phd'),
                      'model_cycles': 2, 'stalled_cycles': 2, 'control_cycles': 0}
        checkpoint.pop('input_fingerprint_version')
        checkpoint['human_inputs'] = cloud_progress.digest({p: cloud_progress.read(self.project / p) for p in (
            'state/run.json', 'state/data-authorizations.json', 'state/human-inputs.json')})
        checkpoint['work_inputs'] = 'f' * 64  # Opaque earlier algorithm, not a comparable v3 digest.
        researchctl.write_json(self.project / cloud_progress.FILE, checkpoint)
        return checkpoint

    def test_fingerprint_upgrade_preserves_existing_pause_without_mutating_it(self):
        from scripts import cloud_progress
        checkpoint = self.legacy_pause()
        before = (self.project / cloud_progress.FILE).read_bytes()
        state = researchctl.load_state('my-phd')
        state.setdefault('history', []).append({'event': 'mechanical_check', 'at': 'later'})
        researchctl.save_state('my-phd', state)
        held = (self.project / model_spend.FILE).read_bytes()
        files = {p: p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        self.assertEqual(cloud_progress.pause_reason('my-phd')['reason'], 'no_new_research_inputs')
        self.assertEqual({p: p.read_bytes() for p in self.project.rglob('*') if p.is_file()}, files)
        @cloud_progress.track_cycle(lambda slug: self.project)
        def transport(slug):
            self.fail('Migration must not grant a retry or POST')
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, 'no_new_research_inputs'):
                transport('my-phd')
        events = [json.loads(line) for line in (self.project / cloud_progress.RESUMES).read_text().splitlines()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['previous_progress'], checkpoint)
        self.assertFalse(events[0]['grants_retry'])
        self.assertEqual((self.project / cloud_progress.FILE).read_bytes(), before)
        self.assertEqual((self.project / model_spend.FILE).read_bytes(), held)
        researchctl.write_json(self.project / 'program/hypothesis-register.json',
                               {'hypotheses': [{'id': 'H1', 'hypothesis': 'A newly specified competing mechanism.'}]})
        self.assertIsNone(cloud_progress.pause_reason('my-phd'))

    def test_cloud_paused_job_binds_legacy_baseline_once_after_existing_authority_checks(self):
        from scripts import cloud_progress
        self.legacy_pause()
        for index in range(3):
            model_spend.reserve(self.project, max_cost_cny=1, paper_id=None, paper_limit_cny=0, run_id='old-hold-' + str(index))
        checkpoint = (self.project / cloud_progress.FILE).read_bytes()
        held = (self.project / model_spend.FILE).read_bytes()
        runtime = self.root / '.runtime'
        request = cloud_job.validate_request({'schema_version': '1.0', 'action': 'continuation',
                                             'project': 'my-phd', 'actor': 'Owner'})
        with patch.dict(os.environ, self.env, clear=True), patch.object(cloud_job, 'ROOT', self.root), \
                patch.object(cloud_job, 'RUNTIME', runtime), patch.object(cloud_job, 'ARTIFACT', runtime / 'cloud-artifact'), \
                patch.object(cloud_job, 'restore_state', return_value=(self.root / 'dummy-worktree', 'cloud-state/my-phd')), \
                patch.object(cloud_job, 'persist_state', return_value=[]), patch.object(cloud_job, 'git'), \
                patch.object(cloud_job, 'run_command') as transport:
            wrong_actor = {**request, 'actor': 'AnotherOwner'}
            self.assertEqual(cloud_job.run_job(wrong_actor, '123450'), 0, (runtime / 'cloud-artifact/redacted-log.txt').read_text())
            self.assertFalse((self.project / cloud_progress.RESUMES).exists())
            for run in ('123451', '123452'):
                self.assertEqual(cloud_job.run_job(request, run), 0, (runtime / 'cloud-artifact/redacted-log.txt').read_text())
            transport.assert_not_called()
        self.assertEqual(len((self.project / cloud_progress.RESUMES).read_text().splitlines()), 1)
        self.assertEqual((self.project / cloud_progress.FILE).read_bytes(), checkpoint)
        self.assertEqual((self.project / model_spend.FILE).read_bytes(), held)
        self.assertEqual(self.decision()['reason'], 'no_new_research_inputs')

    def test_hypothesis_and_ordered_search_changes_are_real_inputs_but_nested_times_are_preserved(self):
        from scripts import cloud_progress, cloud_research_steps as steps, literature_evidence
        hypothesis = self.project / 'program/hypothesis-register.json'
        researchctl.write_json(hypothesis, {'hypotheses': [{'id': 'H1', 'hypothesis': 'Mechanism A'}]})
        plan = self.project / 'program/literature-search-plan.json'
        searches = [{'provider': 'crossref', 'query': query, 'query_family': 'direct', 'limit': 1}
                    for query in ('mechanism A', 'mechanism B')]
        researchctl.write_json(plan, {'searches': searches, 'max_search_calls': 1})
        checkpoint = {**cloud_progress.snapshot('my-phd'), 'stalled_cycles': 2}
        researchctl.write_json(self.project / cloud_progress.FILE, checkpoint)
        self.assertEqual(cloud_progress.pause_reason('my-phd')['reason'], 'no_new_research_inputs')
        researchctl.write_json(hypothesis, {'hypotheses': [{'id': 'H1', 'hypothesis': 'Mechanism B'}]})
        self.assertIsNone(cloud_progress.pause_reason('my-phd'))
        checkpoint = {**cloud_progress.snapshot('my-phd'), 'stalled_cycles': 2}
        researchctl.write_json(self.project / cloud_progress.FILE, checkpoint)
        def search(project, provider, query, **kwargs):
            return {'receipt_id': 'synthetic-' + query[-1], 'provider': provider, 'normalized_results_path': 'evidence/empty-fixture.json'}
        researchctl.write_json(self.project / 'evidence/empty-fixture.json', {'works': []})
        with patch.object(literature_evidence, 'execute_search', side_effect=search) as execute:
            first = steps.literature_context(self.project, 'unused')
            researchctl.write_json(plan, {'searches': list(reversed(searches)), 'max_search_calls': 1})
            self.assertIsNone(cloud_progress.pause_reason('my-phd'))
            second = steps.literature_context(self.project, 'unused')
        self.assertEqual([call.args[2] for call in execute.call_args_list], ['mechanism A', 'mechanism B'])
        self.assertEqual([first['new_search_calls'], second['new_search_calls']], [1, 1])
        scientific_times = {'data': [{'force': 1, 'updated_at': '2026-01-01', 'generated_at': '2026-01-01'}]}
        changed_times = {'data': [{'force': 1, 'updated_at': '2026-01-02', 'generated_at': '2026-01-02'}]}
        self.assertNotEqual(cloud_progress.research_input(scientific_times), cloud_progress.research_input(changed_times))
        researchctl.write_json(plan, {**scientific_times, 'searches': searches})
        before = cloud_progress.work_inputs(self.project)
        researchctl.write_json(plan, {**changed_times, 'searches': searches})
        self.assertNotEqual(before, cloud_progress.work_inputs(self.project))

    def test_drafting_and_proof_work_continue_without_claiming_verified_science(self):
        from scripts import cloud_progress
        draft=self.project/"papers/P01/manuscript/main.tex"
        for index in range(3):
            before=cloud_progress.snapshot("my-phd")
            self.model_attempt("draft-"+str(index))
            draft.write_text("Proof step "+str(index)+": consider the boundary case.")
            report=cloud_progress.record("my-phd",before,str(index),0)
            self.assertTrue(report["research_outputs_changed"])
            self.assertEqual(report["stalled_cycles"],0)
            self.assertFalse(report["scientific_progress_verified"])
            self.assertTrue(self.decision()["should_run"])
        self.assertEqual(model_spend.read(self.project)["authorized_ceiling_cny"],300)
        self.assertEqual(researchctl.load_state("my-phd")["approved_gates"],["G0"])

    def test_new_work_inputs_resume_a_stall_but_a_draft_timestamp_does_not(self):
        from scripts import cloud_progress
        query_plan = self.project / 'program/literature-search-plan.json'
        original_plan = {'queries': ['existing discriminating query'], 'max_search_calls': 12}
        researchctl.write_json(query_plan, original_plan)
        researchctl.write_json(self.project / 'state/research-steps.json', {'paid_model_cycle': True, 'blockers': []})
        with patch.object(researchctl, 'gate_errors', return_value=['Missing controlled evidence']):
            for index in range(cloud_progress.MAX_STALLED_CYCLES):
                before = cloud_progress.snapshot('my-phd')
                self.model_attempt(str(index))
                cloud_progress.record('my-phd', before, str(index), 0)
            self.assertFalse(self.decision()['should_run'])
            topic=self.project/'program/topic.md'
            topic.write_text(topic.read_text()+'\n\n   ')
            self.assertFalse(self.decision()['should_run'])
            query_plan.write_text(json.dumps(original_plan, sort_keys=True, indent=4) + '\n\n')
            self.assertFalse(self.decision()['should_run'])
            researchctl.write_json(self.project / 'program/literature-search-plan.json',
                                   {'queries': ['new discriminating source query']})
            self.assertTrue(self.decision()['should_run'])
            before = cloud_progress.snapshot('my-phd')
            self.model_attempt('new-input')
            report = cloud_progress.record('my-phd', before, 'new-input', 0)
            self.assertEqual(report['stalled_cycles'], 1)
            self.assertTrue(self.decision()['should_run'])
        self.assertEqual(model_spend.read(self.project)['authorized_ceiling_cny'], 300)

    def test_fewer_check_errors_do_not_claim_scientific_progress(self):
        from scripts import cloud_progress
        with patch.object(researchctl,"gate_errors",return_value=["A","B"]):
            before=cloud_progress.snapshot("my-phd")
        with patch.object(researchctl,"gate_errors",return_value=["A"]):
            result=cloud_progress.record("my-phd",before,"software-control-test",0)
        self.assertFalse(result["control_progress"])
        self.assertIsNone(result["semantic_progress"])
        self.assertFalse(result["scientific_progress_verified"])
        self.assertEqual(result["new_experiment_attempts"],0)

    def test_new_executable_input_during_the_cycle_is_not_discarded_by_stall_detection(self):
        from scripts import cloud_progress
        researchctl.write_json(self.project/'state/research-steps.json',{'paid_model_cycle':True,'blockers':[]})
        with patch.object(researchctl,'gate_errors',return_value=['Missing controlled evidence']):
            for index in range(2):
                before=cloud_progress.snapshot('my-phd')
                self.model_attempt('input-'+str(index))
                researchctl.write_json(self.project/'program/literature-search-plan.json',
                                       {'queries':['new discriminating query '+str(index)]})
                report=cloud_progress.record('my-phd',before,'input-'+str(index),0)
                self.assertTrue(report['new_work_inputs'])
                self.assertEqual(report['stalled_cycles'],0)
                self.assertFalse(report['scientific_progress_verified'])
                self.assertTrue(self.decision()['should_run'])
            before=cloud_progress.work_inputs(self.project)
            researchctl.write_json(self.project/'program/literature-workbench.json',
                                   {'papers':[{'id':'new-original-source','source':{'path':'literature/new.txt'}}]})
            self.assertNotEqual(before,cloud_progress.work_inputs(self.project))

    def test_failed_internal_attempt_is_retained_as_activity_without_claiming_scientific_success(self):
        from scripts import cloud_progress
        with patch.object(researchctl,"gate_errors",return_value=["Evidence pending"]):
            before=cloud_progress.snapshot("my-phd")
            root=self.project/"experiments/supplemental/P01/I001/s001"
            row={"attempt_id":"P01-software-fixture","paper_id":"P01","status":"failed",
                 "estimated_cost_usd":0,"outputs":[],"synthetic_fixture_only":True}
            researchctl.write_json(root/"experiments/runs/P01-software-fixture/run.json",row)
            (root/"experiments/registry.jsonl").write_text(json.dumps(row)+"\n",encoding="utf-8")
            result=cloud_progress.record("my-phd",before,"software-evidence-test",0)
        self.assertEqual(result["new_experiment_attempts"],1)
        self.assertEqual(result["experiment_attempts"][0]["status"],"failed")
        self.assertFalse(result["scientific_progress_verified"])

    def test_external_blocker_pauses_after_draft_and_new_owner_input_allows_recheck(self):
        from scripts import cloud_progress
        before=cloud_progress.snapshot('my-phd')
        researchctl.write_json(self.project/'state/research-steps.json',{'paid_model_cycle':True,'task_scope':cloud_progress.digest(researchctl.load_state('my-phd').get('current_work',{})),'blockers':[{'kind':'restricted_source_access'}]})
        cloud_progress.record('my-phd',before,'123',0)
        self.assertEqual(self.decision()['reason'],'external_input_required')
        researchctl.write_json(self.project/'state/data-authorizations.json',{'manifests':{'fixture':{'actor':'Owner'}}})
        self.assertTrue(self.decision()['should_run'])

    def test_legacy_external_review_blocker_is_rechecked_without_resetting_limits(self):
        from scripts import cloud_progress
        researchctl.write_json(self.project / "state/research-steps.json", {"blockers": [{"kind": "data_rights_review"}]})
        value = {"schema_version": "1.0", "scope": "topic-intelligence:P01",
                 "human_inputs": cloud_progress.human_inputs(self.project),
                 "errors": ["named human screening required"],
                 "external_blockers": [{"kind": "literature_screening"}],
                 "model_cycles": 0, "stalled_cycles": 0, "control_cycles": 0}
        path = self.project / cloud_progress.FILE
        researchctl.write_json(path, value)
        original = path.read_bytes()
        with patch.object(researchctl, "gate_errors", return_value=["recorded model screening required"]):
            self.assertIsNone(cloud_progress.pause_reason("my-phd"))
        self.assertEqual(path.read_bytes(), original)
        value["model_cycles"] = 100
        value["stalled_cycles"] = 100
        researchctl.write_json(path, value)
        with patch.object(researchctl, "gate_errors", return_value=["recorded model screening required"]):
            self.assertEqual(cloud_progress.pause_reason("my-phd")["reason"], "no_new_research_inputs")
        value["control_cycles"] = cloud_progress.MAX_CONTROL_CYCLES
        researchctl.write_json(path, value)
        with patch.object(researchctl, "gate_errors", return_value=["recorded model screening required"]):
            self.assertEqual(cloud_progress.pause_reason("my-phd")["reason"], "control_retry_limit")
        self.assertEqual(model_spend.read(self.project)["authorized_ceiling_cny"], 300)
