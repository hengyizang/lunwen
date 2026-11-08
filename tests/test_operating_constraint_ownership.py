"""Owner-approved operating constraints cannot be changed by authoring models."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator, artifact_ownership


class OperatingConstraintOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "projects" / "my-phd"
        self.intake = self.project / "intake/constraints.json"
        self.intake.parent.mkdir(parents=True)
        self.original = b'{"model_api_budget_cny":300,"target_submission_ready_date":"2026-10-07"}\n'
        self.intake.write_bytes(self.original)
        (self.project / "state").mkdir()
        self.api_root = patch.object(api_orchestrator, "ROOT", self.root)
        self.api_root.start()
        self.addCleanup(self.api_root.stop)
        self.set_approval(False)

    def set_approval(self, approved):
        (self.project / "state/run.json").write_text(json.dumps({
            "stage": "topic-intelligence" if approved else "intake",
            "gate": "G1" if approved else "G0", "status": "awaiting_work",
            "approved_gates": ["G0"] if approved else [],
            "approvals": [{"gate": "G0", "actor": "Owner"}] if approved else [],
        }), encoding="utf-8")

    def test_unapproved_g0_intake_remains_draftable_by_shared_api(self):
        self.assertFalse(artifact_ownership.executor_owned(self.project, "intake/constraints.json"))
        self.assertEqual(api_orchestrator.safe_target("my-phd", "intake/constraints.json"), self.intake)
        api_orchestrator.apply_bundle("my-phd", {"stage": "intake", "artifacts": [
            {"path": "intake/constraints.json", "content": '{"status":"draft"}'}]}, "intake")
        self.assertEqual(self.intake.read_text(), '{"status":"draft"}')

    def test_approved_g0_rejects_api_constraints_write(self):
        self.set_approval(True)
        self.assertTrue(artifact_ownership.executor_owned(self.project, "intake/constraints.json"))
        with self.assertRaisesRegex(ValueError, "Executor-owned"):
            api_orchestrator.safe_target("my-phd", "intake/constraints.json")

    def test_existing_state_protection_covers_amendment_receipts(self):
        receipt = self.project / "state/operating-constraints-amendments/amendment.json"
        receipt.parent.mkdir()
        receipt.write_text('{"source_run_id":"123"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Protected state"):
            api_orchestrator.safe_target("my-phd", receipt.relative_to(self.project).as_posix())
        self.assertEqual(receipt.read_text(), '{"source_run_id":"123"}')
