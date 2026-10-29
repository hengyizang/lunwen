"""Cloud metadata for the owner's new model evaluation; no inference in this mode."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.parse

from scripts import ai_providers, catalog_diagnostic, gateway_trial
from scripts import billing_quotes, model_runtime, model_spend
from scripts import production_readiness, relay_billing, relay_guard, writing_comparison

ROOT = Path(__file__).resolve().parents[1]
TRIAL = "model-evaluation-20261029"
BRANCH = "codex/" + TRIAL
STATE = "cloud-state/" + TRIAL
AUTHORIZATION = TRIAL + "-owner-paid-with-legacy-holds"
PROVIDERS = ("cheapai-gpt-pro", "codekey-codex-pro", "codekey-codex-discount",
             "codekey-deepseek", "codekey-gemini", "codekey-kimi")
PLAN = "config/model-evaluation-20261029.json"
PRICES = "config/model-evaluation-pricing-20261029.json"
GEMINI_LEGACY_ID = "2b9e5e82da8a4f0bb9bfb6520ba814d1"
GEMINI_LEGACY_CNY = 9.5836104
DEEPSEEK_LEGACY_CNY = 0.0625758
DEEPSEEK_LEGACY_KIND = "retained_deepseek_legacy"
EXCEPTION_PROVIDERS = {"codekey-gemini", "codekey-gemini-chat", "codekey-deepseek"}


def _safe_error(error):
    keys = [os.environ.get(row["key_setting"], "") for row in ai_providers.PRODUCTION_PROVIDERS.values()]
    return gateway_trial.safe_text(str(error), keys)[:500]


def _meter_summary(value):
    if value.get("kind") == "cheapai_quota_history":
        rows = value.get("rows", [])
        return {key: value[key] for key in ("provider", "kind", "quota_per_unit", "currency_rule")} | {
            "row_count": len(rows), "latest_debits": rows[:8], "full_response_exported": False}
    return value


def _provider_metadata(provider):
    row = {"provider": provider, "generation_calls": 0}
    if provider not in ai_providers.PRODUCTION_PROVIDERS:
        row["configuration_error"] = "provider_not_registered; no generation enabled"
        return row
    try:
        row["configuration"] = ai_providers.configuration(provider, dict(os.environ))
    except (ValueError, KeyError, TypeError) as exc:
        row["configuration_error"] = _safe_error(exc)
    try:
        row["catalog"] = sorted(production_readiness.catalog(provider, dict(os.environ)))
        row["catalog_access_verified"] = True
    except ValueError as exc:
        row["catalog_error"] = _safe_error(exc)
        row["catalog_access_verified"] = False
    try:
        row["meter"] = _meter_summary(relay_billing.read_meter(provider))
    except relay_billing.BillingReconciliationError as exc:
        row["meter_error"] = _safe_error(exc)
    try:
        guard = relay_guard.inspect(provider)
        row["shared_guard"] = {"inference_eligible": guard["inference_eligible"],
            "catalog_access_does_not_release_holds": True,
            "legacy_holds": [{key: hold.get(key) for key in
                ("id", "provider", "requested_model", "reserved_ceiling_cny", "source_branch", "source_file", "source_blob")}
                for hold in guard["legacy_holds"]],
            "active": None if guard["active"] is None else {key: guard["active"].get(key)
                for key in ("id", "provider", "max_cost_cny", "run_id")}}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        row["guard_error"] = _safe_error(exc)
    return row


def metadata(token):
    report = {"schema_version": "1.0", "trial_id": TRIAL, "mode": "metadata",
        "at": datetime.now(timezone.utc).isoformat(), "run_id": os.environ.get("GITHUB_RUN_ID"),
        "code_sha": os.environ.get("GITHUB_SHA"), "model_generation_calls": 0,
        "new_reservations": 0, "production_routing_changed": False,
        "scientific_equivalence_verified": False, "paid_execution_enabled": False}
    budget = writing_comparison.Budget(token)
    try:
        control = budget.refresh()
        held = sum(item["max_cost_cny"] for item in control["reservations"].values())
        report["project_budget"] = {"project": "my-phd", "authorized_ceiling_cny": control["authorized_ceiling_cny"],
            "spent_cny": control["spent_cny"], "held_cny": held,
            "remaining_after_holds_cny": control["authorized_ceiling_cny"] - control["spent_cny"] - held,
            "state_blob": budget.state.expected["model-spend-control.json"],
            "reservations": [{"id": key, "max_cost_cny": value["max_cost_cny"],
                "kind": value.get("kind"), "writing_trial": value.get("writing_trial")}
                for key, value in control["reservations"].items()], "authority_changed": False}
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, gateway_trial.TrialError) as exc:
        report["project_budget_error"] = _safe_error(exc)
    # Every provider operation is an independent metadata GET. No model client,
    # relay reservation or POST transport is invoked by this preparation.
    with ThreadPoolExecutor(max_workers=len(PROVIDERS)) as pool:
        rows = list(pool.map(_provider_metadata, PROVIDERS))
    report["providers"] = {row["provider"]: row for row in rows}
    try:
        report["gemini_catalog_endpoints"] = catalog_diagnostic.report(include_us_host=True)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        report["gemini_catalog_error"] = _safe_error(exc)
    return report


def _state(token):
    state = writing_comparison.State(token, STATE)
    try:
        state.api("git/ref/heads/" + urllib.parse.quote(STATE, safe=""))
    except gateway_trial.TrialError as exc:
        if str(exc) != "http_404":
            raise
        revision = os.environ.get("GITHUB_SHA", "")
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise ValueError("metadata state requires the exact cloud code revision")
        state.api("git/refs", {"ref": "refs/heads/" + STATE, "sha": revision}, "POST")
    return state


def prompt(case):
    return case["instruction"] + "\nBEGIN SOURCE DATA\n" + case["source"] + "\nEND SOURCE DATA"


def validate_plan(plan):
    if (not isinstance(plan, dict) or plan.get("schema_version") != "1.0" or plan.get("trial_id") != TRIAL
            or plan.get("authorization") != AUTHORIZATION or plan.get("project") != "my-phd"
            or plan.get("project_ceiling_cny") != 500 or plan.get("max_calls") != 40
            or plan.get("legacy_budget_reservation_id") != GEMINI_LEGACY_ID
            or plan.get("retained_legacy_hold_cny") != GEMINI_LEGACY_CNY
            or plan.get("automatic_promotion") is not False
            or plan.get("independent_human_ratings_supplied") is not False):
        raise ValueError("exact owner trial, CNY500 authority and preserved legacy reservation required")
    if not isinstance(plan.get("system"), str) or not plan["system"].strip():
        raise ValueError("source-bound shared system instruction required")
    if type(plan.get("max_output_tokens")) is not int or not 1 <= plan["max_output_tokens"] <= 8192:
        raise ValueError("bounded common output limit required")
    cases = plan.get("cases")
    if (not isinstance(cases, list) or len(cases) != 6 or any(not isinstance(c, dict) for c in cases)
            or len({c.get("id") for c in cases if isinstance(c.get("id"), str)}) != 6
            or [c.get("partition") for c in cases].count("calibration") != 3
            or [c.get("partition") for c in cases].count("holdout") != 3):
        raise ValueError("six distinct cases with three calibration and three held-out cases required")
    for case in cases:
        for field in ("id", "task_class", "instruction", "source"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError("each case needs its actual instruction, source and task classification")
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,79}", case["id"]):
            raise ValueError("bounded case ID required")
        checks = case.get("checks")
        if not isinstance(checks, dict) or any(not isinstance(checks.get(k, []), list)
                or any(not isinstance(v, str) or not v for v in checks.get(k, []))
                for k in ("required_fragments", "forbidden_fragments")):
            raise ValueError("invalid mechanical fixture checks")
    routes, seen = plan.get("routes"), set()
    if not isinstance(routes, list) or not 1 <= len(routes) <= 10:
        raise ValueError("explicit finite routes required before paid execution")
    known_cases = {c["id"] for c in cases}
    count = 0
    for route in routes:
        if (not isinstance(route, dict) or set(route) - {"id", "provider", "model", "effort", "case_ids", "max_output_tokens", "timeout"}
                or not isinstance(route.get("id"), str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,79}", route["id"])
                or route["id"] in seen):
            raise ValueError("distinct exact trial routes required")
        seen.add(route["id"])
        provider = route.get("provider")
        if not isinstance(provider, str) or provider not in set(PROVIDERS) | {"codekey-gemini-chat"}:
            raise ValueError("trial provider is outside the owner-selected scope")
        spec = ai_providers.PRODUCTION_PROVIDERS.get(provider)
        if not spec or route.get("model") not in spec["models"]:
            raise ValueError("trial model is not an exact registered provider model")
        if route.get("effort") not in ai_providers.production_supported_efforts(provider, route["model"]):
            raise ValueError("trial effort has no supported exact transport contract")
        selected = route.get("case_ids", list(known_cases))
        if (not isinstance(selected, list) or not selected or any(not isinstance(c, str) for c in selected)
                or len(set(selected)) != len(selected) or not set(selected) <= known_cases):
            raise ValueError("route case selection must be a distinct subset of the frozen six cases")
        for field, default, ceiling in (("max_output_tokens", plan["max_output_tokens"], 8192), ("timeout", 300, 300)):
            if type(route.get(field, default)) is not int or not 1 <= route.get(field, default) <= ceiling:
                raise ValueError("route request limits changed outside the finite trial")
        count += len(selected)
    if count > plan["max_calls"]:
        raise ValueError("frozen trial queue exceeds forty requests")
    return plan


def code_revision():
    revision = os.environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("trial scope requires an exact valid cloud code revision")
    return revision


def freeze_scope(plan):
    validate_plan(plan)
    revision = code_revision()
    prices_path = ROOT / PRICES
    prices = json.loads(prices_path.read_text(encoding="utf-8"))
    quotes, queue = {}, []
    for route in plan["routes"]:
        provider, model = route["provider"], route["model"]
        quote = billing_quotes.select(prices, provider, ai_providers.production_endpoint(provider, model), model,
            {"plan": "production", "group": provider, "mode": "standard"})
        quotes[route["id"]] = quote
    # Case-first order means both advertised Argon diagnostic transports are
    # sampled early; later cases retain the same explicitly frozen route order.
    for case in plan["cases"]:
        for route in plan["routes"]:
            if case["id"] not in route.get("case_ids", [c["id"] for c in plan["cases"]]):
                continue
            tokens = route.get("max_output_tokens", plan["max_output_tokens"])
            ceiling = model_runtime.reservation_bound(route["provider"], prompt(case), plan["system"], tokens,
                quotes[route["id"]], {}, controlled=True)
            if type(ceiling) not in (int, float) or not 0 < ceiling <= 500:
                raise ValueError("one request cannot fit the authorized project ceiling")
            queue.append({"call_id": route["id"] + "|" + case["id"], "route_id": route["id"],
                "case_id": case["id"], "case_sha256": gateway_trial.digest(case),
                "max_output_tokens": tokens, "timeout": route.get("timeout", 300), "reserved_ceiling_cny": ceiling})
    return {"authorization": AUTHORIZATION, "code_sha": revision, "plan_sha256": gateway_trial.digest(plan),
        "prices_sha256": hashlib.sha256(prices_path.read_bytes()).hexdigest(), "max_calls": 40,
        "project": "my-phd", "project_ceiling_cny": 500, "gemini_legacy_reservation_id": GEMINI_LEGACY_ID,
        "gemini_legacy_cny": GEMINI_LEGACY_CNY, "deepseek_legacy_cny": DEEPSEEK_LEGACY_CNY,
        "routes": plan["routes"], "quotes": quotes, "queue": queue,
        "automatic_promotion": False, "independent_human_ratings_supplied": False,
        "scientific_equivalence_verified": False}


def _legacy_budget(budget):
    control = budget.refresh()
    gemini = control["reservations"].get(GEMINI_LEGACY_ID)
    if not gemini or gemini.get("max_cost_cny") != GEMINI_LEGACY_CNY or gemini.get("kind") != "retained_legacy":
        raise ValueError("preserve the exact existing Gemini legacy budget reservation")
    found = [(key, value) for key, value in control["reservations"].items()
        if value.get("writing_trial") == TRIAL and value.get("kind") == DEEPSEEK_LEGACY_KIND]
    if found:
        if len(found) != 1 or found[0][1].get("max_cost_cny") != DEEPSEEK_LEGACY_CNY:
            raise ValueError("DeepSeek legacy reservation changed or duplicated")
        deepseek = found[0][0]
    else:
        # Only this newly acknowledged old DeepSeek hold is added. The historic
        # Gemini reserve is reused, never charged twice or relabeled as spending.
        if set(control["reservations"]) != {GEMINI_LEGACY_ID}:
            raise ValueError("another outstanding project reservation stops new paid work")
        deepseek = budget.reserve(DEEPSEEK_LEGACY_CNY, kind=DEEPSEEK_LEGACY_KIND)
    control = budget.refresh()
    if set(control["reservations"]) != {GEMINI_LEGACY_ID, deepseek}:
        raise ValueError("another outstanding project reservation stops new paid work")
    return {"gemini": GEMINI_LEGACY_ID, "deepseek": deepseek}


def mechanical_checks(case, text):
    checks = case["checks"]
    folded = text.casefold()
    result = {"scope": "mechanical contract checks only, not scientific quality scores",
        "required_fragments": {fragment: fragment.casefold() in folded for fragment in checks.get("required_fragments", [])},
        "forbidden_fragments_absent": {fragment: fragment.casefold() not in folded for fragment in checks.get("forbidden_fragments", [])}}
    if "expected_json" in checks:
        try:
            candidate = text.strip()
            if candidate.startswith("```"):
                candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate)
            value = json.loads(candidate)
            result["expected_json"] = {key: isinstance(value, dict) and key in value
                and type(value[key]) is type(expected) and value[key] == expected
                for key, expected in checks["expected_json"].items()}
        except (ValueError, TypeError):
            result["expected_json"] = {key: False for key in checks["expected_json"]}
    return result


def restore_quarantine(ledger, scope, state):
    """A settled failed attempt remains quarantined across an interrupted save."""
    queue = {row["call_id"]: row for row in scope["queue"]}
    entries = ledger.get("entries", [])
    attempted = [row["call_id"] for row in entries]
    if len(set(attempted)) != len(attempted) or not set(attempted) <= set(queue):
        raise ValueError("duplicate or unapproved attempted IDs; no replay permitted")
    known_routes = {row["id"] for row in scope["routes"]}
    previous = ledger.get("quarantined_routes", [])
    if (not isinstance(previous, list) or any(not isinstance(value, str) for value in previous)
            or not set(previous) <= known_routes):
        raise ValueError("invalid retained route quarantine")
    quarantined = set(previous)
    for entry in entries:
        if entry.get("billing_status") == "settled" and entry.get("generation_status") != "completed":
            identity = queue[entry["call_id"]]["route_id"]
            if entry.get("route_id") != identity:
                raise ValueError("failed attempt differs from its frozen route")
            quarantined.add(identity)
    recovered = [row["id"] for row in scope["routes"] if row["id"] in quarantined]
    if recovered != previous or "quarantined_routes" not in ledger:
        ledger["quarantined_routes"] = recovered
        state.save("ledger.json", ledger)


def execute(plan, state):
    env = os.environ
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != gateway_trial.REPO
            or env.get("GITHUB_REF") != "refs/heads/" + BRANCH or env.get("GITHUB_ACTOR") != "hengyizang"
            or env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}
            or env.get("MODEL_EVALUATION_AUTHORIZATION") != AUTHORIZATION):
        raise ValueError("exact owner authorization and cloud evaluation branch required")
    scope = json.loads(json.dumps(freeze_scope(plan)))
    ledger = state.load("ledger.json")
    if ledger is not None:
        if ledger.get("trial_id") != TRIAL or ledger.get("scope") != scope:
            raise ValueError("frozen trial scope changed; never reset or reopen allowance")
        if ledger.get("status") != "running":
            return ledger
        if any(entry.get("billing_status") != "settled" for entry in ledger.get("entries", [])):
            ledger.update(status="stopped", stop_reason="An unsettled or interrupted new request stops all new paid work.")
            state.save("ledger.json", ledger)
            return ledger
        # A process may have finished independent billing and shared-guard
        # settlement but died before its following quarantine save. Rebuild and
        # persist that consequence before considering any later queue item.
        restore_quarantine(ledger, scope, state)
    budget = writing_comparison.Budget(env["GH_TOKEN"], trial_id=TRIAL)
    legacy = _legacy_budget(budget)
    if ledger is None:
        ledger = {"trial_id": TRIAL, "scope": scope, "status": "running", "entries": [],
            "legacy_budget_reservations": legacy, "quarantined_routes": [],
            "authorization_note": plan["authorization_note"], "automatic_promotion": False,
            "independent_human_ratings_supplied": False, "scientific_equivalence_verified": False,
            "production_routing_changed": False}
        state.save("ledger.json", ledger)
    elif ledger.get("legacy_budget_reservations") != legacy:
        raise ValueError("retained legacy budget bindings changed")
    attempted = {entry["call_id"] for entry in ledger["entries"]}
    if len(attempted) != len(ledger["entries"]) or not attempted <= {row["call_id"] for row in scope["queue"]}:
        raise ValueError("duplicate or unapproved attempted IDs; no replay permitted")
    routes = {row["id"]: row for row in plan["routes"]}
    cases = {row["id"]: row for row in plan["cases"]}
    catalogs = {}
    for request in scope["queue"]:
        call_id = request["call_id"]
        route = routes[request["route_id"]]
        if call_id in attempted or route["id"] in ledger["quarantined_routes"]:
            continue
        if len(ledger["entries"]) >= scope["max_calls"]:
            raise ValueError("trial reached its immutable request cap")
        provider, model, case = route["provider"], route["model"], cases[request["case_id"]]
        try:
            # Re-read exact advertisement before every new POST. No generation
            # is attempted for absent IDs or an unavailable catalog.
            catalogs[provider] = production_readiness.catalog(provider, dict(env))
            if model not in catalogs[provider]:
                raise ValueError("exact requested model is absent from its authenticated current catalog")
            before = relay_billing.read_meter(provider)
        except (ValueError, relay_billing.BillingReconciliationError) as exc:
            ledger["quarantined_routes"].append(route["id"])
            ledger.setdefault("preflight_events", []).append({"route_id": route["id"], "call_id": call_id,
                "status": "not_sent", "diagnostic": _safe_error(exc), "generation_calls": 0})
            state.save("ledger.json", ledger)
            continue
        # Recheck central holds before each reservation. A new ambiguous charge
        # or another process's outstanding request cannot be silently ignored.
        if _legacy_budget(budget) != legacy:
            raise ValueError("project legacy reservation changed during execution")
        receipt = budget.reserve(request["reserved_ceiling_cny"], call_id=call_id)
        entry = {"call_id": call_id, "route_id": route["id"], "case_id": case["id"],
            "task_class": case["task_class"], "partition": case["partition"],
            "case_sha256": request["case_sha256"], "provider": provider, "requested_model": model,
            "requested_effort": route["effort"], "reserved_ceiling_cny": request["reserved_ceiling_cny"],
            "project_reservation_id": receipt, "meter_before": before, "billing_status": "reserved",
            "generation_status": "not_sent", "run_id": env["GITHUB_RUN_ID"], "code_sha": env["GITHUB_SHA"]}
        ledger["entries"].append(entry)
        attempted.add(call_id)
        state.save("ledger.json", ledger)
        ticket = None
        try:
            exception = provider in EXCEPTION_PROVIDERS
            ticket = relay_guard.begin(provider, scope={"trial": TRIAL, "call_id": call_id,
                "authorization": AUTHORIZATION, "project_reservation_id": receipt,
                "legacy_budget_reservation_id": legacy["deepseek" if provider == "codekey-deepseek" else "gemini"]},
                max_cost_cny=request["reserved_ceiling_cny"], evaluation_trial_exception=exception)
            relay_guard.bind_meter(ticket, model, before)
        except (ValueError, OSError, KeyError) as exc:
            entry["diagnostic"] = _safe_error(exc)
            ledger.update(status="stopped", stop_reason="Shared credential reservation failed before transport; preserve central hold.")
            state.save("ledger.json", ledger)
            return ledger
        started = time.monotonic()
        try:
            result = ai_providers.call_production(provider, prompt(case), model=model, system=plan["system"],
                max_output_tokens=request["max_output_tokens"], timeout=request["timeout"], reasoning_effort=route["effort"])
            ai_providers._production_identity(model, result.reported_model)
            if result.completion_status != "completed" or not result.text.strip():
                raise ai_providers.ProviderError("trial response was incomplete; preserve debit and quarantine exact route")
            credentials = [env.get(spec["key_setting"], "") for spec in ai_providers.PRODUCTION_PROVIDERS.values()]
            text = gateway_trial.safe_text(result.text, credentials)
            entry.update(generation_status="completed", text=text, reported_model=result.reported_model,
                usage=gateway_trial.receipt_numbers(result.usage), request_id=gateway_trial.safe_text(result.request_id or "", credentials),
                endpoint=result.endpoint, protocol=result.protocol, completion_status=result.completion_status,
                response_sha256=hashlib.sha256(text.encode()).hexdigest(), mechanical_checks=mechanical_checks(case, text))
        except ai_providers.ProviderError as exc:
            entry.update(generation_status="failed", diagnostic=_safe_error(exc))
            if hasattr(exc, "reported_model"):
                entry["reported_model_unverified"] = gateway_trial.safe_text(exc.reported_model or "missing")
        finally:
            entry["duration_seconds"] = round(time.monotonic() - started, 4)
        state.save("ledger.json", ledger)
        try:
            settlement = relay_billing.settle(provider, model, before)
            entry.update(billing_status="settled", **settlement)
            state.save("ledger.json", ledger)
            budget.settle(receipt, settlement["actual_cost_cny"])
            relay_guard.finish(ticket, settlement)
        except (relay_billing.BillingReconciliationError, model_spend.SpendControlError, relay_guard.RelayGuardError) as exc:
            ledger.update(status="stopped", stop_reason=_safe_error(exc))
            state.save("ledger.json", ledger)
            return ledger
        if entry["generation_status"] != "completed":
            ledger["quarantined_routes"].append(route["id"])
            state.save("ledger.json", ledger)
        print(json.dumps({"call_id": call_id, "generation": entry["generation_status"],
            "actual_cost_cny": entry["actual_cost_cny"], "route_quarantined": route["id"] in ledger["quarantined_routes"]}), flush=True)
    ledger.update(status="closed", completed_at=datetime.now(timezone.utc).isoformat(),
        "unattempted_call_ids": [row["call_id"] for row in scope["queue"] if row["call_id"] not in attempted])
    state.save("ledger.json", ledger)
    return ledger


def export(ledger, destination):
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "execute.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    rows = [{key: row.get(key) for key in ("call_id", "provider", "requested_model", "requested_effort", "reported_model",
        "case_id", "partition", "generation_status", "billing_status", "actual_cost_cny", "reserved_ceiling_cny",
        "duration_seconds", "diagnostic", "mechanical_checks")} for row in ledger.get("entries", [])]
    (destination / "summary.json").write_text(json.dumps({"trial_id": TRIAL, "status": ledger["status"], "entries": rows,
        "unattempted_call_ids": ledger.get("unattempted_call_ids", []), "automatic_promotion": False,
        "scientific_equivalence_verified": False, "independent_human_ratings_supplied": False}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    env = os.environ
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != gateway_trial.REPO
            or env.get("GITHUB_REF") != "refs/heads/" + BRANCH
            or env.get("GITHUB_ACTOR") != "hengyizang"
            or env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}):
        raise ValueError("exact owner repository cloud branch required")
    mode = env.get("MODEL_EVALUATION_MODE", "metadata")
    token = env.get("GH_TOKEN", "")
    if not token:
        raise ValueError("cloud state credential missing")
    state = _state(token)
    output = ROOT / ".runtime" / TRIAL
    if mode == "metadata":
        report = metadata(token)
        output.mkdir(parents=True, exist_ok=True)
        (output / "metadata.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        name = "metadata-" + env["GITHUB_RUN_ID"] + ".json"
        if state.load(name) is not None:
            raise ValueError("an existing metadata receipt cannot be overwritten")
        state.save(name, report)
    elif mode == "execute":
        plan = json.loads((ROOT / PLAN).read_text(encoding="utf-8"))
        try:
            report = execute(plan, state)
        finally:
            saved = state.load("ledger.json")
            if saved is not None:
                export(saved, output)
        name = "ledger.json"
    else:
        raise ValueError("unknown model evaluation mode")
    print(json.dumps({"mode": mode, "trial_id": TRIAL, "state_branch": STATE,
        "state_file": name, "model_generation_calls": 0 if mode == "metadata" else len(report.get("entries", [])),
        "paid_execution_enabled": mode == "execute"}))


if __name__ == "__main__":
    main()

