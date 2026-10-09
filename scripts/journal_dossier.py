"""Dated, evidence-bound journal economics and policy; unknown never means free."""
from __future__ import annotations

import math
import hashlib
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from scripts.research_artifacts import path_in, read, bound_source, write, record, sha

FIELDS = {"apc", "page_charges", "oa_policy", "waivers", "review_time", "submission_url", "ai_policy"}


def fetch_sources(project: Path, fetcher=None) -> dict:
    """Bounded public GETs; no search/model API, login or paid service."""
    from scripts.network_safety import fetch_bytes
    from scripts.direction_evidence import PageText, canonical_url
    fetcher = fetcher or fetch_bytes
    dossier = read(path_in(project, "program/journal-dossiers.json"))
    ledger_path = project / "evidence/journal-sources/index.json"
    ledger = read(ledger_path) if ledger_path.is_file() else {"schema_version": "1.0", "sources": {}}
    requests = {}
    for row in dossier.get("journals", []):
        domains = set(row.get("official_domains", []))
        for item in row.get("fields", {}).values():
            if item.get("url"):
                url = canonical_url(item["url"])
                if urlsplit(url).hostname not in domains:
                    raise ValueError("journal URL is outside the declared publisher domains")
                requests[url] = domains
    if len(requests) > 140:
        raise ValueError("journal source plan exceeds the 140-URL project ceiling")
    fetched, pending = 0, []
    for url, domains in sorted(requests.items()):
        old = ledger["sources"].get(url, {})
        if old.get("status") == "unavailable":
            try:
                failure_age = datetime.now(timezone.utc) - datetime.fromisoformat(old["retrieved_at"])
                if timedelta(0) <= failure_age < timedelta(hours=6):
                    pending.append(url)
                    continue
            except (KeyError, ValueError):
                pass
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(old["retrieved_at"])
            if timedelta(0) <= age < timedelta(days=7) and sha(path_in(project, old["path"])) == old["sha256"] and sha(path_in(project, old["raw_path"])) == old["raw_sha256"]:
                continue
        except (KeyError, OSError, ValueError):
            pass
        if fetched >= 20:
            pending.append(url)
            continue
        fetched += 1
        try:
            payload, final_url, status, mime = fetcher(url, max_bytes=1_000_000)
            if status != 200 or urlsplit(final_url).hostname not in domains:
                raise ValueError("journal source retrieval failed or redirected outside the publisher domains")
            body = payload.decode("utf-8", errors="replace")
            parser = PageText()
            parser.feed(body)
            text = " ".join(" ".join(parser.parts).split()) if "html" in (mime or "") else body
            identifier = hashlib.sha256((url + hashlib.sha256(payload).hexdigest()).encode()).hexdigest()
            source = path_in(project, f"evidence/journal-sources/{identifier}.txt", exists=False)
            raw = path_in(project, f"evidence/journal-sources/{identifier}.raw", exists=False)
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(text, encoding="utf-8")
            raw.write_bytes(payload)
            ledger["sources"][url] = {"url": url, "final_url": final_url, "http_status": status,
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "path": source.relative_to(project).as_posix(),
                "sha256": sha(source), "raw_path": raw.relative_to(project).as_posix(), "raw_sha256": sha(raw), "status": "retrieved"}
            record(project, [source, raw], "scripts/journal_dossier.py")
        except (OSError, ValueError, RuntimeError) as exc:
            ledger["sources"][url] = {"url": url, "status": "unavailable", "retrieved_at": datetime.now(timezone.utc).isoformat(), "error": str(exc)[:400]}
    ledger["pending_urls"] = pending
    ledger["fetched_this_operation"] = fetched
    write(ledger_path, ledger)
    record(project, [ledger_path], "scripts/journal_dossier.py")
    return ledger


def audit(project: Path, *, now: datetime | None = None) -> dict:
    current = now or datetime.now(timezone.utc)
    inputs = path_in(project, "program/journal-dossiers.json")
    value = read(inputs)
    registry = path_in(project, "program/venue-candidates.json")
    candidates = {c["venue_id"] for p in read(registry).get("papers", []) for c in p.get("candidates", [])}
    dossiers, errors, seen = [], [], set()
    for row in value.get("journals", []):
        try:
            identifier = row["venue_id"]
            if identifier not in candidates or identifier in seen:
                raise ValueError("journal must be a unique existing verified venue candidate")
            seen.add(identifier)
            official = set(row.get("official_domains", []))
            if not official:
                raise ValueError("journal official publisher domains are required")
            fields = row["fields"]
            if not isinstance(fields, dict) or set(fields) != FIELDS:
                raise ValueError("journal dossier must address every cost, OA, timing and policy field")
            normalized, unknown = {}, []
            for name in sorted(FIELDS):
                item = fields[name]
                if item.get("status") == "unknown":
                    if not item.get("reason"):
                        raise ValueError("unknown journal fields need a reason")
                    normalized[name] = item
                    unknown.append(name)
                    continue
                if item.get("status") != "verified" or "value" not in item:
                    raise ValueError("journal fields are either unknown or verified with a concrete value")
                source = bound_source(project, item["source"])
                url = urlsplit(item["url"])
                if url.scheme != "https" or url.hostname not in official or url.username or url.password:
                    raise ValueError("journal claims need an official HTTPS publisher source")
                checked = datetime.fromisoformat(item["accessed_at"].replace("Z", "+00:00"))
                expires = datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
                if checked.tzinfo is None or expires.tzinfo is None or checked > current + timedelta(minutes=5) or not checked < expires <= checked + timedelta(days=120) or current >= expires:
                    raise ValueError("journal information is future-dated, expired or lacks a bounded refresh period")
                if not item.get("quote") or item["quote"] not in path_in(project, source["path"]).read_text(encoding="utf-8"):
                    raise ValueError("journal value needs a matching quote in the preserved publisher source")
                ledger = read(path_in(project, "evidence/journal-sources/index.json"))
                receipt = ledger.get("sources", {}).get(item["url"], {})
                if (receipt.get("status") != "retrieved" or receipt.get("path") != source["path"]
                        or receipt.get("sha256") != source["sha256"] or receipt.get("retrieved_at") != item["accessed_at"]
                        or sha(path_in(project, receipt["raw_path"])) != receipt["raw_sha256"]):
                    raise ValueError("journal source must match an actual protected retrieval receipt")
                if name in {"apc", "page_charges"}:
                    amount = item["value"]
                    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or not math.isfinite(amount) or amount < 0 or not item.get("currency") or item.get("tax") not in {"included", "excluded", "unknown"}:
                        raise ValueError("fees need an amount, currency and explicit tax treatment")
                    if not re.search(r"(?<![\w.])" + re.escape(f"{amount:g}") + r"(?!\w|\.\d)", item["quote"].replace(",", "")):
                        raise ValueError("fee amount is absent from its publisher quote")
                if name == "oa_policy" and item["value"] not in {"optional", "required", "subscription", "diamond"}:
                    raise ValueError("OA choice must distinguish optional, required, subscription and diamond")
                if name == "review_time" and (not item.get("definition") or not item.get("statistic") or not item.get("historical_period")):
                    raise ValueError("review timing needs its statistic, definition and historical period")
                normalized[name] = {**item, "source": source}
            dossiers.append({"venue_id": identifier, "fields": normalized, "unknown_fields": unknown,
                             "paid_submission_authorized": False, "acceptance_probability": None,
                             "individual_timeline_guaranteed": False})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    return {"schema_version": "1.0", "status": "pass" if not errors else "fail", "journals": dossiers,
            "errors": errors, "input_sha256": sha(inputs), "registry_sha256": sha(registry),
            "human_policy_review_required": True, "publisher_domain_authenticity_requires_human_review": True}


def refresh(project: Path) -> dict:
    value = audit(project)
    output = project / "program/journal-dossier-report.json"
    write(output, value)
    record(project, [output], "scripts/journal_dossier.py")
    return value


def validate_saved_report(project: Path, selected_venue_id: str | None = None) -> list[str]:
    if not (project / "program/journal-dossiers.json").is_file():
        return []  # Existing journal screening remains mandatory without this optional dossier.
    try:
        expected = audit(project)
        saved = read(path_in(project, "program/journal-dossier-report.json"))
        errors = list(expected["errors"])
        if saved != expected:
            errors.append("journal dossier is stale or differs from a fresh source/expiry check")
        if selected_venue_id is not None and selected_venue_id not in {j["venue_id"] for j in expected["journals"]}:
            errors.append("selected venue lacks its dated journal dossier")
        return errors
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [str(exc)]
