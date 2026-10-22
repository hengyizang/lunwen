"""CCFA prompt isolation and bounded-context regressions; cloud CI only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import api_orchestrator as api, context_efficiency, evidence_context


class CCFAContextIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "projects/demo"

    def text(self, relative, value):
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")

    def test_generated_reference_packets_never_duplicate_into_default_snapshot(self):
        self.text("reports/ccfa-tasks/old-task/packet.json", "OLD_PREFERRED_VERDICT_FULL_REFERENCE" * 200_000)
        self.text("reports/ccfa-tasks/active.json", {"task": "PREFERRED_VERDICT"})
        self.text("reports/ccfa-science/history/old.json", "OLD_CRITIC_FINDINGS" * 200_000)
        self.text("evidence/contrary.md", "MATERIAL_NEGATIVE_EVIDENCE")
        self.text("state/model-spend-control.json", {"authorized_ceiling_cny": 300})
        self.text("program/core-thesis.json", {"doctoral_question": "One doctoral question"})
        for exclude in (False, True):
            with patch.object(api, "ROOT", self.root):
                snapshot = api.project_snapshot("demo", stage="topic-intelligence", exclude_reviews=exclude)
            self.assertNotIn("PREFERRED_VERDICT", snapshot)
            self.assertNotIn("OLD_CRITIC_FINDINGS", snapshot)
            self.assertIn("MATERIAL_NEGATIVE_EVIDENCE", snapshot)
            self.assertIn("authorized_ceiling_cny", snapshot)
            self.assertIn("One doctoral question", snapshot)

    def test_independent_snapshot_excludes_underscore_review_namespace(self):
        self.text("reports/ccfa-science/internal_review/P01.json", "HISTORICAL_REVIEW_PREFERRED_OUTCOME")
        self.text("reports/ccfa-science/novelty_watch/P01.json", "SOURCE_BOUND_WATCH_LIMITATIONS")
        self.text("reports/ccfa-science/exemplar/P01.json", "ATTRIBUTED_WRITING_MOVES")
        self.text("papers/P01/manuscript/main.tex", "CURRENT_MANUSCRIPT")
        with patch.object(api, "ROOT", self.root):
            independent = api.project_snapshot("demo", stage="writing-and-review", exclude_reviews=True)
            ordinary = api.project_snapshot("demo", stage="writing-and-review", exclude_reviews=False)
        self.assertNotIn("HISTORICAL_REVIEW_PREFERRED_OUTCOME", independent)
        self.assertIn("HISTORICAL_REVIEW_PREFERRED_OUTCOME", ordinary)
        for source in ("SOURCE_BOUND_WATCH_LIMITATIONS", "ATTRIBUTED_WRITING_MOVES", "CURRENT_MANUSCRIPT"):
            self.assertIn(source, independent)

    def test_explicit_context_plan_cannot_restore_task_or_internal_review_history(self):
        for relative in ("reports/ccfa-tasks/id/current.json", "reports/ccfa-tasks/active.json",
                         "reports/ccfa-science/history/old.json", "reports/ccfa-science/internal_review/P01.json"):
            self.text(relative, "PREVIOUS_VERDICT")
            self.text(evidence_context.PLAN, {"schema_version": "1.0", "stages": {"topic-intelligence": {
                "question": "Assess actual current evidence independently", "items": [
                    {"path": relative, "reason": "Attempt to restore excluded review", "stance": "neutral"}]}}})
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "prior review"):
                evidence_context.build(self.project, "topic-intelligence")

    def test_shared_predicate_is_case_insensitive_and_preserves_sibling_scientific_outputs(self):
        for relative in ("REPORTS/CCFA-TASKS/active.json", "reports/ccfa-science/history/old.json"):
            self.assertTrue(context_efficiency.operational_path(relative))
        self.assertFalse(context_efficiency.operational_path("reports/ccfa-science/internal_review/P01.json"))
        self.assertTrue(context_efficiency.operational_path("REPORTS/CCFA-SCIENCE/INTERNAL_REVIEW/P01.json", exclude_reviews=True))
        for relative in ("reports/ccfa-science/lineage/P01.json", "reports/ccfa-science/novelty_watch/P01.json",
                         "reports/ccfa-science/exemplar/P01.json", "evidence/contrary.md", "experiments/registry.jsonl"):
            self.assertFalse(context_efficiency.operational_path(relative, exclude_reviews=True))


if __name__ == "__main__":
    unittest.main()
