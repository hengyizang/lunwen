"""Located source synthesis contracts, not evidence-strength validation."""
import copy
from unittest.mock import patch

from scripts import literature_matrix, literature_synthesis
from scripts.research_artifacts import read, sha, write
from tests.test_literature_workbench import WorkbenchFixture


class LiteratureSynthesisTests(WorkbenchFixture):
    def setUp(self):
        super().setUp()
        self.a = self.add_paper("a", "Calibration gains depend on the held-out device protocol.")
        self.b = self.add_paper("b", "Calibration gains disappear when test devices remain unseen.")
        self.card(self.a, field="findings")
        self.card(self.b, field="findings")
        self.build()
        matrix = {"schema_version": "1.0", "question": "Which conditions explain calibration differences?",
            "paper_ids": ["a", "b"], "fields": [{"id": "finding", "type": "text", "card_field": "findings"},
            {"id": "method", "type": "text", "card_field": "methods"}], "cells": []}
        write(self.project / "program/literature-extraction.json", matrix)
        report = literature_matrix.refresh(self.project)
        self.spec = {"schema_version": "1.0", "question": matrix["question"],
            "matrix": {"path": report["report"], "sha256": sha(self.project / report["report"])},
            "judgments": [{"id": "J1", "statement": "The apparent disagreement requires protocol matching.",
                "relation": "conflict", "axes": ["protocol", "population"],
                "supports": [{"paper_id": "a", "field_id": "finding"}],
                "contradicts": [{"paper_id": "b", "field_id": "finding"}],
                "assessment": {key: {"status": "unknown", "text": "Original methodology needs examination.", "cells": []}
                    for key in ("design", "bias", "comparability", "uncertainty")},
                "inference_boundary": "These synthetic statements do not establish matched experimental conditions.",
                "missing_evidence": ["Locate original device splits and tuning rules."]}],
            "outline": [{"title": "Calibration conditions", "purpose": "Explain the question.", "judgment_ids": [],
                "sections": [{"title": "Protocol differences", "purpose": "Organize located evidence.", "judgment_ids": [],
                    "sections": [{"title": "Unseen devices", "purpose": "Identify the discriminating protocol.", "judgment_ids": ["J1"]}]}]}]}

    def test_conflicts_unknowns_and_unaddressed_fields_remain_visible(self):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid pass")):
            report = literature_synthesis.build(self.project, self.spec)
        self.assertFalse(report["vote_counting_used"])
        self.assertFalse(report["semantic_support_verified"])
        self.assertEqual(len(report["unknown_cells"]), 2)
        self.assertEqual(len(report["all_matrix_cells_retained"]), 4)
        self.assertEqual(report["judgments"][0]["contradicts"][0]["paper_id"], "b")

    def test_agreement_cannot_hide_declared_contrary_evidence(self):
        self.spec["judgments"][0]["relation"] = "agreement"
        with self.assertRaisesRegex(ValueError, "contrary"):
            literature_synthesis.build(self.project, self.spec)

    def test_unknown_cells_cannot_be_used_as_support(self):
        self.spec["judgments"][0]["supports"][0]["field_id"] = "method"
        with self.assertRaisesRegex(ValueError, "unknown"):
            literature_synthesis.build(self.project, self.spec)

    def test_strength_interpretation_needs_actual_located_evidence(self):
        self.spec["judgments"][0]["assessment"]["bias"]["status"] = "interpretation"
        with self.assertRaisesRegex(ValueError, "located evidence"):
            literature_synthesis.build(self.project, self.spec)
        self.spec["judgments"][0]["assessment"]["bias"]["status"] = "verified"
        with self.assertRaisesRegex(ValueError, "automated verified"):
            literature_synthesis.build(self.project, self.spec)

    def test_repeated_same_source_is_not_cross_paper_confirmation(self):
        self.spec["judgments"][0]["contradicts"][0]["paper_id"] = "a"
        with self.assertRaisesRegex(ValueError, "two source"):
            literature_synthesis.build(self.project, self.spec)

    def test_inference_boundary_and_disagreement_conditions_are_required(self):
        self.spec["judgments"][0]["inference_boundary"] = ""
        with self.assertRaises(ValueError):
            literature_synthesis.build(self.project, self.spec)
        self.spec["judgments"][0]["inference_boundary"] = "Pending original-source review."
        self.spec["judgments"][0]["axes"] = []
        with self.assertRaisesRegex(ValueError, "conditions"):
            literature_synthesis.build(self.project, self.spec)

    def test_outline_is_three_levels_and_covers_every_registered_judgment(self):
        self.spec["outline"][0]["sections"][0]["sections"][0]["judgment_ids"] = []
        with self.assertRaisesRegex(ValueError, "leaf"):
            literature_synthesis.build(self.project, self.spec)

    def test_matrix_or_scope_changes_invalidate_synthesis(self):
        self.spec["question"] = "A different question"
        with self.assertRaisesRegex(ValueError, "scope"):
            literature_synthesis.build(self.project, self.spec)

    def test_refresh_has_escaped_outline_and_rejects_source_or_output_tamper(self):
        write(self.project / "program/literature-synthesis.json", self.spec)
        report = literature_synthesis.refresh(self.project)
        self.assertTrue(literature_synthesis.validate_saved_report(self.project)["valid"])
        saved = self.project / report["report"]
        changed = read(saved)
        changed["semantic_support_verified"] = True
        write(saved, changed)
        with self.assertRaisesRegex(ValueError, "changed"):
            literature_synthesis.validate_saved_report(self.project)

    def test_changed_matrix_request_cannot_reuse_older_synthesis(self):
        request = read(self.project / "program/literature-extraction.json")
        request["question"] = "Changed matrix question"
        write(self.project / "program/literature-extraction.json", request)
        with self.assertRaisesRegex(ValueError, "request changed"):
            literature_synthesis.build(self.project, self.spec)
