"""Dated, evidence-bound journal economics and policy; unknown never means free."""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from scripts.research_artifacts import path_in, read, bound_source, write, record, sha

FIELDS = {"apc", "page_charges", "oa_policy", "waivers", "review_time", "submission_url", "ai_policy"}


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
                if name in {"apc", "page_charges"}:
                    amount = item["value"]
                    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or not math.isfinite(amount) or amount < 0 or not item.get("currency") or item.get("tax") not in {"included", "excluded", "unknown"}:
                        raise ValueError("fees need an amount, currency and explicit tax treatment")
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
            "human_policy_review_required": True}


def refresh(project: Path) -> dict:
    value = audit(project)
    output = project / "program/journal-dossier-report.json"
    write(output, value)
    record(project, [output], "scripts/journal_dossier.py")
    return value
