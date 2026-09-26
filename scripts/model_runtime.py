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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts import ai_providers
except ImportError:
    import ai_providers  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = ROOT / "config" / "defaults.json"


class ModelBudgetError(RuntimeError):
    """A model call would exceed an explicit local cost ceiling."""


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
    if value <= 0:
        raise ModelBudgetError(f"{name} must be positive")
    return value


def pricing(provider: str, model: str | None = None) -> dict[str, float]:
    family = ai_providers.provider_family(provider)
    defaults = _defaults()
    configured = defaults.get(family)
    configured = configured if isinstance(configured, dict) else {}
    # Explicit model-specific rates avoid charging a premium route at a cheap
    # model's assumed price (or vice versa). No inferred gateway pricing.
    if model:
        raw_rates = os.environ.get("DR_OS_MODEL_PRICING_JSON", "{}")
        try:
            overrides = json.loads(raw_rates)
        except json.JSONDecodeError as exc:
            raise ModelBudgetError("DR_OS_MODEL_PRICING_JSON is invalid JSON") from exc
        if not isinstance(overrides, dict):
            raise ModelBudgetError("model pricing must be an object")
        selected = overrides.get(model)
        if selected is not None:
            if not isinstance(selected, dict):
                raise ModelBudgetError(f"model price entry is malformed: {model}")
            try:
                values = {key: float(selected[key]) for key in ("input_per_million", "output_per_million")}
            except (KeyError, TypeError, ValueError) as exc:
                raise ModelBudgetError(f"model price entry needs numeric input/output CNY per million: {model}") from exc
            if any(not math.isfinite(value) or value <= 0 for value in values.values()):
                raise ModelBudgetError("model prices must be positive finite numbers")
            return values
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
    def integer(*names: str) -> int | None:
        for name in names:
            value = usage.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return None

    return integer("input_tokens", "prompt_tokens"), integer(
        "output_tokens", "completion_tokens"
    )


def estimate_tokens(text: str) -> int:
    # A conservative multilingual approximation used only for cost ceilings.
    return max(1, math.ceil(len(text.encode("utf-8")) / 3.2))


def cost_cny(provider: str, input_tokens: int, output_tokens: int, model: str | None = None) -> float:
    rates = pricing(provider, model)
    return round(
        input_tokens * rates["input_per_million"] / 1_000_000
        + output_tokens * rates["output_per_million"] / 1_000_000,
        8,
    )


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
    values = ledger_entries(project_root)
    spent = round(sum(float(item.get("cost_cny", 0.0)) for item in values), 8)
    paper_spent = round(
        sum(
            float(item.get("cost_cny", 0.0))
            for item in values
            if paper_id and item.get("paper_id") == paper_id
        ),
        8,
    )
    defaults = _defaults()
    project_limit = _float_env(
        "DR_OS_PROJECT_BUDGET_CNY", float(defaults.get("project_hard_limit", 300.0))
    )
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
        "project_hard_limit": project_limit,
        "project_remaining": round(project_limit - spent, 8),
        "paper_id": paper_id,
        "paper_spent": paper_spent if paper_id else None,
        "paper_warning_limit": paper_warning if paper_id else None,
        "paper_warning_reached": paper_spent >= paper_warning if paper_id else None,
        "paper_hard_limit": paper_limit if paper_id else None,
        "paper_remaining": round(paper_limit - paper_spent, 8) if paper_id else None,
    }


def usage_summary(project_root: Path, paper_id: str | None = None) -> dict[str, Any]:
    values = ledger_entries(project_root)
    if paper_id:
        values = [item for item in values if item.get("paper_id") == paper_id]
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in values:
        key = (
            str(item.get("provider") or "unknown"),
            str(item.get("model") or "unknown"),
            str(item.get("role") or "unknown"),
        )
        group = groups.setdefault(
            key,
            {
                "provider": key[0],
                "model": key[1],
                "role": key[2],
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
) -> tuple[str, dict[str, Any]]:
    configuration = ai_providers.configuration(provider)
    identity = {
        "provider": provider,
        "model": model or configuration.get("model"),
        "protocol": configuration.get("protocol"),
        "endpoint": configuration.get("endpoint"),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "system_sha256": hashlib.sha256((system or "").encode("utf-8")).hexdigest(),
        "max_output_tokens": max_output_tokens,
        "cache_schema": "1.0",
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest, identity


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
) -> ai_providers.ModelResult:
    """Call a provider with exact-request caching and hard CNY ceilings."""

    paper_id = _paper_for_stage(project_root, stage)
    key, identity = _cache_key(provider, prompt, system, max_output_tokens, model)
    cache_path = project_root / ".cache" / "model-responses" / f"{key}.json"
    if use_cache and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
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
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            result = None  # type: ignore[assignment]
        if result is not None:
            _append(
                _ledger(project_root),
                {
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
                },
            )
            return result

    predicted_input = estimate_tokens((system or "") + "\n" + prompt)
    predicted_cost = cost_cny(provider, predicted_input, max_output_tokens, model)
    status = budget_status(project_root, paper_id)
    if predicted_cost > float(status["project_remaining"]):
        raise ModelBudgetError(
            f"request could exceed project model budget: need up to CNY {predicted_cost:.4f}, "
            f"remaining CNY {status['project_remaining']:.4f}"
        )
    if paper_id and predicted_cost > float(status["paper_remaining"]):
        raise ModelBudgetError(
            f"request could exceed {paper_id} model budget: need up to CNY {predicted_cost:.4f}, "
            f"remaining CNY {status['paper_remaining']:.4f}"
        )

    result = ai_providers.call(
        provider,
        prompt,
        system=system,
        max_output_tokens=max_output_tokens,
        timeout=timeout,
        model=model,
    )
    input_tokens, output_tokens = usage_counts(result.usage)
    estimated = input_tokens is None or output_tokens is None
    input_tokens = input_tokens if input_tokens is not None else predicted_input
    output_tokens = output_tokens if output_tokens is not None else estimate_tokens(result.text)
    actual_cost = cost_cny(provider, input_tokens, output_tokens, model)
    result.cache_key = key
    _append(
        _ledger(project_root),
        {
            "schema_version": "1.0",
            "at": utc_now(),
            "run_id": run_id,
            "stage": stage,
            "paper_id": paper_id,
            "role": role,
            "provider": provider,
            "model": result.reported_model or result.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "usage_estimated": estimated,
            "cost_cny": actual_cost,
            "cache_hit": False,
            "cache_key": key,
        },
    )
    if use_cache:
        _write_cache(
            cache_path,
            {
                **identity,
                "provider": result.provider,
                "model": result.model,
                "text": result.text,
                "usage": result.usage,
                "request_id": result.request_id,
                "reported_model": result.reported_model,
                "protocol": result.protocol,
                "endpoint": result.endpoint,
                "gateway": result.gateway,
                "created_at": utc_now(),
            },
        )
    return result
