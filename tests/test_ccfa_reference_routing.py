"""Applicable complete CCFA rules reach real prompts without a second call."""
import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator as api
from scripts import ccfa_runtime as runtime
from scripts import research_methods


class CCFAReferenceRoutingTests(unittest.TestCase):
    def test_optional_editorial_methods_are_compact_by_default_and_complete_when_selected(self):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no additional model call")):
            compact = runtime.editorial_method_guidance()
            full = runtime.editorial_method_guidance(full=True)
            self.assertIn(compact, runtime.model_contract("writing-and-review", "critic"))
            self.assertIn(full, runtime.model_contract("writing-and-review", "writer", skill="ccf-humanization"))
        humanizer = runtime.read(runtime.ROOT / "config/humanizer-rules.json")
        defensive = runtime.read(runtime.ROOT / "config/anti-defensive-rules.json")
        for row in humanizer["rules"]:
            self.assertIn(f"H{row['number']:02d} {row['title']}", compact)
            self.assertIn(row["guidance"], full)
            self.assertIn(row["exceptions"], full)
        for row in defensive["groups"]:
            self.assertIn(row["review_id"] + " " + row["title"], compact)
            for guidance in row["semantic_checks"]:
                self.assertIn(guidance, full)
        for name in defensive["semantic_only_checks"]:
            self.assertIn(name, full)
        self.assertIn("not a completed full-method pass", compact)
        self.assertLess(len(compact), len(full))
        self.assertNotIn('"coverage_complete"', full)
        self.assertNotIn('"issue_count"', full)

    def test_changed_optional_editorial_sources_are_unavailable_without_blocking_scientific_contract(self):
        import shutil
        paths = [runtime.LOCK, "integrations/editorial-upstreams.lock.json", "config/humanizer-rules.json",
                 "config/anti-defensive-rules.json", "third_party/humanizer/SKILL.md", "third_party/humanizer/LICENSE",
                 "third_party/anti-defensive-writing/SKILL.md", "third_party/anti-defensive-writing/LICENSE"]
        paths += [row["path"] for row in runtime.humanization_policy_receipt()["sources"]]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in paths:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(runtime.ROOT / name, target)
            source = root / "third_party/humanizer/SKILL.md"
            source.write_text(source.read_text() + "\nUNTRUSTED_CHANGED_OPTIONAL_METHOD")
            with patch("scripts.model_runtime.call", side_effect=AssertionError("no additional call")):
                contract = runtime.humanization_contract("writing-and-review", "critic", root=root)
            self.assertIn("Optional H/AD method sources are unavailable or changed", contract)
            self.assertNotIn("UNTRUSTED_CHANGED_OPTIONAL_METHOD", contract)
            self.assertIn(runtime.COMMIT, contract)
            self.assertNotIn("BEGIN PINNED POLICY", contract)

    def test_default_cycles_select_the_current_owner_and_independent_review_role(self):
        cases = [
            ("topic-intelligence", "writer", "ccf-idea-optimizer"),
            ("topic-intelligence", "critic", "ccf-idea-reviewer"),
            ("experiment-design", "planner", "ccf-experiment-designer"),
            ("writing-and-review", "writer", "ccf-paper-writer"),
            ("writing-and-review", "critic", "ccf-paper-reviewer"),
        ]
        for stage, role, owner in cases:
            with self.subTest(stage=stage, role=role):
                self.assertEqual(runtime.selected(stage, role=role),
                                 ["ccf-humanization", "ccf-common", owner])
                prompt = research_methods.stage_context(stage, role)
                self.assertIn("SELECTED CCFA SOURCE "+owner+"/SKILL.md",prompt)
                self.assertNotIn(runtime.source(owner+"/SKILL.md"),prompt)
                self.assertIn("Scientific reasoning contract",prompt)
                self.assertLess(len(prompt),25000)
                for unrelated in ("ccf-rebuttal-writer", "ccf-submission-checker", "ccf-paper-to-exemplar"):
                    self.assertNotIn("BEGIN PINNED CCFA " + unrelated + "/SKILL.md", prompt)

    def test_explicit_tasks_retain_specialists_and_native_source_links(self):
        prompt = runtime.model_contract("writing-and-review", "critic", skill="ccf-visual-composer")
        self.assertIn(runtime.source("ccf-visual-composer/SKILL.md"), prompt)
        self.assertNotIn("BEGIN PINNED CCFA ccf-paper-reviewer/SKILL.md", prompt)
        self.assertNotIn("human G1/G2 topic decisions", prompt)
        self.assertNotIn("preserve cloud-only execution, G0-G5 approvals", prompt)
        self.assertFalse(runtime.installation_errors())
        for identifier in runtime.STAGE_DEFAULTS.values():
            adapter = (runtime.ROOT / "skills" / identifier / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(runtime.VENDOR + "/" + identifier + "/SKILL.md", adapter)
            self.assertNotIn("human G1/G2 topic decisions", adapter)
            self.assertNotIn("G0-G5 human approvals", adapter)

    def test_all_seventeen_default_modes_include_their_complete_applicable_reference_bodies(self):
        ids = {row["id"] for row in runtime.registry()["routes"]}
        self.assertEqual(set(runtime.REFERENCE_DEFAULTS), ids)
        for identifier in ids:
            with self.subTest(skill=identifier), patch("scripts.model_runtime.call", side_effect=AssertionError("No model call permitted")):
                prompt = runtime.model_contract("intake", "writer", skill=identifier)
                self.assertIn(runtime.source(identifier + "/SKILL.md"), prompt)
                for relative in runtime.reference_paths(identifier,full=True):
                    self.assertIn(runtime.source(relative), prompt)
                for item in runtime.humanization_prompt_sources("intake", full=identifier == "ccf-humanization"):
                    relative = item["path"].removeprefix(runtime.VENDOR + "/")
                    self.assertEqual(prompt.count(runtime.source(relative)), 1)

    def test_detailed_humanization_modes_follow_the_evidence_stage_without_truncating_sources(self):
        baseline = runtime.source("ccf-humanization/SKILL.md")
        prose = runtime.source("ccf-humanization/references/humanization-policy.md")
        experiment = runtime.source("ccf-humanization/references/experiment-discipline.md")
        for stage in ("topic-intelligence", "experiment-design", "writing-and-review"):
            prompt = runtime.model_contract(stage, "writer")
            self.assertNotIn(baseline,prompt)
            self.assertNotIn(prose,prompt)
            self.assertNotIn(experiment,prompt)
            self.assertEqual(prompt.count("CCFA writing guidance ("), 1)
            self.assertNotIn("AVAILABLE OBSERVATION CATALOG", prompt)
        explicit = runtime.model_contract("topic-intelligence", "writer", skill="ccf-humanization")
        for item in runtime.humanization_prompt_sources("topic-intelligence", full=True):
            self.assertIn((runtime.ROOT / item["path"]).read_text(encoding="utf-8"), explicit)

    def test_explicit_policy_reference_is_not_deduplicated_before_it_was_loaded(self):
        path = "ccf-humanization/references/humanization-policy.md"
        prompt = runtime.model_contract("topic-intelligence", "writer", path)
        self.assertEqual(prompt.count(runtime.source(path)), 1)

    def test_exact_humanization_entry_loads_once_without_unrequested_reference_bundle(self):
        relative = "ccf-humanization/SKILL.md"
        body = runtime.source(relative)
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "state").mkdir()
            (project / "state/run.json").write_text(json.dumps({
                "stage": "writing-and-review", "gate": "G5", "active_paper": "P01"}), encoding="utf-8")
            for role in ("planner", "writer", "critic", "remediator"):
                with self.subTest(role=role):
                    ordinary = research_methods.stage_context("writing-and-review", role, project=project)
                    explicit = research_methods.stage_context("writing-and-review", role, project=project,
                        context=runtime.VENDOR + "/" + relative)
                    self.assertNotIn(body, ordinary)
                    self.assertEqual(explicit.count(body), 1)
                    self.assertIn("SHA256 " + hashlib.sha256(runtime.canonical(body.encode())).hexdigest(), explicit)
                    self.assertEqual(explicit.count("CCFA writing guidance ("), 1)
                    self.assertNotIn("LOCAL COMPLETE COVERAGE", explicit)
                    for name in ("humanization-policy.md", "experiment-discipline.md"):
                        self.assertNotIn(runtime.source("ccf-humanization/references/" + name), explicit)

    def test_task_modes_and_exact_nested_sources_select_full_bodies_without_loading_other_venues(self):
        cases = [
            ("ccf-paper-writer", "mode: compress", "ccf-paper-writer/references/compression-rules.md"),
            ("ccf-paper-reviewer", "mode: version-comparison", "ccf-paper-reviewer/references/version-comparison.md"),
            ("ccf-visual-composer", "plot the recorded statistics", "ccf-visual-composer/references/python-plot-recipes.md"),
            ("ccf-idea-optimizer", "frontier ideation", "ccf-idea-optimizer/references/frontier-ideation.md"),
            ("ccf-paper-writer", "ccf-paper-writer/references/venue-guides/cvpr.md", "ccf-paper-writer/references/venue-guides/cvpr.md"),
        ]
        for identifier, task, relative in cases:
            with self.subTest(task=task):
                prompt = runtime.model_contract("writing-and-review", "writer", task, skill=identifier)
                self.assertIn(runtime.source(relative), prompt)
                self.assertNotIn("BEGIN PINNED CCFA ccf-paper-writer/references/venue-guides/aaai.md", prompt)
                hashes = re.findall(r"BEGIN PINNED CCFA \S+ SHA256 ([a-f0-9]{64})", prompt)
                self.assertEqual(len(hashes), len(set(hashes)))

    def test_shared_api_loads_complete_specialist_only_when_task_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.model_runtime.call", side_effect=AssertionError("No paid call permitted")):
            project = Path(directory)
            (project / "state").mkdir()
            (project / "state/run.json").write_text(json.dumps({
                "stage": "experiment-design", "active_paper": "P01"}))
            reference = "ccf-experiment-designer/references/evidence-design.md"
            with patch.object(api, "project_root", return_value=project), patch.object(
                    runtime, "model_contract", side_effect=AssertionError("No implicit method bundle")):
                prompts = [api.planning_prompt("fixture", "experiment-design", "Design the next comparison"),
                    api.writer_prompt("fixture", "experiment-design", "Design the next comparison"),
                    api.critic_prompt("fixture", "experiment-design", "Review the comparison"),
                    api.remediation_prompt("fixture", "experiment-design", "Revise the comparison", "{}")]
            for prompt in prompts:
                self.assertNotIn(runtime.source(reference), prompt)
            packet = runtime.prepare(project, {"schema_version": "1.0", "id": "selected-design",
                "skill": "ccf-experiment-designer", "stage": "experiment-design", "paper_id": "P01",
                "task": "Design the next comparison", "inputs": [], "references": [reference]})
            self.assertEqual(packet["model_calls"], 0)
            self.assertFalse(packet["scientific_completion_verified"])
            with patch.object(api, "project_root", return_value=project):
                explicit = api.writer_prompt("fixture", "experiment-design", "Design the next comparison")
            self.assertEqual(explicit.count(runtime.source(reference)), 1)
            self.assertNotIn("BEGIN PINNED CCFA ccf-paper-writer/references/venue-guides/", explicit)

    def test_active_defaults_and_explicit_reference_share_one_body_and_task_specific_owner(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(directory)
            (project / "state").mkdir()
            (project / "state/run.json").write_text(json.dumps({"stage": "writing-and-review", "active_paper": "P01"}), encoding="utf-8")
            relative = "ccf-paper-writer/references/prose-quality-guardrails.md"
            runtime.prepare(project, {"schema_version": "1.0", "id": "bounded-compression", "skill": "ccf-paper-writer",
                "stage": "writing-and-review", "paper_id": "P01", "task": "mode: compress; preserve all evidence.",
                "inputs": [], "references": [relative]})
            prompt = research_methods.stage_context("writing-and-review", "writer", project=project)
            for relative in (relative, "ccf-paper-writer/SKILL.md", "ccf-paper-writer/references/compression-rules.md"):
                body = runtime.source(relative)
                self.assertEqual(prompt.count(body), 1, relative)
                fingerprint = hashlib.sha256(runtime.canonical(body.encode())).hexdigest()
                self.assertEqual(prompt.count("SHA256 " + fingerprint), 1)
            self.assertNotIn("BEGIN PINNED CCFA ccf-rebuttal-writer/SKILL.md", prompt)
            self.assertNotIn("BEGIN PINNED CCFA ccf-visual-composer/SKILL.md", prompt)
            self.assertNotIn(runtime.source("ccf-humanization/SKILL.md"),prompt)
            self.assertEqual(prompt.count("CCFA writing guidance ("),1)

    def test_explicit_cross_skill_nested_venue_is_reachable_without_activating_another_owner(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(directory)
            (project / "state").mkdir()
            (project / "state/run.json").write_text(json.dumps({"stage": "writing-and-review", "active_paper": "P01"}), encoding="utf-8")
            relative = "ccf-paper-writer/references/venue-guides/cvpr.md"
            packet = runtime.prepare(project, {"schema_version": "1.0", "id": "venue-check", "skill": "ccf-submission-checker",
                "stage": "writing-and-review", "paper_id": "P01", "task": "Inspect the supplied venue policy without submitting.",
                "inputs": [], "references": [relative]})
            self.assertNotIn("ccf-paper-writer", packet["skills"])
            prompt = runtime.model_contract("writing-and-review", "critic", project=project)
            self.assertEqual(prompt.count(runtime.source(relative)), 1)
            self.assertNotIn("BEGIN PINNED CCFA ccf-paper-writer/SKILL.md", prompt)

    def test_shared_api_prompts_preserve_selected_source_once_without_stage_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / "evidence/observations.md"
            source.parent.mkdir()
            body = "Observed effect -0.24; interval [-0.41, -0.07]. Failed replication remains unresolved."
            source.write_text(body)
            with patch.object(api, "project_root", return_value=project), patch.object(
                    runtime, "model_contract", side_effect=AssertionError("No implicit method bundle")):
                prompts = [
                    api.planning_prompt("fixture", "writing-and-review", "Draft the interpretation", source_paths=["evidence/observations.md"]),
                    api.writer_prompt("fixture", "writing-and-review", "Draft the interpretation", source_paths=["evidence/observations.md"]),
                    api.critic_prompt("fixture", "writing-and-review", "Review the interpretation", source_paths=["evidence/observations.md"]),
                    api.remediation_prompt("fixture", "writing-and-review", "Correct the interpretation", "{}", source_paths=["evidence/observations.md"]),
                ]
            for prompt in prompts:
                self.assertEqual(prompt.count(body), 1)
                self.assertIn(hashlib.sha256(source.read_bytes()).hexdigest(), prompt)
                self.assertNotIn("G5 SCIENTIFIC WRITING:", prompt)
                self.assertNotIn("LOCAL COMPLETE COVERAGE", prompt)

    def test_draft_topic_and_exploratory_design_do_not_demand_final_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "state").mkdir()
            (project / "state/run.json").write_text(json.dumps({"stage": "experiment-design", "active_paper": "P01"}))
            with patch.object(api, "project_root", return_value=project):
                topic = api.writer_prompt("fixture", "topic-intelligence", "Refine one working question")
                exploration = api.writer_prompt("fixture", "experiment-design", "Run an exploratory comparison")
            self.assertIn("Refine one working question", topic)
            self.assertNotIn("Only the formal G1 topic decision", topic)
            self.assertNotIn("consecutive_no_material_new_work_rounds", topic)
            self.assertIn("research_phase='exploratory'", exploration)
            self.assertNotIn("critical_tests", exploration)
            self.assertNotIn("clean_room_run_ids", exploration)
            self.assertNotIn("HUMAN_INPUT_REQUIRED", exploration)
