"""Finite follow-up for two clarified synthetic fixtures; no parent mutation.

The owner's existing full-matrix directive covers this validity repair. It is
not a retry of an old paid call, a new model roster, or production acceptance.
Parent results and billing holds remain frozen at an explicitly reviewed blob.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

from scripts import ai_providers, gateway_trial, model_comparison as parent_trial
from scripts import model_comparison_cases_v2 as fixtures
from scripts import model_runtime, relay_billing

ROOT = Path(__file__).resolve().parents[1]
TRIAL = "model-comparison-clarified-20261020"
AUTHORIZATION = "model-comparison-20261020-clarified-baselines"
FILE = TRIAL + ".json"
STATE = parent_trial.STATE
CASE_IDS = ("evidence_conflict_v2", "experiment_design_v2")
MAX_CALLS = 16
MAX_COMBINED_CALLS = 128
RESERVED_NATIVE_PROBE_CALLS = 1


class ClarifiedError(RuntimeError):
    """Controlled, credential-free terminal diagnostic."""


def digest(value):
    return gateway_trial.digest(value)


def blob_json(blob, expected_sha):
    if blob.get("sha") != expected_sha or blob.get("encoding") != "base64":
        raise ClarifiedError("immutable_blob_readback_mismatch")
    try:
        value = json.loads(base64.b64decode(blob["content"]))
    except (KeyError, ValueError, TypeError, UnicodeError):
        raise ClarifiedError("immutable_blob_readback_mismatch") from None
    if not isinstance(value, dict):
        raise ClarifiedError("immutable_blob_readback_mismatch")
    return value


class CloudState(gateway_trial.CloudState):
    """Only the separate clarified file is writable; every write uses file CAS."""
    def __init__(self, token):
        super().__init__(token, branch=STATE)
        self.expected_sha = None
        self.loaded = False

    def load(self):
        ledger, self.expected_sha = super().read(FILE)
        self.loaded = True
        return ledger

    def save(self, ledger):
        if not self.loaded:
            raise ClarifiedError("ledger_read_required")
        raw = (json.dumps(ledger, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
        payload = {"message": TRIAL + ": preserve clarified comparison", "branch": STATE,
                   "content": base64.b64encode(raw).decode()}
        if self.expected_sha:
            payload["sha"] = self.expected_sha
        response = self.api("contents/trial-state/" + FILE, payload, "PUT")
        new_sha = response.get("content", {}).get("sha")
        if not isinstance(new_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", new_sha):
            raise ClarifiedError("ledger_persistence_not_confirmed")
        value = blob_json(self.api("git/blobs/" + new_sha), new_sha)
        if value != ledger:
            raise ClarifiedError("immutable_blob_readback_mismatch")
        self.expected_sha = new_sha


def routes(plan):
    selected = [copy.deepcopy(route) for route in plan["candidates"][:7]
                if route["provider"] != "codekey-gemini"] + copy.deepcopy(plan["focused_settings"])
    if len(selected) != 8 or len({route["id"] for route in selected}) != 8:
        raise ClarifiedError("clarified_cohort_must_be_eight_existing_configurations")
    if len(plan["focused_settings"]) != 2 or any(route["provider"] == "codekey-gemini" for route in selected):
        raise ClarifiedError("clarified_cohort_scope_changed")
    return selected


def scope(plan, parent, parent_sha):
    parent_trial.validate_plan(plan)
    parent_trial.validate_ledger(parent, plan)
    if (not re.fullmatch(r"[0-9a-f]{40}", parent_sha or "")
            or parent.get("status") not in {"closed", "closed_with_holds"}
            or not parent_trial.full_scope(parent)):
        raise ClarifiedError("exact_closed_authorized_parent_required")
    if tuple(item["id"] for item in fixtures.cases()) != CASE_IDS:
        raise ClarifiedError("clarified_fixture_scope_changed")
    selected = routes(plan)
    tasks, quotes = {}, {}
    for route in selected:
        quote = model_runtime.pricing(route["provider"], route["model"])
        quotes[route["id"]] = quote["quote_sha256"]
        for case_id in CASE_IDS:
            item = fixtures.case(case_id)
            if item.get("attachments"):
                raise ClarifiedError("clarified_scope_is_text_only")
            amount = model_runtime.reservation_bound(route["provider"], item["prompt"], item.get("system"),
                route["max_output_tokens"], quote, {}, controlled=True, has_media=False)
            if type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0:
                raise ClarifiedError("invalid_derived_clarified_bound")
            tasks[route["id"] + "|" + case_id] = amount
    if len(tasks) != MAX_CALLS or len(parent["entries"]) + len(tasks) + RESERVED_NATIVE_PROBE_CALLS > MAX_COMBINED_CALLS:
        raise ClarifiedError("combined_fixed_task_limit_exceeded")
    held = round(sum(entry["reserved_ceiling_cny"] for entry in parent["entries"]
                     if entry.get("billing_status") != "settled"), 8)
    actual = round(sum(entry["actual_cost_cny"] for entry in parent["entries"]
                       if entry.get("billing_status") == "settled"), 8)
    ceiling = round(sum(tasks.values()), 8)
    return {"authorization_id": AUTHORIZATION, "parent_blob_sha": parent_sha,
            "parent_ledger_sha256": digest(parent), "parent_attempts": len(parent["entries"]),
            "parent_actual_cost_cny": actual, "parent_outstanding_holds_cny": held,
            "parent_committed_upper_cny": parent_trial.cost(parent),
            "parent_plan_sha256": parent_trial.fingerprint(plan),
            "parent_isolated_providers": sorted(parent.get("isolated_providers", [])),
            "parent_quarantined_candidates": sorted(parent.get("quarantined_candidates", [])),
            "fixture_sha256": digest(fixtures.cases()), "quote_sha256_by_candidate": quotes,
            "task_ceiling_cny": tasks, "ceiling_cny": ceiling,
            "combined_ceiling_cny": round(parent_trial.cost(parent) + ceiling, 8),
            "max_calls": MAX_CALLS, "max_combined_calls": MAX_COMBINED_CALLS,
            "reserved_native_probe_calls": RESERVED_NATIVE_PROBE_CALLS,
            "configurations": selected}


def cost(ledger):
    return parent_trial.cost(ledger)


def new_ledger(contract, parent):
    return {"trial_id": TRIAL, "authorization_id": AUTHORIZATION,
            "authorization": "The owner's full fixed-matrix directive includes this bounded repair of two ambiguous evaluation fixtures; no original responses or scores are overwritten.",
            "scope": copy.deepcopy(contract), "entries": [], "status": "running",
            "started_at": parent_trial.now(), "isolated_providers": list(parent.get("isolated_providers", [])),
            "quarantined_candidates": list(parent.get("quarantined_candidates", [])),
            "production_routing_changed": False, "scientific_equivalence_verified": False,
            "paid_model_judges": 0, "generation_retries": 0}


def validate(ledger, contract):
    if (ledger.get("trial_id") != TRIAL or ledger.get("authorization_id") != AUTHORIZATION
            or ledger.get("scope") != contract or not isinstance(ledger.get("entries"), list)):
        raise ClarifiedError("clarified_authorization_or_scope_changed_do_not_reset")
    if (not set(contract["parent_isolated_providers"]).issubset(ledger.get("isolated_providers", []))
            or not set(contract["parent_quarantined_candidates"]).issubset(ledger.get("quarantined_candidates", []))):
        raise ClarifiedError("parent_route_isolation_must_be_preserved")
    selected = {route["id"]: route for route in contract["configurations"]}
    seen = set()
    for entry in ledger["entries"]:
        call_id = entry.get("call_id")
        route = selected.get(entry.get("candidate_id"))
        if call_id in seen or call_id not in contract["task_ceiling_cny"] or route is None:
            raise ClarifiedError("duplicate_or_unapproved_clarified_attempt")
        seen.add(call_id)
        case_id = entry.get("case_id")
        if (case_id not in CASE_IDS or call_id != route["id"] + "|" + case_id
                or entry.get("case_sha256") != digest(fixtures.case(case_id))
                or any(entry.get(key) != route[key] for key in ("provider", "model", "effort"))
                or entry.get("quote_sha256") != contract["quote_sha256_by_candidate"][route["id"]]):
            raise ClarifiedError("clarified_attempt_binding_changed")
        amount = entry.get("reserved_ceiling_cny")
        if (type(amount) not in (int, float) or not math.isfinite(amount)
                or amount <= 0 or amount > contract["task_ceiling_cny"][call_id]):
            raise ClarifiedError("invalid_clarified_reservation")
        if entry.get("billing_status") == "settled":
            actual = entry.get("actual_cost_cny")
            if (type(actual) not in (int, float) or not math.isfinite(actual)
                    or not 0 <= actual <= amount or not entry.get("debit_evidence")):
                raise ClarifiedError("invalid_independent_clarified_debit")
    if (len(seen) > MAX_CALLS or contract["parent_attempts"] + len(seen) > MAX_COMBINED_CALLS
            or cost(ledger) > contract["ceiling_cny"] + 1e-8):
        raise ClarifiedError("clarified_or_combined_cap_exceeded")


def run_one(ledger, route, case_id, persist):
    call_id = route["id"] + "|" + case_id
    if any(entry["call_id"] == call_id for entry in ledger["entries"]):
        return "already_attempted"
    if route["provider"] in ledger["isolated_providers"] or route["id"] in ledger["quarantined_candidates"]:
        return "isolated_no_generation"
    contract = ledger["scope"]
    if call_id not in contract["task_ceiling_cny"]:
        raise ClarifiedError("attempt_outside_clarified_scope")
    try:
        before = parent_trial.read_meter(route["provider"])
    except relay_billing.BillingReconciliationError:
        ledger.setdefault("metadata_skips", []).append({"call_id": call_id, "reason": "pre_call_meter_unavailable_no_generation"})
        persist(ledger)
        return "metadata_unavailable_no_generation"
    item = fixtures.case(case_id)
    entry = {"call_id": call_id, "candidate_id": route["id"],
             "provider": route["provider"], "model": route["model"], "effort": route["effort"],
             "case_id": case_id, "case_sha256": digest(item),
             "quote_sha256": contract["quote_sha256_by_candidate"][route["id"]],
             "reserved_ceiling_cny": contract["task_ceiling_cny"][call_id],
             "billing_status": "reserved", "generation_status": "not_sent", "meter_before": before,
             "run_id": os.environ.get("GITHUB_RUN_ID"), "code_sha": os.environ.get("GITHUB_SHA")}
    if len(ledger["entries"]) >= MAX_CALLS or cost(ledger) + entry["reserved_ceiling_cny"] > contract["ceiling_cny"] + 1e-8:
        raise ClarifiedError("clarified_cap_prevented_call")
    ledger["entries"].append(entry)
    persist(ledger)  # Confirmed durable reservation before the single generation POST.
    started = time.monotonic()
    try:
        result = ai_providers.call_production(route["provider"], item["prompt"], system=item.get("system"),
            model=route["model"], reasoning_effort=route["effort"],
            max_output_tokens=route["max_output_tokens"], timeout=route["timeout"])
        secrets = [os.environ.get(spec["key_setting"], "") for spec in ai_providers.PRODUCTION_PROVIDERS.values()]
        entry.update(generation_status="completed", reported_model=result.reported_model,
            request_id=gateway_trial.safe_text(result.request_id or "", secrets),
            text=gateway_trial.safe_text(result.text, secrets), usage=gateway_trial.receipt_numbers(result.usage),
            completion_status=result.completion_status, protocol=result.protocol,
            response_sha256=hashlib.sha256(result.text.encode()).hexdigest(), grade=fixtures.score(case_id, result.text))
    except ai_providers.ProviderError as exc:
        entry.update(generation_status="response_failed", diagnostic=gateway_trial.safe_text(str(exc)))
    except Exception:
        entry.update(generation_status="response_failed", diagnostic="unexpected_response_processing_failure")
    entry["duration_seconds"] = round(time.monotonic() - started, 4)
    persist(ledger)
    try:
        settlement = relay_billing.settle(route["provider"], route["model"], before)
    except relay_billing.BillingReconciliationError as exc:
        entry["billing_diagnostic"] = str(exc)
        if route["provider"] not in ledger["isolated_providers"]:
            ledger["isolated_providers"].append(route["provider"])
        if route["id"] not in ledger["quarantined_candidates"]:
            ledger["quarantined_candidates"].append(route["id"])
        persist(ledger)
        return "unknown_charge_full_hold_retained"
    actual = settlement.get("actual_cost_cny")
    if (type(actual) not in (int, float) or not math.isfinite(actual) or actual < 0
            or not settlement.get("debit_evidence")):
        ledger.update(status="stopped", stop_reason="invalid_independent_debit_full_hold_retained")
        persist(ledger)
        raise ClarifiedError(ledger["stop_reason"])
    entry.update(billing_status="settled", actual_cost_cny=actual,
                 debit_evidence=settlement["debit_evidence"])
    if actual > entry["reserved_ceiling_cny"] or cost(ledger) > contract["ceiling_cny"] + 1e-8:
        ledger.update(status="stopped", stop_reason="actual_debit_exceeded_conservative_bound")
        persist(ledger)
        raise ClarifiedError(ledger["stop_reason"])
    if entry["generation_status"] != "completed" and route["id"] not in ledger["quarantined_candidates"]:
        ledger["quarantined_candidates"].append(route["id"])
    persist(ledger)
    print(json.dumps({"call_id": call_id, "generation": entry["generation_status"],
        "score": entry.get("grade", {}).get("score"), "actual_cost_cny": actual,
        "cohort_committed_cny": cost(ledger)}, ensure_ascii=False), flush=True)
    return entry["generation_status"]


def execute(ledger, contract, persist):
    validate(ledger, contract)
    if ledger.get("status") in {"closed", "closed_with_holds", "stopped"}:
        return
    changed = False
    for entry in ledger["entries"]:
        if entry.get("billing_status") != "settled":
            for key, value in (("isolated_providers", entry["provider"]),
                               ("quarantined_candidates", entry["candidate_id"])):
                if value not in ledger[key]:
                    ledger[key].append(value)
                    changed = True
    if changed:
        persist(ledger)  # Crash recovery cannot put a second call on an uncertain meter.
    metadata_deferred = set()
    for case_id in CASE_IDS:
        for route in contract["configurations"]:
            if route["provider"] in metadata_deferred:
                ledger.setdefault("metadata_skips", []).append({"call_id": route["id"] + "|" + case_id,
                    "reason": "pre_call_meter_unavailable_no_generation",
                    "diagnostic": "same_credential_deferred_for_this_pass_after_exhausted_free_cooldown"})
                continue
            if run_one(ledger, route, case_id, persist) == "metadata_unavailable_no_generation":
                metadata_deferred.add(route["provider"])
    ledger.update(status="closed_with_holds" if any(entry.get("billing_status") != "settled"
        for entry in ledger["entries"]) else "closed", closed_at=parent_trial.now())
    persist(ledger)


def summary(ledger):
    contract = ledger["scope"]
    attempted = {entry["call_id"] for entry in ledger["entries"]}
    unattempted = sorted(set(contract["task_ceiling_cny"]) - attempted)
    return {"trial_id": TRIAL, "status": ledger["status"], "parent_blob_sha": contract["parent_blob_sha"],
        "attempts": len(ledger["entries"]), "combined_attempts": contract["parent_attempts"] + len(ledger["entries"]),
        "expected_tasks": len(contract["task_ceiling_cny"]), "unattempted_tasks": unattempted,
        "all_tasks_attempted": not unattempted,
        "completed_responses": sum(e.get("generation_status") == "completed" for e in ledger["entries"]),
        "cohort_committed_upper_cny": cost(ledger),
        "combined_committed_upper_cny": round(contract["parent_committed_upper_cny"] + cost(ledger), 8),
        "outstanding_holds_cny": round(sum(entry["reserved_ceiling_cny"] for entry in ledger["entries"]
            if entry.get("billing_status") != "settled"), 8),
        "parent_outstanding_holds_cny": contract["parent_outstanding_holds_cny"],
        "finite_cohort_ceiling_cny": contract["ceiling_cny"],
        "parent_unchanged": True, "production_routing_changed": False, "scientific_equivalence_verified": False,
        "rows": [{"candidate_id": entry["candidate_id"], "case_id": entry["case_id"],
                  "grade": entry.get("grade"), "generation_status": entry["generation_status"],
                  "billing_status": entry["billing_status"], "actual_cost_cny": entry.get("actual_cost_cny")}
                 for entry in ledger["entries"]]}


def main():
    env = os.environ
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != gateway_trial.REPO
            or env.get("GITHUB_ACTOR") != "hengyizang" or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or env.get("GITHUB_REF") not in {"refs/heads/main", "refs/heads/" + parent_trial.CODE_BRANCH}
            or env.get("COMPARISON_AUTHORIZATION") != AUTHORIZATION):
        raise ClarifiedError("explicit_owner_cloud_clarified_authorization_required")
    parent_sha = env.get("COMPARISON_EXPECTED_LEDGER_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", parent_sha):
        raise ClarifiedError("exact_parent_blob_required")
    state = CloudState(env["COMPARISON_GITHUB_TOKEN"])
    parent = blob_json(state.api("git/blobs/" + parent_sha), parent_sha)
    plan = json.loads((ROOT / "config/model-comparison-20261020.json").read_text())
    contract = scope(plan, parent, parent_sha)
    ledger = state.load()
    if ledger is None:
        ledger = new_ledger(contract, parent)
        state.save(ledger)
    try:
        execute(ledger, contract, state.save)
    finally:
        report = summary(ledger)
        output = ROOT / ".runtime/model-comparison-clarified-summary.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Clarified comparison stopped: " + (str(exc) if type(exc) is ClarifiedError else type(exc).__name__))
        raise SystemExit(1)
