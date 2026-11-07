"""Source-bound journal facts have dates, not an invented fixed expiration."""
from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import journal_dossier as dossier
from scripts.research_artifacts import read, write


class JournalDossierTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        write(self.project / "program/venue-candidates.json", {
            "papers": [{"candidates": [{"venue_id": "synthetic-journal"}]}]})
        self.fields = {name: {"status": "unknown", "reason": "No verified synthetic source yet."}
                       for name in dossier.FIELDS}
        self.fields["apc"]["url"] = "https://publisher.example/fees"
        self.value = {"journals": [{"venue_id": "synthetic-journal",
            "official_domains": ["publisher.example"], "fields": self.fields}]}
        self.save()
        # Native acquisition with an inert local transport, never an actual
        # current fee, publisher-policy decision, or paid/network request.
        ledger = dossier.fetch_sources(self.project, fetcher=lambda url, **_: (
            b"<p>Synthetic APC 100 USD.</p>", url, 200, "text/html"))
        self.receipt = ledger["sources"][self.fields["apc"]["url"]]
        self.fields["apc"].update(status="verified", value=100, currency="USD", tax="unknown",
            quote="Synthetic APC 100 USD.", source={"path": self.receipt["path"],
                "sha256": self.receipt["sha256"], "locator": "synthetic fees paragraph"},
            accessed_at=self.receipt["retrieved_at"])
        self.save()

    def save(self):
        write(self.project / "program/journal-dossiers.json", self.value)

    def test_real_receipt_can_be_old_and_needs_no_synthetic_expiration(self):
        current = datetime.fromisoformat(self.receipt["retrieved_at"]) + timedelta(days=500)
        self.fields["apc"]["expires_at"] = (
            datetime.fromisoformat(self.receipt["retrieved_at"]) + timedelta(days=90)).isoformat()
        self.save()
        result = dossier.audit(self.project, now=current)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["fixed_source_age_limit_enforced"])
        self.assertEqual(result["journals"][0]["fields"]["apc"]["expires_at"], self.fields["apc"]["expires_at"])
        self.fields["apc"].pop("expires_at")
        self.save()
        self.assertEqual(dossier.audit(self.project, now=current)["status"], "pass")

    def test_future_or_unrecorded_access_still_fails(self):
        original = copy.deepcopy(self.fields["apc"])
        for accessed in ((datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                         "2025-01-01T00:00:00", "not a real timestamp"):
            with self.subTest(accessed=accessed):
                self.fields["apc"] = {**original, "accessed_at": accessed}
                self.save()
                self.assertEqual(dossier.audit(self.project)["status"], "fail")

    def test_ai_policy_is_neither_required_nor_fetched_or_enforced(self):
        self.assertNotIn("ai_policy", self.fields)
        self.assertEqual(dossier.audit(self.project)["status"], "pass")
        self.fields["ai_policy"] = {"status": "prohibited", "url": "http://untrusted.example/ai-policy"}
        self.fields["optional_note"] = {"status": "unknown", "reason": "No evidence."}
        self.save()
        with patch("scripts.network_safety.fetch_bytes", side_effect=AssertionError("no additional requests")):
            dossier.fetch_sources(self.project)
        result = dossier.refresh(self.project)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["journal_ai_policy_evaluated"])
        self.assertNotIn("ai_policy", result["journals"][0]["fields"])
        self.assertEqual(read(self.project / "program/journal-dossiers.json"), self.value)
        self.assertEqual(dossier.validate_saved_report(self.project, "synthetic-journal"), [])

    def test_source_drift_fee_invention_and_missing_raw_receipt_still_fail(self):
        original = copy.deepcopy(self.fields["apc"])
        self.fields["apc"]["value"] = 900
        self.save()
        self.assertEqual(dossier.audit(self.project)["status"], "fail")
        self.fields["apc"] = original
        self.save()
        source = self.project / self.receipt["path"]
        source.write_text("Changed original source.", encoding="utf-8")
        self.assertEqual(dossier.audit(self.project)["status"], "fail")
        source.write_text("Synthetic APC 100 USD.", encoding="utf-8")
        (self.project / self.receipt["raw_path"]).unlink()
        self.assertEqual(dossier.audit(self.project)["status"], "fail")

    def test_venue_fit_has_native_official_acquisition_without_new_fee_requirements(self):
        self.fields["scope"] = {"url": "https://publisher.example/scope"}
        self.save()
        ledger = dossier.fetch_sources(self.project, fetcher=lambda url, **_: (
            b"<p>Synthetic official scope and article types.</p>", url, 200, "text/html"))
        receipt = ledger["sources"][self.fields["scope"]["url"]]
        self.assertEqual(receipt["status"], "retrieved")
        self.assertIn("Synthetic official scope", (self.project / receipt["path"]).read_text())
        self.assertEqual(dossier.audit(self.project)["status"], "pass")
        self.assertNotIn("scope", dossier.FIELDS)
        self.fields["article_type"] = {"url": "https://unverified.example/types"}
        self.save()
        with self.assertRaisesRegex(ValueError, "declared publisher domains"):
            dossier.fetch_sources(self.project)
