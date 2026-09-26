#!/usr/bin/env python3
"""Run the pinned ref-verify engine and bind claim checks to a paper snapshot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.citation_audit import manuscript_digest, normalize_doi
except ImportError:  # Direct execution from scripts/.
    from citation_audit import manuscript_digest, normalize_doi  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
EXPECTED_VERSION = "1.2.0"
UPSTREAM_COMMIT = "8d56a6c5ed42c5332efa516f6ee5f56cbba8557d"
PAPER_RE = re.compile(r"^P[0-9]{2}$")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
ALLOWED_CLAIM_TYPES = {"topline", "numeric"}
ALLOWED_SOURCES = {"auto", "crossref", "openalex", "semantic-scholar", "pubmed"}


class RefVerifyAdapterError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_manuscript(paper: Path) -> Path:
    candidates = [
        path
        for path in (
            paper / "manuscript" / "main.tex",
            paper / "manuscript" / "main.docx",
        )
        if path.is_file() and not path.is_symlink()
    ]
    if len(candidates) != 1:
        raise RefVerifyAdapterError(
            "exactly one canonical manuscript/main.tex or manuscript/main.docx is required"
        )
    return candidates[0]


def project_paper(project: str, paper_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", project):
        raise RefVerifyAdapterError("project must be a safe 2-63 character slug")
    if not PAPER_RE.fullmatch(paper_id):
        raise RefVerifyAdapterError("paper must look like P01")
    path = PROJECTS_ROOT / project / "papers" / paper_id
    if not path.is_dir():
        raise RefVerifyAdapterError(f"paper does not exist: {project}/{paper_id}")
    return path


def safe_paper_file(paper: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise RefVerifyAdapterError("claims path must be paper-relative and cannot contain ..")
    path = (paper / value).resolve()
    if paper.resolve() not in path.parents or not path.is_file() or path.is_symlink():
        raise RefVerifyAdapterError(f"claims file is not a regular paper file: {relative}")
    return path


def load_claims(path: Path) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    identifiers: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RefVerifyAdapterError(
                f"citation claim line {line_number} is not valid JSON: {exc}"
            ) from exc
        if not isinstance(item, dict):
            raise RefVerifyAdapterError(f"citation claim line {line_number} must be an object")
        identifier = str(item.get("id", "")).strip()
        claim = str(item.get("claim", "")).strip()
        doi = normalize_doi(str(item.get("doi", "")))
        claim_type = str(item.get("claim_type", "")).strip()
        evidence_depth = str(item.get("evidence_depth", "")).strip()
        if not identifier or identifier in identifiers:
            raise RefVerifyAdapterError(
                f"citation claim line {line_number} needs a unique non-empty id"
            )
        if not DOI_RE.fullmatch(doi):
            raise RefVerifyAdapterError(f"citation claim {identifier} has an invalid DOI")
        if not claim:
            raise RefVerifyAdapterError(f"citation claim {identifier} has empty claim text")
        if claim_type not in ALLOWED_CLAIM_TYPES:
            raise RefVerifyAdapterError(
                f"citation claim {identifier} claim_type must be topline or numeric; "
                "mechanism/procedure claims require full-text verification"
            )
        if evidence_depth != "abstract":
            raise RefVerifyAdapterError(
                f"citation claim {identifier} evidence_depth must be abstract for ref-verify"
            )
        identifiers.add(identifier)
        normalized = {
            "id": identifier,
            "doi": doi,
            "claim": claim,
            "claim_type": claim_type,
            "evidence_depth": evidence_depth,
        }
        source = item.get("source")
        if source is not None:
            source_value = str(source).strip()
            if source_value not in ALLOWED_SOURCES:
                raise RefVerifyAdapterError(
                    f"citation claim {identifier} source must be one of: "
                    + ", ".join(sorted(ALLOWED_SOURCES))
                )
            normalized["source"] = source_value
        note = item.get("note")
        if note is not None:
            normalized["note"] = str(note)
        claims.append(normalized)
    if not claims:
        raise RefVerifyAdapterError("at least one DOI-bound citation claim is required")
    return claims


def find_executable() -> str | None:
    for candidate in (
        ROOT / ".venv" / "bin" / "ref-verify",
        ROOT / ".venv" / "Scripts" / "ref-verify.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ref-verify")


def installed_version() -> str | None:
    try:
        return importlib.metadata.version("ref-verify")
    except importlib.metadata.PackageNotFoundError:
        return None


def _validate_engine_payload(
    payload: dict[str, Any], claims: list[dict[str, str]]
) -> list[str]:
    errors: list[str] = []
    results = payload.get("results")
    summary = payload.get("summary")
    if not isinstance(results, list) or not isinstance(summary, dict):
        return ["ref-verify JSON must contain a results array and summary object"]
    expected = {item["id"]: item for item in claims}
    seen: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            errors.append("ref-verify returned a non-object result row")
            continue
        identifier = str(result.get("id", ""))
        if identifier not in expected or identifier in seen:
            errors.append(f"ref-verify returned an unknown or duplicate id: {identifier}")
            continue
        seen.add(identifier)
        source = expected[identifier]
        if normalize_doi(str(result.get("doi", ""))) != source["doi"]:
            errors.append(f"{identifier}: returned DOI differs from the input")
        if str(result.get("claim", "")).strip() != source["claim"]:
            errors.append(f"{identifier}: returned claim differs from the input")
        if result.get("verdict") != "ACCEPT" or result.get("status") != "SUPPORTED":
            errors.append(
                f"{identifier}: claim is not accepted ({result.get('verdict')}/"
                f"{result.get('status')})"
            )
        if not str(result.get("evidence", "")).strip():
            errors.append(f"{identifier}: accepted result has no fetched evidence excerpt")
    missing = sorted(set(expected) - seen)
    if missing:
        errors.append(f"ref-verify omitted claim ids: {', '.join(missing)}")
    if summary.get("total") != len(claims):
        errors.append("ref-verify summary total differs from the input claim count")
    if summary.get("accept") != len(claims) or summary.get("failed") not in {0, None}:
        errors.append("ref-verify summary does not show every row accepted without failure")
    return errors


def run(
    paper: Path,
    claims_path: Path,
    *,
    executable: str | None = None,
    runner: Callable[..., Any] = subprocess.run,
    timeout: int = 300,
    engine_version: str | None = None,
) -> dict[str, Any]:
    claims = load_claims(claims_path)
    command = executable or find_executable()
    version = engine_version if engine_version is not None else installed_version()
    if not command or version != EXPECTED_VERSION:
        raise RefVerifyAdapterError(
            f"ref-verify=={EXPECTED_VERSION} is required; run "
            "bash scripts/bootstrap-wsl.sh --with-reference-tools"
        )
    manuscript = canonical_manuscript(paper)
    bibliography = paper / "manuscript" / "references.bib"
    if not bibliography.is_file() or bibliography.is_symlink():
        raise RefVerifyAdapterError("manuscript/references.bib is required")

    with tempfile.TemporaryDirectory(prefix="doctoral-os-ref-verify-") as directory:
        normalized_path = Path(directory) / "claims.jsonl"
        normalized_path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in claims),
            encoding="utf-8",
        )
        try:
            completed = runner(
                [command, "check-file", str(normalized_path), "--format", "jsonl", "--json"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RefVerifyAdapterError(f"ref-verify execution failed: {exc}") from exc
    if completed.returncode not in {0, 2}:
        raise RefVerifyAdapterError(
            f"ref-verify failed with exit {completed.returncode}: "
            f"{str(completed.stderr).strip()[:500]}"
        )
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RefVerifyAdapterError("ref-verify did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise RefVerifyAdapterError("ref-verify output must be a JSON object")
    errors = _validate_engine_payload(payload, claims)
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "status": "pass" if not errors else "fail",
        "engine": {
            "name": "ref-verify",
            "version": version,
            "upstream_commit": UPSTREAM_COMMIT,
            "mode": "abstract-bound batch claim check",
        },
        "scope": {
            "accepted_claim_types": sorted(ALLOWED_CLAIM_TYPES),
            "evidence_depth": "abstract",
            "full_text_claims_supported": False,
            "note": (
                "A pass verifies explicit DOI-bound abstract support only. Mechanism, "
                "implementation, procedure, table and figure claims require full-text evidence."
            ),
        },
        "input": {
            "path": claims_path.relative_to(paper).as_posix(),
            "sha256": sha256_file(claims_path),
            "claim_count": len(claims),
        },
        "bibliography": {
            "path": bibliography.relative_to(paper).as_posix(),
            "sha256": sha256_file(bibliography),
        },
        "manuscript": {
            "path": manuscript.relative_to(paper).as_posix(),
            "sha256": manuscript_digest(manuscript),
        },
        "summary": payload.get("summary"),
        "results": payload.get("results"),
        "errors": errors,
    }


def validate_saved_report(paper: Path) -> list[str]:
    errors: list[str] = []
    report_path = paper / "reviews" / "ref-verify.json"
    if not report_path.is_file():
        return ["reviews/ref-verify.json is required"]
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read reviews/ref-verify.json: {exc}"]
    if not isinstance(report, dict) or report.get("schema_version") != "1.0":
        return ["reviews/ref-verify.json must use schema_version 1.0"]
    if report.get("status") != "pass":
        errors.append("ref-verify report must pass")
    engine = report.get("engine") if isinstance(report.get("engine"), dict) else {}
    if engine.get("name") != "ref-verify" or engine.get("version") != EXPECTED_VERSION:
        errors.append(f"ref-verify report must use ref-verify=={EXPECTED_VERSION}")
    if engine.get("upstream_commit") != UPSTREAM_COMMIT:
        errors.append("ref-verify report uses an unreviewed upstream commit")
    input_record = report.get("input") if isinstance(report.get("input"), dict) else {}
    try:
        claims_path = safe_paper_file(paper, str(input_record.get("path", "")))
        claims = load_claims(claims_path)
        if input_record.get("sha256") != sha256_file(claims_path):
            errors.append("ref-verify report is stale for its citation-claim input")
        if input_record.get("claim_count") != len(claims):
            errors.append("ref-verify claim_count is stale")
    except RefVerifyAdapterError as exc:
        errors.append(str(exc))
        claims = []
    bibliography = paper / "manuscript" / "references.bib"
    bibliography_record = (
        report.get("bibliography")
        if isinstance(report.get("bibliography"), dict)
        else {}
    )
    if not bibliography.is_file() or bibliography_record.get("sha256") != sha256_file(bibliography):
        errors.append("ref-verify report is stale for manuscript/references.bib")
    try:
        manuscript = canonical_manuscript(paper)
        manuscript_record = (
            report.get("manuscript")
            if isinstance(report.get("manuscript"), dict)
            else {}
        )
        if manuscript_record.get("sha256") != manuscript_digest(manuscript):
            errors.append("ref-verify report is stale for the manuscript source tree")
    except RefVerifyAdapterError as exc:
        errors.append(str(exc))
    if claims:
        errors.extend(_validate_engine_payload(report, claims))
    return errors


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--paper", required=True)
    parser.add_argument("--claims", default="reviews/citation-claims.jsonl")
    parser.add_argument("--output", default="reviews/ref-verify.json")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    try:
        paper = project_paper(args.project, args.paper)
        claims_path = safe_paper_file(paper, args.claims)
        output = (paper / args.output).resolve()
        if paper.resolve() not in output.parents or output.suffix.lower() != ".json":
            raise RefVerifyAdapterError("output must be a paper-relative JSON path")
        report = run(paper, claims_path, timeout=args.timeout)
        atomic_write(output, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1
    except RefVerifyAdapterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
