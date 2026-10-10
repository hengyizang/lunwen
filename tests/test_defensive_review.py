"""Preservation-first anti-defensive review regressions; no model calls."""
from __future__ import annotations

import json
import unittest

from scripts import defensive_review as review


class DefensiveReviewTests(unittest.TestCase):
    def test_full_source_checklist_workflow_and_local_categories_are_covered(self):
        report = review.audit_text("This paper examines a documented research question.")
        self.assertEqual(len(report["coverage"]), 8)
        self.assertEqual([row["review_id"] for row in report["coverage"]], [f"AD{i:02d}" for i in range(1, 9)])
        self.assertEqual(len(review.load_rules()["groups"]), 8)
        self.assertEqual(len(report["checklist_coverage"]), 10)
        self.assertEqual(len(report["rewrite_procedure"]), 5)
        self.assertEqual(len(report["function_classes"]), 6)
        self.assertEqual(report["source"]["commit"], "c7edf8fc91ae9c4f7e58345bd12934bb4cf41c46")
        self.assertEqual(len(report["source"]["skill_sha256"]), 64)
        self.assertEqual(len(report["source"]["license_sha256"]), 64)
        self.assertFalse(report["automatic_rewrite"])
        self.assertFalse(report["scientific_equivalence_verified"])
        self.assertFalse(report["full_semantic_review_verified"])
        self.assertEqual(report["manuscript_language_requirement"], "English")
        self.assertEqual({row["semantic_verification"] for row in report["coverage"]}, {"not_performed"})

    def test_real_defensive_posture_is_located_and_always_advisory(self):
        text = ("# Abstract\n\nAlthough this study has limitations, it only provides a modest contribution.\n\n"
                "We do not claim universal completeness. This paper does not claim a comprehensive theory.\n\n"
                "To be clear, the results may potentially suggest an explanation. However, nevertheless, the goal is not completeness but focus.")
        report = review.audit_text(text)
        ids = {row["rule_id"] for row in report["findings"]}
        self.assertTrue({"caveat-led-point", "high-impact-caveat", "preemptive-nonclaim", "repeated-negative-claims",
                         "self-minimizing-posture", "hypothetical-clarifier", "stacked-uncertainty", "stacked-transition", "stock-binary"} <= ids)
        for row in report["findings"]:
            self.assertEqual(row["confidence"], "advisory")
            self.assertFalse(row["automatic_edit_allowed"])
            self.assertEqual(text[row["start"]:row["end"]], row["match"])
            self.assertGreaterEqual(row["line"], 1)
            self.assertGreaterEqual(row["column"], 1)
            self.assertEqual(row["raw_location"]["status"], "same_input")

    def test_legitimate_design_uncertainty_controls_ethics_and_rebuttal_are_retained(self):
        cases = [
            "We do not claim causal identification because the design is observational and remains subject to confounding.",
            "Although the confidence interval crosses zero, the effect estimate and its uncertainty remain informative.",
            "Although the 95% CI crosses zero, the estimate remains uncertain.",
            "Although n = 12 limits precision, all independent units are reported.",
            "We do not claim that the method generalizes to unseen populations or unvalidated clinical use.",
            "Although negative controls failed, all failed runs and null results are reported.",
            "This paper is not intended to permit identifiable-data reuse without informed consent and an ethics review.",
            "The goal is not to infer causality but to distinguish an association from causal identification.",
            "Although the reviewer questions the comparison, Table 3 documents both control groups under the same protocol.",
            "Only a modest improvement of 0.2 percentage points was observed; the uncertainty interval includes zero."
        ]
        for text in cases:
            with self.subTest(text=text):
                report = review.audit_text(text)
                self.assertFalse(report["findings"], report["findings"])
                self.assertFalse(report["automatic_rewrite"])
                for row in report["protected_signals"]:
                    self.assertEqual(row["disposition"], "retain_evidence_boundary_and_review_context")
                    self.assertTrue(row["protected_context"])

    def test_single_qualifiers_and_real_negative_results_are_not_banned(self):
        text = ("The results suggest an association in this observational analysis. The effect may differ under these conditions.\n\n"
                "Accuracy fell from 90% to 89%, while latency fell from 100 ms to 60 ms under the same test conditions.\n\n"
                "However, the preregistered negative result did not support the primary hypothesis. The baseline outperformed the method.")
        report = review.audit_text(text)
        self.assertFalse(report["findings"])
        self.assertEqual(report["status"], "no_pattern_findings")

    def test_chinese_modesty_is_reviewed_but_causal_and_ethics_boundaries_stay(self):
        report = review.audit_text("本文仅仅做了初步尝试，只能提供有限参考，仍有很大提升空间。")
        self.assertIn("self-minimizing-posture", {row["rule_id"] for row in report["findings"]})
        for text in ("我们并不声称因果关系，观察性分析仍可能存在混杂。", "尽管阴性对照失败，所有失败实验和阴性结果仍完整报告。", "本文并不试图绕过知情同意、伦理审查或隐私要求。"):
            with self.subTest(text=text):
                report = review.audit_text(text)
                self.assertFalse(report["findings"])
                self.assertTrue(report["protected_signals"])
        self.assertEqual(report["inspection_languages"], ["English", "Chinese"])

    def test_adverse_result_suppression_and_blanket_verdict_get_context_review(self):
        text = ("Negative results were omitted because they were unfavorable.\n\n"
                "The experiments are insufficient. Lower accuracy reveals limitations of the method.\n\n"
                "To avoid potential reviewer criticism, the manuscript adds a generic limitation.")
        report = review.audit_text(text)
        ids = {row["rule_id"] for row in report["findings"]}
        self.assertTrue({"result-direction-suppression", "generic-experiment-verdict", "imagined-reviewer-limit"} <= ids)
        suppression = next(row for row in report["findings"] if row["rule_id"] == "result-direction-suppression")
        self.assertTrue(suppression["integrity_review_required"])
        self.assertFalse(suppression["automatic_edit_allowed"])
        self.assertIn("predeclared", suppression["guidance"])

    def test_repeated_real_limitation_is_not_silently_removed_from_abstract_or_conclusion(self):
        boundary = "We do not claim causal identification from this observational analysis."
        text = "# Abstract\n\n" + boundary + "\n\n# Conclusion\n\n" + boundary
        report = review.audit_text(text)
        self.assertFalse(report["findings"])
        self.assertIn("repeated-limitation", {row["rule_id"] for row in report["protected_signals"]})
        self.assertIn("repeated-negative-claims", {row["rule_id"] for row in report["protected_signals"]})

    def test_raw_locations_are_honest_and_code_math_quoted_examples_are_excluded(self):
        prose = "To be clear, this passage only provides a modest contribution."
        raw = "\\section{Introduction}\n" + prose
        report = review.audit_text(prose, raw_text=raw)
        self.assertTrue(report["findings"])
        self.assertEqual(report["findings"][0]["raw_location"]["line"], 2)
        self.assertEqual(report["findings"][0]["section"], "introduction")
        repeated_raw = prose + "\n" + prose
        repeated = review.audit_text(prose, raw_text=repeated_raw)
        self.assertEqual(repeated["findings"][0]["raw_location"]["status"], "ambiguous")
        examples = "> We do not claim completeness.\n\n```text\nTo be clear, merely provides\n```\n\n$may potentially$"
        self.assertFalse(review.audit_text(examples)["findings"])

    def test_report_is_deterministic_and_semantic_categories_are_not_falsely_certified(self):
        text = "The central contribution is a documented comparison."
        first, second = review.audit_text(text), review.audit_text(text)
        self.assertEqual(first, second)
        json.dumps(first, allow_nan=False)
        semantic = {row["id"]: row for row in first["coverage"]}
        self.assertEqual(semantic["contribution-and-coherence"]["applicability"], "context_dependent")
        self.assertIn("example_fact_integrity", first["context_guidance"])
        self.assertIn("supplement_placement_by_predeclared_role", first["context_guidance"])
        self.assertIn("second_pass_and_itemized_revision_log", first["context_guidance"])

    def test_prompt_covers_full_workflow_without_new_calls_or_fact_import(self):
        contract = review.prompt_contract()
        for required in ("Understand", "direct", "six functions", "Rewrite step 1", "Rewrite step 5", "second self-review", "itemized change log",
                         "negative/null/adverse results", "failed runs", "ethics", "causation", "Examples", "unknown", "evaluation criteria",
                         "demonstrated problems", "optional", "non-Claude", "do not start another", "local edits local"):
            self.assertIn(required, contract)
        self.assertLess(len(contract), 6500)
        for number in range(1, 9):
            self.assertIn(f"AD{number:02d}", contract)
        self.assertEqual(contract, review.prompt_contract())


if __name__ == "__main__":
    unittest.main()
