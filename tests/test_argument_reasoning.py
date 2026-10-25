"""Source-bound argument preparation fixtures; no scientific quality claim."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts import incremental_writing as writing
from scripts.research_artifacts import sha, write


class ArgumentReasoningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.put("papers/P01/manuscript/main.tex", "A bounded illustrative statement.\n")
        self.put("evidence/derivation.md", "Under assumption A, the illustrative relation follows.\n")
        write(self.project / "papers/P01/reviews/paper-facts.json",
              {"facts": [{"id": "F1", "statement": "An explicitly synthetic bounded relation"}]})

    def put(self, relative, content):
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def argument(self, **updates):
        unit = writing.inventory(self.project, "P01")["units"][0]
        paragraph = {"paragraph_id": "PAR1", "section": "Illustrative section",
                     "function": "context", "purpose": "Set the illustrative scope",
                     "claim_ids": ["F1"], "inference_boundary": "Assumption A only",
                     "transition": "The next question follows from this scope",
                     "units": [{"unit_id": unit["unit_id"], "sha256": unit["sha256"]}],
                     **updates}
        return {"id": "ARG1", "paper_id": "P01", "precedence": [], "paragraphs": [paragraph]}

    def anchor(self):
        return {"path": "evidence/derivation.md", "sha256": sha(self.project / "evidence/derivation.md"),
                "kind": "source_lines", "start_line": 1, "end_line": 1,
                "quote": "Under assumption A, the illustrative relation follows."}

    def evaluate(self, row):
        writing.freeze_plan(self.project, row, phase="before_writer")
        return writing.arguments(self.project, row)

    def prepared(self, **updates):
        return self.argument(takeaway="The illustrative relation holds under assumption A.",
                             warrant="The cited derivation starts with A and derives precisely this relation.",
                             reasoning_status="ready_for_scientific_review", **updates)

    def test_legacy_purpose_fallback_is_not_assessed_or_semantically_passed(self):
        result = self.evaluate(self.argument())
        paragraph = result["reverse_outline"][0]
        self.assertEqual(paragraph["takeaway"], "Set the illustrative scope")
        self.assertEqual(paragraph["takeaway_origin"], "legacy_purpose")
        self.assertEqual(paragraph["reasoning_status"], "not_assessed")
        self.assertFalse(result["reasoning_review"]["ready_for_scientific_review"])
        self.assertEqual(result["reasoning_review"]["paragraph_ids_needing_attention"], ["PAR1"])
        self.assertFalse(result["semantic_support_verified"])

    def test_source_bound_preparation_is_not_a_semantic_verdict(self):
        result = self.evaluate(self.prepared(function="interpretation", evidence=[self.anchor()]))
        paragraph = result["reverse_outline"][0]
        self.assertTrue(result["reasoning_review"]["ready_for_scientific_review"])
        self.assertEqual(paragraph["reasoning_status"], "ready_for_scientific_review")
        self.assertEqual(paragraph["review_gaps"], [])
        self.assertTrue(paragraph["scientific_review_required"])
        self.assertFalse(paragraph["semantic_support_verified"])
        self.assertFalse(paragraph["evidence"][0]["semantic_support_verified"])

    def test_self_declared_ready_without_warrant_has_an_actionable_gap(self):
        row = self.prepared()
        del row["paragraphs"][0]["warrant"]
        result = self.evaluate(row)
        paragraph = result["reverse_outline"][0]
        self.assertEqual(paragraph["reasoning_status"], "needs_material")
        self.assertEqual(paragraph["review_gaps"][0]["code"], "missing_warrant")
        self.assertIn("bound evidence", paragraph["review_gaps"][0]["completion_condition"])
        self.assertEqual(paragraph["review_gaps"][0]["claim_ids"], ["F1"])

    def test_theoretical_argument_requires_no_invented_effect_size(self):
        row = self.prepared(function="interpretation", evidence=[self.anchor()])
        row["paragraphs"][0]["warrant"] = "Assumption A and the supplied derivation imply this proposition."
        result = self.evaluate(row)
        self.assertTrue(result["reasoning_review"]["ready_for_scientific_review"])
        self.assertNotIn("effect_size", result["reverse_outline"][0])

    def test_research_question_uses_rationale_without_claiming_observed_data(self):
        row = self.prepared(function="question")
        row["paragraphs"][0].update(takeaway="Does the illustrative relation extend beyond A?",
                                     warrant="The bounded relation motivates testing the unexamined assumption.")
        result = self.evaluate(row)
        self.assertTrue(result["reasoning_review"]["ready_for_scientific_review"])
        self.assertEqual(result["reverse_outline"][0]["evidence"], [])
        self.assertFalse(result["semantic_support_verified"])

    def test_transition_does_not_require_a_scientific_three_part_template(self):
        result = self.evaluate(self.argument(function="transition", claim_ids=[]))
        paragraph = result["reverse_outline"][0]
        self.assertEqual(paragraph["reasoning_status"], "not_applicable")
        self.assertFalse(paragraph["warrant_required"])
        self.assertEqual(paragraph["review_gaps"], [])
        self.assertFalse(paragraph["scientific_review_required"])

    def test_scientific_paragraph_cannot_exempt_itself(self):
        with self.assertRaisesRegex(ValueError, "cannot exempt"):
            self.evaluate(self.argument(reasoning_status="not_applicable"))

    def test_missing_material_has_specific_completion_task_and_remains_pending(self):
        row = self.prepared()
        row["paragraphs"][0]["material_needs"] = [
            {"id": "NEED1", "material_type": "proof", "claim_ids": ["F1"],
             "description": "The extension outside A has no derivation.",
             "completion_condition": "Supply a source-bound proof or retain A as the explicit scope."}]
        result = self.evaluate(row)
        paragraph = result["reverse_outline"][0]
        self.assertEqual(paragraph["reasoning_status"], "needs_material")
        self.assertEqual(paragraph["material_needs"][0]["status"], "pending")
        self.assertFalse(result["reasoning_review"]["ready_for_scientific_review"])

    def test_missing_material_cannot_be_vague_or_link_unrelated_claim(self):
        good = {"id": "NEED1", "material_type": "literature", "claim_ids": ["F1"],
                "description": "Closest prior extension needs a primary source.",
                "completion_condition": "Locate the actual original passage and compare its assumptions."}
        for change in ({"completion_condition": " "}, {"claim_ids": ["OTHER"]},
                       {"material_type": "invented"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.evaluate(self.argument(material_needs=[good | change], reasoning_status="needs_material"))

    def test_changed_warrant_cannot_refresh_only_units_to_bypass_prewrite_plan(self):
        row = self.prepared()
        writing.freeze_plan(self.project, row, phase="before_writer")
        edited = copy.deepcopy(row)
        edited["paragraphs"][0]["warrant"] = "A different causal explanation not present in the frozen plan."
        unit = writing.inventory(self.project, "P01")["units"][0]
        edited["paragraphs"][0]["units"] = [{"unit_id": unit["unit_id"], "sha256": unit["sha256"]}]
        with self.assertRaisesRegex(ValueError, "pre-write frozen plan"):
            writing.arguments(self.project, edited)

    def test_new_reasoning_fields_are_part_of_the_frozen_concept(self):
        row = self.prepared()
        original = writing.concept(row)
        for field, value in (("takeaway", "A newly scoped point"), ("warrant", "A new rationale"),
                             ("reasoning_status", "needs_material"),
                             ("material_needs", [{"id": "NEED1", "material_type": "scope",
                                                  "description": "Clarify A", "completion_condition": "Bound A",
                                                  "claim_ids": ["F1"]}])):
            changed = copy.deepcopy(row)
            changed["paragraphs"][0][field] = value
            self.assertNotEqual(writing.digest(original), writing.digest(writing.concept(changed)))

    def test_schema_contains_the_structured_material_and_preparation_contract(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/research-increments.schema.json").read_text(encoding="utf-8"))
        properties = schema["$defs"]["arguments"]["properties"]["paragraphs"]["items"]["properties"]
        self.assertIn("ready_for_scientific_review", properties["reasoning_status"]["enum"])
        self.assertNotIn("verified", properties["reasoning_status"]["enum"])
        required = schema["$defs"]["argument_material_need"]["required"]
        self.assertIn("completion_condition", required)
        self.assertIn("claim_ids", required)


if __name__ == "__main__":
    unittest.main()
