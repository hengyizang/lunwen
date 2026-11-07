from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import output_provenance, researchctl
from scripts.submission_package import build_package


class SubmissionPackageTests(unittest.TestCase):
    def test_final_binding_includes_protected_panel_outside_the_paper_tree(self):
        from scripts import submission_package as packaging, review_panel, model_runtime, ai_providers
        from tests.test_review_panel import panel_inputs
        def response(project, **kwargs):
            seat=kwargs["role"].removeprefix("independent-critic-panel-")
            return ai_providers.ModelResult(kwargs["provider"],kwargs["model"],json.dumps({
                "view":seat,"findings":[],"uncertainty":["Synthetic transport fixture only"]}),{},
                reported_model=kwargs["model"],completion_status="completed",cache_hit=False)
        with tempfile.TemporaryDirectory() as directory:
            project=self.make_project(Path(directory),mock_submission=False)
            panel_inputs(project)
            with patch.dict(os.environ,{"DR_OS_CLOUD_EXECUTOR":"1"}), \
                 patch.object(model_runtime,"preflight_route",return_value={}), \
                 patch.object(model_runtime,"call",side_effect=response):
                review_panel.run(project,"P01","binding-fixture")
            original=packaging.submission_check_binding(project,"P01")
            latest=project/review_panel.PREFIX/"P01/latest.json"
            saved=latest.read_bytes()
            latest.unlink()
            self.assertNotEqual(original,packaging.submission_check_binding(project,"P01"))
            latest.write_bytes(saved)
            records=review_panel.responses(project,"P01")
            response_path=project/records[0]["receipt"]["response"]["path"]
            response_path.write_text(response_path.read_text()+" ")
            with self.assertRaisesRegex(ValueError,"changed|provenance"):
                packaging.submission_check_binding(project,"P01")

    def test_final_checks_reuse_the_existing_g5_binding_and_detect_changed_external_source(self):
        from scripts import submission_package as packaging
        from scripts.research_artifacts import read,write,sha
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project=self.make_project(root,mock_submission=False)
            source=project/"evidence/journal-scope.txt"
            source.write_text("Synthetic official scope snapshot, not real journal evidence.",encoding="utf-8")
            venue=read(project/"papers/P01/venue.json")
            write(project/"program/journal-dossiers.json",{"journals":[{"venue_id":venue["venue_id"],"fields":{
                "apc":{"status":"unknown","reason":"Synthetic binding fixture only",
                       "source":{"path":source.relative_to(project).as_posix(),"sha256":sha(source)}},
                "ai_policy":{"source":{"path":"../../ignored-policy"}}}}]})
            with patch.object(researchctl,"PROJECTS_ROOT",root),patch("scripts.submission_package.project_dir",lambda slug:root/slug), \
                 patch("scripts.manuscript_audit.validate_saved_report",return_value=[]), \
                 patch.object(packaging,"submission_checks",return_value=[]) as checked:
                # The stub is an explicit synthetic B result. This test checks
                # reuse/invalidations; native compilation is tested separately.
                self.assertEqual(packaging.submission_checks(project,"P01"),[])
                state=read(project/"state/run.json")
                state["approvals"][-1]["submission_checks_sha256"]=packaging.submission_check_binding(project,"P01")
                write(project/"state/run.json",state)
                build_package("demo-study","P01",root/"first.zip")
                build_package("demo-study","P01",root/"second.zip")
                self.assertEqual(checked.call_count,1)
                source.write_text("Changed actual official-source bytes.",encoding="utf-8")
                with self.assertRaisesRegex(researchctl.ResearchCtlError,"submission inputs changed|Paper changed after"):
                    build_package("demo-study","P01",root/"changed.zip")
                self.assertEqual(checked.call_count,1)

    def test_submission_check_rejects_legacy_silent_tool_skip_without_fixed_age_expiry(self):
        from scripts.submission_package import submission_checks
        from scripts.research_artifacts import read,write
        with tempfile.TemporaryDirectory() as directory:
            project=self.make_project(Path(directory),mock_submission=False)
            paper=project/"papers/P01"
            for name in ("venue.json","reviews/venue-compliance.json","reviews/citation-audit.json"):
                value=read(paper/name)
                value.update(created_at="2001-01-01T00:00:00Z",g5_reverified_at="2001-01-01T00:00:00Z")
                write(paper/name,value)
            with patch("scripts.model_runtime.call",side_effect=AssertionError("No model calls")):
                errors=submission_checks(project,"P01")
            self.assertTrue(any("actual LaTeX compilation must pass" in issue for issue in errors),errors)
            self.assertFalse(any("within 120" in issue or "within 180" in issue for issue in errors),errors)

    def make_project(self, root: Path, ready: bool = True, *, mock_visual: bool = True, mock_submission: bool = True) -> Path:
        # These ZIP fixtures contain no statistical study or real revision.
        # Their native A checks have separate result/source preservation tests.
        for name in ("statistical_reporting", "revision_integrity"):
            check = patch("scripts." + name + ".validate_saved_report", return_value=[])
            check.start(); self.addCleanup(check.stop)
        if mock_submission:
            # ZIP and A-integrity unit tests use an explicitly synthetic B result;
            # actual missing-tool/phase/binding checks are exercised separately.
            checks=patch("scripts.submission_package.submission_checks",return_value=[])
            checks.start();self.addCleanup(checks.stop)
        if mock_visual:
            # These synthetic cases isolate packaging; actual attachment/model
            # binding is tested in test_automated_visual_review. They never
            # represent completed rendering or a scientific manuscript.
            visual = patch("scripts.automated_visual_review.verify", return_value=[])
            visual.start(); self.addCleanup(visual.stop)
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
            "manuscript/main.tex": "\\documentclass{article}\\begin{document}\\section{Introduction} " + ("This study presents the method and analysis of the data with reproducible results. " * 35) + "This is a computational experimental study. \\end{document}",
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
        # Source-bound synthetic policy; this does not assert a real exemption.
        from scripts.research_artifacts import write, sha
        policy = project / "evidence/packaging-policy.txt"
        policy.parent.mkdir(parents=True)
        policy.write_text("Synthetic packaging fixture: no manuscript declaration is required by this test policy. Research Article accepts computational research in this synthetic packaging fixture.\n", encoding="utf-8")
        write(paper / "venue.json", {"venue_id": "fixture", "name": "Synthetic Packaging Journal", "scope": {"official_url": "https://publisher.example/scope"}})
        write(paper / "disclosures.json", {"status": "ready_for_review",
            "ai_use": "The synthetic authoring fixture records OpenAI prose drafting and checks all scientific content manually.",
            "ai_policy": {"venue_id": "fixture", "official_url": "https://publisher.example/policy",
                "checked_at": datetime.now(timezone.utc).isoformat(), "requirement": "not_required",
                "rationale": "This synthetic policy exercises packaging only and asserts no real journal exemption.",
                "evidence": {"path": "evidence/packaging-policy.txt", "sha256": sha(policy), "start_line": 1, "end_line": 1,
                    "quote": "no manuscript declaration is required by this test policy"}}})
        # The research identity is a structural packaging fixture, not real
        # publisher policy, originality evidence or completed scientific review.
        from scripts.research_identity import template as identity_template
        write(paper / "paper-contract.json", {"target_venues": [{"name": "Synthetic Packaging Journal", "article_type": "Research Article"}],
            "independence": {"unique_claim_ids": ["FIXTURE"]}})
        write(project / "program/venue-candidates.json", {"papers": [{"paper_id": "P01", "candidates": [{
            "name": "Synthetic Packaging Journal", "article_type": "Research Article",
            "official_guidelines_url": "https://publisher.example/guidelines", "policy_source_url": "https://publisher.example/policy"}]}]})
        identity = identity_template("P01")
        identity.update(research_kind="primary", design_family="computational", methods=["synthetic_packaging_fixture"],
            reporting_description="computational experimental study", claim_ids=["FIXTURE"],
            new_analysis_rationale="This synthetic record exercises the packaging identity boundary and establishes no scientific contribution.",
            validation_plan="This is an isolated deterministic packaging fixture, not a scientifically validated computational study.",
            venue_classifications=[{"venue_name": "Synthetic Packaging Journal", "article_type": "Research Article",
                "official_url": "https://publisher.example/policy", "checked_at": datetime.now(timezone.utc).isoformat(),
                "research_article_eligible": True, "design_eligible": True,
                "rationale": "This synthetic source exercises category binding only and does not assert a real journal policy or eligibility.",
                "evidence": {"path": "evidence/packaging-policy.txt", "sha256": sha(policy), "start_line": 1, "end_line": 1,
                    "quote": "Research Article accepts computational research in this synthetic packaging fixture."}}],
            reporting_statement={"excerpt": "This is a computational experimental study.", "location": {
                "kind": "source_lines", "path": "manuscript/main.tex", "sha256": sha(paper / "manuscript/main.tex"), "start_line": 1, "end_line": 1}})
        write(paper / "research-identity.json", identity)
        write(paper / "reviews/pre-submission-checklist.json", {"article_type": "computational"})
        from tests.review_scope_fixtures import prepare_scope
        prepare_scope(project,state)
        (project / "data" / "raw").mkdir(parents=True)
        (project / "data" / "raw" / "private.csv").write_text("secret", encoding="utf-8")
        final_files=[paper/"manuscript"/"main.tex",paper/"manuscript"/"references.bib",paper/"submission-materials"/"cover-letter.md"]
        output_provenance.record_model_writes(project,final_files,family="openai",provider="codex",model="test",role="persistent-writer",run_id="test")
        # Supply the new mechanical controls with explicit synthetic provenance.
        # This fixture demonstrates packaging, not a scientifically valid paper.
        from scripts import incremental_writing, research_increments
        from scripts.research_artifacts import write, sha
        evidence = project / "evidence/fixture.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("Synthetic bounded packaging fixture.", encoding="utf-8")
        anchor = {"path": "evidence/fixture.txt", "sha256": sha(evidence), "kind": "source_lines",
                  "start_line": 1, "end_line": 1, "quote": evidence.read_text(encoding="utf-8")}
        write(paper / "reviews/paper-facts.json", {"facts": [{"id": "FIXTURE", "statement": "Synthetic fixture"}]})
        increments = research_increments.initialize(project)
        units = incremental_writing.inventory(project, "P01")["units"]
        argument = {"id": "PACKAGING", "paper_id": "P01", "precedence": [], "paragraphs": [
            {"paragraph_id": "PAR" + str(index), "section": "Introduction", "function": "context",
             "purpose": "Exercise packaging fixture coverage", "claim_ids": ["FIXTURE"],
             "takeaway": "The synthetic fixture exercises deterministic packaging coverage.",
             "warrant": "The bounded fixture establishes packaging behavior only and no scientific conclusion.",
             "reasoning_status": "ready_for_scientific_review", "material_needs": [],
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
        from scripts.manuscript_hygiene import refresh as refresh_hygiene
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            refresh_hygiene(project, "P01")
            from scripts import publication_disclosure, statistical_watermarks
            publication_disclosure.refresh(project, "P01")
            statistical_watermarks.refresh(project, "P01")
        from tests.review_scope_fixtures import seal_review
        seal_review(project,state)
        old=researchctl.PROJECTS_ROOT
        try:
            researchctl.PROJECTS_ROOT=root
            state["approvals"].append({"gate":"G5","paper_id":"P01","paper_artifact_sha256":researchctl.paper_artifact_hash("demo-study","P01")})
        finally:researchctl.PROJECTS_ROOT=old
        (project / "state" / "run.json").write_text(json.dumps(state), encoding="utf-8")
        return project

    def test_missing_final_render_or_visual_receipt_blocks_complete_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.make_project(root,mock_visual=False,mock_submission=False)
            with patch.object(researchctl,"PROJECTS_ROOT",root), patch("scripts.submission_package.project_dir",lambda slug:root/slug):
                with self.assertRaisesRegex(researchctl.ResearchCtlError,"LaTeX compilation|final PDF"):
                    build_package("demo-study","P01",root/"blocked.zip")

    def test_builds_deterministic_manual_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = self.make_project(root)
            with patch.object(researchctl, "PROJECTS_ROOT", root), patch(
                "scripts.submission_package.project_dir", lambda slug: root / slug
            ), patch("scripts.manuscript_audit.validate_saved_report", return_value=[]) as validate_manuscript:
                # Isolate ZIP assembly; real scientific rejection is tested below.
                first = build_package("demo-study", "P01", root / "first.zip")
                second = build_package("demo-study", "P01", root / "second.zip")
                self.assertEqual(validate_manuscript.call_count, 2)
                validate_manuscript.assert_called_with(project / "papers/P01")
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(), hashlib.sha256(second.read_bytes()).hexdigest())
            with zipfile.ZipFile(first) as archive:
                names = set(archive.namelist())
                self.assertIn("SUBMISSION-MANIFEST.json", names)
                self.assertIn("MANUAL-CHECKLIST.md", names)
                self.assertIn("submission-materials/cover-letter.md", names)
                self.assertNotIn("data/raw/private.csv", names)
                self.assertNotIn("paper-contract.json",names)
                self.assertNotIn("reviews/citation-audit.json",names)
                self.assertFalse(any("manuscript-hygiene" in name or "original.tex" in name for name in names))
                manifest = json.loads(archive.read("SUBMISSION-MANIFEST.json"))
                self.assertEqual(manifest["submission_mode"], "manual_only")
                self.assertFalse(
                    manifest["output_policy"]["anthropic_final_outputs_allowed"]
                )

    def test_observation_refresh_keeps_current_g5_package_but_new_citation_needs_full_text(self):
        from scripts.research_artifacts import read, write
        from scripts import manuscript_hygiene as hygiene, review_receipts
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); project = self.make_project(root)
            paper = project / "papers/P01"
            with patch.object(researchctl, "PROJECTS_ROOT", root), patch(
                    "scripts.submission_package.project_dir", return_value=project), patch(
                    "scripts.manuscript_audit.validate_saved_report", return_value=[]):
                before = researchctl.paper_artifact_hash("demo-study", "P01")
                reviewed = review_receipts.material_snapshot(project, "writing-and-review", "P01")
                write(paper / "style/academic-style-audit.json", {"status": "observed", "warnings": ["Optional wording hint"]})
                write(paper / "reviews/revision-ledger.json", {})
                with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
                    hygiene.refresh(project, "P01")
                    from scripts import statistical_watermarks
                    statistical_watermarks.refresh(project, "P01")
                self.assertEqual(researchctl.paper_artifact_hash("demo-study", "P01"), before)
                self.assertEqual(review_receipts.material_snapshot(project, "writing-and-review", "P01"), reviewed)
                build_package("demo-study", "P01", root / "observations.zip")
                manuscript = paper / "manuscript/main.tex"
                manuscript.write_text(manuscript.read_text().replace(r"\end{document}",
                    r"An unsupported source claim.\cite{x}\end{document}"), encoding="utf-8")
                self.assertNotEqual(researchctl.paper_artifact_hash("demo-study", "P01"), before)
                # Even an explicitly synthetic reseal cannot bypass the same A
                # source-support check used by native G5.
                state = read(project / "state/run.json")
                state["approvals"][-1]["paper_artifact_sha256"] = researchctl.paper_artifact_hash("demo-study", "P01")
                write(project / "state/run.json", state)
                with self.assertRaisesRegex(researchctl.ResearchCtlError, "full-text.*covering cited keys: x"):
                    build_package("demo-study", "P01", root / "unsupported.zip")

    def test_package_requires_current_manuscript_contribution_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_project(root)
            with patch.object(researchctl, "PROJECTS_ROOT", root), patch(
                "scripts.submission_package.project_dir", lambda slug: root / slug
            ):
                with self.assertRaisesRegex(researchctl.ResearchCtlError, "paper-facts input and manuscript audit must both exist"):
                    build_package("demo-study", "P01", root / "blocked.zip")
            self.assertFalse((root / "blocked.zip").exists())

    def test_package_recomputes_hygiene_even_if_an_approval_hash_is_incorrectly_resigned(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = self.make_project(root)
            latest = project / "reports/manuscript-hygiene/P01/latest.json"
            report = json.loads(latest.read_text(encoding="utf-8"))
            report["watermark_absence_verified"] = True
            latest.write_text(json.dumps(report), encoding="utf-8")
            from scripts.manuscript_hygiene import _record
            _record(project, [latest], "synthetic-forgery")
            with patch.object(researchctl, "PROJECTS_ROOT", root), patch(
                "scripts.submission_package.project_dir", lambda slug: root / slug
            ):
                state = json.loads((project / "state/run.json").read_text(encoding="utf-8"))
                state["approvals"][-1]["paper_artifact_sha256"] = researchctl.paper_artifact_hash("demo-study", "P01")
                (project / "state/run.json").write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaisesRegex(researchctl.ResearchCtlError, "hygiene audit"):
                    build_package("demo-study", "P01", root / "blocked.zip")

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
