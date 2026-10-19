#!/usr/bin/env python3
"""Versioned, fail-closed task routes for the approved production model roster.

This module only selects a route. It never sends requests, grants spending
authority, approves scientific evidence or substitutes a model after failure.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts import ai_providers
except ImportError:
    import ai_providers  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "model-routing.json"
CYCLE_ROLES = (
    "semantic-planner", "persistent-writer", "independent-critic-initial",
    "persistent-remediator", "independent-critic-final",
)
WRITER_ROLES = {"persistent-writer", "persistent-remediator", "writer"}
READ_ONLY_ROLES = {"semantic-planner", "independent-critic-initial", "independent-critic-final"}
APPROVED_MODELS = {
    "sol": ("cheapai-gpt-pro", "gpt-6.1-sol", "openai"),
    "astra": ("cheapai-gpt-pro", "gpt-6-astra", "openai"),
    "luna": ("cheapai-gpt-discount", "gpt-5.6-luna", "openai"),
    "sonnet": ("codekey-kiro-enterprise", "claude-sonnet-5-5", "anthropic"),
    "opus": ("codekey-kiro-enterprise", "claude-opus-5-5", "anthropic"),
    "deepseek": ("codekey-deepseek", "deepseek-v4.1-flash", "deepseek"),
    "argon": ("codekey-gemini", "gemini-4-argon", "google"),
}
APPROVED_AUXILIARY_MODELS = {
    "metadata-extraction": "luna", "format-conversion": "sol", "screening-assist": "sol",
    "evidence-synthesis": "sol", "scientific-judgment": "astra", "independent-critique": "opus",
    "reader-translation": "sol", "reader-qa": "sol", "engineering-diagnosis": "deepseek",
    "multimodal-inspection": "argon",
}
APPROVED_STAGES = {
    "intake", "topic-intelligence", "paper-architecture", "experiment-design",
    "experiment-execution", "writing-and-review",
}
APPROVED_CRITICAL_TASKS = {
    "scientific-judgment", "core-story", "novelty", "critical-experiment-design",
    "complex-revision", "key-algorithm", "thesis-synthesis", "scientific-interpretation",
}
APPROVED_HEALTH_ROLES = {"endpoint-health", "model-signature", "model-instrumentation"}
APPROVED_HEALTH_STAGES = {"health", "acceptance", "instrumentation"}


def _exact_names(value: Any, expected: set[str], label: str) -> None:
    if (not isinstance(value, list) or any(not isinstance(item, str) for item in value)
            or len(value) != len(expected) or set(value) != expected):
        raise ValueError(f"production {label} must match the exact approved task boundary")


def production_enabled() -> bool:
    """Legacy consumers stay unchanged until the production profile is explicit."""
    value = os.environ.get("DR_OS_ROUTING_PROFILE", "")
    if value not in {"", "legacy", "production"}:
        raise ValueError("DR_OS_ROUTING_PROFILE must be production or legacy")
    return value == "production" or bool(os.environ.get("DR_OS_ROUTING_CONFIG"))


def load_policy(environment: Mapping[str, str] | None = None) -> tuple[dict[str, Any], str]:
    env = os.environ if environment is None else environment
    path = Path(env.get("DR_OS_ROUTING_CONFIG") or DEFAULT_POLICY)
    if path.is_symlink() or not path.is_file():
        raise ValueError("production routing policy must be a regular file")
    raw = path.read_bytes()
    try:
        policy = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("production routing policy is invalid JSON") from exc
    if (not isinstance(policy, dict) or policy.get("schema_version") != "1.0"
            or policy.get("profile") != "production"):
        raise ValueError("unsupported production routing policy")
    models = policy.get("models")
    if not isinstance(models, dict) or set(models) != set(APPROVED_MODELS):
        raise ValueError("production policy requires the approved seven-model roster")
    for name, row in models.items():
        if (not isinstance(row, dict) or not isinstance(row.get("provider"), str)
                or not isinstance(row.get("model"), str) or not row["model"]
                or row.get("reasoning_effort") not in {"medium", "high"}
                or type(row.get("max_output_tokens")) is not int or row["max_output_tokens"] < 1):
            raise ValueError(f"malformed production model route: {name}")
        provider = ai_providers.PRODUCTION_PROVIDERS.get(row["provider"])
        if not provider or provider["family"] != row.get("family"):
            raise ValueError("model route family differs from its actual provider family")
        if row["model"] not in provider["models"]:
            raise ValueError("model route is outside its actual transport allowlist")
        if (row["provider"], row["model"], row.get("family")) != APPROVED_MODELS[name]:
            raise ValueError("model route differs from the exact approved model identity")
        if name == "luna" and row["reasoning_effort"] != "medium":
            raise ValueError("Luna is accepted only at the tested medium effort")
        if name != "luna" and row["reasoning_effort"] != "high":
            raise ValueError("scientific and selected auxiliary routes require high effort")
    flags = policy.get("quality_policy", {})
    if (flags.get("automatic_paid_fallback") is not False
            or flags.get("unknown_cost_stops_execution") is not True
            or flags.get("claude_persistent_artifacts_allowed") is not False
            or flags.get("human_gate_approval_required") is not True):
        raise ValueError("production quality and spending boundaries may not be weakened")
    stages = policy.get("stage_routes")
    if not isinstance(stages, dict) or set(stages) != APPROVED_STAGES:
        raise ValueError("production stage routes are missing")
    for stage, routes in stages.items():
        if not isinstance(routes, dict) or set(routes) != set(CYCLE_ROLES):
            raise ValueError(f"production stage needs exactly five existing roles: {stage}")
        for role, key in routes.items():
            if key not in models:
                raise ValueError("production route references an unknown model")
            family = models[key].get("family")
            if role in WRITER_ROLES and family != "openai":
                raise ValueError("persistent scientific writers must use the OpenAI family")
            if role in WRITER_ROLES and key not in {"sol", "astra"}:
                raise ValueError("auxiliary models cannot become persistent scientific writers")
            if role in READ_ONLY_ROLES and family != "anthropic":
                raise ValueError("semantic planners and critics must use the Anthropic family")
            if stage in {"topic-intelligence", "paper-architecture", "experiment-design"}:
                expected = "astra" if role in WRITER_ROLES else "opus"
                if key != expected:
                    raise ValueError("core scientific stages require Astra writers and Opus planners/critics")
        if routes["independent-critic-final"] != "opus":
            raise ValueError("every fresh final critic must use Opus")
    auxiliary = policy.get("auxiliary_routes")
    if not isinstance(auxiliary, dict) or set(auxiliary) != set(APPROVED_AUXILIARY_MODELS):
        raise ValueError("production auxiliary routes are missing")
    for kind, row in auxiliary.items():
        if (not isinstance(row, dict) or row.get("model_key") not in models
                or not isinstance(row.get("quality_boundary"), str) or not row["quality_boundary"]
                or type(row.get("max_output_tokens")) is not int or row["max_output_tokens"] < 1):
            raise ValueError(f"malformed auxiliary route: {kind}")
        if row["model_key"] == "luna" and kind != "metadata-extraction":
            raise ValueError("Luna is accepted only for bounded source-field extraction")
        if row["model_key"] != APPROVED_AUXILIARY_MODELS[kind]:
            raise ValueError("auxiliary role differs from its exact approved model assignment")
    _exact_names(policy.get("critical_tasks"), APPROVED_CRITICAL_TASKS, "critical tasks")
    _exact_names(policy.get("health_roles"), APPROVED_HEALTH_ROLES, "health roles")
    _exact_names(policy.get("health_stages"), APPROVED_HEALTH_STAGES, "health stages")
    _exact_names(policy.get("auxiliary_stages"), APPROVED_STAGES | {"auxiliary"}, "auxiliary stages")
    return policy, hashlib.sha256(raw).hexdigest()


def select(stage: str, role: str, task_kind: str | None = None, *,
           requested_provider: str | None = None, requested_model: str | None = None) -> dict[str, Any]:
    """Return an exact named route, with its policy hash and quality boundary.

    Explicit task_kind marks a critical task before a call; no text heuristic
    chooses cheaper scientific judgment or inserts an extra review call.
    """
    policy, digest = load_policy()
    original_role = role
    if role == "writer":
        role = "persistent-writer"
    persistent = role in WRITER_ROLES
    boundary = "Evidence-bound artifact writing with independent audits and explicit human gates."
    if role in policy["health_roles"]:
        if stage not in policy["health_stages"]:
            raise ValueError("health/instrumentation roles require their explicit control stage")
        candidates = [(key, row) for key, row in policy["models"].items()
                      if row["provider"] == requested_provider and
                      (not requested_model or row["model"] == requested_model)]
        if not candidates:
            raise ValueError("probe provider/model is outside the approved production roster")
        key = candidates[0][0]
        ceiling = 256
        boundary = "Endpoint identity/instrumentation only; never scientific-quality evidence."
    elif role in CYCLE_ROLES:
        if stage not in policy["stage_routes"]:
            raise ValueError(f"no production stage route: {stage}")
        key = policy["stage_routes"][stage][role]
        if task_kind is not None:
            if task_kind not in policy["critical_tasks"]:
                raise ValueError(f"unknown explicit scientific task: {task_kind}")
            key = "astra" if persistent else "opus"
        ceiling = policy["models"][key]["max_output_tokens"]
        if not persistent:
            boundary = "Read-only semantic planning/independent audit; no scientific file writing or gate approval."
    elif role in policy["auxiliary_routes"]:
        if stage not in policy["auxiliary_stages"]:
            raise ValueError(f"no auxiliary production route at stage: {stage}")
        if task_kind is not None:
            raise ValueError("auxiliary tasks cannot silently become core scientific tasks")
        auxiliary = policy["auxiliary_routes"][role]
        key = auxiliary["model_key"]
        ceiling = auxiliary["max_output_tokens"]
        boundary = auxiliary["quality_boundary"]
    elif role in policy["critical_tasks"]:
        if stage not in policy["auxiliary_stages"]:
            raise ValueError(f"no scientific analysis route at stage: {stage}")
        key = "astra"
        ceiling = 5000
        boundary = "Internal core scientific analysis; preserve evidence, uncertainty and human decision authority."
    else:
        raise ValueError(f"no production model route for role: {original_role}")
    model = policy["models"][key]
    return {
        **model,
        "route_id": f"{policy['policy_version']}:{stage}:{original_role}:{task_kind or 'default'}:{key}",
        "policy_version": policy["policy_version"], "policy_sha256": digest,
        "stage": stage, "role": original_role, "task_kind": task_kind,
        "model_key": key, "max_output_tokens": ceiling,
        "persistent_output": persistent, "quality_boundary": boundary,
        "automatic_paid_fallback": False,
        "fresh_required": role.startswith("independent-critic") or role in {"independent-critique", *policy["health_roles"]},
    }


def resolve_call(stage: str, role: str, provider: str, model: str | None = None,
                 reasoning_effort: str | None = None, task_kind: str | None = None) -> dict[str, Any]:
    if not production_enabled():
        return {"provider": provider, "model": model, "reasoning_effort": reasoning_effort}
    route = select(stage, role, task_kind, requested_provider=provider, requested_model=model)
    # Explicit overrides cannot claim one route while paying another. Legacy
    # default provider names may resolve through the approved production map.
    if model is not None and model != route["model"]:
        raise ValueError("explicit model conflicts with the approved task route")
    if reasoning_effort is not None and reasoning_effort != route["reasoning_effort"]:
        raise ValueError("explicit reasoning effort conflicts with the approved task route")
    return route


def cycle_routes(stage: str, task_kind: str | None = None) -> dict[str, dict[str, Any]]:
    return {role: select(stage, role, task_kind) for role in CYCLE_ROLES}
