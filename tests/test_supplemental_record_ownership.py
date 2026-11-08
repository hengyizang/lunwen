"""Authoring boundaries apply inside follow-up studies before protocol sealing."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator as api
from scripts import artifact_ownership, researchctl
from scripts.research_artifacts import write


class SupplementalRecordOwnershipTests(unittest.TestCase):
    protected = (
        "power-analysis.json", "preregistration.json", "reproduction-confirmation.json",
        "watermark-assessment.json", "style/academic-style-audit.json",
        "reviews/ref-verify.json", "reviews/revision-trace.json", "reviews/revision-integrity.json",
        "reviews/revision-ledger-report.json", "reviews/revision-render.json", "reviews/cloud-tex-build.json",
        "reviews/reporting-guideline.json", "reviews/revision-authorizations.json",
        "reviews/revision-base.tex", "reviews/revision-base.docx", "reviews/revision-base/main.tex",
        "reviews/pre-submission-review.json", "reviews/statistical-reporting.json", "reviews/docx-revision.json",
        "submission-materials/revision/response.docx",
    )

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "projects/demo"
        write(self.project / "state/run.json", {
            "gate": "G5", "stage": "writing-and-review", "active_paper": "P02", "paper_count": 2,
            "paper_execution_mode": "independent", "approvals": [], "approved_gates": [],
        })
        self.prefix = "experiments/supplemental/P02/I001/s001"
        write(self.project / self.prefix / "state/run.json", {
            "gate": "G3", "stage": "experiment-design", "active_paper": "P02", "paper_count": 1,
            "supplemental_context": {"paper_id": "P02"}, "approvals": [], "approved_gates": [],
        })
        for target, name, value in ((api, "ROOT", self.root), (researchctl, "PROJECTS_ROOT", self.root / "projects")):
            patched = patch.object(target, name, value)
            patched.start()
            self.addCleanup(patched.stop)

    def relative(self, name):
        return f"{self.prefix}/papers/P02/{name}"

    def test_api_rejects_nested_control_records_and_preserves_author_scientific_inputs(self):
        for name in self.protected:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Executor-owned"):
                api.safe_target("demo", self.relative(name))
        for name in ("paper-contract.json", "study-protocol.json", "experiment-evidence-plan.json",
                     "baseline-reproduction.json", "clean-room-reproduction.json",
                     "statistical-reporting-map.json", "experiments/design.json"):
            with self.subTest(name=name):
                relative = self.relative(name)
                self.assertFalse(artifact_ownership.executor_owned(self.project, relative))
                self.assertEqual(api.safe_target("demo", relative), self.project / relative)
