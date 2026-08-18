from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import researchctl
from scripts.submission_package import build_package


class SubmissionPackageTests(unittest.TestCase):
    def make_project(self, root: Path, ready: bool = True) -> Path:
        project = root / "demo-study"
        paper = project / "papers" / "P01"
        for name in ("manuscript", "figures", "tables", "supplement", "submission-materials", "reviews"):
            (paper / name).mkdir(parents=True, exist_ok=True)
        state = {
            "stage_index": 5,
            "stage": "writing-and-review",
            "gate": "G5",
            "paper_count": 1,
            "active_paper": "P01",
            "paper_statuses": {"P01": "submission_ready" if ready else "active"},
        }
        (project / "state").mkdir()
        (project / "state" / "run.json").write_text(json.dumps(state), encoding="utf-8")
        fixtures = {
            "manuscript/main.tex": "\\documentclass{article}\\begin{document}Ready\\end{document}",
            "manuscript/references.bib": "@article{x, title={Verified}}",
            "paper-contract.json": "{}",
            "venue.json": "{}",
            "disclosures.json": "{}",
            "reviews/citation-audit.json": '{"status":"pass"}',
            "reviews/venue-compliance.json": '{"status":"pass","compile":{"status":"skipped_tool_missing"}}',
            "reviews/response-matrix.csv": "item,response,status\n1,done,closed\n",
            "reviews/round-1.md": "review one",
            "reviews/round-2.md": "review two",
            "figures/figure-1.png": "fixture",
            "submission-materials/cover-letter.md": "Dear editor",
        }
        for relative, content in fixtures.items():
            path = paper / relative
            path.write_text(content, encoding="utf-8")
        (project / "data" / "raw").mkdir(parents=True)
        (project / "data" / "raw" / "private.csv").write_text("secret", encoding="utf-8")
        return project

    def test_builds_deterministic_manual_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = self.make_project(root)
            with patch.object(researchctl, "PROJECTS_ROOT", root), patch(
                "scripts.submission_package.project_dir", lambda slug: root / slug
            ):
                first = build_package("demo-study", "P01", root / "first.zip")
                second = build_package("demo-study", "P01", root / "second.zip")
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())
            with zipfile.ZipFile(first) as archive:
                names = set(archive.namelist())
                self.assertIn("SUBMISSION-MANIFEST.json", names)
                self.assertIn("MANUAL-CHECKLIST.md", names)
                self.assertIn("submission-materials/cover-letter.md", names)
                self.assertNotIn("data/raw/private.csv", names)
                manifest = json.loads(archive.read("SUBMISSION-MANIFEST.json"))
                self.assertEqual(manifest["submission_mode"], "manual_only")

    def test_rejects_paper_before_g5_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root, ready=False)
            with patch.object(researchctl, "PROJECTS_ROOT", root), patch(
                "scripts.submission_package.project_dir", lambda slug: root / slug
            ):
                with self.assertRaises(researchctl.ResearchCtlError):
                    build_package("demo-study", "P01", root / "blocked.zip")

    def test_rejects_credential_like_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = self.make_project(root)
            (project / "papers" / "P01" / "submission-materials" / "portal.key").write_text("x", encoding="utf-8")
            with patch.object(researchctl, "PROJECTS_ROOT", root), patch(
                "scripts.submission_package.project_dir", lambda slug: root / slug
            ):
                with self.assertRaises(researchctl.ResearchCtlError):
                    build_package("demo-study", "P01", root / "blocked.zip")


if __name__ == "__main__":
    unittest.main()
