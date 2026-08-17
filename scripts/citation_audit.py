#!/usr/bin/env python3
"""Audit BibTeX references against Crossref or explicit human verification records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.network_safety import NetworkSafetyError, fetch_json, validate_https_url
except ModuleNotFoundError:  # Direct execution from scripts/.
    from network_safety import (  # type: ignore[no-redef]
        NetworkSafetyError,
        fetch_json,
        validate_https_url,
    )


ENTRY_RE = re.compile(r"@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
FIELD_RE = re.compile(
    r"(?ms)^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(?:\{(.*?)\}|\"(.*?)\")\s*,?\s*$"
)
DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)


class CitationAuditError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_doi(value: str) -> str:
    return DOI_PREFIX_RE.sub("", value.strip()).rstrip(".}").lower()


def normalize_title(value: str) -> str:
    value = re.sub(r"[{}\\]", "", value).lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_title(left), normalize_title(right)).ratio()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tex_citation_keys(path: Path) -> set[str]:
    text = re.sub(r"(?m)(?<!\\)%.*$", "", path.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for match in re.finditer(
        r"\\(?:cite|citep|citet|parencite|textcite|autocite)\*?(?:\[[^]]*\])*\{([^}]*)\}",
        text,
    ):
        keys.update(key.strip() for key in match.group(1).split(",") if key.strip())
    return keys


def parse_bibtex(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for match in ENTRY_RE.finditer(text):
        depth = 1
        index = match.end()
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        body = text[match.end() : index - 1] if depth == 0 else text[match.end() :]
        fields: dict[str, str] = {}
        for field in FIELD_RE.finditer(body):
            fields[field.group(1).lower()] = (field.group(2) or field.group(3) or "").strip()
        entries.append(
            {
                "type": match.group(1).lower(),
                "key": match.group(2),
                "fields": fields,
                "balanced": depth == 0,
            }
        )
    return entries


def crossref_record(doi: str, fetcher: Callable[..., Any]) -> dict[str, Any]:
    encoded = urllib.parse.quote(doi, safe="")
    payload = fetcher(f"https://api.crossref.org/works/{encoded}")
    if not isinstance(payload, dict) or not isinstance(payload.get("message"), dict):
        raise CitationAuditError("Crossref returned an unexpected response")
    return payload["message"]


def record_year(record: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "published", "issued"):
        parts = record.get(key, {}).get("date-parts", []) if isinstance(record.get(key), dict) else []
        if parts and isinstance(parts[0], list) and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def load_manual(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CitationAuditError(f"Cannot read manual verifications: {exc}") from exc
    if not isinstance(value, dict):
        raise CitationAuditError("Manual verifications must be an object keyed by citation key")
    records: dict[str, dict[str, Any]] = {}
    for key, record in value.items():
        if not isinstance(record, dict):
            raise CitationAuditError(f"Manual verification {key} must be an object")
        required = ("verified_by", "verified_at", "source_url", "title")
        if any(not isinstance(record.get(field), str) or not record[field].strip() for field in required):
            raise CitationAuditError(f"Manual verification {key} is missing required fields")
        try:
            validate_https_url(record["source_url"], f"manual verification {key} source_url")
        except NetworkSafetyError as exc:
            raise CitationAuditError(str(exc)) from exc
        try:
            datetime.fromisoformat(record["verified_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise CitationAuditError(
                f"Manual verification {key} verified_at must be ISO 8601"
            ) from exc
        records[str(key)] = record
    return records


def audit(
    bib_path: Path,
    *,
    manual_path: Path | None = None,
    offline: bool = False,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    try:
        text = bib_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CitationAuditError(f"Cannot read bibliography: {exc}") from exc
    entries = parse_bibtex(text)
    manual = load_manual(manual_path)
    findings: list[dict[str, Any]] = []
    seen_dois: dict[str, str] = {}
    for entry in entries:
        fields = entry["fields"]
        key = entry["key"]
        title = fields.get("title", "")
        result: dict[str, Any] = {
            "citation_key": key,
            "entry_type": entry["type"],
            "title": title or None,
            "doi": None,
            "status": "unverified",
            "issues": [],
        }
        if not entry["balanced"]:
            result["issues"].append("unbalanced BibTeX entry")
        if not title:
            result["issues"].append("missing title")
        doi_value = fields.get("doi")
        if doi_value:
            doi = normalize_doi(doi_value)
            result["doi"] = doi
            if not doi.startswith("10.") or "/" not in doi:
                result["issues"].append("malformed DOI")
            if doi in seen_dois:
                result["issues"].append(f"duplicate DOI also used by {seen_dois[doi]}")
            else:
                seen_dois[doi] = key
            if offline:
                result["issues"].append("DOI not queried in offline mode")
            elif not result["issues"]:
                try:
                    record = crossref_record(doi, fetcher)
                    crossref_title = " ".join(record.get("title", []))
                    similarity = title_similarity(title, crossref_title)
                    result["crossref"] = {
                        "title": crossref_title,
                        "year": record_year(record),
                        "type": record.get("type"),
                        "url": record.get("URL"),
                        "title_similarity": round(similarity, 4),
                    }
                    if similarity < 0.75:
                        result["issues"].append("title does not sufficiently match Crossref")
                    bib_year = fields.get("year")
                    crossref_year = record_year(record)
                    if bib_year and bib_year.isdigit() and crossref_year and int(bib_year) != crossref_year:
                        result["issues"].append(
                            f"year mismatch: bibliography {bib_year}, Crossref {crossref_year}"
                        )
                    if not result["issues"]:
                        result["status"] = "verified_crossref"
                except (NetworkSafetyError, CitationAuditError, OSError) as exc:
                    result["issues"].append(f"Crossref verification failed: {exc}")
        elif key in manual:
            verification = manual[key]
            similarity = title_similarity(title, verification["title"])
            result["manual_verification"] = verification
            if similarity < 0.75:
                result["issues"].append("title does not match the manual verification record")
            elif not result["issues"]:
                result["status"] = "verified_manual"
        else:
            result["issues"].append("no DOI or explicit human verification record")
        findings.append(result)
    unresolved = [item["citation_key"] for item in findings if not item["status"].startswith("verified_")]
    bibliography_keys = {entry["key"] for entry in entries}
    tex_path = bib_path.parent / "main.tex"
    docx_path = bib_path.parent / "main.docx"
    manuscript_path = tex_path if tex_path.is_file() else docx_path if docx_path.is_file() else None
    cited_keys = tex_citation_keys(tex_path) if tex_path.is_file() else set()
    missing_citations = sorted(cited_keys - bibliography_keys)
    if missing_citations:
        unresolved.extend(f"missing:{key}" for key in missing_citations)
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "bibliography": str(bib_path),
        "bibliography_sha256": sha256_file(bib_path),
        "manuscript": str(manuscript_path) if manuscript_path else None,
        "manuscript_sha256": sha256_file(manuscript_path) if manuscript_path else None,
        "offline": offline,
        "entry_count": len(entries),
        "verified_count": len(entries) - len(unresolved),
        "unresolved_count": len(unresolved),
        "unresolved_keys": unresolved,
        "status": "pass" if entries and not unresolved else "fail",
        "citation_usage": {
            "cited_keys": sorted(cited_keys),
            "missing_bibliography_keys": missing_citations,
            "unused_bibliography_keys": sorted(bibliography_keys - cited_keys)
            if tex_path.is_file()
            else [],
            "note": (
                "TeX citation keys were checked automatically. DOCX in-text citation mapping "
                "requires human inspection."
            ),
        },
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bibliography", type=Path)
    parser.add_argument("--manual-verifications", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(
            args.bibliography,
            manual_path=args.manual_verifications,
            offline=args.offline,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1
    except CitationAuditError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
