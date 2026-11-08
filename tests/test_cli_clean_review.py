"""Compatibility API review with synthetic transport and real sealed receipts."""
from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts import (
    api_orchestrator,
    autopilot,
    model_spend,
    output_provenance,
    review_receipts,
)
from scripts.ai_providers import ModelResult
from scripts.research_artifacts import read, write
from scripts.research_notebook import cycle_review
from tests.research_cycle_fixtures import pending_decision


class CLICleanReviewTests(unittest.TestCase):
    def run_clean_cycle(self, stage="topic-intelligence", gate="G1", index=1, writer_notes=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        project = root / "projects/demo"
        state = {"schema_version": "2.0", "stage_index": index, "stage": stage, "gate": gate,
                 "status": "awaiting_work", "active_paper": "P01", "paper_count": 1,
                 "paper_statuses": {"P01": "active"}, "approved_gates": [], "approvals": []}
        write(project / "state/run.json", state)
        write(project / "intake/constraints.json", {"research_goal": "Synthetic compatibility fixture"})
        write(project / "papers/P01/paper-contract.json", {"paper_id": "P01", "writing_phase": "scientific"})
        target = project / "program/scientific-notes.txt"
        target.parent.mkdir(parents=True)
        audit = {"verdict": "pass-with-conditions", "fatal_findings": [], "major_findings": [],
                 "minor_findings": [], "missing_evidence": [], "remediation_steps": [],
                 "uncertainty": ["Synthetic software fixture; scientific validity is not established."]}
        calls = []
        write(project / model_spend.FILE, model_spend.initial())
        plan = {"schema_version": "1.0", "stage": stage, **{key: [] for key in (
            "objectives", "artifact_specs", "evidence_requirements", "figure_specs", "risks", "open_questions")}}

        def response(_root, *, role, provider, prompt, **kwargs):
            calls.append(role)
            if role == "semantic-planner":
                payload = plan
            elif role == "persistent-writer":
                token = re.search(r'cycle_id="([^\"]+)"', prompt).group(1)
                notebook = pending_decision(root / "response-fixture", stage, token, "P01" if gate == "G5" else None)
                payload = {"schema_version": "1.0", "stage": stage, "notes": writer_notes or [], "artifacts": [
                    {"path": "program/scientific-notes.txt", "content": "Bounded independent evidence interpretation remains provisional.\n"},
                    {"path": "program/research-notebook.json", "content": json.dumps(notebook)}]}
            else:
                self.assertEqual(role, "independent-critic-initial", "A clean review cannot request repair/re-review")
                payload = audit
            model = "gpt-software-fixture" if provider == "openai" else "claude-software-fixture"
            return ModelResult(provider, model, json.dumps(payload), {}, reported_model=model,
                completion_status="completed", request_id=role + "-fixture")

        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}, clear=True))
            stack.enter_context(patch.object(api_orchestrator, "ROOT", root))
            stack.enter_context(patch.object(autopilot.researchctl, "PROJECTS_ROOT", root / "projects"))
            for selected, value in {
                "scripts.model_routing.production_enabled": False,
                "scripts.scientific_scope.validate": [],
                "scripts.cloud_research_steps.before_cycle": {"control_only": False, "blockers": []},
                "scripts.model_runtime.preflight_route": {},
                "scripts.model_runtime.budget_status": {},
                "scripts.api_orchestrator.stage_config": {"gate": gate},
                "scripts.api_orchestrator.prepare_discovery_evidence": (
                    json.dumps({"literature": {"receipts": [{"fixture_only": True}], "pending_searches": 0}}), None),
                "scripts.api_orchestrator.prepare_revision_baseline": None,
                "scripts.api_orchestrator.refresh_post_write_evidence": {"academic_style_audit": {}, "controlled_steps": {}},
                "scripts.api_orchestrator.refresh_research_method_audits": {},
                "scripts.research_increments.freeze_plans": None,
                "scripts.research_increments.record_editing_attempt": None,
                "scripts.automated_quality.checked_run": None,
                "scripts.literature_model_screening.cycle_input": None,
                "scripts.cost_audit.refresh": {},
                "scripts.researchctl.gate_errors": ["Actual scientific stage remains unaccepted."],
            }.items():
                stack.enter_context(patch(selected, return_value=value))
            for name in ("planning_prompt", "writer_prompt", "critic_prompt", "remediation_prompt"):
                stack.enter_context(patch.object(api_orchestrator, name, return_value="Synthetic source-bound request"))
            stack.enter_context(patch("scripts.model_runtime.call", side_effect=response))
            result = autopilot.run_stage("demo")

        self.assertEqual(calls, ["semantic-planner", "persistent-writer", "independent-critic-initial"])
        self.assertEqual(result["status"], "needs_work")
        self.assertTrue(result["cost_controls"]["remediation_skipped"])
        self.assertEqual(result["provider_audit"]["remediation"]["status"], "not_called")
        token = result["run_id"]
        run_dir = project / "api_runs" / token
        self.assertFalse((run_dir / "remediation-response.txt").exists())
        self.assertFalse((project / "state/autopilot.json").exists())
        key = gate + ("-P01" if gate == "G5" else "")
        receipt_root = project / review_receipts.PREFIX / key / token
        final = read(receipt_root / "observation.json")
        self.assertFalse((receipt_root / "initial.json").exists())
        self.assertFalse((receipt_root / "final.json").exists())
        self.assertEqual(final["phase"], "observation")
        self.assertEqual(final["dispositions"], writer_notes or [])
        self.assertEqual(final["identity"]["request_id"], "independent-critic-initial-fixture")
        self.assertFalse(final["identity"]["cache_hit"])
        self.assertFalse(final["scientific_completion_verified"])
        self.assertFalse(final["gate_authority"])
        decision = cycle_review(project, stage, token)
        self.assertEqual(decision["decisions"][0]["outcome"], "pending")
        self.assertFalse(decision["scientific_completion_verified"])
        log = (project / "reviews/decision-log.md").read_text(encoding="utf-8")
        self.assertIn("One fresh advisory critique", log)
        self.assertNotIn("Final independent audit", log)
        for note in writer_notes or ["no actionable findings"]:
            self.assertIn(note, log)
        self.assertEqual(output_provenance.current_origin(project, target)["family"], "openai")
        self.assertEqual(read(project / "state/run.json"), state)
        return project, result, final

    def test_clean_initial_review_needs_only_one_actual_critic(self):
        project, _, _ = self.run_clean_cycle()
        self.assertFalse(review_receipts.observation(project, "topic-intelligence")["receipt"]["gate_authority"])

    def test_plain_uncertainty_notes_survive_advisory_observation(self):
        notes = ["The scientific interpretation remains provisional."]
        project, _, final = self.run_clean_cycle(writer_notes=notes)
        self.assertEqual(final["dispositions"], notes)
        self.assertFalse(review_receipts.observation(project, "topic-intelligence")["receipt"]["gate_authority"])

    def test_scientific_writing_clean_review_keeps_actual_observation(self):
        project, _, final = self.run_clean_cycle("writing-and-review", "G5", 5)
        self.assertEqual(final["dispositions"], [])
        self.assertEqual(final["materials"]["review_purpose"], "scientific_writing")
        self.assertFalse(review_receipts.observation(project, "writing-and-review", "P01")["receipt"]["gate_authority"])
        self.assertEqual(read(project / "papers/P01/paper-contract.json")["writing_phase"], "scientific")
        self.assertFalse((project / "papers/P01/submission").exists())
        state = read(project / "state/run.json")
        state["writing_phases"] = {"P01": "submission"}
        write(project / "state/run.json", state)
        self.assertTrue(review_receipts.validate_gate(project, "G5", "P01"),
                        "A scientific-writing audit cannot stand in for the submission review")
