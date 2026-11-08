"""Compatibility commands retain actual controller transitions over the API cycle."""

import io
import shutil
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import api_orchestrator as api
from scripts import autopilot, model_runtime, model_spend, researchctl
from scripts.research_artifacts import read, write


class AutopilotTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        (self.root / "config").mkdir()
        shutil.copyfile(
            api.ROOT / "config/stages.json", self.root / "config/stages.json"
        )
        self.stack.enter_context(patch.object(api, "ROOT", self.root))
        self.stack.enter_context(
            patch.object(researchctl, "PROJECTS_ROOT", self.root / "projects")
        )
        self.stack.enter_context(
            patch("scripts.scientific_scope.validate", return_value=[])
        )
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        researchctl.initialize(
            SimpleNamespace(project="demo", paper_count=6, venue=None)
        )
        self.project = researchctl.project_dir("demo")

    def stage(self, index, status="awaiting_work"):
        state = researchctl.load_state("demo")
        state.update(
            stage_index=index,
            stage=researchctl.STAGES[index]["name"],
            gate=researchctl.STAGES[index]["gate"],
            status=status,
        )
        researchctl.save_state("demo", state)
        return state

    def cycle(self, result=None):
        return patch.object(
            api,
            "run_cycle",
            return_value=result
            or {
                "run_id": "synthetic-cycle",
                "research_decision": {"errors": [], "review_errors": []},
            },
        )

    def test_plan_has_no_requests_writes_or_paid_authority_for_two_three_conditional_five_and_panel(
        self,
    ):
        for index, phase, expected, repaired in (
            (0, None, 2, 2),
            (1, None, 3, 5),
            (5, "scientific", 3, 5),
            (5, "submission", 5, 5),
        ):
            with self.subTest(stage=index, phase=phase):
                state = self.stage(index)
                if phase:
                    state["writing_phases"] = {"P01": phase}
                    write(self.project / "state/run.json", state)
                before = {
                    p.relative_to(self.project): p.read_bytes()
                    for p in self.project.rglob("*")
                    if p.is_file()
                }
                with (
                    patch.object(
                        model_runtime,
                        "call",
                        side_effect=AssertionError("plan cannot call models"),
                    ),
                    patch.object(
                        model_runtime,
                        "authorized_calls",
                        side_effect=AssertionError(
                            "plan cannot request paid authority"
                        ),
                    ),
                ):
                    result = autopilot.show_plan("demo", "untrusted task")
                self.assertEqual(result["paid_model_calls"], 0)
                self.assertEqual(result["planned_model_calls"], expected)
                self.assertEqual(result["with_repair_model_calls"], repaired)
                self.assertEqual(
                    before,
                    {
                        p.relative_to(self.project): p.read_bytes()
                        for p in self.project.rglob("*")
                        if p.is_file()
                    },
                )

    def test_pending_owner_topics_stop_before_model_or_budget_access(self):
        for index in (1, 2):
            self.stage(index, "awaiting_approval")
            before = (self.project / "state/run.json").read_bytes()
            with (
                self.cycle() as cycle,
                patch.object(model_runtime, "authorized_calls") as authorize,
            ):
                result = autopilot.run_stage("demo")
            self.assertEqual(result["status"], "awaiting_human_topic_approval")
            cycle.assert_not_called()
            authorize.assert_not_called()
            self.assertEqual((self.project / "state/run.json").read_bytes(), before)

    def test_completed_project_starts_no_cycle(self):
        self.stage(len(researchctl.STAGES) - 1, "submission_ready")
        with self.cycle() as cycle:
            self.assertEqual(autopilot.run_stage("demo")["status"], "submission_ready")
        cycle.assert_not_called()
        self.assertEqual(autopilot.show_plan("demo")["steps"], [])

    def test_start_initializes_once_and_resume_preserves_existing_project_inputs(self):
        with self.cycle({"paid_model_cycle": False}) as cycle:
            self.assertEqual(
                autopilot.main(
                    [
                        "start",
                        "--project",
                        "new-project",
                        "--context",
                        "owner constraints",
                    ]
                ),
                0,
            )
            project = researchctl.project_dir("new-project")
            self.assertEqual(researchctl.load_state("new-project")["paper_count"], 6)
            original = (project / "intake/constraints.json").read_bytes()
            self.assertEqual(autopilot.main(["resume", "--project", "new-project"]), 0)
            self.assertEqual(autopilot.main(["start", "--project", "new-project"]), 0)
        self.assertEqual(cycle.call_count, 3)
        self.assertEqual((project / "intake/constraints.json").read_bytes(), original)

    def test_plan_distinguishes_pending_owner_decisions_and_clean_protocol_double_review(
        self,
    ):
        self.stage(1, "awaiting_approval")
        self.assertEqual(autopilot.show_plan("demo")["planned_model_calls"], 0)
        for index, status in (
            (0, "approved"),
            (2, "approved"),
            (5, "approved"),
            (0, "awaiting_approval"),
            (3, "awaiting_approval"),
        ):
            with self.subTest(index=index, status=status):
                self.stage(index, status)
                before = (self.project / "state/run.json").read_bytes()
                with patch.object(
                    model_runtime,
                    "call",
                    side_effect=AssertionError("no preview inference"),
                ):
                    result = autopilot.show_plan("demo")
                self.assertEqual(result["status"], "control_pending")
                self.assertIsNone(result["planned_model_calls"])
                self.assertIsNone(result["with_repair_model_calls"])
                self.assertEqual(result["paid_model_calls"], 0)
                self.assertEqual((self.project / "state/run.json").read_bytes(), before)
        self.stage(5)
        from scripts.supplemental_experiments import PROPOSAL

        write(
            self.project / "papers/P01" / PROPOSAL,
            {"round_id": "R001", "scope_id": "s001"},
        )
        result = autopilot.show_plan("demo")
        self.assertEqual(result["planned_model_calls"], 4)
        self.assertEqual(result["with_repair_model_calls"], 5)
        self.assertEqual(result["paid_model_calls"], 0)

    def test_actual_G0_ready_and_advance_record_only_a_machine_decision(self):
        with (
            self.cycle() as cycle,
            patch.object(researchctl, "gate_errors", return_value=[]),
            patch.object(researchctl, "artifact_hash", return_value="a" * 64),
        ):
            result = autopilot.run_stage(
                "demo",
                "owner context",
                max_output_tokens=12000,
                control_max_output_tokens=4000,
            )
        current = researchctl.load_state("demo")
        self.assertEqual(result["status"], "stage_advanced")
        self.assertEqual(current["gate"], "G1")
        self.assertEqual(current["status"], "awaiting_work")
        self.assertEqual(current["approvals"][0]["decision_type"], "deterministic")
        self.assertEqual(
            current["approvals"][0]["actor"], "deterministic-control-plane"
        )
        self.assertEqual(
            cycle.call_args.args,
            (
                "demo",
                "intake",
                "anthropic",
                "openai",
                "anthropic",
                "owner context",
                "",
                12000,
                4000,
            ),
        )
        self.assertFalse((self.project / "state/autopilot.json").exists())

    def test_current_checks_mark_both_topics_ready_without_inventing_owner_votes(self):
        for index in (1, 2):
            self.stage(index)
            with (
                self.cycle(),
                patch.object(researchctl, "gate_errors", return_value=[]),
                patch.object(researchctl, "artifact_hash", return_value="a" * 64),
            ):
                result = autopilot.run_stage("demo")
            current = researchctl.load_state("demo")
            self.assertEqual(result["status"], "awaiting_human_topic_approval")
            self.assertEqual(current["status"], "awaiting_approval")
            self.assertEqual(current["approvals"], [])
            self.assertEqual(current.get("paper_topic_approvals", []), [])

    def test_approved_and_legacy_pending_non_topic_gates_use_checked_transition(self):
        for status in ("approved", "awaiting_approval"):
            self.stage(0)
            with (
                patch.object(researchctl, "gate_errors", return_value=[]),
                patch.object(researchctl, "artifact_hash", return_value="a" * 64),
            ):
                researchctl.mark_ready(
                    SimpleNamespace(
                        project="demo", note="Synthetic state-transition fixture"
                    )
                )
                state = researchctl.load_state("demo")
                state["status"] = status
                researchctl.save_state("demo", state)
                with self.cycle(
                    {
                        "paid_model_cycle": False,
                        "controlled_steps": {"control_only": True},
                    }
                ) as cycle:
                    result = autopilot.run_stage("demo")
            self.assertEqual(result["status"], "controlled_step")
            self.assertEqual(researchctl.load_state("demo")["gate"], "G1")
            self.assertEqual(cycle.call_args.args[1], "topic-intelligence")

    def test_control_only_and_special_recovery_results_never_ready_the_old_stage(self):
        cases = (
            ({"paid_model_cycle": False}, "controlled_step"),
            ({"writing_phase_transition": "submission"}, "submission_preparation"),
            ({"primary_recovery": {"retired": True}}, "protocol_retired_to_G3"),
        )
        for manifest, expected in cases:
            self.stage(5)
            with (
                self.cycle(manifest),
                patch.object(autopilot, "transition_ready_gate") as transition,
            ):
                result = autopilot.run_stage("demo")
            self.assertEqual(result["status"], expected)
            transition.assert_not_called()

    def test_independent_decision_errors_prevent_ready_even_when_other_checks_pass(
        self,
    ):
        with (
            self.cycle({"research_decision": {"review_errors": ["wrong cycle"]}}),
            patch.object(researchctl, "gate_errors", return_value=[]),
            patch.object(autopilot, "transition_ready_gate") as transition,
        ):
            result = autopilot.run_stage("demo")
        self.assertEqual(result["gate_errors"], ["research decision: wrong cycle"])
        self.assertEqual(result["status"], "needs_work")
        transition.assert_not_called()

    def test_missing_spending_authority_and_transport_failure_never_advance_or_retry(
        self,
    ):
        (self.project / model_spend.FILE).unlink()
        with self.cycle() as cycle, self.assertRaises(model_spend.SpendControlError):
            autopilot.run_stage("demo")
        cycle.assert_not_called()
        write(self.project / model_spend.FILE, model_spend.initial())
        before = read(self.project / "state/run.json")
        with (
            patch.object(
                api,
                "run_cycle",
                side_effect=RuntimeError("ambiguous transport; retain reservation"),
            ) as cycle,
            patch.object(autopilot, "transition_ready_gate") as transition,
            self.assertRaisesRegex(RuntimeError, "ambiguous"),
        ):
            autopilot.run_stage("demo")
        cycle.assert_called_once()
        transition.assert_not_called()
        self.assertEqual(read(self.project / "state/run.json"), before)
