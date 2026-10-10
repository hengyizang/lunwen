"""Authenticated non-paid owner decisions against synthetic review materials."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import cloud_human_acceptance as acceptance, cloud_human_controls as controls, cloud_job, researchctl, review_packets
from tests.test_review_packets import fixture, judgments


class ReviewPacketControlTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        root_patch = patch.object(researchctl, "PROJECTS_ROOT", self.root / "projects")
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.project = acceptance.fixture(researchctl.PROJECTS_ROOT)
        fixture(self.project)
        review_packets.refresh(self.project)

    def request(self, action, **fields):
        return cloud_job.validate_request(acceptance.request(action, **fields))

    def dossier(self):
        return controls.execute(self.request("review_dossier", operation="confirm_review_packet", packet_id="calibration-one"), "101")

    def test_exact_dossier_decision_records_ratings_without_approving_gate(self):
        reviewed = self.dossier()
        self.assertTrue(reviewed["ready_for_operation"], reviewed)
        self.assertFalse((self.project / "state/review-packet-confirmations").exists())
        request = self.request("confirm_review_packet", packet_id="calibration-one", judgments=judgments(self.project),
            expected_sha256=reviewed["review_sha256"], note="I reviewed these synthetic blinded materials and entered the named rater observations.")
        receipt = controls.execute(request, "102")
        self.assertEqual(receipt["paid_calls"], 0)
        self.assertEqual(len(receipt["outputs"]), 1)
        self.assertTrue((self.project / receipt["outputs"][0]["path"]).is_file())
        state = researchctl.load_state(self.project.name)
        self.assertEqual(state["approved_gates"], [])
        self.assertEqual(state["status"], "awaiting_work")
        result = review_packets.audit(self.project)
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["calibration_status"], "NOT_CALIBRATED")
        self.assertTrue((self.project / controls.AUDIT).is_file())

    def test_changed_artifact_rejects_old_dossier(self):
        reviewed = self.dossier()
        ratings = judgments(self.project)
        (self.project / "api_runs/private-left.md").write_text("Changed synthetic candidate")
        with self.assertRaisesRegex(controls.HumanControlError, "changed"):
            controls.execute(self.request("confirm_review_packet", packet_id="calibration-one", judgments=ratings,
                expected_sha256=reviewed["review_sha256"], note="Review the original synthetic materials."), "103")
        self.assertFalse((self.project / "state/review-packet-confirmations").exists())

    def test_bad_judgments_or_paid_flag_cannot_record_confirmation(self):
        reviewed = self.dossier()
        with self.assertRaises((ValueError, controls.HumanControlError)):
            controls.execute(self.request("confirm_review_packet", packet_id="calibration-one", judgments={},
                expected_sha256=reviewed["review_sha256"], note="Review these synthetic materials."), "104")
        with self.assertRaises(cloud_job.CloudJobError):
            self.request("confirm_review_packet", packet_id="calibration-one", judgments={}, allow_paid=True,
                expected_sha256=reviewed["review_sha256"], note="Review these synthetic materials.")
        self.assertFalse((self.project / "state/review-packet-confirmations").exists())


if __name__ == "__main__":
    unittest.main()
