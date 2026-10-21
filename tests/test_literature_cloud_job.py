"""Owner-job tests use fakes only; no git, data acquisition or model execution."""
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import cloud_job, literaturectl


def request(**extra):
    return {"schema_version": "1.0", "action": "literature", "project": "my-phd", "actor": "Researcher",
            "allow_paid": False, "request_file": "program/literature-request.json", **extra}


def issue(value, *, owner=cloud_job.OWNER_ID):
    return {"action": "opened", "repository": {"full_name": cloud_job.REPOSITORY, "owner": {"id": cloud_job.OWNER_ID}},
            "issue": {"user": {"id": owner}, "title": "[research-cloud] literature",
                      "body": cloud_job.MARKER + "\n\n```json\n" + json.dumps(value) + "\n```"}}


class LiteratureCloudJobTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "projects/my-phd"
        (self.project / "state").mkdir(parents=True)
        (self.project / "program").mkdir()
        (self.project / "state/run.json").write_text(json.dumps({"stage": "topic-intelligence", "gate": "G1", "status": "in_progress"}))
        self.operation = self.project / "program/literature-request.json"
        self.operation.write_text(json.dumps({"action": "literature_workbench"}))
        self.worktree = self.root / "state-worktree"
        self.worktree.mkdir()
        self.runtime = self.root / ".runtime"

    @contextmanager
    def mocked_job(self, *, failure=None):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": "", "DR_OS_CLOUD_EXECUTOR": "1"}))
            for name, value in (("ROOT", self.root), ("RUNTIME", self.runtime), ("ARTIFACT", self.runtime / "cloud-artifact")):
                stack.enter_context(patch.object(cloud_job, name, value))
            restore = stack.enter_context(patch.object(cloud_job, "restore_state", return_value=(self.worktree, "cloud-state/my-phd")))
            persist = stack.enter_context(patch.object(cloud_job, "persist_state", return_value=["program/topic-leads.json"]))
            checkpoint = stack.enter_context(patch.object(cloud_job.cloud_checkpoint, "prepare"))
            stack.enter_context(patch.object(cloud_job.cloud_continuation, "checkpoint"))
            stack.enter_context(patch.object(cloud_job, "selected_files", return_value=[]))
            stack.enter_context(patch.object(cloud_job, "git", return_value=SimpleNamespace(stdout="a" * 40, returncode=0)))
            acquire = stack.enter_context(patch("scripts.cloud_research_steps.acquire_data"))
            execute = stack.enter_context(patch.object(literaturectl, "execute_operation", return_value={"status": "needs_review"}, side_effect=failure))
            commands = stack.enter_context(patch.object(cloud_job, "run_command"))
            read_budget = stack.enter_context(patch.object(cloud_job.model_spend, "read"))
            grant = stack.enter_context(patch.object(cloud_job.model_spend, "grant"))
            yield SimpleNamespace(restore=restore, persist=persist, checkpoint=checkpoint, acquire=acquire, execute=execute,
                                  commands=commands, read_budget=read_budget, grant=grant)

    def test_owner_issue_requires_nonpaid_flag_and_program_json_path(self):
        self.assertEqual(cloud_job.issue_request(issue(request())), request())
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(issue(request(), owner=42))
        for change in ({"allow_paid": True}, {"allow_paid": 0}, {"request_file": "../request.json"},
                       {"request_file": "state/request.json"}, {"request_file": "program/request.txt"},
                       {"request_file": "program/../request.json"}, {"request_file": "C:/program/request.json"},
                       {"request_file": "program/request.json", "execute": True}):
            with self.subTest(change=change), self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request(request(**change))
        missing = request()
        missing.pop("request_file")
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.validate_request(missing)

    def test_operation_is_one_strict_action_and_cannot_enable_paid_analysis(self):
        invalid = [[{"action": "literature_workbench"}], {"operations": [{"action": "literature_workbench"}]},
                   {"action": "authorize_budget", "new_ceiling_cny": 300},
                   {"action": "literature_analyze", "paper_id": "paper-one", "execute": True},
                   {"action": "literature_analyze", "paper_id": "paper-one", "execute": 1},
                   {"action": "literature_analyze", "paper_id": "paper-one", "execute": "true"},
                   {"action": "literature_search"}, {"action": "literature_workbench", "shell": "unapproved"}]
        for value in invalid:
            self.operation.write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(cloud_job.CloudJobError):
                cloud_job.literature_operation(self.project, "program/literature-request.json")
        self.operation.write_text('{"action":"literature_workbench","action":"literature_analyze"}')
        with self.assertRaisesRegex(cloud_job.CloudJobError, "duplicate"):
            cloud_job.literature_operation(self.project, "program/literature-request.json")
        self.operation.write_text('{"action":"literature_analyze","paper_id":"one","max_output_tokens":NaN}')
        with self.assertRaisesRegex(cloud_job.CloudJobError, "nonfinite"):
            cloud_job.literature_operation(self.project, "program/literature-request.json")

    def test_prepared_analysis_and_all_controlled_nonpaid_operations_are_available(self):
        values = [{"action": "literature_discover"}, {"action": "literature_resolve", "url": "https://arxiv.org/abs/2501.00001"},
                  {"action": "literature_figures", "pdf": "literature/paper.pdf", "manifest": "data/manifests/paper.json"},
                  {"action": "literature_figures", "pdf": "literature/paper.pdf", "manifest": "data/manifests/paper.json",
                   "source_receipt": {"path": "literature/sources/receipt.json", "sha256": "a" * 64}},
                  {"action": "literature_register", "candidate_id": "doi:10.1000/one", "expected_leads_sha256": "a" * 64},
                  {"action": "literature_analyze", "paper_id": "one", "execute": False},
                  {"action": "literature_workbench"}, {"action": "literature_search", "query": "robustness"},
                  {"action": "literature_itinerary", "question": "What differs across the sources?"},
                  {"action": "literature_compare", "paper_ids": ["one", "two"]}]
        for value in values:
            self.operation.write_text(json.dumps(value))
            operation, binding = cloud_job.literature_operation(self.project, "program/literature-request.json")
            self.assertEqual(operation, value)
            self.assertEqual(len(binding["sha256"]), 64)

    def test_symlinked_or_oversized_operation_files_do_not_reach_execution(self):
        self.operation.write_text(" " * 64001)
        with self.assertRaisesRegex(cloud_job.CloudJobError, "64 KB"):
            cloud_job.literature_operation(self.project, "program/literature-request.json")
        target = self.project / "program/actual.json"
        target.write_text('{"action":"literature_workbench"}')
        self.operation.unlink()
        try:
            self.operation.symlink_to(target)
        except (OSError, NotImplementedError):
            return
        with self.assertRaisesRegex(cloud_job.CloudJobError, "symlink"):
            cloud_job.literature_operation(self.project, "program/literature-request.json")

    def test_job_restores_acquires_executes_and_checkpoints_without_budget_or_model_route(self):
        with self.mocked_job() as mocks:
            self.assertEqual(cloud_job.run_job(request(), "501"), 0)
            mocks.restore.assert_called_once_with("my-phd")
            mocks.acquire.assert_called_once_with(self.project)
            mocks.execute.assert_called_once_with(self.project, {"action": "literature_workbench"})
            mocks.checkpoint.assert_called_once()
            mocks.persist.assert_called_once()
            mocks.commands.assert_not_called()
            mocks.read_budget.assert_not_called()
            mocks.grant.assert_not_called()
        receipt = json.loads((self.runtime / "cloud-artifact/literature-result.json").read_text())
        self.assertFalse(receipt["gate_approved"])
        self.assertEqual(receipt["paid_model_calls"], 0)
        self.assertEqual(receipt["request"]["path"], "program/literature-request.json")
        failure = json.loads((self.runtime / "cloud-artifact/failure.json").read_text())
        self.assertTrue(failure["checkpoint_persisted"])
        self.assertTrue(failure["execution_started"])
        self.assertIn("one nonpaid literature operation", (self.runtime / "cloud-summary.md").read_text())

    def test_disallowed_paid_operation_never_reaches_execute_and_failed_results_are_preserved(self):
        self.operation.write_text(json.dumps({"action": "literature_analyze", "paper_id": "one", "execute": True}))
        with self.mocked_job() as mocks:
            self.assertEqual(cloud_job.run_job(request(), "502"), 1)
            mocks.execute.assert_not_called()
            mocks.persist.assert_called_once()
            mocks.commands.assert_not_called()
        self.worktree.mkdir(exist_ok=True)
        self.operation.write_text(json.dumps({"action": "literature_workbench"}))
        with self.mocked_job(failure=ValueError("source changed")) as mocks:
            self.assertEqual(cloud_job.run_job(request(), "503"), 1)
            mocks.execute.assert_called_once()
            mocks.persist.assert_called_once()
            mocks.grant.assert_not_called()
        failure = json.loads((self.runtime / "cloud-artifact/failure.json").read_text())
        self.assertTrue(failure["checkpoint_persisted"])
        self.assertIn("source changed", failure["diagnostic"])


if __name__ == "__main__":
    unittest.main()
