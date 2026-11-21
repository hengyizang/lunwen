#!/usr/bin/env python3
"""Versioned configurable task routes with actual provider and model identities.

This module only selects a route. It never sends requests, grants spending
authority, approves scientific evidence or substitutes a model after failure.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts import ai_providers
except ImportError:
    import ai_providers  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config" / "model-routing.json"
# Owner-supplied real transport model IDs. Git-ignored; never invent model names here.
LOCAL_MODEL_OVERRIDES = ROOT / "config" / "model-routing.local.json"
CYCLE_ROLES = (
    "semantic-planner", "persistent-writer", "independent-critic-initial",
    "persistent-remediator", "independent-critic-final",
)
WRITER_ROLES = {"persistent-writer", "persistent-remediator", "writer"}
READ_ONLY_ROLES = {"semantic-planner", "independent-critic-initial", "independent-critic-final"}
PANEL_MODELS = {"independent-critic-panel-domain": "opus", "independent-critic-panel-editorial": "argon",
                "independent-critic-panel-statistics": "deepseek"}
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
    "engineering-code-review": "deepseek", "engineering-test-design": "deepseek",
    "engineering-reproducibility": "deepseek",
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
_CALIBRATION_ROUTE = ContextVar("public_review_calibration_route", default=None)
_G1_TRANSPORT_ROUTE = ContextVar("g1_transport_validation_route", default=None)
VALIDATION_OUTPUT_CAPS = {4000, 12000}


def g1_transport_validation_active() -> bool:
    """Paid-tool adapters may defer work outside this thread's bounded trial."""
    return _G1_TRANSPORT_ROUTE.get() is not None


def g1_transport_validation_roster() -> str | None:
    scope = _G1_TRANSPORT_ROUTE.get()
    return scope.get("validation_roster") if scope else None


def g1_response_streaming_active() -> bool:
    scope = _G1_TRANSPORT_ROUTE.get()
    return bool(scope and scope.get("response_streaming"))


@contextmanager
def g1_transport_validation_route(project: Path, manifest_sha256: str, *, check_inputs=None, max_output_tokens=4000,
                                  validation_roster=None, response_streaming=False):
    """One explicitly scoped native G1 sample; never promote a production route."""
    from scripts.research_artifacts import path_in, read
    if (not production_enabled() or
            (os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1")):
        raise ValueError("G1 transport validation requires the production cloud executor")
    if (not isinstance(manifest_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256)
            or _G1_TRANSPORT_ROUTE.get() is not None or _CALIBRATION_ROUTE.get() is not None):
        raise ValueError("G1 transport validation requires one exact independent manifest scope")
    if type(max_output_tokens) is not int or max_output_tokens not in VALIDATION_OUTPUT_CAPS:
        raise ValueError("validation output tokens must be explicitly 4000 or 12000")
    if validation_roster not in (None, "astra-argon"):
        raise ValueError("G1 validation roster must be the explicit astra-argon sample or absent")
    if type(response_streaming) is not bool or response_streaming and validation_roster != "astra-argon":
        raise ValueError("Responses streaming requires the explicit astra-argon G1 sample")
    state = read(path_in(project, "state/run.json"))
    if (state.get("stage") != "topic-intelligence" or state.get("gate") != "G1"
            or state.get("status") != "awaiting_work" or state.get("approved_gates") != ["G0"]):
        raise ValueError("G1 transport validation requires actual awaiting-work G1 with only G0 approved")
    token = _G1_TRANSPORT_ROUTE.set({"manifest_sha256": manifest_sha256, "project_root": project.resolve(),
                                   "check_inputs": check_inputs, "attempted_roles": set(), "max_output_tokens": max_output_tokens,
                                   "validation_roster": validation_roster, "response_streaming": response_streaming})
    try:
        yield
    finally:
        _G1_TRANSPORT_ROUTE.reset(token)


@contextmanager
def public_review_calibration_route(seat: str, scope_sha256: str, *, max_output_tokens=4000):
    """Scope a fresh, read-only benchmark call to an actual production critic.

    This does not promote a transport candidate or change a persistent policy.
    Only the fixed public-review experiment may select these three identities.
    """
    if (not production_enabled() or
            (os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1")):
        raise ValueError("public-review calibration requires the production cloud executor")
    if (seat not in {"domain", "editorial", "statistics"} or
            not isinstance(scope_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", scope_sha256)
            or _CALIBRATION_ROUTE.get() is not None or _G1_TRANSPORT_ROUTE.get() is not None):
        raise ValueError("calibration requires one exact public-source manifest and a distinct critic seat")
    if type(max_output_tokens) is not int or max_output_tokens not in VALIDATION_OUTPUT_CAPS:
        raise ValueError("validation output tokens must be explicitly 4000 or 12000")
    baseline = select("writing-and-review", "independent-critic-panel-" + seat)
    token = _CALIBRATION_ROUTE.set({"seat": seat, "scope_sha256": scope_sha256, "baseline": baseline, "max_output_tokens": max_output_tokens})
    try:
        yield
    finally:
        _CALIBRATION_ROUTE.reset(token)


def _exact_names(value: Any, expected: set[str], label: str) -> None:
    if (not isinstance(value, list) or any(not isinstance(item, str) for item in value)
            or len(value) != len(expected) or set(value) != expected):
        raise ValueError(f"production {label} must match the exact approved task boundary")


def local_model_overrides() -> dict[str, tuple[str, str, str]]:
    """Read local model identities; aliases and roster size are user choices."""
    if not LOCAL_MODEL_OVERRIDES.is_file():
        return {}
    try:
        document = json.loads(LOCAL_MODEL_OVERRIDES.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError("local model configuration is invalid JSON") from exc
    rows = document.get("models") if isinstance(document, dict) else None
    if not isinstance(rows, dict):
        raise ValueError("local model configuration needs a models object")
    result = {}
    for name, row in rows.items():
        default = APPROVED_MODELS.get(name)
        if not isinstance(row, dict) or not isinstance(row.get("model"), str) or not row["model"].strip():
            raise ValueError("local model identity needs an exact model ID")
        provider = row.get("provider") or (default[0] if default else None)
        family = ai_providers.provider_family(provider)
        if row.get("family", family) != family:
            raise ValueError("local model family differs from its actual provider")
        result[name] = (provider, row["model"], family)
    return result


def _apply_local_model_overrides(policy: dict[str, Any], overrides=None) -> dict[str, Any]:
    models = policy.get("models") if isinstance(policy, dict) else None
    if isinstance(models, dict):
        for name, identity in (local_model_overrides() if overrides is None else overrides).items():
            row = models.setdefault(name, {"reasoning_effort": "high", "max_output_tokens": 12000})
            row.update(zip(("provider", "model", "family"), identity))
    return policy

def production_enabled() -> bool:
    """Legacy consumers stay unchanged until the production profile is explicit."""
    value = os.environ.get("DR_OS_ROUTING_PROFILE", "")
    if value not in {"", "legacy", "production"}:
        raise ValueError("DR_OS_ROUTING_PROFILE must be production or legacy")
    return (value == "production" or bool(os.environ.get("DR_OS_ROUTING_CONFIG"))
            or LOCAL_MODEL_OVERRIDES.is_file())


def load_policy(environment: Mapping[str, str] | None = None) -> tuple[dict[str, Any], str]:
    env = os.environ if environment is None else environment
    path = Path(env.get("DR_OS_ROUTING_CONFIG") or DEFAULT_POLICY)
    if path.is_symlink() or not path.is_file():
        raise ValueError("routing configuration must be a regular file")
    raw = path.read_bytes()
    try:
        policy = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("routing configuration is invalid JSON") from exc
    overrides = local_model_overrides()
    policy = _apply_local_model_overrides(policy, overrides)
    if not isinstance(policy, dict) or policy.get("schema_version") != "1.0":
        raise ValueError("unsupported routing configuration")
    models = policy.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("routing configuration needs at least one model")
    for name, row in models.items():
        if (not isinstance(row, dict) or not isinstance(row.get("provider"), str)
                or not isinstance(row.get("model"), str) or not row["model"].strip()
                or any(ch.isspace() or ord(ch) < 32 for ch in row["model"])
                or row.get("reasoning_effort") not in {None, "none", "minimal", "low", "medium", "high", "xhigh"}
                or type(row.get("max_output_tokens")) is not int or not 1 <= row["max_output_tokens"] <= 100000):
            raise ValueError(f"malformed model route: {name}")
        family = ai_providers.provider_family(row["provider"])
        if row.get("family", family) != family:
            raise ValueError("model route family differs from its actual provider family")
        row["family"] = family
    for routes in [policy.get("default_routes", {}), policy.get("panel_routes", {}), *policy.get("stage_routes", {}).values()]:
        if not isinstance(routes, dict) or any(key not in models for key in routes.values()):
            raise ValueError("route references an unknown model alias")
    for kind, row in policy.get("auxiliary_routes", {}).items():
        if (not isinstance(row, dict) or row.get("model_key") not in models
                or type(row.get("max_output_tokens")) is not int or row["max_output_tokens"] < 1):
            raise ValueError(f"malformed auxiliary route: {kind}")
    if policy.get("default_model", next(iter(models))) not in models:
        raise ValueError("default model references an unknown alias")
    digest = hashlib.sha256(raw).hexdigest()
    if overrides:
        digest = hashlib.sha256(json.dumps({"policy_sha256": digest, "model_overrides": overrides},
                                          sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return policy, digest

def select(stage: str, role: str, task_kind: str | None = None, *,
           requested_provider: str | None = None, requested_model: str | None = None) -> dict[str, Any]:
    """Select a configured preference, or honor an explicit provider/model.

    Stage and role describe the task; they do not authorize a model to write.
    A configured roster is a set of defaults, not a model allowlist.
    """
    policy, digest = load_policy()
    original_role = role
    if role == "writer":
        role = "persistent-writer"
    models = policy["models"]
    auxiliary = policy.get("auxiliary_routes", {}).get(role, {})
    key = (policy.get("stage_routes", {}).get(stage, {}).get(role)
           or policy.get("panel_routes", {}).get(role)
           or auxiliary.get("model_key")
           or policy.get("default_routes", {}).get(role)
           or policy.get("default_model") or next(iter(models)))
    g1_scope = _G1_TRANSPORT_ROUTE.get()
    if g1_scope and stage == "topic-intelligence" and role in CYCLE_ROLES:
        key = "astra" if role in WRITER_ROLES else "opus"
        requested_provider = requested_model = None
    model = dict(models[key])
    if requested_provider is not None or requested_model is not None:
        provider = requested_provider or model["provider"]
        matches = [(name, row) for name, row in models.items() if row["provider"] == provider
                   and (requested_model is None or row["model"] == requested_model)]
        if matches:
            key, row = next(((name, row) for name, row in matches if name == key), matches[0])
            model = dict(row)
        else:
            configured = ai_providers.configuration(provider)
            key = "explicit"
            model = {"provider": provider, "model": requested_model or configured.get("model"),
                     "family": ai_providers.provider_family(provider),
                     "reasoning_effort": "high" if provider in ai_providers.PRODUCTION_PROVIDERS else None,
                     "max_output_tokens": 12000}
            if not model["model"]:
                raise ValueError("the selected provider needs an exact model ID")
    ceiling = model["max_output_tokens"]
    if auxiliary and requested_provider is None and requested_model is None:
        ceiling = min(ceiling, auxiliary["max_output_tokens"])
    if role in APPROVED_HEALTH_ROLES:
        ceiling = min(ceiling, 256)
    persistent = role in WRITER_ROLES
    route = {
        **model,
        "route_id": f"{policy.get('policy_version', 'configured')}:{stage}:{original_role}:{task_kind or 'default'}:{key}",
        "policy_version": policy.get("policy_version", "configured"), "policy_sha256": digest,
        "stage": stage, "role": original_role, "task_kind": task_kind,
        "model_key": key, "max_output_tokens": ceiling,
        "persistent_output": persistent,
        "quality_boundary": auxiliary.get("quality_boundary", "Preserve sources, uncertainty and actual results."),
        "automatic_paid_fallback": False,
        "explicit_selection": requested_provider is not None or requested_model is not None,
        "fresh_required": role.startswith("independent-critic") or role in {"independent-critique", *APPROVED_HEALTH_ROLES},
    }
    calibration = _CALIBRATION_ROUTE.get()
    if calibration is not None and stage == "auxiliary" and original_role == "independent-critique":
        baseline = calibration["baseline"]
        scope = {"purpose": "public-review-calibration", "calibration_scope_sha256": calibration["scope_sha256"],
                 "seat": calibration["seat"], "production_panel_route": baseline, "max_output_tokens": calibration["max_output_tokens"]}
        digest = hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        route.update({key: baseline[key] for key in ("provider", "model", "family", "reasoning_effort", "model_key")})
        route.update(policy_sha256=digest, route_id="public-review-calibration:" + digest,
                     task_kind="scientific-judgment", max_output_tokens=calibration["max_output_tokens"], fresh_required=True,
                     persistent_output=False, temporary_validation_only=True, validation_scope=scope,
                     quality_boundary="Read-only public-review evidence-strength calibration; no gate approval, manuscript writing or route promotion.")
    g1 = _G1_TRANSPORT_ROUTE.get()
    if g1 is not None and stage == "topic-intelligence" and original_role in CYCLE_ROLES:
        if g1["check_inputs"] is not None:
            g1["check_inputs"]()
        scope = {"purpose": "g1-transport-validation", "manifest_sha256": g1["manifest_sha256"],
                 "project": g1["project_root"].name, "production_route": dict(route), "control_max_output_tokens": g1["max_output_tokens"]}
        if g1["validation_roster"] == "astra-argon":
            scope["validation_roster"] = g1["validation_roster"]
            selected = "astra" if role in WRITER_ROLES or role == "semantic-planner" else "argon"
            route.update({name: policy["models"][selected][name] for name in ("provider", "model", "family", "reasoning_effort")})
            route["model_key"] = selected
            if selected == "astra":
                route["provider"] = "codekey-codex-pro"
        elif role in WRITER_ROLES:
            if (route["provider"], route["model"], route["reasoning_effort"]) != ("cheapai-gpt-pro", "gpt-6-astra", "high"):
                raise ValueError("G1 validation may replace only the original same-model Astra transport")
            route["provider"] = "codekey-codex-pro"
        if role not in WRITER_ROLES:
            route["max_output_tokens"] = g1["max_output_tokens"]
        if g1["response_streaming"]:
            scope["response_streaming"] = True
            if route["provider"] == "codekey-codex-pro":
                route["response_streaming"] = True
        digest = hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        route.update(policy_sha256=digest, route_id="g1-transport-validation:" + digest,
                     temporary_validation_only=True, validation_scope=scope, validation_max_input_bytes=2_000_000)
    return route


def effective_task_kind(stage: str, role: str, task_kind: str | None = None,
                        task_profile: dict | None = None) -> str | None:
    """Keep explicitly declared task context without escalating stages or models."""
    if task_kind is not None:
        return task_kind
    return task_profile.get("task_class") if isinstance(task_profile, dict) and task_profile.get("task_class") != "unspecified" else None


def resolve_call(stage: str, role: str, provider: str, model: str | None = None,
                 reasoning_effort: str | None = None, task_kind: str | None = None,
                 task_profile: dict | None = None, *, project_root: Path | None = None) -> dict[str, Any]:
    g1 = _G1_TRANSPORT_ROUTE.get()
    if g1 is not None:
        if project_root is None or Path(project_root).resolve() != g1["project_root"]:
            raise ValueError("G1 transport validation is bound to its actual project")
        if stage != "topic-intelligence" or role not in CYCLE_ROLES or role in g1["attempted_roles"]:
            raise ValueError("G1 transport validation permits its five native roles once; additional paid helpers or retries require a separate ordinary operation")
        g1["attempted_roles"].add(role)
    if not production_enabled():
        return {"provider": provider, "model": model, "reasoning_effort": reasoning_effort}
    task_kind = effective_task_kind(stage, role, task_kind, task_profile)
    route = select(stage, role, task_kind, requested_provider=provider, requested_model=model)
    if reasoning_effort is not None:
        route["reasoning_effort"] = reasoning_effort
    return route


def cycle_routes(stage: str, task_kind: str | None = None, roles=None) -> dict[str, dict[str, Any]]:
    return {role: select(stage, role, task_kind) for role in (CYCLE_ROLES if roles is None else roles)}
