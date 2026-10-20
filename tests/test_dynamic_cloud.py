"""Cloud task declarations and routing control cannot grant paid authority."""
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import api_orchestrator, cloud_continuation, cloud_job, cloud_progress, dynamic_routing
from tests import test_production_cycle as production_fixture
from tests import test_production_cloud_jobs as production_jobs


ROUTINE = {"task_class": "routine-implementation", "science_risk": "routine", "priority": "quality"}


def request(action="cycle", **extra):
    return {"schema_version": "1.0", "action": action, "project": "demo", "actor": "Fixture Owner",
            "allow_paid": action in cloud_job.PAID, **extra}


class DynamicCloudProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "projects" / "demo"
        (self.project / "state").mkdir(parents=True)

    @contextmanager
    def command_context(self):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}))
            stack.enter_context(patch.object(cloud_job, "ROOT", self.root))
            stack.enter_context(patch.object(cloud_progress, "pause_reason", return_value=None))
            stack.enter_context(patch.object(cloud_job.model_spend, "read", return_value={"authorized_ceiling_cny": 300}))
            stack.enter_context(patch.object(cloud_job.cloud_continuation, "configuration_errors", return_value=[]))
            stack.enter_context(patch.object(cloud_job.researchctl, "load_state", return_value={
                "stage": "experiment-execution", "gate": "G4", "status": "awaiting_work"}))
            yield

    def write_profile(self, profile=ROUTINE, stage="experiment-execution"):
        path = self.project / cloud_continuation.TASK_PROFILE
        path.write_text(json.dumps({"schema_version": "1.0", "stage": stage, "task_profile": profile}), encoding="utf-8")
        return path

    def test_cloud_profile_is_structured_and_cannot_override_model_transport_or_budget(self):
        job = request(task_profile=ROUTINE, stage="experiment-execution")
        self.assertEqual(cloud_job.validate_request(job), job)
        bad_profiles = [None, [], "routine", {**ROUTINE, "provider": "cheapai-gpt-discount"},
                        {**ROUTINE, "model": "gpt-5.6-luna"}, {**ROUTINE, "budget_cny": 300},
                        {**ROUTINE, "reasoning_effort": "low"}, {**ROUTINE, "science_risk": "cheap"}]
        for profile in bad_profiles:
            with self.subTest(profile=profile), self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request({**job, "task_profile": profile})

    def test_explicit_cycle_profile_is_validated_and_forwarded_without_budget_mutation(self):
        with self.command_context(), patch.object(cloud_job.model_spend, "grant") as grant:
            command = cloud_job.cycle_command(request(task_profile=ROUTINE), "demo")
        self.assertEqual(json.loads(command[command.index("--task-profile") + 1]),
                         dynamic_routing.validate_profile(ROUTINE, stage="experiment-execution", role="persistent-writer"))
        self.assertNotIn("--task-kind", command)
        grant.assert_not_called()

    def test_automatic_continuation_uses_explicit_current_profile_and_does_not_invent_routine(self):
        with self.command_context():
            missing = cloud_job.cycle_command(request("continuation"), "demo")
            self.assertNotIn("--task-profile", missing)
            self.write_profile()
            declared = cloud_job.cycle_command(request("continuation"), "demo")
        self.assertEqual(json.loads(declared[declared.index("--task-profile") + 1])["science_risk"], "routine")

    def test_stale_invalid_duplicate_or_oversized_continuation_profile_stops(self):
        path = self.write_profile(stage="writing-and-review")
        invalid_values = [path.read_text(), json.dumps({"schema_version": "1.0", "stage": "experiment-execution", "task_profile": None}),
                          '{"schema_version":"1.0","stage":"experiment-execution","task_profile":{},"task_profile":{}}',
                          " " * 16001]
        for value in invalid_values:
            path.write_text(value, encoding="utf-8")
            with self.subTest(value=value[:80]), self.assertRaises(cloud_continuation.ContinuationError):
                cloud_continuation.task_profile(self.project, "experiment-execution")

    def test_symlinked_continuation_profile_is_rejected(self):
        target = self.root / "profile.json"
        target.write_text(json.dumps(ROUTINE), encoding="utf-8")
        path = self.project / cloud_continuation.TASK_PROFILE
        try:
            path.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this runner")
        with self.assertRaises(cloud_continuation.ContinuationError):
            cloud_continuation.task_profile(self.project, "experiment-execution")

    def test_manager_profile_write_requires_current_stage_and_exact_update_hash(self):
        state = self.project / "state/run.json"
        state.write_text(json.dumps({"stage": "experiment-execution", "gate": "G4"}), encoding="utf-8")
        original = state.read_bytes()
        result = cloud_continuation.set_task_profile(self.project, "experiment-execution", ROUTINE,
            actor="Fixture Owner", run_id="fixture-management")
        self.assertEqual(state.read_bytes(), original)
        self.assertEqual(result["paid_calls_executed"], 0)
        self.assertEqual(result["budget_granted_cny"], 0)
        registry = json.loads((self.project / "state/output-provenance.json").read_text())
        self.assertEqual(registry["files"][cloud_continuation.TASK_PROFILE.as_posix()]["provider"],
                         "deterministic-control-plane")
        for changes in ({}, {"expected_profile_sha256": "0" * 64}):
            with self.subTest(changes=changes), self.assertRaises(cloud_continuation.ContinuationError):
                cloud_continuation.set_task_profile(self.project, "experiment-execution", ROUTINE,
                    actor="Fixture Owner", run_id="stale-management", **changes)
        critical = {"task_class": "scientific-interpretation", "science_risk": "critical"}
        updated = cloud_continuation.set_task_profile(self.project, "experiment-execution", critical,
            actor="Fixture Owner", run_id="updated-management", expected_profile_sha256=result["profile_sha256"])
        self.assertEqual(updated["previous_sha256"], result["profile_sha256"])
        self.assertEqual(cloud_continuation.task_profile(self.project, "experiment-execution")["science_risk"], "critical")
        with self.assertRaises(cloud_continuation.ContinuationError):
            cloud_continuation.set_task_profile(self.project, "writing-and-review", ROUTINE,
                actor="Fixture Owner", run_id="wrong-stage", expected_profile_sha256=updated["profile_sha256"])
        self.assertEqual(state.read_bytes(), original)

    def test_set_profile_cloud_request_is_nonpaid_strict_and_stage_bound(self):
        job = request("set_routing_profile", stage="experiment-execution", task_profile=ROUTINE)
        self.assertEqual(cloud_job.validate_request(job), job)
        for changes in ({"allow_paid": True}, {"task_profile": None}, {"stage": []},
                        {"expected_profile_sha256": "x"}, {"model": "cheapest"}, {"budget_cny": 300}):
            with self.subTest(changes=changes), self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request({**job, **changes})

    def test_nonpaid_management_actions_reject_arbitrary_routes_and_paid_flags(self):
        self.assertEqual(cloud_job.validate_request(request("routing_status"))["allow_paid"], False)
        profile_file = "evidence/routing-profiles/routine.json"
        job = request("accept_route", candidate_id="sol-pro-high", packet_id="routing-pilot",
                      profile_file=profile_file, expected_profile_sha256="a" * 64,
                      stage="experiment-execution", role="persistent-writer")
        self.assertEqual(cloud_job.validate_request(job), job)
        for changes in ({"allow_paid": True}, {"provider": "unapproved"}, {"model": "other"},
                        {"budget_cny": 300}, {"profile_file": "../private.json"},
                        {"profile_file": "state/run.json"}, {"candidate_id": "x;cmd"},
                        {"expected_profile_sha256": "b" * 63}, {"role": "approve"}):
            with self.subTest(changes=changes), self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request({**job, **changes})

    def test_cli_rejects_duplicate_and_transport_override_profiles_before_any_model_call(self):
        for supplied in ('{"task_class":"x","task_class":"y","science_risk":"routine"}',
                         '{"task_class":"x","science_risk":"routine","provider":"arbitrary"}', "null"):
            argv = ["api_orchestrator", "cycle", "demo", "experiment-execution", "--task-profile", supplied]
            with self.subTest(supplied=supplied), patch("sys.argv", argv), \
                    patch.object(api_orchestrator.model_runtime, "call") as post, self.assertRaises(SystemExit):
                api_orchestrator.main()
            post.assert_not_called()


class DynamicCycleProfileTests(unittest.TestCase):
    # Reuse only fixture helpers, not its test class (which would rerun its suite).
    setUp = production_fixture.ProductionCycleTests.setUp
    payloads = production_fixture.ProductionCycleTests.payloads
    transport = production_fixture.ProductionCycleTests.transport
    run_cycle = production_fixture.ProductionCycleTests.run_cycle

    def test_cycle_forwards_one_profile_to_five_roles_and_records_actual_transport(self):
        seen = []
        def fake_call(project, **kwargs):
            seen.append(kwargs)
            result = self.transport(kwargs["provider"], kwargs["prompt"], **{
                key: value for key, value in kwargs.items() if key not in {"provider", "prompt"}})
            # Simulate a selected equivalent route; inspect recorded result rather
            # than copying a static baseline into the run manifest.
            result.endpoint = "https://selected-route.invalid/v1/responses"
            return result
        with patch.object(api_orchestrator.model_runtime, "call", side_effect=fake_call):
            manifest = self.run_cycle(task_profile=ROUTINE)
        self.assertEqual(len(seen), 5)
        self.assertTrue(all(item["task_profile"]["task_class"] == ROUTINE["task_class"] for item in seen))
        self.assertEqual(manifest["declared_task_profile"], ROUTINE)
        self.assertEqual(manifest["actual_routes"]["persistent-writer"]["endpoint"],
                         "https://selected-route.invalid/v1/responses")
        self.assertEqual(set(manifest["actual_routes"]), set(manifest["production_route_baseline"]))
        self.assertEqual(manifest["output_policy"]["persistent_writer_family"], "openai")

    def test_unclassified_late_stage_uses_conservative_scientific_kind_without_extra_roles(self):
        with patch.object(dynamic_routing, "enabled", return_value=True), \
                patch.object(api_orchestrator.model_runtime, "call", side_effect=lambda project, **kwargs:
                    self.transport(kwargs["provider"], kwargs["prompt"], **{
                        key: value for key, value in kwargs.items() if key not in {"provider", "prompt"}})) as post:
            manifest = self.run_cycle(routine=False)
        self.assertEqual(post.call_count, 5)
        self.assertIsNone(manifest["declared_task_kind"])
        self.assertEqual(manifest["task_kind"], "scientific-judgment")
        self.assertEqual(manifest["actual_routes"]["persistent-writer"]["model"], "gpt-6-astra")
        self.assertEqual(manifest["actual_routes"]["semantic-planner"]["model"], "claude-opus-5-5")
        self.assertEqual(manifest["task_profile"]["science_risk"], "critical")

    def test_explicit_core_kind_cannot_be_downgraded_by_a_routine_profile(self):
        with patch.object(api_orchestrator.model_runtime, "call", side_effect=lambda project, **kwargs:
                self.transport(kwargs["provider"], kwargs["prompt"], **{
                    key: value for key, value in kwargs.items() if key not in {"provider", "prompt"}})) as post:
            manifest = self.run_cycle(task_kind="core-story", task_profile=ROUTINE)
        self.assertEqual(post.call_count, 5)
        self.assertTrue(all(call.kwargs["task_profile"]["science_risk"] == "critical"
                            for call in post.call_args_list))
        self.assertEqual(manifest["actual_routes"]["persistent-writer"]["model"], "gpt-6-astra")
        self.assertEqual(manifest["declared_task_profile"]["science_risk"], "routine")


class DynamicRoutingManagementTests(unittest.TestCase):
    setUp = production_jobs.ProductionCloudJobTests.setUp
    mocked_job = production_jobs.ProductionCloudJobTests.mocked_job

    def test_owner_routing_status_and_acceptance_use_nonpaid_single_entry_points(self):
        actions = [production_jobs.request("routing_status"), production_jobs.request("accept_route",
            candidate_id="sol-pro-high", packet_id="routing-pilot", stage="experiment-execution",
            role="persistent-writer", profile_file="evidence/routing-profiles/routine.json",
            expected_profile_sha256="a" * 64)]
        for index, job in enumerate(actions):
            self.worktree.mkdir(exist_ok=True)
            with self.subTest(action=job["action"]), self.mocked_job() as mocks:
                self.assertEqual(cloud_job.issue_request(production_jobs.issue(job)), job)
                self.assertEqual(cloud_job.run_job(job, str(510 + index)), 0)
                mocks.execute.assert_called_once()
                command = mocks.execute.call_args.args[0]
                self.assertEqual(command[:2], ["scripts/dynamic_routing.py",
                    "status" if job["action"] == "routing_status" else "accept"])
                self.assertNotIn("--execute", command)
                self.assertNotIn("--allow-paid", command)
                if job["action"] == "accept_route":
                    self.assertEqual(command[command.index("--candidate-id") + 1], job["candidate_id"])
                    self.assertEqual(command[command.index("--expected-profile-sha256") + 1], "a" * 64)
                mocks.grant.assert_not_called()
                mocks.read.assert_not_called()

    def test_non_owner_cannot_enable_even_an_existing_routing_candidate(self):
        event = production_jobs.issue(production_jobs.request("routing_status"))
        event["issue"]["user"]["id"] = 42
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(event)

    def test_owner_set_profile_writes_control_state_without_command_budget_or_model_calls(self):
        job = production_jobs.request("set_routing_profile", stage="experiment-design", task_profile=ROUTINE)
        before = (self.project / "state/run.json").read_bytes()
        with self.mocked_job() as mocks:
            self.assertEqual(cloud_job.run_job(job, "520"), 0)
            mocks.execute.assert_not_called()
            mocks.grant.assert_not_called()
            mocks.read.assert_not_called()
        self.assertEqual((self.project / "state/run.json").read_bytes(), before)
        self.assertEqual(cloud_continuation.task_profile(self.project, "experiment-design")["task_class"],
                         ROUTINE["task_class"])
        receipt = json.loads((self.runtime / "cloud-artifact/routing-profile-receipt.json").read_text())
        self.assertEqual(receipt["run_id"], "520")
        self.assertFalse(receipt["scientific_gate_approved"])


if __name__ == "__main__":
    unittest.main()
