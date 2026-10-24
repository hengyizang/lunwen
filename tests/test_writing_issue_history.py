"""Existing issue history cannot be erased by repeated failed refreshes."""
import copy
import unittest

from scripts import research_extensions as extensions
from scripts.research_artifacts import read, write
from tests import test_writing_review_actions as review_fixtures


class WritingIssueHistoryTests(unittest.TestCase):
    def setUp(self):
        fixture = review_fixtures.WritingReviewActionTests("test_legacy_issue_is_explicitly_not_assessed_and_status_is_preserved")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.project = fixture.project
        evidence = {**fixture.material, "locator": "L2", "quote": "The protocol compares the same held-out devices."}
        self.issue = {"id": "writing-C1", "perspective": "contribution", "severity": "major", "status": "open",
            "question": "Which matched result supports this claim?", "required_action": "Supply the matched analysis and source locations.",
            "evidence": [evidence], "writing_action": fixture.action()}
        self.spec = {"schema_version": "1.0", "review_findings": [self.issue]}
        write(self.project/extensions.INPUT, self.spec)
        self.assertFalse(extensions.refresh(self.project)["errors"])

    def test_removed_issue_stays_blocked_after_two_failed_refreshes(self):
        self.spec["review_findings"] = []
        write(self.project/extensions.INPUT, self.spec)
        for _ in range(2):
            result = extensions.refresh(self.project)
            self.assertTrue(result["errors"])
            self.assertEqual(result["retained_review_findings"][0]["id"], "writing-C1")
            self.assertTrue(extensions.gate_errors(self.project))

    def test_removed_action_cannot_be_laundered_into_a_legacy_issue(self):
        del self.issue["writing_action"]
        write(self.project/extensions.INPUT, self.spec)
        for _ in range(2):
            result = extensions.refresh(self.project)
            self.assertTrue(result["errors"])
            self.assertTrue(result["retained_review_findings"])

    def test_missing_material_stays_pending_when_author_says_answered(self):
        self.issue.update(status="answered_pending_review", response_evidence=copy.deepcopy(self.issue["evidence"]))
        write(self.project/extensions.INPUT, self.spec)
        result = extensions.refresh(self.project)
        self.assertFalse(result["errors"])
        self.assertEqual(result["sections"]["review_findings"][0]["writing_action_assessment"]["status"], "pending_materials")
        self.assertTrue(extensions.gate_errors(self.project))


if __name__ == "__main__":
    unittest.main()
