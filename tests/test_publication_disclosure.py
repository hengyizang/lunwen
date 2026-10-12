"""Disclosure policy/source/placement regressions, using synthetic policy fixtures."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import publication_disclosure as disclosure
from scripts.research_artifacts import read, sha, write


class PublicationDisclosureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "project"
        self.paper = self.project / "papers/P01"
        self.manuscript = self.paper / "manuscript/main.tex"
        self.manuscript.parent.mkdir(parents=True)
        self.statement = "The authors used a synthetic drafting tool and verified every statement against the research evidence."
        self.manuscript.write_text("\\section{Abstract}\nSynthetic study.\n\\section{Declarations}\n" + self.statement + "\n", encoding="utf-8")
        self.evidence = self.project / "evidence/policy.txt"
        self.evidence.parent.mkdir()
        self.evidence.write_text("Synthetic fixture policy, not an actual journal policy.\nDisclose drafting assistance in a manuscript declaration.\n", encoding="utf-8")
        write(self.paper / "venue.json", {"venue_id": "synthetic-venue", "official_domains": ["publisher.example"]})
        self.inputs = {"status": "ready_for_review", "ai_use": {"tools": [{"name": "Synthetic tool",
            "purpose": "Drafting prose from author-approved research evidence."}],
            "human_oversight": "A named author checks all science, sources and final wording."},
            "ai_policy": {"venue_id": "synthetic-venue", "official_url": "https://publisher.example/policy",
                "checked_at": datetime.now(timezone.utc).isoformat(), "requirement": "required",
                "required_placement": "either",
                "rationale": "The synthetic fixture use includes drafting and this fixture policy requires a declaration.",
                "evidence": {"path": "evidence/policy.txt", "sha256": sha(self.evidence), "start_line": 2,
                    "end_line": 2, "quote": "Disclose drafting assistance in a manuscript declaration."},
                "statement": {"placement": "manuscript", "excerpt": self.statement,
                    "location": {"kind": "source_lines", "path": "manuscript/main.tex",
                        "sha256": sha(self.manuscript), "start_line": 4, "end_line": 4}}}}
        self.save()
        cloud = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"})
        cloud.start()
        self.addCleanup(cloud.stop)

    def save(self):
        write(self.paper / "disclosures.json", self.inputs)

    def audit(self):
        return disclosure.audit(self.project, "P01")

    def test_required_statement_is_source_bound_without_rewriting_or_paid_calls(self):
        original = self.manuscript.read_bytes()
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no model call")):
            result = disclosure.refresh(self.project, "P01")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(disclosure.validate_saved_report(self.project, "P01"), [])
        self.assertEqual(self.manuscript.read_bytes(), original)
        self.assertFalse(result["manuscript_label_added"])
        self.assertEqual(result["paid_calls"], 0)
        self.assertTrue(result["human_policy_interpretation_review_required"])

    def test_not_required_keeps_internal_usage_without_manuscript_branding(self):
        policy = self.inputs["ai_policy"]
        policy["requirement"] = "not_required"
        del policy["statement"]
        self.manuscript.write_text("\\section{Abstract}\nSynthetic study.\n", encoding="utf-8")
        self.save()
        result = disclosure.refresh(self.project, "P01")
        self.assertEqual(result["status"], "pass")
        self.assertIsNone(result["statement"])
        self.assertEqual(read(self.paper / "disclosures.json")["ai_use"], self.inputs["ai_use"])
        self.assertNotIn("AI", self.manuscript.read_text())

    def test_missing_or_unresolved_policy_cannot_be_waived_by_watermark_results(self):
        original = copy.deepcopy(self.inputs)
        for requirement in (None, "unknown", "conditional", "not_required_because_no_watermark"):
            with self.subTest(requirement=requirement):
                self.inputs = copy.deepcopy(original)
                self.inputs["ai_policy"]["requirement"] = requirement
                self.inputs["watermark_absence_verified"] = True
                self.save()
                self.assertEqual(self.audit()["status"], "blocked")
        self.inputs.pop("ai_policy")
        self.save()
        self.assertEqual(self.audit()["status"], "blocked")

    def test_stale_future_and_timezone_free_policy_checks_block(self):
        current = datetime.now(timezone.utc)
        for checked in ((current - timedelta(days=31)).isoformat(), (current + timedelta(days=1)).isoformat(), "2026-01-01T00:00:00"):
            with self.subTest(checked=checked):
                self.inputs["ai_policy"]["checked_at"] = checked
                self.save()
                self.assertEqual(self.audit()["status"], "blocked")

    def test_wrong_venue_unofficial_url_and_credential_url_block(self):
        original = copy.deepcopy(self.inputs)
        mutations = [("venue_id", "another-venue"), ("official_url", "https://unrelated.example/policy"),
            ("official_url", "http://publisher.example/policy"),
            ("official_url", "https://secret@publisher.example/policy")]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                self.inputs = copy.deepcopy(original)
                self.inputs["ai_policy"][field] = value
                self.save()
                self.assertEqual(self.audit()["status"], "blocked")

    def test_policy_quote_hash_and_lines_are_real_and_current(self):
        original = copy.deepcopy(self.inputs)
        mutations = [("sha256", "0" * 64), ("quote", "An assertion absent from the preserved policy text."),
            ("start_line", 3), ("start_line", True), ("path", "../external-policy.txt")]
        for field, value in mutations:
            with self.subTest(field=field):
                self.inputs = copy.deepcopy(original)
                self.inputs["ai_policy"]["evidence"][field] = value
                self.save()
                self.assertEqual(self.audit()["status"], "blocked")

    def test_empty_template_and_false_nonuse_are_not_concrete_usage(self):
        for value in (None, "", "not used", "No AI was used in preparation of this entire research manuscript.",
                "During preparation we used [NAME OF TOOL] for [REASON].", {"tools": [], "human_oversight": "Checked."}):
            with self.subTest(value=value):
                self.inputs["ai_use"] = value
                self.save()
                self.assertEqual(self.audit()["status"], "blocked")
        self.inputs["ai_use"] = "The authors used Synthetic Tool for drafting and checked every scientific claim and citation."
        self.save()
        self.assertEqual(self.audit()["status"], "pass")

    def test_required_statement_cannot_point_to_comments_or_internal_reviews(self):
        review = self.paper / "reviews/policy-note.tex"
        review.parent.mkdir()
        review.write_text(self.statement, encoding="utf-8")
        location = self.inputs["ai_policy"]["statement"]["location"]
        location.update({"path": "reviews/policy-note.tex", "sha256": sha(review), "start_line": 1, "end_line": 1})
        self.save()
        self.assertEqual(self.audit()["status"], "blocked")
        self.manuscript.write_text("% " + self.statement + "\n", encoding="utf-8")
        location.update({"path": "manuscript/main.tex", "sha256": sha(self.manuscript)})
        self.save()
        self.assertEqual(self.audit()["status"], "blocked")

    def test_required_statement_missing_or_source_hash_stale_blocks(self):
        self.inputs["ai_policy"]["statement"]["location"]["sha256"] = "0" * 64
        self.save()
        self.assertEqual(self.audit()["status"], "blocked")

    def test_missing_or_ambiguous_canonical_source_returns_a_blocker(self):
        self.manuscript.unlink()
        self.assertEqual(self.audit()["status"], "blocked")
        del self.inputs["ai_policy"]["statement"]
        self.save()
        self.assertEqual(self.audit()["status"], "blocked")

    def test_separate_upload_is_exact_current_upload_file(self):
        target = self.paper / "submission-materials/declaration.md"
        target.parent.mkdir()
        target.write_text(self.statement + "\n", encoding="utf-8")
        self.inputs["ai_policy"]["statement"] = {"placement": "separate_upload", "excerpt": self.statement,
            "location": {"kind": "text_lines", "path": "submission-materials/declaration.md", "sha256": sha(target),
                "start_line": 1, "end_line": 1}}
        self.save()
        self.assertEqual(self.audit()["status"], "pass")
        target.write_text("Changed declaration.\n", encoding="utf-8")
        self.assertEqual(self.audit()["status"], "blocked")

    def test_word_statement_uses_real_canonical_paragraph(self):
        from docx import Document
        self.manuscript.unlink()
        target = self.paper / "manuscript/main.docx"
        document = Document()
        document.add_paragraph(self.statement)
        document.save(target)
        self.inputs["ai_policy"]["statement"]["location"] = {"kind": "docx_paragraph", "path": "manuscript/main.docx",
            "sha256": sha(target), "paragraph": 1}
        self.save()
        self.assertEqual(self.audit()["status"], "pass")
        self.inputs["ai_policy"]["statement"]["location"]["paragraph"] = 2
        self.save()
        self.assertEqual(self.audit()["status"], "blocked")

    def test_report_tampering_policy_change_and_statement_change_invalidate(self):
        disclosure.refresh(self.project, "P01")
        report = self.project / disclosure.review_binding(self.project, "P01")["path"]
        value = read(report)
        value["status"] = "forged"
        write(report, value)
        self.assertTrue(disclosure.validate_saved_report(self.project, "P01"))
        disclosure.refresh(self.project, "P01")
        self.inputs["ai_policy"]["rationale"] += " Changed interpretation."
        self.save()
        self.assertTrue(disclosure.validate_saved_report(self.project, "P01"))

    def test_policy_required_placement_cannot_be_replaced_by_an_easier_upload(self):
        self.inputs["ai_policy"]["required_placement"] = "separate_upload"
        self.save()
        self.assertEqual(self.audit()["status"], "blocked")

    def test_refresh_is_cloud_only_feedback_and_binding_are_read_only(self):
        self.assertEqual(disclosure.prompt_feedback(self.project, "P01")["status"], "pass")
        self.assertIsNone(disclosure.review_binding(self.project, "P01")["sha256"])
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false", "DR_OS_CLOUD_EXECUTOR": "0"}):
            with self.assertRaisesRegex(ValueError, "cloud"):
                disclosure.refresh(self.project, "P01")


if __name__ == "__main__":
    unittest.main()
