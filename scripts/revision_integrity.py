#!/usr/bin/env python3
"""Detect unapproved numeric, citation and claim-strength drift between revisions."""

from __future__ import annotations

import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError

try:
    from scripts.research_artifacts import write as atomic_json, paper_audit_cli, utc_now as now, sha as sha256_file, changed_fields
    from scripts.citation_audit import manuscript_digest, tex_source_paths
    from scripts.manuscript_language import extract_text
    from scripts.ref_verify_adapter import canonical_manuscript
    from scripts.scientific_editing import docx_citations, context_changes, character_audit, scientific_text, formula_tokens, WordSource
except ImportError:  # Direct execution from scripts/.
    from research_artifacts import write as atomic_json, paper_audit_cli, utc_now as now, sha as sha256_file, changed_fields
    from citation_audit import manuscript_digest, tex_source_paths  # type: ignore
    from manuscript_language import extract_text  # type: ignore
    from ref_verify_adapter import canonical_manuscript  # type: ignore
    from scientific_editing import docx_citations, context_changes, character_audit, scientific_text, formula_tokens, WordSource  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROJECTS_ROOT = ROOT / "projects"
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?%?")
SIGNAL_RE = re.compile(
    r"\b(?:may|might|could|suggests?|indicates?|associated|correlat(?:e|es|ed|ion)|"
    r"causes?|caused|drives?|demonstrates?|proves?|establishes?|confirms?)\b",
    re.I,
)


class RevisionIntegrityError(RuntimeError):
    pass


def multiset_delta(before: list[str], after: list[str]) -> dict[str, list[str]]:
    left, right = Counter(before), Counter(after)
    return {
        "removed": sorted((left - right).elements()),
        "added": sorted((right - left).elements()),
    }


def citation_tokens(path: Path, *, document=None) -> list[str]:
    if path.suffix.lower() == ".docx":
        return docx_citations(path, document=document)
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


def _facts(path: Path, *, documents=None):
    document = None
    if path.suffix.lower() == ".docx":
        try:
            document = WordSource(path, complete=documents is not None)
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            raise ValueError(f"cannot read DOCX manuscript: {exc}") from exc
        except ParseError as exc:
            raise ValueError(f"invalid DOCX document XML: {exc}") from exc
        if documents is not None:
            documents[path.resolve()] = document
    text = scientific_text(path, document=document)
    return {
        "numeric": NUMBER_RE.findall(text),
        "citation": citation_tokens(path, document=document),
        "claim_language": [match.group(0).casefold() for match in SIGNAL_RE.finditer(text)],
        "formula": formula_tokens(path, document=document),
    }, text


def tokens(path: Path) -> dict[str, list[str]]:
    return _facts(path)[0]


def load_authorization(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RevisionIntegrityError(f"cannot read revision authorization: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") not in {"1.0", "1.1"}:
        raise RevisionIntegrityError("revision authorization must use schema_version 1.0")
    if value.get("schema_version") == "1.1":
        from scripts.output_provenance import current_origin
        project = path.parents[3]
        origin = current_origin(project, path)
        if (value.get("decision_kind") != "automated_change_record" or origin.get("status") != "tracked"
                or origin.get("provider") != "deterministic-control-plane" or origin.get("model") != "scripts/revision_integrity.py"):
            raise RevisionIntegrityError("automatic change record lacks controller provenance")
        return value
    if not str(value.get("approved_by", "")).strip() or not str(value.get("approved_at", "")).strip():
        raise RevisionIntegrityError("revision authorization needs approved_by and approved_at")
    return value


def revision_authorization(paper: Path):
    path = paper / "reviews/revision-authorizations.json"
    value = load_authorization(path if path.is_file() else None)
    binding = ({"path": path.relative_to(paper).as_posix(), "sha256": sha256_file(path),
                "approved_by": value.get("approved_by"), "approved_at": value.get("approved_at"),
                "decision_kind": value.get("decision_kind", "human")} if value is not None else None)
    return value, binding


def audit(paper: Path, *, include_ledger: bool = True) -> dict[str, Any]:
    current = canonical_manuscript(paper)
    preferred = paper / "reviews" / "revision-base" / current.name
    legacy = paper / "reviews" / f"revision-base{current.suffix.lower()}"
    base = preferred if preferred.is_file() else legacy
    if not base.is_file() or base.is_symlink():
        raise RevisionIntegrityError(f"reviews/revision-base/{current.name} is required")
    authorization, auth_binding = revision_authorization(paper)
    use_ledger = include_ledger and any((paper / "reviews" / name).exists() for name in ("revision-ledger.json", "revision-ledger-report.json"))
    documents = {} if use_ledger else None
    (before, base_text), (after, current_text) = _facts(base, documents=documents), _facts(current, documents=documents)
    digests = {path: manuscript_digest(path) for path in (base, current)}
    changes = {
        key + "_changes": multiset_delta(before[key], after[key])
        for key in ("numeric", "citation", "claim_language", "formula")
    }
    changes["scientific_context_changes"] = context_changes(base_text, current_text)
    has_changes = any(value[side] for value in changes.values() for side in ("removed", "added"))
    errors: list[str] = []
    if has_changes and authorization is None:
        errors.append("protected revision changes need a current source-bound change record and independent review")
    if authorization is not None:
        if authorization.get("schema_version") == "1.1" and (authorization.get("base_sha256") != digests[base]
                or authorization.get("current_sha256") != digests[current]):
            errors.append("automatic change record is stale")
        if authorization.get("schema_version") == "1.1" and authorization.get("revision_ledger_input_sha256") != sha256_file(paper / "reviews/revision-ledger.json"):
            errors.append("automatic change record is stale for the source-bound ledger")
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
        if changes["scientific_context_changes"] != {"removed": [], "added": []} and not str(
            authorization.get("scientific_context_rationale") or authorization.get("claim_language_rationale") or ""
        ).strip():
            errors.append("scientific-context changes require an authorization rationale")
        if changes["formula_changes"] != {"removed": [], "added": []} and not str(
            authorization.get("formula_rationale") or authorization.get("scientific_context_rationale") or authorization.get("claim_language_rationale") or ""
        ).strip():
            errors.append("formula changes require an authorization rationale")
    ledger_binding = None
    if use_ledger:
        try:
            from scripts.revision_ledger import validate_saved_report as ledger_errors
            errors.extend("revision ledger: " + error for error in ledger_errors(paper.parent.parent, paper.name, _documents=documents))
            ledger_path = paper / "reviews/revision-ledger-report.json"
            ledger_binding = {"path": ledger_path.relative_to(paper).as_posix(), "sha256": sha256_file(ledger_path)} if ledger_path.is_file() else None
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"revision ledger: {exc}")
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "status": "pass" if not errors else "fail",
        "base": {"path": base.relative_to(paper).as_posix(), "sha256": digests[base]},
        "current": {"path": current.relative_to(paper).as_posix(), "sha256": digests[current]},
        "authorization": auth_binding,
        "changes": changes,
        "errors": errors,
        "semantic_equivalence_proven": False,
        "human_scientific_review_required": False,
        "independent_scientific_review_required": True,
        "character_findings": character_audit(current_text if current.suffix.lower() == ".docx" else extract_text(current)),
        **({"revision_ledger": ledger_binding} if ledger_binding is not None else {}),
    }


def record_automated_changes(paper: Path) -> dict:
    """Record exact justified deltas; existing independent critics decide validity."""
    from scripts import revision_ledger
    from scripts.research_artifacts import record
    project = paper.parent.parent
    ledger_errors = revision_ledger.validate_saved_report(project, paper.name)
    if ledger_errors:
        raise RevisionIntegrityError("source-bound revision ledger required: " + "; ".join(ledger_errors))
    current = canonical_manuscript(paper)
    base = paper / "reviews/revision-base" / current.name
    if not base.is_file():
        raise RevisionIntegrityError("canonical revision baseline is required")
    facts = audit(paper, include_ledger=False)
    reason = "Exact changes and source-bound author reasons are recorded in the current revision ledger; independent scientific audits remain required."
    value = {"schema_version": "1.1", "decision_kind": "automated_change_record", "recorded_at": now(),
             "base_sha256": facts["base"]["sha256"], "current_sha256": facts["current"]["sha256"],
             "revision_ledger_input_sha256": sha256_file(paper / "reviews/revision-ledger.json"),
             "claim_language_rationale": reason, "scientific_context_rationale": reason, "formula_rationale": reason,
             "human_review": False, "scientific_validity_verified": False, **facts["changes"]}
    destination = paper / "reviews/revision-authorizations.json"
    if destination.exists():
        old = load_authorization(destination)
        if old and old.get("decision_kind") != "automated_change_record":
            archive = project / "state/revision-control-history" / paper.name / (sha256_file(destination) + ".json")
            if not archive.exists():
                atomic_json(archive, old)
                record(project, [archive], "scripts/revision_integrity.py")
        if old and {k:v for k,v in old.items() if k!="recorded_at"} == {k:v for k,v in value.items() if k!="recorded_at"}:
            return old
    atomic_json(destination, value)
    record(project, [destination], "scripts/revision_integrity.py")
    revision_ledger.refresh(project, paper.name)
    return value


def validate_saved_report(paper: Path, *, include_ledger: bool = True) -> list[str]:
    path = paper / "reviews" / "revision-integrity.json"
    if not path.is_file():
        return ["reviews/revision-integrity.json is required"]
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        current = audit(paper, include_ledger=include_ledger)
    except (OSError, json.JSONDecodeError, RevisionIntegrityError, ValueError) as exc:
        return [f"cannot validate revision integrity: {exc}"]
    errors: list[str] = []
    if saved.get("schema_version") != "1.0" or (include_ledger and saved.get("status") != "pass"):
        errors.append("revision integrity must be a passing schema_version 1.0 report")
    errors.extend(f"revision integrity is stale for {key}" for key in changed_fields(
        saved, current, ("base", "current", "authorization", *(("revision_ledger",) if include_ledger else ()))))
    if saved.get("changes") != current.get("changes"):
        errors.append("revision integrity changes differ from a clean rerun")
    errors.extend(current["errors"])
    return errors


def main() -> int:
    return paper_audit_cli(__doc__, PROJECTS_ROOT, audit, "revision-integrity.json", RevisionIntegrityError)


if __name__ == "__main__":
    raise SystemExit(main())
