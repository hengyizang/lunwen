#!/usr/bin/env python3
"""Validate and bind an applicable reporting-guideline checklist to a manuscript."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.citation_audit import manuscript_digest
    from scripts.ref_verify_adapter import canonical_manuscript
except ImportError:  # Direct execution from scripts/.
    from citation_audit import manuscript_digest  # type: ignore
    from ref_verify_adapter import canonical_manuscript  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"


class ReportingChecklistError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_input(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportingChecklistError(f"cannot read reporting checklist input: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise ReportingChecklistError("reporting checklist input must use schema_version 1.0")
    for field in ("study_design", "guideline", "guideline_version", "official_url", "reviewed_by", "reviewed_at"):
        if not str(value.get(field, "")).strip():
            raise ReportingChecklistError(f"reporting checklist input needs {field}")
    if not str(value["official_url"]).startswith("https://"):
        raise ReportingChecklistError("official_url must use HTTPS")
    items = value.get("items")
    if not isinstance(items, list) or not items:
        raise ReportingChecklistError("reporting checklist needs at least one item")
    seen: set[str] = set()
    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append(f"item {index} must be an object")
            continue
        identifier = str(item.get("item_id", "")).strip()
        status = str(item.get("status", "")).strip()
        location = str(item.get("location", "")).strip()
        rationale = str(item.get("rationale", "")).strip()
        evidence_ids = item.get("evidence_ids", [])
        if not identifier or identifier in seen:
            errors.append(f"item {index} needs a unique item_id")
        seen.add(identifier)
        if status not in {"present", "not_applicable", "open"}:
            errors.append(f"{identifier or index}: invalid status")
        if status == "present" and not location:
            errors.append(f"{identifier}: present item needs a manuscript location")
        if status == "not_applicable" and not rationale:
            errors.append(f"{identifier}: not_applicable item needs a rationale")
        if status == "open":
            errors.append(f"{identifier}: checklist item remains open")
        if not isinstance(evidence_ids, list) or any(not str(value).strip() for value in evidence_ids):
            errors.append(f"{identifier}: evidence_ids must be an array of non-empty identifiers")
        normalized.append(
            {"item_id": identifier, "status": status, "location": location,
             "evidence_ids": [str(value).strip() for value in evidence_ids], "rationale": rationale}
        )
    return {**value, "items": normalized, "validation_errors": errors}


def audit(paper: Path) -> dict[str, Any]:
    input_path = paper / "reviews" / "reporting-guideline-input.json"
    if not input_path.is_file() or input_path.is_symlink():
        raise ReportingChecklistError("reviews/reporting-guideline-input.json is required")
    value = load_input(input_path)
    manuscript = canonical_manuscript(paper)
    errors = list(value.pop("validation_errors"))
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "status": "pass" if not errors else "fail",
        "input": {"path": input_path.relative_to(paper).as_posix(), "sha256": sha256_file(input_path)},
        "manuscript": {"path": manuscript.relative_to(paper).as_posix(), "sha256": manuscript_digest(manuscript)},
        "checklist": value,
        "errors": errors,
    }


def validate_saved_report(paper: Path) -> list[str]:
    path = paper / "reviews" / "reporting-guideline.json"
    if not path.is_file():
        return ["reviews/reporting-guideline.json is required"]
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        current = audit(paper)
    except (OSError, json.JSONDecodeError, ReportingChecklistError) as exc:
        return [f"cannot validate reporting checklist: {exc}"]
    errors: list[str] = []
    if saved.get("schema_version") != "1.0" or saved.get("status") != "pass":
        errors.append("reporting checklist must be a passing schema_version 1.0 report")
    for key in ("input", "manuscript", "checklist"):
        if saved.get(key) != current.get(key):
            errors.append(f"reporting checklist is stale or altered for {key}")
    return errors


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--paper", required=True)
    args = parser.parse_args()
    paper = PROJECTS_ROOT / args.project / "papers" / args.paper
    try:
        if not paper.is_dir() or not re.fullmatch(r"P[0-9]{2}", args.paper):
            raise ReportingChecklistError("project/paper does not exist")
        report = audit(paper)
        atomic_json(paper / "reviews" / "reporting-guideline.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1
    except ReportingChecklistError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
