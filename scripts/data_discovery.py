#!/usr/bin/env python3
"""Discover public dataset metadata without asserting license or fitness for use."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from scripts.network_safety import NetworkSafetyError, fetch_json
except ModuleNotFoundError:  # Direct execution from scripts/.
    from network_safety import NetworkSafetyError, fetch_json  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
PROVIDERS = ("datacite", "zenodo", "huggingface", "openml")


class DiscoveryError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _first_text(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            result = _text(item)
            if result:
                return result
    return _text(value)


def _candidate(
    *,
    provider: str,
    provider_id: Any,
    title: Any,
    landing_url: Any,
    description: Any = None,
    version: Any = None,
    license_name: Any = None,
    doi: Any = None,
    updated_at: Any = None,
) -> dict[str, Any] | None:
    identifier = _text(str(provider_id)) if provider_id is not None else None
    normalized_title = _text(title)
    url = _text(landing_url)
    if not identifier or not normalized_title or not url or not url.startswith("https://"):
        return None
    return {
        "provider": provider,
        "provider_id": identifier,
        "title": normalized_title,
        "landing_url": url,
        "description": _text(description),
        "version": _text(str(version)) if version is not None else None,
        "doi": _text(doi),
        "license_claim": _text(license_name),
        "license_status": "unverified_requires_human_review",
        "updated_at": _text(updated_at),
        "download": None,
        "fitness_status": "candidate_only",
    }


def datacite(query: str, limit: int, fetcher: Callable[..., Any]) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {"query": query, "resource-type-id": "dataset", "page[size]": limit}
    )
    payload = fetcher(f"https://api.datacite.org/dois?{params}")
    results: list[dict[str, Any]] = []
    for item in payload.get("data", []) if isinstance(payload, dict) else []:
        attributes = item.get("attributes", {}) if isinstance(item, dict) else {}
        titles = attributes.get("titles", [])
        title = titles[0].get("title") if titles and isinstance(titles[0], dict) else None
        descriptions = attributes.get("descriptions", [])
        description = (
            descriptions[0].get("description")
            if descriptions and isinstance(descriptions[0], dict)
            else None
        )
        rights = attributes.get("rightsList", [])
        license_name = (
            rights[0].get("rightsIdentifier") or rights[0].get("rights")
            if rights and isinstance(rights[0], dict)
            else None
        )
        candidate = _candidate(
            provider="DataCite",
            provider_id=item.get("id"),
            title=title,
            landing_url=attributes.get("url") or f"https://doi.org/{item.get('id', '')}",
            description=description,
            version=attributes.get("version"),
            license_name=license_name,
            doi=attributes.get("doi") or item.get("id"),
            updated_at=attributes.get("updated"),
        )
        if candidate:
            results.append(candidate)
    return results


def zenodo(query: str, limit: int, fetcher: Callable[..., Any]) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query, "size": limit, "type": "dataset"})
    payload = fetcher(f"https://zenodo.org/api/records?{params}")
    hits = payload.get("hits", {}).get("hits", []) if isinstance(payload, dict) else []
    results: list[dict[str, Any]] = []
    for item in hits:
        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
        license_value = metadata.get("license")
        if isinstance(license_value, dict):
            license_value = license_value.get("id") or license_value.get("title")
        links = item.get("links", {}) if isinstance(item, dict) else {}
        candidate = _candidate(
            provider="Zenodo",
            provider_id=item.get("id"),
            title=metadata.get("title"),
            landing_url=links.get("html") or links.get("self_html"),
            description=metadata.get("description"),
            version=metadata.get("version"),
            license_name=license_value,
            doi=metadata.get("doi") or item.get("doi"),
            updated_at=item.get("updated"),
        )
        if candidate:
            results.append(candidate)
    return results


def huggingface(query: str, limit: int, fetcher: Callable[..., Any]) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"search": query, "limit": limit, "full": "true"})
    payload = fetcher(f"https://huggingface.co/api/datasets?{params}")
    results: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        identifier = item.get("id") if isinstance(item, dict) else None
        card = item.get("cardData", {}) if isinstance(item, dict) else {}
        license_value = card.get("license") if isinstance(card, dict) else None
        if isinstance(license_value, list):
            license_value = ", ".join(str(part) for part in license_value)
        candidate = _candidate(
            provider="Hugging Face",
            provider_id=identifier,
            title=(card.get("pretty_name") if isinstance(card, dict) else None) or identifier,
            landing_url=f"https://huggingface.co/datasets/{identifier}" if identifier else None,
            description=card.get("description") if isinstance(card, dict) else None,
            version=item.get("sha") if isinstance(item, dict) else None,
            license_name=license_value,
            updated_at=item.get("lastModified") if isinstance(item, dict) else None,
        )
        if candidate:
            results.append(candidate)
    return results


def openml(query: str, limit: int, fetcher: Callable[..., Any]) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(query, safe="")
    payload = fetcher(
        f"https://www.openml.org/api/v1/json/data/list/data_name/{encoded}/limit/{limit}"
    )
    datasets = payload.get("data", {}).get("dataset", []) if isinstance(payload, dict) else []
    results: list[dict[str, Any]] = []
    for item in datasets:
        dataset_id = item.get("did") if isinstance(item, dict) else None
        candidate = _candidate(
            provider="OpenML",
            provider_id=dataset_id,
            title=item.get("name") if isinstance(item, dict) else None,
            landing_url=(
                f"https://www.openml.org/d/{dataset_id}" if dataset_id is not None else None
            ),
            version=item.get("version") if isinstance(item, dict) else None,
            license_name=item.get("licence") if isinstance(item, dict) else None,
            updated_at=item.get("upload_date") if isinstance(item, dict) else None,
        )
        if candidate:
            results.append(candidate)
    return results


SEARCHERS: dict[str, Callable[[str, int, Callable[..., Any]], list[dict[str, Any]]]] = {
    "datacite": datacite,
    "zenodo": zenodo,
    "huggingface": huggingface,
    "openml": openml,
}


def discover(
    query: str,
    providers: Iterable[str],
    limit: int,
    *,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    if not query.strip():
        raise DiscoveryError("query must not be empty")
    if not 1 <= limit <= 100:
        raise DiscoveryError("limit must be between 1 and 100 per provider")
    selected = list(dict.fromkeys(providers))
    unknown = sorted(set(selected) - set(PROVIDERS))
    if unknown:
        raise DiscoveryError(f"unknown providers: {', '.join(unknown)}")
    candidates: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for provider in selected:
        try:
            found = SEARCHERS[provider](query.strip(), limit, fetcher)
            candidates.extend(found)
            sources.append({"provider": provider, "status": "ok", "candidate_count": len(found)})
        except (NetworkSafetyError, OSError, KeyError, TypeError, ValueError) as exc:
            sources.append({"provider": provider, "status": "error", "error": str(exc)})
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "query": query.strip(),
        "providers": sources,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "warning": (
            "Discovery metadata is not a license decision. A human must verify the official "
            "record, terms, privacy, provenance, version, download URL and research fitness."
        ),
    }


def save_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_search_log(project: str, report: dict[str, Any]) -> None:
    if not project or any(part in project for part in ("/", "\\", "..")):
        raise DiscoveryError("project must be a simple project slug")
    path = PROJECTS_ROOT / project / "evidence" / "search-log.jsonl"
    if not path.parent.is_dir():
        raise DiscoveryError(f"project does not exist: {project}")
    entry = {
        "searched_at": report["created_at"],
        "kind": "dataset_discovery",
        "query": report["query"],
        "providers": report["providers"],
        "candidate_count": report["candidate_count"],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--provider", action="append", choices=PROVIDERS, dest="providers")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project", help="Append a compact query record to this project")
    args = parser.parse_args()
    try:
        report = discover(args.query, args.providers or PROVIDERS, args.limit)
        if args.output:
            save_report(report, args.output)
        if args.project:
            append_search_log(args.project, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if any(item["status"] == "ok" for item in report["providers"]) else 2
    except DiscoveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
