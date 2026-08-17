from __future__ import annotations

import unittest

from scripts.data_discovery import discover
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


if __name__ == "__main__":
    unittest.main()
