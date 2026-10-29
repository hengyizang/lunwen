"""Declared branches retain real failures, frozen phases and all attempt evidence."""
import copy
import json
import os
import unittest
from unittest.mock import patch

from scripts import research_search_tree as tree, research_toolkit as toolkit
from scripts.research_artifacts import read, record, sha, write
from tests import test_research_iteration as fixtures


class ResearchSearchTreeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ResearchIterationTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.project, self.root = self.fixture.project, self.fixture.root
        (self.root / tree.MODULE).write_text("bound tree builder fixture\n", encoding="utf-8")
        self.one = self.fixture.attempt("one", status="failed", exit_code=1, log="ModuleNotFoundError: missing dependency")
        self.two = self.fixture.attempt("two")
        self.three = self.fixture.attempt("three")
        self.iteration = self.fixture.prepare()
        self.relative = "program/search-branches.json"
        self.request = {"kind": "research_search_tree", "id": "branches-fixture", "max_debug_depth": 1,
            "iteration_report": self.iteration["report_path"], "max_items": 2, "nodes": [
                {"node_id": "initial", "parent_id": None, "branch_kind": "root", "run_id": "one", "attempt_id": self.one["attempt_id"], "workflow_phase": "investigation"},
                {"node_id": "repair", "parent_id": "initial", "branch_kind": "debug", "run_id": "two", "attempt_id": self.two["attempt_id"], "workflow_phase": "tuning"},
                {"node_id": "replication", "parent_id": "initial", "branch_kind": "variation", "run_id": "three", "attempt_id": self.three["attempt_id"], "workflow_phase": "main"}]}
        self.save()

    def save(self):
        write(self.project / self.relative, self.request)

    def prepare(self):
        return tree.refresh(self.project, self.relative, root=self.root)

    def context(self, result, role="critic"):
        return tree.model_context(self.project, result["report_path"], role, root=self.root)

    def test_actual_failure_debug_and_replication_preserve_negative_outputs_and_frozen_phase(self):
        before = self.fixture.snapshot()
        result = self.prepare()
        self.assertEqual(result["all_attempt_count"], 3)
        self.assertEqual(result["unrepresented_attempt_count"], 0)
        self.assertEqual(result["root_ids"], ["initial"])
        self.assertEqual(result["leaf_ids"], ["repair", "replication"])
        self.assertEqual(result["nodes"][0]["status"], "executed_failed_pending_scientific_review")
        self.assertIn("logged_modulenotfounderror", result["nodes"][0]["observed_conditions"])
        self.assertEqual(result["nodes"][1]["consecutive_debug_depth"], 1)
        self.assertTrue(result["nodes"][1]["debug_preparation_limit_reached"])
        self.assertEqual(result["nodes"][2]["consecutive_debug_depth"], 0)
        self.assertEqual(result["nodes"][1]["actual_analysis_phase"], "confirmatory")
        self.assertFalse(result["nodes"][1]["workflow_phase_verified"])
        self.assertFalse(result["automatic_selection_or_pruning"])
        self.assertEqual(result["worklist_omitted"], 1)
        self.assertEqual(result["paid_calls"], result["experiments_executed"], 0)
        for relative, content in before.items():
            if relative != "state/output-provenance.json":
                self.assertEqual((self.project / relative).read_bytes(), content, relative)
        self.assertEqual(read(self.project / "experiments/results/two.json")["metric"], 0.0001)

    def test_unchanged_refresh_and_role_context_are_read_only_and_critic_has_no_proposal(self):
        result = self.prepare()
        before = self.fixture.snapshot()
        with patch.object(tree, "write", side_effect=AssertionError("unchanged report must not rewrite")):
            self.assertEqual(self.prepare(), result)
        for role in ("planner", "writer", "remediator", "critic"):
            context = self.context(result, role)
            self.assertEqual(context["scientific_validation"], "not_assessed")
            self.assertEqual("worklist" in context, role != "critic")
            self.assertEqual("declared_workflow_phase" in context["nodes"][0], role != "critic")
        self.assertEqual(self.fixture.snapshot(), before)

    def test_weak_result_cannot_be_declared_a_debug_failure(self):
        self.request["nodes"][2].update(parent_id="repair", branch_kind="debug")
        self.save()
        with self.assertRaisesRegex(ValueError, "never a weak score"):
            self.prepare()

    def test_missing_attempt_never_auto_selects_latest_or_best_and_all_paths_remain_linked(self):
        self.request["nodes"] = [{"node_id": "unselected", "parent_id": None, "branch_kind": "root", "run_id": "two"}]
        self.save()
        result = self.prepare()
        self.assertEqual(result["nodes"][0]["status"], "attempt_not_selected")
        self.assertIsNone(result["nodes"][0]["attempt_id"])
        self.assertEqual(result["unrepresented_attempt_count"], 3)
        self.assertEqual(result["history_retained_in"], self.iteration["report_path"])
        self.assertEqual(result["nodes"][0]["known_attempt_ids"], [self.two["attempt_id"]])

    def test_planned_branch_has_no_invented_execution(self):
        self.fixture.plan["runs"].append({**copy.deepcopy(self.fixture.plan["runs"][2]), "run_id": "four"})
        write(self.project / "experiments/plan.json", self.fixture.plan)
        # A fresh view reflects the changed plan without creating a new G3 approval.
        self.iteration = self.fixture.prepare()
        self.request["iteration_report"] = self.iteration["report_path"]
        self.request["nodes"].append({"node_id": "planned", "parent_id": None, "branch_kind": "root", "run_id": "four"})
        self.save()
        result = self.prepare()
        self.assertEqual(result["nodes"][-1]["status"], "planned_not_executed")
        self.assertFalse(result["gate_approved"])

    def test_structural_errors_and_nonstring_selectors_are_rejected(self):
        original = copy.deepcopy(self.request)
        mutations = [
            lambda r: r["nodes"][0].update(parent_id="repair", branch_kind="variation"),
            lambda r: r["nodes"][1].update(parent_id="missing"),
            lambda r: r["nodes"][2].update(node_id="repair"),
            lambda r: r["nodes"][2].update(run_id="two", attempt_id=self.two["attempt_id"]),
            lambda r: r["nodes"][1].update(attempt_id=self.one["attempt_id"]),
            lambda r: r["nodes"][1].update(attempt_id="absent-attempt"),
            lambda r: r.update(execute=True),
            lambda r: r.update(model="arbitrary-provider"),
            lambda r: r.update(max_debug_depth=True),
            lambda r: r.update(max_items=21),
        ] + [lambda r, key=key: r["nodes"][1].update({key: []})
             for key in ("run_id", "branch_kind", "attempt_id", "workflow_phase", "parent_id")]
        for change in mutations:
            self.request = copy.deepcopy(original)
            change(self.request)
            self.save()
            with self.subTest(request=self.request), self.assertRaises(ValueError):
                self.prepare()

    def test_current_plan_cannot_relabel_a_historical_attempt_into_another_paper(self):
        self.fixture.plan["runs"][1]["paper_id"] = "P02"
        write(self.project / "experiments/plan.json", self.fixture.plan)
        self.iteration = self.fixture.prepare()
        self.request["iteration_report"] = self.iteration["report_path"]
        self.save()
        with self.assertRaisesRegex(ValueError, "matching real executor attempt"):
            self.prepare()

    def test_unknown_executor_status_remains_unknown_instead_of_becoming_a_success(self):
        receipt = self.project / "experiments/runs/three-attempt-001/run.json"
        changed = read(receipt)
        changed["status"] = None
        write(receipt, changed)
        registry = self.project / "experiments/registry.jsonl"
        rows = [json.loads(line) for line in registry.read_text().splitlines()]
        rows[-1] = changed
        registry.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        self.iteration = self.fixture.prepare()
        self.request["iteration_report"] = self.iteration["report_path"]
        self.save()
        result = self.prepare()
        self.assertEqual(result["nodes"][-1]["status"], "executed_unknown_pending_scientific_review")
        self.assertIn("execution_status_unknown", result["nodes"][-1]["observed_conditions"])

    def test_changed_sources_module_or_report_invalidate_existing_context(self):
        result = self.prepare()
        for relative, base in (("experiments/model.py", self.project),
                               ("experiments/runs/one-attempt-001/stderr.txt", self.project),
                               ("experiments/plan.json", self.project),
                               (self.iteration["report_path"], self.project),
                               (result["report_path"], self.project), (tree.MODULE, self.root)):
            target = base / relative
            before = target.read_bytes()
            if target.suffix == ".json":
                value = read(target)
                value["changed"] = True
                write(target, value)
            else:
                target.write_bytes(before + b"changed\n")
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                self.context(result)
            target.write_bytes(before)
        record(self.project, [self.project / result["report_path"]], "untrusted-writer")
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.context(result)

    def test_cloud_boundary_and_current_selected_toolkit_summary(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(ValueError, "cloud"):
                self.prepare()
        result = self.prepare()
        builder = self.root / toolkit.MODULE
        builder.write_text("bound toolkit fixture\n", encoding="utf-8")
        recipe = self.root / "integrations/codex-research-tools/skills/research-ai-scientist/SKILL.md"
        recipe.parent.mkdir(parents=True)
        recipe.write_text("Declared search ancestry; retain every outcome.\n", encoding="utf-8")
        write(self.root / toolkit.CATALOG, {"schema_version": "1.0", "tools": [{"id": "ai-scientist", "repository": "SakanaAI/AI-Scientist-v2", "commit": "a" * 40,
            "skill_path": recipe.relative_to(self.root).as_posix(), "recipe_path": recipe.relative_to(self.root).as_posix(),
            "recipe_sha256": sha(recipe), "stages": ["experiment-execution"], "native_operations": ["research_search_tree"]}]})
        request = "program/selected-method.json"
        write(self.project / request, {"id": "search-method", "stage": "experiment-execution", "tool_ids": ["ai-scientist"], "task": "AUTHOR_PREFERRED_VERDICT",
            "input_bindings": [{"path": result["report_path"], "sha256": sha(self.project / result["report_path"])}]})
        packet = toolkit.refresh(self.project, request, root=self.root)
        actual_context = tree.model_context
        for role in ("writer", "critic"):
            with patch.object(tree, "model_context", side_effect=lambda p, relative, actual_role: actual_context(p, relative, actual_role, root=self.root)):
                text = toolkit.task_context(self.project, "experiment-execution", role, toolkit.MARKER + packet["packet_path"], root=self.root)
                self.assertIn("one-attempt-001", text)
                self.assertEqual("AUTHOR_PREFERRED_VERDICT" in text, role == "writer")
                self.assertEqual("declared_workflow_phase" in text, role == "writer")


if __name__ == "__main__":
    unittest.main()
