"""Fake-only integration coverage for production cloud owner job boundaries."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import cloud_job, model_spend


def request(action="auxiliary", **extra):
    return {"schema_version":"1.0","action":action,"project":"my-phd","actor":"Hengyi",
            "allow_paid":action in cloud_job.PAID,**extra}


def issue(value):
    return {"action":"opened","repository":{"full_name":cloud_job.REPOSITORY,
        "owner":{"id":cloud_job.OWNER_ID}},"issue":{"user":{"id":cloud_job.OWNER_ID},
        "title":"[research-cloud] production auxiliary task", "body":cloud_job.MARKER+
        "\n\n```json\n"+json.dumps(value)+"\n```"}}


class ProductionCloudJobTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.project=self.root/"projects"/"my-phd"
        (self.project/"state").mkdir(parents=True)
        self.state={"stage":"experiment-design","gate":"G3","status":"in_progress","active_paper":"P01"}
        (self.project/"state"/"run.json").write_text(json.dumps(self.state))
        self.worktree=self.root/"state-worktree";self.worktree.mkdir()
        self.runtime=self.root/".runtime"
        self.control={"authorized_ceiling_cny":300,"spent_cny":7.0,"reservations":{}}

    @contextmanager
    def mocked_job(self, *, control=None, budget_error=None, exit_code=0):
        """No git, checkpoint, model, subprocess or network operation escapes."""
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,{"DR_OS_ROUTING_PROFILE":"production","GITHUB_STEP_SUMMARY":""}))
            for name,value in (("ROOT",self.root),("RUNTIME",self.runtime),("ARTIFACT",self.runtime/"cloud-artifact")):
                stack.enter_context(patch.object(cloud_job,name,value))
            stack.enter_context(patch.object(cloud_job,"restore_state",return_value=(self.worktree,"cloud-state/my-phd")))
            stack.enter_context(patch.object(cloud_job,"persist_state",return_value=[]))
            stack.enter_context(patch.object(cloud_job,"selected_files",return_value=[]))
            stack.enter_context(patch.object(cloud_job,"git",return_value=SimpleNamespace(stdout="a"*40,returncode=0)))
            stack.enter_context(patch.object(cloud_job.cloud_checkpoint,"prepare"))
            stack.enter_context(patch.object(cloud_job.cloud_continuation,"checkpoint"))
            reader=stack.enter_context(patch.object(cloud_job.model_spend,"read",
                return_value=self.control if control is None else control,side_effect=budget_error))
            grant=stack.enter_context(patch.object(cloud_job.model_spend,"grant"))
            execute=stack.enter_context(patch.object(cloud_job,"run_command",return_value=(exit_code,"mocked repository entry point")))
            yield SimpleNamespace(read=reader,grant=grant,execute=execute)

    def test_auxiliary_owner_request_manifest_and_paid_flag_are_strict(self):
        valid=request(manifest="evidence/auxiliary-jobs/metadata.json")
        self.assertEqual(cloud_job.issue_request(issue(valid)),valid)
        for changes in ({"allow_paid":False},{"allow_paid":1},{"manifest":"../private.json"},
                        {"manifest":"/tmp/private.json"},{"manifest":"C:/private.json"},
                        {"manifest":"evidence/auxiliary-jobs/../private.json"},
                        {"manifest":"state/request.json"},{"manifest":"evidence/auxiliary-jobs/request.txt"},
                        {"manifest":"evidence/auxiliary-jobs/request.json","provider":"unapproved"},
                        {"manifest":"evidence/auxiliary-jobs/request.json","budget_cny":300}):
            with self.subTest(changes=changes),self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request({**valid,**changes})
        missing=dict(valid);missing.pop("manifest")
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.validate_request(missing)

    def test_auxiliary_start_requires_real_owner_opened_issue_in_exact_repository(self):
        value=request(manifest="evidence/auxiliary-jobs/check.json")
        for mutation in ("other-author","other-repo-owner","other-repository","edited","pull-request","bad-title"):
            event=issue(value)
            if mutation=="other-author":event["issue"]["user"]["id"]=42
            elif mutation=="other-repo-owner":event["repository"]["owner"]["id"]=42
            elif mutation=="other-repository":event["repository"]["full_name"]="someone/lunwen"
            elif mutation=="edited":event["action"]="edited"
            elif mutation=="pull-request":event["issue"]["pull_request"]={}
            else:event["issue"]["title"]="please run"
            with self.subTest(mutation=mutation),self.assertRaises(cloud_job.CloudJobError):
                cloud_job.issue_request(event)

    def test_auxiliary_existing_budget_invokes_one_bounded_entry_point_without_grant(self):
        job=request(manifest="evidence/auxiliary-jobs/check.json")
        with self.mocked_job() as mocks:
            self.assertEqual(cloud_job.run_job(job,"401"),0)
            mocks.execute.assert_called_once_with(["scripts/auxiliary_job.py","--project","my-phd",
                "--manifest",job["manifest"],"--output","evidence/auxiliary/401.json","--execute"])
            mocks.read.assert_called_once_with(self.project,required=True)
            mocks.grant.assert_not_called()
            self.assertEqual(os.environ["DR_OS_REQUIRE_MODEL_AUTH"],"1")
            self.assertEqual(os.environ["DR_OS_REQUIRE_REMOTE_RESERVATION"],"1")
        failure=json.loads((self.runtime/"cloud-artifact"/"failure.json").read_text())
        self.assertTrue(failure["execution_started"])
        self.assertTrue(failure["checkpoint_persisted"])

    def test_auxiliary_unknown_cost_or_no_budget_stops_without_transport_or_grant(self):
        job=request(manifest="evidence/auxiliary-jobs/check.json")
        conditions=[({"authorized_ceiling_cny":0,"reservations":{}},None),
                    ({"authorized_ceiling_cny":300,"reservations":{"pending":{"max_cost_cny":1}}},None),
                    (None,model_spend.SpendControlError("missing or unknown billing control"))]
        for index,(control,error) in enumerate(conditions):
            with self.subTest(index=index),self.mocked_job(control=control,budget_error=error) as mocks:
                self.assertEqual(cloud_job.run_job(job,str(410+index)),1)
                mocks.execute.assert_not_called();mocks.grant.assert_not_called()
            # run_job removes its restored worktree after each mocked attempt.
            self.worktree.mkdir(exist_ok=True)

    def test_failed_paid_auxiliary_entry_is_not_retried_or_replaced(self):
        job=request(manifest="evidence/auxiliary-jobs/check.json")
        with self.mocked_job(exit_code=1) as mocks:
            self.assertEqual(cloud_job.run_job(job,"419"),1)
            mocks.execute.assert_called_once()
            mocks.grant.assert_not_called()
        failure=json.loads((self.runtime/"cloud-artifact"/"failure.json").read_text())
        self.assertEqual(failure["status"],"failed")
        self.assertTrue(failure["execution_started"])
        self.assertEqual(failure["phase"],"execution")

    def test_paperqa_uses_native_source_bound_route_with_existing_budget(self):
        reader=self.project/"evidence"/"readers"/"pilot.txt"
        reader.parent.mkdir(parents=True);reader.write_text("The sample included 120 adults.")
        job=request("paperqa",corpus="evidence/readers",question="How many adults?",settings="high")
        with self.mocked_job() as mocks:
            self.assertEqual(cloud_job.run_job(job,"420"),0)
            mocks.execute.assert_called_once()
            command=mocks.execute.call_args.args[0]
            self.assertEqual(command[0],"scripts/paper_qa.py")
            self.assertIn("--execute",command)
            self.assertEqual(command[command.index("--source")+1],"evidence/readers/pilot.txt")
            self.assertEqual(command[command.index("--question-file")+1],"evidence/qa/420-question.txt")
            self.assertEqual((self.project/"evidence/qa/420-question.txt").read_text(),job["question"])
            mocks.grant.assert_not_called()
            self.assertNotIn("pqa",command)

    def test_paperqa_zero_budget_pending_reservation_and_private_sources_block_execution(self):
        reader=self.project/"evidence"/"readers"/"pilot.txt"
        reader.parent.mkdir(parents=True);reader.write_text("The sample included adults.")
        for index,control in enumerate(({"authorized_ceiling_cny":0,"reservations":{}},
                {"authorized_ceiling_cny":300,"reservations":{"unsettled":{}}})):
            with self.subTest(control=control),self.mocked_job(control=control) as mocks:
                self.assertEqual(cloud_job.run_job(request("paperqa",corpus="evidence/readers",question="adults?"),str(430+index)),1)
                mocks.execute.assert_not_called();mocks.grant.assert_not_called()
            self.worktree.mkdir(exist_ok=True)
        private=self.project/"private";private.mkdir();(private/"notes.txt").write_text("private account material")
        with self.mocked_job() as mocks:
            self.assertEqual(cloud_job.run_job(request("paperqa",corpus="private",question="material?"),"432"),1)
            mocks.execute.assert_not_called();mocks.grant.assert_not_called()

    def test_paperqa_legacy_profile_stays_paused_and_corpus_symlinks_rejected(self):
        reader=self.project/"evidence"/"pilot.txt";reader.parent.mkdir();reader.write_text("Adults.")
        with self.mocked_job() as mocks,patch.dict(os.environ,{"DR_OS_ROUTING_PROFILE":"legacy"}):
            self.assertEqual(cloud_job.run_job(request("paperqa",corpus="evidence/pilot.txt",question="Adults?"),"440"),1)
            mocks.execute.assert_not_called();mocks.grant.assert_not_called()
        self.worktree.mkdir(exist_ok=True)
        alias=self.project/"evidence"/"alias.txt"
        try:alias.symlink_to(reader)
        except (OSError,NotImplementedError):return
        with self.mocked_job() as mocks:
            self.assertEqual(cloud_job.run_job(request("paperqa",corpus="evidence/alias.txt",question="Adults?"),"441"),1)
            mocks.execute.assert_not_called()

    def test_cycle_passes_explicit_critical_task_and_production_provider_groups(self):
        from scripts import cloud_progress, model_routing
        job=request("cycle",stage="experiment-design",task_kind="critical-experiment-design")
        with patch.object(model_routing,"load_policy",return_value=({"critical_tasks":["critical-experiment-design"]},"fake")):
            self.assertEqual(cloud_job.validate_request(job),job)
            for bad in ("make-cheaper",None,[],42):
                with self.subTest(bad=bad),self.assertRaises(cloud_job.CloudJobError):
                    cloud_job.validate_request({**job,"task_kind":bad})
        with patch.dict(os.environ,{"DR_OS_ROUTING_PROFILE":"production"}), \
             patch.object(cloud_job,"ROOT",self.root),patch.object(cloud_progress,"pause_reason",return_value=None), \
             patch.object(cloud_job.model_spend,"read",return_value=self.control), \
             patch.object(cloud_job.cloud_continuation,"configuration_errors",return_value=[]), \
             patch.object(cloud_job.researchctl,"load_state",return_value=self.state), \
             patch.object(cloud_job.model_spend,"grant") as grant:
            command=cloud_job.cycle_command(job,"my-phd")
        self.assertEqual(command[-2:],["--task-kind","critical-experiment-design"])
        self.assertEqual(command[command.index("--writer-provider")+1],"cheapai-gpt-pro")
        self.assertEqual(command[command.index("--critic-provider")+1],"codekey-kiro-enterprise")
        self.assertFalse(any("uuapi" in value for value in command))
        grant.assert_not_called()


if __name__=="__main__":
    unittest.main()
