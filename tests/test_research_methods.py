from __future__ import annotations

import copy
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator, autopilot, figure_layout
from scripts import pre_submission_review as review
from scripts import research_candidates as candidates
from scripts import research_methods as methods
from scripts import source_scope


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def anchor(project, path, excerpt, locator="L1"):
    return {"path": path, "sha256": methods.sha256(project / path),
            "locator": locator, "excerpt": excerpt}


class ResearchMethodTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "study"
        self.source = self.project / "evidence/source.txt"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("X is associated with Y.\nConfounding remains unresolved.\n", encoding="utf-8")
        self.evidence = anchor(self.project, "evidence/source.txt", "X is associated with Y.")

    def idea(self, identifier):
        return {"hypothesis_id": identifier, "hypothesis": "Intervention changes the measured response.",
                "source_observation": "A located association motivates a prospective test.",
                "precise_difference": "Randomize the intervention rather than reuse an observational design.",
                "prediction": "A randomized treatment changes the response under the measured conditions.",
                "falsifying_result": "A precise null effect excludes the predeclared meaningful effect.",
                "null_result_value": "The observational association may not survive intervention.",
                "source_anchors": [copy.deepcopy(self.evidence)],
                "alternative_explanations": [
                    {"explanation": "Confounding", "discriminating_test": "Randomize assignment.",
                     "expected_if_true": "The association disappears under randomization."},
                    {"explanation": "Measurement artifact", "discriminating_test": "Use an independent instrument.",
                     "expected_if_true": "The association disappears with the independent measurement."}],
                "failure_modes": ["Low precision", "Invalid measurement"],
                "test_plan": {"comparator": "Randomized control", "controls": ["Negative control"],
                              "metric": "Predeclared response difference", "dataset": "Authorized simulation",
                              "cloud_execution": "GitHub Actions CPU runner", "budget_cny": 0,
                              "deadline": "2026-10-07"},
                "scientific_value": {
                    "problem": "A synthetic association may reflect bias.", "affected_community": "Synthetic methods readers",
                    "why_unresolved": "The source does not identify causality.", "knowledge_gain": "Separate intervention from association.",
                    "practical_or_theoretical_relevance": "Clarify the bounded synthetic estimand.", "resource_fit": "CPU fixture only",
                    "remaining_uncertainty": "Fixture values are not science.", "source_anchors": [copy.deepcopy(self.evidence)]},
                "decision_test": {"observable": "Independent intervention outcome", "expected_if_hypothesis": "Positive response remains after randomization.",
                    "priority_reason": "Discriminate bias before expansion.", "continue_if": "Precision supports the registered effect.",
                    "revise_if": "The estimate remains imprecise.", "stop_if": "Measurement validity fails.",
                    "remaining_uncertainty": "Scientific relevance requires actual materials."},
                "novelty_status": "prior_art_search_required", "evidence_status": "hypothesis"}

    def register(self):
        from tests.test_innovation_screening import screening
        value = {"schema_version": "1.0", "scope": "specific_topics_after_direction_screening",
                 "direction_id": "screened-direction", "automatic_selection": False,
                 "hypotheses": [self.idea(f"H{i}") for i in range(3)],
                 "argument_plan": {"research_question": "Does the association survive intervention?",
                                   "allowed_claims": ["An association was reported."],
                                   "forbidden_claims": ["Causality has been established."],
                                   "planned_evidence": ["Preregistered intervention analysis"],
                                   "stopping_conditions": ["Data rights are unavailable."]}}
        for index, hypothesis in enumerate(value["hypotheses"]):
            hypothesis["hypothesis"] = f"Synthetic mechanism {index} changes the measured response."
        value["innovation_screening"] = screening(self.project, value["hypotheses"], self.evidence,
            question=value["argument_plan"]["research_question"])
        path = write_json(self.project / "program/hypothesis-register.json", value)
        return value, path

    def exploratory_register(self):
        value, path = self.register()
        screening = value["innovation_screening"]
        screening.update(mode="exploratory", comparisons=[])
        screening["generation"]["rounds"] = screening["generation"]["rounds"][:1]
        screening["evaluation"].update(criteria=[], ratings=[])
        write_json(path, value)
        return value, path

    def test_hypothesis_cli_checks_exploratory_draft_and_keeps_g1_strict(self):
        self.exploratory_register()
        root = self.project.parent
        (root / "projects").mkdir()
        self.project = self.project.rename(root / "projects/study")
        argv = ["research_candidates", "hypotheses", "--project", "study",
                "--spec", "program/hypothesis-register.json", "--output", "program/hypothesis-audit.json"]
        with patch.object(candidates, "ROOT", root), patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(candidates.main(), 0)
        report = json.loads((self.project / "program/hypothesis-audit.json").read_text())
        self.assertEqual(report["status"], "in_progress")
        self.assertFalse(report["for_gate"])
        self.assertTrue(any("still in progress" in error for error in candidates.validate_saved_register(self.project)))
        with patch.object(candidates, "ROOT", root), patch.object(sys, "argv", argv + ["--for-gate"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(candidates.main(), 2)
        report = json.loads((self.project / "program/hypothesis-audit.json").read_text())
        self.assertTrue(report["for_gate"])
        self.assertEqual(report["status"], "blocked")

    def test_api_refresh_preserves_exploration_without_granting_topic_approval(self):
        self.exploratory_register()
        with patch.object(api_orchestrator, "project_root", return_value=self.project):
            result = api_orchestrator.refresh_research_method_audits("study", "topic-intelligence")
        self.assertEqual(result["status"], "in_progress")
        self.assertTrue(result["pass"])
        self.assertFalse(result["scientific_validation"])
        errors = candidates.validate_saved_register(self.project)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("still in progress", errors[0])
        self.assertFalse((self.project / "state/run.json").exists())

    def test_native_exploration_refresh_does_not_build_confirmatory_design_or_reporting(self):
        from tests.test_research_exploration import NativeExplorationTests
        from scripts.research_artifacts import read, write
        fixture = NativeExplorationTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        contract = fixture.project / "papers/P01/paper-contract.json"
        value = read(contract)
        value["empirical_workflow"] = {"causal_design": True, "reporting": True}
        write(contract, value)
        before = {path: path.read_bytes() for path in fixture.project.rglob("*") if path.is_file()}
        for stage in ("experiment-design", "experiment-execution"):
            result = api_orchestrator.refresh_research_method_audits(fixture.slug, stage)
            self.assertEqual(result["status"], "formal_empirical_refresh_deferred")
            self.assertFalse(result["scientific_completion_verified"])
        self.assertEqual(before, {path: path.read_bytes() for path in fixture.project.rglob("*") if path.is_file()})
        fixture.plan["research_phase"] = "confirmatory"
        write(fixture.plan_path, fixture.plan)
        result = api_orchestrator.refresh_research_method_audits(fixture.slug, "experiment-design")
        self.assertNotEqual(result["status"], "formal_empirical_refresh_deferred")
        self.assertIn("P01", result["papers"])

    def test_legacy_hypothesis_audit_fields_do_not_waive_current_gate_checks(self):
        _, path = self.register()
        report = candidates.audit_register(self.project, path)
        del report["status"], report["for_gate"]
        write_json(self.project / "program/hypothesis-audit.json", report)
        self.assertEqual(candidates.validate_saved_register(self.project), [])
        self.exploratory_register()
        report = candidates.audit_register(self.project, path)
        del report["status"], report["for_gate"]
        write_json(self.project / "program/hypothesis-audit.json", report)
        self.assertTrue(any("still in progress" in error for error in candidates.validate_saved_register(self.project)))


    def test_scientific_value_and_decision_test_are_required(self):
        for field in ("scientific_value", "decision_test"):
            value, path = self.register()
            del value["hypotheses"][0][field]
            write_json(path, value)
            self.assertIn(field, "; ".join(candidates.audit_register(self.project, path)["errors"]))

    def test_importance_needs_current_source_not_own_plan_or_report(self):
        value, path = self.register()
        own = self.project / "program/own-importance.txt"
        own.parent.mkdir(parents=True, exist_ok=True)
        own.write_text("Own importance assertion.\n")
        value["hypotheses"][0]["scientific_value"]["source_anchors"] = [
            anchor(self.project, "program/own-importance.txt", "Own importance assertion.")]
        write_json(path, value)
        self.assertTrue(any("not its own plan" in e for e in candidates.audit_register(self.project, path)["errors"]))
        importance = self.project / "evidence/importance.txt"
        importance.write_text("The uncertainty matters for this synthetic community.\n")
        value["hypotheses"][0]["scientific_value"]["source_anchors"] = [
            anchor(self.project, "evidence/importance.txt", "The uncertainty matters for this synthetic community.")]
        write_json(path, value)
        self.assertTrue(candidates.audit_register(self.project, path)["pass"])
        importance.write_text("Changed source, invalid old importance anchor.\n")
        self.assertFalse(candidates.audit_register(self.project, path)["pass"])

    def test_nondiscriminating_prediction_or_identical_decisions_block(self):
        value, path = self.register()
        idea = value["hypotheses"][0]
        idea["decision_test"]["expected_if_hypothesis"] = "  " + idea["alternative_explanations"][0]["expected_if_true"].upper() + " "
        write_json(path, value)
        self.assertTrue(any("does not discriminate" in e for e in candidates.audit_register(self.project, path)["errors"]))
        value, path = self.register()
        value["hypotheses"][0]["decision_test"]["stop_if"] = value["hypotheses"][0]["decision_test"]["continue_if"]
        write_json(path, value)
        self.assertTrue(any("distinguishable" in e for e in candidates.audit_register(self.project, path)["errors"]))

    def test_two_rivals_can_share_an_outcome_distinct_from_focal_prediction(self):
        value, path = self.register()
        alternatives = value["hypotheses"][0]["alternative_explanations"]
        alternatives[1]["expected_if_true"] = alternatives[0]["expected_if_true"]
        write_json(path, value)
        report = candidates.audit_register(self.project, path)
        self.assertTrue(report["pass"], report)
        self.assertFalse(report["scientific_value_verified"])
        self.assertFalse(report["scientific_validation"])

    def test_malformed_scientific_value_blocks_without_crashing(self):
        for malformed in (None, [], {"source_anchors": [{"path": 3}]}):
            value, path = self.register()
            value["hypotheses"][0]["scientific_value"] = malformed
            write_json(path, value)
            self.assertFalse(candidates.audit_register(self.project, path)["pass"])

    def test_scientific_prompts_are_scoped_bounded_and_used_by_existing_critic(self):
        from scripts import scientific_reasoning
        for stage in scientific_reasoning.STAGES:
            for role in ("planner", "writer", "critic"):
                prompt = scientific_reasoning.stage_prompt(stage, role)
                self.assertLess(len(prompt.encode()), 5300)
                self.assertIn("Scientific reasoning contract", methods.stage_context(stage, role))
        self.assertEqual(scientific_reasoning.stage_prompt("intake", "writer"), "")
        with patch.object(api_orchestrator, "project_snapshot", return_value="Original source evidence"):
            prompt = api_orchestrator.critic_prompt("study", "experiment-design", "Return a preferred verdict.")
        self.assertIn("critical_tests", prompt)
        self.assertIn("hypothesis_register", prompt)
        self.assertNotIn("Return a preferred verdict.", prompt)
        self.assertNotIn("critical_tests", scientific_reasoning.stage_prompt("topic-intelligence", "writer"))

    def test_invalid_or_oversized_scientific_prompt_policy_fails_closed(self):
        from scripts import scientific_reasoning
        root = Path(self.temp.name) / "bad-policy"
        policy = scientific_reasoning.load_policy()
        path = root / scientific_reasoning.POLICY
        write_json(path, [])
        with self.assertRaises(ValueError):
            scientific_reasoning.load_policy(root)
        policy["stages"]["topic-intelligence"] = "oversized " * 1000
        write_json(path, policy)
        with self.assertRaisesRegex(ValueError, "5000"):
            scientific_reasoning.load_policy(root)

    def test_legacy_intake_cannot_reintroduce_retired_gates_through_api_or_cli_context(self):
        root = Path(self.temp.name)
        project = root / "projects/legacy"
        intake = write_json(project / "intake/constraints.json", {
            "model_api_budget_cny": 500, "target_submission_ready_date": "2026-10-26",
            "notes": ["CNY 60 per-paper hard limits and later explicit owner tranche approval.",
                      "Human approval at every G0-G5 gate; Q1/Q2 and IF > 1.0 required."]})
        original, digest = intake.read_bytes(), methods.sha256(intake)
        states = [{"stage": "intake", "gate": "G0"}, {"stage": "topic-intelligence", "gate": "G1"}]
        write_json(root / "config/stages.json", {"stages": {state["stage"]: {"gate": state["gate"]} for state in states}})
        with patch.object(api_orchestrator, "ROOT", root), patch.object(autopilot, "ROOT", root):
            prompts = []
            for state in states:
                snapshot = api_orchestrator.project_snapshot("legacy", stage=state["stage"], exclude_reviews=True)
                prompts.extend([api_orchestrator.planning_prompt("legacy", state["stage"], ""),
                                api_orchestrator.writer_prompt("legacy", state["stage"], ""),
                                api_orchestrator.critic_prompt("legacy", state["stage"], ""),
                                autopilot.planner_prompt("legacy", state, {}, ""),
                                autopilot.writer_prompt("legacy", state, {}, "", project / "plan.json"),
                                autopilot.critic_prompt("legacy", state)])
        self.assertIn(digest, snapshot)
        self.assertIn("CNY 60 per-paper hard limits", snapshot)
        for prompt in prompts:
            self.assertIn("CURRENT OPERATING POLICY overrides conflicting historical intake/template prose", prompt)
            self.assertIn("Only actual G1/G2 topic choices need human approval", prompt)
            self.assertIn("per-paper/per-call limits, tranche steps and paid opt-ins are superseded", prompt)
            self.assertIn("never scientific or packaging floors", prompt)
        self.assertEqual(intake.read_bytes(), original)

    def checklist(self):
        self.paper = self.project / "papers/P01"
        manuscript = self.paper / "manuscript/main.tex"
        manuscript.parent.mkdir(parents=True)
        manuscript.write_text("The association does not establish causality.\n", encoding="utf-8")
        ms_anchor = anchor(self.project, "papers/P01/manuscript/main.tex",
                           "The association does not establish causality.")
        value = {"schema_version": "1.0", "article_type": "computational",
                 "calibration_status": "NOT_CALIBRATED", "checks": [
                     {"criterion_id": row["id"], "criterion_source": "ARS and computational extension",
                      "judgement": "MEETS", "rationale": "Synthetic validator fixture only.",
                      "uncertainty": "This fixture is not a scientific judgement.",
                      "decision_bearing": True, "resolution_test": "Inspect the underlying primary evidence.",
                      "manuscript_anchors": [copy.deepcopy(ms_anchor)],
                      "evidence_anchors": [copy.deepcopy(self.evidence)]}
                     for row in review.criteria_for("computational")]}
        path = write_json(self.paper / "reviews/pre-submission-checklist.json", value)
        return value, path

    def test_hash_pinned_installation_detects_modified_reference(self):
        self.assertEqual(methods.installation_errors(), [])
        root = Path(self.temp.name) / "installation"
        for name in ("config/research-methods.json", "config/scientific-reasoning.json", "integrations/upstreams.lock.json",
                     "integrations/vendored-research-methods.json"):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(methods.ROOT / name, target)
        manifest = json.loads((root / "integrations/vendored-research-methods.json").read_text())
        catalog = json.loads((root / "config/research-methods.json").read_text())
        for row in manifest["files"] + catalog["modules"]:
            target = root / row["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(methods.ROOT / row["path"], target)
        self.assertEqual(methods.installation_errors(root), [])
        (root / catalog["modules"][0]["path"]).write_text("Modified methods.")
        self.assertTrue(any("modified adapted" in e for e in methods.installation_errors(root)))
        with self.assertRaises(ValueError):
            methods.load_vendored_module("../unreviewed.py")

    def test_pinned_text_hash_normalizes_checkout_newlines_but_detects_changes(self):
        path = Path(self.temp.name) / "method.txt"
        path.write_bytes(b"one\ntwo\n")
        expected = methods.pinned_text_sha256(path)
        path.write_bytes(b"one\r\ntwo\r\n")
        self.assertEqual(methods.pinned_text_sha256(path), expected)
        path.write_bytes(b"one\r\nchanged\r\n")
        self.assertNotEqual(methods.pinned_text_sha256(path), expected)

    def test_kdense_peer_review_is_primary_in_the_existing_native_critic(self):
        method = methods.peer_review_method()
        self.assertEqual(method["commit"], "65d6e786832e2c52832713117bbbf5096b56f77f")
        self.assertEqual(method["sha256"], methods.pinned_text_sha256(methods.ROOT / method["path"]))
        self.assertEqual(method["selected_sections"], [1, 2, 4, 5, 6, 8, 9])
        write_json(self.project / "state/run.json", {"active_paper": "P01"})
        with patch("scripts.model_runtime.call", side_effect=AssertionError("No extra model pass")), \
             patch.object(api_orchestrator, "project_root", return_value=self.project), \
             patch.object(api_orchestrator, "project_snapshot", return_value="Original source view"), \
             patch.object(api_orchestrator, "figure_reference_context", return_value=""):
            prompt = methods.stage_context("writing-and-review", "critic", project=self.project)
            for active_prompt in (api_orchestrator.critic_prompt("study", "writing-and-review", ""),
                                  autopilot.critic_prompt("study", {"stage": "writing-and-review"})):
                self.assertIn(method["guidance"], active_prompt)
        self.assertIn("PRIMARY PEER-REVIEW METHOD: K-Dense", prompt)
        self.assertIn(method["guidance"], prompt)
        self.assertIn("Analysis–design alignment and assumptions", prompt)
        self.assertIn("missing material remains unassessed", prompt)
        self.assertNotIn("READY_FOR_LOCAL_REVIEW", prompt)
        self.assertNotIn("python3 scripts/validate_review_intake.py", prompt)
        self.assertIn("Public AI-use statements remain author-editable", prompt)
        self.assertIn("without requiring every comparison in the manuscript", prompt)
        _, _ = self.checklist()
        report = review.audit(self.paper)
        self.assertEqual(report["primary_method"]["sha256"], method["sha256"])
        self.assertNotIn("guidance", report["primary_method"])
        self.assertFalse(report["scientific_validation"])

    def test_peer_review_views_are_bounded_and_changed_source_is_rejected(self):
        methods_root = Path(self.temp.name) / "methods"
        source = methods.peer_review_method()
        target = methods_root / source["path"]
        target.parent.mkdir(parents=True)
        shutil.copyfile(methods.ROOT / source["path"], target)
        write_json(methods_root / "integrations/vendored-research-methods.json",
                   {"files": [{key: value for key, value in source.items()
                               if key not in {"source_id", "selected_sections", "guidance"}}]})
        subset = methods.peer_review_context(methods_root, sections=(4, 5))
        self.assertIn("Map claims to evidence", subset)
        self.assertNotIn("### 8. Review figures", subset)
        target.write_text(target.read_text() + "Changed upstream source.\n")
        with self.assertRaisesRegex(ValueError, "has changed"):
            methods.peer_review_context(methods_root)

    def test_line_locator_cannot_be_invented_or_point_elsewhere(self):
        self.assertEqual(candidates.anchor_errors(self.project, self.evidence), [])
        wrong = {**self.evidence, "locator": "L2"}
        self.assertTrue(any("unconfirmed_anchor" in e for e in candidates.anchor_errors(self.project, wrong)))
        wrong["locator"] = "line:9999"
        self.assertTrue(candidates.anchor_errors(self.project, wrong))
        wrong["locator"] = "L9999"
        self.assertTrue(candidates.anchor_errors(self.project, wrong))

    def test_valid_register_never_grants_novelty_or_approves_a_gate(self):
        _, path = self.register()
        report = candidates.audit_register(self.project, path)
        self.assertTrue(report["pass"])
        self.assertFalse(report["novelty_granted"])
        self.assertFalse(report["scientific_validation"])
        write_json(self.project / "program/hypothesis-audit.json", report)
        self.assertEqual(candidates.validate_saved_register(self.project), [])
        report["human_review_required"] = False
        write_json(self.project / "program/hypothesis-audit.json", report)
        self.assertTrue(candidates.validate_saved_register(self.project))

    def test_register_fails_on_stale_source_or_claimed_result(self):
        value, path = self.register()
        self.source.write_text("The earlier source has been revised.\n")
        self.assertFalse(candidates.audit_register(self.project, path)["pass"])
        value["hypotheses"][0]["evidence_status"] = "observed_result"
        value["hypotheses"][0]["novelty_status"] = "proven_novel"
        write_json(path, value)
        errors = candidates.audit_register(self.project, path)["errors"]
        self.assertTrue(any("stale source" in e for e in errors))
        self.assertTrue(any("must be hypothesis" in e for e in errors))
        self.assertTrue(any("prior_art_search_required" in e for e in errors))

    def test_competing_explanations_and_falsification_are_required(self):
        value, path = self.register()
        value["hypotheses"][0]["alternative_explanations"][1]["explanation"] = "  CONFOUNDING "
        value["hypotheses"][1]["falsifying_result"] = ""
        value["hypotheses"][2]["test_plan"]["budget_cny"] = float("nan")
        write_json(path, value)
        errors = candidates.audit_register(self.project, path)["errors"]
        self.assertTrue(any("repeats" in e for e in errors))
        self.assertTrue(any("falsifying_result" in e for e in errors))
        self.assertTrue(any("finite" in e for e in errors))

    def test_malformed_register_is_a_failed_report(self):
        value, path = self.register()
        value["hypotheses"][0]["hypothesis_id"] = {}
        value["hypotheses"][1]["alternative_explanations"][0]["explanation"] = []
        value["argument_plan"]["allowed_claims"] = [{}]
        write_json(path, value)
        self.assertFalse(candidates.audit_register(self.project, path)["pass"])

    def test_partial_card_cannot_assess_unseen_methods_or_upgrade_scope(self):
        value = {"schema_version": "1.0", "paper_id": "synthetic-source",
                 "research_question": "Is X associated with Y?", "claimed_contribution": "Association only.",
                 "source_scope": "abstract", "methods_assessed": False, "experiments_assessed": False,
                 "claim_evidence": [{"claim": "Association", "boundary": "Causality unassessed",
                                    "attribution": "author_statement", "anchor": self.evidence}],
                 "candidate_ideas": []}
        path = write_json(self.project / "evidence/paper-cards/source.json", value)
        self.assertTrue(candidates.audit_card(self.project, path)["pass"])
        value["methods_assessed"] = True
        write_json(path, value)
        self.assertFalse(candidates.audit_card(self.project, path)["pass"])
        value["source_scope"] = "full_text"
        write_json(path, value)
        self.assertTrue(any("source_scope_unconfirmed" in e for e in candidates.audit_card(self.project, path)["errors"]))

    def test_scope_record_is_bound_to_source_and_does_not_certify_reading(self):
        path = source_scope.record(self.project, "evidence/source.txt", "full_text", "Test human")
        primary = {"path": "evidence/source.txt", "sha256": methods.sha256(self.source)}
        receipt = {"path": path.relative_to(self.project).as_posix(), "sha256": methods.sha256(path)}
        self.assertEqual(source_scope.verify(self.project, primary, receipt, "full_text"), [])
        self.assertEqual(json.loads(path.read_text())["human_read_scope"], "not_declared")
        value = json.loads(path.read_text())
        value["human_read_scope"] = "full_text"
        write_json(path, value)
        receipt["sha256"] = methods.sha256(path)
        self.assertTrue(source_scope.verify(self.project, primary, receipt, "full_text"))

    def test_confirmed_card_remains_a_reading_aid(self):
        scope_path = source_scope.record(self.project, "evidence/source.txt", "full_text", "Test human")
        value = {"schema_version": "1.0", "paper_id": "synthetic-source",
                 "research_question": "Association?", "claimed_contribution": "Association only",
                 "source_scope": "full_text", "methods_assessed": True, "experiments_assessed": False,
                 "primary_source": {"path": "evidence/source.txt", "sha256": methods.sha256(self.source)},
                 "scope_record": {"path": scope_path.relative_to(self.project).as_posix(),
                                  "sha256": methods.sha256(scope_path)},
                 "claim_evidence": [{"claim": "Association", "boundary": "No causal inference",
                                    "attribution": "author_statement", "anchor": self.evidence}],
                 "candidate_ideas": []}
        path = write_json(self.project / "evidence/paper-cards/source.json", value)
        result = candidates.audit_card(self.project, path)
        self.assertTrue(result["pass"])
        self.assertTrue(result["provided_scope_confirmed"])
        self.assertFalse(result["scientific_validation"])
        self.assertEqual(result["human_read_scope"], "not_declared")
        self.source.write_text(self.source.read_text() + "Changed supplied material.\n")
        self.assertFalse(candidates.audit_card(self.project, path)["pass"])

    def test_g5_refresh_blocks_missing_paper_facts_and_preserves_no_approval(self):
        _, _ = self.checklist()
        with patch.object(api_orchestrator, "project_root", return_value=self.project), \
             patch.object(api_orchestrator, "active_paper", return_value="P01"):
            result = api_orchestrator.refresh_research_method_audits("study", "writing-and-review")
        self.assertFalse(result["pass"])
        self.assertEqual(result["paper_facts"]["status"], "input_missing")
        self.assertEqual(result["writing_phase"],"scientific")
        self.assertNotIn("figure_layout",result)
        self.assertFalse((self.paper/"reviews/pre-submission-review.json").exists())
        self.assertFalse((self.project / "state/run.json").exists())

    def test_review_all_criteria_and_hashes_are_replayed(self):
        _, _ = self.checklist()
        result = review.audit(self.paper)
        self.assertTrue(result["pass"])
        self.assertEqual(result["criteria_count"], 14)
        self.assertFalse(result["scientific_validation"])
        path = write_json(self.paper / "reviews/pre-submission-review.json", result)
        self.assertEqual(review.validate_saved_report(self.paper), [])
        value = json.loads(path.read_text())
        value["criteria_count"] = 0
        write_json(path, value)
        self.assertTrue(review.validate_saved_report(self.paper))

    def test_review_missing_or_unresolved_criteria_cannot_pass(self):
        value, path = self.checklist()
        value["checks"].pop()
        value["checks"][0]["judgement"] = "PARTLY_MEETS"
        value["checks"][0]["decision_bearing"] = False
        write_json(path, value)
        result = review.audit(self.paper)
        self.assertFalse(result["pass"])
        self.assertIn("originality", result["unresolved_criteria"])
        self.assertTrue(any("unassessed required" in e for e in result["errors"]))

    def test_numeric_scoring_and_skipped_universal_criteria_are_rejected(self):
        value, path = self.checklist()
        value["overall_score"] = 9.8
        value["checks"][0].update(judgement="NOT_APPLICABLE", non_applicability_reason="Author preference.")
        write_json(path, value)
        errors = review.audit(self.paper)["errors"]
        self.assertTrue(any("acceptance probability" in e for e in errors))
        self.assertTrue(any("cannot be skipped" in e for e in errors))

    def test_review_rejects_unused_draft_and_wrong_line(self):
        value, path = self.checklist()
        unused = self.paper / "manuscript/unused.tex"
        unused.write_text("The association does not establish causality.\n", encoding="utf-8")
        value["checks"][0]["manuscript_anchors"] = [anchor(
            self.project, "papers/P01/manuscript/unused.tex", "The association does not establish causality.")]
        value["checks"][1]["evidence_anchors"][0]["locator"] = "L2"
        write_json(path, value)
        errors = review.audit(self.paper)["errors"]
        self.assertTrue(any("canonical manuscript" in e for e in errors))
        self.assertTrue(any("unconfirmed_anchor" in e for e in errors))

    def test_tex_include_and_docx_paragraph_anchors_are_supported(self):
        value, path = self.checklist()
        child = self.paper / "manuscript/results.tex"
        child.write_text("Included results remain bounded.\n", encoding="utf-8")
        (self.paper / "manuscript/main.tex").write_text("\\input{results}\n")
        for check in value["checks"]:
            check["manuscript_anchors"] = [anchor(self.project, "papers/P01/manuscript/results.tex",
                                                 "Included results remain bounded.")]
        write_json(path, value)
        self.assertTrue(review.audit(self.paper)["pass"])
        from docx import Document
        (self.paper / "manuscript/main.tex").unlink()
        doc = Document()
        doc.add_paragraph("The association does not establish causality.")
        doc.save(self.paper / "manuscript/main.docx")
        for check in value["checks"]:
            check["manuscript_anchors"] = [anchor(self.project, "papers/P01/manuscript/main.docx",
                "The association does not establish causality.", "paragraph 1")]
        write_json(path, value)
        self.assertTrue(review.audit(self.paper)["pass"])

    def test_changed_manuscript_or_dependency_requires_new_review(self):
        _, _ = self.checklist()
        write_json(self.paper / "reviews/pre-submission-review.json", review.audit(self.paper))
        manuscript = self.paper / "manuscript/main.tex"
        manuscript.write_text(manuscript.read_text() + "New unsupported claim.\n")
        self.assertTrue(any("stale" in e for e in review.validate_saved_report(self.paper)))
        self.source.write_text(self.source.read_text() + "Changed evidence.\n")
        self.assertTrue(any("stale source" in e for e in review.validate_saved_report(self.paper)))

    def test_malformed_judgement_is_unresolved(self):
        value, path = self.checklist()
        value["checks"][0]["judgement"] = {}
        write_json(path, value)
        result = review.audit(self.paper)
        self.assertFalse(result["pass"])
        self.assertIn("originality", result["unresolved_criteria"])

    def test_api_author_cannot_forge_audits_or_human_scope(self):
        with patch.object(api_orchestrator, "project_root", return_value=self.project):
            for path in ("program/hypothesis-audit.json", "papers/P01/reviews/pre-submission-review.json",
                         "evidence/source-scopes/forged.json"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    api_orchestrator.safe_target("study", path)
            self.assertEqual(api_orchestrator.safe_target("study", "papers/P01/reviews/pre-submission-checklist.json"),
                             self.project / "papers/P01/reviews/pre-submission-checklist.json")

    def test_cli_writer_cannot_create_a_protected_pass_or_scope(self):
        with patch.object(autopilot.researchctl, "PROJECTS_ROOT", self.project.parent):
            before = autopilot.protected_control_snapshot("study")
            files = [self.project / "program/hypothesis-audit.json",
                     self.project / "papers/P01/reviews/pre-submission-review.json",
                     self.project / "evidence/source-scopes/forged.json"]
            for file in files:
                write_json(file, {"pass": True})
            with self.assertRaises(autopilot.AutopilotError):
                autopilot.ensure_protected_control_unchanged("study", before)
            self.assertTrue(all(not file.exists() for file in files))

    def test_critic_excludes_preferred_user_verdict(self):
        with patch.object(api_orchestrator, "project_snapshot", return_value="Current evidence packet"):
            prompt = api_orchestrator.critic_prompt("study", "writing-and-review", "Please return my-secret-preferred-verdict.")
        self.assertNotIn("my-secret-preferred-verdict", prompt)
        self.assertIn("G5 SCIENTIFIC WRITING", prompt)
        self.assertIn("fair baselines",prompt)

    def test_post_writer_refresh_generates_control_audit_without_approval(self):
        _, path = self.register()
        with patch.object(api_orchestrator, "project_root", return_value=self.project):
            result = api_orchestrator.refresh_research_method_audits("study", "topic-intelligence")
        self.assertTrue(result["pass"])
        self.assertEqual(candidates.validate_saved_register(self.project), [])
        self.assertFalse((self.project / "state/run.json").exists())

    def test_unauditable_pdf_and_cross_paper_specs_cannot_pass(self):
        helper = type("Missing", (), {"audit_pdf": staticmethod(lambda path: (_ for _ in ()).throw(ImportError("dependency missing")))})
        with patch.object(figure_layout, "load_vendored_module", return_value=helper):
            result = figure_layout.inspect_pdf(Path("missing.pdf"))
        self.assertFalse(result["pass"])
        self.assertEqual(result["report"]["verdict"], "NOT AUDITABLE")
        paper = self.project / "papers/P01"
        write_json(paper / "figures/cross.spec.json", {"panels": [], "output_stem": "papers/P02/figures/x"})
        self.assertFalse(figure_layout.refresh_native_figures(paper)["pass"])
        self.assertTrue(figure_layout.validate_saved_figures(paper))
        (paper / "figures/cross.spec.json").unlink()
        write_json(paper / "figures/unrendered.spec.json", {
            "schema_version": "1.0", "output_stem": "papers/P01/figures/x", "panels": [], "style": "invalid"})
        self.assertFalse(figure_layout.refresh_native_figures(paper)["pass"])
        self.assertTrue(figure_layout.validate_saved_figures(paper))
        write_json(paper / "figures/unrendered.spec.json", {})
        self.assertFalse(figure_layout.refresh_native_figures(paper)["pass"])
        self.assertTrue(figure_layout.validate_saved_figures(paper))
        self.assertTrue(figure_layout.validate_saved_figures(paper))
        write_json(paper / "figures/unrendered.spec.json", {"output_stem": "papers/P01/figures/x"})
        self.assertFalse(figure_layout.refresh_native_figures(paper)["pass"])
        self.assertTrue(any("unrendered.spec.json" in e for e in figure_layout.validate_saved_figures(paper)))
