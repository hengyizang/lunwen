from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.automatic_data_discovery import (
    AutomaticDataDiscoveryError,
    derive_queries,
    run_automatic_discovery,
)
from scripts.network_safety import NetworkSafetyError


class AutomaticDataDiscoveryTests(unittest.TestCase):
    def test_g1_queries_are_derived_without_manual_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "intake").mkdir()
            (project / "intake" / "constraints.json").write_text(
                json.dumps(
                    {
                        "research_goal": "Reliable predictive maintenance for rotating machinery",
                        "preferred_domains": ["industrial AI", "bearing fault diagnosis"],
                        "data_constraint": "Public licensed datasets only",
                    }
                ),
                encoding="utf-8",
            )
            queries = derive_queries(project, "topic-intelligence")
        self.assertGreaterEqual(len(queries), 3)
        self.assertTrue(any("predictive maintenance" in query.lower() for query in queries))
        self.assertTrue(all(len(query) <= 240 for query in queries))

    def test_g3_queries_include_each_paper_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            for paper, question in (
                ("P01", "Bearing remaining useful life under domain shift"),
                ("P02", "Industrial robot anomaly detection with sensor fusion"),
            ):
                root = project / "papers" / paper
                root.mkdir(parents=True)
                (root / "paper-contract.json").write_text(
                    json.dumps({"working_title": question, "research_question": question}),
                    encoding="utf-8",
                )
            queries = derive_queries(project, "experiment-design")
        joined = " ".join(queries).lower()
        self.assertIn("bearing", joined)
        self.assertIn("robot", joined)

    def test_automatic_search_saves_ranked_report_and_separate_audit_log(self) -> None:
        def fetcher(url: str, **_kwargs):
            self.assertIn("api.datacite.org", url)
            return {
                "data": [
                    {
                        "id": "10.1234/bearing",
                        "attributes": {
                            "titles": [{"title": "Bearing predictive maintenance benchmark dataset"}],
                            "url": "https://example.org/bearing",
                            "doi": "10.1234/bearing",
                            "version": "2",
                            "rightsList": [{"rightsIdentifier": "CC-BY-4.0"}],
                        },
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            summary = run_automatic_discovery(
                project,
                "topic-intelligence",
                explicit_query="bearing predictive maintenance dataset",
                providers=["datacite"],
                limit=5,
                fetcher=fetcher,
            )
            report = json.loads((project / summary["report_path"]).read_text(encoding="utf-8"))
            dataset_log = project / "evidence" / "dataset-search-log.jsonl"
            self.assertTrue(dataset_log.is_file())
            self.assertFalse((project / "evidence" / "search-log.jsonl").exists())
        self.assertGreater(report["candidate_count"], 0)
        self.assertGreater(summary["shortlist_count"], 0)
        self.assertIn("automatic_screening", report["candidates"][0])
        self.assertTrue(report["automatic_screening_summary"]["human_review_required"])

    def test_all_source_failures_stop_before_model_cycle(self) -> None:
        def fetcher(_url: str, **_kwargs):
            raise NetworkSafetyError("offline")

        with tempfile.TemporaryDirectory() as directory, self.assertRaises(
            AutomaticDataDiscoveryError
        ):
            run_automatic_discovery(
                Path(directory),
                "experiment-design",
                explicit_query="robot sensor dataset",
                providers=["zenodo"],
                fetcher=fetcher,
            )


if __name__ == "__main__":
    unittest.main()
