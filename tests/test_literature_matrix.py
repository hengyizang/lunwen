"""Cloud-only synthetic extraction contracts, not real scientific validation."""
import copy
import csv
import io
from unittest.mock import patch

from scripts import literature_matrix as matrix
from scripts.research_artifacts import read, record, sha, write
from tests.test_literature_workbench import WorkbenchFixture


class LiteratureMatrixTests(WorkbenchFixture):
    def setUp(self):
        super().setUp()
        self.paper = self.add_paper("a", "Population A under fixed conditions had accuracy 95.0 %; 95% CI 90.0 to 99.0.")
        self.spec = {"schema_version": "1.0", "question": "Which measurements use comparable conditions?",
                     "paper_ids": ["a"], "fields": [{"id": "accuracy", "label": "Accuracy", "type": "number",
                     "quantity": "accuracy", "unit": "proportion"}], "cells": []}

    def cell(self, *, raw="95.0", raw_unit="%", field="accuracy", quantity="accuracy", text="Reported accuracy"):
        original = (self.project / self.paper["source"]["path"]).read_text(encoding="utf-8")
        return {"paper_id": "a", "field_id": field, "text": text, "kind": "author_claim",
                "evidence": [self.anchor(self.paper, original, last=len(original.splitlines()))],
                "numeric": {"raw_value": raw, "raw_unit": raw_unit, "quantity": quantity},
                "source_context": {"kind": "prose", "population": "Population A", "conditions": "fixed conditions"}}

    def prepare(self, cell=None):
        if cell is not None:
            self.spec["cells"] = [cell]
        self.build()
        return matrix.build(self.project, self.spec)

    def source_text(self, text):
        self.paper["source"] = self.source(self.paper["source"]["path"], text)

    def test_exact_unit_conversion_keeps_original_and_never_promotes_science(self):
        report = self.prepare(self.cell())
        value = report["cells"][0]["numeric"]
        self.assertEqual(value["original_value"], "95.0")
        self.assertEqual(value["original_unit"], "%")
        self.assertEqual(value["value"], "0.950")
        self.assertEqual(value["unit"], "proportion")
        self.assertFalse(value["eligible_for_quantitative_synthesis"])
        self.assertFalse(report["comparability_verified"])
        self.assertFalse(report["semantic_verification"])

    def test_all_paper_field_cells_and_unknowns_are_retained(self):
        self.add_paper("b", "The paper does not provide the requested measurement in this fixture.")
        self.spec["paper_ids"].append("b")
        self.spec["fields"].append({"id": "p_value", "type": "number", "quantity": "p value", "unit": "1", "measure": "p_value"})
        report = self.prepare(self.cell())
        self.assertEqual(len(report["cells"]), 4)
        self.assertEqual(report["unknown_cell_count"], 3)
        p = [c for c in report["cells"] if c["field_id"] == "p_value"]
        self.assertTrue(all("numeric" not in c and c["status"] == "unknown" for c in p))

    def test_existing_card_entries_are_reused_without_selecting_one(self):
        self.spec["fields"] = [{"id": "method", "type": "text", "card_field": "methods"}]
        card = self.card(self.paper, field="methods")
        card["fields"]["methods"].append(copy.deepcopy(card["fields"]["methods"][0]))
        path = self.project / self.paper["card"]["path"]
        write(path, card)
        self.paper["card"]["sha256"] = sha(path)
        report = self.prepare()
        cell = report["cells"][0]
        self.assertTrue(cell["from_reading_card"])
        self.assertEqual(len(cell["entries"]), 2)
        self.assertFalse(cell["semantic_verification"])

    def test_zero_is_preserved_instead_of_being_treated_as_missing(self):
        self.source_text("Population A under fixed conditions had error 0 %.")
        report = self.prepare(self.cell(raw="0"))
        self.assertEqual(report["cells"][0]["numeric"]["value"], "0.00")
        self.assertEqual(report["unknown_cell_count"], 0)

    def test_zero_p_value_is_preserved_with_precision_review(self):
        self.source_text("Population A under fixed conditions reported p = 0.")
        self.spec["fields"] = [{"id": "p", "type": "number", "quantity": "p value", "unit": "1", "measure": "p_value"}]
        report = self.prepare(self.cell(raw="0", raw_unit="1", field="p", quantity="p value"))
        self.assertTrue(report["cells"][0]["numeric"]["reported_zero_p_value_requires_precision_review"])

    def test_reported_p_inequality_remains_censored(self):
        self.source_text("Population A under fixed conditions reported p < 0.001.")
        self.spec["fields"] = [{"id": "p", "type": "number", "quantity": "p value", "unit": "1", "measure": "p_value"}]
        cell = self.cell(raw="0.001", raw_unit="1", field="p", quantity="p value")
        cell["numeric"]["comparator"] = "<"
        report = self.prepare(cell)
        self.assertEqual(report["cells"][0]["numeric"]["comparator"], "<")
        cell["numeric"].pop("comparator")
        with self.assertRaisesRegex(ValueError, "inequality"):
            self.prepare(cell)
        cell["numeric"]["comparator"] = ">"
        with self.assertRaisesRegex(ValueError, "inequality"):
            self.prepare(cell)

    def test_intervals_convert_with_point_and_keep_original_label(self):
        cell = self.cell()
        cell["numeric"]["uncertainty"] = {"lower": "90.0", "upper": "99.0", "label": "95% CI"}
        interval = self.prepare(cell)["cells"][0]["numeric"]["uncertainty"]
        self.assertEqual(interval["lower"], "0.900")
        self.assertEqual(interval["upper"], "0.990")
        self.assertEqual(interval["raw_lower"], "90.0")
        self.assertTrue(interval["contains_reported_estimate"])

    def test_reversed_or_invented_interval_is_rejected(self):
        cell = self.cell()
        for interval in ({"lower": "99.0", "upper": "90.0", "label": "95% CI"},
                         {"lower": "89.0", "upper": "99.0", "label": "95% CI"},
                         {"lower": "90.0", "upper": "99.0", "label": "99% CI"}):
            cell["numeric"]["uncertainty"] = interval
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                self.prepare(cell)

    def test_interval_space_separated_signs_cannot_be_dropped(self):
        self.spec["fields"][0]["quantity"] = "difference"
        for sign in ("-", "+", "\u2212"):
            self.source_text("Population A under fixed conditions had difference -0.7 %; 95% CI [-1.0, " + sign + " 0.5].")
            cell = self.cell(raw="-0.7", quantity="difference")
            cell["numeric"]["uncertainty"] = {"lower": "-1.0", "upper": "0.5", "label": "95% CI"}
            with self.subTest(bound="upper", sign=sign), self.assertRaisesRegex(ValueError, "separated source sign"):
                self.prepare(cell)
            self.source_text("Population A under fixed conditions had difference 0.7 %; 95% CI [" + sign + " 0.5, 1.0].")
            cell = self.cell(raw="0.7", quantity="difference")
            cell["numeric"]["uncertainty"] = {"lower": "0.5", "upper": "1.0", "label": "95% CI"}
            with self.subTest(bound="lower", sign=sign), self.assertRaisesRegex(ValueError, "separated source sign"):
                self.prepare(cell)

    def test_interval_hyphen_between_numeric_bounds_remains_a_range_separator(self):
        self.source_text("Population A under fixed conditions had accuracy 1.5 %; 95% CI [1.0 - 2.0].")
        cell = self.cell(raw="1.5")
        cell["numeric"]["uncertainty"] = {"lower": "1.0", "upper": "2.0", "label": "95% CI"}
        interval = self.prepare(cell)["cells"][0]["numeric"]["uncertainty"]
        self.assertEqual((interval["lower"], interval["upper"]), ("0.010", "0.020"))

    def test_numeric_substring_and_changed_quantity_are_rejected(self):
        cell = self.cell(raw="5.0")
        with self.assertRaisesRegex(ValueError, "token"):
            self.prepare(cell)
        cell = self.cell(quantity="precision")
        with self.assertRaisesRegex(ValueError, "quantity"):
            self.prepare(cell)

    def test_signs_cannot_be_dropped_from_source_measurements(self):
        self.source_text("Population A under fixed conditions had difference -95.0 %.")
        with self.assertRaisesRegex(ValueError, "token"):
            self.prepare(self.cell())
        result = self.prepare(self.cell(raw="-95.0"))["cells"][0]["numeric"]
        self.assertEqual(result["value"], "-0.950")

    def test_units_cannot_be_guessed_or_arbitrarily_rescaled(self):
        cell = self.cell(raw_unit="s")
        with self.assertRaisesRegex(ValueError, "unit"):
            self.prepare(cell)
        self.spec["fields"][0]["unit"] = "score"
        with self.assertRaisesRegex(ValueError, "unsupported unit conversion"):
            self.prepare(self.cell())
        cell = self.cell()
        cell["numeric"]["scale"] = "1000"
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            self.prepare(cell)

    def test_unit_letters_inside_words_cannot_become_measurement_units(self):
        # 'conditions' contains s and 'CI' contains C, but neither establishes
        # seconds or degrees Celsius for the source's percentage measurement.
        for wrong_unit in ("s", "C"):
            self.spec["fields"][0]["unit"] = wrong_unit
            with self.subTest(unit=wrong_unit), self.assertRaisesRegex(ValueError, "complete token"):
                self.prepare(self.cell(raw_unit=wrong_unit))

    def test_space_separated_source_signs_cannot_be_silently_dropped(self):
        for sign in ("-", "+", "\u2212"):
            self.source_text("Population A under fixed conditions had accuracy " + sign + " 95.0 %.")
            with self.subTest(sign=sign), self.assertRaisesRegex(ValueError, "separated source sign"):
                self.prepare(self.cell())

    def test_nonfinite_or_overlarge_decimal_inputs_are_rejected(self):
        for raw in ("nan", "Infinity", "1e999", "True", 95, True):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.prepare(self.cell(raw=raw))

    def test_table_requires_original_headers_context_and_footnote_locations(self):
        self.source_text("Table 2 Population A fixed conditions Accuracy (%) Method X 95.0. Note: held-out split.")
        cell = self.cell()
        cell["source_context"] = {"kind": "table", "population": "Population A", "conditions": "fixed conditions",
                                  "table_label": "Table 2", "row_header": "Method X", "column_header": "Accuracy (%)",
                                  "footnotes": ["Note: held-out split."]}
        output = self.prepare(cell)["cells"][0]
        self.assertEqual(output["status"], "visual_pending")
        self.assertFalse(output["numeric"]["table_cell_alignment_verified"])
        self.assertFalse(output["eligible_for_quantitative_synthesis"])
        cell["source_context"]["column_header"] = "F1 (%)"
        with self.assertRaisesRegex(ValueError, "column_header"):
            self.prepare(cell)

    def test_fake_visual_coordinates_cannot_clear_table_review(self):
        self.source_text("Table 2 Population A fixed conditions Accuracy (%) Method X 95.0.")
        cell = self.cell()
        cell["source_context"] = {"kind": "table", "population": "Population A", "conditions": "fixed conditions",
                                  "table_label": "Table 2", "row_header": "Method X", "column_header": "Accuracy (%)", "footnotes": [],
                                  "visual_asset": {"path": "evidence/fake.png", "sha256": "0" * 64, "pdf_page": 1, "bbox": [0, 0, 10, 10]}}
        with self.assertRaisesRegex(ValueError, "visual_asset"):
            self.prepare(cell)

    def test_inferred_or_self_approved_numbers_are_rejected(self):
        cell = self.cell()
        cell["kind"] = "model_inference"
        cell["inference_boundary"] = "This is inferred."
        with self.assertRaisesRegex(ValueError, "cannot be inferred"):
            self.prepare(cell)
        cell = self.cell()
        cell["semantic_verification"] = True
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            self.prepare(cell)

    def test_source_location_does_not_certify_text_entailment(self):
        self.spec["fields"] = [{"id": "conclusion", "type": "text"}]
        cell = self.cell(text="This deliberately unrelated statement has not been semantically checked.")
        cell.update(field_id="conclusion")
        cell.pop("numeric"); cell.pop("source_context")
        output = self.prepare(cell)["cells"][0]
        self.assertEqual(output["status"], "located_pending_semantic_review")
        self.assertFalse(output["semantic_verification"])

    def test_changed_sources_stale_snapshots_and_missing_papers_block(self):
        self.prepare(self.cell())
        (self.project / self.paper["source"]["path"]).write_text("Changed input.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            matrix.build(self.project, self.spec)
        self.spec["paper_ids"] = ["absent"]
        self.source_text("Population A fixed conditions 95.0 %.")
        self.build()
        with self.assertRaisesRegex(ValueError, "missing, stale or invalid"):
            matrix.build(self.project, self.spec)

    def test_metadata_only_cannot_supply_numeric_measurements(self):
        self.paper["source_scope"] = "metadata_only"
        with self.assertRaisesRegex(ValueError, "metadata-only"):
            self.prepare(self.cell())

    def test_duplicate_cells_and_unknown_field_ids_are_rejected(self):
        cell = self.cell()
        self.spec["fields"].append({"id": "other", "type": "text"})
        self.spec["cells"] = [cell, copy.deepcopy(cell)]
        self.build()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            matrix.build(self.project, self.spec)
        self.spec["cells"] = [{**cell, "field_id": "missing"}]
        with self.assertRaisesRegex(ValueError, "out-of-scope"):
            matrix.build(self.project, self.spec)

    def test_output_csv_and_html_preserve_missing_cells_and_escape_text(self):
        self.spec["fields"] = [{"id": "text", "type": "text"}, {"id": "unknown", "type": "text"}]
        cell = self.cell(text='=HYPERLINK("unsafe") <script>alert(1)</script>')
        cell.update(field_id="text"); cell.pop("numeric"); cell.pop("source_context")
        report = self.prepare(cell)
        rows = list(csv.DictReader(io.StringIO(matrix.csv_text(report))))
        self.assertTrue(rows[0]["text"].startswith("'="))
        self.assertEqual(rows[1]["status"], "unknown")
        page = matrix.html_text(self.project, report)
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn('href="../../evidence/sources/a.txt"', page)

    def test_refresh_and_revalidation_make_no_paid_calls_and_detect_tamper(self):
        self.prepare(self.cell())
        write(self.project / matrix.REQUEST, self.spec)
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid call")):
            result = matrix.refresh(self.project)
            self.assertEqual(result["cell_count"], 1)
            self.assertTrue(matrix.validate_saved_report(self.project)["valid"])
        output = self.project / matrix.OUTPUT / "matrix.json"
        data = read(output)
        data["cells"][0]["numeric"]["value"] = "100"
        write(output, data)
        with self.assertRaisesRegex(ValueError, "output changed"):
            matrix.validate_saved_report(self.project)

    def test_changed_request_invalidates_saved_matrix(self):
        self.prepare(self.cell())
        write(self.project / matrix.REQUEST, self.spec)
        matrix.refresh(self.project)
        self.spec["question"] = "A different research comparison."
        write(self.project / matrix.REQUEST, self.spec)
        with self.assertRaisesRegex(ValueError, "request changed"):
            matrix.validate_saved_report(self.project)

    def test_request_and_output_paths_stay_within_native_project(self):
        self.prepare()
        for request in ("../outside.json", "state/run.json", "program/../outside.json"):
            with self.subTest(request=request), self.assertRaises(ValueError):
                matrix.refresh(self.project, request)
