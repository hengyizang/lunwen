"""Non-generating production configuration and optional catalog inspection.

Never grants a budget, starts research, probes inference or edits project state.
Provider inventory authenticates metadata access only, not model authenticity.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from scripts import ai_providers, billing_quotes, model_routing, relay_billing

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("catalog redirect refused")


def catalog(provider: str, environment: dict) -> set[str]:
    spec = ai_providers.PRODUCTION_PROVIDERS.get(provider)
    if spec is None or spec["root"] not in {"https://cheapai.info", "https://codekey.ai"}:
        raise ValueError("catalog provider is not a configured production route")
    key = environment.get(spec["key_setting"], "")
    if not isinstance(key, str) or not key.strip() or any(ch.isspace() or ord(ch) < 32 for ch in key.strip()):
        raise ValueError("catalog production credential is missing or invalid")
    request = urllib.request.Request(spec["root"] + "/v1/models", method="GET",
        headers={"Authorization": "Bearer " + key.strip(),
                 "User-Agent": "lunwen-production-research/1.0", "Accept": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("catalog size limit")
        data = json.loads(raw)
        if (not isinstance(data, dict) or data.get("success") is False or data.get("error")
                or not isinstance(data.get("data"), list)):
            raise ValueError("malformed catalog envelope")
        rows = data["data"]
        if any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]
               or len(row["id"]) > 160 or any(ch.isspace() or ord(ch) < 32 for ch in row["id"])
               for row in rows):
            raise ValueError("malformed catalog model ID")
        return {row["id"] for row in rows}
    except urllib.error.HTTPError as exc:
        raise ValueError(f"catalog HTTP {exc.code}") from None
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError):
        raise ValueError("catalog unavailable or malformed") from None


def report(environment=None, *, check_models=False, check_billing=False) -> dict:
    env = os.environ if environment is None else environment
    errors, rows = [], []
    try:
        policy, policy_hash = model_routing.load_policy(environment=env)
        prices = json.loads(env.get("DR_OS_MODEL_PRICING_JSON") or
                            (ROOT / "config/model-pricing.json").read_text(encoding="utf-8"))
        for key, route in policy["models"].items():
            config = ai_providers.configuration(route["provider"], env)
            if not config.get("configured"):
                errors.append(f"missing production credential: {config['key_setting']}")
            if ai_providers.provider_family(route["provider"]) != route["family"]:
                errors.append(f"route family mismatch: {key}")
            quote = billing_quotes.select(prices, route["provider"], config["endpoint"], route["model"],
                                          config["billing_identity"])
            rows.append({"model_key":key,"provider":route["provider"],"model":route["model"],
                         "family":route["family"],"requested_effort":route["reasoning_effort"],
                         "credential_present":config.get("configured",False),"quote_sha256":quote["quote_sha256"]})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        policy_hash = None
        errors.append("invalid production policy or exact billing contract: " + type(exc).__name__)
    inventory = {}
    meters = {}
    valid_configuration = not errors
    if check_billing and valid_configuration:
        for provider in sorted({row["provider"] for row in rows}):
            try:
                snapshot = relay_billing.read_meter(provider, environment=env)
                meters[provider] = {"metadata_access_verified":True,"kind":snapshot["kind"]}
            except relay_billing.BillingReconciliationError:
                meters[provider] = {"metadata_access_verified":False}
                errors.append("billing meter inspection failed: " + provider)
    if check_models and valid_configuration:
        for provider in sorted({row["provider"] for row in rows}):
            expected = {row["model"] for row in rows if row["provider"] == provider}
            try:
                supplied = catalog(provider, env)
                missing = sorted(expected - supplied)
                inventory[provider] = {"metadata_access_verified":True,"required_models_missing":missing}
                if missing:
                    errors.append("required model not advertised: " + provider + " / " + ",".join(missing))
            except ValueError as exc:
                inventory[provider] = {"metadata_access_verified":False,"diagnostic":str(exc)}
                errors.append("catalog inspection failed: " + provider)
    return {"profile":"production","configuration_ready":not errors,"configuration_errors":errors,
            "model_routes":rows,"policy_sha256":policy_hash,"model_inventory":inventory,"billing_meters":meters,
            "model_generation_calls":0,"new_spending_authority":False,"scientific_completion":False,
            "inference_access_and_effort_passthrough_verified":False,
            "optional_image_generation":"disabled_no_selected_image_model",
            "upstream_paperqa_sdk":"disabled_unmetered_native_source_qa_available",
            "automatic_research_enabled":env.get("DR_OS_AUTOMATIC_RESEARCH_ENABLED")=="true"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-models", action="store_true", help="read-only authenticated catalogs; never inference")
    parser.add_argument("--check-billing", action="store_true", help="read-only debit counters; never inference or settlement")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    value=report(check_models=args.check_models,check_billing=args.check_billing)
    text=json.dumps(value,ensure_ascii=False,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text+"\n",encoding="utf-8")
    print(text)
    return 0 if value["configuration_ready"] else 1


if __name__=="__main__":
    raise SystemExit(main())
