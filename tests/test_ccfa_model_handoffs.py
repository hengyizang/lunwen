"""All 17 pinned skills remain explicitly reachable through API/CLI roles."""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator as api
from scripts import ccfa_runtime as runtime
from scripts.research_artifacts import read, record, sha, write


class CCFAModelHandoffTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.state = {"stage": "topic-intelligence", "gate": "G1", "active_paper": "P01"}
        write(self.project / "state/run.json", self.state)
        write(self.project / "program/core-thesis.json", {
            "doctoral_question": "Synthetic integration fixture, not a real thesis."})
        self.config = {"contract": "G1", "gate": "G1", "author_task": "Source-bound integration fixture"}
        for mocked in (
            patch.dict("os.environ", {"DR_OS_CLOUD_EXECUTOR": "1"}),
            patch.object(api, "project_root", return_value=self.project),
            patch.object(api, "stage_config", return_value=self.config),
            patch("scripts.model_runtime.call", side_effect=AssertionError("No model call authorized")),
        ):
            mocked.start()
            self.addCleanup(mocked.stop)

    def prompts(self):
        stage = self.state["stage"]
        return {
            "api planner": lambda: api.planning_prompt("fixture", stage, ""),
            "api writer": lambda: api.writer_prompt("fixture", stage, ""),
            "api critic": lambda: api.critic_prompt("fixture", stage, ""),
            "api remediation": lambda: api.remediation_prompt("fixture", stage, "", "{}"),
        }

    def prepare(self, identifier, *, full=False):
        task = ("full-reference-review; " if full else "") + "Author preference: predetermined positive verdict."
        references = runtime.reference_paths(identifier, full=True)
        request = {"schema_version": "1.0", "id": identifier + ("-full" if full else "-scoped"),
            "skill": identifier, "task": task, "stage": self.state["stage"], "paper_id": "P01", "inputs": []}
        if references and not full:
            request["references"] = references[:1]
        return runtime.prepare(self.project, request)

    def assert_role_boundaries(self, name, prompt):
        self.assertIn("CCFA PROJECT ADAPTER", prompt)
        self.assertEqual(prompt.count("native core preflight"), 1)
        for binding in runtime.humanization_policy_receipt()["sources"]:
            self.assertIn(binding["path"], prompt)
            self.assertIn(binding["sha256"], prompt)
        hashes = re.findall(r"BEGIN PINNED CCFA \S+ SHA256 ([a-f0-9]{64})", prompt)
        self.assertEqual(len(hashes), len(set(hashes)))
        if "critic" in name:
            self.assertNotIn("Author preference: predetermined positive verdict.", prompt)
        else:
            self.assertIn("Author preference: predetermined positive verdict.", prompt)

    def test_every_explicit_skill_reaches_all_roles_without_unrequested_preflight_bundles(self):
        identifiers = [row["id"] for row in runtime.registry()["routes"]]
        self.assertEqual(len(identifiers), 17)
        for identifier in identifiers:
            packet = self.prepare(identifier)
            for name, render in self.prompts().items():
                with self.subTest(skill=identifier, role=name):
                    prompt = render()
                    self.assert_role_boundaries(name, prompt)
                    self.assertEqual(prompt.count(runtime.source(identifier + "/SKILL.md")), 1)
                    for reference in packet["selected_references"]:
                        self.assertIn(reference["text"], prompt)
                        self.assertIn(reference["sha256"], prompt)
                    baseline = runtime.source("ccf-humanization/SKILL.md")
                    self.assertEqual(prompt.count(baseline), int(identifier == "ccf-humanization"))
                    if identifier not in {"ccf-common", "ccf-humanization"}:
                        self.assertNotIn(runtime.source("ccf-common/references/routing.md"), prompt)

    def test_full_reference_requests_reach_each_existing_authorized_role(self):
        for identifier in (row["id"] for row in runtime.registry()["routes"]):
            packet = self.prepare(identifier, full=True)
            references = runtime.reference_paths(identifier, packet["request"]["task"], full=True)
            for name, render in self.prompts().items():
                with self.subTest(skill=identifier, role=name):
                    prompt = render()
                    self.assert_role_boundaries(name, prompt)
                    self.assertEqual(prompt.count(runtime.source(identifier + "/SKILL.md")), 1)
                    for relative in references:
                        self.assertIn(runtime.source(relative), prompt)
                    for binding in runtime.humanization_prompt_sources(self.state["stage"], full=True):
                        relative = binding["path"].removeprefix(runtime.VENDOR + "/")
                        self.assertEqual(prompt.count(runtime.source(relative)), 1)

    def test_changed_pinned_task_guidance_is_rejected_by_every_role(self):
        self.prepare("ccf-experiment-designer")
        active = self.project / "reports/ccfa-tasks/active.json"
        binding = read(active)
        target = self.project / binding["path"]
        packet = read(target)
        packet["complete_skill_guidance"][-1]["text"] += "\nChanged fixture guidance."
        packet["packet_id"] = runtime.digest({key: value for key, value in packet.items() if key != "packet_id"})
        write(target, packet)
        write(active, {**binding, "sha256": sha(target)})
        # Even correctly bound controller bytes cannot change the pinned source.
        record(self.project, [target, active], "scripts/ccfa_runtime.py")
        for name, render in self.prompts().items():
            with self.subTest(role=name), self.assertRaisesRegex(ValueError, "task guidance changed"):
                render()

