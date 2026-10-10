"""Integration checks for complete editorial coverage and controlled cleanup."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import academic_style, api_orchestrator, autopilot, cloud_research_steps


def manuscript_text() -> str:
    return "\n\n".join(
        f"Registered comparison {i} estimated the paired difference in the eligible cohort "
        f"using prespecified measurements and reported uncertainty under the documented sampling conditions."
        for i in range(40)
    )


def complete_notes() -> list[str]:
    return [
        f"rejected: {code} Retained the scientifically necessary wording after contextual evidence review."
        for code in [*(f"H{i:02d}" for i in range(1, 27)), *(f"AD{i:02d}" for i in range(1, 9))]
    ]


class EditorialIntegrationTests(unittest.TestCase):
    def test_current_audit_contains_complete_recomputable_reviews(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            manuscript = project / "papers/P01/manuscript/main.tex"
            manuscript.parent.mkdir(parents=True)
            manuscript.write_text(manuscript_text(), encoding="utf-8")
            with patch.object(academic_style, "run_proselint", return_value={"status": "unavailable", "name": "proselint"}), patch.object(
                academic_style, "run_harper", return_value={"status": "unavailable", "name": "harper"}
            ):
                _, report = academic_style.write_audit(project, "P01")
            humanizer = report["analysis"]["humanizer_review"]
            defensive = report["analysis"]["anti_defensive_review"]
            self.assertEqual([row["number"] for row in humanizer["coverage"]], list(range(1, 27)))
            self.assertEqual([row["review_id"] for row in defensive["coverage"]], [f"AD{i:02d}" for i in range(1, 9)])
            self.assertTrue(humanizer["coverage_complete"])
            self.assertFalse(report["detector_score_used"])
            # A forged, incomplete nested coverage cannot hide behind a passing status.
            report["analysis"]["humanizer_review"]["coverage"].pop()
            report["status"] = "pass"
            report["errors"] = []
            academic_style.report_path(manuscript.parent.parent).write_text(json.dumps(report), encoding="utf-8")
            errors = academic_style.validate_saved_audit(manuscript.parent.parent)
            self.assertTrue(any("humanizer_review" in error for error in errors))

    def test_both_writer_paths_receive_full_skills_only_at_g5(self):
        api_prompt = api_orchestrator.writer_prompt("missing-project", "writing-and-review", "")
        api_remediation = api_orchestrator.remediation_prompt("missing-project", "writing-and-review", "", "{}")
        state = {"stage": "writing-and-review", "gate": "G5", "active_paper": "P01"}
        cli_prompt = autopilot.writer_prompt("demo", state, {"contract": "Writing and review"}, "", autopilot.ROOT / "plan.json")
        cli_remediation = autopilot.remediation_prompt("demo", state, autopilot.ROOT / "review.json")
        for value in (api_prompt, api_remediation, cli_prompt, cli_remediation):
            for code in ("H01", "H26", "AD01", "AD08"):
                self.assertIn(code, value)
            self.assertIn("watermark_cleanup", value)
        self.assertNotIn("H26", api_orchestrator.editorial_prompt_contract("topic-intelligence"))

    def test_every_pattern_needs_its_own_substantive_disposition(self):
        notes = complete_notes()
        api_orchestrator.validate_editorial_dispositions(notes, "writing-and-review")
        for bad in (notes[:-1], notes[:-9], notes + [notes[0]], ["fixed: H01 done"] + notes[1:]):
            with self.subTest(notes=bad):
                with self.assertRaises(ValueError):
                    api_orchestrator.validate_editorial_dispositions(bad, "writing-and-review")
        api_orchestrator.validate_editorial_dispositions([], "topic-intelligence")

    def test_api_writer_cannot_forge_cleanup_candidates_or_receipts(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api_orchestrator, "ROOT", Path(directory)):
            for value in ("reports/watermark-cleanup/a/candidate.tex",
                          "reports/watermark-cleanup/a/receipt.json",
                          "Reports/Watermark-Cleanup/a/diff.txt"):
                with self.subTest(path=value):
                    with self.assertRaises(ValueError):
                        api_orchestrator.safe_target("demo", value)

    def test_cli_writer_cleanup_tampering_is_restored_and_new_forgery_removed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(autopilot.researchctl, "PROJECTS_ROOT", Path(directory)):
            project = Path(directory) / "demo"
            target = project / "reports/watermark-cleanup/a/receipt.json"
            target.parent.mkdir(parents=True)
            target.write_text("original", encoding="utf-8")
            before = autopilot.protected_control_snapshot("demo")
            target.write_text("forged", encoding="utf-8")
            forged = project / "reports/watermark-cleanup/b/candidate.tex"
            forged.parent.mkdir(parents=True)
            forged.write_text("fake", encoding="utf-8")
            with self.assertRaises(autopilot.AutopilotError):
                autopilot.ensure_protected_control_unchanged("demo", before)
            self.assertEqual(target.read_text(encoding="utf-8"), "original")
            self.assertFalse(forged.exists())

    def test_two_pass_snapshots_preserve_initial_report(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api_orchestrator, "ROOT", Path(directory)):
            project = Path(directory) / "projects/demo"
            source = project / "papers/P01/style/academic-style-audit.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"pass":"initial"}', encoding="utf-8")
            summary = {"path": source.relative_to(project).as_posix()}
            initial = api_orchestrator.snapshot_editorial_pass("demo", "run1", "initial", summary)
            source.write_text('{"pass":"final"}', encoding="utf-8")
            final = api_orchestrator.snapshot_editorial_pass("demo", "run1", "final", summary)
            self.assertEqual(json.loads((project / initial["snapshot_path"]).read_text())["pass"], "initial")
            self.assertEqual(json.loads((project / final["snapshot_path"]).read_text())["pass"], "final")
            self.assertNotEqual(initial["snapshot_sha256"], final["snapshot_sha256"])

    def test_cloud_queue_performs_real_cleanup_once_and_reuses_current_receipt(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False):
            project = Path(directory)
            source = project / "papers/P01/manuscript/main.txt"
            source.parent.mkdir(parents=True)
            source.write_text("The pro\u200bse reports the registered comparison.", encoding="utf-8")
            program = project / "program"
            program.mkdir()
            request = {"stage": "writing-and-review", "action": "watermark_cleanup",
                       "paper_id": "P01", "source": source.relative_to(project).as_posix(),
                       "expected_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
            (program / "cloud-operations.json").write_text(json.dumps({"operations": [request]}), encoding="utf-8")
            first = cloud_research_steps.after_write(project, "writing-and-review")
            second = cloud_research_steps.after_write(project, "writing-and-review")
            self.assertEqual(first["operation_errors"], [])
            self.assertEqual(second["operation_errors"], [])
            candidates = list((project / "reports/watermark-cleanup").glob("*/candidate.txt"))
            self.assertEqual(len(candidates), 1)
            self.assertIn("prose", candidates[0].read_text(encoding="utf-8"))
            self.assertIn("\u200b", source.read_text(encoding="utf-8"))

