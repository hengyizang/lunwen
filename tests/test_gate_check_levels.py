"""Native A/C boundaries: observations do not waive preservation or real facts.

All documents, identities and cloud environment flags below are inert software
fixtures. No model is invoked and no scientific acceptance is asserted.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import manuscript_hygiene as hygiene, output_provenance, researchctl, revision_integrity
from scripts.research_artifacts import read, sha, write
from tests import test_quality_gate as quality_fixtures


class GateCheckLevelTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "project"
        self.paper = self.project / "papers/P01"
        self.source = self.paper / "manuscript/main.tex"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("\\section{Introduction}\nSynthetic study scope.\n", encoding="utf-8")
        guard = patch("scripts.model_runtime.call", side_effect=AssertionError("no model calls in native gate fixtures"))
        guard.start()
        self.addCleanup(guard.stop)

    def cleanup(self):
        self.source.write_text("\\section{Introduction}\nOrdinary\u200b synthetic prose.\n", encoding="utf-8")
        output_provenance.record_model_writes(self.project, [self.source], family="openai",
            provider="synthetic-gate-fixture", model="fixture", role="writer", run_id="fixture")
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            result = hygiene.refresh(self.project, "P01", apply=True)
        self.assertEqual(len(result["changes"]), 1)
        self.assertNotIn("\u200b", self.source.read_text(encoding="utf-8"))
        return self.project / result["changes"][0]

    def save_integrity(self, before, after):
        baseline = self.paper / "reviews/revision-base/main.tex"
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(before, encoding="utf-8")
        self.source.write_text(after, encoding="utf-8")
        # An incomplete C-level editing ledger cannot manufacture approval or
        # prevent the independent A-level comparison of protected science.
        write(self.paper / "reviews/revision-ledger.json", {})
        result = revision_integrity.audit(self.paper, include_ledger=False)
        write(self.paper / "reviews/revision-integrity.json", result)
        return result

    def test_missing_style_report_is_observed_and_is_not_an_original_integrity_failure(self):
        self.assertFalse((self.project / hygiene.PREFIX / "P01/latest.json").exists())
        self.assertEqual(hygiene.integrity_errors(self.project, "P01"), [])
        warnings = []
        self.assertIsNone(researchctl.paper_observations(self.project, "P01", warnings))
        self.assertTrue(any("academic style" in note for note in warnings))
        self.assertTrue(any("manuscript hygiene" in note for note in warnings))

    def test_missing_latest_style_report_does_not_invalidate_real_preserved_cleanup(self):
        self.cleanup()
        (self.project / hygiene.PREFIX / "P01/latest.json").unlink()
        self.assertEqual(hygiene.integrity_errors(self.project, "P01"), [])
        warnings = []
        researchctl.paper_observations(self.project, "P01", warnings)
        self.assertTrue(any("manuscript hygiene" in note for note in warnings))

    def test_deleted_cleanup_original_still_blocks_despite_observational_style(self):
        receipt = self.cleanup()
        (receipt.parent / "original.tex").unlink()
        self.assertTrue(hygiene.integrity_errors(self.project, "P01"))
        warnings = []
        researchctl.paper_observations(self.project, "P01", warnings)
        self.assertTrue(warnings)
        self.assertTrue(hygiene.integrity_errors(self.project, "P01"))

    def test_tampered_cleanup_receipt_still_blocks_even_without_latest_style_report(self):
        receipt = self.cleanup()
        (self.project / hygiene.PREFIX / "P01/latest.json").unlink()
        value = read(receipt)
        value["original_preserved"] = False
        write(receipt, value)
        self.assertTrue(hygiene.integrity_errors(self.project, "P01"))

    def test_empty_editing_ledger_does_not_block_a_revision_preserving_scientific_content(self):
        result = self.save_integrity("The method works.\n", "The method performs.\n")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(revision_integrity.validate_saved_report(self.paper, include_ledger=False), [])
        self.assertTrue(revision_integrity.validate_saved_report(self.paper, include_ledger=True))

    def test_scientific_changes_stay_blocking_while_optional_disclosure_is_editable(self):
        before = ("\\section{Results}\n"
            "The estimate is 12.3 mg.\n"
            "The negative finding remains important.\n"
            "The null comparison did not detect an effect.\n"
            "The registered sensitivity run failed.\n"
            "\\section{AI Disclosure}\n"
            "The authors used AI assistance to draft this manuscript.\n")
        changes = {
            "number": before.replace("12.3", "99.9"),
            "negative": before.replace("The negative finding remains important.\n", ""),
            "null": before.replace("The null comparison did not detect an effect.\n", ""),
            "failed": before.replace("The registered sensitivity run failed.\n", ""),
            "disclosure": before.replace("The authors used AI assistance to draft this manuscript.\n", ""),
        }
        for name, after in changes.items():
            with self.subTest(removed=name):
                result = self.save_integrity(before, after)
                self.assertEqual(result["status"], "pass" if name == "disclosure" else "fail")
                errors = revision_integrity.validate_saved_report(self.paper, include_ledger=False)
                self.assertEqual(any("protected revision changes" in error for error in errors), name != "disclosure", errors)
                self.assertFalse(any("stale" in error for error in errors), errors)

    def test_missing_optional_quality_report_is_only_a_warning(self):
        errors, warnings = [], []
        researchctl.quality_errors(self.project, "G1", errors, warnings=warnings)
        self.assertEqual(errors, [])
        self.assertTrue(any("no optional quality assessment" in note for note in warnings))

    def test_actual_source_conflicts_reach_the_native_scientific_check(self):
        with patch("scripts.literature_source_tasks.integrity_errors", return_value=["claim C1 contradicts its current source"]) as check:
            errors = researchctl.paper_scientific_errors(self.project, "P01")
        check.assert_called_once_with(self.project, "P01", require_support=False)
        self.assertIn("P01 full-text citation support: claim C1 contradicts its current source", errors)

    def test_final_writing_requires_support_in_the_shared_scientific_check(self):
        write(self.project / "state/run.json", {"active_paper": "P01", "writing_phases": {"P01": "submission"}})
        with patch("scripts.literature_source_tasks.integrity_errors", return_value=[]) as check:
            researchctl.paper_scientific_errors(self.project, "P01")
        check.assert_called_once_with(self.project, "P01", require_support=True)

    def test_figure_appearance_is_c_but_changed_data_and_deleted_figures_remain_a(self):
        from scripts import figure_provenance
        from tests.figure_lineage_fixtures import sealed_run
        sealed_run(self.project)
        renderer = self.project / "analysis/chart.py"
        renderer.write_text("# Deterministic synthetic source, not a research result.\n")
        output_provenance.record_model_writes(self.project, [renderer], family="openai",
            provider="synthetic-gate-fixture", model="fixture", role="renderer", run_id="fixture")
        figure = self.paper / "figures/result.png"
        figure.parent.mkdir(parents=True)
        figure.write_bytes(b"Synthetic output identity fixture")
        figure_provenance.record_figure(self.project, "P01", "papers/P01/figures/result.png",
            "data_chart", "analysis/chart.py", ["results/metrics.csv"], ["r1"])
        with patch("scripts.automated_visual_review.verify", return_value=["layout and English labels need revision"]) as visual:
            errors = researchctl.paper_scientific_errors(self.project, "P01")
            self.assertFalse(any("figure provenance" in issue for issue in errors), errors)
            visual.assert_not_called()
            warnings = []
            researchctl.paper_observations(self.project, "P01", warnings)
            self.assertTrue(any("figure appearance" in issue and "English labels" in issue for issue in warnings), warnings)
            data = self.project / "results/metrics.csv"
            data.write_text("Unsealed changed result data\n")
            errors = researchctl.paper_scientific_errors(self.project, "P01")
            self.assertTrue(any("figure provenance" in issue and "input hash is stale" in issue for issue in errors), errors)
            figure.unlink()
            errors = researchctl.paper_scientific_errors(self.project, "P01")
            self.assertTrue(any("stale/extra figure records" in issue for issue in errors), errors)

    def test_cleanup_scan_refresh_does_not_change_binding_but_original_loss_remains_a(self):
        receipt = self.cleanup()
        before = hygiene.integrity_binding(self.project, "P01")
        latest = self.project / hygiene.PREFIX / "P01/latest.json"
        latest.unlink()
        self.assertEqual(hygiene.integrity_binding(self.project, "P01"), before)
        self.assertEqual(hygiene.integrity_errors(self.project, "P01"), [])
        (receipt.parent / "original.tex").unlink()
        self.assertTrue(hygiene.integrity_errors(self.project, "P01"))

    def test_scientific_response_fields_are_validated_in_the_existing_audit(self):
        audit = {"verdict": "pass-with-conditions", **{field: [] for field in (
            "fatal_findings", "major_findings", "minor_findings", "missing_evidence", "remediation_steps", "uncertainty")},
            "claim_evidence": [{"claim_id": "C1", "outcome": "insufficient"}]}
        errors = []
        self.assertTrue(researchctl.audit_document_valid(Path("critic.json"), audit, errors), errors)
        audit["claim_evidence"] = "unstructured result"
        self.assertFalse(researchctl.audit_document_valid(Path("critic.json"), audit, []))
        audit["claim_evidence"] = []
        audit["unrecognized_authority"] = True
        self.assertFalse(researchctl.audit_document_valid(Path("critic.json"), audit, []))

    def test_quality_score_warning_does_not_waive_actual_factual_source_drift(self):
        source = self.project / "facts.txt"
        source.write_text("Synthetic located scientific evidence.\n", encoding="utf-8")
        value = quality_fixtures.report("G1")
        value["scores"]["novelty"] = 1
        value.pop("venue_readiness")
        value["assessments"] = {"novelty": {"status": "satisfied", "rationale": "Synthetic located factual record",
            "source_anchors": [{"path": "facts.txt", "sha256": sha(source), "locator": "L1",
                                "excerpt": "Synthetic located scientific evidence."}]}}
        write(self.project / "program/quality-G1.json", value)
        errors, warnings = [], []
        researchctl.quality_errors(self.project, "G1", errors, warnings=warnings)
        self.assertEqual(errors, [])
        self.assertTrue(any("scores.novelty" in note for note in warnings))
        source.write_text("Changed underlying scientific source.\n", encoding="utf-8")
        errors = []
        researchctl.quality_errors(self.project, "G1", errors, warnings=warnings)
        self.assertTrue(any("stale source hash" in error for error in errors), errors)

    def test_stale_c_level_assessment_source_remains_an_observation(self):
        from scripts.quality_gate import DIMENSIONS, OBSERVATIONAL_CRITERIA
        science = self.project / "facts.txt"
        observation = self.project / "venue-notes.txt"
        science.write_text("Synthetic located scientific evidence.\n", encoding="utf-8")
        observation.write_text("Synthetic publication planning observation.\n", encoding="utf-8")
        value = quality_fixtures.report("G1")
        value["schema_version"] = "1.2"
        value["assessments"] = {}
        for criterion in DIMENSIONS["G1"]:
            source = observation if criterion in OBSERVATIONAL_CRITERIA else science
            value["assessments"][criterion] = {"status": "satisfied", "rationale": "Synthetic source-bound fixture",
                "source_anchors": [{"path": source.name, "sha256": sha(source), "locator": "L1",
                                    "excerpt": source.read_text().strip()}]}
        write(self.project / "program/quality-G1.json", value)
        observation.write_text("Changed optional publication planning note.\n", encoding="utf-8")
        errors, warnings = [], []
        researchctl.quality_errors(self.project, "G1", errors, warnings=warnings)
        self.assertEqual(errors, [])
        self.assertTrue(any("publication_potential: stale source hash" in note for note in warnings), warnings)
