#!/usr/bin/env python3
"""Load reviewed, stage-scoped research methods without provider calls."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("a nonempty relative path is required")
    parts = Path(relative).parts
    if ".." in parts or any(part.startswith(".") for part in parts):
        raise ValueError("hidden or parent paths are not allowed")
    path = root / relative
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent):
        raise ValueError("symlinked method or evidence paths are not allowed")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("path escapes the declared root")
    return path


def load_catalog(root: Path = ROOT) -> dict[str, Any]:
    return json.loads((root / "config/research-methods.json").read_text(encoding="utf-8"))


def installation_errors(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        catalog = load_catalog(root)
        manifest = json.loads((root / "integrations/vendored-research-methods.json").read_text())
        lock = json.loads((root / "integrations/upstreams.lock.json").read_text())
        sources = {row["id"]: row for row in lock["sources"]}
        for source_id in catalog["source_ids"]:
            if source_id not in sources:
                errors.append(f"unregistered research-method source: {source_id}")
        paths: set[str] = set()
        for row in manifest["files"]:
            relative = row["path"]
            if relative in paths:
                errors.append(f"duplicate installed method path: {relative}")
            paths.add(relative)
            path = safe_path(root, relative)
            if not path.is_file() or sha256(path) != row["sha256"]:
                errors.append(f"missing or modified pinned method: {relative}")
            if not any(source.get("repository", "").removeprefix("https://github.com/") ==
                       row["source_repository"] and source.get("commit") == row["commit"]
                       for source in sources.values()):
                errors.append(f"method source/pin is not registered: {relative}")
        for module in catalog["modules"]:
            path = safe_path(root, module["path"])
            if not path.is_file() or sha256(path) != module["sha256"]:
                errors.append(f"missing or modified adapted method: {module['id']}")
            if not set(module["source_ids"]).issubset(sources):
                errors.append(f"unknown adapted-method source: {module['id']}")
        if not catalog.get("modules") or catalog.get("schema_version") != "1.0":
            errors.append("research-method catalog is empty or unsupported")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"invalid research-method installation: {exc}")
    return errors


def stage_context(stage: str, role: str, root: Path = ROOT) -> str:
    """Use concise local adaptations; never inject the entire third-party suite."""
    issues = installation_errors(root)
    if issues:
        raise ValueError("; ".join(issues))
    blocks = []
    for module in load_catalog(root)["modules"]:
        if stage in module["stages"]:
            text = safe_path(root, module["path"]).read_text(encoding="utf-8")
            blocks.append(f"Reviewed method {module['id']} (SHA-256 {module['sha256']}):\n{text}")
    if not blocks:
        return "(no additional methods for this stage)"
    if stage == "writing-and-review":
        criteria = (root / "config/pre-submission-criteria.json").read_text(encoding="utf-8")
        blocks.append("Required criterion IDs and questions by article type:\n" + criteria)
    boundary = {
        "planner": "Describe semantic requirements only. Do not supply final wording or write files.",
        "critic": "Assess the immutable source packet independently. Do not see another review or a preferred verdict.",
        "writer": "Independently write the required inputs. Never manufacture deterministic reports or human approvals.",
    }.get(role, "Preserve the project's model roles and human gates.")
    return boundary + "\n\n" + "\n\n".join(blocks)


def load_vendored_module(relative: str) -> Any:
    """Import only a reviewed, hash-verified helper, with no dynamic source URL."""
    manifest = json.loads((ROOT / "integrations/vendored-research-methods.json").read_text())
    rows = {row["path"]: row for row in manifest["files"]}
    if relative not in rows:
        raise ValueError("helper is not in the pinned installation manifest")
    path = safe_path(ROOT, relative)
    if sha256(path) != rows[relative]["sha256"]:
        raise ValueError(f"pinned helper hash changed: {relative}")
    name = "_dr_os_" + hashlib.sha256(relative.encode()).hexdigest()[:16]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ValueError("cannot load reviewed helper")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--stage")
    parser.add_argument("--role", choices=["planner", "writer", "critic"], default="writer")
    args = parser.parse_args()
    if args.validate:
        errors = installation_errors()
        print(json.dumps({"pass": not errors, "errors": errors}, indent=2))
        return 2 if errors else 0
    if not args.stage:
        parser.error("--stage or --validate is required")
    print(stage_context(args.stage, args.role))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
