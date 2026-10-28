"""Selected guidance must remain current, nonexecuting and independent."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import api_orchestrator, artifact_ownership, autopilot, cloud_job, literaturectl, research_methods, research_toolkit as toolkit
from scripts.research_artifacts import read, record, sha, write


class ResearchToolkitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "code"
        self.project = Path(self.temporary.name) / "project"
        self.cloud = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"})
        self.cloud.start()
        self.addCleanup(self.cloud.stop)
        builder = self.root / toolkit.MODULE
        builder.parent.mkdir(parents=True)
        builder.write_text("controlled builder fixture\n", encoding="utf-8")
        self.recipe = self.root / "integrations/codex-research-tools/skills/research-fixture/SKILL.md"
        self.recipe.parent.mkdir(parents=True)
        self.recipe.write_text("---\nname: research-fixture\ndescription: Selected method.\n---\nBounded method guidance.\n", encoding="utf-8")
        self.catalog = {"schema_version": "1.0", "tools": [{"id": "fixture-tool", "repository": "example/tool",
            "commit": "a" * 40, "skill_path": self.recipe.relative_to(self.root).as_posix(),
            "recipe_path": self.recipe.relative_to(self.root).as_posix(), "recipe_sha256": sha(self.recipe),
            "stages": ["experiment-design"], "native_operations": ["literature_compare"]}]}
        write(self.root / toolkit.CATALOG, self.catalog)
        write(self.project / "state/run.json", {"stage": "experiment-design", "approved_gates": ["G0", "G1", "G2"]})
        write(self.project / "intake/constraints.json", {"execution_mode": "cloud_only", "budget_cny": 500})
        self.source = self.project / "evidence/current-source.txt"
        self.source.parent.mkdir()
        self.source.write_text("Original source; experiment not yet run.\n", encoding="utf-8")
        self.request = {"id": "design-task", "stage": "experiment-design", "tool_ids": ["fixture-tool"],
            "task": "PREFERRED VERDICT MUST NOT ENTER INDEPENDENT REVIEW",
            "input_bindings": [{"path": "evidence/current-source.txt", "sha256": sha(self.source)}]}
        self.relative = "program/research-tool-task.json"
        write(self.project / self.relative, self.request)

    def prepare(self):
        return toolkit.refresh(self.project, self.relative, root=self.root)

    def marker(self, result):
        return toolkit.MARKER + result["packet_path"]

    def test_packet_reuses_unchanged_output_without_new_calls_or_authority(self):
        old_state = (self.project / "state/run.json").read_bytes()
        first = self.prepare()
        report_path = self.project / first["packet_path"]
        old_receipt = (self.project / "state/output-provenance.json").read_bytes()
        with patch.object(toolkit, "write", side_effect=AssertionError("unchanged packet must not be rewritten")):
            self.assertEqual(self.prepare(), first)
        self.assertEqual((self.project / "state/output-provenance.json").read_bytes(), old_receipt)
        self.assertEqual((self.project / "state/run.json").read_bytes(), old_state)
        self.assertEqual(first["status"], "prepared_not_executed")
        self.assertEqual(first["paid_calls"], 0)
        self.assertFalse(first["upstream_runtime_executed"])
        self.assertEqual(first["scientific_validation"], "not_assessed")
        self.assertTrue(artifact_ownership.executor_owned(self.project, first["packet_path"]))
        self.assertEqual(read(report_path)["input_bindings"], self.request["input_bindings"])

    def test_all_roles_get_current_selected_guidance_but_critic_not_preferred_verdict(self):
        packet = self.prepare()
        marker = self.marker(packet)
        for role in ("planner", "writer", "critic", "remediator"):
            result = toolkit.task_context(self.project, "experiment-design", role, marker, root=self.root)
            self.assertIn("Bounded method guidance.", result)
            self.assertIn("example/tool@" + "a" * 40, result)
            self.assertIn(sha(self.source), result)
            if role == "critic":
                self.assertNotIn(self.request["task"], result)
            else:
                self.assertIn(self.request["task"], result)
        self.assertEqual(toolkit.task_context(None, "intake", "writer", "ordinary unrelated task", root=Path("missing")), "")

    def test_current_literature_reader_note_is_a_source_and_changes_invalidate_packet(self):
        source = self.project / "literature/readers/current.md"
        source.parent.mkdir(parents=True)
        source.write_text("Original methods text, section 3.\n", encoding="utf-8")
        self.request["input_bindings"] = [{"path": "literature/readers/current.md", "sha256": sha(source)}]
        write(self.project / self.relative, self.request)
        packet = self.prepare()
        self.assertIn(sha(source), toolkit.task_context(self.project, "experiment-design", "writer",
            self.marker(packet), root=self.root))
        source.write_text("Changed original text.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "input changed"):
            toolkit.task_context(self.project, "experiment-design", "writer", self.marker(packet), root=self.root)

    def test_changed_source_request_gate_or_recipe_invalidates_existing_packet(self):
        packet = self.prepare()
        marker = self.marker(packet)
        for target in (self.source, self.project / self.relative, self.project / "state/run.json",
                       self.project / "intake/constraints.json", self.recipe, self.root / toolkit.MODULE,
                       self.root / toolkit.CATALOG):
            original = target.read_bytes()
            if target.suffix == ".json":
                value = json.loads(original)
                value["changed"] = True
                write(target, value)
            else:
                target.write_bytes(original + b"changed\n")
            with self.subTest(target=target), self.assertRaises(ValueError):
                toolkit.task_context(self.project, "experiment-design", "writer", marker, root=self.root)
            target.write_bytes(original)

    def test_model_authored_or_modified_packet_is_not_executor_receipt(self):
        packet = self.prepare()
        path = self.project / packet["packet_path"]
        changed = read(path)
        changed["paid_calls"] = 1
        write(path, changed)
        with self.assertRaises(ValueError):
            toolkit.task_context(self.project, "experiment-design", "writer", self.marker(packet), root=self.root)
        write(path, packet)
        record(self.project, [path], "some-other-builder")
        with self.assertRaisesRegex(ValueError, "stale"):
            toolkit.task_context(self.project, "experiment-design", "writer", self.marker(packet), root=self.root)

    def test_unknown_stage_tool_duplicate_or_model_execution_override_is_rejected(self):
        for key, value in (("stage", "submission-ready"), ("tool_ids", ["unknown-tool"]),
                           ("tool_ids", ["fixture-tool", "fixture-tool"]), ("execute", True),
                           ("model", "cheap-model"), ("approve", True)):
            modified = {**self.request, key: value}
            write(self.project / self.relative, modified)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.prepare()
        write(self.project / self.relative, self.request)
        write(self.project / "state/run.json", {"stage": "experiment-execution"})
        with self.assertRaisesRegex(ValueError, "current project stage"):
            self.prepare()

    def test_packet_marker_cannot_escape_or_load_without_matching_stage_and_project(self):
        packet = self.prepare()
        for marker in (toolkit.MARKER + "../outside.json", toolkit.MARKER + "/absolute.json",
                       self.marker(packet) + "\n" + self.marker(packet)):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                toolkit.task_context(self.project, "experiment-design", "writer", marker, root=self.root)
        with self.assertRaises(ValueError):
            toolkit.task_context(None, "experiment-design", "writer", self.marker(packet), root=self.root)
        with self.assertRaises(ValueError):
            toolkit.task_context(self.project, "writing-and-review", "writer", self.marker(packet), root=self.root)

    def test_owner_nonpaid_cloud_operation_reuses_existing_dispatch(self):
        operation = {"action": "research_toolkit", "request_file": self.relative}
        write(self.project / "program/operation.json", operation)
        checked, _ = cloud_job.literature_operation(self.project, "program/operation.json")
        with patch.object(toolkit, "refresh", return_value={"paid_calls": 0}) as refresh:
            self.assertEqual(literaturectl.execute_operation(self.project, checked), {"paid_calls": 0})
            refresh.assert_called_once_with(self.project, self.relative)
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(ValueError, "cloud"):
                self.prepare()
        for forbidden in ("model", "execute", "approve"):
            write(self.project / "program/operation.json", {**operation, forbidden: True})
            with self.assertRaises(cloud_job.CloudJobError):
                cloud_job.literature_operation(self.project, "program/operation.json")

    def test_existing_role_context_loads_packet_only_when_explicitly_selected(self):
        packet = self.prepare()
        with patch.object(research_methods, "installation_errors", return_value=[]), \
             patch.object(research_methods, "load_catalog", return_value={"modules": []}), \
             patch("scripts.ccfa_runtime.model_contract", return_value="Existing CCFA contract"), \
             patch.object(research_methods.scientific_reasoning, "stage_prompt", return_value=""), \
             patch.object(toolkit, "task_context", wraps=toolkit.task_context) as selected:
            # Root is forwarded; normal unselected calls do not open this catalog.
            prompt = research_methods.stage_context("experiment-design", "writer", root=self.root,
                project=self.project, context=self.marker(packet))
            self.assertIn("Bounded method guidance.", prompt)
            self.assertIn("Existing CCFA contract", prompt)
            self.assertEqual(selected.call_count, 1)

    def test_role_snapshot_excludes_old_packets_and_custom_request_but_keeps_scientific_source(self):
        packet = self.prepare()
        write(self.project / "program/custom-operation.json", {"action": "research_toolkit", "request_file": self.relative})
        with patch.object(api_orchestrator, "project_root", return_value=self.project):
            snapshot = api_orchestrator.project_snapshot("study", stage="experiment-design", exclude_reviews=True)
        self.assertNotIn(self.request["task"], snapshot)
        self.assertNotIn(packet["packet_path"], snapshot)
        self.assertNotIn("FILE program/custom-operation.json", snapshot)
        self.assertNotIn("FILE " + self.relative, snapshot)
        self.assertIn("Original source; experiment not yet run.", snapshot)

    def test_cli_review_and_remediation_keep_explicit_tool_selection(self):
        marker = self.marker(self.prepare())
        state = {"stage": "experiment-design", "gate": "G3"}
        with patch.object(api_orchestrator, "critic_prompt", return_value="Independent review") as critic:
            autopilot.critic_prompt("study", state, marker)
        critic.assert_called_once_with("study", "experiment-design", marker)
        with patch.object(research_methods, "stage_context", return_value="Selected method") as methods, \
             patch.object(api_orchestrator, "project_root", return_value=self.project):
            prompt = autopilot.remediation_prompt("study", state, autopilot.ROOT / "review.json", marker)
        self.assertIn("Selected method", prompt)
        methods.assert_called_once_with("experiment-design", "remediator", context=marker, project=self.project)
