"""Real API/CLI submission adapters and frozen panel receipts with inert transports.

Scientific builders use the existing software fixture's pending records. These
tests establish invocation and evidence plumbing, never actual scientific G5.
"""
import json
import re
import unittest
from unittest.mock import patch

from scripts import ai_providers, api_orchestrator as api, autopilot, model_runtime, model_spend, review_panel
from scripts.research_artifacts import write
from tests import test_production_cycle as production_fixture
from tests.research_cycle_fixtures import pending_decision
from tests.test_review_panel import panel_inputs
from tests.review_scope_fixtures import prepare_scope


class SubmissionPanelAdapterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = production_fixture.ProductionCycleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.stack, self.project = self.fixture.stack, self.fixture.project
        self.stage = "writing-and-review"
        write(self.fixture.root / "config/stages.json", {"stages": {self.stage: {
            "gate": "G5", "contract": "Synthetic final submission fixture", "author_task": "Fixture only"}}})
        self.state = {"schema_version": "2.0", "stage_index": 5, "stage": self.stage, "gate": "G5",
            "status": "awaiting_work", "active_paper": "P01", "paper_count": 1,
            "paper_statuses": {"P01": "active"}, "writing_phases": {"P01": "submission"}}
        prepare_scope(self.project, self.state)
        panel_inputs(self.project)
        self.stack.enter_context(patch.object(autopilot, "ROOT", self.fixture.root))
        self.stack.enter_context(patch.object(autopilot.researchctl, "PROJECTS_ROOT", self.fixture.root / "projects"))
        self.count = 0

    def response(self, provider, prompt, **kwargs):
        self.count += 1
        model = kwargs["model"]
        if "Read-only mutually blind scientific critique." in prompt:
            seat = next(seat for seat, purpose in review_panel.PURPOSES.items() if purpose in prompt)
            body = {"view": seat, "findings": [], "uncertainty": ["Synthetic fixture; no scientific clearance."]}
            if seat == "domain":
                pointer = "papers/P01/manuscript/methods.txt:L1-L1"
                body["findings"] = [{"id": "unsupported-inference", "claim_pointer": pointer,
                    "evidence_pointer": pointer, "gap": "No discriminating result is available.",
                    "minimum_test": "Collect the registered discriminating observation.",
                    "severity": "major", "rationale": "Only a synthetic software source was supplied."}]
        elif self.count == 1:
            body = {"schema_version": "1.0", "stage": self.stage, "objectives": ["Synthetic fixture"],
                "artifact_specs": [], "evidence_requirements": [], "figure_specs": [], "risks": [], "open_questions": []}
        else:
            token = re.search(r'cycle_id="([^"]+)"', prompt).group(1)
            notebook = pending_decision(self.fixture.root / "response-fixture", self.stage, token, "P01")
            body = {"schema_version": "1.0", "stage": self.stage, "notes": [], "artifacts": [
                {"path": "program/research-notebook.json", "content": json.dumps(notebook)},
                {"path": "papers/P01/manuscript/writer-note.txt", "content": "Synthetic source only; no scientific result."}]}
        spec = ai_providers.PRODUCTION_PROVIDERS[provider]
        return ai_providers.ModelResult(provider, model, json.dumps(body), {"input_tokens": 10, "output_tokens": 10},
            "fixture-request-" + str(self.count), model, spec["protocol"], spec["root"] + spec["path"].format(model=model),
            "fixture-only-gateway", completion_status="completed", requested_effort=kwargs["reasoning_effort"])

    def assert_panel(self, calls, panel):
        seats = [call for call in calls.call_args_list if call.kwargs["role"].startswith("independent-critic-panel-")]
        self.assertEqual(len(seats), 3)
        self.assertEqual(panel["paid_calls"], 3)
        records = review_panel.responses(self.project, "P01")
        self.assertEqual({row["receipt"]["identity"]["family"] for row in records}, {"anthropic", "google", "deepseek"})
        for call in seats:
            self.assertFalse(call.kwargs["use_cache"])
            seat = call.kwargs["role"].removeprefix("independent-critic-panel-")
            self.assertNotIn("No discriminating result is available.", call.kwargs["prompt"])
            for other in set(review_panel.VIEWS) - {seat}:
                unique = review_panel.VIEWS[other] - review_panel.VIEWS[seat]
                self.assertFalse(any("SYNTHETIC " + kind + " source" in call.kwargs["prompt"] for kind in unique))
        self.assertFalse(panel["scientific_completion_verified"])
        self.assertFalse(panel["gate_authority"])
        self.assertEqual(panel["findings"][0]["severity"], "major")
        self.assertFalse((self.project / "state/review-receipts/G5-P01").exists())
        self.assertFalse((self.project / "papers/P01/submission").exists())
        self.assertEqual(model_spend.read(self.project)["reservations"], {})

    def test_api_final_submission_runs_two_authors_then_three_real_panel_receipts(self):
        with patch.object(ai_providers, "call", side_effect=self.response) as transport, \
                patch.object(model_runtime, "call", wraps=model_runtime.call) as calls:
            result = api.run_cycle("demo", self.stage, "anthropic", "openai", "anthropic", "", "",
                max_output_tokens=300, control_max_output_tokens=100, automatic_data=False,
                task_profile={"task_class": "routine-implementation", "science_risk": "routine"})
        self.assertEqual(transport.call_count, 5)
        self.assertEqual([call.kwargs["role"] for call in calls.call_args_list[:2]], ["semantic-planner", "persistent-writer"])
        self.assertEqual(len(calls.call_args_list), 5)
        self.assertIsNone(result["critic_provider"])
        self.assertEqual(result["provider_audit"]["critic_1"]["reason"], "submission_panel")
        self.assert_panel(calls, result["independent_audit"]["panel"])
        self.assertAlmostEqual(model_spend.read(self.project)["spent_cny"], 0.005)

    def test_cli_final_submission_runs_two_cli_steps_and_three_api_panel_receipts(self):
        token, invoked = "submission-adapter-fixture", []
        self.stack.enter_context(patch.object(autopilot, "run_token", return_value=token))
        self.stack.enter_context(patch.object(autopilot, "load_stage_config", return_value={self.stage: {"gate": "G5"}}))
        self.stack.enter_context(patch.object(autopilot, "planner_prompt", return_value="Synthetic read-only planner packet"))
        self.stack.enter_context(patch.object(autopilot, "writer_prompt", return_value="Synthetic source-bound writer packet"))
        self.stack.enter_context(patch.object(autopilot, "refresh_post_write_evidence", return_value={"academic_style_audit": {}, "controlled_steps": {}}))
        self.stack.enter_context(patch("scripts.autopilot.shutil.which", side_effect=lambda name: "/synthetic/" + name))

        def invoke(name, command, run_dir, timeout, max_output, **kwargs):
            invoked.append(name)
            self.assertEqual(name, "planner", "Final submission must not also run an ordinary CLI critic")
            write(run_dir / (name + ".stdout.txt"), {"result": "Synthetic read-only plan.",
                "model": "claude-opus-5-5", "session_id": "synthetic-planner"})
            return {"name": name, "status": "succeeded", "exit_code": 0}

        def writer(slug, protected, name, command, run_dir, last_message, timeout, max_output):
            invoked.append(name)
            self.assertEqual(name, "writer")
            pending_decision(self.project, self.stage, token, "P01")
            target = self.project / "papers/P01/manuscript/writer-note.txt"
            target.write_text("Synthetic manuscript preparation only.\n")
            write(last_message, {"dispositions": []})
            return {"name": name, "status": "succeeded", "exit_code": 0}

        with patch.object(autopilot, "invoke", side_effect=invoke), patch.object(autopilot, "invoke_writer", side_effect=writer), \
                patch.object(ai_providers, "call", side_effect=self.response) as transport, \
                patch.object(model_runtime, "call", wraps=model_runtime.call) as calls:
            result = autopilot.run_stage("demo", "", "standard", 1, 10000, 0)
        self.assertEqual(invoked, ["planner", "writer"])
        self.assertEqual(transport.call_count, 3)
        self.assertEqual(result["status"], "needs_work")
        self.assertEqual([run["name"] for run in result["runs"]], invoked)
        self.assert_panel(calls, result["submission_panel"])
        self.assertAlmostEqual(model_spend.read(self.project)["spent_cny"], 0.003)
