#!/usr/bin/env python3
"""Track which model family last wrote a project artifact.

The registry is control-plane metadata under ``state/``. Models are not allowed
to edit it. A current Anthropic record blocks a file from a submission package;
human or deterministic local edits invalidate the old hash rather than being
mislabelled as model output.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "1.0"
REGISTRY_RELATIVE = Path("state/output-provenance.json")
SNAPSHOT_EXCLUDED_ROOTS = {"api_runs", "state"}
SNAPSHOT_EXCLUDED_PARTS = {
    ".git",
    "build",
    "cache",
    "credentials",
    "private",
    "raw",
    "secrets",
    "submission",
    "venue-template",
}


class ProvenanceError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError as exc:
        raise ProvenanceError(f"Artifact escapes project directory: {path}") from exc


def _load(project: Path) -> dict[str, Any]:
    path = project / REGISTRY_RELATIVE
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "files": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"Invalid output provenance registry: {exc}") from exc
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != SCHEMA_VERSION
        or not isinstance(value.get("files"), dict)
    ):
        raise ProvenanceError("Unsupported output provenance registry")
    return value


def _write(project: Path, value: dict[str, Any]) -> None:
    path = project / REGISTRY_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def record_model_writes(
    project: Path,
    paths: Iterable[Path],
    *,
    family: str,
    provider: str,
    model: str,
    role: str,
    run_id: str,
) -> list[str]:
    """Record non-empty files written by a model-controlled authoring step."""

    if family not in {"anthropic", "openai", "other"}:
        raise ProvenanceError(f"Unsupported model family: {family}")
    registry = _load(project)
    records = registry["files"]
    written: list[str] = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            continue
        relative = _relative(project, path)
        if relative == REGISTRY_RELATIVE.as_posix():
            raise ProvenanceError("A model cannot record itself as provenance authority")
        records[relative] = {
            "sha256": sha256_file(path),
            "family": family,
            "provider": provider,
            "model": model,
            "role": role,
            "run_id": run_id,
            "recorded_at": utc_now(),
        }
        written.append(relative)
    registry["updated_at"] = utc_now()
    _write(project, registry)
    return sorted(written)


def current_origin(project: Path, path: Path) -> dict[str, Any]:
    """Return the current tracked origin without guessing untracked authorship."""

    relative = _relative(project, path)
    record = _load(project)["files"].get(relative)
    if not isinstance(record, dict):
        return {"status": "untracked", "path": relative}
    if not path.is_file():
        return {"status": "missing", "path": relative}
    if record.get("sha256") != sha256_file(path):
        return {
            "status": "modified_after_record",
            "path": relative,
            "previous_family": record.get("family"),
            "previous_provider": record.get("provider"),
        }
    return {"status": "tracked", "path": relative, **record}


def reject_current_anthropic_outputs(project: Path, paths: Iterable[Path]) -> None:
    blocked: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        origin = current_origin(project, path)
        if origin.get("status") == "tracked" and origin.get("family") == "anthropic":
            blocked.append(origin["path"])
    if blocked:
        raise ProvenanceError(
            "Refusing Claude/Anthropic-authored final output: " + ", ".join(sorted(blocked))
        )


def require_final_origins(project: Path, paths: Iterable[Path]) -> None:
    """Require a current, explicitly non-Anthropic origin for final files."""

    blocked: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        origin = current_origin(project, path)
        if origin.get("status") != "tracked":
            blocked.append(f"{origin['path']} ({origin['status']})")
        elif origin.get("family") == "anthropic":
            blocked.append(f"{origin['path']} (anthropic)")
    if blocked:
        raise ProvenanceError(
            "Final files need current Codex/local/human provenance: "
            + ", ".join(sorted(blocked))
        )


def provenance_report(project: Path, paths: Iterable[Path]) -> list[dict[str, Any]]:
    return [current_origin(project, path) for path in sorted(paths)]


def artifact_snapshot(project: Path) -> dict[str, str]:
    """Hash model-writeable project files before a CLI authoring step."""

    snapshot: dict[str, str] = {}
    if not project.is_dir():
        return snapshot
    for path in sorted(project.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(project)
        if not relative.parts or relative.parts[0].lower() in SNAPSHOT_EXCLUDED_ROOTS:
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        if any(part.lower() in SNAPSHOT_EXCLUDED_PARTS for part in relative.parts):
            continue
        snapshot[relative.as_posix()] = sha256_file(path)
    return snapshot


def changed_files(project: Path, before: dict[str, str]) -> list[Path]:
    after = artifact_snapshot(project)
    return [
        project / relative
        for relative, digest in after.items()
        if before.get(relative) != digest
    ]


def attest_human_files(
    project: Path, paths: Iterable[Path], *, actor: str, note: str
) -> list[str]:
    """Record a human's explicit non-Claude authorship/review attestation."""

    if not actor.strip() or not note.strip():
        raise ProvenanceError("Human attestation requires a named actor and an explanatory note")
    resolved: list[Path] = []
    for path in paths:
        candidate = path if path.is_absolute() else project / path
        _relative(project, candidate)
        if not candidate.is_file() or candidate.is_symlink():
            raise ProvenanceError(f"Attestation target must be a real file: {candidate}")
        resolved.append(candidate)
    return record_model_writes(
        project,
        resolved,
        family="other",
        provider="human-attestation",
        model=actor.strip(),
        role=f"human-reviewed: {note.strip()}",
        run_id="human-" + re.sub(r"[^0-9A-Za-z._-]", "-", utc_now()),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    attest = subcommands.add_parser("attest")
    attest.add_argument("--project", required=True)
    attest.add_argument("--actor", required=True)
    attest.add_argument("--note", required=True)
    attest.add_argument("--path", action="append", required=True, dest="paths")
    args = parser.parse_args()
    try:
        repo = Path(__file__).resolve().parents[1]
        project = repo / "projects" / args.project
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", args.project) or not project.is_dir():
            raise ProvenanceError("Unknown or invalid project")
        written = attest_human_files(
            project, (Path(value) for value in args.paths), actor=args.actor, note=args.note
        )
        print(json.dumps({"attested": written}, ensure_ascii=False, indent=2))
        return 0
    except ProvenanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
