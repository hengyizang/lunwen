#!/usr/bin/env python3
"""Resolve lawful open-access full-text candidates without bypassing controls.

The resolver combines public metadata from OpenAlex, Unpaywall and Crossref.
Every URL remains a candidate until a human or downstream license check confirms
that the exact file may be downloaded and used for the project.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.network_safety import fetch_json
except ImportError:
    from network_safety import fetch_json  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)


class FullTextResolverError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_doi(value: str) -> str:
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I).strip().lower()
    if not DOI_RE.fullmatch(value) or any(char.isspace() for char in value):
        raise FullTextResolverError("doi must be a syntactically valid DOI")
    return value


def _url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("https://"):
        return None
    return value


def _candidate(
    *,
    source: str,
    url: Any,
    landing_url: Any = None,
    version: Any = None,
    license_value: Any = None,
    host_type: Any = None,
    open_access_asserted: bool = False,
) -> dict[str, Any] | None:
    resolved = _url(url) or _url(landing_url)
    if not resolved:
        return None
    return {
        "source": source,
        "url": resolved,
        "landing_url": _url(landing_url),
        "version": str(version) if version else None,
        "license_claim": str(license_value) if license_value else None,
        "host_type": str(host_type) if host_type else None,
        "open_access_asserted_by_provider": bool(open_access_asserted),
        "license_verified": False,
        "download_authorized": False,
    }


def _openalex(doi: str, fetcher: Callable[..., Any]) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(doi, safe="/")
    value = fetcher(f"https://api.openalex.org/works/https://doi.org/{encoded}")
    if not isinstance(value, dict):
        return []
    is_oa = bool((value.get("open_access") or {}).get("is_oa"))
    locations = value.get("locations") if isinstance(value.get("locations"), list) else []
    best = value.get("best_oa_location")
    if isinstance(best, dict):
        locations = [best, *locations]
    out: list[dict[str, Any]] = []
    for item in locations:
        if not isinstance(item, dict):
            continue
        candidate = _candidate(
            source="OpenAlex",
            url=item.get("pdf_url"),
            landing_url=item.get("landing_page_url"),
            version=item.get("version"),
            license_value=item.get("license"),
            host_type=(item.get("source") or {}).get("host_organization_name")
            if isinstance(item.get("source"), dict)
            else None,
            open_access_asserted=is_oa or bool(item.get("is_oa")),
        )
        if candidate:
            out.append(candidate)
    return out


def _unpaywall(
    doi: str, email: str | None, fetcher: Callable[..., Any]
) -> list[dict[str, Any]]:
    if not email:
        return []
    query = urllib.parse.urlencode({"email": email})
    value = fetcher(
        f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi, safe='/')}?{query}"
    )
    if not isinstance(value, dict):
        return []
    locations = value.get("oa_locations") if isinstance(value.get("oa_locations"), list) else []
    best = value.get("best_oa_location")
    if isinstance(best, dict):
        locations = [best, *locations]
    out: list[dict[str, Any]] = []
    for item in locations:
        if not isinstance(item, dict):
            continue
        candidate = _candidate(
            source="Unpaywall",
            url=item.get("url_for_pdf"),
            landing_url=item.get("url_for_landing_page"),
            version=item.get("version"),
            license_value=item.get("license"),
            host_type=item.get("host_type"),
            open_access_asserted=bool(value.get("is_oa")),
        )
        if candidate:
            out.append(candidate)
    return out


def _crossref(doi: str, fetcher: Callable[..., Any]) -> list[dict[str, Any]]:
    value = fetcher(
        f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    )
    message = value.get("message") if isinstance(value, dict) else None
    if not isinstance(message, dict):
        return []
    licenses = message.get("license") if isinstance(message.get("license"), list) else []
    license_url = next(
        (
            item.get("URL")
            for item in licenses
            if isinstance(item, dict) and isinstance(item.get("URL"), str)
        ),
        None,
    )
    links = message.get("link") if isinstance(message.get("link"), list) else []
    out: list[dict[str, Any]] = []
    for item in links:
        if not isinstance(item, dict):
            continue
        content_type = str(item.get("content-type") or "")
        if "pdf" not in content_type.lower() and "xml" not in content_type.lower():
            continue
        candidate = _candidate(
            source="Crossref",
            url=item.get("URL"),
            version=item.get("content-version"),
            license_value=license_url,
            host_type="publisher",
            open_access_asserted=False,
        )
        if candidate:
            out.append(candidate)
    return out


def resolve(
    doi: str,
    *,
    email: str | None = None,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    normalized = normalize_doi(doi)
    providers = (
        ("OpenAlex", lambda: _openalex(normalized, fetcher)),
        ("Unpaywall", lambda: _unpaywall(normalized, email, fetcher)),
        ("Crossref", lambda: _crossref(normalized, fetcher)),
    )
    candidates: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for name, operation in providers:
        if name == "Unpaywall" and not email:
            failures.append({"source": name, "error": "skipped: contact email not configured"})
            continue
        try:
            candidates.extend(operation())
        except Exception as exc:
            failures.append({"source": name, "error": str(exc)[:1000]})
    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate["url"]).rstrip("/").casefold()
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(candidate)
    deduplicated.sort(
        key=lambda item: (
            not item["open_access_asserted_by_provider"],
            item["source"],
            item["url"],
        )
    )
    return {
        "schema_version": "1.0",
        "doi": normalized,
        "resolved_at": utc_now(),
        "status": "candidates_found" if deduplicated else "no_verified_candidate",
        "candidates": deduplicated,
        "provider_failures": failures,
        "policy": {
            "advisory_only": True,
            "license_and_terms_human_confirmation_required": True,
            "access_controls_must_not_be_bypassed": True,
            "publisher_or_library_entitlement_is_not_inferred": True,
        },
    }


def save(project: Path, report: dict[str, Any]) -> Path:
    if not project.is_dir():
        raise FullTextResolverError(f"project does not exist: {project}")
    digest = hashlib.sha256(report["doi"].encode("utf-8")).hexdigest()[:16]
    path = project / "evidence" / "fulltext" / f"doi-{digest}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--doi", required=True)
    parser.add_argument("--email")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", args.project):
        raise SystemExit("error: invalid project slug")
    try:
        report = resolve(args.doi, email=args.email)
        path = save(PROJECTS_ROOT / args.project, report)
    except FullTextResolverError as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
