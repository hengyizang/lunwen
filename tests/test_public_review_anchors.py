"""Public corpus contracts; synthetic transport fixtures do not measure judgment."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import public_review_anchors as corpus, literature_benchmark as benchmark


class PublicReviewAnchorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = {"id": "12345", "version": 1, "assessment_doi": "10.7554/eLife.12345.1.sa0", "partition": "holdout"}
        self.rights = {"DOI": self.candidate["assessment_doi"], "type": "peer-review", "license": [{"URL": corpus.LICENSE}]}
        self.article = {"id": "12345", "version": 1, "doi": "10.7554/eLife.12345", "authorLine": "Synthetic fixture",
            "copyright": {"license": "CC-BY-4.0"}, "title": "Synthetic source fixture",
            "abstract": [{"text": "A synthetic bounded abstract."}], "body": [{"text": "Measured fictional source content. " * 220}],
            "elifeAssessment": {"doi": self.candidate["assessment_doi"], "strength": ["solid"], "content": [{"text": "Fixture public assessment ANSWER_KEY_TEXT."}]}}
        self.calls = []

    def fetch(self, url, path):
        self.calls.append(url)
        value = {"message": self.rights} if "crossref" in url else self.article
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return copy.deepcopy(value)

    def acquire(self, candidate=None):
        with patch.object(corpus, "_fetch", side_effect=self.fetch):
            return corpus._acquire(self.root / "project", candidate or self.candidate, self.root / "originals")

    def test_review_license_is_verified_before_acquiring_article_body(self):
        self.rights["license"] = []
        with self.assertRaisesRegex(ValueError, "license"):
            self.acquire()
        self.assertEqual(len(self.calls), 1)
        self.assertIn("api.crossref.org", self.calls[0])

    def test_original_answer_payloads_stay_outside_the_blind_project(self):
        case, receipt = self.acquire()
        primary = (self.root / "project" / case["source"]["path"]).read_text()
        self.assertNotIn("ANSWER_KEY_TEXT", primary)
        self.assertEqual(receipt["label"], "solid")
        self.assertFalse(list((self.root / "project").rglob("article.json")))
        self.assertTrue((self.root / "originals/12345/article.json").is_file())
        changed = {**self.candidate, "primary_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "frozen public anchor changed"):
            self.acquire(changed)

    def test_public_assessment_categories_are_not_relabelled_as_claim_support(self):
        for label in ("solid", "incomplete+solid"):
            self.assertTrue(benchmark._anchor_label(label, "elife_evidence_strength"))
        for label in ("supports", "solid+incomplete", "solid+solid", ""):
            self.assertFalse(benchmark._anchor_label(label, "elife_evidence_strength"))
        self.assertFalse(benchmark._anchor_label("solid", "claim_support_and_novelty"))

    def test_rate_limited_public_request_preserves_its_failed_attempt(self):
        url = "https://api.crossref.org/works/10.7554/eLife.12345.1.sa0"
        target = self.root / "originals/crossref.json"
        responses = [HTTPError(url, 429, "Too Many Requests", {"Retry-After": "7"}, None),
                     (b'{"source":"synthetic transport fixture"}', url, 200, "application/json"),
                     (b'{"source":"synthetic transport fixture"}', url, 200, "application/json")]
        with patch.object(corpus, "fetch_bytes", side_effect=responses), patch("scripts.literature_evidence.time.sleep") as sleep:
            self.assertEqual(corpus._fetch(url, target), {"source": "synthetic transport fixture"})
            self.assertEqual(corpus._fetch(url, target), {"source": "synthetic transport fixture"})
        attempts = json.loads(target.with_name("crossref-attempts.json").read_text())["attempts"]
        self.assertEqual([row["status"] for row in attempts], [429, 200, 200])
        self.assertEqual(attempts[0]["retry_after"], "7")
        self.assertIn(7, [call.args[0] for call in sleep.call_args_list])

    def test_retained_live_manifest_has_24_distinct_licensed_partitioned_papers(self):
        path = Path(__file__).resolve().parents[1] / "docs/acceptance/elife-public-anchors-2026-11-07.json"
        report = json.loads(path.read_text())
        self.assertEqual(len({row["paper_doi"] for row in report["anchors"]}), 24)
        self.assertEqual(sum(row["partition"] == "holdout" for row in report["anchors"]), 8)
        self.assertTrue(all(row["license_url"] == corpus.LICENSE for row in report["anchors"]))
        self.assertEqual(report["calibration_status"], "NOT_CALIBRATED")
        self.assertIsNone(report["human_claim_sample_agreement"])
        self.assertEqual(report["model_predictions"], 0)
