"""All 17 skills reach actual API/CLI roles without provider requests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import api_orchestrator as api, autopilot, ccfa_runtime as runtime

class CCFAModelHandoffTests(unittest.TestCase):
    def test_every_skill_and_full_references_reach_each_existing_authorized_role(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project = Path(directory)
            (project / "state").mkdir()
            state = {"stage": "topic-intelligence", "gate": "G1", "active_paper": "P01"}
            (project / "state/run.json").write_text(json.dumps(state))
            (project / "program").mkdir()
            (project / "program/core-thesis.json").write_text(json.dumps({"doctoral_question": "Synthetic integration fixture, not a real thesis."}))
            config = {"contract": "G1", "gate": "G1", "author_task": "Source-bound integration fixture"}
            with patch.object(api, "project_root", return_value=project), patch.object(api, "stage_config", return_value=config), patch("scripts.model_runtime.call", side_effect=AssertionError("No model call authorized")):
                for identifier in (row["id"] for row in runtime.registry()["routes"]):
                    with self.subTest(skill=identifier):
                        packet = runtime.prepare(project, {"schema_version": "1.0", "id": identifier,
                            "skill": identifier, "task": "Author preference: predetermined positive verdict.",
                            "stage": state["stage"], "paper_id": "P01", "inputs": []})
                        prompts = {
                            "api planner": api.planning_prompt("fixture", state["stage"], ""),
                            "api writer": api.writer_prompt("fixture", state["stage"], ""),
                            "api critic": api.critic_prompt("fixture", state["stage"], ""),
                            "api remediation": api.remediation_prompt("fixture", state["stage"], "", "{}"),
                            "cli planner": autopilot.planner_prompt("fixture", state, config, ""),
                            "cli writer": autopilot.writer_prompt("fixture", state, config, "", autopilot.ROOT / "plan.md"),
                            "cli critic": autopilot.critic_prompt("fixture", state),
                            "cli remediation": autopilot.remediation_prompt("fixture", state, autopilot.ROOT / "review.json")}
                        for name, prompt in prompts.items():
                            self.assertIn("CCFA PROJECT ADAPTER", prompt, name)
                            self.assertIn("Smoke-Test Scope", prompt, name)
                            self.assertIn(runtime.source("ccf-humanization/SKILL.md"), prompt, name)
                            for guide in packet["complete_skill_guidance"]:
                                if guide["skill"] != "ccf-humanization":
                                    self.assertIn(json.dumps(guide, ensure_ascii=False), prompt, name)
                            if "critic" in name:
                                self.assertNotIn("Author preference: predetermined positive verdict.", prompt)
                            else:
                                self.assertIn("Author preference: predetermined positive verdict.", prompt)

