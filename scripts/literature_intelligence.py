"""Cloud-only, deterministic literature discovery and provisional topic leads.

Public interface: discover(project, plan_path='program/literature-plan.json',
output='program/topic-leads.json', *, fetcher=None). A v1 plan contains an
explicit doctoral_question, topic_keywords, optional exclude_keywords, searches
and/or conferences ({venue: 'conf/icml', year, limit, offset, enrich_limit}),
optional receipt IDs, as_of (ISO date), max_requests (0..20), cache_max_age_days
(0..30). Search entries mirror literature_evidence.execute_search arguments.

Pure helpers canonical_identity, canonical_match, deduplicate and rank_candidates
are usable without network/model calls. Rhetorical markers and citation counts
are discovery heuristics, never assessments of research quality or novelty.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import unicodedata

from scripts import literature_evidence as evidence
from scripts.research_artifacts import path_in, read, record, sha, write

PLAN = "program/literature-plan.json"
OUTPUT = "program/topic-leads.json"
RHETORIC = {
    "problem_or_limitation": ("however", "remains challenging", "remain challenging", "limitation", "open question", "little is known"),
    "author_contribution": ("we propose", "we introduce", "we present", "our approach", "our method"),
    "reported_evaluation": ("experiment", "evaluation", "benchmark", "results show", "we evaluate"),
    "reported_novelty_or_performance": ("state-of-the-art", "state of the art", "SOTA", "first", "novel",
        "outperform", "outperforms", "outperformed", "surpass", "surpasses", "accuracy", "ablation", "ablations"),
}
# Exact source-container labels only. ICML's generic PMLR container is not
# sufficient to establish conference membership and is deliberately unmapped.
CONFERENCE_FALLBACK_VENUES = {
    "https://dblp.org/streams/conf/aaai": "Proceedings of the AAAI Conference on Artificial Intelligence",
    "https://dblp.org/streams/conf/cvpr": "{year} IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)",
    "https://dblp.org/streams/conf/iccv": "{year} IEEE/CVF International Conference on Computer Vision (ICCV)",
}


def conference_fallback(conference: dict, venue: str, year: int) -> dict | None:
    """A separate bounded source query, never a DBLP success or full corpus."""
    supplied = conference.get("fallback")
    if supplied is False:
        return None
    if supplied is None:
        label = CONFERENCE_FALLBACK_VENUES.get(venue)
        if label is None:
            return None
        provider, label = "crossref", label.format(year=year)
    else:
        if (not isinstance(supplied, dict) or set(supplied) != {"provider", "venue"}
                or supplied.get("provider") not in {"crossref", "openalex"}
                or not isinstance(supplied.get("venue"), str) or not 1 <= len(supplied["venue"].strip()) <= 300):
            raise ValueError("conference fallback needs Crossref/OpenAlex and an explicit exact source venue label")
        provider, label = supplied["provider"], supplied["venue"].strip()
    return {"provider": provider, "query": label, "query_family": "conference-fallback-not-dblp",
            "date_range": str(year), "filters": {"venue": label, "year": year},
            "limit": conference.get("limit", 100)}


def _normal(value) -> str:
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", str(value or "")).casefold()))


def _doi(work) -> str | None:
    return evidence._doi(work.get("doi"))


def _arxiv(work) -> tuple[str | None, str | None]:
    for value in (work.get("arxiv_id"), work.get("primary_source_url"), work.get("provider_id"), work.get("id")):
        value = str(value or "")
        value = re.sub(r"^https?://(?:www\.)?arxiv.org/(?:abs|pdf)/", "", value, flags=re.I)
        value = re.sub(r"^(?:arxiv(?:-id)?:)", "", value, flags=re.I).removesuffix(".pdf")
        match = evidence.ARXIV_IDENTIFIER_RE.fullmatch(value)
        if match:
            versioned = match[1].casefold()
            return re.sub(r"v[0-9]+$", "", versioned), versioned
    doi = _doi(work)
    if doi and doi.startswith("10.48550/arxiv."):
        versioned = doi.removeprefix("10.48550/arxiv.")
        return re.sub(r"v[0-9]+$", "", versioned), versioned
    return None, None


def _authors(work) -> set[str]:
    authors = work.get("authors", [])
    return {_normal(value.get("name") or value.get("display_name")) if isinstance(value, dict) else _normal(value)
            for value in authors if isinstance(value, (str, dict))} - {""}


def canonical_identity(work: dict) -> str:
    """Prefer DOI, then arXiv family, then exact normalized title AND authors."""
    if _doi(work):
        return "doi:" + _doi(work)
    arxiv, _ = _arxiv(work)
    if arxiv:
        return "arxiv:" + arxiv
    title, authors = _normal(work.get("title")), sorted(_authors(work))
    if title and authors:
        return "title-author:" + hashlib.sha256(json.dumps([title, authors], ensure_ascii=False).encode()).hexdigest()[:24]
    # Provider identity disambiguates sparse records; equal titles alone do not.
    sparse = [work.get("provider"), work.get("provider_id"), work.get("id"), title, work.get("source_refs", [])]
    return "unresolved:" + hashlib.sha256(json.dumps(sparse, sort_keys=True).encode()).hexdigest()[:24]


def canonical_match(left: dict, right: dict) -> bool:
    """Conservative enrichment/dedup match. A title-only similarity never passes."""
    left_doi, right_doi = _doi(left), _doi(right)
    if left_doi and right_doi:
        return left_doi == right_doi
    left_arxiv, _ = _arxiv(left)
    right_arxiv, _ = _arxiv(right)
    if left_arxiv and right_arxiv:
        return left_arxiv == right_arxiv
    return bool(_normal(left.get("title")) and _normal(left.get("title")) == _normal(right.get("title"))
                and _authors(left).intersection(_authors(right)))


def deduplicate(works: list[dict]) -> list[dict]:
    """Keep source observations, versions and disagreements when identities join."""
    if len(works) > 2000:
        raise ValueError("narrow discovery to at most 2000 retrieved records")
    groups = []
    for work in works:
        target = next((group for group in groups if any(canonical_match(work, item) for item in group)
                       and len({_doi(item) for item in [work, *group] if _doi(item)}) <= 1), None)
        if target is None:
            groups.append([work])
        else:
            target.append(work)
    results = []
    for group in groups:
        # Prefer actual abstract/identity metadata, retaining every observed value.
        richest = sorted(group, key=lambda row: (-int(bool(_doi(row))), -int(bool(row.get("abstract"))),
                                                 -int((re.search(r"v([0-9]+)$", _arxiv(row)[1] or "") or [None, "0"])[1]),
                                                 -len(_authors(row)), canonical_identity(row)))[0]
        merged = dict(richest)
        refs, versions, observations, conflicts = [], set(), [], []
        for item in group:
            for ref in item.get("source_refs", []):
                if ref not in refs:
                    refs.append(ref)
            _, version = _arxiv(item)
            if version:
                versions.add(version)
            observations.append({key: item.get(key) for key in ("provider", "provider_id", "doi", "arxiv_id", "title",
                "publication_year", "publication_date", "authors", "venue", "citation_count", "abstract")})
            for key in ("abstract", "publication_date", "venue", "arxiv_id", "citation_count"):
                if not merged.get(key) and item.get(key) is not None:
                    merged[key] = item[key]
        for key in ("publication_year", "title", "doi"):
            values = sorted({str(item[key]) for item in group if item.get(key) is not None})
            if len(values) > 1:
                conflicts.append({"field": key, "values": values, "resolution": "requires_source_review"})
        merged.update(canonical_id=canonical_identity(merged), source_refs=refs, arxiv_versions=sorted(versions),
                      source_observations=observations, metadata_conflicts=conflicts, duplicate_count=len(group) - 1)
        results.append(merged)
    # Shared titles or arXiv IDs with conflicting DOIs remain separate, visible leads.
    for index, left in enumerate(results):
        for right in results[index + 1:]:
            if _doi(left) and _doi(right) and _doi(left) != _doi(right) and (
                (_arxiv(left)[0] and _arxiv(left)[0] == _arxiv(right)[0]) or
                (_normal(left.get("title")) == _normal(right.get("title")) and _authors(left).intersection(_authors(right)))):
                for item, other in ((left, right), (right, left)):
                    item["metadata_conflicts"].append({"field": "identity", "other_id": other["canonical_id"],
                        "resolution": "conflicting_DOIs_not_automatically_merged"})
    return sorted(results, key=lambda row: row["canonical_id"])


def _keywords(value, field, *, required=False) -> list[str]:
    if not isinstance(value, list) or len(value) > 40 or (required and not value):
        raise ValueError(field + " needs an explicit list of at most 40 phrases")
    if any(not isinstance(item, str) or not 1 <= len(item.strip()) <= 120 for item in value):
        raise ValueError("invalid " + field)
    return sorted(set(item.strip() for item in value), key=str.casefold)


def _contains(text: str, phrase: str) -> bool:
    text, phrase = _normal(text), _normal(phrase)
    return bool(phrase and (phrase in text if re.search(r"[\u3400-\u9fff]", phrase) else f" {phrase} " in f" {text} "))


def _preferences(plan: dict) -> dict:
    weights = {"topic_relevance": 6, "recency": 1, "citation_visibility": 1, "abstract_rhetoric": 1, "interest_feedback": 0}
    supplied = plan.get("ranking_weights", {})
    if not isinstance(supplied, dict) or set(supplied) - set(weights):
        raise ValueError("ranking_weights contains an unknown discovery signal")
    for name, value in supplied.items():
        if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 10:
            raise ValueError("discovery weights must be finite numbers 0..10")
        weights[name] = value
    if not weights["topic_relevance"]:
        raise ValueError("topic relevance must retain a positive weight")
    feedback = plan.get("feedback", [])
    if not isinstance(feedback, list) or len(feedback) > 200:
        raise ValueError("feedback needs at most 200 explicit user records")
    seen = set()
    for row in feedback:
        if (not isinstance(row, dict) or not isinstance(row.get("candidate_id"), str) or not row["candidate_id"]
                or row["candidate_id"] in seen or row.get("interest") not in {"interested", "not_interested", "neutral"}
                or not isinstance(row.get("recorded_by"), str) or not row["recorded_by"].strip()
                or not isinstance(row.get("reason"), str) or not row["reason"].strip()):
            raise ValueError("feedback needs a unique candidate ID, explicit interest, named recorder and reason")
        try:
            stamp = datetime.fromisoformat(str(row.get("recorded_at", "")).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("feedback needs a timezone")
        except ValueError as exc:
            raise ValueError("feedback requires an actual timezone-aware recorded_at") from exc
        seen.add(row["candidate_id"])
    return {"topic_keywords": _keywords(plan.get("topic_keywords"), "topic_keywords", required=True),
            "exclude_keywords": _keywords(plan.get("exclude_keywords", []), "exclude_keywords"),
            "ranking_weights": weights, "feedback": feedback, "autonomous_preference_changes": False}


def rank_candidates(works: list[dict], plan: dict) -> list[dict]:
    preferences = _preferences(plan)
    keywords, exclusions, weights = (preferences[key] for key in ("topic_keywords", "exclude_keywords", "ranking_weights"))
    feedback = {row["candidate_id"]: row for row in preferences["feedback"]}
    current = date.fromisoformat(plan.get("as_of") or datetime.now(timezone.utc).date().isoformat())
    ranked = []
    for work in works:
        title, abstract = str(work.get("title") or ""), str(work.get("abstract") or "")
        matches = [{"keyword": term, "title": _contains(title, term), "abstract": _contains(abstract, term)} for term in keywords]
        matches = [item for item in matches if item["title"] or item["abstract"]]
        excluded = [term for term in exclusions if _contains(title + " " + abstract, term)]
        rhetoric = []
        for kind, markers in RHETORIC.items():
            for marker in markers:
                match = re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", abstract, re.I)
                if match:
                    rhetoric.append({"kind": kind, "marker": marker, "field": "abstract",
                                     "start_char": match.start(), "end_char": match.end(), "quote": abstract[match.start():match.end()]})
        year, citations = work.get("publication_year"), work.get("citation_count")
        year_known = type(year) is int and year <= current.year
        citation_known = type(citations) is int and citations >= 0
        interest = feedback.get(work.get("canonical_id") or canonical_identity(work))
        interest_value = {"interested": 1, "not_interested": -1, "neutral": 0}.get((interest or {}).get("interest"), 0)
        components = {"topic_relevance": round(sum(2 if item["title"] else 1 for item in matches) / (2 * len(keywords)) * weights["topic_relevance"], 6),
                      "recency": round(max(0, 1 - (current.year - year) / 10) * weights["recency"], 6) if year_known else 0,
                      "citation_visibility": round(min(1, math.log1p(citations) / math.log1p(1000)) * weights["citation_visibility"], 6) if citation_known else 0,
                      "abstract_rhetoric": round(len({item["kind"] for item in rhetoric}) / len(RHETORIC) * weights["abstract_rhetoric"], 6),
                      "interest_feedback": interest_value * weights["interest_feedback"]}
        unknowns = [message for flag, message in ((not abstract, "abstract_unavailable"), (not year_known, "publication_year_unknown_or_future"),
                    (not citation_known, "citation_count_unknown")) if flag]
        ranked.append({**work, "score": round(sum(components.values()), 6), "score_components": components,
                       "keyword_matches": matches, "exclusion_matches": excluded, "rhetoric_indicators": rhetoric,
                       "reading_candidate": bool(matches) and not excluded and interest_value >= 0,
                       "interest_feedback": interest, "unknowns": unknowns,
                       "ranking_meaning": "DISCOVERY_HEURISTIC_NOT_RESEARCH_QUALITY",
                       "scientific_inclusion_decided": False, "novelty_verified": False})
    return sorted(ranked, key=lambda row: (not row["reading_candidate"], -row["score"], row.get("canonical_id") or canonical_identity(row)))


def _scope(project: Path, question: str) -> dict:
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
        raise ValueError("discovery requires an explicit doctoral_question")
    core = path_in(project, "program/core-thesis.json", exists=False)
    current = read(core) if core.is_file() else {}
    actual = current.get("doctoral_question")
    unassigned = {"", "unassigned", "tbd", "not selected", "not yet selected", "pending"}
    if isinstance(actual, str) and actual.strip().casefold() not in unassigned:
        if question.strip() != actual.strip():
            raise ValueError("discovery scope differs from the current doctoral question; G1/G2 human review is required")
        return {"doctoral_question": actual.strip(), "scope_status": "current_question_bound_requires_scientific_review",
                "core_thesis": {"path": "program/core-thesis.json", "sha256": sha(core)}}
    return {"doctoral_question": question.strip(), "scope_status": "proposed_requires_G1_review",
            "core_thesis": {"path": "program/core-thesis.json", "sha256": sha(core)} if core.is_file() else None}


def _receipt_works(project: Path, receipt: dict) -> tuple[list[dict], dict]:
    if receipt.get("status") != "success":
        raise ValueError("cannot reuse an unsuccessful literature receipt")
    refs = {"receipt_id": receipt["receipt_id"], "provider": receipt["provider"], "completed_at": receipt.get("completed_at"),
            "query": receipt.get("query"), "actual_conditions": receipt.get("actual_conditions"),
            "filtered_out_count": receipt.get("filtered_out_count"), "unresolved_filter_count": receipt.get("unresolved_filter_count")}
    for path_key, hash_key in (("raw_response_path", "response_sha256"), ("normalized_results_path", "normalized_results_sha256")):
        source = path_in(project, receipt[path_key])
        if sha(source) != receipt.get(hash_key):
            raise ValueError("stale literature receipt: " + receipt["receipt_id"])
        refs[path_key], refs[hash_key] = receipt[path_key], receipt[hash_key]
    normalized = read(path_in(project, receipt["normalized_results_path"]))
    works = normalized.get("works")
    if not isinstance(works, list) or len(works) != receipt.get("result_count"):
        raise ValueError("literature receipt result count differs from its source")
    return [{**work, "source_refs": [{**refs, "locator": f"works[{index}]"}]} for index, work in enumerate(works)], refs


def discover(project: Path, plan_path: str = PLAN, output: str = OUTPUT, *, fetcher=None) -> dict:
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise RuntimeError("literature intelligence runs only on the declared cloud executor")
    if output != OUTPUT:
        raise ValueError("topic leads must use program/topic-leads.json")
    plan_source = path_in(project, plan_path)
    plan = read(plan_source)
    if plan.get("schema_version") != "1.0":
        raise ValueError("unsupported literature intelligence plan")
    scope = _scope(project, plan.get("doctoral_question"))
    preferences = _preferences(plan)
    preference_hash = evidence.sha256_bytes(evidence.canonical_json_bytes(preferences))
    plan_hash = sha(plan_source)
    as_of = date.fromisoformat(plan.get("as_of") or datetime.now(timezone.utc).date().isoformat())
    maximum, max_age = plan.get("max_requests", 12), plan.get("cache_max_age_days", 7)
    if type(maximum) is not int or not 0 <= maximum <= 20 or type(max_age) is not int or not 0 <= max_age <= 30:
        raise ValueError("metadata requests need max_requests 0..20 and cache_max_age_days 0..30")
    searches, conferences, requested = plan.get("searches", []), plan.get("conferences", []), plan.get("receipts", [])
    if any(not isinstance(rows, list) or len(rows) > 20 for rows in (searches, conferences, requested)):
        raise ValueError("discovery lists are bounded to twenty entries each")
    if any(not isinstance(item, dict) for item in [*searches, *conferences]):
        raise ValueError("searches and conferences require explicit operation objects")
    if not any((searches, conferences, requested)):
        raise ValueError("discovery needs explicit searches, conferences or existing receipts")
    ledger = evidence.read_jsonl(project / "evidence/literature-api-ledger.jsonl")
    prior_requests = sum(row.get("request_context", {}).get("plan_sha256") == plan_hash
                         for row in ledger if isinstance(row.get("request_context"), dict))
    now = datetime.fromisoformat(evidence.utc_now().replace("Z", "+00:00"))
    calls, source_receipts, works, errors, enrichment, conference_sources = 0, {}, [], [], [], []

    def consume(receipt):
        rows, reference = _receipt_works(project, receipt)
        source_receipts[receipt["receipt_id"]] = reference
        return rows

    def search(item):
        nonlocal calls
        provider = item.get("provider")
        if provider not in evidence.DEFAULT_SEARCH_PROVIDERS:
            raise ValueError("only bounded public metadata providers are enabled")
        query, limit = item.get("query"), item.get("limit", 25)
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("search needs a bounded query and limit 1..100")
        family = item.get("query_family", "topic-discovery")
        if not isinstance(family, str) or not family.strip():
            raise ValueError("search needs an explicit query family")
        dates, filters = item.get("date_range", "all years"), item.get("filters", "none")
        url = evidence.build_search_url(provider, query, limit, date_range=dates, filters=filters)
        parsed = evidence.parse_conditions(dates, filters)
        cached = None
        for receipt in reversed(ledger):
            if receipt.get("request_url") == url and receipt.get("status") == "failed":
                try:
                    stamp = datetime.fromisoformat(receipt["completed_at"].replace("Z", "+00:00"))
                    if timedelta(0) <= now - stamp < timedelta(hours=6):
                        raise evidence.LiteratureEvidenceError("recent provider failure is in a six-hour cooldown; inspect the retained receipt")
                except (KeyError, ValueError):
                    pass
            if receipt.get("status") != "success" or receipt.get("request_url") != url or receipt.get("provider") != provider:
                continue
            # Old receipts do not attest that structured constraints were applied.
            if parsed["constraints"] != receipt.get("actual_conditions", {}).get("constraints", {}):
                continue
            try:
                stamp = datetime.fromisoformat(receipt["completed_at"].replace("Z", "+00:00")).date()
                if not 0 <= (now.date() - stamp).days <= max_age:
                    continue
                consume(receipt)
                cached = receipt
                break
            except (KeyError, ValueError, OSError):
                continue
        if cached:
            return consume(cached)
        if prior_requests + calls >= maximum:
            raise ValueError("metadata request ceiling reached; remaining work is pending")
        calls += 1
        options = {"fetcher": fetcher} if fetcher is not None else {}
        try:
            receipt = evidence.execute_search(project, provider, query, query_family=family,
                date_range=dates, filters=filters, limit=limit,
                request_context={"plan_sha256": plan_hash, "operation": "literature_intelligence"}, **options)
        except (ValueError, OSError, evidence.LiteratureEvidenceError):
            ledger[:] = evidence.read_jsonl(project / "evidence/literature-api-ledger.jsonl")
            raise
        ledger.append(receipt)
        return consume(receipt)

    for identifier in requested:
        if not isinstance(identifier, str) or not evidence.SAFE_RECEIPT_RE.fullmatch(identifier):
            raise ValueError("receipts must contain exact existing receipt IDs")
        matches = [row for row in ledger if row.get("receipt_id") == identifier]
        if len(matches) != 1:
            raise ValueError("receipt is missing or ambiguous: " + identifier)
        works.extend(consume(matches[0]))
    for index, item in enumerate(searches):
        try:
            works.extend(search(item))
        except (ValueError, OSError, evidence.LiteratureEvidenceError) as exc:
            errors.append({"kind": "search", "index": index, "error": str(exc)})
    for index, conference in enumerate(conferences):
        try:
            venue, year = evidence._dblp_stream(conference["venue"]), conference["year"]
            enrich_limit = conference.get("enrich_limit", 5)
            if type(year) is not int or not 1000 <= year <= 9999 or type(enrich_limit) is not int or not 0 <= enrich_limit <= 20:
                raise ValueError("conference needs an explicit year and enrich_limit 0..20")
            fallback = conference_fallback(conference, venue, year)
            try:
                records = search({"provider": "dblp", "query": "*", "query_family": "conference-enumeration",
                    "date_range": str(year), "filters": {"venue": venue, "year": year, "offset": conference.get("offset", 0),
                        "transport": conference.get("transport", "search")},
                    "limit": conference.get("limit", 100)})
                conference_sources.append({"index": index, "venue": venue, "year": year, "provider": "dblp",
                    "status": "bounded_primary_window", "accepted_count": len(records), "complete_enumeration": False})
            except (ValueError, OSError, evidence.LiteratureEvidenceError) as exc:
                errors.append({"kind": "conference_primary", "index": index, "provider": "dblp", "error": str(exc)})
                records = []
                detail = {"index": index, "venue": venue, "year": year, "primary_provider": "dblp",
                          "primary_status": "unavailable", "database_not_dblp": True, "complete_enumeration": False}
                if fallback is None:
                    detail.update(status="pending_explicit_alternative_source", accepted_count=0)
                else:
                    detail.update(provider=fallback["provider"], exact_source_venue=fallback["filters"]["venue"])
                    try:
                        records = search(fallback)
                        detail.update(status="bounded_alternative_window", accepted_count=len(records))
                    except (ValueError, OSError, evidence.LiteratureEvidenceError) as fallback_error:
                        detail.update(status="alternative_unavailable", accepted_count=0)
                        errors.append({"kind": "conference_fallback", "index": index, "provider": fallback["provider"],
                                       "error": str(fallback_error)})
                conference_sources.append(detail)
            works.extend(records)
            for work in records[:enrich_limit]:
                identity = "DOI:" + _doi(work) if _doi(work) else None
                arxiv, _ = _arxiv(work)
                identity = identity or ("ARXIV:" + arxiv if arxiv else None)
                candidates = search({"provider": "semantic-scholar", "query": work["title"], "query_family": "conference-enrichment",
                    "filters": {"identity": identity} if identity else "none", "limit": 5})
                matched = [item for item in candidates if canonical_match(work, item)]
                enrichment.append({"work_id": canonical_identity(work), "matched_ids": [canonical_identity(item) for item in matched],
                    "unmatched_ids": [canonical_identity(item) for item in candidates if item not in matched],
                    "status": "canonical_match" if matched else "unresolved_no_canonical_match"})
                works.extend(matched)
        except (KeyError, TypeError, ValueError, OSError, evidence.LiteratureEvidenceError) as exc:
            errors.append({"kind": "conference", "index": index, "error": str(exc)})
    ranked = rank_candidates(deduplicate(works), {**plan, "as_of": as_of.isoformat()})
    destination = path_in(project, output, exists=False)
    previous = read(destination) if destination.is_file() else {}
    previous_hash = sha(destination) if destination.is_file() else None
    comparable = (previous.get("kind") == "literature_discovery_intelligence"
                  and previous.get("doctoral_question") == scope["doctoral_question"])
    before = {row["canonical_id"]: row for row in previous.get("candidates", [])} if comparable else {}
    after = {row["canonical_id"]: row for row in ranked}
    def content(row):
        return {key: row.get(key) for key in ("title", "authors", "doi", "arxiv_versions", "publication_year", "publication_date",
            "citation_count", "abstract", "venue", "score", "score_components", "exclusion_matches", "interest_feedback", "reading_candidate")}
    delta = {"added": sorted(set(after) - set(before)), "removed_from_current_window": sorted(set(before) - set(after)),
             "changed": sorted(key for key in set(before) & set(after) if content(before[key]) != content(after[key])),
             "previous_output_sha256": previous_hash, "previous_scope_comparable": comparable,
             "preferences_changed": comparable and previous.get("preferences_sha256") != preference_hash,
             "removal_is_not_scientific_exclusion": True}
    source_hash = evidence.sha256_bytes(evidence.canonical_json_bytes(list(source_receipts.values())))
    implementation_hash = sha(Path(__file__))
    input_hash = evidence.sha256_bytes(evidence.canonical_json_bytes({"plan": plan_hash, "scope": scope,
        "sources": source_hash, "preferences": preference_hash, "implementation_sha256": implementation_hash,
        "as_of": as_of.isoformat(), "candidates": ranked, "errors": errors}))
    if previous.get("input_fingerprint") == input_hash:
        return {**previous, "metadata_requests": calls, "changed": False,
                "recommendation_delta": {**delta, "added": [], "removed_from_current_window": [], "changed": []}}
    leads = []
    for work in [row for row in ranked if row["reading_candidate"]][:10]:
        limitation = next((item for item in work["rhetoric_indicators"] if item["kind"] == "problem_or_limitation"), None)
        leads.append({"id": "lead-" + hashlib.sha256(work["canonical_id"].encode()).hexdigest()[:16],
            "kind": "inspect_author_reported_problem" if limitation else "question_scoped_reading_lead",
            "doctoral_question": scope["doctoral_question"], "candidate_id": work["canonical_id"],
            "question": "What evidence in this source bears on the declared doctoral question, and what remains untested?",
            "source_refs": work["source_refs"], "metadata_anchor": limitation or {"field": "title", "quote": work["title"]},
            "topic_keywords": [item["keyword"] for item in work["keyword_matches"]],
            "status": "proposed_requires_fulltext_comparison_and_G1_review", "gap_proven": False,
            "uncertainty": ["Metadata and abstract rhetoric cannot establish a literature gap, causal mechanism or originality.",
                            "Compare closest full texts, counterevidence and conference coverage before scientific adoption.", *work["unknowns"]]})
    report = {"schema_version": "1.0", "kind": "literature_discovery_intelligence", **scope,
        "as_of": as_of.isoformat(), "plan": {"path": plan_path, "sha256": plan_hash},
        "implementation_sha256": implementation_hash, "source_receipts": list(source_receipts.values()),
        "sources_sha256": source_hash, "input_fingerprint": input_hash,
        "metadata_requests": calls, "metadata_requests_total_for_plan": prior_requests + calls,
        "max_requests": maximum, "request_ceiling_scope": "cumulative_per_exact_plan_hash", "paid_model_calls": 0,
        "preferences": preferences, "preferences_sha256": preference_hash,
        "ranking_policy": {"weights": preferences["ranking_weights"], "meaning": "DISCOVERY_HEURISTIC_NOT_RESEARCH_QUALITY"},
        "recommendation_delta": delta,
        "reading_recommendations": [row["canonical_id"] for row in ranked if row["reading_candidate"]][:10],
        "candidates": ranked, "topic_leads": leads, "enrichment": enrichment, "errors": errors,
        "conference_sources": conference_sources,
        "status": "partial_requires_review" if errors else "discovery_requires_G1_review",
        "coverage_complete": False, "automatic_inclusion_exclusion": False, "novelty_verified": False,
        "scope_alignment_verified": False,
        "scientific_completion_verified": False, "gate_approved": False, "human_scientific_review_required": True}
    event_id = evidence.sha256_bytes(evidence.canonical_json_bytes([input_hash, previous_hash]))
    history_path = f"reports/literature-intelligence/{as_of.isoformat()}-{event_id}.json"
    report["history_path"] = history_path
    history = path_in(project, history_path, exists=False)
    if history.is_file() and read(history) != report:
        raise ValueError("refusing to alter a prior discovery change event")
    if not history.is_file():
        write(history, report)
    write(destination, report)
    record(project, [project / output, history], "scripts/literature_intelligence.py")
    return {**report, "changed": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--plan", default=PLAN)
    parser.add_argument("--output", default=OUTPUT)
    args = parser.parse_args()
    report = discover(evidence.project_path(args.project), args.plan, args.output)
    print(json.dumps({"output": args.output, "status": report["status"], "metadata_requests": report["metadata_requests"],
                      "candidate_count": len(report["candidates"]), "gate_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
