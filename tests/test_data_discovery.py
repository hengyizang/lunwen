from __future__ import annotations

import unittest

from scripts.data_discovery import PROVIDERS, discover, discover_many
from scripts.network_safety import NetworkSafetyError


class DataDiscoveryTests(unittest.TestCase):
    def test_datacite_candidates_are_normalized_and_unverified(self) -> None:
        def fetcher(url: str):
            self.assertIn("api.datacite.org", url)
            return {
                "data": [
                    {
                        "id": "10.1234/example",
                        "attributes": {
                            "titles": [{"title": "Example dataset"}],
                            "url": "https://data.example.org/record",
                            "doi": "10.1234/example",
                            "rightsList": [{"rightsIdentifier": "CC-BY-4.0"}],
                        },
                    }
                ]
            }

        report = discover("vibration", ["datacite"], 5, fetcher=fetcher)
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(
            report["candidates"][0]["license_status"],
            "unverified_requires_human_review",
        )

    def test_provider_failure_is_reported_without_fabricating_results(self) -> None:
        def fetcher(url: str):
            raise NetworkSafetyError("offline fixture")

        report = discover("robot", ["zenodo"], 5, fetcher=fetcher)
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["providers"][0]["status"], "error")

    def test_eight_official_provider_families_are_available(self) -> None:
        self.assertEqual(
            set(PROVIDERS),
            {"datacite", "zenodo", "huggingface", "openml", "figshare", "dryad", "dataverse", "datagov"},
        )

    def test_figshare_post_search_is_normalized(self) -> None:
        def fetcher(url: str, **kwargs):
            self.assertEqual(url, "https://api.figshare.com/v2/articles/search")
            self.assertEqual(kwargs["method"], "POST")
            self.assertEqual(kwargs["json_body"]["search_for"], "bearing")
            self.assertEqual(kwargs["json_body"]["item_type"], 3)
            return [{"id": 42, "title": "Bearing vibration dataset", "doi": "10.1/demo", "published_date": "2026-01-01"}]

        report = discover("bearing", ["figshare"], 5, fetcher=fetcher)
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["candidates"][0]["provider"], "Figshare")
        self.assertEqual(report["candidates"][0]["landing_url"], "https://figshare.com/articles/dataset/_/42")

    def test_broad_search_deduplicates_doi_and_ranks_metadata_only(self) -> None:
        def fetcher(url: str, **_kwargs):
            if "datacite" in url:
                return {"data": [{"id": "10.1234/same", "attributes": {"titles": [{"title": "Industrial bearing vibration benchmark"}], "url": "https://example.org/one", "doi": "10.1234/same", "rightsList": [{"rightsIdentifier": "CC-BY-4.0"}]}}]}
            return {"hits": {"hits": [{"id": 9, "metadata": {"title": "Industrial bearing vibration benchmark", "doi": "10.1234/same"}, "links": {"html": "https://example.org/two"}}]}}

        report = discover_many(
            ["industrial bearing vibration", "bearing fault benchmark"],
            ["datacite", "zenodo"],
            5,
            fetcher=fetcher,
        )
        self.assertEqual(report["raw_candidate_count"], 4)
        self.assertEqual(report["candidate_count"], 1)
        candidate = report["candidates"][0]
        self.assertGreater(candidate["metadata_relevance_score"], 50)
        self.assertEqual(set(candidate["also_found_by"]), {"DataCite", "Zenodo"})
        self.assertEqual(
            candidate["fitness_status"],
            "candidate_only_requires_scientific_and_human_review",
        )


if __name__ == "__main__":
    unittest.main()
