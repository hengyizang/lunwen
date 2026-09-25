#!/usr/bin/env python3
"""Create hash-bound evidence for live literature searches and local exports.

The module records the exact provider response before normalization, appends an
immutable call receipt, and creates a G1 search-log entry that remains pending
until a named human screens the returned identifiers.  Commercial database
exports are imported locally and hash-bound; this program never automates or
bypasses Web of Science, Scopus, or JCR access controls.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from scripts.network_safety import DEFAULT_JSON_LIMIT, fetch_bytes
except ImportError:
    from network_safety import DEFAULT_JSON_LIMIT, fetch_bytes  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
PROVIDERS = (
    "openalex",
    "crossref",
    "semantic-scholar",
    "arxiv",
    "europe-pmc",
    "dblp",
    "hal",
)
DISPLAY_NAMES = {
    "openalex": "OpenAlex",
    "crossref": "Crossref",
    "semantic-scholar": "Semantic Scholar",
    "arxiv": "arXiv",
    "europe-pmc": "Europe PMC",
    "dblp": "DBLP",
    "hal": "HAL",
    "opencitations": "OpenCitations",
    "wos": "Web of Science",
    "scopus": "Scopus",
}
SOURCE_URLS = {
    "wos": "https://www.webofscience.com/",
    "scopus": "https://www.scopus.com/",
}
MAX_RESULTS = 100
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_RECEIPT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,127}$")
TRANSIENT_HTTP_RE = re.compile(r"HTTP Error (?:429|500|502|503|504)\b")


class LiteratureEvidenceError(RuntimeError):
    """Raised when evidence cannot be produced or verified safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def project_path(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", slug):
        raise LiteratureEvidenceError("project must be a safe 2-63 character slug")
    project = PROJECTS_ROOT / slug
    if not project.is_dir():
        raise LiteratureEvidenceError(f"project does not exist: {slug}")
    return project


def safe_project_file(project: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise LiteratureEvidenceError("file must be project-relative and cannot contain ..")
    path = (project / relative).resolve()
    if path == project.resolve() or project.resolve() not in path.parents:
        raise LiteratureEvidenceError("file escapes the project directory")
    if not path.is_file() or path.is_symlink():
        raise LiteratureEvidenceError(f"file is not a regular project file: {value}")
    return path


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def replace_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        temporary = handle.name
    os.replace(temporary, path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    values: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LiteratureEvidenceError(f"invalid JSONL {path}:{number}: {exc}") from exc
        if not isinstance(value, dict):
            raise LiteratureEvidenceError(f"JSONL entry must be an object: {path}:{number}")
        values.append(value)
    return values


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = " ".join(str(value).split())
    return result or None


def _doi(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.I)
    text = re.sub(r"^doi:\s*", "", text, flags=re.I).strip().lower()
    embedded = re.search(r"(?:^|\s)doi:(10\.[^\s;]+/[^\s;]+)", text, flags=re.I)
    if embedded:
        text = embedded.group(1).lower()
    return text if text.startswith("10.") and "/" in text else None


def provider_headers(provider: str) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "DoctoralResearchOS/2.2 "
            "(https://github.com/hengyizang/lunwen; auditable metadata discovery)"
        )
    }
    if provider == "arxiv":
        headers["Accept"] = "application/atom+xml"
    elif provider == "dblp":
        headers["Accept"] = "application/sparql-results+json"
    else:
        headers["Accept"] = "application/json"
    if provider == "semantic-scholar":
        api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        if api_key:
            headers["x-api-key"] = api_key
    if provider == "opencitations":
        access_token = os.environ.get("OPENCITATIONS_ACCESS_TOKEN", "").strip()
        if access_token:
            headers["authorization"] = access_token
    return headers


def fetch_provider_bytes(
    fetcher: Callable[..., tuple[bytes, str, int | None, str | None]],
    request_url: str,
    provider: str,
) -> tuple[bytes, str, int | None, str | None]:
    """Retry only explicit transient HTTP failures, preserving all final errors."""

    for attempt, delay in enumerate((0, 2, 5), 1):
        if delay:
            time.sleep(delay)
        try:
            return fetcher(
                request_url,
                max_bytes=MAX_RESPONSE_BYTES,
                headers=provider_headers(provider),
            )
        except Exception as exc:
            if attempt == 3 or not TRANSIENT_HTTP_RE.search(str(exc)):
                raise
    raise AssertionError("unreachable provider retry state")


def _year(value: Any) -> int | None:
    if isinstance(value, int) and 1800 <= value <= 2100:
        return value
    match = re.search(r"\b(18|19|20|21)\d{2}\b", str(value or ""))
    return int(match.group(0)) if match else None


def _authors(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for item in values:
        if isinstance(item, str):
            name = _text(item)
        elif isinstance(item, dict):
            name = _text(
                item.get("display_name")
                or item.get("name")
                or " ".join(
                    str(item.get(key, "")) for key in ("given", "family")
                )
            )
        else:
            name = None
        if name and name not in result:
            result.append(name)
    return result


def normalized_work(
    provider: str,
    provider_id: Any,
    title: Any,
    year: Any,
    doi: Any,
    url: Any,
    authors: Any,
    *,
    abstract: Any = None,
    venue: Any = None,
) -> dict[str, Any] | None:
    normalized_title = _text(title)
    if not normalized_title:
        return None
    normalized_doi = _doi(doi)
    normalized_provider_id = _text(provider_id)
    stable_id = (
        f"doi:{normalized_doi}"
        if normalized_doi
        else f"{provider}:{normalized_provider_id or sha256_bytes(normalized_title.lower().encode())[:20]}"
    )
    link = _text(url)
    if not link and normalized_doi:
        link = f"https://doi.org/{normalized_doi}"
    return {
        "id": stable_id,
        "provider": DISPLAY_NAMES.get(provider, provider),
        "provider_id": normalized_provider_id,
        "doi": normalized_doi,
        "title": normalized_title,
        "publication_year": _year(year),
        "primary_source_url": link,
        "authors": _authors(authors),
        "venue": _text(venue),
        "abstract": _text(abstract),
    }


def build_search_url(provider: str, query: str, limit: int) -> str:
    encoded = urllib.parse.urlencode
    if provider == "openalex":
        return "https://api.openalex.org/works?" + encoded(
            {"search": query, "per-page": limit}
        )
    if provider == "crossref":
        return "https://api.crossref.org/works?" + encoded(
            {"query.bibliographic": query, "rows": limit}
        )
    if provider == "semantic-scholar":
        return "https://api.semanticscholar.org/graph/v1/paper/search?" + encoded(
            {
                "query": query,
                "limit": limit,
                "fields": "paperId,title,year,authors,externalIds,url,abstract,venue,publicationDate",
            }
        )
    if provider == "arxiv":
        terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]*", query)[:8]
        search_query = " AND ".join(f"all:{term}" for term in terms) or "all:science"
        return "https://export.arxiv.org/api/query?" + encoded(
            {"search_query": search_query, "start": 0, "max_results": limit}
        )
    if provider == "europe-pmc":
        return "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + encoded(
            {"query": query, "pageSize": limit, "format": "json"}
        )
    if provider == "dblp":
        terms = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]*", query.lower())[:2]
        phrase = " ".join(terms) or "science"
        sparql = "\n".join(
            (
                "PREFIX dblp: <https://dblp.org/rdf/schema#>",
                "SELECT ?publ ?title ?year ?doi WHERE {",
                "  ?publ a dblp:Publication ; dblp:title ?title .",
                "  OPTIONAL { ?publ dblp:yearOfPublication ?year . }",
                "  OPTIONAL { ?publ dblp:doi ?doi . }",
                f'  FILTER(CONTAINS(LCASE(STR(?title)), "{phrase}"))',
                "}",
                f"LIMIT {limit}",
            )
        )
        return "https://sparql.dblp.org/sparql?" + encoded({"query": sparql})
    if provider == "hal":
        return "https://api.archives-ouvertes.fr/search/?" + encoded(
            {
                "q": query,
                "rows": limit,
                "fl": "halId_s,title_s,producedDateY_i,doiId_s,uri_s,authFullName_s,abstract_s,journalTitle_s",
                "wt": "json",
            }
        )
    raise LiteratureEvidenceError(f"unsupported provider: {provider}")


def _json_payload(payload: bytes) -> Any:
    try:
        return json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiteratureEvidenceError(f"provider returned invalid UTF-8 JSON: {exc}") from exc


def normalize_search(provider: str, payload: bytes) -> list[dict[str, Any]]:
    works: list[dict[str, Any] | None] = []
    if provider == "arxiv":
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise LiteratureEvidenceError(f"arXiv returned invalid Atom XML: {exc}") from exc
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            identifier = _text(entry.findtext("a:id", default="", namespaces=ns))
            authors = [
                _text(author.findtext("a:name", default="", namespaces=ns)) or ""
                for author in entry.findall("a:author", ns)
            ]
            doi = entry.findtext("{http://arxiv.org/schemas/atom}doi")
            works.append(
                normalized_work(
                    provider,
                    identifier.rsplit("/", 1)[-1] if identifier else None,
                    entry.findtext("a:title", default="", namespaces=ns),
                    entry.findtext("a:published", default="", namespaces=ns),
                    doi,
                    identifier,
                    authors,
                    abstract=entry.findtext("a:summary", default="", namespaces=ns),
                )
            )
    else:
        data = _json_payload(payload)
        if provider == "openalex":
            for item in data.get("results", []) if isinstance(data, dict) else []:
                if not isinstance(item, dict):
                    continue
                primary = item.get("primary_location") if isinstance(item.get("primary_location"), dict) else {}
                source = primary.get("source") if isinstance(primary.get("source"), dict) else {}
                works.append(normalized_work(
                    provider, item.get("id"), item.get("display_name"), item.get("publication_year"),
                    item.get("doi"), item.get("doi") or item.get("id"),
                    [value.get("author", {}) for value in item.get("authorships", []) if isinstance(value, dict)],
                    venue=source.get("display_name"),
                ))
        elif provider == "crossref":
            message = data.get("message", {}) if isinstance(data, dict) else {}
            for item in message.get("items", []) if isinstance(message, dict) else []:
                if not isinstance(item, dict):
                    continue
                title = item.get("title", [None])
                container = item.get("container-title", [None])
                issued = item.get("issued", {}).get("date-parts", [[None]]) if isinstance(item.get("issued"), dict) else [[None]]
                works.append(normalized_work(
                    provider, item.get("DOI"), title[0] if isinstance(title, list) and title else title,
                    issued[0][0] if issued and issued[0] else None, item.get("DOI"), item.get("URL"),
                    item.get("author", []), venue=container[0] if isinstance(container, list) and container else container,
                ))
        elif provider == "semantic-scholar":
            for item in data.get("data", []) if isinstance(data, dict) else []:
                if not isinstance(item, dict):
                    continue
                external = item.get("externalIds") if isinstance(item.get("externalIds"), dict) else {}
                works.append(normalized_work(
                    provider, item.get("paperId"), item.get("title"), item.get("year") or item.get("publicationDate"),
                    external.get("DOI"), item.get("url"), item.get("authors", []),
                    abstract=item.get("abstract"), venue=item.get("venue"),
                ))
        elif provider == "europe-pmc":
            result_list = data.get("resultList", {}) if isinstance(data, dict) else {}
            for item in result_list.get("result", []) if isinstance(result_list, dict) else []:
                if not isinstance(item, dict):
                    continue
                author_text = item.get("authorString")
                works.append(normalized_work(
                    provider, item.get("id") or item.get("pmcid"), item.get("title"), item.get("pubYear"),
                    item.get("doi"), f"https://europepmc.org/article/{item.get('source', 'MED')}/{item.get('id')}" if item.get("id") else None,
                    [part.strip() for part in str(author_text or "").split(",") if part.strip()],
                    venue=item.get("journalTitle"),
                ))
        elif provider == "dblp":
            results = data.get("results", {}) if isinstance(data, dict) else {}
            bindings = results.get("bindings", []) if isinstance(results, dict) else []
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                values = {
                    key: item.get("value")
                    for key, item in binding.items()
                    if isinstance(item, dict)
                }
                works.append(
                    normalized_work(
                        provider,
                        values.get("publ"),
                        values.get("title"),
                        values.get("year"),
                        values.get("doi"),
                        values.get("publ"),
                        [],
                    )
                )
        elif provider == "hal":
            response = data.get("response", {}) if isinstance(data, dict) else {}
            for item in response.get("docs", []) if isinstance(response, dict) else []:
                if not isinstance(item, dict):
                    continue
                title = item.get("title_s")
                works.append(normalized_work(
                    provider, item.get("halId_s"), title[0] if isinstance(title, list) and title else title,
                    item.get("producedDateY_i"), item.get("doiId_s"), item.get("uri_s"),
                    item.get("authFullName_s", []), abstract=item.get("abstract_s"), venue=item.get("journalTitle_s"),
                ))
        else:
            raise LiteratureEvidenceError(f"unsupported provider: {provider}")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for work in works:
        if work is None or work["id"] in seen:
            continue
        seen.add(work["id"])
        result.append(work)
    return result


def execute_citation_graph(
    project: Path,
    doi: str,
    direction: str,
    *,
    date_range: str,
    filters: str,
    fetcher: Callable[..., tuple[bytes, str, int | None, str | None]] = fetch_bytes,
) -> dict[str, Any]:
    normalized_doi = _doi(doi)
    if not normalized_doi:
        raise LiteratureEvidenceError("citation expansion requires a valid DOI")
    if direction not in {"citations", "references"}:
        raise LiteratureEvidenceError("direction must be citations or references")
    if not date_range.strip() or not filters.strip():
        raise LiteratureEvidenceError("date-range and filters are required")
    identifier = urllib.parse.quote(f"doi:{normalized_doi}", safe=":/")
    request_url = f"https://api.opencitations.net/index/v2/{direction}/{identifier}"
    receipt_id = _receipt_id("opencitations")
    requested_at = utc_now()
    raw_path, normalized_path = _artifact_paths(project, receipt_id, "json")
    payload: bytes | None = None
    final_url: str | None = None
    status: int | None = None
    content_type: str | None = None
    try:
        payload, final_url, status, content_type = fetch_provider_bytes(
            fetcher, request_url, "opencitations"
        )
        raw_path.write_bytes(payload)
        data = _json_payload(payload)
        if not isinstance(data, list):
            raise LiteratureEvidenceError("OpenCitations response must be an array")
        works: list[dict[str, Any]] = []
        target_field = "citing" if direction == "citations" else "cited"
        for item in data:
            if not isinstance(item, dict):
                continue
            target_doi = _doi(item.get(target_field))
            if not target_doi:
                continue
            work = normalized_work(
                "opencitations",
                target_doi,
                f"DOI {target_doi} (resolve metadata before inclusion)",
                item.get("creation"),
                target_doi,
                f"https://doi.org/{target_doi}",
                [],
            )
            if work:
                work["citation_edge"] = {
                    "direction": direction,
                    "seed_doi": normalized_doi,
                    "oci": item.get("oci"),
                }
                works.append(work)
    except Exception as exc:
        failed = {
            "schema_version": "1.0", "receipt_id": receipt_id,
            "mode": "citation_graph", "provider": "opencitations",
            "provider_name": DISPLAY_NAMES["opencitations"], "query": normalized_doi,
            "request_url": request_url, "requested_at": requested_at,
            "completed_at": utc_now(), "status": "failed", "error": str(exc),
        }
        if payload is not None:
            failed.update(
                {
                    "final_url": final_url,
                    "http_status": status,
                    "content_type": content_type,
                    "response_sha256": sha256_bytes(payload),
                    "raw_response_path": raw_path.relative_to(project).as_posix(),
                }
            )
        append_jsonl(project / "evidence" / "literature-api-ledger.jsonl", failed)
        raise LiteratureEvidenceError(f"OpenCitations expansion failed: {exc}") from exc
    assert payload is not None and final_url is not None
    normalized_payload = canonical_json_bytes({"schema_version": "1.0", "works": works}) + b"\n"
    normalized_path.write_bytes(normalized_payload)
    receipt = {
        "schema_version": "1.0", "receipt_id": receipt_id,
        "mode": "citation_graph", "provider": "opencitations",
        "provider_name": DISPLAY_NAMES["opencitations"], "query": normalized_doi,
        "request_url": request_url, "final_url": final_url,
        "requested_at": requested_at, "completed_at": utc_now(), "status": "success",
        "http_status": status, "content_type": content_type, "direction": direction,
        "result_count": len(works), "response_sha256": sha256_bytes(payload),
        "normalized_results_sha256": sha256_bytes(normalized_payload),
        "raw_response_path": raw_path.relative_to(project).as_posix(),
        "normalized_results_path": normalized_path.relative_to(project).as_posix(),
    }
    append_jsonl(project / "evidence" / "literature-api-ledger.jsonl", receipt)
    append_jsonl(
        project / "evidence" / "search-log.jsonl",
        _search_record(
            receipt,
            "forward_citation" if direction == "citations" else "backward_citation",
            date_range.strip(),
            filters.strip(),
        ),
    )
    return receipt


def _receipt_id(provider: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    return f"{timestamp}-{provider}-{uuid.uuid4().hex[:10]}"


def _artifact_paths(project: Path, receipt_id: str, extension: str) -> tuple[Path, Path]:
    base = project / "evidence" / "literature"
    raw = base / "raw" / f"{receipt_id}.{extension}"
    normalized = base / "normalized" / f"{receipt_id}.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    normalized.parent.mkdir(parents=True, exist_ok=True)
    return raw, normalized


def _search_record(
    receipt: dict[str, Any], query_family: str, date_range: str, filters: str
) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "search_id": receipt["receipt_id"],
        "database": receipt["provider_name"],
        "query_family": query_family,
        "query": receipt["query"],
        "searched_at": receipt["completed_at"],
        "date_range": date_range,
        "filters": filters,
        "result_count": receipt["result_count"],
        "included_work_ids": [],
        "exclusion_reasons": ["Pending named human screening of the hash-bound result set."],
        "source_url": receipt["final_url"],
        "evidence_receipt_id": receipt["receipt_id"],
        "response_sha256": receipt["response_sha256"],
        "normalized_results_sha256": receipt["normalized_results_sha256"],
        "screened_by": None,
    }


def execute_search(
    project: Path,
    provider: str,
    query: str,
    *,
    query_family: str,
    date_range: str,
    filters: str,
    limit: int,
    fetcher: Callable[..., tuple[bytes, str, int | None, str | None]] = fetch_bytes,
) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise LiteratureEvidenceError(f"unsupported provider: {provider}")
    if not query.strip() or not query_family.strip() or not date_range.strip() or not filters.strip():
        raise LiteratureEvidenceError("query, query-family, date-range and filters are required")
    if not 1 <= limit <= MAX_RESULTS:
        raise LiteratureEvidenceError(f"limit must be between 1 and {MAX_RESULTS}")
    receipt_id = _receipt_id(provider)
    requested_at = utc_now()
    request_url = build_search_url(provider, query.strip(), limit)
    raw_path, normalized_path = _artifact_paths(
        project, receipt_id, "xml" if provider == "arxiv" else "json"
    )
    payload: bytes | None = None
    final_url: str | None = None
    status: int | None = None
    content_type: str | None = None
    try:
        payload, final_url, status, content_type = fetch_provider_bytes(
            fetcher, request_url, provider
        )
        raw_path.write_bytes(payload)
        normalized = normalize_search(provider, payload)
    except Exception as exc:
        failed = {
            "schema_version": "1.0",
            "receipt_id": receipt_id,
            "mode": "live_search",
            "provider": provider,
            "provider_name": DISPLAY_NAMES[provider],
            "query": query.strip(),
            "request_url": request_url,
            "requested_at": requested_at,
            "completed_at": utc_now(),
            "status": "failed",
            "error": str(exc),
        }
        if payload is not None:
            failed.update(
                {
                    "final_url": final_url,
                    "http_status": status,
                    "content_type": content_type,
                    "response_sha256": sha256_bytes(payload),
                    "raw_response_path": raw_path.relative_to(project).as_posix(),
                }
            )
        append_jsonl(project / "evidence" / "literature-api-ledger.jsonl", failed)
        raise LiteratureEvidenceError(f"{DISPLAY_NAMES[provider]} search failed: {exc}") from exc
    assert payload is not None and final_url is not None
    normalized_payload = canonical_json_bytes({"schema_version": "1.0", "works": normalized})
    normalized_path.write_bytes(normalized_payload + b"\n")
    receipt = {
        "schema_version": "1.0",
        "receipt_id": receipt_id,
        "mode": "live_search",
        "provider": provider,
        "provider_name": DISPLAY_NAMES[provider],
        "query": query.strip(),
        "request_url": request_url,
        "final_url": final_url,
        "requested_at": requested_at,
        "completed_at": utc_now(),
        "status": "success",
        "http_status": status,
        "content_type": content_type,
        "result_count": len(normalized),
        "response_sha256": sha256_bytes(payload),
        "normalized_results_sha256": sha256_bytes(normalized_payload + b"\n"),
        "raw_response_path": raw_path.relative_to(project).as_posix(),
        "normalized_results_path": normalized_path.relative_to(project).as_posix(),
    }
    append_jsonl(project / "evidence" / "literature-api-ledger.jsonl", receipt)
    append_jsonl(
        project / "evidence" / "search-log.jsonl",
        _search_record(receipt, query_family.strip(), date_range.strip(), filters.strip()),
    )
    return receipt


def _field(row: dict[str, Any], aliases: Iterable[str]) -> Any:
    by_key = {str(key).strip().lower(): value for key, value in row.items()}
    for alias in aliases:
        if alias.lower() in by_key and _text(by_key[alias.lower()]):
            return by_key[alias.lower()]
    return None


def import_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            for key in ("records", "results", "items"):
                if isinstance(value.get(key), list):
                    value = value[key]
                    break
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise LiteratureEvidenceError("JSON import must be an array of records")
        return [dict(item) for item in value]
    raise LiteratureEvidenceError("local index imports support CSV or JSON")


def execute_import(
    project: Path,
    source: str,
    relative_file: str,
    *,
    query: str,
    query_family: str,
    date_range: str,
    filters: str,
    actor: str,
) -> dict[str, Any]:
    if source not in {"wos", "scopus"}:
        raise LiteratureEvidenceError("source must be wos or scopus")
    if not actor.strip():
        raise LiteratureEvidenceError("actor is required for a licensed local export")
    if not query.strip() or not query_family.strip() or not date_range.strip() or not filters.strip():
        raise LiteratureEvidenceError("query, query-family, date-range and filters are required")
    path = safe_project_file(project, relative_file)
    rows = import_rows(path)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        work = normalized_work(
            source,
            _field(row, ("ut", "eid", "id", "accession number")),
            _field(row, ("article title", "title", "document title")),
            _field(row, ("publication year", "year", "published")),
            _field(row, ("doi", "digital object identifier")),
            _field(row, ("url", "link", "source url")),
            str(_field(row, ("authors", "author full names", "author")) or "").split(";"),
            abstract=_field(row, ("abstract",)),
            venue=_field(row, ("source title", "journal", "publication name")),
        )
        if work:
            normalized.append(work)
    receipt_id = _receipt_id(source)
    _, normalized_path = _artifact_paths(project, receipt_id, path.suffix.lstrip(".") or "dat")
    normalized_payload = canonical_json_bytes({"schema_version": "1.0", "works": normalized}) + b"\n"
    normalized_path.write_bytes(normalized_payload)
    receipt = {
        "schema_version": "1.0",
        "receipt_id": receipt_id,
        "mode": "licensed_local_export",
        "provider": source,
        "provider_name": DISPLAY_NAMES[source],
        "query": query.strip(),
        "request_url": SOURCE_URLS[source],
        "final_url": SOURCE_URLS[source],
        "requested_at": utc_now(),
        "completed_at": utc_now(),
        "status": "success",
        "result_count": len(normalized),
        "response_sha256": sha256_file(path),
        "normalized_results_sha256": sha256_bytes(normalized_payload),
        "raw_response_path": path.relative_to(project).as_posix(),
        "normalized_results_path": normalized_path.relative_to(project).as_posix(),
        "imported_by": actor.strip(),
        "rights_note": "Locally imported licensed database export; the source file is not uploaded or redistributed.",
    }
    append_jsonl(project / "evidence" / "literature-api-ledger.jsonl", receipt)
    append_jsonl(
        project / "evidence" / "search-log.jsonl",
        _search_record(receipt, query_family.strip(), date_range.strip(), filters.strip()),
    )
    return receipt


def screen_receipt(
    project: Path,
    receipt_id: str,
    included_ids: list[str],
    exclusion_reasons: list[str],
    actor: str,
) -> dict[str, Any]:
    if not SAFE_RECEIPT_RE.fullmatch(receipt_id):
        raise LiteratureEvidenceError("invalid receipt ID")
    if not actor.strip() or not exclusion_reasons or any(not item.strip() for item in exclusion_reasons):
        raise LiteratureEvidenceError("actor and at least one exclusion reason are required")
    ledger = {item.get("receipt_id"): item for item in read_jsonl(project / "evidence" / "literature-api-ledger.jsonl")}
    receipt = ledger.get(receipt_id)
    if not receipt or receipt.get("status") != "success":
        raise LiteratureEvidenceError("receipt is missing or unsuccessful")
    normalized_path = safe_project_file(project, str(receipt["normalized_results_path"]))
    normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    known = {
        str(item.get("id"))
        for item in normalized.get("works", [])
        if isinstance(item, dict) and item.get("id")
    }
    unknown = sorted(set(included_ids) - known)
    if unknown:
        raise LiteratureEvidenceError("included IDs are absent from the result set: " + ", ".join(unknown))
    log_path = project / "evidence" / "search-log.jsonl"
    records = read_jsonl(log_path)
    matches = [index for index, item in enumerate(records) if item.get("evidence_receipt_id") == receipt_id]
    if len(matches) != 1:
        raise LiteratureEvidenceError("search log must contain exactly one matching receipt")
    record = records[matches[0]]
    record["included_work_ids"] = sorted(set(included_ids))
    record["exclusion_reasons"] = [item.strip() for item in exclusion_reasons]
    record["screened_by"] = actor.strip()
    replace_jsonl(log_path, records)
    return record


def validate_search_evidence(project: Path, records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    try:
        ledger_values = read_jsonl(project / "evidence" / "literature-api-ledger.jsonl")
    except LiteratureEvidenceError as exc:
        return [str(exc)]
    ledger: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(ledger_values):
        receipt_id = item.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id:
            errors.append(f"literature ledger[{index}] has no receipt_id")
        elif receipt_id in ledger:
            errors.append(f"literature ledger repeats receipt_id {receipt_id}")
        else:
            ledger[receipt_id] = item
    for index, record in enumerate(records):
        prefix = f"search-log[{index}]"
        if record.get("schema_version") != "1.1":
            errors.append(f"{prefix} must use schema_version 1.1 with real execution evidence")
            continue
        receipt_id = record.get("evidence_receipt_id")
        receipt = ledger.get(str(receipt_id))
        if receipt is None or receipt.get("status") != "success":
            errors.append(f"{prefix} references a missing or unsuccessful evidence receipt")
            continue
        if record.get("search_id") != receipt_id:
            errors.append(f"{prefix}.search_id must equal evidence_receipt_id")
        if record.get("database") != receipt.get("provider_name"):
            errors.append(f"{prefix}.database differs from the receipt provider")
        if record.get("query") != receipt.get("query"):
            errors.append(f"{prefix}.query differs from the executed query")
        if record.get("result_count") != receipt.get("result_count"):
            errors.append(f"{prefix}.result_count differs from the receipt")
        for field in ("response_sha256", "normalized_results_sha256"):
            if record.get(field) != receipt.get(field) or not HEX64_RE.fullmatch(str(record.get(field, ""))):
                errors.append(f"{prefix}.{field} differs from the receipt")
        for path_field, hash_field in (
            ("raw_response_path", "response_sha256"),
            ("normalized_results_path", "normalized_results_sha256"),
        ):
            try:
                path = safe_project_file(project, str(receipt.get(path_field, "")))
            except LiteratureEvidenceError as exc:
                errors.append(f"{prefix}: {exc}")
                continue
            if sha256_file(path) != receipt.get(hash_field):
                errors.append(f"{prefix} {path_field} is stale or hash-mismatched")
        try:
            normalized_path = safe_project_file(project, str(receipt.get("normalized_results_path", "")))
            normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
            works = normalized.get("works", []) if isinstance(normalized, dict) else []
            known = {str(item.get("id")) for item in works if isinstance(item, dict) and item.get("id")}
        except (LiteratureEvidenceError, OSError, json.JSONDecodeError) as exc:
            errors.append(f"{prefix} cannot read normalized evidence: {exc}")
            known = set()
        included = record.get("included_work_ids")
        included_set = {str(item) for item in included} if isinstance(included, list) else set()
        unknown = sorted(included_set - known)
        if unknown:
            errors.append(f"{prefix} includes IDs absent from the executed result: {', '.join(unknown)}")
        if not isinstance(record.get("screened_by"), str) or not record["screened_by"].strip():
            errors.append(f"{prefix} requires a named human screening decision")
    return errors


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search")
    search.add_argument("--project", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--query-family", required=True)
    search.add_argument("--date-range", required=True)
    search.add_argument("--filters", required=True)
    search.add_argument("--provider", action="append", choices=PROVIDERS)
    search.add_argument("--limit", type=int, default=25)
    imported = sub.add_parser("import-index")
    imported.add_argument("--project", required=True)
    imported.add_argument("--source", choices=("wos", "scopus"), required=True)
    imported.add_argument("--file", required=True)
    imported.add_argument("--query", required=True)
    imported.add_argument("--query-family", required=True)
    imported.add_argument("--date-range", required=True)
    imported.add_argument("--filters", required=True)
    imported.add_argument("--actor", required=True)
    citation = sub.add_parser("citation")
    citation.add_argument("--project", required=True)
    citation.add_argument("--doi", required=True)
    citation.add_argument("--direction", choices=("citations", "references"), required=True)
    citation.add_argument("--date-range", required=True)
    citation.add_argument("--filters", required=True)
    screen = sub.add_parser("screen")
    screen.add_argument("--project", required=True)
    screen.add_argument("--receipt", required=True)
    screen.add_argument("--include", action="append", default=[])
    screen.add_argument("--exclusion-reason", action="append", required=True)
    screen.add_argument("--actor", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--project", required=True)
    return root


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        project = project_path(args.project)
        if args.command == "search":
            providers = args.provider or list(PROVIDERS)
            receipts = [
                execute_search(
                    project,
                    provider,
                    args.query,
                    query_family=args.query_family,
                    date_range=args.date_range,
                    filters=args.filters,
                    limit=args.limit,
                )
                for provider in providers
            ]
            print(json.dumps(receipts, ensure_ascii=False, indent=2))
        elif args.command == "import-index":
            receipt = execute_import(
                project,
                args.source,
                args.file,
                query=args.query,
                query_family=args.query_family,
                date_range=args.date_range,
                filters=args.filters,
                actor=args.actor,
            )
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
        elif args.command == "citation":
            receipt = execute_citation_graph(
                project,
                args.doi,
                args.direction,
                date_range=args.date_range,
                filters=args.filters,
            )
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
        elif args.command == "screen":
            record = screen_receipt(
                project,
                args.receipt,
                args.include,
                args.exclusion_reason,
                args.actor,
            )
            print(json.dumps(record, ensure_ascii=False, indent=2))
        else:
            records = read_jsonl(project / "evidence" / "search-log.jsonl")
            errors = validate_search_evidence(project, records)
            print(json.dumps({"status": "pass" if not errors else "block", "errors": errors}, indent=2))
            return 1 if errors else 0
    except (LiteratureEvidenceError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
