#!/usr/bin/env python3
"""Audit reference identity using actual provider evidence or legacy human records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.research_artifacts import sha as sha256_file
except ImportError:  # Direct execution from scripts/.
    from research_artifacts import sha as sha256_file

try:
    from scripts.network_safety import NetworkSafetyError, fetch_json, validate_https_url
except ModuleNotFoundError:  # Direct execution from scripts/.
    from network_safety import (  # type: ignore[no-redef]
        NetworkSafetyError,
        fetch_json,
        validate_https_url,
    )


ENTRY_RE = re.compile(r"@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
FIELD_RE = re.compile(r"(?s)^\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(.*?)\s*$")
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


def tex_source_paths(path: Path, root: Path | None=None, seen: set[Path] | None=None)->set[Path]:
    try:
        try:from scripts.tex_sources import expand
        except ModuleNotFoundError:from tex_sources import expand
        sources=set(expand(path,root=root).files)
        if seen is not None:seen.update(sources);return seen
        return sources
    except ValueError as exc:raise CitationAuditError(str(exc)) from exc


def manuscript_digest(path: Path) -> str:
    if path.suffix.lower()!=".tex":return sha256_file(path)
    digest=hashlib.sha256();root=path.parent.resolve()
    for source in sorted(tex_source_paths(path),key=lambda item:item.relative_to(root).as_posix()):
        digest.update(source.relative_to(root).as_posix().encode());digest.update(b"\0");digest.update(source.read_bytes());digest.update(b"\0")
    return digest.hexdigest()


def tex_citation_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for source in tex_source_paths(path):
        text = re.sub(r"(?m)(?<!\\)%.*$", "", source.read_text(encoding="utf-8"))
        for match in re.finditer(r"\\(?:cite|citep|citet|parencite|textcite|autocite|citeauthor|citeyear|citeyearpar|footcite|footcitetext)\*?(?:\[[^]]*\])*\{([^}]*)\}",text):keys.update(key.strip() for key in match.group(1).split(",") if key.strip())
    return keys


def docx_citation_keys(path: Path) -> tuple[set[str], list[str]]:
    """Map explicit bibliography keys; unsupported formatted citations fail closed."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    text = "\n".join("".join(p.itertext()) for p in root.findall(".//w:p", ns))
    keys = {key for group in re.findall(r"\[[^\]]*@[^\]]+\]", text)
            for key in re.findall(r"@([A-Za-z0-9_:.+/-]+)", group)}
    instructions = ["".join(node.text or "" for node in paragraph.findall(".//w:instrText", ns))
                    for paragraph in root.findall(".//w:p", ns)]
    instructions.extend(node.get("{" + ns["w"] + "}instr", "") for node in root.findall(".//w:fldSimple", ns))
    errors = []
    for instruction in instructions:
        keys.update(re.findall(r"\bCITATION\s+([A-Za-z0-9_:.+/-]+)", instruction))
        if re.search(r"\bCITATION\s", instruction):
            keys.update(re.findall(r"\\m\s+([A-Za-z0-9_:.+/-]+)", instruction))
        if "CSL_CITATION" in instruction:
            errors.append("unsupported CSL citation keys require an explicit bibliography mapping")
    if not keys:
        errors.append("DOCX has no explicit citation-key mapping; retain [@key] markers or Word CITATION fields")
    if re.search(r"\[\d+(?:\s*[,–-]\s*\d+)*\]", text):
        errors.append("numeric DOCX citations require an explicit bibliography-key mapping")
    return keys, errors


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
        # Commas inside braced or quoted values do not separate fields.
        segments: list[str] = []
        start = nested = 0
        quoted = escaped = False
        for pos, char in enumerate(body):
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
            elif char == '"' and nested == 0:
                quoted = not quoted
            elif not quoted and char == "{":
                nested += 1
            elif not quoted and char == "}":
                nested -= 1
            elif char == "," and nested == 0 and not quoted:
                segments.append(body[start:pos])
                start = pos + 1
        segments.append(body[start:])
        for segment in segments:
            if not segment.strip():
                continue
            field = FIELD_RE.fullmatch(segment)
            if not field:
                depth = 1
                continue
            value = field.group(2).strip()
            if len(value) >= 2 and ((value[0] == "{" and value[-1] == "}") or (value[0] == '"' and value[-1] == '"')):
                value = value[1:-1]
            elif not re.fullmatch(r"\d+", value):
                # Macro expansion and concatenation need a full BibTeX engine;
                # fail closed rather than treating them as literal metadata.
                depth = 1
            fields[field.group(1).lower()] = value.strip()
        if nested != 0 or quoted:
            depth = 1
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


def _metadata_cache_directory(bib_path: Path) -> Path | None:
    projects = (Path(__file__).resolve().parents[1] / "projects").resolve()
    resolved = bib_path.resolve()
    if resolved.is_relative_to(projects):
        parts = resolved.relative_to(projects).parts
        if len(parts) >= 2:
            return projects / parts[0] / "state/citation-metadata"
    return None


def cached_crossref_record(doi: str, fetcher: Callable[..., Any], cache_directory: Path | None,
                          *, refresh: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cache public metadata for 24h; never cache a bibliography PASS decision."""
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    target = cache_directory / (hashlib.sha256(url.encode()).hexdigest() + ".json") if cache_directory else None
    if target is not None:
        if any(p.is_symlink() for p in (target, *target.parents)):
            raise CitationAuditError("citation metadata cache cannot use symlinks")
        if target.is_file() and not refresh:
            try:
                value = json.loads(target.read_text(encoding="utf-8"))
                age = datetime.now(timezone.utc) - datetime.fromisoformat(value["retrieved_at"])
                encoded = json.dumps(value["record"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
                if (value.get("schema_version") == "1.0" and value.get("url") == url
                        and value.get("doi") == doi and isinstance(value["record"], dict)
                        and timedelta(0) <= age < timedelta(hours=24)
                        and hashlib.sha256(encoded).hexdigest() == value["record_sha256"]):
                    return value["record"], {"source_url": url, "retrieved_at": value["retrieved_at"],
                                              "record_sha256": value["record_sha256"], "cache_hit": True}
            except (OSError, ValueError, TypeError, KeyError):
                pass
    record = crossref_record(doi, fetcher)
    digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    receipt = {"schema_version": "1.0", "doi": doi, "url": url, "retrieved_at": now(),
               "record_sha256": digest, "record": record}
    if target is not None:
        try:
            from scripts.research_artifacts import write
        except ModuleNotFoundError:
            from research_artifacts import write  # type: ignore
        write(target, receipt)
    return record, {"source_url": url, "retrieved_at": receipt["retrieved_at"],
                    "record_sha256": digest, "cache_hit": False}


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


def _identity_text(value: str) -> str:
    """Conservative Unicode tokens; identity matching is never fuzzy."""
    return " ".join(re.findall(r"[^\W_]+", re.sub(r"[{}\\]", "", value).casefold(), re.UNICODE))


def _bib_authors(value: str) -> list[str]:
    names = []
    for author in re.split(r"\s+and\s+", value.strip(), flags=re.IGNORECASE):
        parts = [part.strip() for part in author.split(",")]
        if not author.strip() or len(parts) > 2 or _identity_text(author) == "others":
            return []
        names.append(_identity_text(" ".join(reversed(parts))))
    return names if all(names) else []


def _bibliography_project(bib_path: Path) -> Path | None:
    path = bib_path.absolute()
    if (path.parent.name == "manuscript" and re.fullmatch(r"P[0-9]{2}", path.parent.parent.name)
            and path.parent.parent.parent.name == "papers"):
        return path.parent.parent.parent.parent
    return None


def provider_identity(bib_path: Path, fields: dict[str, str], *, selection: dict | None = None) -> dict:
    """Recheck a no-DOI identity against executed official metadata, offline.

    The receipt proves bibliographic identity only. It is not a licence,
    scientific claim-support finding, or substitute for original-source reading.
    """
    try:
        try:
            from scripts import literature_evidence as evidence, output_provenance
            from scripts.research_artifacts import path_in, read
        except ImportError:
            import literature_evidence as evidence
            import output_provenance
            from research_artifacts import path_in, read
        project = _bibliography_project(bib_path)
        if project is None:
            raise ValueError("provider identity needs a canonical papers/Pxx/manuscript bibliography")
        path_in(project, bib_path.absolute().relative_to(project).as_posix())
        title, year, authors = _identity_text(fields.get("title", "")), fields.get("year", ""), _bib_authors(fields.get("author", ""))
        if not title or not re.fullmatch(r"[0-9]{4}", year) or not authors:
            raise ValueError("no-DOI identity needs an exact title, four-digit year and complete ordered authors")
        arxiv = fields.get("eprint", "").removeprefix("arXiv:").strip()
        if arxiv and not evidence.ARXIV_IDENTIFIER_RE.fullmatch(arxiv):
            raise ValueError("unsupported arXiv identifier")
        url = fields.get("url", "").strip()
        if url:
            validate_https_url(url, "bibliographic source URL")
        if not url and not arxiv:
            raise ValueError("no-DOI identity needs an exact source URL or arXiv identifier")
        receipt_id, work_id = fields.get("evidence_receipt_id"), fields.get("evidence_work_id")
        if selection is not None:
            if receipt_id and (receipt_id, work_id) != (selection.get("receipt_id"), selection.get("work_id")):
                raise ValueError("saved bibliographic receipt differs from the explicit bibliography selection")
            receipt_id, work_id = selection.get("receipt_id"), selection.get("work_id")
        if bool(receipt_id) != bool(work_id):
            raise ValueError("evidence_receipt_id and evidence_work_id must be supplied together")
        if receipt_id and not evidence.SAFE_RECEIPT_RE.fullmatch(receipt_id):
            raise ValueError("invalid bibliographic receipt identifier")
        ledger = path_in(project, "evidence/literature-api-ledger.jsonl")

        def owned(path):
            if path.stat().st_size > evidence.MAX_RESPONSE_BYTES:
                raise ValueError("bibliographic source exceeds its bounded evidence size")
            origin = output_provenance.current_origin(project, path)
            if (origin.get("status") != "tracked" or origin.get("family") != "other"
                    or origin.get("provider") != "deterministic-control-plane"
                    or origin.get("model") != "scripts/literature_evidence.py"):
                raise ValueError("bibliographic evidence lacks current acquisition-controller provenance")

        owned(ledger)
        receipts = evidence.read_jsonl(ledger)
        ids = [row.get("receipt_id") for row in receipts]
        if len(ids) != len(set(ids)):
            raise ValueError("bibliographic receipt identifiers are ambiguous")
        if receipt_id:
            receipts = [row for row in receipts if row.get("receipt_id") == receipt_id]
            if len(receipts) != 1:
                raise ValueError("selected bibliographic receipt is missing or ambiguous")
        candidates, blockers = {}, []
        for receipt in receipts:
            provider = receipt.get("provider")
            if receipt.get("status") != "success" or receipt.get("mode") != "live_search" or provider not in evidence.DEFAULT_SEARCH_PROVIDERS:
                continue
            try:
                expected_url = evidence.build_search_url(provider, receipt["query"], 1,
                    date_range=receipt["declared_date_range"], filters=receipt["declared_filters"])
                expected = urllib.parse.urlsplit(expected_url)
                for source_url in (receipt["request_url"], receipt["final_url"]):
                    validate_https_url(source_url, "executed provider URL")
                    parsed = urllib.parse.urlsplit(source_url)
                    if (parsed.scheme, parsed.hostname, parsed.port, parsed.path) != (expected.scheme, expected.hostname, expected.port, expected.path):
                        raise ValueError("bibliographic receipt does not identify its official metadata endpoint")
                if receipt.get("http_status") != 200:
                    raise ValueError("bibliographic receipt lacks a successful HTTP response")
                raw_relative, normalized_relative = receipt["raw_response_path"], receipt["normalized_results_path"]
                if not raw_relative.startswith("evidence/literature/raw/") or not normalized_relative.startswith("evidence/literature/normalized/"):
                    raise ValueError("bibliographic evidence is outside protected acquisition paths")
                raw, normalized = path_in(project, raw_relative), path_in(project, normalized_relative)
                for path, expected_hash in ((raw, receipt["response_sha256"]), (normalized, receipt["normalized_results_sha256"])):
                    owned(path)
                    if sha256_file(path) != expected_hash:
                        raise ValueError("bibliographic provider evidence changed")
                works = read(normalized).get("works")
                replayed, _ = evidence.filter_results(provider, evidence.normalize_search(provider, raw.read_bytes()),
                    evidence.parse_conditions(receipt["declared_date_range"], receipt["declared_filters"]))
                if not isinstance(works, list) or works != replayed or len(works) != receipt.get("result_count"):
                    raise ValueError("normalized bibliographic metadata does not replay from the original response")
                for work in works:
                    if work_id and work.get("id") != work_id:
                        continue
                    work_authors = work.get("authors", [])
                    source_matches = bool(url and work.get("primary_source_url") == url)
                    if arxiv:
                        parsed_url = urllib.parse.urlsplit(url)
                        source_matches = work.get("arxiv_id") == arxiv and (not url or (
                            parsed_url.hostname == "arxiv.org" and parsed_url.path in {
                                "/abs/" + arxiv, "/pdf/" + arxiv, "/pdf/" + arxiv + ".pdf"}))
                    if (work.get("doi") or not source_matches or _identity_text(work.get("title", "")) != title
                            or work.get("publication_year") != int(year) or not isinstance(work_authors, list)
                            or any(not isinstance(name, str) for name in work_authors)
                            or [_identity_text(name) for name in work_authors] != authors):
                        continue
                    identity = {"kind": "automated_bibliographic_identity", "receipt_id": receipt["receipt_id"],
                        "receipt_sha256": hashlib.sha256(evidence.canonical_json_bytes(receipt)).hexdigest(),
                        "work_id": work["id"], "provider": provider, "ledger_path": "evidence/literature-api-ledger.jsonl",
                        "raw": {"path": raw_relative, "sha256": receipt["response_sha256"]},
                        "normalized": {"path": normalized_relative, "sha256": receipt["normalized_results_sha256"]},
                        "title": work["title"], "year": work["publication_year"], "authors": work_authors,
                        "source_url": work.get("primary_source_url"), "arxiv_id": work.get("arxiv_id"),
                        "human_verification": False, "claim_support_verified": False, "rights_verified": False}
                    candidates.setdefault(work["id"], identity)
            except (OSError, ValueError, KeyError, TypeError, evidence.LiteratureEvidenceError) as exc:
                blockers.append(str(exc))
        if len(candidates) != 1:
            detail = "; ".join(sorted(set(blockers))[:3])
            raise ValueError("no unique matching executed bibliographic identity" + (": " + detail if detail else ""))
        return next(iter(candidates.values()))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        raise CitationAuditError("source-bound bibliographic identity: " + str(exc)) from exc


def validate_provider_identities(bib_path: Path, report: dict) -> list[str]:
    """Invalidate saved automatic identity results when their sources change."""
    errors = []
    try:
        entries = {entry["key"]: entry for entry in parse_bibtex(bib_path.read_text(encoding="utf-8"))}
        for finding in report.get("findings", []):
            if not isinstance(finding, dict):
                raise CitationAuditError("citation findings must be records")
            if finding.get("status") != "verified_provider_identity":
                continue
            stored = finding.get("provider_identity")
            if not isinstance(stored, dict):
                raise CitationAuditError("automatic citation identity receipt is missing")
            entry = entries.get(finding.get("citation_key"))
            if entry is None or provider_identity(bib_path, entry["fields"], selection=stored) != stored:
                raise CitationAuditError("saved automatic bibliographic identity is stale")
    except (OSError, ValueError, KeyError, TypeError, CitationAuditError) as exc:
        errors.append(str(exc))
    return errors


def audit(
    bib_path: Path,
    *,
    manual_path: Path | None = None,
    offline: bool = False,
    docx_verified_by: str | None = None,
    fetcher: Callable[..., Any] = fetch_json,
    cache_directory: Path | None = None,
    refresh_metadata: bool = False,
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
                    record, metadata_receipt = cached_crossref_record(doi, fetcher, cache_directory,
                                                                       refresh=refresh_metadata)
                    result["metadata_receipt"] = metadata_receipt
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
        else:
            try:
                identity = provider_identity(bib_path, fields)
                result["provider_identity"] = identity
                if not result["issues"]:
                    result["status"] = "verified_provider_identity"
            except CitationAuditError as exc:
                if key in manual:
                    verification = manual[key]
                    similarity = title_similarity(title, verification["title"])
                    result["manual_verification"] = verification
                    if similarity < 0.75:
                        result["issues"].append("title does not match the manual verification record")
                    elif not result["issues"]:
                        result["status"] = "verified_manual"
                else:
                    result["issues"].append(str(exc))
        findings.append(result)
    unresolved = [item["citation_key"] for item in findings if not item["status"].startswith("verified_")]
    bibliography_keys = {entry["key"] for entry in entries}
    tex_path = bib_path.parent / "main.tex"
    docx_path = bib_path.parent / "main.docx"
    manuscript_path = tex_path if tex_path.is_file() else docx_path if docx_path.is_file() else None
    usage_errors = []
    if tex_path.is_file():
        cited_keys = tex_citation_keys(tex_path)
    elif docx_path.is_file():
        cited_keys, usage_errors = docx_citation_keys(docx_path)
    else:
        cited_keys = set()
    unresolved.extend("usage:" + error for error in usage_errors)
    missing_citations = sorted(cited_keys - bibliography_keys)
    if missing_citations:
        unresolved.extend(f"missing:{key}" for key in missing_citations)
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "bibliography": str(bib_path),
        "bibliography_sha256": sha256_file(bib_path),
        "manuscript": str(manuscript_path) if manuscript_path else None,
        "manuscript_sha256": manuscript_digest(manuscript_path) if manuscript_path else None,
        "offline": offline,
        "entry_count": len(entries),
        "verified_count": sum(item["status"].startswith("verified_") for item in findings),
        "unresolved_count": len(unresolved),
        "unresolved_keys": unresolved,
        "status": "pass" if entries and not unresolved else "fail",
        "citation_usage": {
            "status": (
                "checked_automatically" if (tex_path.is_file() or docx_path.is_file()) and not usage_errors
                else "mapping_required" if docx_path.is_file()
                else "no_manuscript_found"
            ),
            "verified_by": docx_verified_by.strip() if isinstance(docx_verified_by,str) and docx_verified_by.strip() else None,
            "verified_at": now() if docx_path.is_file() and isinstance(docx_verified_by,str) and docx_verified_by.strip() else None,
            "cited_keys": sorted(cited_keys),
            "missing_bibliography_keys": missing_citations,
            "unused_bibliography_keys": sorted(bibliography_keys - cited_keys)
            if tex_path.is_file()
            else [],
            "mapping_errors": usage_errors,
            "note": "Explicit citation keys checked against the bibliography; unsupported DOCX formats remain unresolved.",
        },
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bibliography", type=Path)
    parser.add_argument("--manual-verifications", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--refresh-metadata", action="store_true", help="Bypass the 24h metadata cache when checking changed publisher metadata")
    parser.add_argument("--cache-metadata", action="store_true", help="Control-plane use only: save hash-bound public metadata under project state")
    parser.add_argument("--docx-citations-verified-by",help="Named human who checked every DOCX in-text citation against the bibliography")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(
            args.bibliography,
            manual_path=args.manual_verifications,
            offline=args.offline,
            docx_verified_by=args.docx_citations_verified_by,
            refresh_metadata=args.refresh_metadata,
            cache_directory=_metadata_cache_directory(args.bibliography) if args.cache_metadata else None,
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
