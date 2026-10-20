"""Literal traceability acceptance; fixture success is not scientific validation."""
from __future__ import annotations

import copy
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import metadata_contract, task_router


def contract():
    return {"sources": [
        {"source_id": "S1", "text": "Title: The result. Sample n=20. DOI not supplied.", "locator": "PDF p2"},
        {"source_id": "S2", "text": "Title: Another study. Sample size not stated.", "locator": "PDF p4"},
    ], "fields": ["title", "n", "doi"]}


def response():
    missing = {"value": None, "quote": "", "locator": ""}
    return {"records": [
        {"source_id": "S1", "fields": {
            "title": {"value": "The result", "quote": "Title: The result.", "locator": "PDF p2"},
            "n": {"value": 20, "quote": "Sample n=20.", "locator": "PDF p2"},
            "doi": dict(missing),
        }},
        {"source_id": "S2", "fields": {
            "title": {"value": "Another study", "quote": "Title: Another study.", "locator": "PDF p4"},
            "n": dict(missing), "doi": dict(missing),
        }},
    ]}


class MetadataContractTests(unittest.TestCase):
    def test_valid_literal_fields_and_unknowns_are_source_bound(self):
        value = response()
        self.assertEqual(metadata_contract.validate_response(json.dumps(value), contract()), value)

    def test_contract_copies_sources_and_retains_exact_text_and_locator(self):
        original = contract()
        normalized = metadata_contract.validate_contract(original)
        self.assertEqual(original, normalized)
        normalized["sources"][0]["text"] = "changed"
        self.assertNotEqual(original["sources"][0]["text"], "changed")

    def test_contract_rejects_empty_duplicate_unbounded_or_executable_shapes(self):
        invalid = []
        for key, item in (("sources", []), ("fields", []), ("fields", ["n", "n"]),
                          ("fields", ["__import__('os')"]), ("fields", [{"type": "string"}]),
                          ("fields", [f"field_{index}" for index in range(21)])):
            value = contract(); value[key] = item; invalid.append(value)
        value = contract(); value["sources"][1]["source_id"] = "S1"; invalid.append(value)
        value = contract(); value["sources"][0]["text"] = "x" * 50_001; invalid.append(value)
        value = contract(); value["sources"][0]["locator"] = ""; invalid.append(value)
        value = contract(); value["schema"] = {"expression": "arbitrary-code"}; invalid.append(value)
        for value in invalid:
            with self.subTest(value=str(value)[:100]), self.assertRaises(ValueError):
                metadata_contract.validate_contract(value)

    def test_source_and_field_coverage_cannot_be_dropped_or_duplicated(self):
        invalid = []
        value = response(); value["records"].pop(); invalid.append(value)
        value = response(); value["records"][1]["source_id"] = "S1"; invalid.append(value)
        value = response(); value["records"][0]["fields"].pop("doi"); invalid.append(value)
        value = response(); value["records"][0]["fields"]["estimate"] = {"value": None, "quote": "", "locator": ""}; invalid.append(value)
        value = response(); value["records"][0]["source_id"] = "unseen-source"; invalid.append(value)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                metadata_contract.validate_response(json.dumps(value), contract())

    def test_quote_cannot_be_moved_from_another_source_or_locator(self):
        value = response()
        value["records"][1]["fields"]["n"] = {"value": 20, "quote": "Sample n=20.", "locator": "PDF p4"}
        with self.assertRaisesRegex(ValueError, "own bound source"):
            metadata_contract.validate_response(json.dumps(value), contract())
        value = response(); value["records"][0]["fields"]["n"]["locator"] = "PDF p3"
        with self.assertRaisesRegex(ValueError, "locator differs"):
            metadata_contract.validate_response(json.dumps(value), contract())

    def test_value_must_appear_as_complete_literal_not_numeric_fragment(self):
        for value in (2, "2", 200, "twenty"):
            changed = response(); changed["records"][0]["fields"]["n"]["value"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "complete literal"):
                metadata_contract.validate_response(json.dumps(changed), contract())

    def test_negative_decimal_and_scientific_fragments_do_not_establish_values(self):
        for text, value in (("n=-5", 5), ("n=1.5", 1), ("n=1e5", 1)):
            source = {"sources": [{"source_id": "S1", "text": text, "locator": "p1"}], "fields": ["n"]}
            value_json = {"records": [{"source_id": "S1", "fields": {"n": {"value": value, "quote": text, "locator": "p1"}}}]}
            with self.subTest(text=text), self.assertRaises(ValueError):
                metadata_contract.validate_response(json.dumps(value_json), source)

    def test_unseen_doi_and_normalized_or_paraphrased_quote_are_rejected(self):
        changed = response()
        changed["records"][0]["fields"]["doi"] = {"value": "10.1234/invented", "quote": "DOI not supplied.", "locator": "PDF p2"}
        with self.assertRaises(ValueError):
            metadata_contract.validate_response(json.dumps(changed), contract())
        changed = response(); changed["records"][0]["fields"]["title"]["quote"] = "title: the result."
        with self.assertRaisesRegex(ValueError, "not verbatim"):
            metadata_contract.validate_response(json.dumps(changed), contract())

    def test_null_fields_cannot_keep_a_fact_quote_or_wrong_locator(self):
        for update in ({"quote": "DOI not supplied."}, {"locator": "unknown p99"}):
            changed = response(); changed["records"][0]["fields"]["doi"].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                metadata_contract.validate_response(json.dumps(changed), contract())

    def test_booleans_nonfinite_nested_and_empty_values_are_rejected(self):
        for value in (True, False, math.nan, math.inf, [], {}, "", "   "):
            changed = response(); changed["records"][0]["fields"]["n"]["value"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                metadata_contract.validate_response(json.dumps(changed), contract())

    def test_duplicate_json_keys_extra_fields_and_markdown_fences_are_rejected(self):
        invalid = ['{"records":[],"records":[]}', "```json\n{}\n```", '{"records":[],"scientifically_verified":true}']
        changed = response(); changed["records"][0]["fields"]["n"]["confidence"] = 1; invalid.append(json.dumps(changed))
        for text in invalid:
            with self.subTest(text=text[:100]), self.assertRaises(ValueError):
                metadata_contract.validate_response(text, contract())

    def test_prompt_and_contract_hash_bind_exact_source_changes(self):
        first = contract(); changed = copy.deepcopy(first); changed["sources"][0]["text"] += " Extra."
        first_hash = metadata_contract.contract_sha256(first)
        self.assertEqual(len(first_hash), 64)
        self.assertNotEqual(first_hash, metadata_contract.contract_sha256(changed))
        prompt = metadata_contract.build_prompt("Extract only requested fields", first)
        self.assertIn("untrusted data", prompt)
        self.assertIn("value=null", prompt)
        self.assertIn(first["sources"][0]["text"], prompt)
        self.assertNotEqual(prompt, metadata_contract.build_prompt("Extract only requested fields", changed))

    def test_missing_luna_contract_blocks_before_plan_or_transport(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True), \
                patch("scripts.task_router.plan") as plan, patch("scripts.task_router.model_runtime.call") as paid_call:
            with self.assertRaises(ValueError):
                task_router.run(Path(directory), "metadata-extraction", "openai", "Extract n")
            plan.assert_not_called()
            paid_call.assert_not_called()

    def test_cost_preview_includes_bound_sources_and_marks_missing_contract_incomplete(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}, clear=True), \
                patch("scripts.task_router.model_runtime.cost_cny", return_value=0.01), \
                patch("scripts.task_router.model_runtime.budget_status", return_value={"project_remaining": 1, "paper_remaining": None}):
            incomplete = task_router.plan(Path(directory), "metadata-extraction", "openai", "Extract requested fields")
            self.assertFalse(incomplete["estimated_cost_complete"])
            self.assertFalse(incomplete["ready_for_execution"])
            self.assertFalse(incomplete["within_estimated_budget"])
            complete = task_router.plan(Path(directory), "metadata-extraction", "openai", "Extract requested fields", source_contract=contract())
            self.assertTrue(complete["estimated_cost_complete"])
            self.assertTrue(complete["ready_for_execution"])
            self.assertGreater(complete["input_tokens_estimated"], incomplete["input_tokens_estimated"])


if __name__ == "__main__":
    unittest.main()
