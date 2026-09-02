#!/usr/bin/env python3
"""Discover public dataset metadata without asserting license or fitness for use."""

from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import re
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
PROVIDERS = (
    "datacite",
    "zenodo",
    "huggingface",
    "openml",
    "figshare",
    "dryad",
    "dataverse",
    "datagov",
)


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


def _plain_text(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


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
        "description": _plain_text(description),
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


def figshare(query: str, limit: int, fetcher: Callable[..., Any]) -> list[dict[str, Any]]:
    payload = fetcher(
        "https://api.figshare.com/v2/articles/search",
        method="POST",
        json_body={
            "search_for": query,
            "item_type": 3,
            "page_size": limit,
            "order": "published_date",
            "order_direction": "desc",
        },
    )
    results: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        candidate = _candidate(
            provider="Figshare",
            provider_id=identifier,
            title=item.get("title"),
            landing_url=(
                item.get("url_public_html")
                or item.get("url")
                or (f"https://figshare.com/articles/dataset/_/{identifier}" if identifier else None)
            ),
            description=item.get("description"),
            doi=item.get("doi"),
            updated_at=item.get("modified_date") or item.get("published_date"),
        )
        if candidate:
            results.append(candidate)
    return results


def dryad(query: str, limit: int, fetcher: Callable[..., Any]) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query, "per_page": limit})
    payload = fetcher(f"https://datadryad.org/api/v2/search?{params}")
    embedded = payload.get("_embedded", {}) if isinstance(payload, dict) else {}
    datasets = []
    if isinstance(embedded, dict):
        datasets = embedded.get("stash:datasets") or embedded.get("datasets") or []
    results: list[dict[str, Any]] = []
    for item in datasets if isinstance(datasets, list) else []:
        if not isinstance(item, dict):
            continue
        identifier = item.get("identifier") or item.get("doi") or item.get("id")
        doi = str(identifier).removeprefix("doi:") if identifier is not None else None
        links = item.get("_links", {}) if isinstance(item.get("_links"), dict) else {}
        version_link = links.get("stash:version") or links.get("self") or {}
        api_url = version_link.get("href") if isinstance(version_link, dict) else None
        candidate = _candidate(
            provider="Dryad",
            provider_id=identifier,
            title=item.get("title"),
            landing_url=(f"https://doi.org/{doi}" if doi else api_url),
            description=item.get("abstract"),
            version=item.get("versionNumber") or item.get("version"),
            license_name=item.get("license"),
            doi=doi,
            updated_at=item.get("publicationDate") or item.get("lastModificationDate"),
        )
        if candidate:
            results.append(candidate)
    return results


def dataverse(query: str, limit: int, fetcher: Callable[..., Any]) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {"q": query, "type": "dataset", "per_page": limit, "sort": "score", "order": "desc"}
    )
    payload = fetcher(f"https://dataverse.harvard.edu/api/search?{params}")
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    items = data.get("items", []) if isinstance(data, dict) else []
    results: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        identifier = item.get("global_id") or item.get("identifier") or item.get("entity_id")
        candidate = _candidate(
            provider="Harvard Dataverse",
            provider_id=identifier,
            title=item.get("name") or item.get("title"),
            landing_url=item.get("url"),
            description=item.get("description"),
            version=item.get("version"),
            doi=identifier if isinstance(identifier, str) and "10." in identifier else None,
            updated_at=item.get("published_at") or item.get("updated_at"),
        )
        if candidate:
            results.append(candidate)
    return results


def datagov(query: str, limit: int, fetcher: Callable[..., Any]) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query, "rows": limit})
    payload = fetcher(f"https://catalog.data.gov/api/3/action/package_search?{params}")
    result = payload.get("result", {}) if isinstance(payload, dict) else {}
    datasets = result.get("results", []) if isinstance(result, dict) else []
    results: list[dict[str, Any]] = []
    for item in datasets if isinstance(datasets, list) else []:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id") or item.get("name")
        name = item.get("name")
        landing = item.get("url")
        if not isinstance(landing, str) or not landing.startswith("https://"):
            landing = f"https://catalog.data.gov/dataset/{name}" if name else None
        candidate = _candidate(
            provider="Data.gov",
            provider_id=identifier,
            title=item.get("title") or name,
            landing_url=landing,
            description=item.get("notes"),
            version=item.get("version"),
            license_name=item.get("license_title") or item.get("license_id"),
            updated_at=item.get("metadata_modified") or item.get("metadata_created"),
        )
        if candidate:
            results.append(candidate)
    return results


SEARCHERS: dict[str, Callable[[str, int, Callable[..., Any]], list[dict[str, Any]]]] = {
    "datacite": datacite,
    "zenodo": zenodo,
    "huggingface": huggingface,
    "openml": openml,
    "figshare": figshare,
    "dryad": dryad,
    "dataverse": dataverse,
    "datagov": datagov,
}


def _query_terms(query: str) -> set[str]:
    return {part for part in re.findall(r"[a-z0-9]+", query.lower()) if len(part) >= 3}


def _rank_candidate(candidate: dict[str, Any], queries: list[str]) -> tuple[int, list[str], list[str]]:
    title = str(candidate.get("title") or "").lower()
    description = str(candidate.get("description") or "").lower()
    matched_queries: list[str] = []
    matched_terms: set[str] = set()
    all_terms: set[str] = set()
    phrase_bonus = 0
    title_matches = 0
    for query in queries:
        terms = _query_terms(query)
        all_terms.update(terms)
        current = {term for term in terms if term in title or term in description}
        if current:
            matched_queries.append(query)
            matched_terms.update(current)
        normalized_query = " ".join(re.findall(r"[a-z0-9]+", query.lower()))
        if normalized_query and normalized_query in f"{title} {description}":
            phrase_bonus = max(phrase_bonus, 18)
        title_matches += len({term for term in terms if term in title})
    coverage = len(matched_terms) / max(1, len(all_terms))
    score = min(
        100,
        round(coverage * 62 + min(title_matches, 5) * 4 + phrase_bonus
              + (5 if candidate.get("doi") else 0)
              + (4 if candidate.get("license_claim") else 0)),
    )
    reasons = [f"matched {len(matched_terms)}/{max(1, len(all_terms))} query terms"]
    if title_matches:
        reasons.append(f"{title_matches} title-term matches")
    if candidate.get("doi"):
        reasons.append("persistent identifier present")
    if candidate.get("license_claim"):
        reasons.append("license metadata present but unverified")
    return score, reasons, matched_queries


def _dedupe_key(candidate: dict[str, Any]) -> str:
    doi = str(candidate.get("doi") or "").lower().strip()
    doi = doi.removeprefix("https://doi.org/").removeprefix("doi:")
    if doi:
        return f"doi:{doi}"
    return f"url:{str(candidate.get('landing_url') or '').lower().rstrip('/')}"


def discover_many(
    queries: Iterable[str],
    providers: Iterable[str],
    limit: int,
    *,
    max_candidates: int = 250,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    cleaned_queries = list(dict.fromkeys(item.strip() for item in queries if item.strip()))
    if not cleaned_queries:
        raise DiscoveryError("at least one query is required")
    if len(cleaned_queries) > 12:
        raise DiscoveryError("at most 12 query variants are allowed")
    selected = list(dict.fromkeys(providers))
    if not selected:
        raise DiscoveryError("at least one provider is required")
    unknown = sorted(set(selected) - set(PROVIDERS))
    if unknown:
        raise DiscoveryError(f"unknown providers: {', '.join(unknown)}")
    if not 1 <= limit <= 100:
        raise DiscoveryError("limit must be between 1 and 100 per provider")
    if not 1 <= max_candidates <= 2000:
        raise DiscoveryError("max_candidates must be between 1 and 2000")

    tasks = [(query, provider) for query in cleaned_queries for provider in selected]

    def search(task: tuple[str, str]) -> tuple[str, str, list[dict[str, Any]], str | None]:
        query, provider = task
        try:
            return query, provider, SEARCHERS[provider](query, limit, fetcher), None
        except (NetworkSafetyError, OSError, KeyError, TypeError, ValueError) as exc:
            return query, provider, [], str(exc)

    collected: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(tasks))) as pool:
        for query, provider, found, error in pool.map(search, tasks):
            sources.append(
                {"query": query, "provider": provider, "status": "error" if error else "ok",
                 "candidate_count": len(found), **({"error": error} if error else {})}
            )
            for candidate in found:
                candidate["matched_queries"] = [query]
                collected.append(candidate)

    merged: dict[str, dict[str, Any]] = {}
    for candidate in collected:
        key = _dedupe_key(candidate)
        if key not in merged:
            merged[key] = candidate
            candidate["also_found_by"] = [candidate["provider"]]
        else:
            current = merged[key]
            current["matched_queries"] = sorted(
                set(current.get("matched_queries", [])) | set(candidate.get("matched_queries", []))
            )
            current["also_found_by"] = sorted(
                set(current.get("also_found_by", [])) | {candidate["provider"]}
            )
            if not current.get("license_claim") and candidate.get("license_claim"):
                current["license_claim"] = candidate["license_claim"]

    ranked = list(merged.values())
    for candidate in ranked:
        score, reasons, matched = _rank_candidate(candidate, cleaned_queries)
        candidate["metadata_relevance_score"] = score
        candidate["screening_reasons"] = reasons
        candidate["matched_queries"] = sorted(set(candidate.get("matched_queries", [])) | set(matched))
        candidate["fitness_status"] = "candidate_only_requires_scientific_and_human_review"
    ranked.sort(
        key=lambda item: (
            -int(item["metadata_relevance_score"]),
            -len(item.get("also_found_by", [])),
            str(item.get("title", "")).lower(),
        )
    )
    ranked = ranked[:max_candidates]
    return {
        "schema_version": "1.1",
        "created_at": now(),
        "query": cleaned_queries[0],
        "queries": cleaned_queries,
        "providers": sources,
        "provider_count": len(selected),
        "query_count": len(cleaned_queries),
        "raw_candidate_count": len(collected),
        "candidate_count": len(ranked),
        "candidates": ranked,
        "ranking_note": (
            "The score measures metadata/query overlap only. It is not evidence of scientific "
            "fitness, data quality, license validity, novelty, or publication suitability."
        ),
        "warning": (
            "Discovery metadata is not a license decision. A human must verify the official "
            "record, terms, privacy, provenance, version, download URL and research fitness."
        ),
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
    if not selected:
        raise DiscoveryError("at least one provider is required")
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
    parser.add_argument("--query", action="append", dest="extra_queries", default=[])
    parser.add_argument("--provider", action="append", choices=PROVIDERS, dest="providers")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--max-candidates", type=int, default=250)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project", help="Append a compact query record to this project")
    args = parser.parse_args()
    try:
        report = discover_many(
            [args.query, *args.extra_queries],
            args.providers or PROVIDERS,
            args.limit,
            max_candidates=args.max_candidates,
        )
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
