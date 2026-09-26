#!/usr/bin/env python3
"""Verify that reviewer-response commitments are present in the current manuscript."""

from __future__ import annotations

import argparse
import csv
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
    from scripts.manuscript_language import extract_text
    from scripts.ref_verify_adapter import canonical_manuscript
except ImportError:  # Direct execution from scripts/.
    from citation_audit import manuscript_digest  # type: ignore
    from manuscript_language import extract_text  # type: ignore
    from ref_verify_adapter import canonical_manuscript  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
REQUIRED_COLUMNS = {
    "comment_id",
    "commitment_id",
    "fulfillment_status",
    "location",
    "revised_text",
    "unfulfilled_rationale",
}
STATUSES = {"fulfilled", "partial", "not_fulfilled", "rejected_with_rationale"}


class RevisionTraceError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def load_matrix(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
                missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
                raise RevisionTraceError(
                    "response matrix is missing columns: " + ", ".join(missing)
                )
            rows = [{key: str(value or "").strip() for key, value in row.items()} for row in reader]
    except OSError as exc:
        raise RevisionTraceError(f"cannot read response matrix: {exc}") from exc
    if not rows:
        raise RevisionTraceError("response matrix must contain at least one commitment")
    seen: set[str] = set()
    for index, row in enumerate(rows, 2):
        commitment = row["commitment_id"]
        if not row["comment_id"] or not commitment or commitment in seen:
            raise RevisionTraceError(f"row {index} needs unique comment_id and commitment_id")
        seen.add(commitment)
        if row["fulfillment_status"] not in STATUSES:
            raise RevisionTraceError(f"row {index} has invalid fulfillment_status")
    return rows


def audit(paper: Path) -> dict[str, Any]:
    matrix = paper / "reviews" / "response-matrix.csv"
    if not matrix.is_file() or matrix.is_symlink():
        raise RevisionTraceError("reviews/response-matrix.csv is required")
    manuscript = canonical_manuscript(paper)
    body = normalized(extract_text(manuscript))
    rows = load_matrix(matrix)
    findings: list[str] = []
    checks: list[dict[str, Any]] = []
    for row in rows:
        status = row["fulfillment_status"]
        excerpt = normalized(row["revised_text"])
        location = normalized(row["location"])
        rationale = normalized(row["unfulfilled_rationale"])
        present = bool(excerpt and excerpt in body)
        if status == "fulfilled":
            if not location:
                findings.append(f"{row['commitment_id']}: fulfilled commitment lacks location")
            if not excerpt or not present:
                findings.append(
                    f"{row['commitment_id']}: promised revised_text is absent from the manuscript"
                )
        elif status == "partial":
            if not rationale:
                findings.append(f"{row['commitment_id']}: partial commitment lacks rationale")
            if not excerpt or not present:
                findings.append(
                    f"{row['commitment_id']}: partial revised_text is absent from the manuscript"
                )
        elif not rationale:
            findings.append(f"{row['commitment_id']}: unfulfilled commitment lacks rationale")
        checks.append(
            {
                "comment_id": row["comment_id"],
                "commitment_id": row["commitment_id"],
                "fulfillment_status": status,
                "location": location,
                "revised_text_present": present,
            }
        )
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "status": "pass" if not findings else "fail",
        "manuscript": {
            "path": manuscript.relative_to(paper).as_posix(),
            "sha256": manuscript_digest(manuscript),
        },
        "response_matrix": {
            "path": matrix.relative_to(paper).as_posix(),
            "sha256": sha256_file(matrix),
            "commitment_count": len(rows),
        },
        "checks": checks,
        "errors": findings,
    }


def validate_saved_report(paper: Path) -> list[str]:
    path = paper / "reviews" / "revision-trace.json"
    if not path.is_file():
        return ["reviews/revision-trace.json is required"]
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        current = audit(paper)
    except (OSError, json.JSONDecodeError, RevisionTraceError, ValueError) as exc:
        return [f"cannot validate revision trace: {exc}"]
    errors: list[str] = []
    if saved.get("schema_version") != "1.0" or saved.get("status") != "pass":
        errors.append("revision trace must be a passing schema_version 1.0 report")
    for key in ("manuscript", "response_matrix"):
        if not isinstance(saved.get(key), dict) or saved[key].get("sha256") != current[key]["sha256"]:
            errors.append(f"revision trace is stale for {key}")
    if saved.get("checks") != current["checks"]:
        errors.append("revision trace checks differ from the current manuscript or matrix")
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
            raise RevisionTraceError("project/paper does not exist")
        report = audit(paper)
        atomic_json(paper / "reviews" / "revision-trace.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1
    except RevisionTraceError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
