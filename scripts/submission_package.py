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


def tex_dependency_files(paper: Path, manuscript: Path) -> list[Path]:
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
        if path.suffix.lower() in {".sty",".cls",".bst",".def",".cfg",".clo"}:
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


def select_files(paper: Path) -> list[Path]:
    manuscript = paper / "manuscript"
    sources = [path for path in (manuscript / "main.tex", manuscript / "main.docx") if path.is_file()]
    if len(sources) != 1:
        raise ResearchCtlError("Exactly one manuscript/main.tex or manuscript/main.docx is required.")

    selected = tex_dependency_files(paper,sources[0]) if sources[0].suffix.lower()==".tex" else list(sources)
    for name in ("references.bib", "main.pdf"):
        path = manuscript / name
        if path.is_file():
            selected.append(path)
    for dirname in OPTIONAL_DIRS:
        selected.extend(directory_files(paper / dirname, paper))

    compliance = load_object(paper / "reviews" / "venue-compliance.json")
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

Research-stage checks are completed by the recorded automated workflow after
human selection of the doctoral topic and every paper topic. Packaging does not
waive external authorship, consent or publisher requirements.

- [ ] Satisfy the journal's author agreement and any co-author consent requirements.
- [ ] Match portal metadata to the manuscript exactly.
- [ ] Upload files manually and preview the portal-generated proof.
- [ ] Save the portal receipt and submitted version outside this archive.

Do not upload `SUBMISSION-MANIFEST.json` or this checklist unless the journal requests them.
"""
    return text.encode("utf-8")


def build_package(slug: str, paper_id: str, output: Path | None = None) -> Path:
    from scripts.paper_execution import enabled,scope
    project=project_dir(slug)
    if enabled(project):
        with scope(project,paper_id):
            return _build_package(slug,paper_id,output)
    return _build_package(slug,paper_id,output)


def _build_package(slug: str, paper_id: str, output: Path | None = None) -> Path:
    paper_id = validate_paper_id(paper_id)
    state = load_state(slug)
    if state.get("paper_statuses", {}).get(paper_id) != "submission_ready":
        raise ResearchCtlError(f"{paper_id} has not passed its G5 checks.")
    paper = project_dir(slug) / "papers" / paper_id
    if not paper.is_dir():
        raise ResearchCtlError(f"Missing paper directory: {paper}")

    project = paper.parent.parent
    venue_errors = validate_selected_venue(project, paper_id)
    if venue_errors:
        raise ResearchCtlError("; ".join(venue_errors))
    approval=next((item for item in reversed(state.get("approvals",[])) if item.get("gate")=="G5" and item.get("paper_id")==paper_id),None)
    if not approval or approval.get("paper_artifact_sha256")!=paper_artifact_hash(slug,paper_id):
        raise ResearchCtlError("Paper changed after the G5 decision or lacks its current per-paper hash; re-run G5 checks")
    try:
        try:from scripts.jcr_verify import verify as verify_jcr_payload
        except ModuleNotFoundError:from jcr_verify import verify as verify_jcr_payload
        try:from scripts.venue_policy import target_from_contract
        except ModuleNotFoundError:from venue_policy import target_from_contract
        verify_jcr_payload(load_object(paper/"jcr-verification.json"),target_from_contract(load_object(paper/"paper-contract.json")))
    except Exception as exc:
        raise ResearchCtlError(f"Current paper-specific JCR verification failed: {exc}") from exc
    try:
        try:from scripts.manuscript_language import analyze_submission
        except ModuleNotFoundError:from manuscript_language import analyze_submission
        language=analyze_submission(paper)
        if language.get("status")!="pass":raise ResearchCtlError("English submission validation failed: "+"; ".join(language.get("errors",[])))
        from scripts.citation_audit import validate_provider_identities
        citation_identity_errors=validate_provider_identities(paper/"manuscript/references.bib",load_object(paper/"reviews/citation-audit.json"))
        if citation_identity_errors:raise ResearchCtlError("Citation identity evidence failed: "+"; ".join(citation_identity_errors))
        try:from scripts.figure_provenance import validate_figure_provenance
        except ModuleNotFoundError:from figure_provenance import validate_figure_provenance
        figure_errors=validate_figure_provenance(project,paper)
        if figure_errors:raise ResearchCtlError("Figure provenance failed: "+"; ".join(figure_errors))
        from scripts.manuscript_docx import validate_saved_report as validate_docx_build
        docx_errors=validate_docx_build(paper)
        if docx_errors:raise ResearchCtlError("DOCX build/visual checks failed: "+"; ".join(docx_errors))
        if (paper/"manuscript/main.tex").is_file():
            from scripts.automated_visual_review import verify as verify_visual
            visual_errors=verify_visual(project,paper_id,f"papers/{paper_id}/manuscript/main.tex")
            if visual_errors:raise ResearchCtlError("Final PDF visual checks failed: "+"; ".join(visual_errors))
        from scripts.docx_revision import validate_saved_report as validate_word_revision
        revision_errors=validate_word_revision(project,paper_id)
        from scripts.revision_ledger import validate_saved_report as validate_revision_ledger
        revision_errors.extend(validate_revision_ledger(project,paper_id,require_when_changed=True))
        if (project/"program/research-support.json").exists():
            from scripts.research_support import validate_saved_report as validate_support
            revision_errors.extend(validate_support(project))
        if (project/"program/review-packets.json").exists():
            from scripts.review_packets import validate_gate_reviews
            revision_errors.extend(validate_gate_reviews(project,paper_id))
        from scripts.research_extensions import gate_errors as extension_errors
        revision_errors.extend(extension_errors(project))
        from scripts.research_increments import gate_errors as increment_errors
        revision_errors.extend(increment_errors(project, "G5", paper_id))
        from scripts.manuscript_audit import validate_saved_report as validate_manuscript
        revision_errors.extend(validate_manuscript(paper))
        from scripts.empirical_workflow import gate_errors as empirical_errors
        revision_errors.extend(empirical_errors(project, "G5", paper_id))
        from scripts.manuscript_hygiene import validate_saved_report as validate_hygiene
        revision_errors.extend(validate_hygiene(project, paper_id))
        from scripts import reviewer_rounds, publication_disclosure, statistical_watermarks
        for module in (reviewer_rounds, publication_disclosure, statistical_watermarks):
            revision_errors.extend(module.validate_saved_report(project, paper_id))
        from scripts.research_identity import validate as validate_research_identity
        revision_errors.extend(validate_research_identity(project, paper_id, "G5"))
        from scripts.review_receipts import validate_gate as validate_review_receipts
        from scripts.scientific_scope import validate as validate_scientific_scope
        revision_errors.extend(validate_review_receipts(project,"G5",paper_id))
        revision_errors.extend(validate_scientific_scope(project,"G5",paper_id))
        if revision_errors:raise ResearchCtlError("Word revision package failed: "+"; ".join(revision_errors))
    except ImportError as exc:
        raise ResearchCtlError(f"Submission validator unavailable: {exc}") from exc
    files = select_files(paper)
    try:
        require_final_origins(project, files)
    except ProvenanceError as exc:
        raise ResearchCtlError(str(exc)) from exc
    origins = provenance_report(project, files)
    entries: dict[str, bytes] = {
        path.relative_to(paper).as_posix(): path.read_bytes() for path in files
    }
    entries["MANUAL-CHECKLIST.md"] = checklist(slug, paper_id)
    manifest = {
        "schema_version": "1.0",
        "project": slug,
        "paper_id": paper_id,
        "submission_mode": "manual_only",
        "output_policy": {
            "anthropic_final_outputs_allowed": False,
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

    destination = output or paper / "submission" / "manual-upload.zip"
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
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--project", required=True)
    value.add_argument("--paper", required=True)
    value.add_argument("--output", type=Path)
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        destination = build_package(args.project, args.paper, args.output)
    except ResearchCtlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(destination)
    print("Package created for manual upload only; no submission action was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
