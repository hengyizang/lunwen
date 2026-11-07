from __future__ import annotations

import unittest

from scripts.open_fulltext import FullTextResolverError, normalize_doi, resolve


class OpenFullTextTests(unittest.TestCase):
    def test_combines_and_deduplicates_public_candidates_without_authorizing_download(self):
        def fetcher(url: str):
            if "openalex" in url:
                return {
                    "open_access": {"is_oa": True},
                    "best_oa_location": {
                        "pdf_url": "https://repository.example/paper.pdf",
                        "landing_page_url": "https://repository.example/item",
                        "version": "acceptedVersion",
                        "license": "cc-by",
                    },
                    "locations": [],
                }
            if "unpaywall" in url:
                return {
                    "is_oa": True,
                    "best_oa_location": {
                        "url_for_pdf": "https://repository.example/paper.pdf",
                        "url_for_landing_page": "https://repository.example/item",
                        "version": "acceptedVersion",
                        "license": "cc-by",
                        "host_type": "repository",
                    },
                    "oa_locations": [],
                }
            return {
                "message": {
                    "link": [
                        {
                            "URL": "https://publisher.example/full.xml",
                            "content-type": "application/xml",
                            "content-version": "vor",
                        }
                    ],
                    "license": [],
                }
            }

        value = resolve("https://doi.org/10.1234/Example", email="research@example.org", fetcher=fetcher)
        self.assertEqual(value["doi"], "10.1234/example")
        self.assertEqual(len(value["candidates"]), 2)
        self.assertFalse(value["policy"]["license_and_terms_human_confirmation_required"])
        self.assertEqual(value["policy"]["license_and_terms_verification"], "optional_metadata")
        self.assertEqual([item["version"] for item in value["candidates"]], ["acceptedVersion", "vor"])
        self.assertTrue(all(not item["license_verified"] for item in value["candidates"]))
        self.assertIsNone(value["candidates"][1]["license_claim"])
        self.assertTrue(value["policy"]["access_controls_must_not_be_bypassed"])
        self.assertTrue(value["policy"]["publisher_or_library_entitlement_is_not_inferred"])
        self.assertTrue(all(not item["download_authorized"] for item in value["candidates"]))

    def test_invalid_doi_is_rejected(self):
        with self.assertRaises(FullTextResolverError):
            normalize_doi("not-a-doi")
