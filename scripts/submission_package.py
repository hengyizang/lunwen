#!/usr/bin/env python3
"""Build a deterministic, local-only package for manual journal submission."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from researchctl import ResearchCtlError, file_sha256, load_state, paper_artifact_hash, project_dir, validate_paper_id
except ModuleNotFoundError:  # Support `python -m unittest` package imports.
    from scripts.researchctl import (
        ResearchCtlError,
        file_sha256,
        load_state,
        paper_artifact_hash,
        project_dir,
        validate_paper_id,
    )

try:
    from output_provenance import (
        ProvenanceError,
        provenance_report,
        require_final_origins,
    )
except ModuleNotFoundError:
    from scripts.output_provenance import (
        ProvenanceError,
        provenance_report,
        require_final_origins,
    )


SECRET_NAMES = {".env", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
SECRET_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
OPTIONAL_DIRS = ("figures", "tables", "supplement", "submission-materials")
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ResearchCtlError(f"Missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ResearchCtlError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchCtlError(f"Expected a JSON object: {path}")
    return value


def validate_selected_venue(project: Path, paper_id: str) -> list[str]:
    """Example-only venue metadata is never a submission target."""
    if not re.fullmatch(r"P[0-9]{2}", paper_id):
        return ["an exact paper ID is required for venue validation"]
    try:
        venue = load_object(project / "papers" / paper_id / "venue.json")
    except ResearchCtlError as exc:
        return [str(exc)]
    if "trial_only" in venue and type(venue["trial_only"]) is not bool:
        return [f"{paper_id}/venue.json: trial_only must be a boolean"]
    if venue.get("trial_only") is True or venue.get("selection_status") == "trial":
        return [f"{paper_id}/venue.json: trial_only example venue cannot enter submission-ready; select a verified target"]
    return []



def submission_checks(project: Path, paper_id: str, *, warnings: list[str] | None = None) -> list[str]:
    """Inspect current selected material without scoring or stage-approval prerequisites.

    No check here acquires data, runs an experiment, submits, or invokes a model.
    """
    from scripts import citation_audit, journal_dossier, jcr_verify, venue_policy, venue_compliance
    from scripts import manuscript_docx, revision_render, reporting_checklist, study_routes, publication_disclosure
    paper=project/"papers"/paper_id;errors=validate_selected_venue(project,paper_id);venue={}
    def check(label, callback):
        try:errors.extend(f"{paper_id} {label}: {issue}" for issue in callback())
        except (OSError,ValueError,RuntimeError,KeyError,TypeError,ImportError) as exc:errors.append(f"{paper_id} {label}: {exc}")
    def rendered_pdf():
        if (paper / "reviews/revision-render.json").is_file():
            revision_render.validate_render_manifest(paper)
        else:
            report = load_object(paper / "reviews/venue-compliance.json")
            value = report.get("compile", {}).get("pdf") or report.get("compile", {}).get("pdf_path")
            if not isinstance(value, str) or not value:
                raise ValueError("actual compiled PDF is missing")
            pdf = Path(value)
            if not pdf.is_absolute():
                pdf = paper / pdf
            safe_file(pdf, paper)
            revision_render.validate_render_receipt(paper, pdf, paper / "reviews/venue-compliance.json")
        return []
    # Quartiles and impact factors describe targets; they are not scientific
    # validity or automatic venue-fit cutoffs. Preserve unknown metadata.
    if warnings is not None:
        try:warnings.extend(f"{paper_id} JCR planning observation: {issue}" for issue in jcr_verify.verify(load_object(paper/"jcr-verification.json"),venue_policy.target_from_contract(load_object(paper/"paper-contract.json"))))
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:warnings.append(f"{paper_id} JCR planning observation: {exc}")
    try:
        venue=load_object(paper/"venue.json")
        errors.extend(f"{paper_id} journal dossier: {issue}" for issue in journal_dossier.validate_saved_report(project,venue.get("venue_id")))
        manuscripts=[path for path in (paper/"manuscript/main.tex",paper/"manuscript/main.docx") if path.is_file()]
        if len(manuscripts)!=1:raise ResearchCtlError("Exactly one canonical manuscript is required")
        manuscript=manuscripts[0]
        compliance=load_object(paper/"reviews/venue-compliance.json")
        if compliance.get("status")!="pass":errors.append(f"{paper_id} venue compliance report must pass")
        if compliance.get("venue_sha256")!=file_sha256(paper/"venue.json"):errors.append(f"{paper_id} venue compliance is stale for venue.json")
        if compliance.get("manuscript",{}).get("source_tree_sha256")!=venue_compliance.manuscript_tree_sha256(manuscript):errors.append(f"{paper_id} venue compliance is stale for the final manuscript")
        compile_status=compliance.get("compile",{}).get("status")
        if manuscript.suffix.lower()==".tex" and compile_status!="pass":errors.append(f"{paper_id} actual LaTeX compilation must pass; a missing tool or skipped build is not verification")
        elif manuscript.suffix.lower()==".docx" and compile_status not in {"pass","not_applicable"}:errors.append(f"{paper_id} venue compilation has an unexplained skip")
        citation=load_object(paper/"reviews/citation-audit.json")
        bibliography=paper/"manuscript/references.bib"
        if citation.get("status")!="pass":errors.append(f"{paper_id} citation identity audit must pass")
        if citation.get("bibliography_sha256")!=file_sha256(bibliography):errors.append(f"{paper_id} citation audit is stale for references.bib")
        if citation.get("manuscript_sha256")!=citation_audit.manuscript_digest(manuscript):errors.append(f"{paper_id} citation audit is stale for the manuscript")
        errors.extend(f"{paper_id} citation identity: {issue}" for issue in citation_audit.validate_provider_identities(bibliography,citation))
        if manuscript.suffix.lower()==".docx":
            current_keys,mapping_errors=citation_audit.docx_citation_keys(manuscript)
            bib_keys={entry["key"] for entry in citation_audit.parse_bibtex(bibliography.read_text(encoding="utf-8"))}
            usage=citation.get("citation_usage",{})
            if mapping_errors or current_keys-bib_keys or usage.get("status")!="checked_automatically" or sorted(current_keys)!=usage.get("cited_keys"):
                errors.append(f"{paper_id} DOCX citation mapping is incomplete or stale")
        else:check("final PDF",rendered_pdf)
        files=select_files(paper)
        require_final_origins(project,files)
    except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:errors.append(f"{paper_id} final package: {exc}")
    check("DOCX export",lambda:manuscript_docx.validate_saved_report(paper,include_visual=False))
    if ((paper / "reviews/reporting-guideline-input.json").is_file() or
            venue.get("requirements", {}).get("reporting_guideline")):
        check("reporting guideline",lambda:reporting_checklist.audit(paper).get("errors", []))
    check("research exports",lambda:study_routes.export_errors(project,paper_id))
    # Check truthful internal usage; public AI-use statements are author-editable.
    check("recorded internal usage",lambda:publication_disclosure.integrity_errors(project,paper_id))
    if warnings is not None:
        try:
            from scripts.review_panel import submission_errors
            warnings.extend(f"{paper_id} optional source review: {issue}" for issue in submission_errors(project, paper_id))
        except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
            warnings.append(f"{paper_id} optional source review: {exc}")
    return errors


def _submission_inputs(project: Path, paper_id: str) -> dict:
    """Capture the actual final B inputs used by both binding and packaging."""
    from scripts.research_artifacts import path_in
    paper=project/"papers"/paper_id
    paths=set()
    def sources(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in {"path","raw_path","source_path"} and isinstance(item,str):
                    relative = Path(item)
                    if relative.is_absolute():
                        relative = relative.resolve().relative_to(project.resolve())
                    source=path_in(project,relative.as_posix(),exists=False)
                    if source.is_file():paths.add(source)
                else:sources(item)
        elif isinstance(value,list):
            for item in value:sources(item)
    venue=load_object(paper/"venue.json")
    dossiers=project/"program/journal-dossiers.json"
    selected=[]
    if dossiers.is_file():
        from scripts.journal_dossier import FETCH_FIELDS
        selected=[{**row,"fields":{key:value for key,value in row.get("fields",{}).items() if key in FETCH_FIELDS}}
                  for row in load_object(dossiers).get("journals",[]) if row.get("venue_id")==venue.get("venue_id")]
        sources(selected)
    source_index=project/"evidence/journal-sources/index.json"
    receipts={}
    if source_index.is_file():
        all_receipts=load_object(source_index).get("sources",{})
        urls={item.get("url") for row in selected for item in row.get("fields",{}).values() if isinstance(item,dict)}
        receipts={url:all_receipts.get(url) for url in sorted(url for url in urls if isinstance(url,str))}
        sources(receipts)
    # Paper contents are also sealed by paper_artifact_sha256. Include package
    # and local template bytes here because build/venue-template are excluded there.
    paths.update(select_files(paper))
    fixed=("venue.json","submission-files.json","reviews/venue-compliance.json","reviews/citation-audit.json","reviews/revision-render.json","reviews/cloud-tex-build.json","reviews/cloud-word-build.json","disclosures.json",
           "reviews/docx-build.json", "reviews/tex-dependency-rights.json", "reviews/paper-facts.json",
           "statistical-reporting-map.json", "reviews/reporting-guideline-input.json")
    paths.update(paper/name for name in fixed if (paper/name).is_file())
    for name in ("reviews/citation-audit.json", "reviews/docx-build.json", "reviews/paper-facts.json", "statistical-reporting-map.json"):
        if (paper/name).is_file():sources(load_object(paper/name))
    selected_paths = select_files(paper)
    selected_names = {path.relative_to(project).as_posix() for path in selected_paths}
    registry = paper / "figures/figure-provenance.json"
    selected_figures = ([row for row in load_object(registry).get("figures", [])
                         if isinstance(row, dict) and row.get("figure_path") in selected_names]
                        if registry.is_file() and any(path.is_relative_to(paper / "figures") for path in selected_paths) else [])
    sources(selected_figures)
    for receipt in (paper / "figures").glob("*.editable-export.json"):
        try:
            value = load_object(receipt)
        except ResearchCtlError:
            if receipt in selected_paths:
                raise
            continue
        if any(isinstance(row, dict) and row.get("path") in selected_names for row in value.get("outputs", [])):
            paths.add(receipt); sources(value)
    # Optional reviewer opinions have their own source bindings. Their presence
    # does not add a hidden prerequisite to exporting the chosen manuscript.
    module_names=("submission_package.py","journal_dossier.py","jcr_verify.py","venue_policy.py","venue_compliance.py",
        "citation_audit.py","manuscript_docx.py","revision_render.py","cloud_runtime.py","word_render.py",
        "reporting_checklist.py","publication_disclosure.py","review_panel.py","research_artifacts.py",
        "researchctl.py","manuscript_audit.py","literature_source_tasks.py","statistical_reporting.py",
        "revision_integrity.py","figure_provenance.py","manuscript_hygiene.py","research_identity.py",
        "scientific_scope.py","empirical_workflow.py","research_extensions.py","research_increments.py")
    payload={"schema_version":"1.0","paper_id":paper_id,"journal_dossiers":selected,"journal_receipts":receipts,
        "files":{path.relative_to(project).as_posix():file_sha256(path) for path in sorted(paths)},
        "validators":{name:file_sha256(Path(__file__).parent/name) if (Path(__file__).parent/name).is_file() else None for name in module_names},
        "selected_figure_records": selected_figures,
        "provenance":provenance_report(project,select_files(paper))}
    return payload


def _submission_binding(inputs: dict) -> str:
    return sha256_bytes(json.dumps(inputs,sort_keys=True,separators=(",",":")).encode())


def submission_check_binding(project: Path, paper_id: str) -> str:
    """Bind final B inputs to the existing G5 decision without another state file."""
    return _submission_binding(_submission_inputs(project,paper_id))

def safe_file(path: Path, paper: Path) -> None:
    if any(item.is_symlink() for item in (path,*path.parents)):
        raise ResearchCtlError(f"Refusing symlink in submission package: {path}")
    try:
        path.resolve().relative_to(paper.resolve())
    except ValueError as exc:
        raise ResearchCtlError(f"Path escapes paper directory: {path}") from exc
    lowered = path.name.lower()
    if lowered in SECRET_NAMES or path.suffix.lower() in SECRET_SUFFIXES:
        raise ResearchCtlError(f"Refusing credential-like file: {path}")
    if any(part.startswith(".") for part in path.relative_to(paper).parts):
        raise ResearchCtlError(f"Refusing hidden file: {path}")
    if any(part.lower() in {"private","raw","secrets","credentials","api_runs","state"} for part in path.relative_to(paper).parts):
        raise ResearchCtlError(f"Refusing private/control material: {path}")


def tex_dependency_files(paper: Path, manuscript: Path, *, require_rights: bool = True) -> list[Path]:
    """Select actual safe build inputs; third-party source needs reviewable rights."""
    try:
        from scripts.tex_sources import dependencies
        paths=dependencies(manuscript,paper=paper)
    except ValueError as exc:raise ResearchCtlError(str(exc)) from exc
    rights_path=paper/"reviews/tex-dependency-rights.json"
    rights=load_object(rights_path).get("files",[]) if rights_path.is_file() else []
    if not isinstance(rights,list):raise ResearchCtlError("TeX dependency rights files must be an array")
    records={row.get("path"):row for row in rights if isinstance(row,dict)}
    licenses=[]
    for path in paths:
        safe_file(path,paper)
        relative=path.relative_to(paper).as_posix()
        if path.relative_to(paper).parts[0] not in {"manuscript","figures","tables","supplement","submission-materials"}:
            raise ResearchCtlError("Internal review material cannot be a submitted TeX dependency: "+relative)
        if require_rights and path.suffix.lower() in {".sty",".cls",".bst",".def",".cfg",".clo"}:
            row=records.get(relative,{})
            if (row.get("sha256")!=file_sha256(path) or row.get("redistribution_allowed") is not True
                    or not isinstance(row.get("license"),str) or not row["license"].strip()
                    or not str(row.get("confirmed_by","")).strip()):
                raise ResearchCtlError("Local TeX class/style needs current named redistribution-rights evidence: "+relative)
            binding=row.get("license_evidence",{})
            evidence=paper/str(binding.get("path",""))
            safe_file(evidence,paper)
            if (not evidence.is_file() or binding.get("sha256")!=file_sha256(evidence)
                    or evidence.relative_to(paper).parts[0]!="manuscript"):
                raise ResearchCtlError("Local TeX source license evidence is missing, changed or outside manuscript sources")
            licenses.append(evidence)
    return [*paths,*licenses]


def directory_files(directory: Path, paper: Path) -> Iterable[Path]:
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise ResearchCtlError(f"Expected a real directory: {directory}")
    files: list[Path] = []
    for root, dirs, names in os.walk(directory, followlinks=False):
        root_path = Path(root)
        for name in dirs:
            candidate = root_path / name
            if candidate.is_symlink():
                raise ResearchCtlError(f"Refusing symlink in submission package: {candidate}")
        for name in names:
            candidate = root_path / name
            safe_file(candidate, paper)
            if candidate.name == "figure-provenance.json" or candidate.name.endswith(".image-source.json"):
                continue
            if candidate.is_file():
                files.append(candidate)
    return sorted(files, key=lambda item: item.relative_to(paper).as_posix())


def select_files(paper: Path, *, draft: bool = False, warnings: list[str] | None = None) -> list[Path]:
    """Select the manuscript's actual dependencies and explicitly named deliverables.

    Working figures, recipes, thumbnails and abandoned drafts are not a submission
    simply because they share a directory with the chosen paper.
    """
    manuscript = paper / "manuscript"
    sources = [path for path in (manuscript / "main.tex", manuscript / "main.docx") if path.is_file()]
    if not sources and draft:
        sources = [path for path in (manuscript / "main.md", manuscript / "draft.md") if path.is_file()][:1]
    if len(sources) != 1:
        raise ResearchCtlError("Exactly one manuscript/main.tex or manuscript/main.docx is required.")

    selected = list(sources)
    if sources[0].suffix.lower() == ".tex":
        try:
            selected = tex_dependency_files(paper, sources[0], require_rights=not draft)
        except ResearchCtlError as exc:
            if not draft or "Missing" not in str(exc):
                raise
            if warnings is not None:
                warnings.append("Incomplete draft dependency closure: " + str(exc))
    for name in ("references.bib", "main.pdf"):
        path = manuscript / name
        if path.is_file():
            selected.append(path)
    selection_path = paper / "submission-files.json"
    if selection_path.is_file():
        declared = load_object(selection_path).get("files")
        if not isinstance(declared, list) or any(not isinstance(name, str) for name in declared):
            raise ResearchCtlError("submission-files.json must name a files array of paper-relative paths")
        for name in declared:
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] not in {"manuscript", *OPTIONAL_DIRS}:
                raise ResearchCtlError("Selected submission file must be a publishable paper-relative path: " + name)
            selected.append(paper / name)

    compliance_path = paper / "reviews" / "venue-compliance.json"
    compliance = load_object(compliance_path) if compliance_path.is_file() and not draft else {}
    compile_info = compliance.get("compile", {})
    if isinstance(compile_info, dict) and compile_info.get("status") == "pass":
        pdf_value = compile_info.get("pdf") or compile_info.get("pdf_path")
        if isinstance(pdf_value, str) and pdf_value.strip():
            pdf = Path(pdf_value)
            if not pdf.is_absolute():
                pdf = paper / pdf
            safe_file(pdf, paper)
            if pdf.is_file():
                recorded=compile_info.get("pdf_sha256")
                if not isinstance(recorded,str) or recorded!=file_sha256(pdf):
                    raise ResearchCtlError("Compiled PDF changed after venue compliance audit")
                selected.append(pdf)

    unique = {path.resolve(): path for path in selected}
    for path in unique.values():
        safe_file(path, paper)
        if not path.is_file() or path.stat().st_size == 0:
            raise ResearchCtlError(f"Submission file is missing or empty: {path}")
    return sorted(unique.values(), key=lambda item: item.relative_to(paper).as_posix())


def checklist(project: str, paper_id: str) -> bytes:
    text = f"""# Journal upload checklist — {project}/{paper_id}

This archive was prepared locally. It has **not** been submitted anywhere.

The manifest records the selected files and their current hashes. Packaging does
not establish scientific validity or waive authorship, consent or publisher requirements.

- [ ] Satisfy the journal's author agreement and any co-author consent requirements.
- [ ] Match portal metadata to the manuscript exactly.
- [ ] Upload files manually and preview the portal-generated proof.
- [ ] Save the portal receipt and submitted version outside this archive.

Do not upload `SUBMISSION-MANIFEST.json` or this checklist unless the journal requests them.
"""
    return text.encode("utf-8")


def build_package(slug: str, paper_id: str, output: Path | None = None, *, draft: bool = False) -> Path:
    if draft:
        return _build_draft(slug, paper_id, output)
    from scripts.paper_execution import enabled,scope
    project=project_dir(slug)
    if enabled(project):
        with scope(project,paper_id):
            return _build_package(slug,paper_id,output)
    return _build_package(slug,paper_id,output)


def _build_package(slug: str, paper_id: str, output: Path | None = None) -> Path:
    paper_id = validate_paper_id(paper_id)
    paper = project_dir(slug) / "papers" / paper_id
    if not paper.is_dir():
        raise ResearchCtlError(f"Missing paper directory: {paper}")
    project = paper.parent.parent
    venue_errors = validate_selected_venue(project, paper_id)
    if venue_errors:
        raise ResearchCtlError("; ".join(venue_errors))
    snapshot = _submission_inputs(project, paper_id)
    checked_binding = _submission_binding(snapshot)
    observations: list[str] = []
    issues = submission_checks(project, paper_id, warnings=observations)
    from scripts import researchctl
    issues.extend(researchctl.paper_scientific_errors(project, paper_id))
    researchctl.paper_observations(project, paper_id, observations)
    if issues:
        raise ResearchCtlError("Final submission checks failed: " + "; ".join(dict.fromkeys(issues)))
    files = select_files(paper)
    try:
        require_final_origins(project, files)
    except ProvenanceError as exc:
        raise ResearchCtlError(str(exc)) from exc
    origins = snapshot["provenance"]
    entries: dict[str, bytes] = {
        path.relative_to(paper).as_posix(): path.read_bytes() for path in files
    }
    expected = {Path(item["path"]).relative_to(paper.relative_to(project)).as_posix(): snapshot["files"].get(item["path"])
                for item in origins}
    if (set(entries) != set(expected) or any(sha256_bytes(payload) != expected[name] for name,payload in entries.items())
            or any(item.get("sha256") != snapshot["files"].get(item["path"]) for item in origins)):
        raise ResearchCtlError("Submission payload differs from the checked input snapshot")
    entries["MANUAL-CHECKLIST.md"] = checklist(slug, paper_id)
    manifest = {
        "schema_version": "1.0",
        "project": slug,
        "paper_id": paper_id,
        "submission_mode": "manual_only",
        "scientific_completion_verified": False,
        "observations": observations,
        "output_policy": {
            "provenance": origins,
        },
        "files": [
            {"path": name, "size": len(payload), "sha256": sha256_bytes(payload)}
            for name, payload in sorted(entries.items())
        ],
    }
    entries["SUBMISSION-MANIFEST.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    def unchanged():
        if checked_binding != submission_check_binding(project, paper_id):
            raise ResearchCtlError("Submission inputs changed during packaging; rerun the submission check")
    return _write_archive(entries, output or paper / "submission/manual-upload.zip", unchanged)


def _build_draft(slug: str, paper_id: str, output: Path | None = None) -> Path:
    """Export readable work at any stage, without inventing review or readiness."""
    paper_id = validate_paper_id(paper_id)
    paper = project_dir(slug) / "papers" / paper_id
    warnings: list[str] = []
    files = select_files(paper, draft=True, warnings=warnings)
    entries = {path.relative_to(paper).as_posix(): path.read_bytes() for path in files}
    hashes = {name: sha256_bytes(payload) for name, payload in entries.items()}
    selection = paper / "submission-files.json"
    selection_hash = file_sha256(selection) if selection.is_file() else None
    manifest = {"schema_version": "1.0", "project": slug, "paper_id": paper_id,
                "submission_mode": "draft_unreviewed", "submission_ready": False,
                "scientific_completion_verified": False, "warnings": warnings,
                "files": [{"path": name, "size": len(payload), "sha256": hashes[name]}
                          for name, payload in sorted(entries.items())]}
    entries["DRAFT-MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    entries["DRAFT-README.txt"] = b"Unreviewed draft. Export does not certify completeness, scientific validity, or submission readiness.\n"
    def unchanged():
        if (any(not (paper / name).is_file() or file_sha256(paper / name) != value for name, value in hashes.items())
                or (file_sha256(selection) if selection.is_file() else None) != selection_hash):
            raise ResearchCtlError("Draft inputs changed during export; retry using the current files")
    return _write_archive(entries, output or paper / "submission/draft.zip", unchanged)


def _write_archive(entries: dict[str, bytes], destination: Path, unchanged) -> Path:
    """Atomically publish only after checking every written archive member."""
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, payload in sorted(entries.items()):
                if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                    raise ResearchCtlError(f"Unsafe archive path: {name}")
                info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        try:
            with zipfile.ZipFile(temporary) as archive:
                names = archive.namelist()
                if len(names) != len(entries) or set(names) != set(entries):
                    raise ResearchCtlError("Written submission ZIP has a changed or duplicate member inventory")
                for name, payload in entries.items():
                    if archive.getinfo(name).file_size != len(payload):
                        raise ResearchCtlError("Written submission ZIP member size differs from the checked payload: " + name)
                    with archive.open(name) as member:
                        written = member.read(len(payload) + 1)
                    if len(written) != len(payload) or sha256_bytes(written) != sha256_bytes(payload):
                        raise ResearchCtlError("Written submission ZIP differs from the checked payload: " + name)
        except zipfile.BadZipFile as exc:
            raise ResearchCtlError("Written submission ZIP failed CRC or container validation") from exc
        unchanged()
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--project", required=True)
    value.add_argument("--paper", required=True)
    value.add_argument("--output", type=Path)
    value.add_argument("--draft", action="store_true", help="Export current selected materials without submission approval; label the archive as an unreviewed draft")
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        destination = build_package(args.project, args.paper, args.output, draft=args.draft)
    except ResearchCtlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(destination)
    print("Unreviewed draft exported; no submission readiness is asserted." if args.draft else "Package created for manual upload only; no submission action was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
