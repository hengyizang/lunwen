"""Bilingual concept plans and source-bound trial-search history; no requests.

The existing writer proposes terms and scope. This deterministic layer renders
bounded queries, distinguishes platform capabilities, and reads actual receipts.
It never edits the active discovery plan, exclusions, screenings or model routes.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from scripts import literature_evidence as evidence, literature_intelligence as intelligence
from scripts import literature_workbench as workbench
from scripts.research_artifacts import path_in, read, record, sha, write

REQUEST = "program/literature-search-strategy.json"
OUTPUT = "reports/literature-search-strategy"
MODULE = "scripts/literature_search_strategy.py"
TIERS = ("broad", "medium", "strict")
NATIVE = set(evidence.DEFAULT_SEARCH_PROVIDERS)
PLATFORMS = NATIVE | {"wos", "cnki"}


def _digest(value):
    return hashlib.sha256(evidence.canonical_json_bytes(value)).hexdigest()


def _keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + " has unsupported fields")


def _text(value, label, maximum=1000):
    return workbench._text(value, label, maximum).strip()


def _term(value):
    value = _text(value, "concept term", 120)
    if any(ord(ch) < 32 for ch in value) or any(ch in value for ch in '\\"():[]{}'):
        raise ValueError("concept terms must be literal phrases without query operators or delimiters")
    return value


def _concepts(project, incoming):
    if not isinstance(incoming, list) or not 1 <= len(incoming) <= 12:
        raise ValueError("concept table needs 1..12 explicit concepts")
    concepts, papers = {}, None
    for item in incoming:
        _keys(item, {"id", "zh", "en", "aliases", "disciplinary_sense", "evidence"}, "concept")
        identifier = workbench._id(item.get("id"), "concept ID")
        if identifier in concepts:
            raise ValueError("duplicate concept ID")
        zh, en = _term(item.get("zh")), _term(item.get("en"))
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list) or len(aliases) > 6:
            raise ValueError("at most six aliases per concept")
        terms = []
        for term in [en, zh, *[_term(a) for a in aliases]]:
            if term.casefold() not in {t.casefold() for t in terms}:
                terms.append(term)
        bound = []
        anchors = item.get("evidence", [])
        if not isinstance(anchors, list) or len(anchors) > 12:
            raise ValueError("concept evidence must be bounded original anchors")
        for anchor in anchors:
            if papers is None:
                library, _, _ = workbench._snapshot(project)
                papers = {p["id"]: p for p in library["papers"] if p.get("status") == "current"}
            if not isinstance(anchor, dict) or anchor.get("paper_id") not in papers:
                raise ValueError("concept evidence must name a current literature source")
            bound.append({"paper_id": anchor["paper_id"], **workbench.validate_anchor(project,
                papers[anchor["paper_id"]], {k: v for k, v in anchor.items() if k != "paper_id"})})
        concepts[identifier] = {"id": identifier, "zh": zh, "en": en,
            "aliases": [term for term in terms if term.casefold() not in {zh.casefold(), en.casefold()}],
            "terms": terms, "disciplinary_sense": _text(item.get("disciplinary_sense"), "disciplinary sense"),
            "evidence": bound, "terminology_semantics_verified": False}
    return concepts


def _queries(concepts, tiers, platforms):
    if not isinstance(tiers, list) or len(tiers) != 3 or [t.get("level") for t in tiers if isinstance(t, dict)] != list(TIERS):
        raise ValueError("tiers must be ordered broad, medium, strict")
    previous, result = set(), []
    for tier in tiers:
        _keys(tier, {"level", "concept_ids", "reason"}, "tier")
        ids = tier.get("concept_ids")
        if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in concepts for i in ids)
                or len(set(ids)) != len(ids) or not previous <= set(ids)):
            raise ValueError("broad/medium/strict concept selections must be distinct and nested")
        previous = set(ids)
        reason = _text(tier.get("reason"), "tier reason")
        ast = {"op": "and", "children": [{"op": "or", "concept_id": i, "terms": concepts[i]["terms"]} for i in ids]}
        generic = " AND ".join("(" + " OR ".join('"' + term + '"' for term in concepts[i]["terms"]) + ")" for i in ids)
        for platform in platforms:
            if platform == "arxiv":
                query = " AND ".join("(" + " OR ".join('all:"' + term + '"' for term in concepts[i]["terms"]) + ")" for i in ids)
                evidence.build_search_url("arxiv", query, 1)
                variants, syntax = [query], "native_bounded_boolean"
            elif platform == "wos":
                variants, syntax = ["TS=(" + generic + ")"], "syntax_unverified_manual_required"
            elif platform == "cnki":
                variants, syntax = [generic], "syntax_unverified_manual_required"
            else:
                variants = [" ".join(concepts[i]["en"] for i in ids), " ".join(concepts[i]["zh"] for i in ids)]
                for identifier in ids:
                    for alias in concepts[identifier]["aliases"][:1]:
                        variants.append(" ".join(alias if i == identifier else concepts[i]["en"] for i in ids))
                variants = list(dict.fromkeys(variants))[:5]
                syntax = "native_plain_text_boolean_not_claimed"
            for index, query in enumerate(variants, 1):
                if len(query) > 1000:
                    raise ValueError("rendered query exceeds 1000 characters; narrow explicit aliases without silent truncation")
                result.append({"id": f"{tier['level']}-{platform}-{index}", "tier": tier["level"], "platform": platform,
                    "query": query, "query_sha256": hashlib.sha256(query.encode()).hexdigest(), "ast": ast,
                    "reason": reason, "syntax_status": syntax, "manual_required": platform not in NATIVE,
                    "executed": False, "counterevidence_excluded": False,
                    "plan_entry": {"provider": platform, "query": query, "query_family": "direct", "limit": 25}
                        if platform in NATIVE else None})
    return result


def _provider_counts(project, receipt):
    """Keep raw returned records separate from provider totals/normalized works."""
    raw = path_in(project, receipt["raw_response_path"]).read_bytes()
    if len(raw) > evidence.MAX_RESPONSE_BYTES:
        raise ValueError("trial response exceeds the existing provider response bound")
    provider = receipt["provider"]
    if provider == "arxiv":
        if b"<!ENTITY" in raw.upper():
            raise ValueError("trial XML entities are not supported")
        root = ET.fromstring(raw)
        returned = sum(node.tag.rsplit("}", 1)[-1] == "entry" for node in root)
        values = [n.text for n in root.iter() if n.tag.rsplit("}", 1)[-1] == "totalResults"]
        value = values[0] if len(values) == 1 else None
    elif provider in {"semantic-scholar", "crossref", "openalex", "europe-pmc", "hal", "dblp"}:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None, None
        if provider == "semantic-scholar":
            value, rows = payload.get("total"), [payload] if payload.get("paperId") else payload.get("data", [])
        elif provider == "crossref":
            value, rows = payload.get("message", {}).get("total-results"), payload.get("message", {}).get("items", [])
        elif provider == "openalex":
            value, rows = payload.get("meta", {}).get("count"), payload.get("results", [])
        elif provider == "europe-pmc":
            value, rows = payload.get("hitCount"), payload.get("resultList", {}).get("result", [])
        elif provider == "hal":
            value, rows = payload.get("response", {}).get("numFound"), payload.get("response", {}).get("docs", [])
        else:
            value = payload.get("result", {}).get("hits", {}).get("@total")
            rows = payload.get("result", {}).get("hits", {}).get("hit", payload.get("results", {}).get("bindings", []))
        returned = len(rows) if isinstance(rows, list) else None
    else:
        value, returned = None, None
    if value is None:
        return None, returned
    if type(value) is int and value >= 0:
        return value, returned
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,15}", value):
        return int(value), returned
    raise ValueError("provider total must be a nonnegative exact integer")


def _trials(project, incoming, queries):
    if not isinstance(incoming, list) or len(incoming) > 100:
        raise ValueError("at most 100 explicit trial records")
    if not incoming:
        return [], []
    ledger = evidence.read_jsonl(project / "evidence/literature-api-ledger.jsonl")
    receipts = {}
    for row in ledger:
        if row.get("receipt_id") in receipts:
            raise ValueError("duplicate receipt ID in the native literature ledger")
        receipts[row["receipt_id"]] = row
    by_query = {q["id"]: q for q in queries}
    trials, bindings, seen = [], [], set()
    for item in incoming:
        _keys(item, {"id", "query_id", "receipt_id", "reason", "screening"}, "trial")
        identifier = workbench._id(item.get("id"), "trial ID")
        if identifier in seen or item.get("query_id") not in by_query:
            raise ValueError("trial IDs must be distinct and bind a current rendered query")
        seen.add(identifier)
        query = by_query[item["query_id"]]
        receipt = receipts.get(item.get("receipt_id"))
        if not receipt or receipt.get("query") != query["query"] or receipt.get("provider") != query["platform"]:
            raise ValueError("trial receipt must match the exact current platform and query")
        works, references = intelligence._receipt_works(project, receipt)
        context = receipt.get("request_context")
        if context is not None:
            plan = path_in(project, intelligence.PLAN)
            if (not isinstance(context, dict) or context.get("operation") != "literature_intelligence"
                    or sha(plan) != context.get("plan_sha256")):
                raise ValueError("trial discovery plan changed; old plan-bound receipts cannot certify the current strategy")
            bindings.append({"path": intelligence.PLAN, "sha256": sha(plan)})
        stamp = datetime.fromisoformat(str(receipt.get("completed_at", "")).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("trial execution date needs its actual timezone")
        total, raw_returned = _provider_counts(project, receipt)
        retrieved, deduplicated = len(works), len(intelligence.deduplicate(works))
        if total is not None and total < retrieved:
            raise ValueError("provider total cannot be smaller than the actual retrieved set")
        screened, screening = None, None
        if "screening" in item:
            supplied = item["screening"]
            if not isinstance(supplied, dict) or set(supplied) != {"path", "sha256"} or not str(supplied.get("path", "")).startswith("evidence/systematic/"):
                raise ValueError("trial screening needs a current native systematic ledger")
            target = path_in(project, supplied["path"])
            if sha(target) != supplied["sha256"]:
                raise ValueError("trial screening ledger changed")
            from scripts import systematic_review
            systematic_review.assess(project, target)
            decisions = read(target)
            if receipt["receipt_id"] not in decisions["receipt_ids"]:
                raise ValueError("trial screening does not include this receipt")
            screened = sum(receipt["receipt_id"] in s["receipt_ids"] and s["title_abstract"]["decision"] != "pending" for s in decisions["studies"])
            screening = supplied
            bindings.append(supplied)
        if screened is not None and screened > retrieved:
            raise ValueError("screened source-report records exceed this trial's normalized source records")
        bindings.extend({"path": references[p], "sha256": references[h]} for p, h in
            (("raw_response_path", "response_sha256"), ("normalized_results_path", "normalized_results_sha256")))
        source_mode = receipt.get("mode", "unknown")
        trials.append({"id": identifier, "query_id": query["id"], "query_sha256": query["query_sha256"],
            "provider": receipt["provider"], "receipt_id": receipt["receipt_id"], "source_mode": source_mode,
            "recorded_at": receipt["completed_at"],
            "searched_at": receipt["completed_at"] if source_mode == "live_search" else None,
            "imported_at": receipt["completed_at"] if source_mode == "licensed_local_export" else None,
            "execution_basis": "native_live_search_receipt" if source_mode == "live_search" else
                "licensed_export_import_query_declared_search_time_unknown" if source_mode == "licensed_local_export" else
                "receipt_time_only_platform_search_unverified",
            "reason": _text(item.get("reason"), "trial/adjustment reason"), "source_receipt": references,
            "discovery_plan": context,
            "counts": {"platform_total": total, "raw_response_returned": raw_returned,
                       "retrieved": retrieved, "deduplicated": deduplicated, "screened_report_records": screened},
            "raw_response_returned_basis": "provider_response_entries_before_identity_normalization_or_filters",
            "retrieved_basis": "actual_normalized_provider_records_after_declared_filters",
            "deduplicated_basis": "intelligence_work_clusters_not_screening_report_ids",
            "screened_basis": "native_systematic_source_report_records_not_work_clusters",
            "platform_total_basis": "actual_raw_provider_response" if total is not None else "unknown_not_inferred_from_return_limit",
            "screening": screening, "scientific_coverage_verified": False})
    return trials, bindings


def build(project: Path, spec: dict) -> dict:
    _keys(spec, {"schema_version", "version", "change_reason", "doctoral_question", "question", "concepts", "tiers", "platforms", "exclusions", "trials"}, "search strategy")
    if spec.get("schema_version") != "1.0" or type(spec.get("version")) is not int or not 1 <= spec["version"] <= 9999:
        raise ValueError("search strategy needs schema 1.0 and a positive bounded version")
    scope = intelligence._scope(project, spec.get("doctoral_question"))
    question = _text(spec.get("question"), "specific research question", 4000)
    concepts = _concepts(project, spec.get("concepts"))
    platforms = spec.get("platforms")
    if (not isinstance(platforms, list) or not platforms or len(platforms) > len(PLATFORMS)
            or any(not isinstance(p, str) or p not in PLATFORMS for p in platforms) or len(set(platforms)) != len(platforms)):
        raise ValueError("platforms must be distinct supported native or manual sources")
    exclusions = spec.get("exclusions", [])
    if not isinstance(exclusions, list) or len(exclusions) > 12:
        raise ValueError("at most twelve proposed scope exclusions")
    proposed = []
    for item in exclusions:
        _keys(item, {"term", "reason", "scope_category"}, "exclusion")
        if item.get("scope_category") not in {"population", "study_type", "document_type", "language"}:
            raise ValueError("outcome/performance/counterevidence exclusions are forbidden")
        proposed.append({"term": _term(item.get("term")), "reason": _text(item.get("reason"), "exclusion reason"),
            "scope_category": item["scope_category"], "applied": False,
            "review_status": "proposal_only_existing_scope_review_required"})
    queries = _queries(concepts, spec.get("tiers"), platforms)
    trials, bindings = _trials(project, spec.get("trials", []), queries)
    for query in queries:
        query["executed_receipt_ids"] = [t["receipt_id"] for t in trials if t["query_id"] == query["id"] and t["source_mode"] == "live_search"]
        query["imported_receipt_ids"] = [t["receipt_id"] for t in trials if t["query_id"] == query["id"] and t["source_mode"] == "licensed_local_export"]
        query["executed"] = bool(query["executed_receipt_ids"])
    if scope.get("core_thesis"):
        bindings.append(scope["core_thesis"])
    report = {"schema_version": "1.0", "kind": "bilingual_layered_search_strategy", "version": spec["version"],
        "change_reason": _text(spec.get("change_reason"), "strategy change reason"), "scope": scope, "question": question,
        "concepts": list(concepts.values()), "queries": queries, "proposed_exclusions": proposed,
        "trials": trials, "inputs": bindings, "source_semantics_verified": False,
        "active_discovery_plan_modified": False, "automatic_exclusion": False, "gate_approved": False,
        "model_call_made": False, "network_requests": 0, "paid_calls": 0,
        "implementation_sha256": sha(Path(__file__))}
    report["fingerprint"] = _digest(report)
    return report


def _trusted(project, target):
    from scripts.output_provenance import current_origin
    origin = current_origin(project, target)
    if origin.get("status") != "tracked" or origin.get("family") != "other" or origin.get("model") != MODULE:
        raise ValueError("search strategy history/output changed outside the deterministic builder")


def _history(project):
    target = path_in(project, OUTPUT + "/history.json", exists=False)
    if not target.exists():
        return []
    _trusted(project, target)
    value = read(target)
    entries = value.get("versions")
    if not isinstance(entries, list) or len(entries) > 9999:
        raise ValueError("invalid strategy history")
    for version, entry in enumerate(entries, 1):
        if entry.get("version") != version:
            raise ValueError("search strategy history must retain consecutive versions")
        source = path_in(project, entry.get("path", ""))
        _trusted(project, source)
        if sha(source) != entry.get("sha256"):
            raise ValueError("search strategy snapshot changed")
    return entries


def refresh(project: Path, request_path=REQUEST) -> dict:
    if not isinstance(request_path, str) or not request_path.startswith("program/") or Path(request_path).suffix != ".json":
        raise ValueError("search strategy request belongs under program/*.json")
    target = path_in(project, request_path)
    if target.stat().st_size > 500_000:
        raise ValueError("search strategy request exceeds 500 KB")
    spec = workbench._json(target.read_bytes())
    report = build(project, spec)
    report["request"] = {"path": request_path, "sha256": sha(target)}
    versions = _history(project)
    latest = path_in(project, OUTPUT + "/latest.json", exists=False)
    history = path_in(project, OUTPUT + "/history.json", exists=False)
    view = path_in(project, OUTPUT + "/index.html", exists=False)
    for existing in (latest, view):
        if existing.exists(): _trusted(project, existing)
    version = report["version"]
    snapshot = OUTPUT + f"/versions/v{version:04d}.json"
    destination = path_in(project, snapshot, exists=False)
    if version == len(versions):
        if not versions or read(destination) != report:
            raise ValueError("existing strategy version is immutable; increment version with a reason")
    elif version == len(versions) + 1:
        if destination.exists():
            raise ValueError("strategy version path is already occupied")
        write(destination, report)
        record(project, [destination], MODULE)
        versions.append({"version": version, "path": snapshot, "sha256": sha(destination),
                         "reason": report["change_reason"], "request_sha256": sha(target)})
    else:
        raise ValueError("strategy versions must advance by one without deleting history")
    write(latest, report)
    write(history, {"schema_version": "1.0", "versions": versions})
    rows = "".join("<tr><td>" + "</td><td>".join(html.escape(str(q[k])) for k in
        ("tier", "platform", "query", "syntax_status")) + "</td></tr>" for q in report["queries"])
    view.write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'">'
        '<title>Layered search strategy</title><h1>Layered search strategy</h1><p>' + html.escape(report["question"]) +
        '</p><p>Queries are proposals. Manual-platform syntax requires checking. No exclusion or scientific decision is applied.</p>'
        '<table><tr><th>Tier</th><th>Platform</th><th>Query</th><th>Syntax</th></tr>' + rows + '</table>', encoding="utf-8")
    record(project, [latest, history, view], MODULE)
    return {"report": OUTPUT + "/latest.json", "history": OUTPUT + "/history.json", "html": OUTPUT + "/index.html",
            "version": version, "query_count": len(report["queries"]), "trial_count": len(report["trials"]), "paid_calls": 0}


def validate_saved_report(project: Path, request_path=REQUEST) -> dict:
    versions = _history(project)
    latest = path_in(project, OUTPUT + "/latest.json")
    _trusted(project, latest)
    request = path_in(project, request_path)
    fresh = build(project, workbench._json(request.read_bytes()))
    fresh["request"] = {"path": request_path, "sha256": sha(request)}
    if not versions or read(latest) != fresh or versions[-1]["version"] != fresh["version"]:
        raise ValueError("search strategy inputs, implementation or current version changed")
    return {"valid": True, "version": fresh["version"], "scientific_coverage_verified": False}
