"""Regression tests of cloud owner authority and real deterministic validators."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_checkpoint as cp, cloud_human_acceptance as acceptance
from scripts import cloud_human_controls as controls, cloud_job, researchctl, research_quality as quality
from scripts import literature_evidence, source_scope


class CloudHumanControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root_patch = patch.object(researchctl, "PROJECTS_ROOT", self.root / "projects")
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.project = acceptance.fixture(researchctl.PROJECTS_ROOT)

    def request(self, action, **fields):
        return cloud_job.validate_request(acceptance.request(action, **fields))

    def decide(self, operation, **selectors):
        return acceptance.decide(operation, selectors=selectors)

    def prepare_quality(self):
        acceptance.set_fixture_stage(self.project, "G3")
        acceptance.quality_fixture(self.project)

    def freeze(self):
        self.prepare_quality()
        self.decide("confirm_data_quality", dataset_id="d1")
        self.decide("freeze_preregistration", paper_id="all")

    def test_review_is_read_only_and_checkpoint_refresh_keeps_digest(self):
        before = cp.inventory(self.project)
        first = acceptance.review("ready", gate="G0")
        self.assertTrue(first["ready_for_operation"])
        self.assertEqual(cp.inventory(self.project), before)
        cp.prepare(self.project, self.root / "checkpoint", "10")
        second = acceptance.review("ready", gate="G0")
        self.assertEqual(first["review_sha256"], second["review_sha256"])
        self.assertEqual(researchctl.load_state(self.project.name)["approved_gates"], [])

    def test_real_gate_sequence_and_stale_decision_rejection(self):
        old = acceptance.review("ready", gate="G0")
        job = self.request("ready", gate="G0", expected_sha256=old["review_sha256"],
                           note="I reviewed the exact synthetic intake.")
        controls.execute(job, "11")
        with self.assertRaisesRegex(controls.HumanControlError, "changed"):
            controls.execute(job, "12")
        approved = self.decide("approve", gate="G0")
        self.assertEqual(approved["state_after"]["status"], "approved")
        advance = acceptance.review("advance", gate="G0")
        constraints = self.project / "intake/constraints.json"
        constraints.write_text(constraints.read_text() + "\n", encoding="utf-8")
        with self.assertRaisesRegex(controls.HumanControlError, "changed"):
            controls.execute(self.request("advance", gate="G0", expected_sha256=advance["review_sha256"],
                                          note="I reviewed this approved gate snapshot."), "13")
        self.assertTrue(acceptance.review("advance", gate="G0")["blockers"])
        self.decide("ready", gate="G0")
        self.decide("approve", gate="G0")
        self.decide("advance", gate="G0")
        self.assertEqual(researchctl.load_state(self.project.name)["gate"], "G1")
        self.assertTrue(acceptance.review("ready", gate="G1")["blockers"])

    def test_reopen_records_revision_without_granting_a_gate(self):
        self.decide("ready", gate="G0")
        self.decide("reopen", gate="G0")
        state = researchctl.load_state(self.project.name)
        self.assertEqual(state["status"], "awaiting_work")
        self.assertNotIn("ready_artifact_sha256", state)
        self.assertEqual(state["approved_gates"], [])

    def test_missing_evidence_and_wrong_reviewer_cannot_be_confirmed(self):
        self.prepare_quality()
        snapshot = acceptance.review("confirm_data_quality", dataset_id="d1")
        job = self.request("confirm_data_quality", dataset_id="d1", expected_sha256=snapshot["review_sha256"],
                           actor="Another named reviewer", note="I reviewed the synthetic quality report.")
        with self.assertRaisesRegex(controls.HumanControlError, "changed"):
            controls.execute(job, "14")
        data = self.project / "data/raw/dataset.csv"
        data.write_text("machine,split,label,value\nA,train,ok,99\n", encoding="utf-8")
        job["actor"] = acceptance.request("status")["actor"]
        with self.assertRaisesRegex(controls.HumanControlError, "invalid"):
            controls.execute(job, "15")
        self.assertFalse((self.project / "data/quality/d1-confirmation.json").exists())

    def test_quality_confirmation_and_freeze_do_not_approve_g3(self):
        self.freeze()
        confirmation = researchctl.read_json(self.project / "data/quality/d1-confirmation.json")
        prereg = researchctl.read_json(self.project / "papers/P01/preregistration.json")
        self.assertEqual(quality.validate_data_quality_confirmation(confirmation, "d1", self.project), [])
        self.assertEqual(quality.validate_preregistration(prereg, "P01", self.project), [])
        self.assertEqual(researchctl.load_state(self.project.name)["approved_gates"], [])
        self.assertFalse(acceptance.review("ready", gate="G3")["ready_for_operation"])
        self.assertEqual(prereg["source_run_id"], "1")

    def test_all_paper_freeze_checks_every_paper_before_writing(self):
        self.prepare_quality()
        self.decide("confirm_data_quality", dataset_id="d1")
        state = researchctl.load_state(self.project.name)
        state["paper_count"] = 2
        researchctl.save_state(self.project.name, state)
        (self.project / "papers/P02").mkdir()
        snapshot = acceptance.review("freeze_preregistration", paper_id="all")
        self.assertTrue(snapshot["blockers"])
        with self.assertRaises(controls.HumanControlError):
            controls.execute(self.request("freeze_preregistration", paper_id="all",
                             expected_sha256=snapshot["review_sha256"], note="Review all synthetic preregistration inputs."), "16")
        self.assertFalse((self.project / "papers/P01/preregistration.json").exists())

    def test_freeze_after_any_experiment_attempt_is_rejected(self):
        self.prepare_quality()
        self.decide("confirm_data_quality", dataset_id="d1")
        (self.project / "experiments/registry.jsonl").write_text(
            '{"run_id":"failed-fixture","status":"failed"}\n', encoding="utf-8")
        result = acceptance.review("freeze_preregistration", paper_id="all")
        self.assertIn("after experiment attempts", result["blockers"][0])
        self.assertFalse((self.project / "papers/P01/preregistration.json").exists())

    def test_reproduction_confirmation_uses_original_checks_and_rejects_stale_outputs(self):
        self.freeze()
        acceptance.set_fixture_stage(self.project, "G4")
        acceptance.reproduction_fixture(self.project)
        self.decide("confirm_reproduction", paper_id="P01")
        path = self.project / "papers/P01/reproduction-confirmation.json"
        self.assertEqual(quality.validate_reproduction_confirmation(researchctl.read_json(path), "P01", self.project), [])
        old = acceptance.review("confirm_reproduction", paper_id="P01")
        (self.project / "experiments/metrics.json").write_text('{"metric": 99}', encoding="utf-8")
        with self.assertRaisesRegex(controls.HumanControlError, "changed"):
            controls.execute(self.request("confirm_reproduction", paper_id="P01", expected_sha256=old["review_sha256"],
                                         note="Review the synthetic reproduction reports."), "17")
        self.assertTrue(acceptance.review("confirm_reproduction", paper_id="P01")["blockers"])

    def test_named_literature_screening_is_bound_to_provider_receipts(self):
        acceptance.set_fixture_stage(self.project, "G1")
        payload = json.dumps({"results": [{"id": "https://openalex.org/W1",
                             "display_name": "Synthetic software test work", "doi": "https://doi.org/10.1000/example"}]}).encode()
        receipt = literature_evidence.execute_search(
            self.project, "openalex", "synthetic fixture", query_family="test", date_range="all", filters="none", limit=1,
            fetcher=lambda url, **kwargs: (payload, url, 200, "application/json"))
        decisions = {"included_work_ids": ["doi:10.1000/example"], "exclusion_reasons": ["Other records are outside the fixture scope."]}
        acceptance.decide("screen_literature", selectors={"receipt_id": receipt["receipt_id"]}, **decisions)
        records = literature_evidence.read_jsonl(self.project / "evidence/search-log.jsonl")
        self.assertEqual(literature_evidence.validate_search_evidence(self.project, records), [])
        self.assertEqual(records[0]["screened_by"], acceptance.request("status")["actor"])
        (self.project / receipt["raw_response_path"]).write_text("changed", encoding="utf-8")
        self.assertTrue(acceptance.review("screen_literature", receipt_id=receipt["receipt_id"])["blockers"])

    def test_supplied_source_scope_does_not_claim_scientific_reading(self):
        acceptance.set_fixture_stage(self.project, "G1")
        path = self.project / "evidence/supplied-abstract.txt"
        path.write_text("Synthetic abstract fixture only.", encoding="utf-8")
        result = self.decide("confirm_source_scope", source="evidence/supplied-abstract.txt", scope="abstract")
        receipt = self.project / result["outputs"][0]["path"]
        record = researchctl.read_json(receipt)
        self.assertEqual(record["human_read_scope"], "not_declared")
        self.assertFalse(record["semantic_verification"])
        self.assertEqual(source_scope.verify(self.project, record["primary_source"],
                         {"path": receipt.relative_to(self.project).as_posix(), "sha256": cp.sha(receipt)}, "abstract"), [])

    def test_g5_dossier_is_bound_to_the_active_paper(self):
        acceptance.set_fixture_stage(self.project, "G5")
        before = acceptance.review("ready", gate="G5")["review_sha256"]
        state = researchctl.load_state(self.project.name)
        state["active_paper"] = "P02"
        researchctl.save_state(self.project.name, state)
        after = acceptance.review("ready", gate="G5")["review_sha256"]
        self.assertNotEqual(before, after)

    def test_cloud_dispatch_restores_data_and_never_runs_a_paid_command(self):
        runtime = self.root / ".runtime"
        runtime.mkdir()
        with patch.object(cloud_job, "ROOT", self.root), patch.object(cloud_job, "RUNTIME", runtime), \
             patch.object(cloud_job, "ARTIFACT", runtime / "cloud-artifact"), \
             patch.object(cloud_job, "restore_state", return_value=(self.root / "worktree", "cloud-state/human-control-fixture")) as restore, \
             patch.object(cloud_job, "persist_state", return_value=[]) as persist, \
             patch.object(cloud_job, "git"), \
             patch("scripts.cloud_research_steps.acquire_data", return_value={"acquired": [], "blockers": []}) as acquire, \
             patch.object(cloud_job, "run_command", side_effect=AssertionError("no command or provider call allowed")) as command, \
             patch("urllib.request.urlopen", side_effect=AssertionError("no paid network allowed")), \
             patch.dict("os.environ", {}, clear=True):
            before = cp.sha(self.project / "state/model-spend-control.json")
            self.assertEqual(cloud_job.run_job(self.request("review_dossier", operation="ready", gate="G0"), "18"), 0)
            receipt = researchctl.read_json(runtime / "cloud-artifact/human-control-receipt.json")
            self.assertTrue(receipt["ready_for_operation"])
            self.assertEqual(cloud_job.run_job(self.request("ready", gate="G0",
                             expected_sha256=receipt["review_sha256"], note="Review the synthetic cloud intake."), "19"), 0)
            self.assertEqual(researchctl.load_state(self.project.name)["status"], "awaiting_approval")
            self.assertEqual(before, cp.sha(self.project / "state/model-spend-control.json"))
            self.assertEqual(restore.call_count, 2)
            self.assertEqual(acquire.call_count, 2)
            self.assertEqual(persist.call_count, 2)
            command.assert_not_called()

    def test_all_new_requests_still_require_owner_issue_and_nonpaid_flag(self):
        value = acceptance.request("review_dossier", operation="ready", gate="G0")
        fence = chr(96) * 3
        event = {"action": "opened", "repository": {"full_name": cloud_job.REPOSITORY,
                 "owner": {"id": cloud_job.OWNER_ID}}, "issue": {"user": {"id": 42},
                 "title": "[research-cloud] review",
                 "body": cloud_job.MARKER + "\n" + fence + "json\n" + json.dumps(value) + "\n" + fence}}
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(event)
        event["issue"]["user"]["id"] = cloud_job.OWNER_ID
        self.assertEqual(cloud_job.issue_request(event), value)
        for fields in ({"allow_paid": True}, {"paper_id": "P01"}, {"operation": "shell"}, {"gate": "G6"}):
            with self.subTest(fields=fields), self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request({**value, **fields})
        with self.assertRaises(cloud_job.CloudJobError):
            self.request("confirm_data_quality", dataset_id="../outside", expected_sha256="a"*64, note="Review the report.")
        with self.assertRaises(cloud_job.CloudJobError):
            self.request("confirm_source_scope", source="data/raw/private.txt", scope="full_text",
                         expected_sha256="a"*64, note="Review the source.")

    def test_complete_software_acceptance_keeps_actual_project_untouched(self):
        result = acceptance.run(self.root / "acceptance", real_power=False)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["scientific_completion_verified"])
        self.assertEqual(result["paid_provider_calls"], 0)
        self.assertFalse((self.root / "acceptance/projects/my-phd").exists())


if __name__ == "__main__":
    unittest.main()
