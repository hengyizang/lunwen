"""New, separately authorized cloud comparison; synthetic tasks only.

No production role change, scientific gate, paid judge, generation retry or
reopening of the closed 20261019 allowance. Every attempted call has a durable
reservation and an independent meter. Unknown charges stop further generation.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time

from scripts import ai_providers, gateway_trial, model_runtime, relay_billing
from scripts import model_comparison_cases as fixtures

ROOT = Path(__file__).resolve().parents[1]
TRIAL = "model-comparison-20261020"
AUTHORIZATION = TRIAL + "-cny30"
STATE = "cloud-state/" + TRIAL
FILE = TRIAL + ".json"
LIMIT = 30.0
MAX_CALLS = 128
CODE_BRANCH = "codex/" + TRIAL


class ComparisonError(RuntimeError):
    """Controlled, credential-free diagnostic."""


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return gateway_trial.digest(value)


class CloudState(gateway_trial.CloudState):
    """Contents API optimistic locking plus durable readback before generation."""

    def __init__(self, token):
        super().__init__(token, branch=STATE)
        self.expected_sha = None
        self.loaded = False

    def load(self):
        value, self.expected_sha = super().read(FILE)
        self.loaded = True
        return value

    def save(self, ledger):
        if not self.loaded:
            raise ComparisonError("ledger_read_required")
        payload = {"message": TRIAL + ": preserve comparison ledger", "branch": STATE,
                   "content": base64.b64encode((json.dumps(ledger, ensure_ascii=False, indent=2,
                                            allow_nan=False) + "\n").encode()).decode()}
        if self.expected_sha:
            payload["sha"] = self.expected_sha
        response = self.api("contents/trial-state/" + FILE, payload, "PUT")
        new_sha = response.get("content", {}).get("sha")
        if not isinstance(new_sha, str):
            raise ComparisonError("ledger_persistence_not_confirmed")
        value, remote_sha = super().read(FILE)
        if remote_sha != new_sha or value != ledger:
            raise ComparisonError("ledger_readback_mismatch_no_generation")
        self.expected_sha = new_sha


def validate_plan(plan):
    if (plan.get("trial_id") != TRIAL or type(plan.get("budget_cny")) is not float
            or plan["budget_cny"] != LIMIT or plan.get("execution") != "github-actions-cloud-only"
            or plan.get("closed_prior_trial_id") != "relay-acceptance-20261019"):
        raise ComparisonError("new_allowance_scope_mismatch")
    routes = plan.get("candidates", []) + plan.get("focused_settings", [])
    if not routes or len(routes) > 30 or len({r["id"] for r in routes}) != len(routes):
        raise ComparisonError("invalid_route_matrix")
    known_cases = {item["id"] for item in fixtures.cases()}
    if (plan.get("screening_cases") != ["evidence_conflict", "experiment_design"]
            or plan.get("focused_cases") != ["scientific_plan", "code_statistics", "claim_precision", "long_context", "visual_chart"]):
        raise ComparisonError("fixture_phase_scope_changed")
    for route in routes:
        spec = ai_providers.PRODUCTION_PROVIDERS.get(route.get("provider"))
        if (spec is None or route.get("model") not in spec["models"]
                or route.get("effort") not in ai_providers.production_supported_efforts(route["provider"], route["model"])
                or route.get("max_output_tokens") != 8192 or route.get("timeout") != 180):
            raise ComparisonError("unapproved_trial_route_or_limits")
        selected = route.get("screening_cases", []) + route.get("focused_cases", [])
        if (not set(selected).issubset(known_cases)
                or route.get("screening_cases") != plan["screening_cases"]
                or len(set(selected)) != len(selected)):
            raise ComparisonError("unknown_fixture")
    return plan


def fingerprint(plan):
    # All task content (including media) is fixed across resumes. A software
    # repair cannot create another allowance or replay an attempted call ID.
    return digest({"plan": plan, "fixtures": fixtures.cases()})


def cost(ledger):
    return round(sum(entry.get("actual_cost_cny", entry["reserved_ceiling_cny"])
                     if entry.get("billing_status") == "settled" else entry["reserved_ceiling_cny"]
                     for entry in ledger["entries"]), 8)


def validate_ledger(ledger, plan):
    if (ledger.get("trial_id") != TRIAL or ledger.get("authorization_id") != AUTHORIZATION
            or ledger.get("limit_cny") != LIMIT or ledger.get("plan_sha256") != fingerprint(plan)
            or not isinstance(ledger.get("entries"), list)):
        raise ComparisonError("ledger_authorization_mismatch_do_not_reset")
    ids = set()
    routes = {r["id"]: r for r in plan["candidates"] + plan.get("focused_settings", [])}
    for entry in ledger["entries"]:
        call_id = entry.get("call_id")
        if call_id in ids or entry.get("candidate_id") not in routes:
            raise ComparisonError("duplicate_or_unknown_attempt")
        ids.add(call_id)
        route = routes[entry["candidate_id"]]
        case_id = entry.get("case_id")
        if (case_id not in route["screening_cases"] + route["focused_cases"]
                or call_id != entry["candidate_id"] + "|" + case_id
                or entry.get("case_sha256") != digest(fixtures.case(case_id))):
            raise ComparisonError("attempt_fixture_binding_changed")
        if any(entry.get(k) != route[k] for k in ("provider", "model", "effort")):
            raise ComparisonError("attempt_route_changed")
        amount = entry.get("reserved_ceiling_cny")
        if type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0:
            raise ComparisonError("invalid_reservation")
        if entry.get("billing_status") == "settled":
            actual = entry.get("actual_cost_cny")
            if (type(actual) not in (int, float) or not math.isfinite(actual) or actual < 0
                    or not entry.get("debit_evidence")):
                raise ComparisonError("invalid_settlement")
    if len(ids) > MAX_CALLS or cost(ledger) > LIMIT + 1e-8:
        raise ComparisonError("trial_cap_exceeded")
    return ledger


def new_ledger(plan):
    return {"schema_version": "1.0", "trial_id": TRIAL, "authorization_id": AUTHORIZATION,
            "authorization": plan["authorization"], "limit_cny": LIMIT,
            "plan_sha256": fingerprint(plan), "started_at": now(), "entries": [],
            "status": "running", "production_routing_changed": False,
            "scientific_completion": False, "paid_model_judges": 0}


def reserve(ledger, entry, persist, *, phase_limit=LIMIT):
    if any(e["call_id"] == entry["call_id"] for e in ledger["entries"]):
        return False
    if any(e.get("billing_status") != "settled" for e in ledger["entries"]):
        raise ComparisonError("unknown_charge_blocks_new_generation")
    amount = entry["reserved_ceiling_cny"]
    if type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0:
        raise ComparisonError("invalid_reservation")
    if len(ledger["entries"]) >= MAX_CALLS or cost(ledger) + amount > min(LIMIT, phase_limit):
        return False
    entry.update(billing_status="reserved", reserved_at=now())
    ledger["entries"].append(entry)
    persist(ledger)  # A conflict or failed readback aborts before the model call.
    return True


def settle_entry(ledger, entry, settlement, persist):
    amount = settlement["actual_cost_cny"]
    if type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0:
        raise ComparisonError("invalid_independent_debit")
    if not settlement.get("debit_evidence"):
        raise ComparisonError("independent_debit_required")
    entry.update(billing_status="settled", actual_cost_cny=amount,
                 debit_evidence=settlement["debit_evidence"], reconciled_at=now())
    if amount > entry["reserved_ceiling_cny"] or cost(ledger) > LIMIT:
        ledger["status"] = "stopped"
        ledger["stop_reason"] = "actual_debit_exceeded_reserved_bound"
        persist(ledger)
        raise ComparisonError(ledger["stop_reason"])
    persist(ledger)


def read_meter(provider):
    # Only free metadata may be retried on a rate limit. Generation is never
    # wrapped in a retry loop.
    for index in range(3):
        try:
            return relay_billing.read_meter(provider)
        except relay_billing.BillingReconciliationError as exc:
            if "429" not in str(exc) or index == 2:
                raise
            time.sleep(20)


def reconcile_attempt(ledger, entry, persist):
    # In this serial isolated trial, a single new independent debit is
    # attributable even when the model response was incomplete or lost.
    settlement = relay_billing.settle(entry["provider"], entry["model"], entry["meter_before"])
    settle_entry(ledger, entry, settlement, persist)


def run_one(ledger, route, case_id, phase, persist):
    if route["id"] in ledger.get("quarantined_candidates", []):
        return "quarantined_no_generation"
    item = fixtures.case(case_id)
    call_id = route["id"] + "|" + case_id
    if any(e["call_id"] == call_id for e in ledger["entries"]):
        return "already_attempted"
    media = item.get("attachments") or []
    if media and ai_providers.provider_family(route["provider"]) not in {"openai", "google"}:
        return "unsupported_modality"
    quote = model_runtime.pricing(route["provider"], route["model"])
    ceiling = model_runtime.reservation_bound(route["provider"], item["prompt"], item.get("system"),
        route["max_output_tokens"], quote, {}, controlled=True, has_media=bool(media))
    phase_limit = 18.0 if phase == "screening" else LIMIT
    if cost(ledger) + ceiling > phase_limit:
        return "budget_insufficient_for_conservative_hold"
    try:
        before = read_meter(route["provider"])
    except relay_billing.BillingReconciliationError:
        ledger.setdefault("metadata_skips", []).append({"call_id": call_id, "at": now(),
                                                       "reason": "pre_call_meter_unavailable_no_generation"})
        persist(ledger)
        return "metadata_unavailable_no_generation"
    entry = {"call_id": call_id, "candidate_id": route["id"],
             "provider": route["provider"], "model": route["model"], "effort": route["effort"],
             "case_id": case_id, "phase": phase, "case_sha256": digest(item),
             "quote_sha256": quote["quote_sha256"], "reserved_ceiling_cny": ceiling,
             "meter_before": before, "generation_status": "not_sent",
             "run_id": os.environ.get("GITHUB_RUN_ID"), "code_sha": os.environ.get("GITHUB_SHA")}
    if not reserve(ledger, entry, persist, phase_limit=phase_limit):
        return "budget_or_call_limit"
    started = time.monotonic()
    try:
        result = ai_providers.call_production(route["provider"], item["prompt"],
            system=item.get("system"), model=route["model"], reasoning_effort=route["effort"],
            max_output_tokens=route["max_output_tokens"], timeout=route["timeout"],
            attachments=media or None)
        # Model text is synthetic test output, never a persistent research artifact.
        keys = [os.environ.get(s["key_setting"], "") for s in ai_providers.PRODUCTION_PROVIDERS.values()]
        entry.update(generation_status="completed", reported_model=result.reported_model,
                     request_id=gateway_trial.safe_text(result.request_id or "", keys),
                     text=gateway_trial.safe_text(result.text, keys), usage=gateway_trial.receipt_numbers(result.usage),
                     completion_status=result.completion_status, protocol=result.protocol,
                     response_sha256=hashlib.sha256(result.text.encode()).hexdigest(),
                     grade=fixtures.score(case_id, result.text))
    except ai_providers.ProviderError as exc:
        entry.update(generation_status="response_failed", diagnostic=gateway_trial.safe_text(str(exc)))
        # No retry and no silent alternate route. Preserve the paid attempt.
    except Exception:
        entry.update(generation_status="response_failed", diagnostic="unexpected_response_processing_failure")
    entry["duration_seconds"] = round(time.monotonic() - started, 4)
    persist(ledger)  # Preserve any available response before read-only reconciliation.
    try:
        reconcile_attempt(ledger, entry, persist)
    except relay_billing.BillingReconciliationError:
        ledger.update(status="stopped", stop_reason="unknown_charge_reconciliation_required")
        persist(ledger)
        raise ComparisonError("unknown_charge_reconciliation_required") from None
    if entry["generation_status"] != "completed":
        ledger.setdefault("quarantined_candidates", []).append(route["id"])
    print(json.dumps({"call_id": call_id, "generation": entry["generation_status"],
                      "score": entry.get("grade", {}).get("score"),
                      "actual_cost_cny": entry["actual_cost_cny"],
                      "cumulative_cny": cost(ledger)}, ensure_ascii=False), flush=True)
    return entry["generation_status"]


def qualified(ledger, route):
    rows = [e for e in ledger["entries"] if e["candidate_id"] == route["id"]
            and e["case_id"] in route["screening_cases"]]
    return (len(rows) == len(route["screening_cases"]) and all(
        e.get("billing_status") == "settled" and e.get("generation_status") == "completed"
        and e.get("grade", {}).get("passed") is True for e in rows))


def execute(plan, ledger, persist):
    validate_ledger(ledger, plan)
    if ledger.get("status") in {"closed", "stopped"}:
        return  # Re-dispatch never resets a closed trial or its allowance.
    if any(e.get("billing_status") != "settled" for e in ledger["entries"]):
        raise ComparisonError("unknown_charge_blocks_new_generation")
    # Cover every model/channel once before the second shared screening task.
    for case_id in plan["screening_cases"]:
        for route in plan["candidates"]:
            if route["id"] not in ledger.get("quarantined_candidates", []):
                run_one(ledger, route, case_id, "screening", persist)
    # Focused settings first get the same screens. They cannot inherit another
    # effort's success or become production accepted through this trial.
    for route in plan.get("focused_settings", []):
        for case_id in route["screening_cases"]:
            run_one(ledger, route, case_id, "focused-setting-screen", persist)
    primary = [route for route in plan["candidates"] if route.get("baseline")]
    alternatives = [route for route in plan["candidates"] if not route.get("baseline")] + plan.get("focused_settings", [])
    for pool in (primary, alternatives):
        for case_id in plan["focused_cases"]:
            for route in pool:
                if case_id in route["focused_cases"] and qualified(ledger, route):
                    run_one(ledger, route, case_id, "focused", persist)
    ledger.update(status="closed", closed_at=now(), committed_upper_cny=cost(ledger))
    persist(ledger)


def summary(ledger, plan):
    rows = []
    for route in plan["candidates"] + plan.get("focused_settings", []):
        entries = [e for e in ledger["entries"] if e["candidate_id"] == route["id"]]
        rows.append({"candidate_id": route["id"], "provider": route["provider"],
                     "model": route["model"], "effort": route["effort"], "attempts": len(entries),
                     "complete": sum(e.get("generation_status") == "completed" for e in entries),
                     "settled_cost_cny": round(sum(e.get("actual_cost_cny", 0) for e in entries
                                                   if e.get("billing_status") == "settled"), 8),
                     "screening_passed": qualified(ledger, route),
                     "cases": [{"case_id": e["case_id"], "score": e.get("grade", {}).get("score"),
                                "passed": e.get("grade", {}).get("passed"),
                                "duration_seconds": e.get("duration_seconds"),
                                "billing_status": e.get("billing_status"),
                                "generation_status": e["generation_status"]} for e in entries]})
    return {"trial_id": TRIAL, "status": ledger["status"], "limit_cny": LIMIT,
            "committed_upper_cny": cost(ledger), "attempts": len(ledger["entries"]),
            "stop_reason": ledger.get("stop_reason"), "routes": rows,
            "unattempted_are_unknown_not_failed": True,
            "production_routing_changed": False, "scientific_equivalence_verified": False,
            "limitation": "Small synthetic screening; no human blind review or broad model quality certification."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("execute", "reconcile"), required=True)
    args = parser.parse_args()
    env = os.environ
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != "hengyizang/lunwen"
            or env.get("GITHUB_ACTOR") != "hengyizang" or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or env.get("GITHUB_REF") not in {"refs/heads/main", "refs/heads/" + CODE_BRANCH}):
        raise ComparisonError("explicit_owner_cloud_dispatch_required")
    if args.mode == "execute" and env.get("COMPARISON_AUTHORIZATION") != AUTHORIZATION:
        raise ComparisonError("new_cny30_allowance_confirmation_required")
    plan = validate_plan(json.loads((ROOT / "config/model-comparison-20261020.json").read_text()))
    state = CloudState(env["COMPARISON_GITHUB_TOKEN"])
    ledger = state.load()
    if ledger is None:
        if args.mode != "execute":
            raise ComparisonError("no_existing_trial_to_reconcile")
        ledger = new_ledger(plan)
        state.save(ledger)
    validate_ledger(ledger, plan)
    try:
        if args.mode == "reconcile":
            for entry in ledger["entries"]:
                if entry.get("billing_status") != "settled":
                    reconcile_attempt(ledger, entry, state.save)
            # Reconciliation never reopens or generates. A stopped trial stays stopped.
        else:
            execute(plan, ledger, state.save)
    finally:
        receipt = summary(ledger, plan)
        output = ROOT / ".runtime/model-comparison-summary.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Comparison stopped: " + (str(exc) if type(exc) is ComparisonError else type(exc).__name__))
        raise SystemExit(1)
