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
    """B: one final package check, independent of numerical/editorial self-scores.

    G5 records its binding in the existing decision. Packaging reuses that check
    only while the approved paper and its actual external sources remain equal.
    No check here acquires data, runs an experiment, submits, or invokes a model.
    """
    from scripts import citation_audit, journal_dossier, jcr_verify, venue_policy, venue_compliance
    from scripts import manuscript_docx, automated_visual_review, reporting_checklist, study_routes, publication_disclosure
    paper=project/"papers"/paper_id;errors=validate_selected_venue(project,paper_id)
    def check(label, callback):
        try:errors.extend(f"{paper_id} {label}: {issue}" for issue in callback())
        except (OSError,ValueError,RuntimeError,KeyError,TypeError,ImportError) as exc:errors.append(f"{paper_id} {label}: {exc}")
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
        else:check("final PDF",lambda:automated_visual_review.verify(project,paper_id,f"papers/{paper_id}/manuscript/main.tex"))
        files=select_files(paper)
        require_final_origins(project,files)
    except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:errors.append(f"{paper_id} final package: {exc}")
    check("DOCX export",lambda:manuscript_docx.validate_saved_report(paper))
    check("reporting guideline",lambda:reporting_checklist.validate_saved_report(paper))
    check("research exports",lambda:study_routes.export_errors(project,paper_id))
    # Check truthful internal usage; public AI-use statements are author-editable.
    check("recorded internal usage",lambda:publication_disclosure.integrity_errors(project,paper_id))
    try:
        from scripts.review_panel import submission_errors
        check("blind scientific panel",lambda:submission_errors(project,paper_id))
    except ImportError as exc:errors.append(f"{paper_id} blind scientific panel unavailable: {exc}")
    return errors


def submission_check_binding(project: Path, paper_id: str) -> str:
    """Bind final B inputs to the existing G5 decision without another state file."""
    from scripts.research_artifacts import path_in
    paper=project/"papers"/paper_id
    paths=set()
    def sources(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in {"path","raw_path"} and isinstance(item,str):
                    source=path_in(project,item,exists=False)
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
    for directory in ("manuscript","figures","tables","supplement","submission-materials","venue-template"):
        base=paper/directory
        if base.exists():
            for path in base.rglob("*"):
                if path.is_symlink():raise ResearchCtlError("Submission inputs cannot use symlinks")
                if path.is_file():paths.add(path)
    fixed=("venue.json","jcr-verification.json","reviews/venue-compliance.json","reviews/citation-audit.json","reviews/panel-inputs.json","disclosures.json")
    paths.update(paper/name for name in fixed if (paper/name).is_file())
    for name in ("jcr-verification.json","reviews/citation-audit.json","reviews/panel-inputs.json"):
        if (paper/name).is_file():sources(load_object(paper/name))
    # Panel receipts live outside the paper tree. Bind the actual current
    # protected opinions as well as the author's source-bound responses so
    # cached B checks cannot conceal changed or removed review evidence.
    from scripts import review_panel
    latest=path_in(project,f"{review_panel.PREFIX}/{paper_id}/latest.json",exists=False)
    if latest.exists():
        paths.add(latest)
        sources(load_object(latest))
        for row in review_panel.responses(project,paper_id):sources(row["receipt"])
    module_names=("submission_package.py","journal_dossier.py","jcr_verify.py","venue_policy.py","venue_compliance.py","citation_audit.py","manuscript_docx.py","automated_visual_review.py","reporting_checklist.py","publication_disclosure.py","review_panel.py","research_artifacts.py")
    payload={"schema_version":"1.0","paper_id":paper_id,"journal_dossiers":selected,"journal_receipts":receipts,
        "files":{path.relative_to(project).as_posix():file_sha256(path) for path in sorted(paths)},
        "validators":{name:file_sha256(Path(__file__).parent/name) if (Path(__file__).parent/name).is_file() else None for name in module_names},
        "provenance":provenance_report(project,select_files(paper))}
    return sha256_bytes(json.dumps(payload,sort_keys=True,separators=(",",":")).encode())

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
    binding=approval.get("submission_checks_sha256")
    if binding is None:
        # Old G5 records did not carry B input bindings. Inspect once rather
        # than inventing a completed check or rewriting their research history.
        issues=submission_checks(project,paper_id)
        if issues:raise ResearchCtlError("Final submission checks failed: "+"; ".join(issues))
    elif binding!=submission_check_binding(project,paper_id):
        raise ResearchCtlError("Final submission inputs changed after G5; rerun the submission check")
    from scripts import researchctl,research_identity,scientific_scope,empirical_workflow,research_extensions,research_increments
    scientific_errors=researchctl.paper_scientific_errors(project,paper_id)
    for check in (
        lambda:research_identity.validate(project,paper_id,"G5"),
        lambda:scientific_scope.validate(project,"G5",paper_id),
        lambda:empirical_workflow.gate_errors(project,"G5",paper_id),
        lambda:research_extensions.gate_errors(project),
        lambda:research_increments.gate_errors(project,"G5",paper_id)):
        scientific_errors.extend(check())
    if scientific_errors:raise ResearchCtlError("Scientific integrity changed after G5: "+"; ".join(scientific_errors))
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
