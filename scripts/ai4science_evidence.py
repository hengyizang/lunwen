#!/usr/bin/env python3
"""Hash-bind outputs from reviewed optional AI4Science tools.

This adapter deliberately does not make an AI-generated answer authoritative.
It records the installed package version and exact local input/output files so
the result can be audited and then checked by a human against primary sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
PACKAGES = {
    "tooluniverse": "tooluniverse",
    "paperqa2": "paper-qa",
    "kdense-scientific-agent-skills": "scientific-agent-skills",
}


class AI4ScienceEvidenceError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_path(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", slug):
        raise AI4ScienceEvidenceError("invalid project slug")
    project = PROJECTS_ROOT / slug
    if not project.is_dir():
        raise AI4ScienceEvidenceError(f"project does not exist: {slug}")
    return project


def safe_file(project: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise AI4ScienceEvidenceError("files must be project-relative and cannot contain ..")
    path = (project / relative).resolve()
    if project.resolve() not in path.parents or not path.is_file() or path.is_symlink():
        raise AI4ScienceEvidenceError(f"not a regular project file: {value}")
    return path


def file_record(project: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(project).as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def append(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def record(
    project: Path,
    tool: str,
    output: str,
    inputs: list[str],
    actor: str,
    purpose: str,
) -> dict[str, Any]:
    if tool not in PACKAGES:
        raise AI4ScienceEvidenceError("unsupported tool")
    if not actor.strip() or not purpose.strip():
        raise AI4ScienceEvidenceError("actor and purpose are required")
    package = PACKAGES[tool]
    try:
        version = metadata.version(package)
    except metadata.PackageNotFoundError as exc:
        raise AI4ScienceEvidenceError(
            f"{package} is not installed in this environment; no receipt was created"
        ) from exc
    output_path = safe_file(project, output)
    input_paths = [safe_file(project, value) for value in inputs]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    receipt = {
        "schema_version": "1.0",
        "receipt_id": f"{timestamp}-{tool}-{uuid.uuid4().hex[:10]}",
        "tool": tool,
        "package": package,
        "package_version": version,
        "recorded_at": now(),
        "recorded_by": actor.strip(),
        "purpose": purpose.strip(),
        "output": file_record(project, output_path),
        "inputs": [file_record(project, path) for path in input_paths],
        "advisory_only": True,
        "human_verification_required": True,
    }
    append(project / "evidence" / "ai4science-ledger.jsonl", receipt)
    return receipt


def read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    result: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AI4ScienceEvidenceError(f"invalid ledger JSON at line {number}: {exc}") from exc
        if not isinstance(value, dict):
            raise AI4ScienceEvidenceError(f"ledger line {number} is not an object")
        result.append(value)
    return result


def validate(project: Path, values: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        prefix = f"ai4science-ledger[{index}]"
        receipt_id = item.get("receipt_id")
        if not isinstance(receipt_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]+", receipt_id):
            errors.append(f"{prefix}.receipt_id is invalid")
        elif receipt_id in seen:
            errors.append(f"{prefix}.receipt_id is duplicated")
        else:
            seen.add(receipt_id)
        tool = item.get("tool")
        if tool not in PACKAGES or item.get("package") != PACKAGES.get(tool):
            errors.append(f"{prefix} tool/package is unsupported")
        if item.get("advisory_only") is not True or item.get("human_verification_required") is not True:
            errors.append(f"{prefix} must remain advisory and require human verification")
        for label, records in (("output", [item.get("output")]), ("inputs", item.get("inputs"))):
            if not isinstance(records, list):
                errors.append(f"{prefix}.{label} must contain file evidence")
                continue
            for file_index, file_value in enumerate(records):
                if not isinstance(file_value, dict):
                    errors.append(f"{prefix}.{label}[{file_index}] is invalid")
                    continue
                try:
                    path = safe_file(project, str(file_value.get("path")))
                except AI4ScienceEvidenceError as exc:
                    errors.append(f"{prefix}.{label}[{file_index}]: {exc}")
                    continue
                if file_value.get("sha256") != sha256_file(path) or file_value.get("bytes") != path.stat().st_size:
                    errors.append(f"{prefix}.{label}[{file_index}] is stale")
    return errors


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    item = sub.add_parser("record")
    item.add_argument("--project", required=True)
    item.add_argument("--tool", required=True, choices=sorted(PACKAGES))
    item.add_argument("--output", required=True)
    item.add_argument("--input", action="append", default=[])
    item.add_argument("--actor", required=True)
    item.add_argument("--purpose", required=True)
    check = sub.add_parser("validate")
    check.add_argument("--project", required=True)
    return root


def main(argv: Iterable[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        project = project_path(args.project)
        if args.command == "record":
            print(json.dumps(record(project, args.tool, args.output, args.input, args.actor, args.purpose), indent=2))
        else:
            errors = validate(project, read_ledger(project / "evidence" / "ai4science-ledger.jsonl"))
            print(json.dumps({"status": "pass" if not errors else "block", "errors": errors}, indent=2))
            if errors:
                raise AI4ScienceEvidenceError(f"{len(errors)} invalid receipt(s)")
        return 0
    except AI4ScienceEvidenceError as exc:
        print(f"error: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
