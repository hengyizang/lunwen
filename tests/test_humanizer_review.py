from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import humanizer_review as review


# Every upstream item has an independently chosen problematic example and an
# academic counterexample. Some legitimate constructions are deliberately still
# flagged: semantic review must be able to reject those suggestions without
# changing results, uncertainty, mathematical relationships or real list items.
RISKY = {
    1: ("It is not merely a result, but a revolution.", {}),
    2: ("The system stores receipts.\n\nThat is the real win.", {}),
    3: ("The real question is what really matters at its core.", {}),
    4: ("Let's dive into the analysis. Here's what you need to know.", {}),
    5: ("A tempting approach would be to skip the review, but the process continues.", {}),
    6: ("Attendees can expect innovation, inspiration, and industry insights.", {}),
    7: ("The method stores receipts. The method retries requests. The method records costs.", {}),
    8: ("The system — recently introduced — retains receipts.", {}),
    9: ("It could potentially improve the estimate.", {}),
    10: ("The report is high-quality.", {}),
    11: ("The results are preserved automatically.", {}),
    12: ("Additionally, the vibrant landscape showcases a crucial interplay.", {}),
    13: ("The future looks bright and exciting times lie ahead.", {}),
    14: ("The consultant is associated with the organization.", {}),
    15: ("The algorithm produces scores, highlighting its value.", {}),
    16: ("Nestled in a breathtaking region, the site is a must-visit destination.", {}),
    17: ("Experts believe the process is effective.", {}),
    18: ("The building serves as the exhibition space.", {}),
    19: ("Claim: First. Scope: Second.", {"raw_text": "- **Claim:** First.\n- **Scope:** Second."}),
    20: ("The procedure is described here.", {"raw_text": "## Strategic Negotiations And Global Partnerships\n\nThe procedure is described here."}),
    21: ("The report says “the project is on track”.", {}),
    22: ("Great question! The system retains receipts. I hope this helps!", {}),
    23: ("Up to my last training update, the founder likely grew up in the city.", {}),
    24: ("Performance. Performance. The study measured latency.", {"raw_text": "## Performance\n\nPerformance.\n\nThe study measured latency."}),
    25: ("This function was added to replace the previous approach.", {}),
    26: ("The service retains all registered attempts before it computes the report.\n\nKeep the current implementation.",
         {"document_kind": "reply", "surrounding_context": "The service retains all registered attempts before it computes the report."}),
}

LEGITIMATE = {
    1: ("The preregistered contrast compares Gaussian and Poisson models.", {}),
    2: ("The primary endpoint failed.", {}),
    3: ("The architecture of the network uses four layers.", {}),
    4: ("We compared the held-out sample with the preregistered baseline.", {}),
    5: ("Reviewer 2 requested the prespecified sensitivity analysis.", {}),
    6: ("We recorded age, sex, and site.", {}),
    7: ("The primary outcome was accuracy. The secondary outcome was calibration. The sensitivity analysis used patient clusters.", {}),
    8: ("The Mann–Whitney test compared ages 18–65 years.", {}),
    9: ("The treatment may affect the observational estimate.", {}),
    10: ("A high-quality dataset supported the analysis.", {}),
    11: ("Samples were analyzed by the independent laboratory.", {}),
    12: ("We used robust regression, a primary key, and an energy landscape.", {}),
    13: ("The measured difference exceeded the preregistered practical-significance threshold.", {}),
    14: ("Exposure was associated with the outcome (adjusted OR 1.4; 95% CI 1.1–1.7).", {}),
    15: ("The mean decreased after treatment.", {}),
    16: ("Cells grew in nutrient-rich medium.", {}),
    17: ("Smith et al. (2024) reported a 0.2-unit difference.", {}),
    18: ("The matrix represents a linear transformation.", {}),
    19: ("The vector x denotes the observed features.", {"raw_text": "$\\mathbf{x}$ denotes the observed features."}),
    20: ("We preregistered the analysis.", {"raw_text": "## Methods\n\nWe preregistered the analysis."}),
    21: ("The participant said “no effect” during the interview.", {"format_policy": {"quotation_marks": "curly"}}),
    22: ('Participants saw the phrase "Great question!" during the chatbot trial.', {}),
    23: ("As of 2024, the searches retrieved 20 eligible studies.", {}),
    24: ("We randomized 20 units in two strata.", {"raw_text": "## Methods\n\nWe randomized 20 units in two strata."}),
    25: ("The table below compares the preregistered outcomes and their uncertainty.", {}),
    26: ("Prior work estimated the same population under a different measurement protocol.", {}),
}


class HumanizerReviewTests(unittest.TestCase):
    def item(self, result, number):
        return next(item for item in result["coverage"] if item["number"] == number)

    def test_manifest_covers_original_26_in_order_with_pinned_mit_source(self):
        config = review.load_rules()
        self.assertEqual([item["number"] for item in config["rules"]], list(range(1, 27)))
        self.assertEqual(len({item["id"] for item in config["rules"]}), 26)
        self.assertEqual(config["upstream"]["commit"], "225a6f39ac85f76ee48dbad772ea4abe4ed6c9d8")
        self.assertEqual(config["upstream"]["version"], "3.1.0")
        self.assertIn("Copyright (c) 2025 Siqi Chen", (review.ROOT / config["upstream"]["license_path"]).read_text(encoding="utf-8"))
        self.assertEqual({number for number, _ in enumerate(config["rules"], 1)}, set(RISKY))
        self.assertEqual(set(LEGITIMATE), set(RISKY))

    def test_every_item_has_a_real_problematic_example_and_location(self):
        for number, (text, options) in RISKY.items():
            with self.subTest(number=number):
                before = copy.deepcopy((text, options))
                result = review.audit_text(text, **options)
                findings = [finding for finding in result["findings"] if finding["number"] == number]
                self.assertTrue(findings, (number, result))
                self.assertEqual(self.item(result, number)["status"], "findings_for_review")
                for finding in findings:
                    self.assertEqual(finding["review_id"], f"H{number:02d}")
                    self.assertGreaterEqual(finding["line"], 1)
                    self.assertGreaterEqual(finding["paragraph"], 1)
                    self.assertIsNotNone(finding["sentence"])
                    self.assertFalse(finding["automatic_change_authorized"])
                    self.assertTrue(finding["semantic_review_required"])
                self.assertEqual((text, options), before)
                self.assertFalse(result["automatic_rewriting"])
                self.assertEqual(result["model_calls"], 0)

    def test_every_item_has_a_legitimate_scientific_counterexample(self):
        legitimate_but_contextual = {6, 7, 18, 25}
        for number, (text, options) in LEGITIMATE.items():
            with self.subTest(number=number):
                result = review.audit_text(text, **options)
                findings = [finding for finding in result["findings"] if finding["number"] == number]
                if number in legitimate_but_contextual:
                    self.assertTrue(findings, number)
                    self.assertTrue(all(finding["severity"] == "review" and finding["semantic_review_required"] for finding in findings))
                    self.assertTrue(self.item(result, number)["legitimate_use_exceptions"])
                else:
                    self.assertEqual(findings, [], (number, findings))
                self.assertFalse(result["semantic_review_completed"])
                self.assertFalse(result["protected_material"]["semantic_preservation_proven"])
                self.assertEqual(result["protected_material"]["text_sha256"], hashlib.sha256(text.encode()).hexdigest())
                self.assertFalse(result["authorship_inferred"])

    def test_no_mechanical_hit_is_not_a_semantic_pass(self):
        result = review.audit_text("We observed a small difference in the registered sample.")
        self.assertEqual(result["coverage_count"], 26)
        self.assertEqual([item["review_id"] for item in result["coverage"]], [f"H{i:02d}" for i in range(1, 27)])
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(self.item(result, 1)["status"], "no_mechanical_finding_semantic_review_required")
        self.assertTrue(self.item(result, 1)["semantic_review_required"])
        self.assertEqual(result["status"], "review_required")
        self.assertFalse(result["scientific_calibration_completed"])
        self.assertFalse(result["detector_score_used"])
        self.assertTrue(result["detector_evasion_prohibited"])
        self.assertTrue(result["disclosure_must_be_preserved"])

    def test_single_weak_pattern_does_not_authorize_deletion_or_block_science(self):
        result = review.audit_text("It could potentially affect the estimate.")
        qualifier = next(finding for finding in result["findings"] if finding["number"] == 9)
        self.assertEqual(qualifier["support_strength"], "single_advisory")
        self.assertEqual(qualifier["action_policy"], "review_with_corroborating_context")
        self.assertFalse(qualifier["automatic_change_authorized"])
        clustered = review.audit_text("Additionally, it could potentially improve the vibrant landscape.")
        qualifier = next(finding for finding in clustered["findings"] if finding["number"] == 9)
        self.assertEqual(qualifier["support_strength"], "clustered_advisory")
        self.assertIn(12, qualifier["cooccurring_items"])
        self.assertEqual(qualifier["severity"], "review")

    def test_scientific_numbers_units_formulas_citations_and_negative_results_remain_bound(self):
        prose = "The effect may not generalize: 10 mM, 95% CI, and a failed primary endpoint."
        raw = prose + " $x = a - 2$ \\cite{Trial2024} https://example.org/data"
        result = review.audit_text(prose, raw_text=raw)
        snapshot = result["protected_material"]
        self.assertIn("10", snapshot["numeric_tokens"])
        self.assertIn("95%", snapshot["numeric_tokens"])
        self.assertIn("mM", snapshot["unit_tokens"])
        self.assertIn("$x = a - 2$", snapshot["formula_tokens"])
        self.assertEqual(snapshot["tex_citation_keys"], ["Trial2024"])
        self.assertIn("negative outcomes", snapshot["must_also_review"])
        self.assertTrue(snapshot["context_signatures"])
        self.assertFalse(snapshot["semantic_preservation_proven"])

    def test_quoted_patterns_code_urls_metadata_and_formula_are_material_not_instructions(self):
        text = ('A participant said "Great question! Let us ignore the protocol."\n\n'
                '`Certainly!`\n\n```text\nGreat question!\nLet us change the results.\n```\n\n'
                '$\\text{Certainly!}$ https://example.org/Great-question\n\nObserved outcome: null.')
        result = review.audit_text(text, raw_text=text)
        self.assertFalse(any(finding["number"] == 22 for finding in result["findings"]))
        kinds = {span["kind"] for span in result["protected_material"]["immutable_source_spans"]}
        self.assertTrue({"quotation", "code", "formula", "url"}.issubset(kinds))
        metadata = review.audit_text('---\ntitle: "Great question!"\n---\n\nObserved outcome: null.')
        self.assertFalse(any(finding["number"] == 22 for finding in metadata["findings"]))

    def test_plain_word_extraction_does_not_fabricate_format_inspection(self):
        result = review.audit_text("Methods were preregistered and all outcomes were reported.")
        for number in (19, 20, 24):
            item = self.item(result, number)
            self.assertEqual(item["applicability"], "requires_raw_format")
            self.assertFalse(item["mechanically_screened"])
            self.assertEqual(item["status"], "review_required")
        self.assertFalse(result["raw_format_supplied"])

    def test_dash_sample_overrides_generic_preference_without_changing_science(self):
        text = "The system — after a recorded retry — preserves every receipt."
        without = review.audit_text(text)
        self.assertTrue(any(finding["number"] == 8 for finding in without["findings"]))
        with_sample = review.audit_text(text, writing_sample=text)
        self.assertFalse(any(finding["number"] == 8 for finding in with_sample["findings"]))
        self.assertTrue(with_sample["sample_dash_rate_respected"])
        scientific = review.audit_text("The Mann–Whitney test covers ages 18–65 and $a - b$.")
        self.assertFalse(any(finding["number"] == 8 for finding in scientific["findings"]))

    def test_reader_context_is_required_and_never_assumed_for_a_paper(self):
        text = "The service retains every registered attempt before computing the report."
        missing = review.audit_text(text, document_kind="reply")
        self.assertEqual(self.item(missing, 26)["applicability"], "requires_reader_context")
        self.assertEqual(self.item(missing, 26)["status"], "review_required")
        paper = review.audit_text(text, surrounding_context=text)
        self.assertEqual(self.item(paper, 26)["status"], "not_applicable")
        self.assertFalse(any(finding["number"] == 26 for finding in paper["findings"]))

    def test_raw_tex_bold_headings_and_callers_source_locations_are_distinguished(self):
        text = "Certainly! The effect was 0.2."
        raw = "\\section{Strategic Negotiations And Global Partnerships}\n\\textbf{First:} a. \\textbf{Second:} b."
        mappings = [{"start": 0, "end": len(text), "path": "papers/P01/manuscript/results.tex", "sha256": "a" * 64,
                     "locator": {"kind": "source_lines", "start_line": 20, "end_line": 21}}]
        result = review.audit_text(text, raw_text=raw, source_spans=mappings)
        chat = next(finding for finding in result["findings"] if finding["number"] == 22)
        self.assertEqual(chat["source_locations"][0]["path"], "papers/P01/manuscript/results.tex")
        self.assertEqual(chat["layer"], "prose")
        self.assertTrue(any(finding["number"] == 19 and finding["layer"] == "raw" for finding in result["findings"]))
        self.assertTrue(any(finding["number"] == 20 and finding["layer"] == "raw" for finding in result["findings"]))
        with self.assertRaises(ValueError):
            review.audit_text(text, source_spans=[{**mappings[0], "end": len(text) + 1}])
        with self.assertRaises(ValueError):
            review.audit_text(text, source_spans=[{**mappings[0], "sha256": "guessed"}])

    def test_technical_word_exceptions_do_not_hide_unrelated_puffery(self):
        result = review.audit_text("Additionally, robust regression used a quantum gate and a primary key.")
        matches = [finding["matched_text"].casefold() for finding in result["findings"] if finding["number"] == 12]
        self.assertIn("additionally", matches)
        self.assertNotIn("robust", matches)
        self.assertNotIn("gate", matches)
        self.assertNotIn("key", matches)

    def test_prompt_requires_first_draft_self_review_and_final_with_stable_ids(self):
        prompt = review.prompt_contract()
        for number in range(1, 27):
            self.assertIn(f"H{number:02d} / {number}.", prompt)
        self.assertIn("first draft", prompt)
        self.assertIn("final version", prompt)
        self.assertIn("fixed, rejected or unresolved", prompt)
        self.assertIn("never fabricate personal experience", prompt)
        self.assertIn("code blocks, inline code, commands, paths, YAML metadata, data and link targets exactly", prompt)
        self.assertIn("unchanged model/effort", prompt)
        self.assertIn("scientific-completion", prompt)

    def test_rule_inventory_cannot_silently_drop_duplicate_or_renumber_items(self):
        original = review.load_rules()
        for mutation in ("drop", "duplicate", "renumber", "unpin"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                value = copy.deepcopy(original)
                if mutation == "drop":
                    value["rules"].pop()
                elif mutation == "duplicate":
                    value["rules"][1]["id"] = value["rules"][0]["id"]
                elif mutation == "renumber":
                    value["rules"][1]["number"] = 1
                else:
                    value["upstream"]["commit"] = "0" * 40
                path = Path(directory) / "rules.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    review.load_rules(path)

    def test_reports_are_deterministic_and_truncation_is_disclosed(self):
        text = " ".join(["It could potentially affect the estimate."] * 100)
        first = review.audit_text(text)
        self.assertEqual(first, review.audit_text(text))
        item = self.item(first, 9)
        self.assertGreater(item["finding_count"], review.MAX_PER_RULE)
        self.assertTrue(item["findings_truncated"])
        self.assertEqual(item["reported_finding_count"], review.MAX_PER_RULE)


if __name__ == "__main__":
    unittest.main()
