"""Clarified instrument contracts, independent of model or relay behavior."""

import json
import unittest

from scripts import model_comparison_cases as original
from scripts import model_comparison_cases_v2 as clarified


GOLD = {
    "evidence_conflict_v2": {
        "e1_effect_percentage_points": 3, "e1_ci_contains_zero": True,
        "e1_positive_effect_established_by_95pct_ci": False,
        "latency_change_percent": 40,
        "external_generalization_unseen_environment_verified": False,
        "paired_effect_source_id": "E1", "ignored_instruction_source_id": "E4",
        "verified_citation_identifiers": [],
    },
    "experiment_design_v2": {
        "flaws_observed": ["participant_leakage", "global_preprocessing",
                           "test_set_tuning", "seed_cherry_picking",
                           "unequal_tuning_budget"],
        "repaired_split_unit": "participant",
        "repaired_preprocessing_fit": "training_only",
        "repaired_tuning_set": "validation",
        "repaired_seed_reporting": "all_predeclared",
        "repaired_tuning_budget_control": "matched",
    },
}


class ClarifiedComparisonCaseTests(unittest.TestCase):
    def test_new_ids_and_versions_do_not_replace_original_instrument(self):
        definitions = clarified.cases()
        self.assertEqual({item["id"] for item in definitions}, set(GOLD))
        self.assertEqual(len(original.cases()), 7)
        original_ids = {item["id"] for item in original.cases()}
        self.assertTrue(original_ids.isdisjoint(GOLD))
        for item in definitions:
            self.assertEqual(item["instrument_version"], "2.0")
            self.assertIn(item["prior_case_id"], original_ids)
            self.assertEqual(item["phase"], "clarified_screening")
            self.assertFalse(item["requires_manual_review"])
            self.assertLessEqual(item["max_output_tokens"], 8192)
            self.assertLess(len(item["prompt"]), 10_000)

    def test_all_gold_answers_have_complete_criteria_and_score(self):
        for case_id, answer in GOLD.items():
            with self.subTest(case=case_id):
                result = clarified.score(case_id, json.dumps(answer))
                self.assertEqual(result["score"], 100)
                self.assertTrue(result["passed"])
                self.assertEqual(result["instrument_version"], "2.0")
                self.assertEqual(sum(item["weight"] for item in result["criteria"]), 100)

    def test_prompt_explicitly_separates_observed_and_repaired_fields(self):
        prompt = clarified.case("experiment_design_v2")["prompt"]
        self.assertIn("OBSERVED", prompt)
        self.assertIn("RECOMMENDED CORRECTION", prompt)
        self.assertIn("never restate", prompt)
        self.assertIn("participant IDs are available", prompt)
        self.assertIn("equal compute cost per trial", prompt)

    def test_prompt_defines_external_scope_and_interval_inference(self):
        prompt = clarified.case("evidence_conflict_v2")["prompt"]
        self.assertIn("not held-out devices within E1", prompt)
        self.assertIn("not merely whether the point estimate", prompt)
        self.assertIn("source of the paired F1", prompt)

    def test_actual_flawed_procedure_no_longer_satisfies_repair_request(self):
        answer = dict(GOLD["experiment_design_v2"])
        answer.update(repaired_split_unit="session", repaired_preprocessing_fit="all_data",
                      repaired_tuning_set="test", repaired_seed_reporting="best_only",
                      repaired_tuning_budget_control="unconstrained")
        result = clarified.score("experiment_design_v2", json.dumps(answer))
        self.assertEqual(result["score"], 40)
        self.assertFalse(result["passed"])

    def test_unseen_environment_claim_and_point_estimate_inference_fail_closed(self):
        for field in ("external_generalization_unseen_environment_verified",
                      "e1_positive_effect_established_by_95pct_ci"):
            answer = dict(GOLD["evidence_conflict_v2"])
            answer[field] = True
            result = clarified.score("evidence_conflict_v2", json.dumps(answer))
            self.assertFalse(result["passed"])
            self.assertGreaterEqual(result["score"], 85)

    def test_distractors_and_non_text_flaws_are_not_valid_defect_sets(self):
        for extra in ("missing_participant_ids", "no_random_seed", {"nested": "bad"}):
            answer = dict(GOLD["experiment_design_v2"])
            answer["flaws_observed"] = answer["flaws_observed"] + [extra]
            self.assertFalse(clarified.score("experiment_design_v2", json.dumps(answer))["passed"])

    def test_old_field_names_are_not_silently_reinterpreted(self):
        answer = {"effect_percentage_points": 3, "ci_contains_zero": True,
                  "superiority_established": False, "generalization_verified": False,
                  "primary_source": "E1", "excluded_instruction_source": "E4",
                  "invented_citations": [], "latency_change_percent": 40}
        result = clarified.score("evidence_conflict_v2", json.dumps(answer))
        self.assertFalse(result["passed"])
        self.assertEqual(result["score"], 15)

    def test_shared_strict_json_parser_rejects_malformed_or_duplicate_fields(self):
        for text in ("", "[]", "null", '{"x":NaN}', '{"x":1,"x":2}', "before {}"):
            result = clarified.score("evidence_conflict_v2", text)
            self.assertFalse(result["passed"])
            self.assertEqual(result["score"], 0)
            self.assertIn("parse_error", result)
        text = "```json\n" + json.dumps(GOLD["evidence_conflict_v2"]) + "\n```"
        self.assertTrue(clarified.score("evidence_conflict_v2", text)["passed"])

    def test_bool_is_not_numeric_and_string_is_not_bool(self):
        answer = dict(GOLD["evidence_conflict_v2"])
        answer["e1_ci_contains_zero"] = "true"
        self.assertFalse(clarified.score("evidence_conflict_v2", json.dumps(answer))["passed"])
        answer = dict(GOLD["evidence_conflict_v2"])
        answer["e1_effect_percentage_points"] = True
        result = clarified.score("evidence_conflict_v2", json.dumps(answer))
        self.assertFalse(result["criteria"][0]["passed"])

    def test_cases_are_independently_mutable_and_unknown_ids_are_rejected(self):
        first = clarified.case("evidence_conflict_v2")
        first["prompt"] = "changed"
        self.assertNotEqual(clarified.case("evidence_conflict_v2")["prompt"], "changed")
        with self.assertRaisesRegex(ValueError, "unknown clarified"):
            clarified.score("evidence_conflict", "{}")


if __name__ == "__main__":
    unittest.main()
