#!/usr/bin/env python3
"""Detect unapproved numeric, citation and claim-strength drift between revisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.citation_audit import manuscript_digest, tex_source_paths
    from scripts.manuscript_language import extract_text
    from scripts.ref_verify_adapter import canonical_manuscript
except ImportError:  # Direct execution from scripts/.
    from citation_audit import manuscript_digest, tex_source_paths  # type: ignore
    from manuscript_language import extract_text  # type: ignore
    from ref_verify_adapter import canonical_manuscript  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?%?")
SIGNAL_RE = re.compile(
    r"\b(?:may|might|could|suggests?|indicates?|associated|correlat(?:e|es|ed|ion)|"
    r"causes?|caused|drives?|demonstrates?|proves?|establishes?|confirms?)\b",
    re.I,
)


class RevisionIntegrityError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def multiset_delta(before: list[str], after: list[str]) -> dict[str, list[str]]:
    left, right = Counter(before), Counter(after)
    return {
        "removed": sorted((left - right).elements()),
        "added": sorted((right - left).elements()),
    }


def citation_tokens(path: Path) -> list[str]:
    if path.suffix.lower() != ".tex":
        return []
    values: list[str] = []
    for source in sorted(tex_source_paths(path)):
        text = re.sub(r"(?m)(?<!\\)%.*$", "", source.read_text(encoding="utf-8"))
        for match in re.finditer(
            r"\\(?:cite|citep|citet|parencite|textcite|autocite)\*?(?:\[[^]]*\])*\{([^}]*)\}",
            text,
        ):
            values.extend(key.strip() for key in match.group(1).split(",") if key.strip())
    return values


def tokens(path: Path) -> dict[str, list[str]]:
    text = extract_text(path)
    return {
        "numeric": NUMBER_RE.findall(text),
        "citation": citation_tokens(path),
        "claim_language": [match.group(0).casefold() for match in SIGNAL_RE.finditer(text)],
    }


def load_authorization(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RevisionIntegrityError(f"cannot read revision authorization: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise RevisionIntegrityError("revision authorization must use schema_version 1.0")
    if not str(value.get("approved_by", "")).strip() or not str(value.get("approved_at", "")).strip():
        raise RevisionIntegrityError("revision authorization needs approved_by and approved_at")
    return value


def audit(paper: Path) -> dict[str, Any]:
    current = canonical_manuscript(paper)
    preferred = paper / "reviews" / "revision-base" / current.name
    legacy = paper / "reviews" / f"revision-base{current.suffix.lower()}"
    base = preferred if preferred.is_file() else legacy
    if not base.is_file() or base.is_symlink():
        raise RevisionIntegrityError(f"reviews/revision-base/{current.name} is required")
    auth_path = paper / "reviews" / "revision-authorizations.json"
    authorization = load_authorization(auth_path if auth_path.is_file() else None)
    before, after = tokens(base), tokens(current)
    changes = {
        key + "_changes": multiset_delta(before[key], after[key])
        for key in ("numeric", "citation", "claim_language")
    }
    has_changes = any(value[side] for value in changes.values() for side in ("removed", "added"))
    errors: list[str] = []
    if has_changes and authorization is None:
        errors.append("protected revision changes require named human authorization")
    if authorization is not None:
        for key, actual in changes.items():
            expected = authorization.get(key, {"removed": [], "added": []})
            if not isinstance(expected, dict) or actual != {
                "removed": sorted(str(item) for item in expected.get("removed", [])),
                "added": sorted(str(item) for item in expected.get("added", [])),
            }:
                errors.append(f"{key} do not match the exact authorized multiset")
        if changes["claim_language_changes"] != {"removed": [], "added": []} and not str(
            authorization.get("claim_language_rationale", "")
        ).strip():
            errors.append("claim-language changes require an authorization rationale")
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "status": "pass" if not errors else "fail",
        "base": {"path": base.relative_to(paper).as_posix(), "sha256": manuscript_digest(base)},
        "current": {"path": current.relative_to(paper).as_posix(), "sha256": manuscript_digest(current)},
        "authorization": (
            {"path": auth_path.relative_to(paper).as_posix(), "sha256": sha256_file(auth_path),
             "approved_by": authorization["approved_by"], "approved_at": authorization["approved_at"]}
            if authorization is not None else None
        ),
        "changes": changes,
        "errors": errors,
    }


def validate_saved_report(paper: Path) -> list[str]:
    path = paper / "reviews" / "revision-integrity.json"
    if not path.is_file():
        return ["reviews/revision-integrity.json is required"]
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        current = audit(paper)
    except (OSError, json.JSONDecodeError, RevisionIntegrityError, ValueError) as exc:
        return [f"cannot validate revision integrity: {exc}"]
    errors: list[str] = []
    if saved.get("schema_version") != "1.0" or saved.get("status") != "pass":
        errors.append("revision integrity must be a passing schema_version 1.0 report")
    for key in ("base", "current", "authorization"):
        if saved.get(key) != current.get(key):
            errors.append(f"revision integrity is stale for {key}")
    if saved.get("changes") != current.get("changes"):
        errors.append("revision integrity changes differ from a clean rerun")
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
            raise RevisionIntegrityError("project/paper does not exist")
        report = audit(paper)
        atomic_json(paper / "reviews" / "revision-integrity.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1
    except RevisionIntegrityError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
