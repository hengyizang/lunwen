#!/usr/bin/env python3
"""Distinguish implemented code, tested capability and real research completion."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "config/requirements-traceability.json"
ACCEPTANCE = {"ci-required", "live-network-required", "credentials-required", "human-review-required",
              "research-not-yet-executed", "optional-not-enabled", "blocked-unmetered", "verified"}


def evidence_path(relative: str) -> Path:
    if not isinstance(relative, str) or "\\" in relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("evidence must name a repository-relative path")
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError(f"missing evidence file: {relative}")
    return path


def validate(path: Path = MATRIX) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [str(exc)]
    if not isinstance(value, dict) or value.get("schema_version") != "2.0" or value.get("execution_mode") != "cloud_only":
        return ["requirements trace must be schema 2.0 for cloud_only execution"]
    rows = value.get("requirements")
    if not isinstance(rows, list) or not rows:
        return ["requirements are missing"]
    errors, ids = [], set()
    for row in rows:
        if not isinstance(row, dict):
            errors.append("requirement row must be an object")
            continue
        identifier = row.get("id", "")
        if not isinstance(identifier, str) or not identifier.startswith("R") or identifier in ids:
            errors.append("duplicate or invalid requirement ID")
        ids.add(str(identifier))
        if row.get("implementation") not in {"implemented", "partial", "not-started", "optional"}:
            errors.append(f"{identifier}: invalid implementation status")
        if row.get("acceptance") not in ACCEPTANCE or not row.get("remaining"):
            errors.append(f"{identifier}: acceptance and an explicit remaining condition are required")
        evidence, tests = row.get("evidence"), row.get("tests")
        if not isinstance(evidence, list) or not evidence or not isinstance(tests, list):
            errors.append(f"{identifier}: implementation evidence and test bindings are required")
            continue
        if row.get("implementation") == "implemented" and not tests:
            errors.append(f"{identifier}: implemented capability needs a regression/acceptance test binding")
        try:
            for relative in evidence + tests:
                evidence_path(relative)
            if row.get("acceptance") == "verified":
                receipt = row.get("verification", {})
                proof = evidence_path(receipt.get("path", ""))
                if hashlib.sha256(proof.read_bytes()).hexdigest() != receipt.get("sha256"):
                    raise ValueError("verification receipt hash changed")
                report = json.loads(proof.read_text(encoding="utf-8"))
                if (report.get("status") != "passed" or identifier not in report.get("requirement_ids", [])
                        or not report.get("source_commit") or not report.get("workflow_run_url")):
                    raise ValueError("verified requires a passing scoped receipt bound to a code commit and workflow run")
        except (ValueError, TypeError, OSError) as exc:
            errors.append(f"{identifier}: {exc}")
    return errors


def main() -> int:
    errors = validate()
    value = json.loads(MATRIX.read_text(encoding="utf-8"))
    print(json.dumps({"requirements": len(value["requirements"]), "matrix_valid": not errors,
                      "all_requirements_fulfilled": all(r["acceptance"] == "verified" for r in value["requirements"]),
                      "errors": errors, "pending": [{"id": r["id"], "status": r["acceptance"], "remaining": r["remaining"]}
                                                     for r in value["requirements"] if r["acceptance"] != "verified"]}, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
