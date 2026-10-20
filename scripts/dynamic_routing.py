"""Deterministic quality-constrained routing; no HTTP, grants or paid retries.

Transport candidates are not accepted routes. Promotion reuses frozen, blinded
review packets with current human judgments and independently settled bills.
The selector never treats a completed response as evidence of scientific quality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts import ai_providers, model_routing, model_spend, output_provenance
    from scripts.research_artifacts import path_in, read, sha, write
except ImportError:
    import ai_providers, model_routing, model_spend, output_provenance  # type: ignore
    from research_artifacts import path_in, read, sha, write  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/model-candidates.json"
ACCEPTANCES = "state/dynamic-routing-acceptances.json"
IDENTITY = ("provider", "model", "family", "reasoning_effort")
RISKS = {"critical", "scientific", "routine", "auxiliary"}
CYCLE = set(model_routing.CYCLE_ROLES) | {"writer"}


class RoutingError(ValueError):
    """Selection cannot safely proceed."""


def enabled() -> bool:
    mode = os.environ.get("DR_OS_DYNAMIC_ROUTING", "production")
    if mode not in {"off", "production"}:
        raise RoutingError("DR_OS_DYNAMIC_ROUTING must be off or production")
    return mode == "production"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_profile(value: Any, *, stage: str | None = None, role: str | None = None) -> dict:
    if value is None:
        risk = "critical" if stage in {"experiment-execution", "writing-and-review"} and role in CYCLE else "scientific" if role in CYCLE else "auxiliary"
        return {"task_class": "unspecified", "science_risk": risk, "priority": "quality"}
    allowed = {"task_class", "science_risk", "min_output_tokens", "deadline_seconds", "priority"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise RoutingError("task profile permits only task class, risk, output need, deadline and priority")
    task = value.get("task_class")
    risk = value.get("science_risk")
    if not isinstance(task, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", task):
        raise RoutingError("task_class must be a lowercase task identifier")
    if not isinstance(risk, str) or risk not in RISKS:
        raise RoutingError("science_risk must be critical, scientific, routine or auxiliary")
    priority = value.get("priority", "quality")
    if not isinstance(priority, str) or priority not in {"quality", "cost", "latency"}:
        raise RoutingError("priority must be quality, cost or latency")
    result = {"task_class": task, "science_risk": risk, "priority": priority}
    for key, ceiling in (("min_output_tokens", 32768), ("deadline_seconds", 600)):
        if key in value:
            if type(value[key]) is not int or not 1 <= value[key] <= ceiling:
                raise RoutingError(f"{key} must be a positive integer up to {ceiling}")
            result[key] = value[key]
    return result


def load_policy() -> tuple[dict, str]:
    if POLICY.is_symlink() or not POLICY.is_file():
        raise RoutingError("candidate registry must be a regular file")
    policy = read(POLICY)
    if set(policy) != {"schema_version", "policy_version", "minimum_paired_cases", "minimum_holdout_cases", "cooldown_seconds", "minimum_cost_improvement", "candidates"} or policy["schema_version"] != "1.0":
        raise RoutingError("unsupported dynamic routing registry")
    for key, minimum in (("minimum_paired_cases", 6), ("minimum_holdout_cases", 3), ("cooldown_seconds", 60)):
        if type(policy[key]) is not int or not minimum <= policy[key] <= 86400:
            raise RoutingError("candidate registry weakens acceptance or cooldown limits")
    if type(policy["minimum_cost_improvement"]) not in {int, float} or not 0.05 <= policy["minimum_cost_improvement"] <= 0.5:
        raise RoutingError("cost improvement hysteresis must be between 5 and 50 percent")
    rows = policy["candidates"]
    if not isinstance(rows, list) or not rows:
        raise RoutingError("candidate registry needs explicit transport candidates")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"candidate_id", *IDENTITY, "context_band", "max_input_bytes", "max_output_tokens", "timeout_seconds", "modalities", "status"}:
            raise RoutingError("malformed transport candidate")
        if row["candidate_id"] in seen or row["status"] != "candidate":
            raise RoutingError("duplicate candidate or attempted registry-only promotion")
        seen.add(row["candidate_id"])
        spec = ai_providers.PRODUCTION_PROVIDERS.get(row["provider"])
        if not spec or row["family"] != spec["family"] or row["model"] not in spec["models"]:
            raise RoutingError("candidate is outside the native transport allowlist")
        if row["reasoning_effort"] not in {"low", "medium", "high"} or row["context_band"] not in {"standard", "long"}:
            raise RoutingError("unknown candidate effort or context band")
        for key, maximum in (("max_input_bytes", 8_000_000), ("max_output_tokens", 32768), ("timeout_seconds", 600)):
            if type(row[key]) is not int or not 1 <= row[key] <= maximum:
                raise RoutingError("unbounded candidate request limits")
        if not isinstance(row["modalities"], list) or not row["modalities"] or set(row["modalities"]) - {"text", "image", "pdf"}:
            raise RoutingError("unknown candidate modalities")
    return policy, sha(POLICY)


def _ledger(project: Path) -> list[dict]:
    target = path_in(project, "state/model-usage.jsonl", exists=False)
    if not target.is_file():
        return []
    try:
        rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (ValueError, UnicodeError) as exc:
        raise RoutingError("usage history is malformed; reconcile before selection") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise RoutingError("usage history must contain objects")
    return rows


def _check_holds(project: Path, rows: list[dict]) -> None:
    state = model_spend.read(project)
    if state and state["reservations"]:
        raise RoutingError("billing reconciliation is required; outstanding reservations block route changes and new paid requests")
    reconciled = {event.get("receipt_id") for event in (state or {}).get("reconciliation_events", [])}
    for row in rows:
        if ((row.get("cost_status") in {"unknown_reconcile_required", "estimated_reconcile_required"}
             or row.get("usage_estimated") is True)
                and (not row.get("reservation_id") or row["reservation_id"] not in reconciled)):
            raise RoutingError("unknown request costs require reconciliation before selection")


def _id(route: dict) -> dict:
    return {key: route.get(key) for key in IDENTITY}


def _profile_for_route(value: dict | None, route: dict) -> dict:
    profile = validate_profile(value, stage=route.get("stage"), role=route.get("role"))
    if (route.get("task_kind") is not None or route.get("role") in model_routing.APPROVED_CRITICAL_TASKS
            or (route.get("stage") in {"topic-intelligence", "paper-architecture", "experiment-design"} and route.get("role") in CYCLE)):
        profile["science_risk"] = "critical"
    return profile


def _origin(project: Path, target: Path, *, authority: bool = False) -> None:
    origin = output_provenance.current_origin(project, target)
    if origin.get("status") != "tracked":
        raise RoutingError("routing evidence needs current hash-bound provenance")
    if authority and (origin.get("family") != "other" or origin.get("provider") != "deterministic-control-plane" or origin.get("model") != "scripts/dynamic_routing.py" or origin.get("role") != "routing-acceptance"):
        raise RoutingError("acceptance must be recorded by the routing control plane")


def _settled_cost(row: dict) -> float | None:
    # This shared parser verifies independent gateway debit identity and amount.
    try:
        from scripts.calibration_analysis import settled_cost
    except ImportError:
        from calibration_analysis import settled_cost  # type: ignore
    return settled_cost(row)


def _evaluate(project: Path, candidate: dict, baseline: dict, profile: dict, packet_id: str,
              rows: list[dict], policy: dict) -> dict:
    try:
        from scripts import calibration_analysis, review_packets
    except ImportError:
        import calibration_analysis, review_packets  # type: ignore
    review_packets.identifier(packet_id)
    summary = calibration_analysis.summarize(project, packet_id)
    snapshot = review_packets.review_snapshot(project, packet_id)
    analysis = path_in(project, f"reports/review-packets/{packet_id}/analysis.json")
    _origin(project, analysis)
    if read(analysis) != summary or summary.get("status") != "descriptive_summary" or summary.get("rater_count", 0) < 2:
        raise RoutingError("refresh the real independently rated calibration summary before acceptance")
    costs = summary.get("costs", {})
    if costs.get("model_cost_coverage_complete") is not True or costs.get("scope_confirmed_by_owner_record") is not True or costs.get("total_cost_status") != "owner_reconciled_cash_scope":
        raise RoutingError("calibration requires complete owner-confirmed actual cost scope")
    answers_path = path_in(project, f"reports/review-packets/{packet_id}/answer-key.json")
    answer = read(answers_path)
    results = {(item["case_label"], item["candidate_label"]): item for item in summary["candidate_results"]}
    selected = {"baseline": [], candidate["candidate_id"]: []}
    paired: dict[str, set] = {}
    paired_scores: dict[str, dict] = {}
    case_sources: dict[str, set[str]] = {}
    evidence_runs = set()
    for keyed in answer["answer_key"]:
        entry = keyed["candidate"]
        channel = entry.get("channel")
        if channel not in selected:
            continue
        expected = baseline if channel == "baseline" else candidate
        if entry.get("routing_identity") != _id(expected):
            raise RoutingError("calibration candidate lacks exact model, channel and effort identity")
        result = results[(keyed["case_label"], keyed["candidate_label"])]
        if result.get("qualified") is not True or result.get("critical_errors"):
            raise RoutingError("every paired calibration and holdout result must pass every quality threshold")
        run_ids = entry.get("run_ids", [])
        if not run_ids or evidence_runs.intersection(run_ids):
            raise RoutingError("each paired candidate requires its own complete billable run IDs")
        evidence_runs.update(run_ids)
        actual = [row for row in rows if row.get("run_id") in run_ids and row.get("cache_hit") is not True
                  and row.get("validation_status") is None]
        if {row.get("run_id") for row in actual} != set(run_ids) or not actual:
            raise RoutingError("calibration run IDs have no complete actual request history")
        for row in actual:
            if (row.get("provider") != expected["provider"] or row.get("model") != expected["model"]
                    or row.get("requested_reasoning_effort") != expected["reasoning_effort"]
                    or row.get("role") != baseline.get("role") or row.get("stage") != baseline.get("stage")
                    or row.get("completion_status") != "completed" or _settled_cost(row) is None):
                raise RoutingError("reviewed runs differ from exact role/transport/effort or have unsettled costs")
        selected[channel].append((result, actual))
        paired.setdefault(keyed["case_id"], set()).add(channel)
        paired_scores.setdefault(keyed["case_id"], {})[channel] = result["scores"]
        case_sources.setdefault(keyed["case_id"], set()).update(source["sha256"] for source in keyed["sources"])
    if len(paired) < policy["minimum_paired_cases"] or any(value != set(selected) for value in paired.values()):
        raise RoutingError("acceptance needs at least six paired, source-independent cases")
    if any(len(value) != len(paired) for value in selected.values()):
        raise RoutingError("duplicate or incomplete paired candidate observations")
    used_sources: set[str] = set()
    for sources in case_sources.values():
        if not sources or used_sources.intersection(sources):
            raise RoutingError("independent calibration cases cannot reuse the same source content")
        used_sources.update(sources)
    for scores in paired_scores.values():
        base_scores, new_scores = scores["baseline"], scores[candidate["candidate_id"]]
        if set(base_scores) != set(new_scores) or any(new_scores[key]["min"] < base_scores[key]["min"] for key in base_scores):
            raise RoutingError("candidate quality cannot be below its paired baseline on any rubric dimension")
    if any(sum(result.get("partition") == "holdout" for result, _ in values) < policy["minimum_holdout_cases"] for values in selected.values()):
        raise RoutingError("acceptance needs at least three frozen holdout cases per route")
    stats = {}
    for channel, values in selected.items():
        calls = [row for _, actual in values for row in actual]
        output = [row.get("max_output_tokens") for row in calls]
        inputs = [row.get("prompt_input_bytes", 0) + sum(media.get("size_bytes", 0) for media in row.get("attachments", [])) for row in calls]
        if any(type(value) is not int or value < 1 for value in output + inputs):
            raise RoutingError("acceptance needs recorded input bytes and output limits")
        latencies = [row.get("duration_seconds") for row in calls]
        known_latency = all(type(value) in {int, float} and math.isfinite(value) and value > 0 for value in latencies)
        stats[channel] = {"accepted_tasks": len(values), "failure_rate": 0.0,
                          "cost_per_accepted_task_cny": sum(_settled_cost(row) or 0 for row in calls) / len(values),
                          "latency_seconds": sum(latencies) / len(values) if known_latency else None,
                          "max_input_bytes": max(inputs), "output_tokens": min(output),
                          "run_ids": sorted(row["run_id"] for row in calls)}
    reviewed = review_packets.audit(project)
    packet_review = next(item for item in reviewed["packets"] if item["id"] == packet_id)
    bindings = [{"path": analysis.relative_to(project).as_posix(), "sha256": sha(analysis)},
                {"path": answers_path.relative_to(project).as_posix(), "sha256": sha(answers_path)},
                snapshot["manifest"], *[{"path": item["path"], "sha256": item["sha256"]} for item in packet_review["confirmations"]]]
    reviewed_rows = [row for row in rows if row.get("run_id") in evidence_runs]
    return {"snapshot_sha256": snapshot["snapshot_sha256"], "bindings": bindings, "statistics": stats,
            "receipt_scope_sha256": digest(reviewed_rows),
            "scope": {"stage": baseline.get("stage"), "role": baseline.get("role"),
                      "task_class": profile["task_class"], "science_risk": profile["science_risk"]}}


def _revalidate(project: Path, accepted: dict, rows: list[dict]) -> None:
    """Check frozen acceptance without invalidating it when unrelated rows append."""
    try:
        from scripts import review_packets
    except ImportError:
        import review_packets  # type: ignore
    packet_id = accepted["packet_id"]
    review_packets.identifier(packet_id)
    snapshot = review_packets.review_snapshot(project, packet_id)
    if snapshot["snapshot_sha256"] != accepted["snapshot_sha256"]:
        raise RoutingError("accepted review packet or its source evidence changed")
    current_reviews = next(item for item in review_packets.audit(project)["packets"] if item["id"] == packet_id)
    expected_reviews = [{"path": item["path"], "sha256": item["sha256"]} for item in current_reviews["confirmations"]]
    frozen_reviews = [item for item in accepted["bindings"] if item["path"].startswith(f"state/review-packet-confirmations/{packet_id}/")]
    if current_reviews.get("status") != "pass" or expected_reviews != frozen_reviews:
        raise RoutingError("independent human review history changed; re-evaluate acceptance")
    for binding in accepted["bindings"]:
        name = binding["path"]
        if not (name.startswith(f"reports/review-packets/{packet_id}/") or name.startswith(f"state/review-packet-confirmations/{packet_id}/")):
            raise RoutingError("acceptance references an unrelated or private file")
        target = path_in(project, name)
        if sha(target) != binding["sha256"]:
            raise RoutingError("accepted analysis or human judgment changed")
        if name.endswith("/analysis.json"):
            _origin(project, target)
    runs = {run for values in accepted["statistics"].values() for run in values["run_ids"]}
    actual = [row for row in rows if row.get("run_id") in runs]
    if digest(actual) != accepted["receipt_scope_sha256"]:
        raise RoutingError("accepted request accounting changed")


def record_acceptance(project: Path, candidate_id: str, baseline_route: dict, *, task_profile: dict,
                      packet_id: str, actor: str) -> dict:
    """Called only by the manager control plane; never by scientific writers."""
    project = Path(project)
    policy, _ = load_policy()
    candidate = next((row for row in policy["candidates"] if row["candidate_id"] == candidate_id), None)
    if candidate is None or not isinstance(actor, str) or not actor.strip():
        raise RoutingError("acceptance requires a registered candidate and named manager")
    profile = _profile_for_route(task_profile, baseline_route)
    if profile["science_risk"] in {"critical", "scientific"} or baseline_route.get("fresh_required"):
        if any(candidate[key] != baseline_route.get(key) for key in ("model", "family", "reasoning_effort")):
            raise RoutingError("scientific acceptance cannot lower the approved model/family/effort floor")
    _available(candidate)
    rows = _ledger(project)
    _check_holds(project, rows)
    evidence = _evaluate(project, candidate, baseline_route, profile, packet_id, rows, policy)
    record = {"candidate_id": candidate_id, "candidate_sha256": digest(candidate),
              "baseline_identity": _id(baseline_route), "packet_id": packet_id, "actor": actor.strip(),
              "accepted_at": datetime.now(timezone.utc).isoformat(), **evidence}
    record["acceptance_sha256"] = digest(record)
    target = path_in(project, ACCEPTANCES, exists=False)
    document = read(target) if target.is_file() else {"schema_version": "1.0", "acceptances": []}
    if target.is_file():
        _origin(project, target, authority=True)
    if document.get("schema_version") != "1.0" or not isinstance(document.get("acceptances"), list):
        raise RoutingError("malformed acceptance registry")
    document["acceptances"] = [item for item in document["acceptances"] if not (item.get("candidate_id") == candidate_id and item.get("scope") == evidence["scope"])] + [record]
    write(target, document)
    output_provenance.record_model_writes(project, [target], family="other", provider="deterministic-control-plane",
                                          model="scripts/dynamic_routing.py", role="routing-acceptance", run_id=packet_id)
    return record


def _available(candidate: dict) -> None:
    configuration = ai_providers.configuration(candidate["provider"])
    if not configuration.get("configured"):
        raise RoutingError("candidate key is not configured")
    if candidate["reasoning_effort"] not in ai_providers.production_supported_efforts(candidate["provider"], candidate["model"]):
        raise RoutingError("candidate effort is not implemented by the native transport")
    try:
        from scripts import model_runtime
    except ImportError:
        import model_runtime  # type: ignore
    quote = model_runtime.pricing(candidate["provider"], candidate["model"], billing_identity=configuration.get("billing_identity"))
    if quote.get("quote_schema") != "2.0" or not quote.get("quote_sha256"):
        raise RoutingError("candidate needs an exact transport/group CNY quote")


def _budget_feasible(project: Path, candidate: dict, baseline: dict, prompt: str, system: str | None,
                     max_output_tokens: int, *, has_media: bool) -> float:
    try:
        from scripts import billing_quotes, model_runtime
    except ImportError:
        import billing_quotes, model_runtime  # type: ignore
    configuration = ai_providers.configuration(candidate["provider"])
    quote = model_runtime.pricing(candidate["provider"], candidate["model"],
                                  billing_identity=configuration.get("billing_identity"))
    tools = model_runtime._billing_configuration("DR_OS_MODEL_TOOL_LIMITS_JSON", candidate["provider"], None)
    limits = billing_quotes.tool_limits(quote, tools)
    bound = model_runtime.reservation_bound(candidate["provider"], prompt, system, max_output_tokens, quote, limits,
                                            controlled=model_spend.read(project) is not None, has_media=has_media)
    paper = model_runtime._paper_for_stage(project, str(baseline.get("stage", "")))
    budget = model_runtime.budget_status(project, paper)
    if bound > budget["project_remaining"] or (paper is not None and bound > budget["paper_remaining"]):
        raise RoutingError("candidate worst-case reservation does not fit the remaining project or paper budget")
    return bound


def choose(project: Path, baseline_route: dict, *, prompt: str, system: str | None = None,
           max_output_tokens: int, timeout: int, attachments: list | None = None,
           task_profile: dict | None = None, baseline_cache_hit: bool = False) -> dict:
    project = Path(project)
    if not isinstance(prompt, str) or (system is not None and not isinstance(system, str)):
        raise RoutingError("selector requires the complete final request text")
    if type(max_output_tokens) is not int or max_output_tokens < 1 or type(timeout) is not int or not 1 <= timeout <= 600:
        raise RoutingError("request output and timeout must be bounded positive integers")
    mode = "production" if enabled() else "off"
    if type(baseline_cache_hit) is not bool:
        raise RoutingError("baseline cache availability must be verified by the runtime")
    profile = _profile_for_route(task_profile, baseline_route)
    route = dict(baseline_route)
    route["max_output_tokens"] = min(max_output_tokens, baseline_route.get("max_output_tokens", max_output_tokens))
    route["timeout"] = min(timeout, profile.get("deadline_seconds", timeout))
    needed = profile.get("min_output_tokens", 1)
    if needed > max_output_tokens:
        raise RoutingError("explicit output requirement exceeds the caller's authorized token ceiling")
    baseline_output_sufficient = route["max_output_tokens"] >= needed
    decision = {"mode": mode, "selected_candidate_id": "baseline", "task_profile": profile,
                "excluded": [], "reason": "approved baseline; no unverified route is tried", "not_scientific_equivalence": True}
    if mode == "off":
        if not baseline_output_sufficient:
            raise RoutingError("explicit output requirement exceeds the approved baseline; adjust the task before calling")
        return {"route": route, "decision": decision}
    policy, policy_sha = load_policy()
    rows = _ledger(project)
    _check_holds(project, rows)
    input_bytes = len(prompt.encode("utf-8")) + len((system or "").encode("utf-8"))
    media = ai_providers.validate_attachments(attachments) if attachments else []
    modalities = {"text"} | ({"pdf" if item.get("mime_type") == "application/pdf" else "text" if item.get("mime_type") == "text/plain" else "image" for item in media} if media else set())
    input_bytes += sum(len(item["decoded"]) for item in media)
    decision.update(input_bytes=input_bytes, history_sha256=digest(rows), policy_sha256=policy_sha,
                    cache_transfer_assumed=False, cooldown_seconds=policy["cooldown_seconds"])
    target = path_in(project, ACCEPTANCES, exists=False)
    records = []
    if target.is_file():
        _origin(project, target, authority=True)
        document = read(target)
        if document.get("schema_version") != "1.0" or not isinstance(document.get("acceptances"), list):
            raise RoutingError("malformed routing acceptance state")
        records = document["acceptances"]
    if baseline_cache_hit and not baseline_route.get("fresh_required") and baseline_output_sufficient:
        decision.update(reason="verified exact approved response cache has zero additional generation cost",
                        selected_policy_sha256=route.get("policy_sha256"))
        return {"route": route, "decision": decision}
    eligible = []
    scope = {"stage": baseline_route.get("stage"), "role": baseline_route.get("role"),
             "task_class": profile["task_class"], "science_risk": profile["science_risk"]}
    recent = [row for row in rows if row.get("stage") == scope["stage"] and row.get("role") == scope["role"]
              and isinstance(row.get("task_profile"), dict) and row["task_profile"].get("task_class") == profile["task_class"]]
    latest = recent[-1] if recent else {}
    def failure(row: dict) -> bool:
        return (bool(row.get("transport_error")) or bool(row.get("transport_error_type")) or row.get("validation_status") in {
            "source_contract_failed_no_retry", "completion_failed_no_retry"}
            or row.get("completion_status") not in {None, "completed"})
    baseline_failures = [row for row in recent if row.get("dynamic_candidate_id") in {None, "baseline"} and failure(row)]
    failed_run_scopes = {(row.get("run_id"), row.get("provider"), row.get("model"), row.get("role")) for row in baseline_failures}
    baseline_completions = [row for row in recent if row.get("dynamic_candidate_id") in {None, "baseline"} and row.get("completion_status") == "completed" and not failure(row)
                            and (row.get("run_id"), row.get("provider"), row.get("model"), row.get("role")) not in failed_run_scopes]
    if len(baseline_failures) >= 2:
        last_failures = baseline_failures[-2:]
        newest_pass = max((row.get("at", "") for row in baseline_completions), default="")
        reviewed_after = max((item.get("accepted_at", "") for item in records if item.get("scope") == scope), default="")
        if newest_pass < last_failures[0].get("at", "") and reviewed_after < last_failures[-1].get("at", ""):
            raise RoutingError("repeated baseline failures require manager review before further paid requests")
    for candidate in policy["candidates"]:
        name = candidate["candidate_id"]
        try:
            required_output = max(route["max_output_tokens"], needed)
            if candidate["max_input_bytes"] < input_bytes or candidate["max_output_tokens"] < required_output or not modalities <= set(candidate["modalities"]):
                raise RoutingError("candidate limits cannot preserve the complete task")
            family = candidate["family"]
            if family == "anthropic" and baseline_route.get("role") not in model_routing.READ_ONLY_ROLES | {"independent-critique"}:
                raise RoutingError("Claude remains limited to read-only scientific planning and independent audits")
            if baseline_route.get("persistent_output") and family != "openai":
                raise RoutingError("persistent scientific writer must remain OpenAI")
            if baseline_route.get("persistent_output") and candidate["model"] not in {"gpt-6.1-sol", "gpt-6-astra"}:
                raise RoutingError("persistent scientific writers remain Sol or Astra")
            if candidate["model"] == "gpt-5.6-luna" and baseline_route.get("role") not in {"metadata-extraction", *model_routing.APPROVED_HEALTH_ROLES}:
                raise RoutingError("Luna remains limited to its validated metadata source-contract role")
            if baseline_route.get("role") in model_routing.READ_ONLY_ROLES and family != "anthropic":
                raise RoutingError("independent planner/critic must remain Anthropic")
            if (profile["science_risk"] in {"critical", "scientific"} or baseline_route.get("task_kind") is not None or baseline_route.get("fresh_required")) and _id(candidate) != _id(baseline_route):
                # For scientific roles only transport/group/context may vary.
                if any(candidate[key] != baseline_route.get(key) for key in ("model", "family", "reasoning_effort")):
                    raise RoutingError("scientific model, family and effort floor cannot be lowered")
            if baseline_route.get("role") == "metadata-extraction" and candidate["model"] != "gpt-5.6-luna":
                raise RoutingError("metadata source-contract route retains its accepted model")
            if baseline_route.get("role") in {"engineering-diagnosis", "engineering-code-review", "engineering-test-design", "engineering-reproducibility"} and candidate["model"] != "deepseek-v4.1-flash":
                raise RoutingError("engineering source-contract role retains its scoped model")
            matching = [item for item in records if item.get("candidate_id") == name and item.get("scope") == scope]
            if len(matching) != 1:
                raise RoutingError("no task-specific manager acceptance with held-out human quality and bills")
            accepted = matching[0]
            if accepted.get("acceptance_sha256") != digest({key: value for key, value in accepted.items() if key != "acceptance_sha256"}) or accepted.get("candidate_sha256") != digest(candidate) or accepted.get("baseline_identity") != _id(baseline_route):
                raise RoutingError("acceptance identity or content changed")
            _revalidate(project, accepted, rows)
            statistics_ = accepted["statistics"][name]
            baseline_stats = accepted["statistics"]["baseline"]
            if input_bytes > statistics_["max_input_bytes"] or required_output > statistics_["output_tokens"]:
                raise RoutingError("task exceeds the actually accepted input/output envelope")
            latency = statistics_["latency_seconds"]
            if profile.get("deadline_seconds") and (latency is None or latency > profile["deadline_seconds"]):
                raise RoutingError("candidate has no accepted latency evidence within the task deadline")
            _available(candidate)
            _budget_feasible(project, candidate, baseline_route, prompt, system, required_output, has_media=bool(media))
            # Never claim cache portability. Paid sample costs include actual cache
            # writes/reads; require a margin to offset switching uncertainty.
            cost = statistics_["cost_per_accepted_task_cny"]
            if cost >= baseline_stats["cost_per_accepted_task_cny"] * (1 - policy["minimum_cost_improvement"]):
                if profile["priority"] != "latency" or latency is None or baseline_stats["latency_seconds"] is None or latency >= baseline_stats["latency_seconds"] * .9 or cost > baseline_stats["cost_per_accepted_task_cny"]:
                    raise RoutingError("no measured accepted-task cost/latency improvement after switching margin")
            at = latest.get("at")
            if at and latest.get("dynamic_candidate_id") not in {None, name}:
                elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(at.replace("Z", "+00:00"))).total_seconds()
                if elapsed < policy["cooldown_seconds"]:
                    raise RoutingError("current route is inside the switching cooldown")
            if any(row.get("dynamic_candidate_id") == name and failure(row)
                   and row.get("at", "") > accepted.get("accepted_at", "") for row in recent[-10:]):
                raise RoutingError("recent incomplete responses suspend this candidate pending review")
            eligible.append((candidate, accepted, statistics_))
        except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
            decision["excluded"].append({"candidate_id": name, "reason": str(exc)})
    if eligible:
        candidate, accepted, stats = min(eligible, key=lambda item: ((item[2]["latency_seconds"] or float("inf")) if profile["priority"] == "latency" else item[2]["cost_per_accepted_task_cny"], item[2]["cost_per_accepted_task_cny"], item[0]["candidate_id"]))
        route.update({key: candidate[key] for key in IDENTITY})
        route["max_output_tokens"] = max(route["max_output_tokens"], needed)
        route["timeout"] = min(candidate["timeout_seconds"], profile.get("deadline_seconds", candidate["timeout_seconds"]))
        identity = {"baseline": baseline_route.get("policy_sha256"), "registry": policy_sha,
                    "candidate": digest(candidate), "acceptance": accepted["acceptance_sha256"], "profile": profile}
        route["policy_sha256"] = digest(identity)
        route["route_id"] = f"dynamic:{candidate['candidate_id']}:{profile['task_class']}:{baseline_route.get('role')}"
        decision.update(selected_candidate_id=candidate["candidate_id"], acceptance_sha256=accepted["acceptance_sha256"],
                        reason="task-specific accepted route improves measured completed-task cost or latency", measured=stats)
    elif not baseline_output_sufficient:
        raise RoutingError("no accepted route satisfies the explicit output requirement; split or review the task")
    decision["selected_policy_sha256"] = route.get("policy_sha256")
    return {"route": route, "decision": decision}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("--project", required=True)
    accept = commands.add_parser("accept")
    for name in ("project", "candidate-id", "packet-id", "profile-file", "expected-profile-sha256", "stage", "role", "actor"):
        accept.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.project):
        parser.error("project must be an existing project identifier")
    project = ROOT / "projects" / args.project
    if not project.is_dir() or project.is_symlink():
        parser.error("project is missing or is a symlink")
    policy, policy_sha = load_policy()
    if args.command == "status":
        target = path_in(project, ACCEPTANCES, exists=False)
        print(json.dumps({"mode": os.environ.get("DR_OS_DYNAMIC_ROUTING", "production"), "policy_sha256": policy_sha,
                          "candidate_count": len(policy["candidates"]), "candidates": policy["candidates"],
                          "acceptances": read(target) if target.is_file() else None,
                          "paid_calls_executed": 0, "scientific_equivalence_verified": False}, indent=2))
        return 0
    target = path_in(project, args.profile_file)
    if sha(target) != args.expected_profile_sha256:
        parser.error("task profile hash changed")
    profile = validate_profile(read(target), stage=args.stage, role=args.role)
    task_kind = model_routing.effective_task_kind(args.stage, args.role, None, profile)
    baseline = model_routing.select(args.stage, args.role, task_kind)
    print(json.dumps(record_acceptance(project, args.candidate_id, baseline, task_profile=profile,
                                       packet_id=args.packet_id, actor=args.actor), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
