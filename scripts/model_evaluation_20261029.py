"""Cloud metadata for the owner's new model evaluation; no inference in this mode."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import urllib.parse

from scripts import ai_providers, catalog_diagnostic, gateway_trial
from scripts import production_readiness, relay_billing, relay_guard, writing_comparison

ROOT = Path(__file__).resolve().parents[1]
TRIAL = "model-evaluation-20261029"
BRANCH = "codex/" + TRIAL
STATE = "cloud-state/" + TRIAL
AUTHORIZATION = TRIAL + "-owner-paid-with-legacy-holds"
PROVIDERS = ("cheapai-gpt-pro", "codekey-codex-pro", "codekey-codex-discount",
             "codekey-deepseek", "codekey-gemini", "codekey-kimi")


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


def main():
    env = os.environ
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != gateway_trial.REPO
            or env.get("GITHUB_REF") != "refs/heads/" + BRANCH
            or env.get("GITHUB_ACTOR") != "hengyizang"
            or env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}):
        raise ValueError("exact owner repository cloud branch required")
    mode = env.get("MODEL_EVALUATION_MODE", "metadata")
    if mode != "metadata":
        raise ValueError("paid execution is not enabled by this metadata preparation")
    token = env.get("GH_TOKEN", "")
    if not token:
        raise ValueError("cloud state credential missing")
    report = metadata(token)
    output = ROOT / ".runtime" / TRIAL / "metadata.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    state = _state(token)
    name = "metadata-" + env["GITHUB_RUN_ID"] + ".json"
    if state.load(name) is not None:
        raise ValueError("an existing metadata receipt cannot be overwritten")
    state.save(name, report)
    print(json.dumps({"mode": mode, "trial_id": TRIAL, "state_branch": STATE,
        "metadata_file": name, "model_generation_calls": 0, "paid_execution_enabled": False}))


if __name__ == "__main__":
    main()
