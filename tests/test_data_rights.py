"""Automatic rights adapter controls; all provider/model data are synthetic."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import artifact_ownership, data_rights, dataset_fetch, output_provenance
from scripts import cloud_research_steps as steps
from scripts.research_artifacts import read, record, sha, write
from tests.test_dataset_fetch import valid_manifest


class DataRightsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "demo"
        self.path = self.project / "data/manifests/fixture.json"
        self.manifest = valid_manifest()
        self.manifest.update(provider="Zenodo", source_url="https://zenodo.org/records/123")
        self.manifest["license"]["confirmed_by_human"] = False
        self.manifest["download"].update(url="https://zenodo.org/api/records/123/files/data.csv/content")
        write(self.path, self.manifest)
        write(self.project / "state/run.json", {"gate": "G3", "status": "awaiting_work"})
        self.metadata = {"id": 123, "metadata": {"title": "Example", "version": "1.0",
            "access_right": "open", "resource_type": {"type": "dataset"}, "license": {"id": "cc-by-4.0"}},
            "files": [{"size": 10, "links": {"self": self.manifest["download"]["url"]}}]}

    def fetch(self, url, **kwargs):
        self.assertEqual(url, "https://zenodo.org/api/records/123")
        return json.dumps(self.metadata).encode(), url, 200, "application/json"

    def prepare_assessment(self):
        with self.assertRaisesRegex(ValueError, "writer provenance"):
            data_rights.prepare(self.project, self.path, fetcher=self.fetch)
        metadata = self.project / "evidence/data-rights/example-v1/metadata.json"
        self.manifest["provenance"]["rights_assessment"] = {
            "source_metadata_sha256": sha(metadata), "personal_data": "none", "cloud_use_allowed": True,
            "additional_restrictions": False,
            "privacy_basis": "Synthetic fixture assessment; no actual personal-data determination is asserted.",
            "terms_basis": "Synthetic fixture license and cloud-use assessment for software controls only."}
        write(self.path, self.manifest)
        output_provenance.record_model_writes(self.project, [self.path], family="openai", provider="test-fixture",
            model="synthetic", role="writer", run_id="fixture")
        final = self.project / "state/review-receipts/G3/fixture/final.json"
        write(final, {"synthetic_review_fixture_only": True})
        record(self.project, [final], "scripts/review_receipts.py")
        write(self.project / "state/review-receipts/G3/latest.json",
              {"path": final.relative_to(self.project).as_posix(), "sha256": sha(final)})

    def test_first_pass_supplies_evidence_without_inventing_assessment(self):
        with self.assertRaisesRegex(ValueError, "writer provenance"):
            data_rights.prepare(self.project, self.path, fetcher=self.fetch)
        self.assertTrue((self.project / "evidence/data-rights/example-v1/metadata.json").is_file())
        self.assertFalse((self.project / "state/data-rights/example-v1.json").exists())
        self.assertTrue(artifact_ownership.executor_owned(self.project, "evidence/data-rights/example-v1/metadata.json"))

    def test_metadata_alone_cannot_replace_independent_rights_review(self):
        self.prepare_assessment()
        with self.assertRaisesRegex(ValueError, "independent scientific review"):
            data_rights.prepare(self.project, self.path, fetcher=self.fetch)

    def test_public_counters_do_not_invalidate_current_rights_but_metadata_changes_do(self):
        self.prepare_assessment()
        metadata_path=self.project / "evidence/data-rights/example-v1/metadata.json"
        original=metadata_path.read_bytes()
        self.metadata["stats"]={"views":42}
        with patch.object(data_rights.review_receipts,"validate_gate",return_value=[]):
            data_rights.prepare(self.project,self.path,fetcher=self.fetch)
        self.assertEqual(metadata_path.read_bytes(),original)
        self.metadata["metadata"]["description"]="Changed privacy-relevant publication content."
        with self.assertRaisesRegex(ValueError,"privacy"):
            data_rights.prepare(self.project,self.path,fetcher=self.fetch)

    def test_supported_source_and_current_review_produce_honest_automated_authority(self):
        self.prepare_assessment()
        with patch.object(data_rights.review_receipts, "validate_gate", return_value=[]):
            data_rights.prepare(self.project, self.path, fetcher=self.fetch)
        self.assertEqual(dataset_fetch.license_errors(self.manifest, project=self.project), [])
        receipt = read(self.project / "state/data-rights/example-v1.json")
        self.assertFalse(receipt["human_confirmation"])
        self.assertFalse(receipt["scientific_validity_verified"])
        self.assertTrue(receipt["declaration"]["attribution_required"])
        authority = steps.authorize_data(self.project, self.path.relative_to(self.project).as_posix(), sha(self.path),
                                        "deterministic_control_plane", "fixture", automated=True)
        self.assertFalse(authority["human_confirmation"])
        self.assertEqual(authority["decision_kind"], "automated")
        self.path.write_text(self.path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertTrue(dataset_fetch.license_errors(self.manifest, project=self.project))

    def test_unknown_license_restricted_access_wrong_file_and_personal_data_do_not_authorize(self):
        for change in (lambda m: m["metadata"].update(access_right="restricted"),
                       lambda m: m["metadata"].update(license={"id": "custom"}),
                       lambda m: m["files"][0].update(size=999)):
            original = json.loads(json.dumps(self.metadata)); change(self.metadata)
            with self.assertRaises(ValueError):
                data_rights.prepare(self.project, self.path, fetcher=self.fetch)
            self.metadata = original
        self.prepare_assessment()
        self.manifest["provenance"]["rights_assessment"]["personal_data"] = "unknown"
        write(self.path, self.manifest)
        output_provenance.record_model_writes(self.project, [self.path], family="openai", provider="test-fixture",
            model="synthetic", role="writer", run_id="fixture")
        with patch.object(data_rights.review_receipts, "validate_gate", return_value=[]), self.assertRaisesRegex(ValueError, "privacy"):
            data_rights.prepare(self.project, self.path, fetcher=self.fetch)

    def test_unsupported_provider_never_makes_a_network_request(self):
        self.manifest.update(source_url="https://example.org/dataset")
        write(self.path, self.manifest)
        with patch.object(data_rights.network_safety, "fetch_bytes") as fetch:
            with self.assertRaisesRegex(ValueError, "Zenodo"):
                data_rights.prepare(self.project, self.path)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
