#!/usr/bin/env python3
"""Import a user-downloaded SciencePro export as advisory, hash-bound evidence.

This tool never logs in, replays cookies, discovers hidden endpoints or treats a
platform-generated statement as verified scientific evidence.  It copies the
original into the Git-ignored private area and creates a small review manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
ALLOWED_SUFFIXES = {".pdf", ".docx", ".csv", ".tsv", ".bib", ".json", ".md", ".txt"}
MAX_BYTES = 512 * 1024 * 1024
DOI_RE = re.compile(r"(?i)\b10\.\d{4,9}/[-._;()/:A-Z0-9]+")
URL_RE = re.compile(r"https://[^\s<>\"']+")


class ScienceProImportError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".bib", ".json", ".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")[:5_000_000], "plain-text"
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                payload = archive.read("word/document.xml").decode("utf-8", errors="replace")
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            raise ScienceProImportError(f"cannot inspect DOCX: {exc}") from exc
        return re.sub(r"<[^>]+>", " ", payload)[:5_000_000], "docx-xml"
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            return "", "pdf-text-extraction-unavailable"
        try:
            reader = PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:500])
        except Exception as exc:
            return "", f"pdf-text-extraction-failed:{type(exc).__name__}"
        return text[:5_000_000], "pypdf"
    return "", "unsupported"


def import_export(project: Path, source: Path, actor: str) -> tuple[Path, dict[str, Any]]:
    if not project.is_dir():
        raise ScienceProImportError(f"project does not exist: {project}")
    source = source.expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise ScienceProImportError("source must be a regular local file")
    if source.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ScienceProImportError("unsupported export type")
    if source.stat().st_size > MAX_BYTES:
        raise ScienceProImportError("export exceeds the 512 MiB safety limit")
    if not actor.strip():
        raise ScienceProImportError("actor must identify who performed the export")
    digest = sha256_file(source)
    receipt_id = f"sciencepro-{digest[:16]}"
    private_dir = project / "data" / "private" / "sciencepro" / receipt_id
    private_dir.mkdir(parents=True, exist_ok=True)
    copied = private_dir / f"source{source.suffix.lower()}"
    if copied.exists() and sha256_file(copied) != digest:
        raise ScienceProImportError("existing private source hash conflicts with this export")
    if not copied.exists():
        shutil.copyfile(source, copied)
    extracted, extractor = _text(copied)
    dois = sorted({match.rstrip(".,;)").lower() for match in DOI_RE.findall(extracted)})
    urls = sorted({match.rstrip(".,;)") for match in URL_RE.findall(extracted)})[:1000]
    report = {
        "schema_version": "1.0",
        "receipt_id": receipt_id,
        "platform": "SciencePro",
        "imported_at": utc_now(),
        "imported_by": actor.strip(),
        "source": {
            "private_path": copied.relative_to(project).as_posix(),
            "original_filename": source.name,
            "size": copied.stat().st_size,
            "sha256": digest,
            "suffix": copied.suffix.lower(),
        },
        "extraction": {
            "method": extractor,
            "text_extracted": bool(extracted.strip()),
            "doi_candidates": dois,
            "https_url_candidates": urls,
        },
        "evidence_status": "advisory_requires_independent_verification",
        "required_follow_up": [
            "Verify DOI and bibliographic metadata through Crossref/OpenAlex.",
            "Verify every claim against the cited primary source and exact location.",
            "Confirm license, privacy, research-use terms and dataset provenance.",
            "Do not cite this receipt as a scientific source.",
        ],
        "human_review_required": True,
    }
    output = project / "evidence" / "sciencepro" / f"{receipt_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output.parent, delete=False
    ) as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(output)
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--actor", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", args.project):
        raise SystemExit("error: invalid project slug")
    try:
        output, report = import_export(PROJECTS_ROOT / args.project, args.source, args.actor)
    except ScienceProImportError as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(json.dumps({"receipt": str(output), "doi_candidates": len(report["extraction"]["doi_candidates"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
