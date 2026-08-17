from __future__ import annotations

import unittest

from scripts.dataset_fetch import DatasetError, https_url, safe_filename, validate_manifest


def valid_manifest() -> dict:
    return {
        "schema_version": "1.0",
        "dataset_id": "example-v1",
        "title": "Example",
        "provider": "Official Provider",
        "source_url": "https://data.example.org/dataset",
        "version": "1.0",
        "accessed_at": "2026-08-12",
        "license": {
            "name": "CC BY 4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "research_use_allowed": True,
            "redistribution_allowed": True,
            "confirmed_by_human": True,
        },
        "download": {
            "url": "https://data.example.org/files/data.csv",
            "sha256": "a" * 64,
            "expected_bytes": 10,
            "filename": "data.csv",
        },
        "provenance": {
            "collection_method": "Provider release",
            "transformations": [],
        },
        "unit_of_analysis": "record",
        "split_strategy": "grouped split",
        "known_limitations": ["Synthetic fixture"],
    }


class DatasetFetchTests(unittest.TestCase):
    def test_valid_manifest(self) -> None:
        manifest = valid_manifest()
        self.assertEqual(validate_manifest(manifest), [])
        self.assertEqual(safe_filename(manifest), "data.csv")

    def test_http_and_credentials_are_rejected(self) -> None:
        with self.assertRaises(DatasetError):
            https_url("http://example.org/data", "url")
        with self.assertRaises(DatasetError):
            https_url("https://user:pass@example.org/data", "url")

    def test_unsafe_filename_is_rejected(self) -> None:
        manifest = valid_manifest()
        manifest["download"]["filename"] = "../secret.csv"
        with self.assertRaises(DatasetError):
            safe_filename(manifest)

    def test_license_must_allow_research(self) -> None:
        manifest = valid_manifest()
        manifest["license"]["research_use_allowed"] = False
        self.assertIn(
            "license.research_use_allowed must be true",
            validate_manifest(manifest),
        )


if __name__ == "__main__":
    unittest.main()

