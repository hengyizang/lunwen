"""Typed literature lineage, scoped gaps and verified cloud ingestion receipts.

Mechanical correspondence is never semantic support, novelty or scientific completion.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from scripts.research_artifacts import path_in, read, sha

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
DIGEST = re.compile(r"[a-f0-9]{64}")
GAP_TYPES = {"knowledge", "conceptual", "theoretical", "empirical", "methodological",
             "population", "practical", "application", "interdisciplinary", "temporal"}
STATES = {"hypothesis", "planned", "exploratory", "confirmatory", "failed", "stopped", "unknown"}
KINDS = {"primary_finding", "review_report", "review_interpretation", "project_inference",
         "project_observation"}


def text(value, label, maximum=12000):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= maximum:
        raise ValueError(label + " needs bounded nonempty text")
    return value


def identifier(value, label="id"):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(label + " needs a safe stable identifier")
    return value


def rows(value, label, maximum=200, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{label} needs {minimum}-{maximum} entries")
    if any(not isinstance(row, dict) for row in value):
        raise ValueError(label + " needs objects")
    return value


def strings(value, label, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= 200:
        raise ValueError(label + " needs a bounded list")
    for item in value:
        text(item, label, 1000)
    if len(set(value)) != len(value):
        raise ValueError(label + " contains duplicates")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def binding(project, value):
    if not isinstance(value, dict):
        raise ValueError("a current source binding is required")
    relative = text(value.get("path"), "source path", 1000)
    target = path_in(project, relative)
    if not DIGEST.fullmatch(str(value.get("sha256", ""))) or sha(target) != value["sha256"]:
        raise ValueError("source hash changed: " + relative)
    return {"path": relative, "sha256": value["sha256"]}


def anchor(project, value):
    """Validate actual source coordinates; never invent rendered page numbers."""
    bound = binding(project, value)
    target = path_in(project, bound["path"])
    if target.stat().st_size > 50_000_000:
        raise ValueError("source exceeds the bounded anchor reader")
    quote = text(value.get("quote"), "exact source quote")
    kind = value.get("kind")
    if target.suffix.lower() == ".pdf":
        if kind != "pdf_page" or type(value.get("page")) is not int:
            raise ValueError("PDF evidence needs an actual one-based page")
        import fitz
        with fitz.open(target) as document:
            if not 1 <= value["page"] <= len(document):
                raise ValueError("PDF page is outside the actual source")
            content = document[value["page"] - 1].get_text()
        located = {"kind": kind, "page": value["page"]}
    else:
        if kind != "source_lines":
            raise ValueError("text evidence needs exact source_lines")
        content = target.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        start, end = value.get("start_line"), value.get("end_line")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ValueError("source line range is invalid")
        content = "".join(lines[start - 1:end])
        located = {"kind": kind, "start_line": start, "end_line": end}
    if content.count(quote) != 1:
        raise ValueError("quote must occur exactly once at the specified source location")
    return {**bound, **located, "quote": quote, "semantic_support_verified": False}


def anchors(project, value, minimum=1):
    return [anchor(project, item) for item in rows(value, "evidence", 30, minimum)]


def jsonl(project, relative):
    path = path_in(project, relative, exists=False)
    if not path.is_file():
        return []
    result = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows(result, relative, 100000)


def lineage(project: Path, row: dict) -> dict:
    identifier(row.get("id"))
    paper = text(row.get("paper_id"), "paper_id", 3)
    if not re.fullmatch(r"P[0-9]{2}", paper):
        raise ValueError("lineage requires a paper ID")
    nodes = rows(row.get("nodes"), "lineage nodes", 500, 1)
    by_id = {}
    for node in nodes:
        key = identifier(node.get("id"))
        if key in by_id:
            raise ValueError("duplicate lineage node")
        if node.get("kind") not in KINDS or node.get("research_state") not in STATES:
            raise ValueError("explicit attribution kind and research state required")
        if node.get("read_scope") not in {"full_text", "abstract", "excerpt", "metadata"}:
            raise ValueError("explicit supplied read scope required")
        text(node.get("statement"), "source statement")
        text(node.get("boundary"), "inference boundary")
        strings(node.get("parents", []), "lineage parents")
        if node["kind"] in {"review_report", "review_interpretation", "project_inference"}:
            text(node.get("attribution_wording"), "explicit secondary/inferred attribution")
        observed = anchors(project, node.get("evidence"))
        if any(item["path"].startswith(("reports/research-increments/", "state/"))
               or item["path"] == "program/research-increments.json" for item in observed):
            raise ValueError("lineage cannot ground itself or use a control record as scientific evidence")
        if node["read_scope"] == "metadata" and node.get("claim_type") != "identity":
            raise ValueError("metadata cannot substantiate a substantive finding")
        if node.get("claim_type") in {"mechanism", "procedure", "table", "figure"} and node["read_scope"] != "full_text":
            raise ValueError("unseen mechanisms/procedures/tables/figures require full-text evidence")
        if node["read_scope"] == "full_text" and node["kind"] not in {"project_inference", "project_observation"}:
            from scripts.source_scope import verify
            primary = {k: observed[0][k] for k in ("path", "sha256")}
            errors = verify(project, primary, node.get("scope_record"), "full_text")
            if errors:
                raise ValueError("full-text scope unconfirmed: " + "; ".join(errors))
        by_id[key] = {**node, "evidence": observed, "semantic_support_verified": False}
    visiting, done = set(), set()

    def visit(key):
        if key in visiting:
            raise ValueError("lineage contains a cycle")
        if key in done:
            return
        if key not in by_id:
            raise ValueError("unknown lineage parent: " + key)
        visiting.add(key)
        node = by_id[key]
        for parent in node.get("parents", []):
            visit(parent)
        if node["kind"] == "review_report" and not node.get("parents"):
            if node.get("primary_access") != "not_obtained":
                raise ValueError("unread primary study must remain explicitly not_obtained")
        if node["kind"] == "review_interpretation" and not node.get("parents"):
            raise ValueError("review interpretation needs the reported finding it interprets")
        if node["kind"] == "project_inference" and not node.get("parents"):
            raise ValueError("project inference needs its actual premises")
        if node["kind"] == "review_report" and node.get("parents"):
            if not any(by_id[parent]["kind"] == "primary_finding" for parent in node["parents"]):
                raise ValueError("obtained primary study requires an actual primary-finding parent")
        if node["kind"] in {"review_interpretation", "project_inference"}:
            if node["research_state"] in {"exploratory", "confirmatory"}:
                raise ValueError("an interpretation cannot be promoted into an executed observation")
        if node["kind"] == "project_observation":
            attempts = [item for item in jsonl(project, "experiments/registry.jsonl")
                        if item.get("attempt_id") == node.get("attempt_id")]
            if len(attempts) != 1 or attempts[0].get("status") != "succeeded" or attempts[0].get("paper_id") != paper:
                raise ValueError("project observation requires one successful matching executor attempt")
            attempt = attempts[0]
            receipt = path_in(project, f"experiments/runs/{attempt['attempt_id']}/run.json")
            if read(receipt) != attempt or attempt.get("input_integrity", {}).get("passed") is not True:
                raise ValueError("project observation executor receipt is absent or inconsistent")
            outputs = {(item["path"], item["sha256"]) for item in attempt.get("outputs", [])}
            if not outputs or any((item["path"], item["sha256"]) not in outputs for item in node["evidence"]):
                raise ValueError("observation must anchor the exact registered attempt outputs")
            for relative, checksum in outputs:
                if sha(path_in(project, relative)) != checksum:
                    raise ValueError("executor output changed")
            if node["research_state"] not in {"exploratory", "confirmatory"}:
                raise ValueError("completed observations require their registered analysis state")
            plan = read(path_in(project, "experiments/plan.json"))
            run = next((item for item in plan.get("runs", []) if item.get("run_id") == attempt.get("run_id")), None)
            if run is None or run.get("paper_id") != paper:
                raise ValueError("observation is not in the registered plan")
            # Confirmatory status is a scientific designation, not a successful exit.
            if node["research_state"] == "confirmatory":
                from scripts.experiment_evidence import validate_report
                errors = validate_report(project, paper)
                if errors:
                    raise ValueError("confirmatory observation lacks current experimental evidence: " + "; ".join(errors))
        visiting.remove(key)
        done.add(key)

    for key in by_id:
        visit(key)
    mappings = rows(row.get("fact_links"), "fact lineage links", 2000, 1)
    facts = read(path_in(project, f"papers/{paper}/reviews/paper-facts.json"))
    expected = {item["id"] for item in facts.get("facts", [])}
    linked = []
    for link in mappings:
        if link.get("node_id") not in by_id:
            raise ValueError("fact links reference unknown lineage nodes")
        linked.append(link.get("fact_id"))
    if len(linked) != len(set(linked)) or set(linked) != expected:
        raise ValueError("lineage links must exactly cover current paper facts")
    return {"id": row["id"], "paper_id": paper, "nodes": list(by_id.values()), "fact_links": mappings,
            "facts_sha256": sha(project / f"papers/{paper}/reviews/paper-facts.json"),
            "semantic_support_verified": False, "human_read_scope": "not_declared"}


def gaps(project: Path, row: dict) -> dict:
    identifier(row.get("id"))
    types = strings(row.get("types"), "gap types", 1)
    if not set(types) <= GAP_TYPES:
        raise ValueError("unknown gap type; extend the versioned vocabulary explicitly")
    if row.get("status") not in {"candidate", "unknown", "refuted"}:
        raise ValueError("a gap remains candidate, unknown or refuted; novelty is never granted")
    if row.get("scope") not in {"supplied_materials", "executed_queries"}:
        raise ValueError("finite sources cannot establish field-wide absence")
    for field in ("question", "importance", "precise_difference", "falsification_test",
                  "feasibility", "failure_condition", "missing_evidence", "attribution"):
        text(row.get(field), field)
    if row["attribution"] not in {"author_acknowledged", "reader_inferred"}:
        raise ValueError("gap attribution must distinguish source acknowledgement and inference")
    observed = anchors(project, row.get("evidence"))
    counter = anchors(project, row.get("counterevidence", []), 0)
    if counter and row["status"] == "candidate" and not row.get("counterevidence_resolution"):
        raise ValueError("a surviving gap needs an explicit response to counterevidence")
    if row["status"] == "refuted" and not counter:
        raise ValueError("a refutation needs located counterevidence")
    register = read(path_in(project, "program/hypothesis-register.json"))
    hypotheses = register.get("hypotheses", [])
    if row.get("hypothesis_id") not in {item.get("hypothesis_id") for item in hypotheses}:
        raise ValueError("gap must link an existing hypothesis")
    matrix = read(path_in(project, "program/novelty-claim-matrix.json"))
    claims = matrix.get("claims", [])
    if row.get("novelty_claim_id") not in {item.get("claim_id") for item in claims}:
        raise ValueError("gap must link the existing novelty claim matrix")
    closest = strings(row.get("closest_work_ids"), "closest prior work", 1)
    audit = read(path_in(project, "program/originality-audit.json"))
    if set(closest) - {item.get("id") for item in audit.get("closest_prior_work", [])}:
        raise ValueError("closest work must already occur in the originality audit")
    known = {item.get("search_id"): item for item in jsonl(project, "evidence/search-log.jsonl")}
    searches = strings(row.get("counter_search_ids", []), "counterexample queries")
    coverage = []
    ledger = jsonl(project, "evidence/literature-api-ledger.jsonl")
    for key in searches:
        if key not in known:
            raise ValueError("gap query was not executed: " + key)
        receipt = next((item for item in ledger if item.get("receipt_id") == known[key].get("evidence_receipt_id")), None)
        if not receipt or receipt.get("status") != "success":
            raise ValueError("gap query needs its real successful provider receipt")
        for p, h in (("raw_response_path", "response_sha256"), ("normalized_results_path", "normalized_results_sha256")):
            if sha(path_in(project, receipt[p])) != receipt[h]:
                raise ValueError("gap query receipt is stale")
        coverage.append({"search_id": key, "receipt_id": receipt["receipt_id"],
                         "coverage": "returned_results_only", "field_complete": False})
    if row["scope"] == "executed_queries" and not searches:
        raise ValueError("executed-query scope needs actual counterexample searches")
    if row.get("source_scope") != "full_text" and row.get("gap_level") in {"mechanism", "method", "experiment"}:
        raise ValueError("abstract-only material cannot establish unseen experimental gaps")
    if row.get("source_scope") == "full_text":
        from scripts.source_scope import verify
        primary = {k: observed[0][k] for k in ("path", "sha256")}
        errors = verify(project, primary, row.get("scope_record"), "full_text")
        if errors:
            raise ValueError("gap full-text scope is unconfirmed: " + "; ".join(errors))
    return {**row, "evidence": observed, "counterevidence": counter, "query_coverage": coverage,
            "novelty_granted": False, "scientific_validation": False}


def ingest(project: Path, row: dict) -> dict:
    identifier(row.get("id"))
    identifier(row.get("work_id"), "work_id")
    identifiers = row.get("identifiers")
    if not isinstance(identifiers, dict) or not identifiers or not set(identifiers) <= {"doi", "arxiv"}:
        raise ValueError("ingestion requires DOI/arXiv identity, never title-only deduplication")
    for key, value in identifiers.items():
        text(value, key, 200)
        if key == "doi" and not re.fullmatch(r"10\.\d{4,9}/\S+", value, re.I):
            raise ValueError("invalid DOI identity")
        if key == "arxiv" and not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", value, re.I):
            raise ValueError("invalid arXiv identity")
    title = text(row.get("title"), "expected title", 2000)
    version = text(row.get("version"), "explicit paper version", 200)
    parsed = urlsplit(text(row.get("source_url"), "source URL", 2000))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("literature source requires an identified HTTPS URL without credentials")
    result = {"id": row["id"], "work_id": row["work_id"], "identifiers": identifiers,
              "title": title, "version": version, "source_url": row["source_url"],
              "related_work_ids": strings(row.get("related_work_ids", []), "related versions"),
              "identity_status": "bibliographic_identity_unverified", "attachment_status": "metadata_only",
              "scope_confirmation": "not_confirmed", "semantic_support_verified": False,
              "human_full_text_read": "not_declared", "model_calls": 0, "network_calls": 0}
    attachment = row.get("attachment")
    if attachment is not None:
        bound = binding(project, attachment)
        target = path_in(project, bound["path"])
        if target.suffix.lower() != ".pdf" or not 0 < target.stat().st_size <= 50_000_000:
            raise ValueError("full-text receipt needs a bounded actual PDF")
        manifest = binding(project, row.get("rights_manifest"))
        rights = read(path_in(project, manifest["path"]))
        authorization = read(path_in(project, "state/data-authorizations.json")).get("manifests", {}).get(manifest["path"], {})
        if (authorization.get("sha256") != manifest["sha256"] or authorization.get("cloud_use_confirmed") is not True
                or rights.get("download", {}).get("sha256") != bound["sha256"]
                or rights.get("download", {}).get("expected_bytes") != target.stat().st_size):
            raise ValueError("owner-reviewed acquisition rights and exact attachment identity required")
        import fitz
        with fitz.open(target) as document:
            if document.is_encrypted or not 1 <= len(document) <= 2000:
                raise ValueError("PDF is encrypted, empty or exceeds the page bound")
            first = " ".join(document[i].get_text() for i in range(min(2, len(document))))
            normalized = lambda value: "".join(re.findall(r"\w", value.casefold()))
            title_match = normalized(title) in normalized(first)
            id_match = any(normalized(value) in normalized(first) for value in identifiers.values())
            readable = any(document[i].get_text().strip() for i in range(len(document)))
            result.update(attachment=bound, rights_manifest=manifest, page_count=len(document),
                          attachment_status="parseable_text" if readable else "image_only_needs_ocr",
                          identity_status="identity_match_candidate" if title_match and id_match else "pending_identity_check",
                          title_found=title_match, identifier_found=id_match)
        if row.get("scope_record"):
            from scripts.source_scope import verify
            errors = verify(project, bound, row["scope_record"], "full_text")
            if errors:
                raise ValueError("ingestion scope record is stale: " + "; ".join(errors))
            result["scope_confirmation"] = "supplied_full_text_confirmed_not_reading"
            result["scope_record"] = binding(project, row["scope_record"])
    result["identity_key"] = digest({"identifiers": {k: v.casefold() for k, v in identifiers.items()}, "version": version})
    result["content_key"] = digest({k: v for k, v in result.items() if k not in {"id", "work_id", "related_work_ids"}})
    return result

