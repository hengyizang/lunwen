"""Small deterministic artifact helpers. No model calls or experiment execution."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def path_in(project: Path, relative: str, *, exists: bool = True) -> Path:
    candidate = Path(relative)
    if not relative or candidate.is_absolute() or ".." in candidate.parts or "\\" in relative or ":" in relative:
        raise ValueError("artifact needs a project-relative path")
    target = project / candidate
    if any(p.is_symlink() for p in (target, *target.parents)) or not target.resolve().is_relative_to(project.resolve()):
        raise ValueError("symlink or escaped artifact is forbidden")
    if exists and not target.is_file():
        raise ValueError(f"artifact is missing: {relative}")
    return target


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("artifact must be a JSON object")
    return value


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, path)


def record(project: Path, paths: list[Path], module: str) -> None:
    from scripts.output_provenance import record_model_writes
    record_model_writes(project, paths, family="other", provider="deterministic-control-plane",
                        model=module, role="artifact-builder", run_id="quality-refresh")


def bound_source(project: Path, value: dict) -> dict:
    target = path_in(project, value["path"])
    actual = sha(target)
    if value.get("sha256") != actual or not str(value.get("locator", "")).strip():
        raise ValueError("source needs its current hash and a page/section/record locator")
    return {"path": value["path"], "sha256": actual, "locator": value["locator"]}
