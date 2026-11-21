"""Actual local exploration, immutable preparation, and truthful numeric binding."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import experiment_runner as runner, paper_execution, research_phase, research_quality
from scripts.research_artifacts import read, sha, write
from scripts.result_values import extract
from scripts.scientific_numbers import number_in_text


class ExecutionProtocolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "research-probe"
        self.project.mkdir()
        write(self.project / "state/run.json", {"stage": "writing-and-review", "gate": "G1", "status": "draft",
              "paper_count": 2, "active_paper": "P01", "paper_execution_mode": "independent", "approvals": []})
        write(self.project / "intake/constraints.json", {"cloud_compute_budget_usd": 1, "cash_budget_usd": 1})
        self.script = self.project / "analysis/probe.py"; self.script.parent.mkdir()
        self.script.write_text("from pathlib import Path\np=Path('results/P01/probe.json')\n"
                               "p.parent.mkdir(parents=True,exist_ok=True)\np.write_text('{\"estimate\": -0.5}')\n")
        self.plan = {"schema_version": "1.0", "status": "ready_for_review", "research_phase": "exploratory",
            "exploration": {"unknown": "Can the synthetic probe retain an adverse value?", "discriminating_test": "Read its actual output."},
            "runs": [{"run_id": "P01-probe", "paper_id": "P01", "argv": [sys.executable, "analysis/probe.py"],
                "cwd": ".", "seed": 0, "timeout_seconds": 10, "estimated_cost_usd": 0, "isolation": {"kind": "host"},
                "inputs": [{"path": "analysis/probe.py", "sha256": sha(self.script)}], "expected_outputs": ["results/P01/probe.json"]}]}
        self.plan_path = paper_execution.artifact_path(self.project, "experiments/plan.json")
        write(self.plan_path, self.plan)
        write(paper_execution.artifact_path(self.project, "experiments/budget.json"), {"status": "ready_for_review", "hard_ceiling_usd": 1})
        env = patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "DR_OS_REQUIRE_REMOTE_RESERVATION": "0"})
        env.start(); self.addCleanup(env.stop)

    def test_minimal_probe_executes_from_any_context_without_review_or_other_paper(self):
        state = (self.project / "state/run.json").read_bytes()
        result = runner.execute(self.project.name, project_root=self.project)
        self.assertEqual(result[0]["status"], "succeeded")
        self.assertEqual(read(self.project / "results/P01/probe.json")["estimate"], -0.5)
        self.assertEqual((self.project / "state/run.json").read_bytes(), state)
        self.assertIsNone(paper_execution.approval(self.project, "G3"))
        snapshot = paper_execution.protocol_seal(self.project)
        self.assertEqual(snapshot["kind"], "execution_protocol")
        self.assertEqual(snapshot, runner.prepare_execution(self.project))
        self.assertEqual(research_phase.build_report(self.project, "P01")["status"], "complete")
        research_phase.archive_and_reopen(self.project)
        self.assertTrue(research_phase.histories(self.project, "P01"))

    def test_snapshot_does_not_allow_input_or_phase_relabeling(self):
        runner.prepare_execution(self.project)
        self.script.write_text("print('changed after freeze')")
        with self.assertRaisesRegex((runner.ExperimentError, ValueError), "changed"):
            runner.prepare_execution(self.project)
        self.plan["research_phase"] = "confirmatory"
        write(self.plan_path, self.plan)
        with self.assertRaises((runner.ExperimentError, ValueError, RuntimeError)):
            runner.prepare_execution(self.project)

    def test_confirmatory_label_requires_actual_prospective_design(self):
        self.plan["research_phase"] = "confirmatory"; write(self.plan_path, self.plan)
        with self.assertRaises((runner.ExperimentError, ValueError, RuntimeError)):
            runner.execute(self.project.name, project_root=self.project)
        self.assertFalse((self.project / "results/P01/probe.json").exists())


class ActualResultValueTests(unittest.TestCase):
    def test_meta_contradiction_requires_an_opposite_interval(self):
        from scripts.results_validation import _outcome_error
        comparison = {"analysis_phase": "confirmatory", "role": "primary", "decision": "does_not_establish_claim",
            "statistics": {"direction": "greater", "minimum_effect": .1, "summary": {"ci_low": -.2, "ci_high": .2}}}
        self.assertIsNotNone(_outcome_error("contradicted", [comparison], empirical=False))
        comparison["statistics"]["summary"] = {"ci_low": -.7, "ci_high": -.3}
        self.assertIsNone(_outcome_error("contradicted", [comparison], empirical=False))
        comparison["statistics"].update(direction="less", summary={"ci_low": .3, "ci_high": .7})
        self.assertIsNone(_outcome_error("contradicted", [comparison], empirical=False))

    def test_unused_method_damage_does_not_stop_a_task_but_selected_damage_does(self):
        from scripts import research_methods
        module = {"id": "unavailable-method", "stages": ["experiment-design"], "path": "references/unavailable-method.md",
                  "sha256": "a"*64, "source_ids": []}
        with patch.object(research_methods, "load_catalog", return_value={"modules": [module]}), \
                patch.object(research_methods, "installation_errors", side_effect=AssertionError("global installation audit is not a task dependency")):
            self.assertIn("not loaded", research_methods.stage_context("experiment-design", "writer"))
            with self.assertRaisesRegex(ValueError, "modified adapted method"):
                research_methods.stage_context("experiment-design", "writer", context="unavailable-method")

    def test_signed_tokens_never_match_the_opposite_or_a_substring(self):
        for text, value, expected in (("estimate=-0.125", "0.125", False), ("estimate=−0.125", "0.125", False),
                ("estimate=−0.125", "-0.125", True), ("effect 1.25e-2", "0.0125", True),
                ("effect 10.125", "0.125", False), ("value NaN", "NaN", False)):
            self.assertEqual(number_in_text(text, value), expected)

    def test_value_must_come_from_selected_output_and_exact_json_or_csv_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); write(root / "result.json", {"metrics": {"F1": 0.8}})
            binding = {"path": "result.json", "sha256": sha(root / "result.json"), "selector": {"json_pointer": "/metrics/F1"}}
            outputs = {(binding["path"], binding["sha256"])}
            self.assertEqual(extract(root, binding, outputs=outputs), 0.8)
            with self.assertRaisesRegex(ValueError, "selected attempts"):
                extract(root, binding, outputs=set())
            (root / "result.csv").write_text("id,estimate\na,-0.125\nb,0.8\n")
            binding = {"path": "result.csv", "sha256": sha(root / "result.csv"), "selector": {"column": "estimate", "row": {"id": "a"}}}
            self.assertEqual(extract(root, binding), -0.125)
            (root / "result.csv").write_text("id,estimate\na,-0.125\na,0.8\n"); binding["sha256"] = sha(root / "result.csv")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                extract(root, binding)

    def test_nonfinite_comparison_values_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), 10**1000):
            errors = []
            research_quality._validate_comparison_values({"metric": "F1", "original_value": value,
                "reproduction_value": .8, "absolute_tolerance": .02, "within_tolerance": True},
                "fixture", {"F1": .02}, errors, baseline=False)
            self.assertTrue(any("finite" in e for e in errors))
