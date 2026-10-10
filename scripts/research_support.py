"""Question clarification, primary-method dissection and honest FAIR metadata.

This builds review aids from actual source anchors. Metadata GETs cannot publish,
authorize data acquisition, certify a method, resolve an owner question or prove
scientific completion. FAIR can include controlled-access data.
"""
from __future__ import annotations

import ast
import hashlib
import ipaddress
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from scripts.research_artifacts import path_in, read, record, sha, write
from scripts.network_safety import fetch_bytes, validate_https_url

INPUT = "program/research-support.json"
OUTPUT = "reports/research-support.json"
INDEX = "evidence/support-sources/index.json"
META_PROVIDER = "deterministic-control-plane"
METHOD_FIELDS = {"research_question", "design_type", "estimand", "sampling", "measurements", "comparators",
                 "analysis", "assumptions", "falsification", "limitations"}
ESTIMAND = {"population", "intervention_or_exposure", "comparator", "outcome", "time_horizon", "unit_of_analysis"}
FAIR = {"findable", "accessible", "interoperable", "reusable"}


def _timestamp(value) -> datetime:
    if not isinstance(value, str):
        raise ValueError("source retrieval timestamp is required")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("source retrieval timestamp needs timezone")
    return stamp.astimezone(timezone.utc)


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " needs concrete text")
    return value


def _strings(value, label: str, *, minimum=1) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum or len(value) > 100:
        raise ValueError(label + " needs a bounded list of text")
    return [_text(item, label) for item in value]


def _url(value) -> str:
    parsed = urlsplit(validate_https_url(value))
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith((".local", ".localhost")) or parsed.port not in {None, 443}:
        raise ValueError("metadata URL must identify a public HTTPS host on its standard port")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("metadata URL cannot use a private or reserved address")
    for key, _ in parse_qsl(parsed.query):
        if any(secret in key.lower() for secret in ("token", "key", "secret", "password", "authorization", "signature")):
            raise ValueError("metadata URL cannot contain credentials or signed download parameters")
    if hostname in {"api.openai.com", "api.anthropic.com"}:
        raise ValueError("paid model endpoints are outside public metadata collection")
    if re.search(r"\.(?:pdf|zip|gz|tar|csv|tsv|parquet|h5|hdf5|bin|npy|npz|docx|xlsx)(?:$|/)", parsed.path, re.I):
        raise ValueError("support collection fetches metadata, never datasets or full-text binaries")
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _requests(value: dict) -> dict:
    plan = value.get("metadata_sources", [])
    if not isinstance(plan, list) or len(plan) > 80:
        raise ValueError("metadata source plan must be a list of at most 80 URLs")
    requests = {}
    for item in plan:
        if not isinstance(item, dict) or item.get("purpose") != "public_metadata":
            raise ValueError("source fetches need an explicit public_metadata purpose")
        url = _url(item.get("url"))
        domains = set(_strings(item.get("official_domains"), "official metadata domains"))
        if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain) for domain in domains):
            raise ValueError("declared metadata domains need exact lowercase hostnames")
        if urlsplit(url).hostname not in domains:
            raise ValueError("metadata URL is outside its declared official domains")
        if url in requests and requests[url] != domains:
            raise ValueError("duplicate metadata URL has conflicting domain declarations")
        requests[url] = domains
    return requests


def _origin(project: Path, target: Path) -> bool:
    from scripts.output_provenance import current_origin
    origin = current_origin(project, target)
    return (origin.get("status") == "tracked" and origin.get("family") == "other"
            and origin.get("provider") == META_PROVIDER and origin.get("model") == "scripts/research_support.py")


def _receipt(project: Path, url: str, domains: set[str], *, current: datetime, max_age=timedelta(days=7)) -> dict:
    index = path_in(project, INDEX)
    ledger = read(index)
    if not isinstance(ledger.get("sources"), dict):
        raise ValueError("metadata source index must contain a source mapping")
    receipt = ledger["sources"].get(url)
    if ledger.get("schema_version") != "1.0" or not _origin(project, index) or not isinstance(receipt, dict):
        raise ValueError("metadata source needs an actual protected control-plane receipt")
    if receipt.get("status") != "retrieved" or receipt.get("http_status") != 200 or receipt.get("url") != url:
        raise ValueError("metadata source was not successfully retrieved")
    age = current - _timestamp(receipt.get("retrieved_at"))
    if not timedelta(0) <= age <= max_age:
        raise ValueError("metadata retrieval receipt is expired or future-dated")
    final_url = _url(receipt.get("final_url"))
    if urlsplit(final_url).hostname not in domains:
        raise ValueError("metadata receipt redirected outside the declared official domains")
    source, raw = path_in(project, receipt.get("path", "")), path_in(project, receipt.get("raw_path", ""))
    if not _origin(project, source) or not _origin(project, raw):
        raise ValueError("metadata raw/source records lack current deterministic provenance")
    if sha(source) != receipt.get("sha256") or sha(raw) != receipt.get("raw_sha256"):
        raise ValueError("metadata raw/source hash differs from its retrieval receipt")
    identifier = hashlib.sha256((url + sha(raw)).encode()).hexdigest()
    if receipt["path"] != f"evidence/support-sources/{identifier}.txt" or receipt["raw_path"] != f"evidence/support-sources/{identifier}.response.txt":
        raise ValueError("metadata receipt paths do not match their actual URL and response hash")
    return receipt


def fetch_sources(project: Path, fetcher=None, *, now: datetime | None = None) -> dict:
    """At most ten public metadata GETs, seven-day cache, six-hour failure cooldown."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("metadata clock needs timezone")
    value = read(path_in(project, INPUT))
    requests = _requests(value)
    index_path = path_in(project, INDEX, exists=False)
    ledger = read(index_path) if index_path.is_file() else {"schema_version": "1.0", "sources": {}}
    if ledger.get("schema_version") != "1.0" or not isinstance(ledger.get("sources"), dict):
        raise ValueError("unsupported support metadata receipt index")
    fetcher = fetcher or fetch_bytes
    count, pending = 0, []
    for url, domains in sorted(requests.items()):
        old = ledger["sources"].get(url, {})
        if isinstance(old, dict) and old.get("status") == "unavailable":
            try:
                if timedelta(0) <= current - _timestamp(old.get("retrieved_at")) < timedelta(hours=6):
                    pending.append(url)
                    continue
            except (ValueError, TypeError):
                pass
        try:
            _receipt(project, url, domains, current=current)
            continue
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if count >= 10:
            pending.append(url)
            continue
        count += 1
        try:
            payload, final_url, status, mime = fetcher(url, max_bytes=500_000)
            final_url = _url(final_url)
            if status != 200 or urlsplit(final_url).hostname not in domains:
                raise ValueError("metadata retrieval failed or redirected outside the declared domains")
            media = (mime or "").split(";", 1)[0].lower().strip()
            if media not in {"text/html", "text/plain", "application/json", "application/ld+json", "application/xml", "text/xml", "application/atom+xml"}:
                raise ValueError("metadata retrieval returned an unsupported binary or dataset content type")
            if not isinstance(payload, bytes) or not payload or len(payload) > 500_000:
                raise ValueError("metadata response is empty or exceeds the bounded byte limit")
            body = payload.decode("utf-8")
            if media == "text/html":
                from scripts.direction_evidence import PageText
                parser = PageText()
                parser.feed(body)
                text = " ".join(" ".join(parser.parts).split())
            else:
                text = body
            if not text.strip():
                raise ValueError("metadata response has no inspectable text")
            identifier = hashlib.sha256((url + hashlib.sha256(payload).hexdigest()).encode()).hexdigest()
            source = path_in(project, f"evidence/support-sources/{identifier}.txt", exists=False)
            raw = path_in(project, f"evidence/support-sources/{identifier}.response.txt", exists=False)
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(text, encoding="utf-8")
            raw.write_bytes(payload)
            ledger["sources"][url] = {"url": url, "final_url": final_url, "http_status": status, "content_type": media,
                                      "retrieved_at": current.isoformat(), "path": source.relative_to(project).as_posix(),
                                      "sha256": sha(source), "raw_path": raw.relative_to(project).as_posix(), "raw_sha256": sha(raw),
                                      "status": "retrieved", "data_download_authorized": False, "publishing_authorized": False}
            record(project, [source, raw], "scripts/research_support.py")
        except (OSError, ValueError, RuntimeError, UnicodeError) as exc:
            ledger["sources"][url] = {"url": url, "status": "unavailable", "retrieved_at": current.isoformat(), "error": str(exc)[:400]}
    ledger.update({"fetched_this_operation": count, "pending_urls": pending, "paid_calls": 0,
                   "publishing_authorized": False, "data_download_authorized": False})
    write(index_path, ledger)
    record(project, [index_path], "scripts/research_support.py")
    return ledger


def _anchor(project: Path, value: dict, *, primary_path: str | None = None) -> dict:
    if not isinstance(value, dict):
        raise ValueError("supporting source anchor must be an object")
    path = path_in(project, value.get("path", ""))
    if value["path"] in {INPUT, OUTPUT} or value["path"].startswith("reports/research-support"):
        raise ValueError("research support cannot cite its own input/report as evidence")
    if primary_path is not None and value["path"] != primary_path:
        raise ValueError("method observation must anchor its confirmed primary source")
    quote = _text(value.get("quote"), "exact evidence quote")
    _text(value.get("locator"), "evidence locator")
    if sha(path) != value.get("sha256"):
        raise ValueError("supporting source hash is stale")
    from scripts.research_candidates import anchor_errors
    normalized = {**value, "excerpt": quote}
    errors = anchor_errors(project, normalized)
    if errors:
        raise ValueError("; ".join(errors))
    # Text, page or paragraph location is recomputed by anchor_errors. Presence
    # does not establish that an interpretation follows from the quoted passage.
    return {key: value[key] for key in ("path", "sha256", "locator", "quote", "pdf_page") if key in value}


def _statement(project: Path, value, label: str, *, primary_path=None, pending: list | None = None) -> dict:
    if not isinstance(value, dict):
        raise ValueError(label + " must contain status, value and evidence")
    if value.get("status") == "not_assessed":
        reason = _text(value.get("reason"), label + " missing-assessment reason")
        if value.get("value") not in {None, ""} or value.get("evidence") not in (None, []):
            raise ValueError(label + " cannot assert unseen content as not_assessed")
        if pending is not None:
            pending.append(label + ": " + reason)
        return {"status": "not_assessed", "reason": reason}
    if value.get("status") not in {"source_statement", "analyst_interpretation"}:
        raise ValueError(label + " must distinguish source statement, analyst interpretation or not_assessed")
    text = _text(value.get("value"), label)
    boundary = _text(value.get("boundary"), label + " inference boundary")
    anchors = value.get("evidence")
    if not isinstance(anchors, list) or not 1 <= len(anchors) <= 20:
        raise ValueError(label + " needs bounded source evidence")
    return {"status": value["status"], "value": text, "boundary": boundary,
            "evidence": [_anchor(project, anchor, primary_path=primary_path) for anchor in anchors],
            "entailment_verified": False}


def _clarification(project: Path, row: dict, pending: list) -> dict:
    identifier = _text(row.get("id"), "clarification ID")
    question = _text(row.get("question"), "human research question")
    estimand = row.get("estimand")
    if not isinstance(estimand, dict) or set(estimand) != ESTIMAND:
        raise ValueError("clarification must spell out all six estimand components")
    estimand = {key: _text(value, "estimand." + key) for key, value in estimand.items()}
    assumptions = row.get("assumptions")
    if not isinstance(assumptions, list) or not 1 <= len(assumptions) <= 30:
        raise ValueError("clarification needs explicit bounded assumptions")
    normalized = []
    for item in assumptions:
        if not isinstance(item, dict) or item.get("status") not in {"proposed", "source_supported", "unresolved"}:
            raise ValueError("assumptions must be proposed, source_supported or unresolved; no inferred owner approval")
        _text(item.get("statement"), "assumption")
        _text(item.get("failure_consequence"), "assumption failure consequence")
        anchors = item.get("evidence", [])
        if not isinstance(anchors, list) or len(anchors) > 20 or (item["status"] == "source_supported" and not anchors):
            raise ValueError("source-supported assumption needs actual source evidence")
        normalized.append({**item, "evidence": [_anchor(project, anchor) for anchor in anchors]})
        if item["status"] in {"proposed", "unresolved"}:
            pending.append(identifier + ": assumption remains " + item["status"])
    boundary = row.get("boundaries")
    if not isinstance(boundary, dict) or set(boundary) != {"included", "excluded", "inference_ceiling"}:
        raise ValueError("clarification needs explicit included/excluded/inference boundaries")
    boundary = {"included": _strings(boundary["included"], "included boundary"),
                "excluded": _strings(boundary["excluded"], "excluded boundary"),
                "inference_ceiling": _text(boundary["inference_ceiling"], "inference ceiling")}
    if {item.strip().casefold() for item in boundary["included"]} & {item.strip().casefold() for item in boundary["excluded"]}:
        raise ValueError("included and excluded boundaries cannot contain the same scope")
    questions = row.get("pending_owner_questions")
    if not isinstance(questions, list) or len(questions) > 20:
        raise ValueError("clarification needs an explicit pending_owner_questions list")
    seen = set()
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("owner question must be an object")
        qid = _text(item.get("id"), "owner question ID")
        if qid in seen:
            raise ValueError("owner question IDs must be unique")
        seen.add(qid)
        _text(item.get("question"), "owner question")
        if item.get("status", "pending_owner") != "pending_owner" or item.get("resolved") not in {None, False}:
            raise ValueError("support builder cannot declare an owner question answered or approve a gate")
        if "choices" in item:
            _strings(item["choices"], "owner question choices", minimum=2)
        pending.append(identifier + ": owner question " + qid)
    return {"id": identifier, "question": question, "estimand": estimand, "assumptions": normalized,
            "boundaries": boundary, "pending_owner_questions": questions, "human_confirmation_required": True,
            "owner_approval_inferred": False}


def _number(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("worked example values must be finite numbers")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("worked example values must be numeric") from exc
    if not number.is_finite() or abs(number) > Decimal("1e18"):
        raise ValueError("worked example value is nonfinite or exceeds the arithmetic ceiling")
    return number


def _arithmetic(expression: str, variables: dict) -> Decimal:
    _text(expression, "worked-example expression")
    if len(expression) > 500:
        raise ValueError("worked-example expression is too long")
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 80:
        raise ValueError("worked-example expression is too complex")
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            return _number(node.value)
        if isinstance(node, ast.Name) and node.id in variables:
            return variables[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div):
                if right == 0:
                    raise ValueError("worked example divides by zero")
                result = left / right
            else:
                if right != right.to_integral_value() or abs(right) > 6:
                    raise ValueError("worked-example powers need a bounded integer exponent")
                if left == 0 and right < 0:
                    raise ValueError("worked example divides by zero")
                result = left ** int(right)
            return _number(str(result))
        raise ValueError("worked example permits only numeric names and bounded arithmetic, never code/tool execution")
    with localcontext() as context:
        context.prec = 28
        return visit(tree)


def _worked_example(project: Path, value, primary: dict, label: str, pending: list) -> dict:
    if not isinstance(value, dict):
        raise ValueError("method needs an explicit worked_example requirement")
    status = value.get("status")
    if status in {"pending", "not_applicable"}:
        reason = _text(value.get("reason"), "worked-example reason")
        if status == "pending":
            pending.append(label + ": worked example pending")
        else:
            anchors = value.get("evidence")
            if not isinstance(anchors, list) or not anchors:
                raise ValueError("not-applicable worked example needs source-bound rationale for human review")
            return {"status": status, "reason": reason, "evidence": [_anchor(project, item, primary_path=primary["path"]) for item in anchors],
                    "human_applicability_review_required": True}
        return {"status": status, "reason": reason}
    if status != "documented":
        raise ValueError("worked example must be pending, documented or not_applicable")
    reference = value.get("record")
    if not isinstance(reference, dict):
        raise ValueError("documented example needs a real hash-bound JSON calculation record")
    target = path_in(project, reference.get("path", ""))
    if target.suffix != ".json" or target.relative_to(project).as_posix() in {INPUT, OUTPUT} or sha(target) != reference.get("sha256"):
        raise ValueError("worked-example record is stale or not an independent JSON artifact")
    example = read(target)
    if example.get("schema_version") != "1.0" or example.get("input_origin") not in {"synthetic_illustration", "source_example"}:
        raise ValueError("worked example must disclose synthetic illustration versus source example")
    _text(example.get("problem"), "worked example problem")
    _text(example.get("scientific_limit"), "worked example scientific limit")
    method_anchor = _anchor(project, value.get("method_anchor"), primary_path=primary["path"])
    inputs, steps = example.get("inputs"), example.get("steps")
    if not isinstance(inputs, dict) or not 1 <= len(inputs) <= 20 or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,30}", key) for key in inputs):
        raise ValueError("worked example inputs need bounded named numeric values")
    variables = {key: _number(number) for key, number in inputs.items()}
    if example["input_origin"] == "source_example":
        anchors = example.get("input_evidence")
        if not isinstance(anchors, dict) or set(anchors) != set(inputs):
            raise ValueError("source example inputs each need an actual primary-source anchor")
        for key, anchor in anchors.items():
            bound = _anchor(project, anchor, primary_path=primary["path"])
            if not _contains(str(inputs[key]), bound["quote"]):
                raise ValueError("worked-example source value is absent from its actual quote")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
        raise ValueError("worked example needs a bounded sequence of explicit calculation steps")
    results = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("worked-example calculation step must be an object")
        name = _text(step.get("name"), "worked-example result name")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,30}", name) or name in variables:
            raise ValueError("worked-example result names must be valid and cannot overwrite inputs")
        _text(step.get("reason"), "worked-example calculation reason")
        actual = _arithmetic(step.get("expression"), variables)
        expected = _number(step.get("result"))
        tolerance = _number(step.get("absolute_tolerance", 0))
        if tolerance < 0 or tolerance > Decimal("0.000001"):
            raise ValueError("worked-example tolerance must be between zero and 0.000001")
        if abs(actual - expected) > tolerance:
            raise ValueError("worked-example stated result does not match the independently recomputed arithmetic")
        variables[name] = actual
        results.append({"name": name, "expression": step["expression"], "computed": str(actual), "stated": str(expected),
                        "absolute_tolerance": str(tolerance), "reason": step["reason"]})
    return {"status": "documented", "record": {"path": reference["path"], "sha256": sha(target)}, "method_anchor": method_anchor,
            "input_origin": example["input_origin"], "problem": example["problem"], "scientific_limit": example["scientific_limit"],
            "steps": results, "arithmetic_checked": True, "method_validated": False, "experiment_result": False,
            "arithmetic_scope": "bounded scalar illustration; numerical agreement cannot validate a statistical or scientific method"}


def _method(project: Path, row: dict, pending: list) -> dict:
    identifier = _text(row.get("id"), "method-dissection ID")
    primary = row.get("primary_source")
    if not isinstance(primary, dict):
        raise ValueError("method needs an actual primary source path and hash")
    source = path_in(project, primary.get("path", ""))
    if sha(source) != primary.get("sha256") or set(primary) != {"path", "sha256"}:
        raise ValueError("method primary source hash is stale or primary_source is malformed")
    scope = row.get("source_scope")
    assessed = row.get("methods_assessed")
    if scope not in {"full_text", "abstract", "excerpt", "metadata"} or not isinstance(assessed, bool):
        raise ValueError("method dissection needs explicit source_scope and methods_assessed")
    scope_confirmed = False
    if scope == "full_text":
        from scripts.source_scope import verify
        errors = verify(project, primary, row.get("scope_record"), "full_text")
        if errors:
            raise ValueError("; ".join(errors))
        scope_confirmed = True
    if assessed and not scope_confirmed:
        raise ValueError("methods_assessed requires actual protected human-confirmed supplied full text")
    if not assessed:
        pending.append(identifier + ": methods not assessed; unseen details remain pending")
    fields = row.get("fields")
    if not isinstance(fields, dict) or set(fields) != METHOD_FIELDS:
        raise ValueError("method dissection must address design, estimand, assumptions, falsification and all method fields")
    normalized = {key: _statement(project, value, identifier + "." + key, primary_path=primary["path"], pending=pending)
                  for key, value in sorted(fields.items())}
    if assessed and any(item["status"] == "not_assessed" for item in normalized.values()):
        raise ValueError("methods_assessed cannot conceal missing method-dissection fields")
    example = _worked_example(project, row.get("worked_example"), primary, identifier, pending)
    return {"id": identifier, "primary_source": primary, "source_scope": scope, "supplied_scope_confirmed": scope_confirmed,
            "methods_assessed": assessed, "fields": normalized, "worked_example": example,
            "human_read_scope": "not_declared", "scientific_validation": False, "independent_replication_performed": False,
            "human_scientific_review_required": True}


def _contains(value: str, quote: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", quote, re.I))


def _datasets(project: Path) -> tuple[dict, dict]:
    path = path_in(project, "data/datasets.jsonl")
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if not isinstance(row, dict) or not isinstance(row.get("dataset_id"), str) or row["dataset_id"] in values:
            raise ValueError("dataset manifest entries need unique dataset IDs")
        values[row["dataset_id"]] = row
    return values, {"path": "data/datasets.jsonl", "sha256": sha(path)}


def _availability(project: Path, row: dict, datasets: dict, requests: dict, current: datetime, pending: list) -> dict:
    identifier = _text(row.get("dataset_id"), "availability dataset ID")
    if identifier not in datasets or row.get("version") != datasets[identifier].get("version"):
        raise ValueError("data availability must bind an existing registered dataset and its exact version")
    manifest = datasets[identifier]
    license = manifest.get("license")
    if not isinstance(license, dict) or any(not isinstance(license.get(key), bool) for key in ("research_use_allowed", "redistribution_allowed", "confirmed_by_human")):
        raise ValueError("data availability needs explicit existing license/permission fields")
    _text(license.get("name"), "registered license name")
    access = row.get("access_mode")
    if access not in {"open", "restricted", "embargoed", "unavailable"}:
        raise ValueError("availability must distinguish open, restricted, embargoed and unavailable access")
    fair = row.get("fair")
    if not isinstance(fair, dict) or set(fair) != FAIR:
        raise ValueError("FAIR report must address findable, accessible, interoperable and reusable separately")
    normalized = {key: _statement(project, value, identifier + ".FAIR." + key, pending=pending) for key, value in sorted(fair.items())}
    deposit = row.get("deposit")
    if not isinstance(deposit, dict) or deposit.get("status") not in {"planned", "record_observed", "unavailable"}:
        raise ValueError("deposit status must distinguish planned, record_observed and unavailable")
    if any(deposit.get(key) is True for key in ("uploaded", "availability_verified", "upload_ownership_verified", "data_files_verified")):
        raise ValueError("metadata observation cannot certify upload, ownership or actual dataset files")
    receipt = None
    if deposit["status"] == "record_observed":
        url = _url(deposit.get("url"))
        if url not in requests:
            raise ValueError("deposit record must belong to the explicit public metadata source plan")
        receipt = _receipt(project, url, requests[url], current=current)
        if deposit.get("version") != row["version"]:
            raise ValueError("observed repository record refers to a different dataset version")
        _text(deposit.get("identifier"), "repository record identifier")
        _text(deposit.get("access_label"), "repository access label")
        access_labels = {"open": "open", "open access": "open", "public": "open",
                         "restricted": "restricted", "controlled": "restricted", "controlled access": "restricted",
                         "embargo": "embargoed", "embargoed": "embargoed",
                         "unavailable": "unavailable", "not available": "unavailable"}
        if access_labels.get(deposit["access_label"].strip().casefold()) != access:
            raise ValueError("repository access label differs from declared access mode or is unknown")
        labels = {"identifier_anchor": deposit["identifier"], "version_anchor": deposit["version"],
                  "access_anchor": deposit["access_label"], "license_anchor": license["name"]}
        anchors = {}
        for field, label in labels.items():
            anchor = _anchor(project, deposit.get(field), primary_path=receipt["path"])
            if not _contains(str(label), anchor["quote"]):
                raise ValueError("repository record value is absent from its actual metadata quote: " + field)
            anchors[field] = anchor
        if access == "open" and re.search(r"\b(?:not|no|never|isn't)\b[^.;\n]{0,60}\b(?:open|public)\b", anchors["access_anchor"]["quote"], re.I):
            raise ValueError("negative access evidence cannot support an open deposit")
        deposit = {key: value for key, value in deposit.items() if not key.endswith("_anchor")}
        deposit.update(anchors)
    else:
        _text(deposit.get("reason"), "pending/unavailable deposit reason")
        pending.append(identifier + ": repository record " + deposit["status"])
        if deposit.get("uploaded") is True or deposit.get("availability_verified") is True:
            raise ValueError("a planned/unavailable deposit cannot claim a completed upload")
    warnings = []
    if license["confirmed_by_human"] is not True or license["research_use_allowed"] is not True:
        warnings.append("Existing research-use/license human authorization is incomplete; this report grants no access.")
        pending.append(identifier + ": license/research-use approval pending")
    if license["redistribution_allowed"] is not True:
        warnings.append("Public metadata or viewing access does not grant redistribution; publication of data remains unauthorized.")
    return {"dataset_id": identifier, "version": row["version"], "access_mode": access, "fair": normalized,
            "deposit": deposit, "metadata_receipt": receipt, "registered_rights": license, "warnings": warnings,
            "fair_certified": False, "fair_requires_unrestricted_open_access": False,
            "metadata_record_observed": receipt is not None, "upload_ownership_verified": False,
            "data_files_retrieved_or_verified": False, "publishing_authorized": False,
            "human_license_and_access_review_required": True}


def audit(project: Path, *, now: datetime | None = None) -> dict:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("support audit clock needs timezone")
    input_path = path_in(project, INPUT, exists=False)
    result = {"schema_version": "1.0", "input": None, "clarifications": [], "method_dissections": [], "data_availability": [],
              "dataset_registry": None, "source_bindings": [], "errors": [], "pending_inputs": [], "paid_calls": 0,
              "semantic_entailment_verified": False, "scientific_completion_verified": False, "human_scientific_review_required": True,
              "owner_approval_inferred": False, "experiments_authorized": False, "publishing_authorized": False}
    result["official_domain_authenticity_requires_human_review"] = True
    if not input_path.is_file():
        return {**result, "status": "pending_inputs", "pending_inputs": ["Create program/research-support.json for the actual topic and sources."]}
    result["input"] = {"path": INPUT, "sha256": sha(input_path)}
    try:
        value = read(input_path)
        if value.get("schema_version") != "1.0":
            raise ValueError("research support must use schema_version 1.0")
        requests = _requests(value)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {**result, "status": "blocked", "errors": [str(exc)]}
    datasets = {}
    if value.get("data_availability"):
        try:
            datasets, result["dataset_registry"] = _datasets(project)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            result["errors"].append(str(exc))
    for section, limit in (("clarifications", 30), ("method_dissections", 80), ("data_availability", 80)):
        rows = value.get(section, [])
        if not isinstance(rows, list) or len(rows) > limit:
            result["errors"].append(section + " needs a bounded list")
            continue
        seen = set()
        for row in rows:
            try:
                if not isinstance(row, dict):
                    raise ValueError(section + " entry must be an object")
                identifier = row.get("dataset_id") if section == "data_availability" else row.get("id")
                if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
                    raise ValueError(section + " IDs must be unique and nonempty")
                seen.add(identifier)
                if section == "clarifications":
                    parsed = _clarification(project, row, result["pending_inputs"])
                elif section == "method_dissections":
                    parsed = _method(project, row, result["pending_inputs"])
                else:
                    parsed = _availability(project, row, datasets, requests, current, result["pending_inputs"])
                result[section].append(parsed)
            except (OSError, ValueError, TypeError, KeyError, RuntimeError, SyntaxError, InvalidOperation, OverflowError) as exc:
                result["errors"].append(section + ": " + str(exc))
    if not any(value.get(section) for section in ("clarifications", "method_dissections", "data_availability")):
        result["pending_inputs"].append("No actual-topic clarification, primary-method dissection or availability inputs supplied.")
    # Bind every source nested in the actual report, including full-text scope and
    # calculation records. Saved reports cannot survive source edits unnoticed.
    bindings = {}
    def collect(node):
        if isinstance(node, dict):
            if isinstance(node.get("path"), str) and isinstance(node.get("sha256"), str):
                bindings[node["path"]] = node["sha256"]
            if isinstance(node.get("raw_path"), str):
                bindings[node["raw_path"]] = node.get("raw_sha256")
            for child in node.values():
                collect(child)
        elif isinstance(node, list):
            for child in node:
                collect(child)
    collect(result)
    for row in value.get("method_dissections", []) if isinstance(value.get("method_dissections", []), list) else []:
        if isinstance(row, dict) and isinstance(row.get("scope_record"), dict):
            collect(row["scope_record"])
    if any(row.get("metadata_receipt") for row in result["data_availability"]):
        bindings[INDEX] = sha(path_in(project, INDEX))
    result["source_bindings"] = [{"path": path, "sha256": digest} for path, digest in sorted(bindings.items())]
    result["status"] = "blocked" if result["errors"] else "pending_inputs" if result["pending_inputs"] else "needs_scientific_review"
    return result


def refresh(project: Path) -> dict:
    result = audit(project)
    output = path_in(project, OUTPUT, exists=False)
    write(output, result)
    record(project, [output], "scripts/research_support.py")
    return result


def validate_saved_report(project: Path) -> list[str]:
    if not (project / INPUT).is_file() and not (project / OUTPUT).is_file():
        return []
    try:
        current, saved = audit(project), read(path_in(project, OUTPUT))
        errors = list(current["errors"])
        if current != saved:
            errors.append("research-support report is stale or differs from a clean source-bound rerun")
        return errors
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        return ["cannot validate research support: " + str(exc)]
