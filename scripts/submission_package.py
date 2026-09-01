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


def safe_file(path: Path, paper: Path) -> None:
    if path.is_symlink():
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
            if candidate.name == "figure-provenance.json":
                continue
            if candidate.is_file():
                files.append(candidate)
    return sorted(files, key=lambda item: item.relative_to(paper).as_posix())


def select_files(paper: Path) -> list[Path]:
    manuscript = paper / "manuscript"
    sources = [path for path in (manuscript / "main.tex", manuscript / "main.docx") if path.is_file()]
    if len(sources) != 1:
        raise ResearchCtlError("Exactly one manuscript/main.tex or manuscript/main.docx is required.")

    selected = list(sources)
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
    text = f"""# Manual submission checklist — {project}/{paper_id}

This archive was prepared locally. It has **not** been submitted anywhere.

- [ ] Open and visually inspect the final PDF/DOCX.
- [ ] Confirm title, authors, affiliations, corresponding author and ORCID values.
- [ ] Confirm author order and obtain every co-author's approval.
- [ ] Recheck journal scope, article type, current JCR status, fees and deadlines.
- [ ] Recheck word limits, figure/table limits and required separate upload files.
- [ ] Verify ethics, consent, funding, conflicts, AI-use and data/code statements.
- [ ] Verify every citation and DOI; resolve all editorial placeholders.
- [ ] Match portal metadata to the manuscript exactly.
- [ ] Upload files manually and preview the portal-generated proof.
- [ ] Save the portal receipt and submitted version outside this archive.

Do not upload `SUBMISSION-MANIFEST.json` or this checklist unless the journal requests them.
"""
    return text.encode("utf-8")


def build_package(slug: str, paper_id: str, output: Path | None = None) -> Path:
    paper_id = validate_paper_id(paper_id)
    state = load_state(slug)
    if state.get("paper_statuses", {}).get(paper_id) != "submission_ready":
        raise ResearchCtlError(f"{paper_id} has not passed its G5 human gate.")
    paper = project_dir(slug) / "papers" / paper_id
    if not paper.is_dir():
        raise ResearchCtlError(f"Missing paper directory: {paper}")

    project = paper.parent.parent
    approval=next((item for item in reversed(state.get("approvals",[])) if item.get("gate")=="G5" and item.get("paper_id")==paper_id),None)
    if not approval or approval.get("paper_artifact_sha256")!=paper_artifact_hash(slug,paper_id):
        raise ResearchCtlError("Paper changed after G5 approval or approval predates the per-paper hash; re-run G5 review and approval")
    try:
        try:from scripts.jcr_verify import verify as verify_jcr_payload
        except ModuleNotFoundError:from jcr_verify import verify as verify_jcr_payload
        verify_jcr_payload(load_object(paper/"jcr-verification.json"))
    except Exception as exc:
        raise ResearchCtlError(f"Current JCR Q1 verification failed: {exc}") from exc
    try:
        try:from scripts.manuscript_language import analyze_submission
        except ModuleNotFoundError:from manuscript_language import analyze_submission
        language=analyze_submission(paper)
        if language.get("status")!="pass":raise ResearchCtlError("English submission validation failed: "+"; ".join(language.get("errors",[])))
        try:from scripts.figure_provenance import validate_figure_provenance
        except ModuleNotFoundError:from figure_provenance import validate_figure_provenance
        figure_errors=validate_figure_provenance(project,paper)
        if figure_errors:raise ResearchCtlError("Figure provenance failed: "+"; ".join(figure_errors))
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
