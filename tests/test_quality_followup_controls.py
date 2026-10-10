import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator, cloud_research_steps as steps, cloud_runtime
from scripts.research_artifacts import write


class FollowupControlTests(unittest.TestCase):
    def test_model_cannot_forge_new_receipts_but_can_write_review_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "projects/demo").mkdir(parents=True)
            with patch.object(api_orchestrator, "ROOT", root):
                for relative in (
                    "papers/P01/reviews/revision-ledger-report.json",
                    "papers/P01/reviews/revision-render.json",
                    "papers/P01/reviews/cloud-tex-build.json",
                    "reports/research-notebook-daily/2026-10-10.json",
                    "reports/research-support.json", "reports/review-packets/review/manifest.json",
                    "evidence/support-sources/index.json", "reports/figure-output-qa/file/page.png",
                    "papers/P01/figures/figure.render-receipt.json",
                    "state/review-packet-confirmations/review/actor.json",
                ):
                    with self.subTest(path=relative), self.assertRaises(ValueError):
                        api_orchestrator.safe_target("demo", relative)
                for relative in ("papers/P01/reviews/revision-ledger.json", "program/research-support.json",
                                 "program/review-packets.json"):
                    self.assertEqual(api_orchestrator.safe_target("demo", relative), root / "projects/demo" / relative)

    def test_followup_operations_use_deterministic_builders_and_keep_independent_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            operations = [{"stage": "writing-and-review", "action": action, "paper_id": "P01"}
                          for action in ("research_support", "research_notebook_daily", "revision_ledger", "review_packets")]
            write(project / "program/cloud-operations.json", {"operations": operations})
            with patch("scripts.research_support.refresh", side_effect=ValueError("missing actual input")), \
                 patch("scripts.research_notebook.daily_brief", return_value={}) as daily, \
                 patch("scripts.revision_ledger.refresh", return_value={}) as ledger, \
                 patch("scripts.review_packets.refresh", return_value={}) as packets, \
                 patch("scripts.model_runtime.call", side_effect=AssertionError("no paid model calls")):
                report = steps.after_write(project, "writing-and-review")
            self.assertEqual(report["operation_errors"], [{"action": "research_support", "error": "missing actual input"}])
            daily.assert_called_once_with(project)
            ledger.assert_called_once_with(project, "P01")
            packets.assert_called_once_with(project)

    def test_rendering_refuses_local_execution_before_launching_processes(self):
        with patch.dict(os.environ, {}, clear=True), patch("scripts.cloud_runtime.subprocess.run") as process:
            with self.assertRaisesRegex(RuntimeError, "cloud executor"):
                cloud_runtime.compile_tex(Path("absent"), "P01")
            process.assert_not_called()

    def test_author_contract_documents_receipts_without_changing_roles(self):
        contract = json.loads(api_orchestrator.research_quality_artifact_contract("writing-and-review"))
        followup = contract["quality_followup"]
        self.assertIn("NOT_CALIBRATED", followup["review_packets"])
        self.assertIn("seeds_are_independent_units=false", followup["statistical_semantics"])
        self.assertIn("Existing independent human authorization", followup["revision_ledger"])


if __name__ == "__main__":
    unittest.main()
