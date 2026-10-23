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
    def test_all_seventeen_default_modes_include_their_complete_applicable_reference_bodies(self):
        ids = {row["id"] for row in runtime.registry()["routes"]}
        self.assertEqual(set(runtime.REFERENCE_DEFAULTS), ids)
        for identifier in ids:
            with self.subTest(skill=identifier), patch("scripts.model_runtime.call", side_effect=AssertionError("No model call permitted")):
                prompt = runtime.model_contract("intake", "writer", skill=identifier)
                self.assertIn(runtime.source(identifier + "/SKILL.md"), prompt)
                for relative in runtime.reference_paths(identifier):
                    self.assertIn(runtime.source(relative), prompt)
                for relative in ("ccf-humanization/SKILL.md", "ccf-humanization/references/humanization-policy.md",
                                 "ccf-humanization/references/experiment-discipline.md"):
                    self.assertEqual(prompt.count(runtime.source(relative)), 1)

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

    def test_unactivated_ordinary_api_and_cli_prompts_receive_reference_text_not_only_paths(self):
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
                    self.assertIn(runtime.source(relative), prompt)
                self.assertNotIn("BEGIN PINNED CCFA ccf-paper-writer/references/venue-guides/", prompt)

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
            self.assertEqual(prompt.count(runtime.source("ccf-humanization/SKILL.md")), 1)

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


if __name__ == "__main__":
    unittest.main()
