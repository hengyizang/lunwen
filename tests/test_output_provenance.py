from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import output_provenance


class OutputProvenanceTests(unittest.TestCase):
    def test_bulk_checks_load_one_registry_and_observe_later_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            artifacts = [project / name for name in ("first.txt", "second.txt")]
            for artifact in artifacts:
                artifact.write_text("Original fixture")
            def record(family):
                output_provenance.record_model_writes(project, artifacts, family=family,
                    provider="synthetic", model="fixture", role="test", run_id="fixture")
            record("other")
            for operation in (output_provenance.provenance_report, output_provenance.require_final_origins,
                              output_provenance.reject_current_anthropic_outputs):
                with patch.object(output_provenance, "_load", wraps=output_provenance._load) as load:
                    operation(project, iter(artifacts))
                self.assertEqual(load.call_count, 1)
            artifacts[0].write_text("Changed fixture")
            self.assertEqual(output_provenance.provenance_report(project, artifacts)[0]["status"], "modified_after_record")
            record("anthropic")
            with self.assertRaises(output_provenance.ProvenanceError):
                output_provenance.require_final_origins(project, artifacts)
            with self.assertRaises(output_provenance.ProvenanceError):
                output_provenance.reject_current_anthropic_outputs(project, artifacts)

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

    def test_final_origin_rejects_untracked_and_accepts_human_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)/"project";artifact=project/"papers"/"P01"/"manuscript"/"main.tex";artifact.parent.mkdir(parents=True);artifact.write_text("Human text",encoding="utf-8")
            with self.assertRaises(output_provenance.ProvenanceError):output_provenance.require_final_origins(project,[artifact])
            output_provenance.attest_human_files(project,[artifact],actor="Researcher",note="Independently reviewed and not Claude-derived")
            output_provenance.require_final_origins(project,[artifact])


if __name__ == "__main__":
    unittest.main()
