"""Synthetic proposal records never become proof of novelty or independence."""
import copy
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import innovation_screening as innovation
from scripts.research_artifacts import sha, write


QUESTION = "Does the association survive intervention?"


def screening(project, hypotheses, evidence, question=QUESTION):
    """Reusable complete fixture. Every process/rating here is explicitly synthetic."""
    ids = [h["hypothesis_id"] for h in hypotheses]
    rounds = []
    for number, stage in enumerate(("independent", "post_evidence"), 1):
        row = {"round_id": "round-" + str(number), "stage": stage, "candidate_ids": list(ids)}
        relative = "program/innovation-round-" + str(number) + ".json"
        write(project / relative, {**row, "ideas": [{"hypothesis_id": h["hypothesis_id"], "statement": h["hypothesis"], "prediction": h["prediction"], "precise_difference": h["precise_difference"]} for h in hypotheses],
            "evidence_inputs": [{"path": evidence["path"], "sha256": evidence["sha256"]}] if stage == "post_evidence" else [],
            "evidence_limits": ["Synthetic source only; no actual literature search."],
            "notice": "Synthetic declaration only; no human participation or model call occurred."})
        rounds.append({**row, "record_binding": {"path": relative, "sha256": sha(project / relative)}})
    candidates = [{"hypothesis_id": identity, "mechanism": "Candidate mechanism " + identity,
        "assumption_ids": ["shared-measurement"], "evidence_status": "search_incomplete",
        "evidence_for": [copy.deepcopy(evidence)], "evidence_against": [],
        "evidence_gaps": [{"gap_id": "gap-" + identity, "question": "Is the effect attributable to this mechanism?",
            "resolution_test": "Inspect an independently measured intervention.", "next_action": "Plan one bounded discriminating test."}],
        "search_limits": ["Only synthetic source evidence is present."],
        "prior_exposure": {"status": "unknown", "observed_inputs": [], "details": "Synthetic fixture has no real research history.",
            "analysis_phase": "exploratory", "future_confirmatory_evidence": "Use new or demonstrably untouched observations after approval."},
        "adversarial_checks": [{"challenge": "Could measurement artifact explain the apparent effect?", "response": "Retain the alternative pending an orthogonal measurement.",
            "next_test": "A proposed independent measurement, not an executed experiment.", "residual_uncertainty": "No actual scientific validation."}],
        "disposition": {"status": "retain", "rationale": "Retain only as a synthetic proposal for validation.", "next_action": "Review actual evidence before protocol design.",
            "revisit_when": "Actual materials contradict the mechanism or change feasibility.", "owner": "synthetic-fixture-owner"},
        "gate_status": {"feasibility": "not_assessed", "rigor": "not_assessed", "ethics": "not_assessed"}} for identity in ids]
    comparisons = [{"candidate_ids": [left, right], "mechanism_difference": "Different synthetic mechanisms require semantic review.",
        "prediction_difference": "Candidate-specific intervention contrast remains proposed.", "distinguishing_test": "Measure a discriminating observable under comparable conditions.",
        "shared_assumption_ids": ["shared-measurement"], "common_failure_risk": "Invalid shared measurement could invalidate both candidates; verify it first."}
        for index, left in enumerate(ids) for right in ids[index + 1:]]
    return {"schema_version": "1.0", "scope": {"focal_question": question, "doctoral_question": "One synthetic doctoral question only.",
            "in_scope": ["Mechanisms within the same synthetic thesis."], "out_of_scope": ["Unrelated doctoral topics."],
            "constraints": [{"statement": "Cloud-only execution with existing gates.", "status": "real"}]},
        "generation": {"method": "AI-assisted declared ideation", "reason": "Exercise source-bound records without representing real participants.",
            "contributors": [{"contributor_id": "fixture-model", "kind": "model", "tool_and_purpose": "Synthetic fixture; no actual model call."}],
            "represented_perspectives": ["Synthetic methodological viewpoint"], "missing_perspectives": ["Real domain participants"],
            "independence": "unknown", "prior_examples": [], "deviations": ["AI-only synthetic fixture does not prove human-first or independent generation."],
            "rounds": rounds, "clustering_events": []},
        "assumptions": [{"assumption_id": "shared-measurement", "statement": "Measurement distinguishes the proposed mechanisms.",
            "category": "measurement", "status": "untested", "candidate_ids": list(ids), "source_anchors": [],
            "test_or_check": "Compare an orthogonal measurement before expensive execution.", "failure_consequence": "All candidates relying on this instrument may fail together."}],
        "candidates": candidates, "comparisons": comparisons,
        "evaluation": {"mode": "narrative", "criteria": [{"criterion_id": "information_gain", "definition": "Potential to distinguish the competing mechanisms.",
            "direction": "higher", "minimum": 1, "maximum": 5, "anchors": ["No discrimination", "Partial discrimination", "Clear independent test"], "weight": None}],
            "ratings": [{"rating_id": "rating-" + identity, "supersedes": None, "hypothesis_id": identity, "criterion_id": "information_gain", "rater_id": "fixture-rater",
                "score": None, "low": None, "high": None, "rationale": "Abstain: actual scientific materials are absent.", "source_anchors": []} for identity in ids],
            "dissent": ["No domain consensus is supplied by a fixture."], "reconciliation": [],
            "method_limits": "No score, independence, scientific validity or selection is established.", "matrix": None}}


class InnovationScreeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.cloud = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"})
        self.cloud.start()
        self.addCleanup(self.cloud.stop)
        write(self.project / "evidence/source.json", {"observation": "Synthetic source only."})
        source = self.project / "evidence/source.txt"
        source.write_text("Synthetic source only.\n", encoding="utf-8")
        self.evidence = {"path": "evidence/source.txt", "sha256": sha(source), "locator": "L1", "excerpt": "Synthetic source only."}
        self.hypotheses = [{"hypothesis_id": "H" + str(i), "hypothesis": "Mechanism " + str(i),
            "prediction": "Prediction " + str(i), "precise_difference": "Intervention contrast " + str(i)} for i in range(3)]
        self.register = {"hypotheses": self.hypotheses, "argument_plan": {"research_question": QUESTION},
            "innovation_screening": screening(self.project, self.hypotheses, self.evidence)}

    def errors(self):
        return innovation.validate(self.project, self.register)

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}

    def test_complete_ai_only_proposals_and_explicit_abstentions_pass_without_writes_or_scientific_claims(self):
        before = self.snapshot()
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.register["innovation_screening"]["generation"]["independence"], "unknown")
        self.assertTrue(all(r["score"] is None for r in self.register["innovation_screening"]["evaluation"]["ratings"]))

    def test_numbered_copies_cannot_impersonate_distinct_candidates(self):
        self.hypotheses[1].update({key: "  " + self.hypotheses[0][key].upper() + "  " for key in ("hypothesis", "prediction", "precise_difference")})
        self.assertIn("exact same", "; ".join(self.errors()))

    def test_every_pair_and_shared_dependency_must_be_visible_but_shared_background_is_allowed(self):
        value = self.register["innovation_screening"]
        self.assertEqual(self.errors(), [])
        saved = value["comparisons"].pop()
        self.assertIn("every candidate pair", "; ".join(self.errors()))
        value["comparisons"].append(saved)
        saved["shared_assumption_ids"] = []
        self.assertIn("every declared common dependency", "; ".join(self.errors()))

    def test_assumption_references_and_current_evidence_are_required(self):
        value = self.register["innovation_screening"]
        value["assumptions"][0]["candidate_ids"].pop()
        self.assertIn("both directions", "; ".join(self.errors()))
        value["assumptions"][0]["candidate_ids"].append("H2")
        value["assumptions"][0].update(status="support_located", source_anchors=[])
        self.assertIn("actual source", "; ".join(self.errors()))
        value["assumptions"][0]["source_anchors"] = [self.evidence]
        self.assertEqual(self.errors(), [])
        (self.project / "evidence/source.txt").write_text("Changed source.\n", encoding="utf-8")
        self.assertIn("stale", "; ".join(self.errors()))

    def test_seen_or_unknown_outcomes_cannot_be_retroactively_prospective(self):
        exposure = self.register["innovation_screening"]["candidates"][0]["prior_exposure"]
        exposure["analysis_phase"] = "prospective"
        self.assertIn("must remain exploratory", "; ".join(self.errors()))
        exposure.update(status="seen", analysis_phase="exploratory", observed_inputs=[])
        self.assertTrue(self.errors())
        exposure["observed_inputs"] = [{"path": "evidence/source.txt", "sha256": sha(self.project / "evidence/source.txt")}]
        self.assertEqual(self.errors(), [])
        exposure["status"] = "none"
        self.assertIn("contradicts observed", "; ".join(self.errors()))

    def test_original_rounds_reopening_and_deviations_remain_replayable(self):
        generation = self.register["innovation_screening"]["generation"]
        generation["deviations"] = []
        self.assertIn("truthful deviation", "; ".join(self.errors()))
        generation["independence"] = "declared"
        self.assertIn("AI-only", "; ".join(self.errors()))
        generation["independence"] = "unknown"
        generation["deviations"] = ["No independent participants were present."]
        self.assertEqual(self.errors(), [])
        binding = generation["rounds"][0]["record_binding"]
        (self.project / binding["path"]).write_text("{}", encoding="utf-8")
        self.assertIn("stale bound", "; ".join(self.errors()))

    def test_every_candidate_and_current_revision_have_retained_round_content(self):
        generation = self.register["innovation_screening"]["generation"]
        for row in generation["rounds"]:
            source = self.project / row["record_binding"]["path"]
            value = json.loads(source.read_text())
            row["candidate_ids"] = ["H0"]
            value["candidate_ids"] = ["H0"]
            value["ideas"] = [value["ideas"][0]]
            write(source, value)
            row["record_binding"]["sha256"] = sha(source)
        self.assertIn("every current candidate", "; ".join(self.errors()))
        self.register["innovation_screening"] = screening(self.project, self.hypotheses, self.evidence)
        self.hypotheses[1]["prediction"] = "Changed prediction after the retained records."
        self.assertIn("latest retained round", "; ".join(self.errors()))

    def test_candidate_dispositions_and_hard_gate_cannot_be_hidden_by_scores(self):
        row = self.register["innovation_screening"]["candidates"][0]
        row["gate_status"]["feasibility"] = "blocked"
        self.assertIn("cannot be offset", "; ".join(self.errors()))
        row["disposition"]["status"] = "defer"
        self.assertEqual(self.errors(), [])
        row["disposition"]["revisit_when"] = ""
        self.assertIn("revisit_when", "; ".join(self.errors()))

    def test_raw_and_revised_ratings_keep_abstentions_and_unknown_bounds(self):
        evaluation = self.register["innovation_screening"]["evaluation"]
        revised = {**evaluation["ratings"][0], "rating_id": "revision-1", "supersedes": "rating-H0", "score": 3}
        evaluation["ratings"].append(revised)
        self.assertEqual(self.errors(), [])
        self.assertIsNone(evaluation["ratings"][0]["score"])
        revised["low"] = 2
        self.assertIn("both be supplied", "; ".join(self.errors()))
        revised["high"] = 4
        self.assertEqual(self.errors(), [])
        revised["supersedes"] = "rating-H1"
        self.assertIn("current predecessor", "; ".join(self.errors()))

    def test_missing_or_malformed_sections_block_without_crashing(self):
        original = copy.deepcopy(self.register)
        for key in ("scope", "generation", "assumptions", "candidates", "comparisons", "evaluation"):
            self.register = copy.deepcopy(original)
            self.register["innovation_screening"].pop(key)
            with self.subTest(key=key):
                self.assertTrue(self.errors())
        self.register = original
        self.register["innovation_screening"]["candidates"][0]["hypothesis_id"] = []
        self.assertTrue(self.errors())

    def test_nontext_hypothesis_and_nonobject_retained_round_fail_as_validation_errors(self):
        original = self.hypotheses[0]["hypothesis"]
        for value in (None, 1, {}, []):
            self.hypotheses[0]["hypothesis"] = value
            with self.subTest(value=value):
                self.assertIn("bounded concrete text", "; ".join(self.errors()))
        self.hypotheses[0]["hypothesis"] = original
        binding = self.register["innovation_screening"]["generation"]["rounds"][0]["record_binding"]
        source = self.project / binding["path"]
        for value in (None, [], 1):
            source.write_text(json.dumps(value), encoding="utf-8")
            binding["sha256"] = sha(source)
            with self.subTest(value=value):
                self.assertIn("must be an object", "; ".join(self.errors()))

    def make_matrix(self):
        evaluation = self.register["innovation_screening"]["evaluation"]
        evaluation["mode"] = "weighted_matrix"
        evaluation["criteria"][0]["weight"] = 1
        for index, rating in enumerate(evaluation["ratings"]):
            rating.update(score=index + 2, rationale="Synthetic criterion rating only.")
        criterion = evaluation["criteria"][0]
        config = self.project / "program/criteria.json"
        write(config, {"schema_version": "1.0", "criteria": [{"name": criterion["criterion_id"], "description": criterion["definition"],
            "weight": 1, "direction": "higher", "minimum": 1, "maximum": 5}]})
        scores = self.project / "program/scores.csv"
        with scores.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["idea_id", "information_gain", "information_gain_low", "information_gain_high", "qualitative_review", "uncertainties"])
            writer.writeheader()
            for rating in evaluation["ratings"]:
                writer.writerow({"idea_id": rating["hypothesis_id"], "information_gain": rating["score"],
                    "information_gain_low": "", "information_gain_high": "", "qualitative_review": "Synthetic rating", "uncertainties": "Bounds unassessed"})
        result = self.project / "program/matrix.json"
        completed = subprocess.run([sys.executable, str(innovation.ROOT / innovation.SOURCE / "evaluate_matrix.py"), str(scores), "--config", str(config), "--weight-delta", "0.1"],
            capture_output=True, text=True, timeout=30, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result.write_text(completed.stdout, encoding="utf-8")
        evaluation["matrix"] = {"criteria_file": {"path": "program/criteria.json", "sha256": sha(config)},
            "scores_file": {"path": "program/scores.csv", "sha256": sha(scores)}, "result_file": {"path": "program/matrix.json", "sha256": sha(result)},
            "weight_delta": .1, "rater_id": "fixture-rater", "deferred_candidate_ids": []}
        return evaluation, result

    def test_actual_pinned_matrix_replay_preserves_unassessed_bounds_and_never_selects(self):
        evaluation, result = self.make_matrix()
        before = self.snapshot()
        self.assertEqual(self.errors(), [])
        self.assertEqual(self.snapshot(), before)
        output = json.loads(result.read_text())
        self.assertIsNone(output["decision"])
        self.assertIsNone(evaluation["ratings"][0]["low"])
        # Unknown bounds remain explicit in the current upstream helper result.
        self.assertTrue(all(not row["criteria"]["information_gain"]["bounds_supplied"] for row in output["results"]))
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}):
            self.assertTrue(self.errors())

    def test_matrix_cannot_fabricate_known_bounds_impute_abstentions_or_reuse_changed_output(self):
        evaluation, result = self.make_matrix()
        evaluation["ratings"][0]["score"] = None
        self.assertIn("deferral", "; ".join(self.errors()))
        evaluation["ratings"][0]["score"] = 2
        scores = self.project / evaluation["matrix"]["scores_file"]["path"]
        before = scores.read_bytes()
        with scores.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            names, rows = reader.fieldnames, list(reader)
        rows[0].update(information_gain_low="2", information_gain_high="2")
        with scores.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=names)
            writer.writeheader()
            writer.writerows(rows)
        evaluation["matrix"]["scores_file"]["sha256"] = sha(scores)
        self.assertIn("point interval", "; ".join(self.errors()))
        scores.write_bytes(before)
        evaluation["matrix"]["scores_file"]["sha256"] = sha(scores)
        actual = json.loads(result.read_text())
        actual["decision"] = "H2"
        write(result, actual)
        evaluation["matrix"]["result_file"]["sha256"] = sha(result)
        self.assertIn("selects a winner", "; ".join(self.errors()))

    def test_explicit_complete_case_deferral_retains_original_abstention(self):
        evaluation, result = self.make_matrix()
        evaluation["ratings"][0]["score"] = None
        evaluation["matrix"]["deferred_candidate_ids"] = ["H0"]
        scores = self.project / evaluation["matrix"]["scores_file"]["path"]
        with scores.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            names, rows = reader.fieldnames, list(reader)
        with scores.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=names)
            writer.writeheader()
            writer.writerows(row for row in rows if row["idea_id"] != "H0")
        completed = subprocess.run([sys.executable, str(innovation.ROOT / innovation.SOURCE / "evaluate_matrix.py"), str(scores),
            "--config", str(self.project / "program/criteria.json"), "--weight-delta", "0.1"],
            capture_output=True, text=True, timeout=30, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result.write_text(completed.stdout, encoding="utf-8")
        evaluation["matrix"]["scores_file"]["sha256"] = sha(scores)
        evaluation["matrix"]["result_file"]["sha256"] = sha(result)
        self.assertEqual(self.errors(), [])
        self.assertIsNone(evaluation["ratings"][0]["score"])
        self.assertEqual({row["idea_id"] for row in json.loads(result.read_text())["results"]}, {"H1", "H2"})

    def test_nonobject_matrix_configuration_and_truncated_csv_are_controlled_errors(self):
        evaluation, _ = self.make_matrix()
        binding = evaluation["matrix"]["criteria_file"]
        config = self.project / binding["path"]
        original = config.read_bytes()
        for value in (None, [], 1):
            config.write_text(json.dumps(value), encoding="utf-8")
            binding["sha256"] = sha(config)
            with self.subTest(value=value):
                self.assertIn("must be an object", "; ".join(self.errors()))
        config.write_bytes(original)
        binding["sha256"] = sha(config)
        scores = self.project / evaluation["matrix"]["scores_file"]["path"]
        scores.write_text("idea_id,information_gain,information_gain_low,information_gain_high,qualitative_review,uncertainties\nH0,2\nH1,3\nH2,4\n", encoding="utf-8")
        evaluation["matrix"]["scores_file"]["sha256"] = sha(scores)
        self.assertIn("truncated", "; ".join(self.errors()))


if __name__ == "__main__":
    unittest.main()
