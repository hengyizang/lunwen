from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import output_provenance


class OutputProvenanceTests(unittest.TestCase):
    def test_current_anthropic_hash_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            artifact = project / "papers" / "P01" / "manuscript" / "main.tex"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("Claude wording", encoding="utf-8")
            output_provenance.record_model_writes(
                project,
                [artifact],
                family="anthropic",
                provider="anthropic",
                model="claude-test",
                role="persistent-writer",
                run_id="run-1",
            )
            with self.assertRaises(output_provenance.ProvenanceError):
                output_provenance.reject_current_anthropic_outputs(
                    project, [artifact]
                )

    def test_human_or_local_edit_invalidates_old_model_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            artifact = project / "papers" / "P01" / "manuscript" / "main.tex"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("old", encoding="utf-8")
            output_provenance.record_model_writes(
                project,
                [artifact],
                family="anthropic",
                provider="anthropic",
                model="claude-test",
                role="persistent-writer",
                run_id="run-1",
            )
            artifact.write_text("independently rewritten", encoding="utf-8")
            output_provenance.reject_current_anthropic_outputs(project, [artifact])
            self.assertEqual(
                output_provenance.current_origin(project, artifact)["status"],
                "modified_after_record",
            )


if __name__ == "__main__":
    unittest.main()
