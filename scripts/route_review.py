"""Read existing routing evidence at normal and incident boundaries; never call a model."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

from scripts.research_artifacts import path_in, read, sha

ROOT = Path(__file__).resolve().parents[1]
POLICY = "config/task-model-policy.json"
RISKS = {"auxiliary": 0, "routine": 1, "scientific": 2, "critical": 3}


def load_policy(root: Path = ROOT) -> dict:
    policy = read(path_in(root, POLICY))
    if policy.get("schema_version") != "1.0" or policy.get("quality_first") is not True:
        raise ValueError("unsupported task-model policy")
    if policy.get("automatic_paid_probes") is not False or policy.get("automatic_paid_retry") is not False:
        raise ValueError("route review cannot authorize paid probes or retries")
    for key, lower, upper in (("normal_review_hours", 1, 168), ("acceptance_review_days", 1, 90), ("recent_request_window", 2, 100)):
        if type(policy.get(key)) is not int or not lower <= policy[key] <= upper:
            raise ValueError("invalid route review window")
    for key in ("latency_regression_ratio", "cost_regression_ratio"):
        if type(policy.get(key)) not in {int, float} or not math.isfinite(policy[key]) or policy[key] <= 1:
            raise ValueError("invalid operational regression ratio")
    tasks = policy.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("task-model policy has no task classes")
    ids = set()
    for row in tasks:
        if (not isinstance(row, dict) or not isinstance(row.get("task_class"), str)
                or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", row["task_class"]) or row["task_class"] in ids
                or not isinstance(row.get("science_risk"), str) or row["science_risk"] not in RISKS
                or not isinstance(row.get("execution"), str) or row["execution"] not in {"deterministic", "cycle", "auxiliary"}
                or not isinstance(row.get("stages"), list) or not row["stages"]):
            raise ValueError("invalid or duplicate task class")
        ids.add(row["task_class"])
    return policy


def classify(task_profile: dict | None, *, stage: str | None = None, root: Path = ROOT) -> dict:
    """Return a task's minimum risk without changing a provider, model or authority."""
    if task_profile is not None and not isinstance(task_profile, dict):
        raise ValueError("task profile must be an object")
    supplied = dict(task_profile or {})
    if set(supplied) - {"task_class", "science_risk", "min_output_tokens", "deadline_seconds", "priority"}:
        raise ValueError("task profile cannot override model, effort, provider or budget")
    for key, maximum in (("min_output_tokens", 32768), ("deadline_seconds", 600)):
        if key in supplied and (type(supplied[key]) is not int or not 1 <= supplied[key] <= maximum):
            raise ValueError("task request limits must be bounded positive integers")
    if not isinstance(supplied.get("priority", "quality"), str) or supplied.get("priority", "quality") not in {"quality", "cost", "latency"}:
        raise ValueError("task priority must be quality, cost or latency")
    task = supplied.get("task_class", "unspecified")
    if not isinstance(task, str):
        raise ValueError("task_class must be text")
    definition = next((row for row in load_policy(root)["tasks"] if row["task_class"] == task), None)
    risk = supplied.get("science_risk", "critical" if stage in {"experiment-execution", "writing-and-review"} else "scientific")
    if not isinstance(risk, str) or risk not in RISKS:
        raise ValueError("invalid science risk")
    understated = definition is not None and RISKS[risk] < RISKS[definition["science_risk"]]
    if understated:
        supplied["science_risk"] = definition["science_risk"]
    else:
        supplied["science_risk"] = risk
    supplied["task_class"] = task
    return {"definition": definition, "effective_task_profile": supplied,
            "risk_floor_applied": understated, "task_known": definition is not None,
            "stage_matches": definition is None or stage is None or stage in definition["stages"]}


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.astimezone(timezone.utc) if result.tzinfo is not None else None


def _number(value):
    return float(value) if type(value) in {int, float} and math.isfinite(value) and value >= 0 else None


def _label(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", value) else "unavailable"


def _identity(row):
    return (_label(row.get("provider")), _label(row.get("requested_model") or row.get("model")),
            _label(row.get("requested_reasoning_effort") or row.get("reasoning_effort") or "unknown"))


def _lines(project, relative, bindings):
    target = path_in(project, relative, exists=False)
    if not target.is_file():
        return []
    bindings.append({"path": relative, "sha256": sha(target)})
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("routing history must contain objects")
    return rows


def _failure(row):
    return (bool(row.get("transport_error")) or bool(row.get("transport_error_type"))
            or row.get("validation_status") in {"source_contract_failed_no_retry", "completion_failed_no_retry"}
            or row.get("completion_status") not in {None, "completed"})


def review(project: Path, *, task_profile: dict | None = None, stage: str | None = None,
           role: str | None = None, catalogs: dict | None = None, quote_hashes: dict | None = None,
           now: datetime | None = None, root: Path = ROOT) -> dict:
    """Sanitized management observations only. Optional current GET observations are not attestations."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("route review needs an aware current time")
    now = now.astimezone(timezone.utc)
    policy = load_policy(root)
    task = classify(task_profile, stage=stage, root=root)
    bindings = [{"path": POLICY, "sha256": sha(path_in(root, POLICY))}]
    triggers = []

    def add(code, severity, **fields):
        triggers.append({"code": code, "severity": severity, **fields})

    if task["risk_floor_applied"]:
        add("task_risk_understated", "incident")
    if not task["stage_matches"]:
        add("task_stage_mismatch", "incident")
    if not task["task_known"]:
        add("task_classification_required", "review_due")
    definition = task["definition"]
    if definition and definition["execution"] == "deterministic":
        add("deterministic_tools_first", "information")
    if task["effective_task_profile"]["science_risk"] == "critical":
        add("critical_quality_floor", "information")
    if task_profile and task_profile.get("min_output_tokens", 0) > 12000:
        add("large_output_envelope_review", "review_due")
    if catalogs is not None and (not isinstance(catalogs, dict) or any(not isinstance(k, str) or not isinstance(v, list) or any(not isinstance(m, str) for m in v) for k, v in catalogs.items())):
        raise ValueError("catalog observations must map providers to exact model IDs")
    if quote_hashes is not None and (not isinstance(quote_hashes, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{64}", v) for k, v in quote_hashes.items())):
        raise ValueError("quote observations must map route keys to quote hashes")
    states, blocking = [], False
    try:
        usage = _lines(project, "state/model-usage.jsonl", bindings)
        decisions = _lines(project, "state/model-route-decisions.jsonl", bindings)
        health = _lines(project, "state/model-health.jsonl", bindings)
        from scripts import model_spend
        spend_path = path_in(project, "state/model-spend-control.json", exists=False)
        if spend_path.is_file():
            bindings.append({"path": "state/model-spend-control.json", "sha256": sha(spend_path)})
        spend = model_spend.read(project)
        reconciled = {r.get("receipt_id") for r in (spend or {}).get("reconciliation_events", [])}
        unknown = [r for r in usage if (r.get("cost_status") in {"unknown_reconcile_required", "estimated_reconcile_required"} or r.get("usage_estimated") is True)
                   and (not r.get("reservation_id") or r["reservation_id"] not in reconciled)]
        if unknown or (spend or {}).get("reservations"):
            blocking = True
            add("billing_reconciliation_required", "blocked", unresolved_request_count=len(unknown), pending_reservation_count=len((spend or {}).get("reservations", {})))
        if spend is None:
            add("spending_authority_unavailable", "blocked")
            blocking = True
        elif spend["authorized_ceiling_cny"] <= spend["spent_cny"]:
            add("existing_budget_exhausted_or_not_authorized", "blocked")
            blocking = True
        accepts_path = path_in(project, "state/dynamic-routing-acceptances.json", exists=False)
        acceptances = []
        if accepts_path.is_file():
            bindings.append({"path": "state/dynamic-routing-acceptances.json", "sha256": sha(accepts_path)})
            document = read(accepts_path)
            if not isinstance(document.get("acceptances"), list) or any(not isinstance(r, dict) for r in document["acceptances"]):
                raise ValueError("acceptances must be objects")
            acceptances = document["acceptances"]
        for accepted in acceptances:
            at = _time(accepted.get("accepted_at"))
            if at is None or (now - at).total_seconds() > policy["acceptance_review_days"] * 86400:
                add("acceptance_review_due", "review_due", candidate_id=_label(accepted.get("candidate_id")))
        baseline_path = path_in(root, "config/model-routing.json")
        bindings.append({"path": "config/model-routing.json", "sha256": sha(baseline_path)})
        baseline = read(baseline_path)["models"]
        identities = {_identity(r) for r in baseline.values()} | {_identity(r) for r in usage}
        for identity in sorted(identities):
            provider, model, effort = identity
            rows = [r for r in usage if _identity(r) == identity and r.get("cache_hit") is not True]
            groups = {}
            for index, row in enumerate(rows):
                groups.setdefault((row.get("run_id", index), row.get("role")), []).append(row)
            groups = dict(list(groups.items())[-policy["recent_request_window"]:])
            rows = [row for group in groups.values() for row in group]
            failed = sum(any(_failure(r) for r in group) for group in groups.values())
            completed = sum(any(r.get("completion_status") == "completed" for r in group) and not any(_failure(r) for r in group) for group in groups.values())
            recent_at = max((at for r in rows if (at := _time(r.get("at"))) is not None), default=None)
            operation_age = (now - recent_at).total_seconds() if recent_at else None
            if operation_age is None or operation_age > policy["normal_review_hours"] * 3600:
                add("normal_operational_review_due", "review_due", provider=provider, model=model, reasoning_effort=effort)
            available = None if catalogs is None or provider not in catalogs else model in catalogs[provider]
            events = [r for r in decisions if _identity(r) == identity and r.get("availability_error")]
            recovered_at = max((at for r in rows if r.get("completion_status") == "completed"
                and not _failure(r) and (at := _time(r.get("at"))) is not None), default=None)
            unresolved_availability = any(_time(r.get("at")) is None or recovered_at is None
                or recovered_at <= _time(r["at"]) for r in events)
            if available is False:
                add("catalog_model_absent", "incident", provider=provider, model=model, generation_sent=False)
            elif available is None and unresolved_availability:
                add("last_catalog_preflight_failed", "incident", provider=provider, model=model, generation_sent=False)
            mismatch = any(r.get("requested_model") and (r.get("reported_model") or r.get("model"))
                           and r["requested_model"] != (r.get("reported_model") or r.get("model")) for r in rows)
            mismatch |= any(r.get("identity_status") in {"missing", "mismatched"} for r in rows)
            if mismatch:
                add("model_identity_review_required", "incident", provider=provider, model=model)
            if failed:
                add("recent_request_failure", "incident", provider=provider, model=model, failed_attempts=failed)
            if any(r.get("quality_regression") is True or r.get("validation_status") == "source_contract_failed_no_retry" for r in rows):
                add("source_quality_review_required", "incident", provider=provider, model=model)
            latencies = [n for r in rows if (n := _number(r.get("duration_seconds"))) is not None and n > 0]
            costs = [n for r in rows if r.get("cost_status") in {"settled_gateway_debit", "settled_usage_receipt"} and (n := _number(r.get("cost_cny"))) is not None]
            if len(latencies) >= 4 and sum(latencies[-2:]) / 2 > sum(latencies[:-2]) / len(latencies[:-2]) * policy["latency_regression_ratio"]:
                add("latency_regression_review", "review_due", provider=provider, model=model)
            if len(costs) >= 4 and sum(costs[-2:]) / 2 > sum(costs[:-2]) / len(costs[:-2]) * policy["cost_regression_ratio"]:
                add("cost_regression_review", "review_due", provider=provider, model=model)
            quote_key = "/".join(identity)
            previous_quote = next((r.get("billing_quote_sha256") for r in reversed(rows) if r.get("billing_quote_sha256")), None)
            if quote_hashes and quote_key in quote_hashes and previous_quote and quote_hashes[quote_key] != previous_quote:
                add("price_contract_changed", "incident", provider=provider, model=model)
            probes = [r for r in health if r.get("provider") == provider and r.get("model") == model]
            latest_probe = probes[-1] if probes else {}
            states.append({"provider": provider, "model": model, "reasoning_effort": effort,
                "catalog_available": available, "catalog_authenticates_upstream_weights": False,
                "recent_unique_attempts": len(groups), "recent_completed_attempts": completed,
                "recent_failed_attempts": failed, "last_request_at": recent_at.isoformat() if recent_at else None,
                "last_explicit_probe_status": _label(latest_probe.get("status")) if latest_probe else "unknown",
                "scientific_quality_verified": False})
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        blocking = True
        add("routing_evidence_unreadable", "blocked", error_type=type(exc).__name__)
    status = "blocked" if blocking else "incident_review" if any(t["severity"] == "incident" for t in triggers) else "review_due" if any(t["severity"] == "review_due" for t in triggers) else "normal"
    return {"schema_version": "1.0", "kind": "route_review", "checked_at": now.isoformat(), "status": status,
        "task": task, "stage": stage, "role": role, "triggers": triggers, "route_states": states,
        "source_bindings": bindings, "paid_calls": 0, "state_changed": False,
        "billing_blocks_new_paid_work": blocking,
        "selection_policy": {"before_generation": "Use existing selector and only current task-accepted compatible routes; preserve quality, family, effort and complete inputs.",
                             "after_possible_billing": "Preserve the attempt, reconcile its charge, then request a separately bounded retry; never automatic fallback POST.",
                             "normal_review": "Read existing receipts and free catalog/quote observations; no extra model judge or recurring paid probe.",
                             "new_models": "Terra, Kimi and new gateway/model versions remain scoped candidates until their actual task evidence is accepted."},
        "authorizes_paid_request": False, "scientific_equivalence_verified": False}

