#!/usr/bin/env python3
"""Cost-guarded exact-prompt cache for external model calls.

The cache never changes model roles or skips a scientific review.  It only
reuses a byte-identical request to the same audited model endpoint, which makes
retries inexpensive without weakening the actor-critic protocol.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts import ai_providers, billing_quotes, model_spend, model_routing, relay_billing, engineering_contract
except ImportError:
    import ai_providers  # type: ignore
    import billing_quotes  # type: ignore
    import model_spend  # type: ignore
    import model_routing  # type: ignore
    import relay_billing  # type: ignore
    import engineering_contract  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = ROOT / "config" / "defaults.json"


class ModelBudgetError(RuntimeError):
    """A model call would exceed its recorded cost ceiling."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _defaults() -> dict[str, Any]:
    try:
        value = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {}
    budget = value.get("model_budget")
    return budget if isinstance(budget, dict) else {}


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ModelBudgetError(f"{name} must be numeric") from exc
    if not math.isfinite(value) or value <= 0:
        raise ModelBudgetError(f"{name} must be positive")
    return value


def _billing_configuration(name: str, provider: str, explicit: dict | None) -> dict | None:
    """Optional billing metadata never reaches provider inference arguments."""
    if explicit is not None:
        return explicit
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ModelBudgetError(f"{name} is invalid JSON") from exc
    if not isinstance(values, dict) or provider not in values or not isinstance(values[provider], dict):
        raise ModelBudgetError(f"{name} needs an exact provider entry")
    return values[provider]


def _route_configuration(provider: str, model: str | None = None) -> dict[str, Any]:
    configuration = ai_providers.configuration(provider)
    if provider in ai_providers.PRODUCTION_PROVIDERS:
        configuration = {**configuration,
                         "endpoint": ai_providers.production_endpoint(provider, model)}
    return configuration


def pricing(provider: str, model: str | None = None, *, billing_identity: dict | None = None) -> dict[str, Any]:
    family = ai_providers.provider_family(provider)
    defaults = _defaults()
    configured = defaults.get(family)
    configured = configured if isinstance(configured, dict) else {}
    # Explicit model-specific rates avoid charging a premium route at a cheap
    # model's assumed price (or vice versa). No inferred gateway pricing.
    if model:
        raw_rates = os.environ.get("DR_OS_MODEL_PRICING_JSON", "").strip()
        if not raw_rates and provider in ai_providers.PRODUCTION_PROVIDERS:
            raw_rates = (ROOT / "config" / "model-pricing.json").read_text(encoding="utf-8")
        raw_rates = raw_rates or "{}"
        try:
            overrides = json.loads(raw_rates)
        except json.JSONDecodeError as exc:
            raise ModelBudgetError("DR_OS_MODEL_PRICING_JSON is invalid JSON") from exc
        if not isinstance(overrides, dict):
            raise ModelBudgetError("model pricing must be an object")
        configuration = _route_configuration(provider, model)
        scope_key = "|".join((provider, str(configuration.get("endpoint") or ""), model))
        try:
            scoped_identity = _billing_configuration("DR_OS_MODEL_BILLING_IDENTITY_JSON", provider, billing_identity)
            if scoped_identity is None and provider in ai_providers.PRODUCTION_PROVIDERS:
                scoped_identity = configuration["billing_identity"]
            request_identity = billing_quotes.identity(scoped_identity)
            if "schema_version" in overrides or "quotes" in overrides:
                return billing_quotes.select(overrides, provider, str(configuration.get("endpoint") or ""), model, request_identity)
            if any(request_identity.values()):
                raise billing_quotes.BillingQuoteError("plan/group/mode identity needs an exact version 2 quote")
        except billing_quotes.BillingQuoteError as exc:
            raise ModelBudgetError(str(exc)) from exc
        # Once any scoped quote exists for this model, never silently select a
        # model-only price when an endpoint or provider changes.
        scoped = any(isinstance(key, str) and "|" in key and key.rsplit("|", 1)[-1] == model for key in overrides)
        if scoped and scope_key not in overrides:
            raise ModelBudgetError("scoped model quotes require an exact transport route; no price fallback")
        selected = overrides.get(scope_key) if scoped else overrides.get(model)
        if selected is not None:
            if not isinstance(selected, dict):
                raise ModelBudgetError(f"model price entry is malformed: {model}")
            try:
                values = {key: float(selected[key]) for key in ("input_per_million", "output_per_million")}
            except (KeyError, TypeError, ValueError) as exc:
                raise ModelBudgetError(f"model price entry needs numeric input/output CNY per million: {model}") from exc
            if any(not math.isfinite(value) or value <= 0 for value in values.values()):
                raise ModelBudgetError("model prices must be positive finite numbers")
            if selected.get("currency", "CNY") != "CNY":
                raise ModelBudgetError("budget rates must be expressed in CNY")
            for field, actual in (("provider", provider), ("endpoint", configuration.get("endpoint")), ("model", model)):
                if selected.get(field) is not None and selected[field] != actual:
                    raise ModelBudgetError(f"price quote {field} differs from the requested route")
            if any(key in selected for key in ("context_brackets", "context_basis", "tool_fees", "plan", "group", "mode", *billing_quotes.CACHE_WRITE_TTL_RATES)):
                raise ModelBudgetError("conditional billing fields require the version 2 pricing schema")
            for key in ("cache_read_per_million", "cache_write_per_million"):
                if key in selected:
                    try:
                        value = float(selected[key])
                    except (TypeError, ValueError) as exc:
                        raise ModelBudgetError("cache rate must be numeric") from exc
                    if not math.isfinite(value) or value < 0:
                        raise ModelBudgetError("cache rate must be non-negative and finite")
                    values[key] = value
            values["price_version"] = str(selected.get("price_version") or "legacy-model-only")
            values["scope_key"] = scope_key
            values["billing_identity"] = request_identity
            values["quote_sha256"] = billing_quotes.quote_digest(values)
            return values
        if os.environ.get("DR_OS_REQUIRE_MODEL_AUTH") == "1":
            raise ModelBudgetError(f"exact CNY input/output rates are required for cloud model {model}")
    prefix = "DR_OS_ANTHROPIC" if family == "anthropic" else "DR_OS_OPENAI"
    return {
        "input_per_million": _float_env(
            f"{prefix}_INPUT_CNY_PER_M",
            float(configured.get("input_per_million", 0.0)),
        ),
        "output_per_million": _float_env(
            f"{prefix}_OUTPUT_CNY_PER_M",
            float(configured.get("output_per_million", 0.0)),
        ),
    }


def usage_counts(usage: dict[str, Any]) -> tuple[int | None, int | None]:
    if not isinstance(usage, dict):
        raise ModelBudgetError("usage must be an object; billing reconciliation is required")

    def integer(*names: str) -> int | None:
        values = []
        for name in names:
            if name not in usage:
                continue
            value = usage[name]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ModelBudgetError(f"{name} is malformed; billing reconciliation is required")
            values.append(value)
        if len(set(values)) > 1:
            raise ModelBudgetError("conflicting token usage counters; billing reconciliation is required")
        return values[0] if values else None

    return integer("input_tokens", "prompt_tokens"), integer(
        "output_tokens", "completion_tokens"
    )


def estimate_tokens(text: str) -> int:
    # A conservative multilingual approximation used only for cost ceilings.
    return max(1, math.ceil(len(text.encode("utf-8")) / 3.2))


def cost_cny(provider: str, input_tokens: int, output_tokens: int, model: str | None = None, *,
             billing_identity: dict | None = None, declared_tool_limits: dict | None = None) -> float:
    """Conservative ceiling; conditional rates require actual usage to settle."""
    rates = pricing(provider, model, billing_identity=billing_identity)
    try:
        return billing_quotes.reserve_cost(rates, input_tokens, output_tokens, declared_tool_limits)
    except billing_quotes.BillingQuoteError as exc:
        raise ModelBudgetError(str(exc)) from exc


def billed_cost(provider: str, usage: dict, model: str, input_tokens: int, output_tokens: int, *,
                quote: dict | None = None, billing_identity: dict | None = None,
                declared_tool_limits: dict | None = None, request_id: str | None = None) -> tuple[float, bool, dict]:
    """Output includes reasoning; never add reasoning tokens a second time."""
    rates = quote if quote is not None else pricing(provider, model, billing_identity=billing_identity)
    try:
        return billing_quotes.bill(rates, usage, input_tokens, output_tokens,
                                   anthropic=ai_providers.provider_family(provider) == "anthropic",
                                   tools=declared_tool_limits, request_id=request_id)
    except billing_quotes.BillingQuoteError as exc:
        raise ModelBudgetError(str(exc)) from exc


def _ledger(project_root: Path) -> Path:
    return project_root / "state" / "model-usage.jsonl"


def ledger_entries(project_root: Path) -> list[dict[str, Any]]:
    path = _ledger(project_root)
    if not path.is_file():
        return []
    values: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def budget_status(project_root: Path, paper_id: str | None = None) -> dict[str, Any]:
    control = model_spend.read(project_root, required=os.environ.get("DR_OS_REQUIRE_MODEL_AUTH") == "1")
    values = ledger_entries(project_root) if control is None else []
    spent = round(sum(float(item.get("cost_cny", 0.0)) for item in values), 8) if control is None else control["spent_cny"]
    paper_spent = round(sum(float(item.get("cost_cny", 0.0)) for item in values if paper_id and item.get("paper_id") == paper_id), 8) if control is None else control["paper_spent_cny"].get(paper_id, 0.0)
    reserved = model_spend.reserved(control) if control is not None else 0.0
    paper_reserved = model_spend.reserved(control, paper_id) if control is not None and paper_id else 0.0
    defaults = _defaults()
    configured_project_limit = _float_env(
        "DR_OS_PROJECT_BUDGET_CNY", float(defaults.get("project_hard_limit", 300.0))
    )
    project_limit = float(control["authorized_ceiling_cny"]) if control is not None else configured_project_limit
    paper_limit = _float_env(
        "DR_OS_PAPER_BUDGET_CNY", float(defaults.get("paper_hard_limit", 60.0))
    )
    paper_warning = _float_env(
        "DR_OS_PAPER_WARNING_CNY",
        min(float(defaults.get("paper_warning_limit", 45.0)), paper_limit),
    )
    if paper_warning > paper_limit:
        raise ModelBudgetError("paper warning limit cannot exceed paper hard limit")
    return {
        "currency": "CNY",
        "spent": spent,
        "reserved": reserved,
        "project_hard_limit": project_limit,
        "project_remaining": round(project_limit - spent - reserved, 8),
        "paper_id": paper_id,
        "paper_spent": paper_spent if paper_id else None,
        "paper_warning_limit": paper_warning if paper_id else None,
        "paper_warning_reached": paper_spent >= paper_warning if paper_id else None,
        "paper_hard_limit": paper_limit if paper_id else None,
        "paper_remaining": round(paper_limit - paper_spent - paper_reserved, 8) if paper_id else None,
    }


def usage_summary(project_root: Path, paper_id: str | None = None) -> dict[str, Any]:
    from scripts.cost_audit import summarize
    values = ledger_entries(project_root)
    if paper_id:
        values = [item for item in values if item.get("paper_id") == paper_id]
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in values:
        key = (
            str(item.get("provider") or "unknown"),
            str(item.get("model") or "unknown"),
            str(item.get("role") or "unknown"),
            json.dumps(item.get("billing_identity") or {}, sort_keys=True),
        )
        group = groups.setdefault(
            key,
            {
                "provider": key[0],
                "model": key[1],
                "role": key[2],
                "billing_identity": json.loads(key[3]),
                "paid_calls": 0,
                "cache_hits": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_cny": 0.0,
            },
        )
        if item.get("cache_hit") is True:
            group["cache_hits"] += 1
        else:
            group["paid_calls"] += 1
        group["input_tokens"] += int(item.get("input_tokens") or 0)
        group["output_tokens"] += int(item.get("output_tokens") or 0)
        group["cost_cny"] += float(item.get("cost_cny") or 0.0)
    rows = []
    for group in groups.values():
        group["cost_cny"] = round(group["cost_cny"], 8)
        rows.append(group)
    rows.sort(key=lambda item: (-item["cost_cny"], item["provider"], item["role"]))
    return {
        "schema_version": "1.0",
        "paper_id": paper_id,
        "paid_calls": sum(item["paid_calls"] for item in rows),
        "cache_hits": sum(item["cache_hits"] for item in rows),
        "input_tokens": sum(item["input_tokens"] for item in rows),
        "output_tokens": sum(item["output_tokens"] for item in rows),
        "cost_cny": round(sum(item["cost_cny"] for item in rows), 8),
        "budget": budget_status(project_root, paper_id),
        "by_provider_model_role": rows,
        "cost_diagnostics": summarize(values),
    }


def _append(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def _cache_key(
    provider: str,
    prompt: str,
    system: str | None,
    max_output_tokens: int,
    model: str | None = None,
    billing_quote: dict | None = None,
    declared_tool_limits: dict | None = None,
    *,
    stage: str | None = None,
    role: str | None = None,
    reasoning_effort: str | None = None,
    attachment_identity: list | None = None,
    routing_policy_sha256: str | None = None,
) -> tuple[str, dict[str, Any]]:
    configuration = _route_configuration(provider, model)
    identity = {
        "provider": provider,
        "model": model or configuration.get("model"),
        "protocol": configuration.get("protocol"),
        "max_tokens_field": configuration.get("max_tokens_field"),
        "strict_model_id": configuration.get("strict_model_id"),
        "anthropic_version": os.environ.get("ANTHROPIC_VERSION", "2023-06-01") if ai_providers.provider_family(provider) == "anthropic" else None,
        "endpoint": configuration.get("endpoint"),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "system_sha256": hashlib.sha256((system or "").encode("utf-8")).hexdigest(),
        "max_output_tokens": max_output_tokens,
        "cache_schema": "5.0",
        "stage": stage,
        "role": role,
        "reasoning_effort": reasoning_effort,
        "attachment_identity": attachment_identity or [],
        "routing_policy_sha256": routing_policy_sha256,
        "billing_identity": (billing_quote or {}).get("billing_identity", {}),
        "billing_quote_sha256": (billing_quote.get("quote_sha256") or billing_quotes.quote_digest(billing_quote)) if billing_quote is not None else None,
        "declared_tool_limits": declared_tool_limits or {},
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest, identity


def fresh_call_required(role: str) -> bool:
    return role.startswith("independent-critic") or role in {"independent-critique", "endpoint-health"}


def preflight_route(provider: str, model: str | None = None) -> dict[str, Any]:
    """Check the whole cycle's known routes before spending on its first role."""
    configuration = _route_configuration(provider, model)
    if os.environ.get("DR_OS_REQUIRE_MODEL_AUTH") == "1" and not configuration.get("configured"):
        raise ModelBudgetError(f"model route is not configured: {provider}")
    effective_model = model or str(configuration.get("model") or "") or None
    quote = pricing(provider, effective_model)
    try:
        billing_quotes.tool_limits(quote, _billing_configuration("DR_OS_MODEL_TOOL_LIMITS_JSON", provider, None))
    except billing_quotes.BillingQuoteError as exc:
        raise ModelBudgetError(str(exc)) from exc
    return {"provider": provider, "model": effective_model, "quote_sha256": quote.get("quote_sha256")}


@contextmanager
def authorized_calls(project_root: Path):
    """A paid CLI probe must use project authority even outside a cloud job."""
    previous = os.environ.get("DR_OS_REQUIRE_MODEL_AUTH")
    os.environ["DR_OS_REQUIRE_MODEL_AUTH"] = "1"
    try:
        model_spend.read(project_root, required=True)
        yield
    finally:
        if previous is None:
            os.environ.pop("DR_OS_REQUIRE_MODEL_AUTH", None)
        else:
            os.environ["DR_OS_REQUIRE_MODEL_AUTH"] = previous


def _write_cache(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _paper_for_stage(project_root: Path, stage: str) -> str | None:
    if stage != "writing-and-review":
        return None
    try:
        state = json.loads((project_root / "state" / "run.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = state.get("active_paper") if isinstance(state, dict) else None
    return value if isinstance(value, str) else None


def reservation_bound(provider: str, prompt: str, system: str | None, max_output_tokens: int,
                      quote: dict, limits: dict, *, controlled: bool = False,
                      has_media: bool = False) -> float:
    """Pure conservative bound shared by selection and the final spending gate."""
    request_text = (system or "") + "\n" + prompt
    predicted = estimate_tokens(request_text)
    conservative = controlled or quote.get("quote_schema") == "2.0"
    inputs = max(predicted, len(request_text.encode("utf-8")) + 1000) if conservative else predicted
    production = provider in ai_providers.PRODUCTION_PROVIDERS
    if production:
        inputs = max(inputs + 8192, 65536 if ai_providers.provider_family(provider) == "anthropic" else 8192)
        if has_media:
            inputs = max(inputs, 1048576)
    cost = billing_quotes.reserve_cost(quote, inputs, max_output_tokens, limits)
    return round(7 * cost, 8) if production else cost


def call(
    project_root: Path,
    *,
    run_id: str,
    stage: str,
    role: str,
    provider: str,
    prompt: str,
    system: str | None = None,
    max_output_tokens: int = 8000,
    timeout: int = 180,
    use_cache: bool = True,
    model: str | None = None,
    billing_identity: dict | None = None,
    declared_tool_limits: dict | None = None,
    reasoning_effort: str | None = None,
    attachments: list | None = None,
    task_kind: str | None = None,
    source_contract: dict | None = None,
    task_profile: dict | None = None,
) -> ai_providers.ModelResult:
    """Call a provider with exact-request caching and hard CNY ceilings."""

    route = model_routing.resolve_call(stage, role, provider, model, reasoning_effort, task_kind, task_profile)
    provider, model, reasoning_effort = route["provider"], route["model"], route["reasoning_effort"]
    production = provider in ai_providers.PRODUCTION_PROVIDERS
    requested_output_limit = max_output_tokens
    if route.get("max_output_tokens") is not None:
        max_output_tokens = min(max_output_tokens, route["max_output_tokens"])
    if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 100000:
        raise ModelBudgetError("output token ceiling must be a bounded positive integer")
    media = ai_providers.validate_attachments(attachments) if attachments else []
    if media and (not production or ai_providers.provider_family(provider) not in {"openai", "google"}):
        raise ModelBudgetError("attachments require a supported native production route")
    if role == "multimodal-inspection" and not media:
        raise ModelBudgetError("multimodal inspection requires source-hashed attachments")
    contract_validator = None
    if role in engineering_contract.TASKS:
        if not production or model != "deepseek-v4.1-flash" or source_contract is None:
            raise ModelBudgetError("engineering support requires its production route and source contract")
        contract_validator = engineering_contract
    elif production and model == "gpt-5.6-luna" and role not in {"endpoint-health", "model-signature", "model-instrumentation"}:
        if role != "metadata-extraction" or source_contract is None:
            raise ModelBudgetError("Luna requires a bounded metadata source contract")
        from scripts import metadata_contract
        contract_validator = metadata_contract
    elif source_contract is not None:
        raise ModelBudgetError("source contracts require their scoped metadata or engineering route")
    if contract_validator is not None:
        source_contract = contract_validator.validate_contract(source_contract)
        prompt = contract_validator.build_prompt(prompt, source_contract)
    decision = None
    if production:
        from scripts import dynamic_routing
        if (route.get("task_kind") or role in model_routing.APPROVED_CRITICAL_TASKS
                or (stage in {"topic-intelligence", "paper-architecture", "experiment-design"}
                    and role in {*model_routing.CYCLE_ROLES, "writer"})):
            task_profile = {**dynamic_routing.validate_profile(task_profile, stage=stage, role=role),
                            "science_risk": "critical"}
        # A fully validated exact replay has no new inference cost. Do not
        # switch to a paid candidate merely because its historical unit price
        # is lower. Fresh independent reviews never enter this path.
        baseline_cache_hit = False
        if use_cache and not fresh_call_required(role) and not route.get("fresh_required", False):
            try:
                baseline_quote = pricing(provider, model, billing_identity=billing_identity)
                baseline_limits = billing_quotes.tool_limits(baseline_quote, _billing_configuration(
                    "DR_OS_MODEL_TOOL_LIMITS_JSON", provider, declared_tool_limits))
                baseline_media = [{"sha256": item["sha256"], "mime_type": item["mime_type"],
                                   "size_bytes": len(item["decoded"])} for item in media]
                baseline_key, baseline_identity = _cache_key(
                    provider, prompt, system, max_output_tokens, model, baseline_quote, baseline_limits,
                    stage=stage, role=role, reasoning_effort=reasoning_effort,
                    attachment_identity=baseline_media, routing_policy_sha256=route.get("policy_sha256"))
                baseline_file = project_root / ".cache/model-responses" / (baseline_key + ".json")
                cached_baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
                if (not baseline_file.is_symlink()
                        and all(cached_baseline.get(k) == v for k, v in baseline_identity.items())
                        and cached_baseline.get("reported_model") == model
                        and cached_baseline.get("completion_status") == "completed"
                        and cached_baseline.get("response_text_sha256") == hashlib.sha256(
                            str(cached_baseline.get("text", "")).encode("utf-8")).hexdigest()):
                    if contract_validator is not None:
                        contract_validator.validate_response(cached_baseline["text"], source_contract)
                    baseline_cache_hit = True
            except (OSError, ValueError, KeyError, TypeError, ModelBudgetError):
                baseline_cache_hit = False
        try:
            selection = dynamic_routing.choose(project_root, route, prompt=prompt, system=system,
                                               max_output_tokens=requested_output_limit, timeout=timeout,
                                               attachments=attachments, task_profile=task_profile,
                                               baseline_cache_hit=baseline_cache_hit)
        except dynamic_routing.RoutingError as exc:
            raise ModelBudgetError("dynamic route blocked: " + str(exc)) from exc
        route, decision = selection["route"], selection["decision"]
        provider, model, reasoning_effort = route["provider"], route["model"], route["reasoning_effort"]
        max_output_tokens = route["max_output_tokens"]
        timeout = route.get("timeout", timeout)
        task_profile = decision.get("task_profile", task_profile)
        if (type(max_output_tokens) is not int or not 1 <= max_output_tokens <= min(requested_output_limit, 32768)
                or type(timeout) is not int or not 1 <= timeout <= 600):
            raise ModelBudgetError("selected route exceeds the explicit request or native transport ceiling")
    media_identity = [{"sha256":item["sha256"], "mime_type":item["mime_type"],
                       "size_bytes":len(item["decoded"])} for item in media]
    paper_id = _paper_for_stage(project_root, stage)
    configuration = _route_configuration(provider, model)
    effective_model = str(model or configuration.get("model") or "")
    if not effective_model and os.environ.get("DR_OS_REQUIRE_MODEL_AUTH") == "1":
        raise ModelBudgetError("a configured exact model ID is required")
    quote = pricing(provider, effective_model or None, billing_identity=billing_identity)
    try:
        limits = billing_quotes.tool_limits(quote, _billing_configuration("DR_OS_MODEL_TOOL_LIMITS_JSON", provider, declared_tool_limits))
    except billing_quotes.BillingQuoteError as exc:
        raise ModelBudgetError(str(exc)) from exc
    # Fresh reviews are deliberately billable: response replay is not another
    # independent scientific review or a current endpoint-health observation.
    use_cache = use_cache and not fresh_call_required(role) and not route.get("fresh_required", False)
    key, identity = _cache_key(provider, prompt, system, max_output_tokens, effective_model or None, quote, limits,
                               stage=stage, role=role, reasoning_effort=reasoning_effort,
                               attachment_identity=media_identity,
                               routing_policy_sha256=route.get("policy_sha256"))
    request_metrics = {
        "prompt_sha256": identity["prompt_sha256"],
        "system_sha256": identity["system_sha256"],
        "prompt_input_bytes": len(prompt.encode("utf-8")) + len((system or "").encode("utf-8")),
        "max_output_tokens": max_output_tokens,
        "cache_policy": "exact_request" if use_cache else "fresh_required_or_explicit",
        "requested_reasoning_effort": reasoning_effort,
        "reasoning_effort_attestation": "requested_not_independently_attested" if reasoning_effort else None,
        "routing_policy_sha256": route.get("policy_sha256"),
        "route_id": route.get("route_id"),
        "requested_model": effective_model,
        "timeout_seconds": timeout,
        "task_profile": task_profile,
        "dynamic_candidate_id": decision.get("selected_candidate_id") if decision else None,
        "dynamic_decision": decision,
        "attachments": media_identity,
    }
    if decision is not None:
        _append(project_root / "state/model-route-decisions.jsonl", {
            "schema_version": "1.0", "at": utc_now(), "run_id": run_id,
            "stage": stage, "role": role, **request_metrics,
            "provider": provider, "model": effective_model,
            "not_scientific_evidence": True,
        })
    cache_path = project_root / ".cache" / "model-responses" / f"{key}.json"
    if use_cache and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if any(cached.get(field) != value for field, value in identity.items()):
                raise ValueError("cached scope or billing identity differs from the exact request")
            if configuration.get("strict_model_id") is True and cached.get("reported_model") != effective_model:
                raise ValueError("cached reported model differs from the strict requested identity")
            if cached.get("response_text_sha256") != hashlib.sha256(str(cached.get("text", "")).encode("utf-8")).hexdigest():
                raise ValueError("cached response content changed")
            result = ai_providers.ModelResult(
                provider=str(cached["provider"]),
                model=str(cached["model"]),
                text=str(cached["text"]),
                usage=cached.get("usage", {}) if isinstance(cached.get("usage"), dict) else {},
                request_id=cached.get("request_id"),
                reported_model=cached.get("reported_model"),
                protocol=cached.get("protocol"),
                endpoint=cached.get("endpoint"),
                gateway=cached.get("gateway"),
                cache_hit=True,
                cache_key=key,
                completion_status=cached.get("completion_status"),
                requested_effort=reasoning_effort,
                attachment_sha256=tuple(item["sha256"] for item in media_identity),
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            result = None  # type: ignore[assignment]
        if result is not None:
            ai_providers.require_complete(result)
            result.route_id = route.get("route_id")
            result.dynamic_candidate_id = request_metrics["dynamic_candidate_id"]
            result.routing_policy_sha256 = route.get("policy_sha256")
            if source_contract is not None:
                contract_validator.validate_response(result.text, source_contract)
            _append(
                _ledger(project_root),
                {
                    **request_metrics,
                    "schema_version": "1.0",
                    "at": utc_now(),
                    "run_id": run_id,
                    "stage": stage,
                    "paper_id": paper_id,
                    "role": role,
                    "provider": provider,
                    "model": result.reported_model or result.model,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_cny": 0.0,
                    "cache_hit": True,
                    "cache_key": key,
                    "billing_identity": identity["billing_identity"],
                    "billing_quote_sha256": identity["billing_quote_sha256"],
                    "declared_tool_limits": limits,
                },
            )
            return result

    request_text = (system or "") + "\n" + prompt
    predicted_input = estimate_tokens(request_text)
    status = budget_status(project_root, paper_id)
    control = model_spend.read(project_root)
    controlled = control is not None
    if production and not controlled:
        raise ModelBudgetError("production calls require the persisted owner-approved spending ledger")
    if production and (os.environ.get("GITHUB_ACTIONS") != "true"
                       or os.environ.get("DR_OS_REQUIRE_REMOTE_RESERVATION") != "1"):
        raise ModelBudgetError("production generation requires the cloud runner and durable remote reservation mode")
    if control and control["reservations"]:
        raise ModelBudgetError("billing reconciliation is required before another paid request")
    reserved_cost = reservation_bound(provider, prompt, system, max_output_tokens, quote, limits,
                                      controlled=controlled, has_media=bool(media))
    if reserved_cost > float(status["project_remaining"]):
        raise ModelBudgetError(
            f"request could exceed project model budget: reserve up to CNY {reserved_cost:.4f}, "
            f"remaining CNY {status['project_remaining']:.4f}"
        )
    if paper_id and reserved_cost > float(status["paper_remaining"]):
        raise ModelBudgetError(
            f"request could exceed {paper_id} model budget: reserve up to CNY {reserved_cost:.4f}, "
            f"remaining CNY {status['paper_remaining']:.4f}"
        )
    meter_before = None
    if production:
        if not configuration.get("configured"):
            raise ModelBudgetError("production route credentials are missing")
        from scripts.production_readiness import catalog
        availability_error = None
        try:
            if effective_model not in catalog(provider, dict(os.environ)):
                availability_error = "model_not_advertised"
        except ValueError:
            availability_error = "catalog_unavailable"
        if availability_error:
            _append(project_root / "state/model-route-decisions.jsonl", {
                "schema_version": "1.0", "at": utc_now(), "run_id": run_id,
                "stage": stage, "role": role, **request_metrics,
                "provider": provider, "model": effective_model,
                "availability_error": availability_error, "generation_sent": False,
                "not_scientific_evidence": True,
            })
            raise ModelBudgetError(
                f"production route unavailable ({availability_error}); no generation sent"
            )
        meter_before = relay_billing.read_meter(provider)
    reservation_id = model_spend.reserve(project_root, max_cost_cny=reserved_cost, paper_id=paper_id,
                                         paper_limit_cny=float(status["paper_hard_limit"] or 0), run_id=run_id) if controlled else None
    if reservation_id:
        from scripts.cloud_checkpoint import sync_billing
        sync_billing(project_root)

    request_started = time.monotonic()
    try:
        inference_options = {"reasoning_effort": reasoning_effort} if reasoning_effort is not None else {}
        if attachments:
            inference_options["attachments"] = attachments
        result = ai_providers.call(
            provider, prompt, system=system, max_output_tokens=max_output_tokens,
            timeout=timeout, model=model, **inference_options,
        )
    except Exception as exc:
        _append(_ledger(project_root), {
            **request_metrics, "schema_version": "2.0", "at": utc_now(), "run_id": run_id,
            "stage": stage, "paper_id": paper_id, "role": role, "provider": provider,
            "model": effective_model, "cache_hit": False, "cache_key": key,
            "cost_cny": 0.0, "cost_status": "unknown_reconcile_required",
            "reservation_id": reservation_id, "reserved_cost_cny": reserved_cost,
            "billing_identity": identity["billing_identity"],
            "billing_quote_sha256": identity["billing_quote_sha256"],
            "endpoint": configuration.get("endpoint"), "protocol": configuration.get("protocol"),
            "declared_tool_limits": limits,
            "transport_error_type": type(exc).__name__,
            "zero_cost_not_confirmed": True,
            "gateway_meter_before": meter_before,
            "duration_seconds": round(time.monotonic() - request_started, 6),
        })
        raise
    request_metrics["duration_seconds"] = round(time.monotonic() - request_started, 6)
    result.route_id = route.get("route_id")
    result.dynamic_candidate_id = request_metrics["dynamic_candidate_id"]
    result.routing_policy_sha256 = route.get("policy_sha256")
    settled = None
    try:
        input_tokens, output_tokens = usage_counts(result.usage)
        estimated = input_tokens is None or output_tokens is None
        if estimated and quote.get("quote_schema") == "2.0":
            raise ModelBudgetError("conditional billing needs actual token usage; reconcile the outstanding reservation")
        input_tokens = input_tokens if input_tokens is not None else predicted_input
        output_tokens = output_tokens if output_tokens is not None else estimate_tokens(result.text)
        try:
            actual_cost, cache_price_unknown, billing_details = billed_cost(provider, result.usage, effective_model, input_tokens, output_tokens,
                                                                          quote=quote, declared_tool_limits=limits, request_id=result.request_id)
        except ModelBudgetError:
            if not production:
                raise
            # Independent gateway settlement can resolve missing cache TTL or
            # a promotional price without fabricating a precise token quote.
            actual_cost, cache_price_unknown = reserved_cost, True
            billing_details = {"modeled_cost_unknown":True,"usage_receipt":result.usage}
        if production:
            if output_tokens > max_output_tokens:
                raise ModelBudgetError("provider output exceeded the reserved ceiling")
            settled = relay_billing.settle(provider, effective_model, meter_before)
            if settled["actual_cost_cny"] > reserved_cost:
                if reservation_id:
                    # Keep a pending hold for the known debit, rather than
                    # releasing it and permitting another underquoted call.
                    # This records an existing liability, not new authority.
                    control = model_spend.read(project_root, required=True)
                    pending = control["reservations"][reservation_id]
                    pending["max_cost_cny"] = settled["actual_cost_cny"]
                    pending["confirmed_gateway_debit_cny"] = settled["actual_cost_cny"]
                    pending["review_reason"] = "gateway_debit_exceeded_reserved_ceiling"
                    model_spend.write(project_root, control)
                    from scripts.cloud_checkpoint import sync_billing
                    sync_billing(project_root)
                raise ModelBudgetError("gateway debit exceeded the reserved ceiling; hold for reconciliation")
            billing_details = {**billing_details,"modeled_cost_cny":None if cache_price_unknown else actual_cost,
                               "independent_gateway_debit":settled}
            actual_cost, cache_price_unknown, estimated = settled["actual_cost_cny"], False, False
    except (ModelBudgetError, relay_billing.BillingReconciliationError) as exc:
        _append(_ledger(project_root), {**request_metrics, "schema_version": "2.0", "at": utc_now(), "run_id": run_id, "stage": stage,
                                      "paper_id": paper_id, "role": role, "provider": provider,
                                      "model": result.reported_model or result.model, "cache_hit": False,
                                      "cache_key": key, "cost_cny": 0.0, "cost_status": "unknown_reconcile_required",
                                      "reservation_id": reservation_id, "reserved_cost_cny": reserved_cost,
                                      "billing_identity": identity["billing_identity"], "billing_quote_sha256": identity["billing_quote_sha256"],
                                      "declared_tool_limits": limits, "request_id": result.request_id,
                                      "billing_error": str(exc), "usage_receipt": result.usage,
                                      "independent_gateway_debit": settled,
                                      "completion_status": result.completion_status,
                                      "endpoint": result.endpoint, "gateway": result.gateway, "protocol": result.protocol})
        raise
    estimated = estimated or cache_price_unknown
    result.cache_key = key
    if reservation_id and not estimated:
        model_spend.settle(project_root, reservation_id, actual_cost_cny=actual_cost)
    _append(
        _ledger(project_root),
        {
            **request_metrics,
            "schema_version": "1.0",
            "at": utc_now(),
            "run_id": run_id,
            "stage": stage,
            "paper_id": paper_id,
            "role": role,
            "provider": provider,
            "model": result.reported_model or result.model,
            "input_tokens": input_tokens,
            "request_id": result.request_id,
            "output_tokens": output_tokens,
            "usage_estimated": estimated,
            "cost_cny": actual_cost,
            "cache_hit": False,
            "cache_key": key,
            "completion_status": result.completion_status,
            "billing": billing_details,
            "endpoint": result.endpoint,
            "gateway": result.gateway,
            "protocol": result.protocol,
            "billing_identity": identity["billing_identity"],
            "billing_quote_sha256": identity["billing_quote_sha256"],
            "declared_tool_limits": limits,
            "reservation_id": reservation_id,
            "cost_status": ("estimated_reconcile_required" if estimated else
                            "settled_gateway_debit" if production else "settled_usage_receipt"),
        },
    )
    # Account for the billable response first. Truncated/refused answers must
    # never become cached scientific artifacts, even if their text parses.
    ai_providers.require_complete(result)
    if source_contract is not None:
        try:
            contract_validator.validate_response(result.text, source_contract)
        except ValueError:
            _append(_ledger(project_root), {**request_metrics,"at":utc_now(),"run_id":run_id,
                "stage":stage,"role":role,"provider":provider,"model":effective_model,
                "cost_cny":0.0,"validation_status":"source_contract_failed_no_retry",
                "request_id":result.request_id,"not_scientific_evidence":True})
            raise
    if use_cache and not estimated:
        _write_cache(
            cache_path,
            {
                **identity,
                "provider": result.provider,
                "model": result.model,
                "text": result.text,
                "response_text_sha256": hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
                "usage": result.usage,
                "request_id": result.request_id,
                "reported_model": result.reported_model,
                "protocol": result.protocol,
                "endpoint": result.endpoint,
                "gateway": result.gateway,
                "completion_status": result.completion_status,
                "created_at": utc_now(),
            },
        )
    return result
