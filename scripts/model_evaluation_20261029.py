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
CONTINUATION_AUTHORIZATION = TRIAL + "-owner-isolated-continuation-retain-unknown-argon"
CONTINUATION_FILE = "continuation-ledger.json"
ORIGINAL_BLOB = "65406a6cd6344c20ba4ec608ca12b0b8602c1a50"
ORIGINAL_CODE = "7ab623c3d1702d03d171bff3309d0b57a3ef87a1"
ORIGINAL_PLAN_SHA = "99c6bdc51f77c8075a43632507b05eb502c0d014d0fc079bfbb1237d06798ce7"
ORIGINAL_PRICES_SHA = "8a1287ba4aa1560914b03d84719694a53dda1ad0a55a591a3c0659f78c71deb9"
UNKNOWN_ARGON_CALL = "argon-native-high|discriminating-experiment"
UNKNOWN_ARGON_ID = "f705e87ba4514cb99c961768f59f4278"
UNKNOWN_ARGON_CNY = 0.4321632
UNKNOWN_ARGON_TICKET = "381830bce3954c0fbc628b548e2b031e"
DEEPSEEK_LEGACY_ID = "97bdea2e1dd64aaaaa68dfa390e9ec76"
CONTINUATION_ROUTES = ("terra-high", "deepseek-high", "kimi-high", "sol-high")
CONTINUATION_CASES = ("discriminating-experiment", "writing-integrity", "evidence-conflict")
UNSENT_REPAIR_BLOB = "4687efee7987c3ef0bd9749f75e11629555ef2b0"
UNSENT_REPAIR_CODE = "86315b06344078679570e8f301e0ea8166f05b9b"
UNSENT_RESERVATION = "5d63ab62a5f64f66ae40952fc56fadaf"
UNSENT_TICKET = "1e2cda05f6044fe7a87a412dfa33f7b6"


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


def continuation_plan(plan, original, original_blob, active_guard):
    """GET-only proposal; possession of this preview never authorizes transport."""
    validate_plan(plan)
    old = original.get("scope", {})
    if (original_blob != ORIGINAL_BLOB or original.get("trial_id") != TRIAL
            or original.get("status") != "stopped" or old.get("code_sha") != ORIGINAL_CODE
            or old.get("authorization") != AUTHORIZATION or old.get("max_calls") != 40
            or old.get("project_ceiling_cny") != 500 or old.get("project") != "my-phd"
            or old.get("plan_sha256") != ORIGINAL_PLAN_SHA
            or gateway_trial.digest(plan) != ORIGINAL_PLAN_SHA
            or old.get("prices_sha256") != ORIGINAL_PRICES_SHA
            or hashlib.sha256((ROOT / PRICES).read_bytes()).hexdigest() != ORIGINAL_PRICES_SHA
            or old.get("routes") != plan["routes"]
            or original.get("legacy_budget_reservations") != {"gemini": GEMINI_LEGACY_ID, "deepseek": DEEPSEEK_LEGACY_ID}):
        raise ValueError("exact immutable stopped source and unchanged original plan/prices required")
    entries, queue = original.get("entries", []), old.get("queue", [])
    attempted = [row["call_id"] for row in entries]
    if (len(queue) != 39 or len(entries) != 22 or len(set(attempted)) != 22
            or attempted != [row["call_id"] for row in queue[:22]]
            or any(row.get("billing_status") != "settled" for row in entries[:21])):
        raise ValueError("only the exact twenty-one settled attempts plus unknown Argon attempt may be isolated")
    failed = entries[-1]
    if (failed.get("call_id") != UNKNOWN_ARGON_CALL or failed.get("billing_status") != "reserved"
            or failed.get("generation_status") != "failed" or failed.get("provider") != "codekey-gemini"
            or failed.get("project_reservation_id") != UNKNOWN_ARGON_ID
            or failed.get("reserved_ceiling_cny") != UNKNOWN_ARGON_CNY):
        raise ValueError("unknown Argon attempt and its full reservation must remain unchanged")
    active = active_guard.get("active")
    expected_holds = {"44064d7e5133c1c82704269da0095f60541c12e8c24be1560eac5e67920f46e9": .431508,
        "f6da77fa19739e14aedd1e040301f29d85ee7f899c840b2fd7138cc7dc44b5e9": 9.1521024}
    holds = active_guard.get("legacy_holds")
    if (not isinstance(holds, list) or len(holds) != 2 or any(not isinstance(h, dict) for h in holds)
            or {h.get("id"): h.get("reserved_ceiling_cny") for h in holds} != expected_holds):
        raise ValueError("exact historic Gemini holds required; newly discovered unknown charges stop continuation")
    if (active_guard.get("provider") != "codekey-gemini" or not isinstance(active, dict)
            or active.get("id") != UNKNOWN_ARGON_TICKET or active.get("provider") != "codekey-gemini"
            or not re.fullmatch(r"[a-f0-9]{64}", active.get("credential_sha256", ""))
            or active.get("max_cost_cny") != UNKNOWN_ARGON_CNY
            or active.get("run_id") != failed.get("run_id")
            or active.get("scope") != {"trial": TRIAL, "call_id": UNKNOWN_ARGON_CALL,
                "authorization": AUTHORIZATION, "project_reservation_id": UNKNOWN_ARGON_ID,
                "legacy_budget_reservation_id": GEMINI_LEGACY_ID}):
        raise ValueError("exact active Gemini credential ticket must stay isolated and held")
    selected = [row for row in queue if row["route_id"] in CONTINUATION_ROUTES
        and row["case_id"] in CONTINUATION_CASES and row["call_id"] not in attempted]
    expected = {route + "|" + case for route in CONTINUATION_ROUTES for case in CONTINUATION_CASES}
    if len(selected) != 12 or {row["call_id"] for row in selected} != expected:
        raise ValueError("continuation is limited to twelve never-attempted original holdout calls")
    cases = {case["id"]: case for case in plan["cases"]}
    if any(row["case_sha256"] != gateway_trial.digest(cases[row["case_id"]]) for row in selected):
        raise ValueError("original holdout source or instruction changed")
    binding = {"source_blob": ORIGINAL_BLOB, "source_sha256": gateway_trial.digest(original),
        "source_code_sha": ORIGINAL_CODE, "source_plan_sha256": ORIGINAL_PLAN_SHA,
        "source_prices_sha256": ORIGINAL_PRICES_SHA, "original_attempted_call_ids": attempted,
        "original_queue_size": 39, "unknown_reservation_id": UNKNOWN_ARGON_ID,
        "unknown_reserved_cny": UNKNOWN_ARGON_CNY, "active_gemini_ticket": active,
        "gemini_legacy_holds": expected_holds}
    scope = {**old, "authorization": CONTINUATION_AUTHORIZATION, "code_sha": code_revision(),
        "max_calls": 12, "original_binding": binding,
        "routes": [route for route in old["routes"] if route["id"] in CONTINUATION_ROUTES],
        "quotes": {route: old["quotes"][route] for route in CONTINUATION_ROUTES}, "queue": selected}
    return json.loads(json.dumps({"mode": "continue-isolated", "required_owner_authorization": CONTINUATION_AUTHORIZATION,
        "authorization_is_not_granted_by_preview": True, "state_file": CONTINUATION_FILE,
        "original_ledger_will_be_modified": False, "new_request_count": 12,
        "overall_attempts_if_all_sent": len(entries) + len(selected), "original_request_cap": 40,
        "scope": scope}))


class _Continuation:
    """Specific immutable source binding, not a general unknown-cost bypass."""

    def __init__(self, plan, source):
        self.plan, self.source = plan, source
        original, sha = source.read("ledger.json")
        self.preview = continuation_plan(plan, original, sha, relay_guard.inspect("codekey-gemini"))
        self._bind_credentials(self.preview)
        self.scope = self.preview["scope"]

    @staticmethod
    def _bind_credentials(preview):
        binding = preview["scope"]["original_binding"]
        identities = {route["provider"]: relay_guard.fingerprint(route["provider"])
            for route in preview["scope"]["routes"]}
        if binding["active_gemini_ticket"]["credential_sha256"] in identities.values():
            raise ValueError("isolated Gemini credential cannot be reused by any continuation route")
        binding["continuation_credential_sha256"] = identities

    def check(self, budget):
        original, sha = self.source.read("ledger.json")
        current = continuation_plan(self.plan, original, sha, relay_guard.inspect("codekey-gemini"))
        self._bind_credentials(current)
        if current != self.preview:
            raise ValueError("isolated continuation source or credential binding changed")
        control = budget.refresh()
        reservations = control["reservations"]
        if (control.get("authorized_ceiling_cny") != 500
                or set(reservations) != {GEMINI_LEGACY_ID, DEEPSEEK_LEGACY_ID, UNKNOWN_ARGON_ID}
                or reservations[GEMINI_LEGACY_ID].get("kind") != "retained_legacy"
                or reservations[GEMINI_LEGACY_ID].get("max_cost_cny") != GEMINI_LEGACY_CNY
                or reservations[DEEPSEEK_LEGACY_ID].get("kind") != DEEPSEEK_LEGACY_KIND
                or reservations[DEEPSEEK_LEGACY_ID].get("writing_trial") != TRIAL
                or reservations[DEEPSEEK_LEGACY_ID].get("max_cost_cny") != DEEPSEEK_LEGACY_CNY
                or reservations[UNKNOWN_ARGON_ID].get("writing_trial") != TRIAL
                or reservations[UNKNOWN_ARGON_ID].get("call_id") != UNKNOWN_ARGON_CALL
                or reservations[UNKNOWN_ARGON_ID].get("max_cost_cny") != UNKNOWN_ARGON_CNY):
            raise ValueError("retain all three exact full holds; any new unknown cost stops continuation")
        return {"gemini": GEMINI_LEGACY_ID, "deepseek": DEEPSEEK_LEGACY_ID}


class _ContinuationState:
    """Only the separate continuation file can be loaded or saved by execute."""

    def __init__(self, source, initial=None):
        self.source = source
        self.initial = initial

    def load(self, name):
        if name != "ledger.json":
            raise ValueError("unexpected isolated state name")
        if self.initial is not None:
            value, self.initial = self.initial, None
            return value
        return self.source.load(CONTINUATION_FILE)

    def save(self, name, value):
        if name != "ledger.json":
            raise ValueError("unexpected isolated state name")
        return self.source.save(CONTINUATION_FILE, value)


def repair_unstarted(plan, state, context):
    """One reviewed pre-POST failure; preserve its receipt and all real costs."""
    ledger = state.load(CONTINUATION_FILE)
    if not ledger or ledger.get("status") != "stopped" or len(ledger.get("entries", [])) != 2:
        return None
    source, blob = state.read(CONTINUATION_FILE)
    if blob != UNSENT_REPAIR_BLOB:
        return None
    row = ledger["entries"][-1]
    scope = ledger["scope"]
    if (source != ledger or scope.get("code_sha") != UNSENT_REPAIR_CODE
            or {**scope, "code_sha": code_revision()} != context.scope
            or ledger["entries"][0].get("billing_status") != "settled"
            or row.get("call_id") != "deepseek-high|discriminating-experiment"
            or row.get("generation_status") != "not_sent" or row.get("billing_status") != "reserved"
            or row.get("diagnostic") != "shared relay write readback failed"
            or row.get("project_reservation_id") != UNSENT_RESERVATION
            or row.get("code_sha") != UNSENT_REPAIR_CODE or row.get("run_id") != "41027978880"
            or row.get("reserved_ceiling_cny") != .0605584):
        raise ValueError("exact independently reviewed pre-transport interruption required")
    store, name, shared, expected = relay_guard.load("codekey-deepseek", import_legacy=False)
    ticket = shared.get("active")
    marker = {"source_blob": blob, "source_code_sha": UNSENT_REPAIR_CODE,
        "reservation_id": UNSENT_RESERVATION, "ticket_id": UNSENT_TICKET, "generation_sent": False}
    if ticket is not None:
        if (ticket.get("id") != UNSENT_TICKET or ticket.get("provider") != "codekey-deepseek"
                or ticket.get("credential_sha256") != relay_guard.fingerprint("codekey-deepseek")
                or ticket.get("scope", {}).get("project_reservation_id") != UNSENT_RESERVATION
                or ticket.get("scope", {}).get("call_id") != row["call_id"]
                or ticket.get("run_id") != row["run_id"] or ticket.get("max_cost_cny") != row["reserved_ceiling_cny"]
                or "active_meter" in shared):
            raise ValueError("a meter-bound or different request cannot be cancelled as unsent")
        shared["events"].append({"status": "not_sent_recovered", "ticket": ticket, "repair": marker})
        shared["active"] = None
        store.write(name, shared, expected)
    elif not any(event.get("repair") == marker for event in shared.get("events", [])):
        raise ValueError("missing exact unsent shared cancellation receipt")
    budget = writing_comparison.Budget(os.environ["GH_TOKEN"], trial_id=TRIAL)
    control = budget.refresh()
    held = control["reservations"].get(UNSENT_RESERVATION)
    if held is not None:
        if (held.get("call_id") != row["call_id"] or held.get("run_id") != row["run_id"]
                or held.get("writing_trial") != TRIAL or held.get("max_cost_cny") != row["reserved_ceiling_cny"]):
            raise ValueError("unstarted central reservation differs from reviewed failure")
        model_spend.cancel_unsent(budget.root, UNSENT_RESERVATION,
            reason="Immutable pre-POST failure " + blob + "; shared ticket has no bound meter; no generation was authorized.")
        budget.persist()
    elif not any(event.get("receipt_id") == UNSENT_RESERVATION and event.get("generation_sent") is False
            for event in control.get("unsent_events", [])):
        raise ValueError("missing exact central unsent cancellation receipt")
    # Keep the never-sent lease as an event, so its call may be sent ONCE later.
    ledger.setdefault("preflight_events", []).append({"status": "not_sent_recovered", "repair": marker,
        "original_entry": ledger["entries"].pop(), "generation_calls": 0})
    ledger.setdefault("repair_amendments", []).append({**marker, "previous_scope": scope,
        "new_code_sha": code_revision(), "authorization": CONTINUATION_AUTHORIZATION})
    ledger["scope"] = context.scope
    ledger["status"] = "running"
    ledger.pop("stop_reason", None)
    state.save(CONTINUATION_FILE, ledger)
    return ledger


def continue_isolated(plan, state):
    if (os.environ.get("MODEL_EVALUATION_MODE") != "continue-isolated"
            or os.environ.get("MODEL_EVALUATION_AUTHORIZATION") != CONTINUATION_AUTHORIZATION):
        raise ValueError("new exact owner exception required before isolated continuation")
    context = _Continuation(plan, state)
    repaired = repair_unstarted(plan, state, context)
    return execute(plan, _ContinuationState(state, initial=repaired), _continuation=context)


def _legacy_budget(budget, *, _continuation=None):
    if _continuation is not None:
        if type(_continuation) is not _Continuation:
            raise ValueError("invalid isolated continuation binding")
        return _continuation.check(budget)
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


def execute(plan, state, *, _continuation=None):
    env = os.environ
    authorization = AUTHORIZATION
    if _continuation is not None:
        if type(_continuation) is not _Continuation or env.get("MODEL_EVALUATION_MODE") != "continue-isolated":
            raise ValueError("invalid isolated continuation mode")
        authorization = CONTINUATION_AUTHORIZATION
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != gateway_trial.REPO
            or env.get("GITHUB_REF") != "refs/heads/" + BRANCH or env.get("GITHUB_ACTOR") != "hengyizang"
            or env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}
            or env.get("MODEL_EVALUATION_AUTHORIZATION") != authorization):
        raise ValueError("exact owner authorization and cloud evaluation branch required")
    scope = json.loads(json.dumps(_continuation.scope if _continuation is not None else freeze_scope(plan)))
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
    legacy = _legacy_budget(budget, _continuation=_continuation)
    if ledger is None:
        ledger = {"trial_id": TRIAL, "scope": scope, "status": "running", "entries": [],
            "legacy_budget_reservations": legacy, "quarantined_routes": [],
            "authorization_note": ("New owner-authorized isolated continuation; retain original unknown Argon charge in full."
                if _continuation is not None else plan["authorization_note"]), "automatic_promotion": False,
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
        if _legacy_budget(budget, _continuation=_continuation) != legacy:
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
            guard_scope = {"trial": TRIAL, "call_id": call_id,
                "authorization": authorization, "project_reservation_id": receipt,
                "legacy_budget_reservation_id": legacy["deepseek" if provider == "codekey-deepseek" else "gemini"]}
            if _continuation is not None:
                guard_scope.update(continuation_source_blob=ORIGINAL_BLOB, retained_unknown_reservation_id=UNKNOWN_ARGON_ID)
            ticket = relay_guard.begin(provider, scope=guard_scope,
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
        unattempted_call_ids=[row["call_id"] for row in scope["queue"] if row["call_id"] not in attempted])
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
    elif mode in {"execute", "continue-isolated"}:
        plan = json.loads((ROOT / PLAN).read_text(encoding="utf-8"))
        name = CONTINUATION_FILE if mode == "continue-isolated" else "ledger.json"
        try:
            report = continue_isolated(plan, state) if mode == "continue-isolated" else execute(plan, state)
        finally:
            saved = state.load(name)
            if saved is not None:
                export(saved, output)
    else:
        raise ValueError("unknown model evaluation mode")
    print(json.dumps({"mode": mode, "trial_id": TRIAL, "state_branch": STATE,
        "state_file": name, "model_generation_calls": 0 if mode == "metadata" else len(report.get("entries", [])),
        "paid_execution_enabled": mode in {"execute", "continue-isolated"}}))


if __name__ == "__main__":
    main()

