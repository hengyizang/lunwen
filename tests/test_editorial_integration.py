"""Integration checks for optional editorial observations and controlled cleanup."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import (
    academic_style,
    api_orchestrator,
    cloud_research_steps,
    output_provenance,
    research_improvementctl,
)


def manuscript_text() -> str:
    return "\n\n".join(
        f"Registered comparison {i} estimated the paired difference in the eligible cohort "
        f"using prespecified measurements and reported uncertainty under the documented sampling conditions."
        for i in range(40)
    )


class EditorialIntegrationTests(unittest.TestCase):
    def test_current_audit_reports_retired_mechanics_without_fabricating_semantic_review(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            manuscript = project / "papers/P01/manuscript/main.tex"
            manuscript.parent.mkdir(parents=True)
            manuscript.write_text(manuscript_text(), encoding="utf-8")
            with patch.object(academic_style, "find_proselint", return_value=None), patch.object(
                academic_style, "find_harper", return_value=None
            ):
                _, report = academic_style.write_audit(project, "P01")
            self.assertEqual(report["analysis"]["editorial_methods"], {
                "status": "retired", "mechanical_review_performed": False, "semantic_review_status": "unknown"})
            self.assertNotIn("humanizer_review", report["analysis"])
            self.assertNotIn("anti_defensive_review", report["analysis"])
            report["analysis"]["editorial_methods"]["mechanical_review_performed"] = True
            academic_style.report_path(manuscript.parent.parent).write_text(json.dumps(report), encoding="utf-8")
            self.assertTrue(academic_style.validate_saved_audit(manuscript.parent.parent))

    @patch("scripts.research_phase.writing_phase",return_value="submission")
    def test_shared_writer_roles_receive_optional_observations_in_submission_phase(self, phase):
        api_prompt = api_orchestrator.writer_prompt("missing-project", "writing-and-review", "")
        api_remediation = api_orchestrator.remediation_prompt("missing-project", "writing-and-review", "", "{}")
        api_critic = api_orchestrator.critic_prompt("missing-project", "writing-and-review", "")
        for value in (api_prompt, api_remediation,   api_critic, ):
            for code in ("H01", "H26", "AD01", "AD08"):
                self.assertIn(code, value)
            self.assertIn("Empty or partial observation lists are valid", value)
            self.assertNotIn("Apply every CFH", value)
            self.assertNotIn("as the two editorial passes", value)
        for value in (api_prompt, api_remediation,  ):
            self.assertIn("watermark_cleanup", value)
        for value in (api_critic, ):
            self.assertIn("read-only independent adversarial scientific reviewer", value)
            self.assertNotIn("In remediation notes", value)
            self.assertIn("Use actual scientific sources and relevant observations in a read-only independent review.", value)
        self.assertNotIn("Inspect protected_signals", api_prompt)
        self.assertNotIn("H26", api_orchestrator.editorial_prompt_contract("topic-intelligence"))


    def test_evidence_led_narrative_reaches_all_existing_g5_roles(self):
        prompts = [
            api_orchestrator.writer_prompt("missing-project", "writing-and-review", ""),
            api_orchestrator.remediation_prompt("missing-project", "writing-and-review", "", "{}"),
            api_orchestrator.critic_prompt("missing-project", "writing-and-review", "secret-preferred-verdict"),
        ]
        for prompt in prompts:
            with self.subTest(role=prompt[:80]):
                for instruction in (
                    "evidence-led narrative", "strongest supported contribution",
                    "before results", "normal approval", "post-hoc",
                    "fixed evaluation criteria", "negative/null/adverse results",
                ):
                    self.assertIn(instruction, prompt.lower())
                self.assertNotIn("Lead the abstract and conclusion with the preregistered primary finding", prompt)
                self.assertNotIn("secret-preferred-verdict", prompt)
        # Narrative quality and independent science review do not require style scorecards.

    def test_retired_legacy_reports_never_supply_a_claimed_mechanical_or_semantic_pass(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api_orchestrator, "ROOT", Path(directory)):
            project = Path(directory) / "projects/demo"
            (project / "state").mkdir(parents=True)
            (project / "state/run.json").write_text('{"active_paper":"P01","writing_phases":{"P01":"submission"}}')
            report = project / "papers/P01/style/academic-style-audit.json"
            report.parent.mkdir(parents=True)
            report.write_text(json.dumps({"analysis": {"anti_defensive_review": {"status": "pass"}}}))
            result = json.loads(api_orchestrator.editorial_feedback("demo", "writing-and-review"))
            self.assertEqual(result["editorial_methods"]["status"], "unavailable")
            self.assertEqual(result["editorial_methods"]["semantic_review_status"], "unknown")
            self.assertEqual(result["reviews"], {})

    def test_api_writer_cannot_forge_cleanup_candidates_or_receipts(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api_orchestrator, "ROOT", Path(directory)):
            for value in ("reports/watermark-cleanup/a/candidate.tex",
                          "reports/watermark-cleanup/a/receipt.json",
                          "Reports/Watermark-Cleanup/a/diff.txt"):
                with self.subTest(path=value):
                    with self.assertRaises(ValueError):
                        api_orchestrator.safe_target("demo", value)


    def test_api_bundle_cannot_reach_cleanup_records_through_symlink_aliases(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(api_orchestrator, "ROOT", Path(directory)):
            project = Path(directory) / "projects/demo"
            target = project / "reports/watermark-cleanup/a/receipt.json"
            target.parent.mkdir(parents=True)
            target.write_text("original receipt", encoding="utf-8")
            (project / "program").mkdir()
            try:
                (project / "program/receipt-alias.json").symlink_to(target)
                (project / "program/reports-alias").symlink_to(target.parent, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"This runner cannot create the symlinks required by this test: {exc}")
            for alias in ("program/receipt-alias.json", "program/reports-alias/receipt.json"):
                with self.subTest(alias=alias), self.assertRaisesRegex(ValueError, "symlink"):
                    api_orchestrator.apply_bundle("demo", {"stage": "writing-and-review", "artifacts": [
                        {"path": alias, "content": "forged receipt"}
                    ]}, "writing-and-review")
            self.assertEqual(target.read_text(encoding="utf-8"), "original receipt")

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

    def test_cli_editorial_audit_revise_is_an_unsuccessful_exit(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False):
            root = Path(directory)
            (root / "projects/demo").mkdir(parents=True)
            with patch.object(research_improvementctl, "ROOT", root), patch("sys.argv", ["ctl", "editorial-audit", "--project", "demo", "--paper", "P01"]), patch(
                "scripts.academic_style.write_audit", return_value=(root / "audit.json", {"status": "revise"})
            ):
                self.assertEqual(research_improvementctl.main(), 1)

    def test_shared_controller_executes_declared_editorial_operation(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False), patch.object(
            api_orchestrator, "ROOT", Path(directory)
        ):
            project = Path(directory) / "projects/demo"
            source = project / "papers/P01/manuscript/main.txt"
            source.parent.mkdir(parents=True)
            source.write_text("The pro\u200bse is evidence-bound.", encoding="utf-8")
            (project / "state").mkdir()
            (project / "state/run.json").write_text(json.dumps({"active_paper": "P01"}), encoding="utf-8")
            (project / "program").mkdir()
            (project / "program/cloud-operations.json").write_text(json.dumps({"operations": [{
                "stage": "writing-and-review", "action": "watermark_cleanup", "paper_id": "P01",
                "source": source.relative_to(project).as_posix(),
                "expected_sha256": hashlib.sha256(source.read_bytes()).hexdigest()
            }]}), encoding="utf-8")
            with patch.object(api_orchestrator, "refresh_academic_style_audit", return_value=None):
                result = api_orchestrator.refresh_post_write_evidence("demo", "writing-and-review", "run", "initial")
            self.assertEqual(result["controlled_steps"]["operation_errors"], [])
            self.assertEqual(len(list((project / "reports/watermark-cleanup").glob("*/candidate.txt"))), 1)
            other_stage = api_orchestrator.refresh_post_write_evidence("demo", "topic-intelligence", "run", "initial")["controlled_steps"]
            self.assertEqual(other_stage["stage"], "topic-intelligence")
            self.assertEqual(other_stage["operation_errors"], [])
            self.assertEqual(len(list((project / "reports/watermark-cleanup").glob("*/candidate.txt"))), 1)

    def test_shared_controller_audit_the_built_word_manuscript_after_each_pass(self):
        controller = api_orchestrator
        with self.subTest(controller=controller.__name__), tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"GITHUB_ACTIONS": "true"}, clear=False
        ), patch.object(api_orchestrator, "ROOT", Path(directory)), patch.object(
            academic_style, "find_proselint", return_value=None
        ), patch.object(academic_style, "find_harper", return_value=None):
            project = Path(directory) / "projects/demo"
            paper = project / "papers/P01"
            source = paper / "manuscript/draft.md"
            source.parent.mkdir(parents=True)
            source.write_text(manuscript_text(), encoding="utf-8")
            metadata = paper / "manuscript/metadata.json"
            metadata.write_text(json.dumps({"schema_version": "1.0", "title": "Registered comparison",
                "abstract": "We report the prespecified cohort comparison.", "authors": [{"name": "Test Author"}],
                "keywords": ["cohort", "comparison", "uncertainty"]}), encoding="utf-8")
            (project / "state").mkdir()
            (project / "state/run.json").write_text(json.dumps({"active_paper": "P01", "writing_phases":{"P01":"submission"}}), encoding="utf-8")
            (project / "program").mkdir()
            (project / "program/cloud-operations.json").write_text(json.dumps({"operations": [{
                "stage": "writing-and-review", "action": "docx", "source": source.relative_to(project).as_posix(),
                "metadata": metadata.relative_to(project).as_posix(), "output": "papers/P01/manuscript/main.docx"
            }]}), encoding="utf-8")
            snapshots = []
            for phase in ("initial", "final"):
                if phase == "final":
                    source.write_text(source.read_text(encoding="utf-8") + "\n\nThe revised analysis retained all registered outcomes.", encoding="utf-8")
                output_provenance.record_model_writes(project, [source, metadata], family="openai", provider="test",
                    model="fixture", role="writer", run_id=phase)
                result = controller.refresh_post_write_evidence("demo", "writing-and-review", "run", phase)
                self.assertEqual(result["controlled_steps"]["operation_errors"], [])
                self.assertTrue((source.parent / "main.docx").is_file())
                errors = academic_style.validate_saved_audit(paper)
                self.assertFalse(any("stale" in error or "does not match" in error or "coverage" in error for error in errors), errors)
                snapshots.append(project / result["academic_style_audit"]["snapshot_path"])
            initial = json.loads(snapshots[0].read_text(encoding="utf-8"))
            final = json.loads(snapshots[1].read_text(encoding="utf-8"))
            self.assertNotEqual(initial["manuscript"]["source_tree_sha256"], final["manuscript"]["source_tree_sha256"])
