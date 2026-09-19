from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import live_acceptance


class LiveAcceptanceTests(unittest.TestCase):
    def test_literature_acceptance_requires_real_http_results(self) -> None:
        def receipt(_project, provider, _query, **_kwargs):
            return {
                "status": "success",
                "http_status": 200,
                "content_type": "application/json",
                "result_count": 1,
                "receipt_id": f"receipt-{provider}",
                "response_sha256": "a" * 64,
                "normalized_results_sha256": "b" * 64,
                "raw_response_path": f"evidence/raw/{provider}.json",
                "normalized_results_path": f"evidence/normalized/{provider}.json",
            }

        with tempfile.TemporaryDirectory() as directory, patch(
            "scripts.live_acceptance.execute_search", side_effect=receipt
        ):
            report = live_acceptance.literature_acceptance(
                Path(directory) / "evidence",
                ["openalex", "crossref"],
                query="machine learning",
                limit=1,
                include_opencitations=False,
                citation_doi=live_acceptance.DEFAULT_DOI,
            )
        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(report["checks"]), 2)

    def test_literature_acceptance_preserves_provider_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "scripts.live_acceptance.execute_search",
            side_effect=live_acceptance.LiteratureEvidenceError("rate limited"),
        ):
            report = live_acceptance.literature_acceptance(
                Path(directory) / "evidence",
                ["semantic-scholar"],
                query="machine learning",
                limit=1,
                include_opencitations=False,
                citation_doi=live_acceptance.DEFAULT_DOI,
            )
        self.assertEqual(report["status"], "failed")
        self.assertIn("rate limited", report["checks"][0]["error"])

    def test_container_acceptance_enforces_isolation_flags(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "root_read_only": True,
                    "tmp_writable": True,
                    "network_blocked": True,
                }
            ),
            stderr="",
        )
        environment = {
            "platform": "Linux",
            "python": "3.12",
            "kernel": "microsoft-standard-WSL2",
            "is_wsl": True,
            "is_wsl2": True,
            "container_engines": ["docker"],
        }
        with (
            patch("scripts.live_acceptance.environment_report", return_value=environment),
            patch("scripts.live_acceptance.shutil.which", return_value="/usr/bin/docker"),
            patch("scripts.live_acceptance.subprocess.run", return_value=completed) as run,
        ):
            report = live_acceptance.container_acceptance(
                live_acceptance.DEFAULT_IMAGE,
                require_wsl2=True,
            )
        command = run.call_args.args[0]
        self.assertEqual(report["status"], "passed")
        self.assertIn("--network=none", command)
        self.assertIn("--read-only", command)
        self.assertIn("--cap-drop=ALL", command)
        self.assertIn(live_acceptance.DEFAULT_IMAGE, command)

    def test_container_acceptance_reports_non_wsl_as_blocked(self) -> None:
        environment = {
            "platform": "Linux",
            "python": "3.12",
            "kernel": "linux",
            "is_wsl": False,
            "is_wsl2": False,
            "container_engines": [],
        }
        with patch(
            "scripts.live_acceptance.environment_report", return_value=environment
        ):
            report = live_acceptance.container_acceptance(
                live_acceptance.DEFAULT_IMAGE,
                require_wsl2=True,
            )
        self.assertEqual(report["status"], "blocked")
        self.assertIn("WSL2", report["error"])


if __name__ == "__main__":
    unittest.main()
