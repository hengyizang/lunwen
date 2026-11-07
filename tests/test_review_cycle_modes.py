"""Actual observation and protocol receipts from synthetic read-only callbacks."""
from contextlib import ExitStack
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import research_cycle, review_receipts
from scripts.research_artifacts import read, write
from tests.research_cycle_fixtures import pending_decision


class ReviewCycleModeTests(unittest.TestCase):
    def test_current_scientific_decision_survives_C_only_refresh_after_actual_review(self):
        from tests.test_quality_gate import report
        write(self.project / "state/run.json", {"stage": "topic-intelligence", "gate": "G1", "active_paper": "P01"})
        pending_decision(self.project, "topic-intelligence", "actual")
        quality = report("G1")
        write(self.project / "program/quality-G1.json", quality)
        def refresh_C(*args):
            quality["scores"]["publication_potential"] = 1
            quality["assessments"] = {"publication_potential": {"status": "unresolved"}}
            write(self.project / "program/quality-G1.json", quality)
        result = research_cycle.review_cycle(self.project, "topic-intelligence", "actual", writer_family="openai",
            prompt=lambda: "Inspect current synthetic sources", invoke=self.invoke, remediate=lambda *args: self.fail("No repair"),
            refresh=lambda phase: ({}, {}), writer_notes=[], log=refresh_C)
        self.assertEqual(result["research_decision"]["status"], "independently_observed")
        self.assertEqual(research_cycle.decision_errors(result["research_decision"]), [])
        self.assertEqual(self.calls, ["initial"])

    def test_independent_assessment_errors_prevent_submission_transition(self):
        decision = {"errors": [], "review_errors": ["the latest critic assessed a different cycle"]}
        with patch("scripts.supplemental_experiments.automatic_approval", return_value={}) as approve, patch(
            "scripts.research_phase.enter_submission"
        ) as transition:
            result = research_cycle.after_reviews(self.project, "writing-and-review", "actual", decision, lambda: [])
        transition.assert_not_called()
        approve.assert_not_called()
        self.assertNotIn("writing_phase_transition", result)
        self.assertEqual(research_cycle.decision_errors(decision),
                         ["research decision: the latest critic assessed a different cycle"])

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.project = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        write(self.project / "state/run.json", {"stage":"writing-and-review", "gate":"G5", "active_paper":"P01"})
        write(self.project / "papers/P01/paper-contract.json", {"paper_id":"P01", "writing_phase":"scientific"})
        self.stack.enter_context(patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR":"1"}))
        self.stack.enter_context(patch("scripts.automated_quality.checked_run", return_value=None))
        pending_decision(self.project, "writing-and-review", "actual", "P01")
        self.calls = []

    def invoke(self, phase, request):
        self.calls.append(phase)
        audit = {"verdict":"pass-with-conditions", "fatal_findings":[], "major_findings":[], "minor_findings":[],
                 "missing_evidence":[], "remediation_steps":[], "uncertainty":["Synthetic fixture cannot establish scientific validity."]}
        path = self.project / ("reviews/independent/actual-" + phase + ".json")
        write(path, audit)
        return audit, path, {"provider":"synthetic-anthropic", "family":"anthropic", "requested_model":"synthetic-critic",
            "reported_model":"synthetic-critic", "completion_status":"completed", "cache_hit":False, "request_id":phase}

    def cycle(self, invoke=None):
        return research_cycle.review_cycle(self.project, "writing-and-review", "actual", writer_family="openai",
            prompt=lambda: "Inspect current synthetic sources", invoke=invoke or self.invoke,
            remediate=lambda *args: self.fail("A clean observation does not justify repair"),
            refresh=lambda phase: ({}, {}), writer_notes=[], log=lambda *args: None)

    def test_pending_supplemental_protocol_keeps_two_real_authority_receipts_without_repair(self):
        with patch("scripts.supplemental_experiments.proposal_pending", return_value=True):
            result = self.cycle()
            self.assertEqual(self.calls, ["initial", "final"])
            self.assertTrue(result["remediation_skipped"])
            self.assertEqual(review_receipts.validate_gate(self.project, "G5", "P01", expected_purpose="supplemental_protocol"), [])
            self.assertTrue(review_receipts.validate_gate(self.project, "G5", "P01", expected_purpose="stage"))
        directory = self.project / review_receipts.PREFIX / "G5-P01/actual"
        first, last = read(directory / "initial.json"), read(directory / "final.json")
        self.assertNotEqual(first["identity"]["request_id"], last["identity"]["request_id"])
        self.assertEqual(last["materials"]["review_purpose"], "supplemental_protocol")
        self.assertFalse(read(directory / "observation.json")["gate_authority"])
        self.assertFalse((self.project / "experiments/registry.jsonl").exists())

    def test_ordinary_clean_cycle_has_only_one_protected_advisory_observation(self):
        self.cycle()
        self.assertEqual(self.calls, ["initial"])
        observed = review_receipts.observation(self.project, "writing-and-review", "P01")["receipt"]
        self.assertFalse(observed["gate_authority"])
        self.assertTrue(review_receipts.validate_gate(self.project, "G5", "P01", expected_purpose="scientific_writing"))

    def test_failed_invocation_id_is_never_replayed_or_overwritten(self):
        def broken(phase, request):
            self.calls.append(phase)
            raise ValueError("Synthetic response failure")
        with self.assertRaisesRegex(ValueError, "response failure"):
            self.cycle(broken)
        attempt = self.project / review_receipts.PREFIX / "G5-P01/actual/attempt.json"
        before = attempt.read_bytes()
        with self.assertRaises(FileExistsError):
            self.cycle()
        self.assertEqual(self.calls, ["initial"])
        self.assertEqual(attempt.read_bytes(), before)
