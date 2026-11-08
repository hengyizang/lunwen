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
from scripts.research_artifacts import write


class AutomaticDataDiscoveryTests(unittest.TestCase):
    delivery_goal = (
        "Develop six distinct, independently defensible doctoral-level English papers around a core thesis A "
        "and a separately doctoral-level extension B. Target at least three current JCR Q1 SCI/SCIE journals "
        "and at least current JCR Q2 SCI/SCIE for every remaining paper, all with JIF > 1.0. Apply identical "
        "novelty, original-contribution, experimental, statistical, reproducibility and writing requirements "
        "to every paper. Prepare packages for human inspection and manual submission before 2026-10-26; "
        "journal acceptance is not promised."
    )

    def test_actual_intake_delivery_goal_cannot_displace_supplied_research_domains(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write(project / "intake/constraints.json", {"research_goal": self.delivery_goal,
                "preferred_domains": ["AI", "robotics", "mechanical engineering"],
                "researcher_background": "Self-reported mechanical engineering and Big Data/business intelligence studies; credentials unverified."})
            queries = derive_queries(project, "topic-intelligence")
            self.assertEqual(queries[0], "AI robotics mechanical engineering dataset")
            self.assertNotRegex(" ".join(queries), r"(?i)doctoral|defensible|JCR|JIF|English|packages|promised")
            self.assertNotIn("predictive maintenance", " ".join(queries).lower())
            write(project / "program/core-thesis.json", {"doctoral_question": "Sensor calibration under mechanical wear"})
            self.assertEqual(derive_queries(project, "topic-intelligence")[0], "Sensor calibration under mechanical wear dataset")
            explicit = "tactile force calibration"
            self.assertEqual(derive_queries(project, "topic-intelligence", explicit_query=explicit)[0], explicit)

    def test_paper_delivery_goal_alone_is_not_research_input(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write(project / "intake/constraints.json", {"research_goal": self.delivery_goal, "preferred_domains": []})
            with self.assertRaisesRegex(AutomaticDataDiscoveryError, "research input"):
                derive_queries(project, "topic-intelligence")

    def test_scientific_research_goal_alone_remains_a_valid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            for goal, expected in (("How does language contact change vowel trajectories?", "language contact"),
                ("Develop interpretable models for journal article classification", "interpretable models"),
                (self.delivery_goal + " How does language contact change vowel trajectories?", "language contact")):
                with self.subTest(goal=goal):
                    write(project / "intake/constraints.json", {"research_goal": goal})
                    self.assertIn(expected, derive_queries(project, "topic-intelligence")[0])

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

    def test_legacy_g3_queries_preserve_each_paper_contract(self) -> None:
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

    def test_unset_scope_does_not_invent_a_field_or_search_template_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write(project / "intake/constraints.json", {"research_goal": None, "preferred_domains": [],
                "data_constraint": "Prefer public or authorized datasets"})
            write(project / "program/core-thesis.json", {"schema_version": "1.0", "status": "draft", "theme_id": "A", "title": ""})
            write(project / "program/topic-shortlist.json", {"candidates": [], "selected_direction_cloud_feasibility": {
                "current_papers_feasible": False, "pilot": {"status": "not_run"}}})
            with self.assertRaisesRegex(AutomaticDataDiscoveryError, "research input"):
                run_automatic_discovery(project, "topic-intelligence", fetcher=lambda *args, **kwargs: self.fail("No research input: no search"))
            self.assertFalse((project / "data").exists())

    def test_queries_use_actual_nonengineering_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write(project / "program/core-thesis.json", {"title": "Historical linguistics and language contact"})
            joined = " ".join(derive_queries(project, "topic-intelligence")).lower()
            self.assertIn("historical linguistics", joined)
            self.assertNotIn("robot", joined)
            self.assertNotIn("industrial", joined)

    def test_independent_g3_queries_only_read_the_active_paper(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            state = {"gate": "G3", "paper_execution_mode": "independent", "active_paper": "P02", "paper_count": 2}
            write(project / "state/run.json", state)
            write(project / "papers/P01/paper-contract.json", {"research_question": "Ocean salinity measurement"})
            write(project / "papers/P02/paper-contract.json", {"research_question": "Historical language contact"})
            joined = " ".join(derive_queries(project, "experiment-design")).lower()
            self.assertIn("historical language contact", joined)
            self.assertNotIn("ocean", joined)
            self.assertEqual(json.loads((project / "state/run.json").read_text()), state)

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
        self.assertFalse(report["automatic_screening_summary"]["human_review_required"])
        self.assertTrue(report["automatic_screening_summary"]["scientific_review_required"])
        self.assertFalse(summary["human_review_required"])
        self.assertTrue(summary["scientific_review_required"])

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
