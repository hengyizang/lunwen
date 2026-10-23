"""Owner operating amendments preserve science, accounting and stopped execution."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_continuation, cloud_human_acceptance as acceptance
from scripts import cloud_human_controls as controls, model_spend, operating_constraints, researchctl
from scripts.research_artifacts import read, sha, write


class OperatingConstraintsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patched = patch.object(researchctl, "PROJECTS_ROOT", self.root / "projects")
        patched.start()
        self.addCleanup(patched.stop)
        cloud = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"})
        cloud.start()
        self.addCleanup(cloud.stop)
        self.project = acceptance.fixture(researchctl.PROJECTS_ROOT)
        target = self.project / "intake/constraints.json"
        constraints = read(target)
        constraints.update(target_submission_ready_date="2026-10-07", time_horizon_years=None,
            research_goal="Six independently defensible papers before 2026-10-07; acceptance is not promised.",
            notes=["The requested date is preserved; the planning checkpoint is 2026-10-06. Quality cannot be promised.",
                   "The owner confirmed the initial cumulative model API envelope of CNY 300, with CNY 45 per-paper warning and CNY 60 per-paper hard limits. This intake is not a ledger grant; the separate owner cloud authorize_budget job records the first tranche before any paid transport.",
                   "Spending authorization is cumulative: initial approval for CNY 300, then an explicit next-tranche approval for CNY 600, CNY 900 and so on.",
                   "Historical initial tranche of CNY 300 was approved separately; cloud execution only.",
                   "Historical observed event on 2026-10-07 and 2026-10-06 must stay recorded."])
        write(target, constraints)
        for operation in ("ready", "approve", "advance"):
            acceptance.decide(operation, selectors={"gate": "G0"})
        state = researchctl.load_state(self.project.name)
        self.actor = acceptance.request("status")["actor"]
        model_spend.grant(self.project, new_ceiling_cny=300, actor=self.actor, run_id="10")
        policy = {"schema_version": "1.0", "enabled": True, "actor": self.actor,
            "confirmed_at": "2026-09-30T17:24:37+00:00", "confirmation_note": "Standing cloud work only under all existing controls.",
            "system_execution_hours_per_day": 24, "resume_interval_minutes": 15,
            "constraints_sha256": sha(target), "g0_approval_artifact_sha256": state["approvals"][-1]["artifact_sha256"],
            "stop_when": "all_papers_submission_ready"}
        write(self.project / cloud_continuation.POLICY, policy)
        self.selectors = {"new_ceiling_cny": 500, "target_submission_ready_date": "2026-10-26"}

    def dossier(self, **selectors):
        return controls.execute(acceptance.request("review_dossier", operation="amend_operating_constraints",
            **(selectors or self.selectors)), "20")

    def decide(self, dossier=None, **selectors):
        fields = selectors or self.selectors
        snapshot = dossier or self.dossier(**fields)
        return controls.execute(acceptance.request("amend_operating_constraints", **fields,
            expected_sha256=snapshot["review_sha256"], note="Owner explicitly requests total CNY 500 and target 2026-10-26; do not start paid work."), "21")

    def test_review_is_read_only_and_exposes_exact_narrow_change(self):
        from scripts.cloud_checkpoint import inventory
        before = inventory(self.project)
        with patch("urllib.request.urlopen", side_effect=AssertionError("no provider calls")):
            dossier = self.dossier()
        self.assertTrue(dossier["ready_for_operation"], dossier["blockers"])
        self.assertEqual(before, inventory(self.project))
        preview = dossier["operating_amendment_preview"]
        self.assertEqual(preview["constraints_before"]["model_api_budget_cny"], 300)
        self.assertEqual(preview["constraints_after"]["model_api_budget_cny"], 500)
        self.assertEqual(preview["constraints_after"]["target_submission_ready_date"], "2026-10-26")

    def test_apply_preserves_existing_approvals_accounts_and_cloud_policy(self):
        reservation = model_spend.reserve(self.project, max_cost_cny=30, paper_id="P01", paper_limit_cny=60, run_id="11")
        model_spend.settle(self.project, reservation, actual_cost_cny=12)
        model_spend.reserve(self.project, max_cost_cny=6, paper_id="P01", paper_limit_cny=60, run_id="12")
        original = read(self.project / "intake/constraints.json")
        old_state = researchctl.load_state(self.project.name)
        old_spend = model_spend.read(self.project, required=True)
        old_policy = read(self.project / cloud_continuation.POLICY)
        with patch("urllib.request.urlopen", side_effect=AssertionError("no provider calls")):
            receipt = self.decide()
        current = read(self.project / "intake/constraints.json")
        self.assertEqual({k: v for k, v in original.items() if k not in {"notes", "research_goal", "model_api_budget_cny", "target_submission_ready_date"}},
                         {k: v for k, v in current.items() if k not in {"notes", "research_goal", "model_api_budget_cny", "target_submission_ready_date"}})
        self.assertIn("2026-10-26", current["research_goal"])
        self.assertIn("2026-10-25", current["notes"][0])
        self.assertIn("CNY 45 per-paper warning and CNY 60", current["notes"][1])
        self.assertIn("CNY 500", current["notes"][2])
        self.assertIn("CNY 800", current["notes"][2])
        self.assertEqual(current["notes"][3], original["notes"][3])
        self.assertEqual(current["notes"][4], original["notes"][4])
        state = researchctl.load_state(self.project.name)
        self.assertEqual(state["approved_gates"], ["G0"])
        self.assertEqual(state["approvals"][:-1], old_state["approvals"])
        self.assertFalse(state["approvals"][-1]["scientific_approval_granted"])
        self.assertEqual({k: state[k] for k in ("gate", "stage", "status", "paper_count", "paper_statuses")},
                         {k: old_state[k] for k in ("gate", "stage", "status", "paper_count", "paper_statuses")})
        spend = model_spend.read(self.project, required=True)
        for key in ("spent_cny", "paper_spent_cny", "reservations", "reconciliation_events"):
            self.assertEqual(spend[key], old_spend[key])
        self.assertEqual(spend["authorization_events"][:-1], old_spend["authorization_events"])
        self.assertEqual(spend["authorized_ceiling_cny"], 500)
        policy = read(self.project / cloud_continuation.POLICY)
        self.assertEqual(policy["constraints_sha256"], sha(self.project / "intake/constraints.json"))
        self.assertEqual(policy["g0_approval_artifact_sha256"], state["approvals"][-1]["artifact_sha256"])
        for key in set(policy) - {"constraints_sha256", "g0_approval_artifact_sha256"}:
            self.assertEqual(policy[key], old_policy[key])
        self.assertEqual(receipt["paid_calls"], 0)
        self.assertEqual(cloud_continuation.evaluate(self.project.name, {})["reason"], "billing_reconciliation_pending")
        audit = read(self.project / "state/operating-constraints-amendments/21.json")
        self.assertEqual(audit["constraints_before"], original)
        self.assertTrue(audit["planning_date_is_not_a_completion_guarantee"])

    def test_different_date_or_changed_state_cannot_reuse_review(self):
        snapshot = self.dossier()
        with self.assertRaisesRegex(controls.HumanControlError, "changed"):
            self.decide(snapshot, new_ceiling_cny=500, target_submission_ready_date="2026-10-27")
        state = researchctl.load_state(self.project.name)
        state["history"].append({"event": "changed synthetic context"})
        researchctl.save_state(self.project.name, state)
        with self.assertRaisesRegex(controls.HumanControlError, "changed"):
            self.decide(snapshot)

    def test_stopped_continuation_remains_stopped_and_noop_is_rejected(self):
        policy = read(self.project / cloud_continuation.POLICY)
        policy["enabled"] = False
        write(self.project / cloud_continuation.POLICY, policy)
        self.decide()
        self.assertFalse(read(self.project / cloud_continuation.POLICY)["enabled"])
        result = self.dossier()
        self.assertFalse(result["ready_for_operation"])
        self.assertIn("must change", result["blockers"][0])

    def test_deadline_only_does_not_add_budget_authorization(self):
        before = model_spend.read(self.project, required=True)
        self.decide(new_ceiling_cny=300, target_submission_ready_date="2026-10-26")
        self.assertEqual(model_spend.read(self.project, required=True), before)

    def test_advanced_or_scientifically_approved_projects_are_not_silently_rebound(self):
        baseline = researchctl.load_state(self.project.name)
        variants = [dict(baseline, status="awaiting_approval"), dict(baseline, approved_gates=["G0", "G1"]),
                    dict(baseline, approvals=[*baseline["approvals"], {"gate": "G1", "actor": self.actor}])]
        for state in variants:
            with self.subTest(state=state):
                write(self.project / "state/run.json", state)
                self.assertIn("limited to open G1", self.dossier()["blockers"][0])
        write(self.project / "state/run.json", baseline)
        (self.project / "experiments/registry.jsonl").write_text('{"run_id":"failed","status":"failed"}\n', encoding="utf-8")
        self.assertIn("executed experiment", self.dossier()["blockers"][0])

    def test_changed_old_intake_or_wrong_owner_cannot_rebind_authority(self):
        current = read(self.project / "intake/constraints.json")
        current["research_goal"] += " Unauthorized change."
        write(self.project / "intake/constraints.json", current)
        self.assertIn("hashes must still match", self.dossier()["blockers"][0])
        with self.assertRaisesRegex(ValueError, "hashes must still match"):
            operating_constraints.prepare(self.project, 500, "2026-10-26", "Another owner")

    def test_bad_selectors_and_underfunded_ceiling_are_rejected(self):
        for amount in (True, 500.0, 0, -1, "500"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                operating_constraints.validate_selectors(amount, "2026-10-26")
        for day in (None, "20261026", "2026-1-2", "2026-02-30"):
            with self.subTest(day=day), self.assertRaises(ValueError):
                operating_constraints.validate_selectors(500, day)
        model_spend.reserve(self.project, max_cost_cny=30, paper_id="P01", paper_limit_cny=60, run_id="12")
        self.assertIn("below spent and reserved", self.dossier(new_ceiling_cny=20,
            target_submission_ready_date="2026-10-26")["blockers"][0])

    def test_failed_write_rolls_back_entire_control_transaction(self):
        before = {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()}
        with patch.object(operating_constraints, "record", side_effect=RuntimeError("synthetic provenance write failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic provenance"):
                self.decide()
        after = {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
