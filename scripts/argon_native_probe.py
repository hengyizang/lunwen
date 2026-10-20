"""One explicit diagnostic of the historically verified native Argon base ID.

This is a distinct native contract, not a retry of the failed high alias.
No provider registry or parent ledger is changed. Prior holds remain held.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import time
from scripts import ai_providers, billing_quotes, gateway_trial, model_comparison as parent_trial
from scripts import model_comparison_clarified as clarified, model_comparison_cases as fixtures
from scripts import model_runtime, relay_billing

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = "model-comparison-20261020-argon-base-probe"
FILE = AUTHORIZATION + ".json"
MODEL = "gemini-4-argon"
ENDPOINT = "https://codekey.ai/v1beta/models/gemini-4-argon:generateContent"
CASE = "visual_chart"


class ProbeError(RuntimeError):
    pass


class CloudState(clarified.CloudState):
    def load(self):
        value, self.expected_sha = gateway_trial.CloudState.read(self, FILE)
        self.loaded = True
        return value

    def save(self, ledger):
        if not self.loaded:
            raise ProbeError("ledger_read_required")
        raw = (json.dumps(ledger, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
        body = {"message": AUTHORIZATION + ": preserve one native probe", "branch": parent_trial.STATE,
                "content": base64.b64encode(raw).decode()}
        if self.expected_sha:
            body["sha"] = self.expected_sha
        reply = self.api("contents/trial-state/" + FILE, body, "PUT")
        sha = reply.get("content", {}).get("sha")
        if not isinstance(sha, str) or not re.fullmatch("[a-f0-9]{40}", sha):
            raise ProbeError("probe_write_not_verified")
        if clarified.blob_json(self.api("git/blobs/" + sha), sha) != ledger:
            raise ProbeError("probe_write_not_verified")
        self.expected_sha = sha


def quote():
    prices = json.loads((ROOT / "config/model-pricing.json").read_text())
    raw = next(dict(q) for q in prices["quotes"]
               if q["provider"] == "codekey-gemini" and q["model"] == "gemini-4-argon-high")
    # Historical base transport used these same conservative rates. Keep an
    # explicit base quote; never pretend the high and base API IDs are equal.
    raw.update(model=MODEL, endpoint=ENDPOINT, price_version=raw["price_version"] + "-explicit-native-base-probe")
    return billing_quotes.select({"schema_version": "2.0", "quotes": [raw]},
        "codekey-gemini", ENDPOINT, MODEL, {"plan": "production", "group": "codekey-gemini", "mode": "standard"})


def contract(parent, parent_sha, sibling_attempts):
    if parent.get("status") not in {"closed", "closed_with_holds"} or not parent_trial.full_scope(parent):
        raise ProbeError("closed_authorized_parent_required")
    if len(parent["entries"]) + sibling_attempts + 1 > 128:
        raise ProbeError("combined_attempt_cap")
    item = fixtures.case(CASE)
    price = quote()
    ceiling = model_runtime.reservation_bound("codekey-gemini", item["prompt"], item["system"],
        8192, price, {}, controlled=True, has_media=bool(item.get("attachments")))
    return {"authorization_id": AUTHORIZATION, "parent_blob_sha": parent_sha,
        "parent_ledger_sha256": parent_trial.digest(parent), "parent_attempts": len(parent["entries"]),
        "sibling_attempts": sibling_attempts, "max_combined_attempts": 128,
        "parent_committed_upper_cny": parent_trial.cost(parent),
        "parent_argon_holds": [e for e in parent["entries"] if e["provider"] == "codekey-gemini"
                               and e.get("billing_status") != "settled"],
        "model": MODEL, "provider": "codekey-gemini", "endpoint": ENDPOINT, "effort": "high",
        "case_id": CASE, "case_sha256": parent_trial.digest(item), "quote_sha256": price["quote_sha256"],
        "reserved_ceiling_cny": ceiling, "max_fresh_calls": 1}


def execute(ledger, scope, persist):
    if ledger.get("authorization_id") != AUTHORIZATION or ledger.get("scope") != scope:
        raise ProbeError("probe_authorization_changed_do_not_reset")
    if ledger.get("entries"):
        return  # One durable attempt forever, even if its response was lost.
    item = fixtures.case(CASE)
    before = parent_trial.read_meter("codekey-gemini")
    entry = {"call_id": "native-argon-base-high|" + CASE, "requested_model": MODEL,
             "effort": "high", "endpoint": ENDPOINT, "case_sha256": scope["case_sha256"],
             "reserved_ceiling_cny": scope["reserved_ceiling_cny"], "billing_status": "reserved",
             "generation_status": "not_sent", "meter_before": before,
             "run_id": os.environ.get("GITHUB_RUN_ID"), "code_sha": os.environ.get("GITHUB_SHA")}
    ledger["entries"].append(entry)
    persist(ledger)
    start = time.monotonic()
    try:
        key = os.environ[ai_providers.PRODUCTION_PROVIDERS["codekey-gemini"]["key_setting"]].strip()
        parts = [{"text": item["prompt"]}] + [{"inlineData": {
            "mimeType": media["mime_type"], "data": media["data_base64"]}}
            for media in item.get("attachments", [])]
        payload = {"contents": [{"role": "user", "parts": parts}],
            "systemInstruction": {"parts": [{"text": item["system"]}]},
            "generationConfig": {"maxOutputTokens": 8192, "thinkingConfig": {"thinkingLevel": "HIGH"}},
            "tools": []}
        data = ai_providers._production_request(ENDPOINT, {"x-goog-api-key": key}, payload, 180)
        reported = ai_providers._production_identity(MODEL, data.get("modelVersion"))
        text, status = ai_providers._google_text(data)
        if status != "completed":
            raise ai_providers.ProviderError("native base probe incomplete; retain hold")
        usage = ai_providers._production_usage(data, "google")
        secrets = [os.environ.get(s["key_setting"], "") for s in ai_providers.PRODUCTION_PROVIDERS.values()]
        entry.update(generation_status="completed", reported_model=reported,
            text=gateway_trial.safe_text(text, secrets), usage=gateway_trial.receipt_numbers(usage),
            response_sha256=hashlib.sha256(text.encode()).hexdigest(), grade=fixtures.score(CASE, text),
            native_completion=status)
    except ai_providers.ProviderError as exc:
        entry.update(generation_status="response_failed", diagnostic=gateway_trial.safe_text(str(exc)))
    entry["duration_seconds"] = round(time.monotonic() - start, 4)
    persist(ledger)
    try:
        after = parent_trial.read_meter("codekey-gemini")
        entry["meter_after"] = after
        if (after["requests"] == before["requests"] + 1 and after["cost_cny"] >= before["cost_cny"]):
            entry["observed_cost_delta_cny"] = round(after["cost_cny"] - before["cost_cny"], 12)
            if not scope["parent_argon_holds"]:
                amount = entry["observed_cost_delta_cny"]
                if amount > entry["reserved_ceiling_cny"]:
                    raise ProbeError("observed_cost_exceeded_hold")
                entry.update(billing_status="settled", actual_cost_cny=amount,
                             debit_evidence={"before": before, "after": after,
                                 "source": "https://codekey.ai/v1/usage", "exactly_one_new_gateway_request": True})
            else:
                entry["billing_diagnostic"] = "aggregate_delta_not_attributed_while_prior_same_key_hold_exists"
        else:
            entry["billing_diagnostic"] = "no_unique_new_gateway_debit"
    except relay_billing.BillingReconciliationError:
        entry["billing_diagnostic"] = "meter_unavailable_full_hold_retained"
    ledger["status"] = "closed" if entry["billing_status"] == "settled" else "closed_with_holds"
    ledger["closed_at"] = parent_trial.now()
    persist(ledger)


def main():
    env = os.environ
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != gateway_trial.REPO
            or env.get("GITHUB_ACTOR") != "hengyizang" or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or env.get("GITHUB_REF") not in {"refs/heads/main", "refs/heads/" + parent_trial.CODE_BRANCH}
            or env.get("COMPARISON_AUTHORIZATION") != AUTHORIZATION):
        raise ProbeError("explicit_owner_probe_authorization_required")
    sha = env.get("COMPARISON_EXPECTED_LEDGER_SHA", "")
    if not re.fullmatch("[a-f0-9]{40}", sha):
        raise ProbeError("exact_parent_blob_required")
    state = CloudState(env["COMPARISON_GITHUB_TOKEN"])
    parent = clarified.current_parent(state, sha)
    plan = json.loads((ROOT / "config/model-comparison-20261020.json").read_text())
    parent_trial.validate_ledger(parent, plan)
    sibling, _ = gateway_trial.CloudState.read(state, clarified.FILE)
    if (not sibling or sibling.get("status") not in {"closed", "closed_with_holds"}
            or sibling.get("scope", {}).get("parent_blob_sha") != sha):
        raise ProbeError("closed_clarified_sibling_with_same_parent_required")
    sibling_attempts = len(sibling.get("entries", []))
    scope = contract(parent, sha, sibling_attempts)
    ledger = state.load()
    if ledger is None:
        ledger = {"authorization_id": AUTHORIZATION, "scope": scope, "entries": [], "status": "running",
                  "parent_unchanged": True, "production_routing_changed": False}
        state.save(ledger)
    try:
        execute(ledger, scope, state.save)
    finally:
        path = ROOT / ".runtime/argon-native-base-probe.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": ledger["status"], "attempts": len(ledger["entries"]),
            "generation_status": ledger["entries"][0].get("generation_status") if ledger["entries"] else None,
            "parent_unchanged": True}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Argon base probe stopped: " + (str(exc) if isinstance(exc, (ProbeError, gateway_trial.TrialError)) else type(exc).__name__))
        raise SystemExit(1)
