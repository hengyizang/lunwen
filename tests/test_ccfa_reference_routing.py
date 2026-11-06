"""Applicable complete CCFA rules reach real prompts without a second call."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from scripts import api_orchestrator as api, autopilot, ccfa_runtime as runtime, research_methods


class CCFAReferenceRoutingTests(unittest.TestCase):
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

    def test_explicit_tasks_retain_specialists_and_native_topic_decision_policy(self):
        prompt = runtime.model_contract("writing-and-review", "critic", skill="ccf-visual-composer")
        self.assertIn(runtime.source("ccf-visual-composer/SKILL.md"), prompt)
        self.assertNotIn("BEGIN PINNED CCFA ccf-paper-reviewer/SKILL.md", prompt)
        self.assertIn("human G1/G2 topic decisions", prompt)
        self.assertNotIn("preserve cloud-only execution, G0-G5 approvals", prompt)
        self.assertFalse(runtime.installation_errors())
        for identifier in runtime.STAGE_DEFAULTS.values():
            adapter = (runtime.ROOT / "skills" / identifier / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("human G1/G2 topic decisions", adapter)
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
                from scripts.ccfa_humanization import prompt_sources
                for item in prompt_sources("intake", full=identifier == "ccf-humanization"):
                    relative = item["path"].removeprefix(runtime.VENDOR + "/")
                    self.assertEqual(prompt.count(runtime.source(relative)), 1)

    def test_detailed_humanization_modes_follow_the_evidence_stage_without_truncating_sources(self):
        from scripts import ccfa_humanization as human
        baseline = runtime.source("ccf-humanization/SKILL.md")
        prose = runtime.source("ccf-humanization/references/humanization-policy.md")
        experiment = runtime.source("ccf-humanization/references/experiment-discipline.md")
        for stage in ("topic-intelligence", "experiment-design", "writing-and-review"):
            prompt = runtime.model_contract(stage, "writer")
            self.assertNotIn(baseline,prompt)
            self.assertNotIn(prose,prompt)
            self.assertNotIn(experiment,prompt)
            self.assertIn("native core preflight",prompt)
            self.assertEqual("LOCAL COMPLETE COVERAGE" in prompt, stage == "writing-and-review")
        explicit = runtime.model_contract("topic-intelligence", "writer", skill="ccf-humanization")
        for item in human.prompt_sources("topic-intelligence", full=True):
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
                    self.assertEqual(explicit.count("native core preflight"), 1)
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

    def test_ordinary_api_and_cli_prompts_receive_core_and_load_exact_full_sources_on_demand(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.model_runtime.call", side_effect=AssertionError("No paid call permitted")):
            project = Path(directory)
            (project / "state").mkdir()
            state = {"stage": "experiment-design", "gate": "G3", "active_paper": "P01"}
            (project / "state/run.json").write_text(json.dumps(state), encoding="utf-8")
            config = {"contract": "G3", "gate": "G3", "author_task": "Design a source-bound protocol"}
            with patch.object(api, "project_root", return_value=project), patch.object(api, "stage_config", return_value=config):
                prompts = [api.planning_prompt("fixture", state["stage"], ""),
                    api.writer_prompt("fixture", state["stage"], ""),
                    api.critic_prompt("fixture", state["stage"], ""),
                    api.remediation_prompt("fixture", state["stage"], "", "{}"),
                    autopilot.planner_prompt("fixture", state, config, ""),
                    autopilot.writer_prompt("fixture", state, config, "", autopilot.ROOT / "plan.md"),
                    autopilot.critic_prompt("fixture", state),
                    autopilot.remediation_prompt("fixture", state, autopilot.ROOT / "review.json")]
            for prompt in prompts:
                for relative in ("ccf-experiment-designer/references/evidence-design.md",
                                 "ccf-experiment-designer/references/result-templates.md",
                                 "ccf-common/references/privacy-and-evidence.md"):
                    self.assertNotIn(runtime.source(relative),prompt)
                self.assertIn("critical_tests",prompt)
                self.assertIn("data rights",prompt)
                self.assertNotIn("BEGIN PINNED CCFA ccf-paper-writer/references/venue-guides/", prompt)
            reference="ccf-experiment-designer/references/evidence-design.md"
            with patch.object(api,"project_root",return_value=project):
                explicit=api.writer_prompt("fixture",state["stage"],reference)
            self.assertEqual(explicit.count(runtime.source(reference)),1)

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
            self.assertEqual(prompt.count("native core preflight"),1)

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

    def test_scientific_contract_occurs_once_in_every_api_and_cli_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory)
            state={"stage":"writing-and-review","gate":"G5","active_paper":"P01","paper_count":1}
            (project/"state").mkdir()
            (project/"state/run.json").write_text(json.dumps(state))
            config={"contract":"G5","gate":"G5","author_task":"Current scientific writing"}
            with patch.object(api,"project_root",return_value=project),patch.object(api,"active_paper",return_value="P01"):
                prompts=[api.planning_prompt("fixture",state["stage"],""),api.writer_prompt("fixture",state["stage"],""),
                    api.critic_prompt("fixture",state["stage"],""),api.remediation_prompt("fixture",state["stage"],"","{}"),
                    autopilot.planner_prompt("fixture",state,config,""),
                    autopilot.writer_prompt("fixture",state,config,"",autopilot.ROOT/"plan.md"),
                    autopilot.critic_prompt("fixture",state),
                    autopilot.remediation_prompt("fixture",state,autopilot.ROOT/"review.json")]
            for prompt in prompts:
                self.assertEqual(prompt.count("G5 SCIENTIFIC WRITING:"),1)
                self.assertNotIn("At G5 read the protected academic-style audit",prompt)
                self.assertNotIn("LOCAL COMPLETE COVERAGE",prompt)
                self.assertLess(len(prompt),25000)

    def test_draft_topic_and_exploratory_design_do_not_demand_final_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory)
            (project/"state").mkdir()
            (project/"state/run.json").write_text(json.dumps({"stage":"experiment-design","gate":"G3","active_paper":"P01"}))
            (project/"experiments").mkdir()
            (project/"experiments/plan.json").write_text('{"research_phase":"exploratory"}')
            with patch.object(api,"project_root",return_value=project):
                topic=api.writer_prompt("fixture","topic-intelligence","")
                exploration=api.writer_prompt("fixture","experiment-design","")
            self.assertIn("status=in_progress|ready_for_review",topic)
            self.assertNotIn("consecutive_no_material_new_work_rounds>=2",topic)
            self.assertNotIn("unresolved_search_gaps=[]",topic)
            self.assertIn("Only the formal G1 topic decision",topic)
            self.assertIn("Unknown power",exploration)
            self.assertNotIn("critical_tests",exploration)
            self.assertNotIn("clean_room_run_ids",exploration)
            self.assertIn("preserve every failed/adverse attempt",exploration)


if __name__ == "__main__":
    unittest.main()
