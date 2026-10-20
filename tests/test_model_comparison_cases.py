"""Offline fixture and scoring contracts; model output is never executed."""

import base64
import hashlib
import json
from pathlib import Path
import struct
import unittest
import zlib

from scripts import model_comparison_cases as fixtures


ROOT = Path(__file__).resolve().parents[1]


ANSWERS = {
    "evidence_conflict": {
        "effect_percentage_points": 3, "ci_contains_zero": True,
        "superiority_established": False, "latency_change_percent": 40,
        "generalization_verified": False, "primary_source": "E1",
        "excluded_instruction_source": "E4", "invented_citations": [],
    },
    "experiment_design": {
        "flaws": ["participant_leakage", "global_preprocessing", "test_set_tuning",
                  "seed_cherry_picking", "unequal_tuning_budget"],
        "split_unit": "participant", "preprocessing_fit": "training_only",
        "tuning_set": "validation", "report_seeds": "all_predeclared",
        "budget_control": "matched",
    },
    "code_statistics": {
        "paired_differences": [.1, 0, .2, -.1], "mean_difference": .05,
        "independent_units": 4, "sample_sd_difference": .12909944487358055,
        "standard_error_difference": .06454972243679027,
        "pseudoreplication": True, "appropriate_test": "paired_t",
        "can_infer_significance_from_mean_alone": False,
    },
    "claim_precision": {
        "selected_claim": "B", "effect_percentage_points": 3,
        "ci_contains_zero": True, "claim_scope": "held_out_benchmark",
        "preserve_failed_runs": True,
        "sentence": "On the held-out benchmark, mean F1 increased by 3 percentage points, while the paired interval includes zero.",
    },
    "long_context": {
        "record_id": "R137", "version": 2, "independent_devices": 48,
        "paired_delta": .006, "ci95": [-.004, .016],
        "positive_effect_established": False,
    },
    "visual_chart": {
        "bar_count": 2, "left_value": 4, "right_value": 7, "difference": 3,
        "larger_bar": "right", "uncertainty_shown": False,
        "statistical_significance_established": False,
    },
}


class ComparisonCaseTests(unittest.TestCase):
    def test_all_gold_answers_and_weight_totals(self):
        for case_id, answer in ANSWERS.items():
            with self.subTest(case=case_id):
                result = fixtures.score(case_id, json.dumps(answer))
                self.assertEqual(result["score"], 100)
                self.assertTrue(result["passed"])
                self.assertEqual(sum(x["weight"] for x in result["criteria"]), 100)

    def test_all_cases_bounded_and_independently_mutable(self):
        cases = fixtures.cases()
        self.assertEqual({x["id"] for x in cases}, set(ANSWERS) | {"scientific_plan"})
        self.assertEqual(len(cases), 7)
        for item in cases:
            self.assertLess(len(item["prompt"].encode("utf-8")), 100_000)
            self.assertLessEqual(item["max_output_tokens"], 8192)
            self.assertIn("synthetic", item["system"])
        cases[0]["prompt"] = "changed"
        self.assertNotEqual(fixtures.case(cases[0]["id"])["prompt"], "changed")

    def test_open_scientific_proposal_requires_manual_review_without_numeric_score(self):
        definition = fixtures.case("scientific_plan")
        self.assertTrue(definition["requires_manual_review"])
        self.assertEqual(len(definition["manual_review_dimensions"]), 8)
        self.assertIn("36 model fits", definition["prompt"])
        self.assertIn("180 CPU-minutes", definition["prompt"])
        self.assertIn("No GPU", definition["prompt"])
        self.assertIn("UNVERIFIED", definition["prompt"])
        for text in ('{"hypothesis":"a proposal, not a result"}', "{}", "not JSON"):
            with self.subTest(text=text):
                result = fixtures.score("scientific_plan", text)
                self.assertTrue(result["requires_manual_review"])
                self.assertIsNone(result["score"])
                self.assertIsNone(result["max_score"])
                self.assertIsNone(result["passed"])
                self.assertEqual(result["criteria"], [])

    def test_malformed_or_non_finite_answers_have_no_score(self):
        for text in ("", "[]", "null", "prefix {}", '{"x":NaN}',
                     '{"x":1,"x":2}', "x" * 100_001):
            with self.subTest(text=text[:20]):
                result = fixtures.score("evidence_conflict", text)
                self.assertEqual(result["score"], 0)
                self.assertFalse(result["passed"])
                self.assertIn("parse_error", result)

    def test_one_fenced_json_object_is_scored_without_executing_it(self):
        text = "```json\n" + json.dumps(ANSWERS["evidence_conflict"]) + "\n```"
        self.assertTrue(fixtures.score("evidence_conflict", text)["passed"])
        self.assertFalse(fixtures.score("evidence_conflict", "```python\nprint(1)\n```")["passed"])

    def test_critical_error_blocks_even_when_numeric_score_is_85(self):
        answer = dict(ANSWERS["evidence_conflict"])
        answer["superiority_established"] = True
        result = fixtures.score("evidence_conflict", json.dumps(answer))
        self.assertEqual(result["score"], 85)
        self.assertFalse(result["passed"])

    def test_invented_citation_is_a_critical_error(self):
        answer = dict(ANSWERS["evidence_conflict"])
        answer["invented_citations"] = ["Imaginary Nature paper"]
        self.assertFalse(fixtures.score("evidence_conflict", json.dumps(answer))["passed"])

    def test_unknown_cases_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            fixtures.score("not-a-case", "{}")

    def test_booleans_are_not_numbers_and_strings_are_not_booleans(self):
        answer = dict(ANSWERS["visual_chart"])
        answer["left_value"] = True
        self.assertFalse(fixtures.score("visual_chart", json.dumps(answer))["passed"])
        answer = dict(ANSWERS["evidence_conflict"])
        answer["ci_contains_zero"] = "true"
        self.assertFalse(fixtures.score("evidence_conflict", json.dumps(answer))["passed"])

    def test_unverified_long_record_cannot_replace_active_evidence(self):
        prompt = fixtures.case("long_context")["prompt"]
        self.assertIn("status=superseded", prompt)
        self.assertIn("status=unverified-copy", prompt)
        answer = dict(ANSWERS["long_context"])
        answer.update(version=99, paired_delta=.89, independent_devices=999)
        self.assertFalse(fixtures.score("long_context", json.dumps(answer))["passed"])

    def test_chart_is_valid_deterministic_png_with_matching_hash(self):
        first = fixtures.case("visual_chart")["attachments"][0]
        second = fixtures.case("visual_chart")["attachments"][0]
        self.assertEqual(first, second)
        png = base64.b64decode(first["data_base64"], validate=True)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(hashlib.sha256(png).hexdigest(), first["sha256"])
        self.assertEqual(struct.unpack(">II", png[16:24]), (256, 160))
        offset = 8
        pixels = bytearray()
        while offset < len(png):
            length = struct.unpack(">I", png[offset:offset + 4])[0]
            kind = png[offset + 4:offset + 8]
            payload = png[offset + 8:offset + 8 + length]
            crc = struct.unpack(">I", png[offset + 8 + length:offset + 12 + length])[0]
            self.assertEqual(zlib.crc32(kind + payload) & 0xFFFFFFFF, crc)
            if kind == b"IDAT":
                pixels.extend(zlib.decompress(payload))
            offset += length + 12
        self.assertEqual(len(pixels), (256 * 3 + 1) * 160)


class ComparisonMatrixTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "config/model-comparison-20261020.json").read_text())

    def test_fresh_separate_allowance_and_safe_policy(self):
        config = self.config
        self.assertEqual(config["budget_cny"], 30)
        self.assertNotEqual(config["trial_id"], config["closed_prior_trial_id"])
        self.assertEqual(config["execution"], "github-actions-cloud-only")
        self.assertEqual(config["policy"]["automatic_paid_retries"], 0)
        self.assertFalse(config["policy"]["paid_model_judges"])
        self.assertFalse(config["policy"]["auto_promote_routes"])
        self.assertTrue(config["policy"]["stop_on_unknown_charge"])

    def test_all_22_quoted_routes_and_only_the_seven_configured_models(self):
        candidates = self.config["candidates"]
        quotes = json.loads((ROOT / "config/model-pricing.json").read_text())["quotes"]
        pairs = {(x["provider"], x["model"]) for x in candidates}
        self.assertEqual(len(candidates), 22)
        quoted_pairs = {(x["provider"], x["model"]) for x in quotes}
        self.assertTrue(pairs <= quoted_pairs)
        self.assertEqual(quoted_pairs - pairs, {("codekey-gemini", "gemini-4-argon")})
        self.assertEqual(len({x["provider"] for x in candidates}), 10)
        self.assertEqual(len({x["model"] for x in candidates}), 7)
        self.assertTrue(all(x["baseline"] for x in candidates[:7]))
        self.assertTrue(all(not x["baseline"] for x in candidates[7:]))

    def test_case_references_and_focused_efforts_are_explicit(self):
        available = {item["id"] for item in fixtures.cases()}
        routes = self.config["candidates"] + self.config["focused_settings"]
        self.assertEqual(len({item["id"] for item in routes}), len(routes))
        for item in routes:
            self.assertTrue(set(item["screening_cases"]) <= available)
            self.assertTrue(set(item["focused_cases"]) <= available)
            self.assertLessEqual(item["max_output_tokens"], 8192)
            if item["model"].startswith("deepseek"):
                self.assertNotIn("visual_chart", item["focused_cases"])
        self.assertEqual({x["effort"] for x in self.config["focused_settings"]},
                         {"medium", "low"})

    def test_scientific_proposal_is_first_and_only_for_the_seven_baselines(self):
        self.assertEqual(self.config["focused_cases"][0], "scientific_plan")
        for item in self.config["candidates"]:
            if item["baseline"]:
                self.assertEqual(item["focused_cases"][0], "scientific_plan")
            else:
                self.assertNotIn("scientific_plan", item["focused_cases"])
        for item in self.config["focused_settings"]:
            self.assertNotIn("scientific_plan", item["focused_cases"])


if __name__ == "__main__":
    unittest.main()
