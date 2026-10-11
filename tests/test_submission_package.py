from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import output_provenance, researchctl
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
            "approvals": [],
        }
        (project / "state").mkdir()
        (project / "state" / "run.json").write_text(json.dumps(state), encoding="utf-8")
        fixtures = {
            "manuscript/main.tex": "\\documentclass{article}\\begin{document}\\section{Introduction} " + ("This study presents the method and analysis of the data with reproducible results. " * 35) + "\\end{document}",
            "manuscript/references.bib": "@article{x, title={Verified}}",
            "paper-contract.json": "{}",
            "venue.json": "{}",
            "disclosures.json": "{}",
            "reviews/citation-audit.json": '{"status":"pass"}',
            "reviews/venue-compliance.json": '{"status":"pass","compile":{"status":"skipped_tool_missing"}}',
            "reviews/response-matrix.csv": "item,response,status\n1,done,closed\n",
            "reviews/round-1.md": "review one",
            "reviews/round-2.md": "review two",
            "submission-materials/cover-letter.md": "Dear editor",
            "jcr-verification.json": json.dumps({"schema_version":"1.0","database":"Clarivate Journal Citation Reports","verification_year":datetime.now(timezone.utc).year,"impact_factor":2.5,"quartile":"Q1","category":"Engineering, Mechanical","indexing":"SCIE","source_url":"https://example.org/jcr","verified_by":"Human","verified_at":datetime.now(timezone.utc).isoformat()}),
        }
        for relative, content in fixtures.items():
            path = paper / relative
            path.write_text(content, encoding="utf-8")
        (project / "data" / "raw").mkdir(parents=True)
        (project / "data" / "raw" / "private.csv").write_text("secret", encoding="utf-8")
        final_files=[paper/"manuscript"/"main.tex",paper/"manuscript"/"references.bib",paper/"submission-materials"/"cover-letter.md"]
        output_provenance.record_model_writes(project,final_files,family="openai",provider="codex",model="test",role="persistent-writer",run_id="test")
        # Supply the new mechanical controls with explicit synthetic provenance.
        # This fixture demonstrates packaging, not a scientifically valid paper.
        from scripts import incremental_writing, research_increments
        from scripts.research_artifacts import write, sha
        evidence = project / "evidence/fixture.txt"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("Synthetic bounded packaging fixture.", encoding="utf-8")
        anchor = {"path": "evidence/fixture.txt", "sha256": sha(evidence), "kind": "source_lines",
                  "start_line": 1, "end_line": 1, "quote": evidence.read_text(encoding="utf-8")}
        write(paper / "reviews/paper-facts.json", {"facts": [{"id": "FIXTURE", "statement": "Synthetic fixture"}]})
        increments = research_increments.initialize(project)
        units = incremental_writing.inventory(project, "P01")["units"]
        argument = {"id": "PACKAGING", "paper_id": "P01", "precedence": [], "paragraphs": [
            {"paragraph_id": "PAR" + str(index), "section": "Introduction", "function": "context",
             "purpose": "Exercise packaging fixture coverage", "claim_ids": ["FIXTURE"],
             "inference_boundary": "Synthetic engineering fixture only", "transition": "Fixture continuation",
             "units": [{"unit_id": unit["unit_id"], "sha256": unit["sha256"]}]}
            for index, unit in enumerate(units, 1)]}
        increments["arguments"] = [argument]
        increments["lineage"] = [{"id": "PACKAGING", "paper_id": "P01", "nodes": [
            {"id": "SOURCE", "kind": "primary_finding", "research_state": "unknown", "read_scope": "excerpt",
             "statement": "Synthetic packaging source", "boundary": "Not scientific evidence",
             "parents": [], "evidence": [anchor]}], "fact_links": [{"fact_id": "FIXTURE", "node_id": "SOURCE"}]}]
        write(project / research_increments.PLAN, increments)
        incremental_writing.freeze_plan(project, argument, phase="before_writer")
        research_increments.refresh(project)
        old=researchctl.PROJECTS_ROOT
        try:
            researchctl.PROJECTS_ROOT=root
            state["approvals"].append({"gate":"G5","paper_id":"P01","paper_artifact_sha256":researchctl.paper_artifact_hash("demo-study","P01")})
        finally:researchctl.PROJECTS_ROOT=old
        (project / "state" / "run.json").write_text(json.dumps(state), encoding="utf-8")
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
                self.assertNotIn("paper-contract.json",names)
                self.assertNotIn("reviews/citation-audit.json",names)
                manifest = json.loads(archive.read("SUBMISSION-MANIFEST.json"))
                self.assertEqual(manifest["submission_mode"], "manual_only")
                self.assertFalse(
                    manifest["output_policy"]["anthropic_final_outputs_allowed"]
                )

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

    def test_rejects_current_anthropic_authored_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = self.make_project(root)
            manuscript = project / "papers" / "P01" / "manuscript" / "main.tex"
            output_provenance.record_model_writes(
                project,
                [manuscript],
                family="anthropic",
                provider="uuapi-anthropic",
                model="claude-test",
                role="persistent-writer",
                run_id="test-run",
            )
            with patch.object(researchctl, "PROJECTS_ROOT", root), patch(
                "scripts.submission_package.project_dir", lambda slug: root / slug
            ):
                with self.assertRaises(researchctl.ResearchCtlError):
                    build_package("demo-study", "P01", root / "blocked.zip")


if __name__ == "__main__":
    unittest.main()
