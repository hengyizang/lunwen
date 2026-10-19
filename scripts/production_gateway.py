"""Bind reviewed relay routes to the existing cloud controller.

Credentials remain process-local. This entry point never grants a budget, edits
an approval, changes the frozen intake, or enqueues another research cycle.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scripts import ai_providers, billing_quotes

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "config/production-gateway-20261019.json"
PREFIXES = {"uuapi-openai": "UUAPI_OPENAI", "uuapi-anthropic": "UUAPI_ANTHROPIC"}


def prepare_environment(profile: dict, environment: dict[str, str]) -> dict[str, str]:
    if profile.get("schema_version") != "1.0":
        raise ValueError("unsupported production gateway profile")
    routes = profile.get("routes")
    if not isinstance(routes, list) or len(routes) != 2:
        raise ValueError("exactly two explicit production routes are required")
    result = dict(environment)
    selected = {}
    identities = {}
    for route in routes:
        provider = route["provider"]
        if provider not in PREFIXES or provider in selected:
            raise ValueError("each writer/critic provider must occur exactly once")
        if route["family"] != ai_providers.provider_family(provider):
            raise ValueError("writer/critic family mismatch")
        prefix = PREFIXES[provider]
        secret_name = route["secret_name"]
        if not isinstance(secret_name, str) or not secret_name.startswith("MODEL_TEST_") or not secret_name.endswith("_KEY"):
            raise ValueError("invalid reviewed secret binding")
        secret = environment.get(secret_name, "").strip()
        if not secret:
            raise ValueError(f"missing Actions Secret binding: {secret_name}")
        settings = {prefix + "_API_KEY": secret, prefix + "_BASE_URL": route["root"],
                    prefix + "_MODEL": route["model"]}
        if provider == "uuapi-openai":
            settings.update(UUAPI_OPENAI_PROTOCOL="responses",
                            UUAPI_OPENAI_REASONING_EFFORT=route["effort"])
        else:
            settings["UUAPI_ANTHROPIC_EFFORT"] = route["effort"]
        for name, value in settings.items():
            if environment.get(name, "").strip() and environment[name] != value:
                raise ValueError(f"existing production setting conflicts with reviewed profile: {name}")
            result[name] = value
        config = ai_providers.configuration(provider, result)
        if not config["configured"]:
            raise ValueError("reviewed provider configuration is invalid")
        identities[provider] = {"plan": "relay-production-20261019", "group": route["group"], "mode": "standard"}
        quote = billing_quotes.select(profile["pricing"], provider, config["endpoint"],
                                      config["model"], identities[provider])
        billing_quotes.reserve_cost(quote, 1, 1)
        selected[provider] = config
    if set(selected) != set(PREFIXES):
        raise ValueError("both model families are required")
    result["UUAPI_STRICT_MODEL_ID"] = "true"
    result["DR_OS_MODEL_PRICING_JSON"] = json.dumps(profile["pricing"], sort_keys=True)
    result["DR_OS_MODEL_BILLING_IDENTITY_JSON"] = json.dumps(identities, sort_keys=True)
    # Keep only the redacted canonical credential names in child processes.
    for route in routes:
        result.pop(route["secret_name"], None)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("check", "trial"), default="check")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    from scripts import cloud_continuation, cloud_job
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    configured = prepare_environment(profile, dict(os.environ))
    errors = cloud_continuation.configuration_errors(configured)
    if errors:
        raise ValueError("; ".join(errors))
    os.environ.clear()
    os.environ.update(configured)
    request = {"schema_version": "1.0", "action": "preflight" if args.mode == "check" else "cycle",
               "project": "my-phd", "actor": "Hengyi Zang", "allow_paid": args.mode == "trial"}
    if args.mode == "trial":
        request.update(stage="topic-intelligence", context=(
            "Owner request on 2026-10-19: complete one real cloud trial before estimating a new submission-ready date. "
            "The old October 7 date is historical, not a current promise; retain the frozen approval records. "
            "Use current public primary evidence to compare cloud-feasible prognostics, battery reliability and ECG robustness. "
            "Do not select the final doctoral direction or invent novelty, screened literature, experiment results, "
            "job-market scores or JCR evidence. Preserve retrieval failures, propose source-bound questions and "
            "prepare explicit human review materials. Keep all six future papers within one doctoral question. "
            "Use the existing authorized project budget and independent writer/critic roles."
        ))
    code = cloud_job.run_job(cloud_job.validate_request(request), args.run_id)
    if args.mode == "check":
        path = cloud_job.ARTIFACT / "gateway-startup.json"
        if path.is_file():
            report = json.loads(path.read_text(encoding="utf-8"))
            print(json.dumps({key: report.get(key) for key in (
                "configuration_ready", "ready_to_continue", "configuration_errors", "current_state", "budget",
                "paid_calls", "next_action")}, ensure_ascii=False, indent=2))
            if not report.get("configuration_ready"):
                return 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())
