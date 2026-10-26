"""Transparent discovery-role classification, without scientific exclusion."""
from pathlib import Path
import html

from scripts import literature_intelligence as intelligence, literature_workbench as wb
from scripts.research_artifacts import path_in, record, sha, write

OUTPUT = "reports/literature-roles"
FAMILIES = {"direct": "core_candidate", "adjacent": "adjacent_candidate", "counterevidence": "counterevidence_candidate"}


def build(project, spec):
    if (not isinstance(spec, dict) or set(spec) != {"schema_version", "leads"}
            or spec.get("schema_version") != "1.0" or not isinstance(spec.get("leads"), dict)
            or set(spec["leads"]) != {"path", "sha256"} or spec["leads"]["path"] != "program/topic-leads.json"):
        raise ValueError("classification needs the canonical discovery leads binding")
    source = path_in(project, spec["leads"]["path"])
    from scripts.output_provenance import current_origin
    if sha(source) != spec["leads"]["sha256"] or current_origin(project, source).get("status") != "tracked":
        raise ValueError("classification leads changed or lack executor provenance")
    leads = wb._json(source.read_bytes())
    if leads.get("kind") != "literature_discovery_intelligence":
        raise ValueError("classification needs native discovery output")
    scope = intelligence._scope(project, leads["doctoral_question"])
    ledger = {}
    for receipt in intelligence.evidence.read_jsonl(project / "evidence/literature-api-ledger.jsonl"):
        identifier = receipt.get("receipt_id")
        if not isinstance(identifier, str) or not identifier or identifier in ledger:
            raise ValueError("classification needs unique actual literature receipt IDs")
        ledger[identifier] = receipt
    search_log = intelligence.evidence.read_jsonl(project / "evidence/search-log.jsonl")
    receipts, source_works = {}, {}
    for ref in leads["source_receipts"]:
        identifier = ref["receipt_id"]
        if identifier not in ledger or identifier in receipts:
            raise ValueError("classification receipt missing or repeated in discovery leads")
        actual = ledger[identifier]
        works, expected_ref = intelligence._receipt_works(project, actual)
        if ref != expected_ref:
            raise ValueError("classification discovery receipt binding differs from actual raw/normalized sources")
        receipts[identifier] = actual
        source_works[identifier] = {work["source_refs"][0]["locator"]: work for work in works}
    rows = []
    for candidate in leads["candidates"]:
        routes, members, seen_refs = [], [], set()
        for ref in candidate.get("source_refs", []):
            identifier = ref["receipt_id"]
            if identifier not in receipts:
                raise ValueError("candidate references unknown discovery receipt")
            locator = ref.get("locator")
            member = source_works[identifier].get(locator) if isinstance(locator, str) else None
            marker = (identifier, locator)
            if member is None or ref != member["source_refs"][0] or marker in seen_refs:
                raise ValueError("candidate source locator/hash differs from its actual normalized work")
            seen_refs.add(marker)
            members.append(member)
            actual = receipts[identifier]
            matching = [entry for entry in search_log if entry.get("evidence_receipt_id") == identifier
                        and entry.get("response_sha256") == actual.get("response_sha256")
                        and entry.get("normalized_results_sha256") == actual.get("normalized_results_sha256")
                        and entry.get("query") == actual.get("query")]
            families = {entry.get("query_family") for entry in matching}
            family = next(iter(families)) if len(families) == 1 else None
            routes.append({"receipt_id": identifier, "query_family": family,
                           "query": actual.get("query"), "role": FAMILIES.get(family, "unclassified_candidate")})
        # Replay the native identity grouping on the exact cited works. Merely
        # naming a real receipt must not transfer its query role to another work.
        grouped = intelligence.deduplicate(members) if members else []
        identity_fields = ("canonical_id", "title", "doi", "arxiv_id", "authors", "publication_year")
        if (len(grouped) != 1 or any(candidate.get(k) != grouped[0].get(k) for k in identity_fields)
                or intelligence.canonical_identity(candidate) != grouped[0]["canonical_id"]):
            raise ValueError("classification candidate identity differs from its actual source works")
        roles = sorted({r["role"] for r in routes}) or ["unclassified_candidate"]
        rows.append({"candidate_id": candidate["canonical_id"], "title": candidate["title"], "roles": roles,
            "rationale": "Membership follows recorded query families; overlapping roles are retained.",
            "routes": routes, "basis": "discovery_metadata_not_fulltext_scientific_fit",
            "fulltext_review_required": True, "inclusion_decision": None})
    return {"schema_version": "1.0", "kind": "literature_discovery_roles", "source": spec["leads"],
        "scope": scope, "items": rows, "method": "recorded_query_family_multi_label",
        "automatic_scientific_exclusion": False, "novelty_verified": False, "paid_calls": 0}


def refresh(project, request_path="program/literature-roles.json"):
    from scripts.literaturectl import require_cloud
    require_cloud()
    if not isinstance(request_path, str) or not request_path.startswith("program/"):
        raise ValueError("classification request belongs under program/")
    source = path_in(project, request_path)
    if source.stat().st_size > 64000:
        raise ValueError("classification request exceeds 64 KB")
    report = build(project, wb._json(source.read_bytes()))
    report["request"] = {"path": request_path, "sha256": sha(source)}
    directory = path_in(project, OUTPUT, exists=False)
    target, page, manifest = (directory / n for n in ("latest.json", "index.html", "manifest.json"))
    write(target, report)
    page.write_text("<!doctype html><meta charset='utf-8'><title>Literature roles</title><h1>Discovery roles</h1>"
        "<p>Provisional, overlapping query roles. No scientific inclusion/exclusion.</p><ul>" + "".join(
        "<li>" + html.escape(r["title"] + ": " + ", ".join(r["roles"])) + "</li>" for r in report["items"]) + "</ul>", encoding="utf-8")
    write(manifest, {"request": report["request"], "implementation_sha256": sha(Path(__file__)),
        "files": [{"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in (target, page)]})
    record(project, [target, page, manifest], "scripts/literature_roles.py")
    return report


def validate_saved_report(project, request_path="program/literature-roles.json"):
    source = path_in(project, request_path)
    manifest = wb._json(path_in(project, OUTPUT + "/manifest.json").read_bytes())
    from scripts.output_provenance import current_origin
    if manifest["request"] != {"path": request_path, "sha256": sha(source)} or manifest["implementation_sha256"] != sha(Path(__file__)):
        raise ValueError("classification request/implementation changed")
    for binding in manifest["files"]:
        path = path_in(project, binding["path"])
        if sha(path) != binding["sha256"] or current_origin(project, path).get("status") != "tracked":
            raise ValueError("classification output changed")
    actual = wb._json(path_in(project, OUTPUT + "/latest.json").read_bytes())
    expected = build(project, wb._json(source.read_bytes()))
    if {k: v for k, v in actual.items() if k != "request"} != expected:
        raise ValueError("classification no longer matches actual receipts")
    return actual
