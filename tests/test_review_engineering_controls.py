"""Review regressions: reject unsupported inputs before execution or delivery."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import api_orchestrator, cloud_job, literature_evidence as evidence
from scripts import literature_intelligence as intelligence, researchctl
from scripts import submission_package
from tests.test_cloud_job import issue, request
from tests import test_literature_intelligence as literature_fixture


class ReviewEngineeringControlsTests(unittest.TestCase):
    def test_writer_policy_rejected_before_a_model_call(self):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no model invocation")):
            for provider in ("anthropic", "codekey-gemini", "codekey-deepseek"):
                with self.subTest(provider=provider), self.assertRaisesRegex(ValueError, "OpenAI/Codex"):
                    api_orchestrator.validate_roles("anthropic", provider, "openai")
            api_orchestrator.validate_roles("anthropic", "cheapai-gpt-pro", "anthropic")

    def test_formal_entry_points_require_six_before_creating_a_project(self):
        for count in (0, 1, 4, 7, 20, True):
            with self.subTest(count=count), self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request(request("init", paper_count=count))
        self.assertEqual(cloud_job.validate_request(request("init"))["action"], "init")
        with tempfile.TemporaryDirectory() as directory, patch.object(researchctl, "PROJECTS_ROOT", Path(directory)):
            args = researchctl.parser().parse_args(["init", "--project", "unsupported-count", "--paper-count", "4"])
            with self.assertRaisesRegex(researchctl.ResearchCtlError, "six"):
                args.func(args)
            self.assertFalse((Path(directory) / "unsupported-count").exists())
            with patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}):
                with self.assertRaisesRegex(researchctl.ResearchCtlError, "six"):
                    researchctl.initialize(SimpleNamespace(project="unsupported-count", paper_count=4, venue=None))

    def test_corrupt_failed_receipt_does_not_trigger_another_request(self):
        fixture = literature_fixture.LiteratureIntelligenceTests()
        for stamp in (None, "not-a-date", 123):
            with self.subTest(stamp=stamp), tempfile.TemporaryDirectory() as directory:
                project = fixture.project(Path(directory))
                row = {"receipt_id": "synthetic-failed", "status": "failed", "provider": "semantic-scholar",
                       "request_url": evidence.build_search_url("semantic-scholar", "robust machinery", 10,
                                                               date_range="all years", filters="none")}
                if stamp is not None:
                    row["completed_at"] = stamp
                ledger = project / "evidence/literature-api-ledger.jsonl"
                ledger.parent.mkdir()
                ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
                with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), \
                     patch.object(evidence, "execute_search", side_effect=AssertionError("must not retry")) as transport:
                    result = intelligence.discover(project)
                transport.assert_not_called()
                self.assertIn("invalid completed_at", result["errors"][0]["error"])

    def test_owner_identity_is_bound_to_event_and_not_displayed_actor(self):
        value = request("status", actor="A display name, not the authenticated login")
        event = issue(value)
        event["issue"].update(number=17)
        event["issue"]["user"]["login"] = "authenticated-owner"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text(json.dumps(event), encoding="utf-8")
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_PATH": str(path), "GITHUB_RUN_ID": "901"}):
                proof = cloud_job.authenticated_owner_event(value, "901")
                self.assertEqual(proof["actor_id"], cloud_job.OWNER_ID)
                self.assertEqual(proof["actor_login"], "authenticated-owner")
                self.assertEqual(proof["issue_number"], 17)
                self.assertEqual(len(proof["event_sha256"]), 64)
                with self.assertRaises(cloud_job.CloudJobError):
                    cloud_job.authenticated_owner_event(value, "902")
                with self.assertRaises(cloud_job.CloudJobError):
                    cloud_job.authenticated_owner_event(dict(value, actor="rewritten request"), "901")
                event["issue"]["user"]["id"] = 42
                path.write_text(json.dumps(event), encoding="utf-8")
                with self.assertRaises(cloud_job.CloudJobError):
                    cloud_job.authenticated_owner_event(value, "901")
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(cloud_job.authenticated_owner_event(value, "901"))

    def test_continuation_uses_existing_authority_without_requiring_an_issue_event(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "continuation.json"
            config.write_text(json.dumps(request("continuation")), encoding="utf-8")
            with patch.object(sys, "argv", ["cloud_job", "execute", "--config", str(config), "--run-id", "905"]), \
                 patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch"}), \
                 patch.object(cloud_job, "authenticated_owner_event", side_effect=AssertionError("not a human decision")), \
                 patch.object(cloud_job, "run_job", return_value=0) as execute:
                self.assertEqual(cloud_job.main(), 0)
            self.assertIsNone(execute.call_args.kwargs["owner_authorization"])

    def test_trial_marker_blocks_packaging_even_with_existing_ready_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(researchctl, "PROJECTS_ROOT", Path(directory)):
            project = Path(directory) / "trial-target"
            paper = project / "papers/P01"
            paper.mkdir(parents=True)
            (project / "state").mkdir()
            (project / "state/run.json").write_text(json.dumps({"paper_count": 6,
                "stage_index": 5, "stage": "writing-and-review", "gate": "G5",
                "paper_statuses": {"P01": "submission_ready"}}), encoding="utf-8")
            venue = paper / "venue.json"
            for value in ({"trial_only": True}, {"selection_status": "trial", "trial_only": False}, {"trial_only": "false"}):
                venue.write_text(json.dumps(value), encoding="utf-8")
                self.assertTrue(submission_package.validate_selected_venue(project, "P01"))
                with self.assertRaisesRegex(researchctl.ResearchCtlError, "trial_only"):
                    submission_package.build_package("trial-target", "P01", Path(directory) / "blocked.zip")
                self.assertFalse((Path(directory) / "blocked.zip").exists())
            venue.write_text('{"trial_only":false,"selection_status":"candidate"}', encoding="utf-8")
            self.assertEqual(submission_package.validate_selected_venue(project, "P01"), [])


if __name__ == "__main__":
    unittest.main()
