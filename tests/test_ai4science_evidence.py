from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ai4science_evidence import record, validate


class AI4ScienceEvidenceTests(unittest.TestCase):
    def test_real_local_output_is_versioned_hash_bound_and_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            (project / "evidence").mkdir(parents=True)
            source = project / "evidence" / "papers.csv"
            output = project / "evidence" / "paperqa-answer.json"
            source.write_text("doi,title\n10.1000/example,Example\n", encoding="utf-8")
            output.write_text('{"answer":"requires primary-source review"}', encoding="utf-8")
            with patch("scripts.ai4science_evidence.metadata.version", return_value="2026.08.12"):
                receipt = record(
                    project,
                    "paperqa2",
                    "evidence/paperqa-answer.json",
                    ["evidence/papers.csv"],
                    "Researcher",
                    "Contradiction scan over the human-owned corpus.",
                )
            self.assertTrue(receipt["advisory_only"])
            self.assertEqual(validate(project, [receipt]), [])
            output.write_text("changed", encoding="utf-8")
            self.assertTrue(any("stale" in item for item in validate(project, [receipt])))


if __name__ == "__main__":
    unittest.main()
