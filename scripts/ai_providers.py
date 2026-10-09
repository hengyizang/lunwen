#!/usr/bin/env python3
"""Dependency-free model adapters for the Doctoral Research OS.

The adapters return model text and auditable request metadata. They never
execute model-produced commands; local execution remains under the human-gated
Python control plane.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


PROVIDERS = (
    "anthropic",
    "openai",
    "uuapi-anthropic",
    "uuapi-openai",
)
UUAPI_ANTHROPIC_UA = "claude-cli/2.0.76 (external, cli)"
UUAPI_OPENAI_UA = "codex_cli_rs/0.77.0 (external, cli)"


class ProviderError(RuntimeError):
    """A provider configuration, transport or response failure."""


@dataclass
class ModelResult:
    provider: str
    model: str
    text: str
    usage: dict[str, Any]
    request_id: str | None = None
    reported_model: str | None = None
    protocol: str | None = None
    endpoint: str | None = None
    gateway: str | None = None
    cache_hit: bool = False
    cache_key: str | None = None
    completion_status: str | None = None


def completion_status(data: dict[str, Any], protocol: str) -> str:
    """Preserve termination failures even when the provider returned partial text."""
    if protocol == "openai_responses":
        for item in data.get("output", []):
            if isinstance(item, dict):
                if item.get("status") in {"incomplete", "failed", "in_progress"}:
                    return str(item["status"])
                if any(p.get("type") == "refusal" for p in item.get("content", []) if isinstance(p, dict)):
                    return "refusal"
                if item.get("type") in {"function_call", "tool_call"}:
                    return "tool_use"
        return str(data.get("status") or "unknown")
    if protocol == "openai_chat_completions":
        choice = (data.get("choices") or [{}])[0]
        if not isinstance(choice, dict):
            return "unknown"
        if (choice.get("message") or {}).get("refusal"):
            return "refusal"
        reason = choice.get("finish_reason")
        return "completed" if reason == "stop" else str(reason or "unknown")
    reason = data.get("stop_reason")
    return "completed" if reason in {"end_turn", "stop_sequence"} else str(reason or "unknown")


def require_complete(result: ModelResult) -> None:
    strict = os.environ.get("DR_OS_REQUIRE_MODEL_AUTH") == "1"
    status = result.completion_status or "unknown"
    if status != "completed" and (strict or status != "unknown"):
        raise ProviderError(f"model response did not complete ({status}); no artifact writes or automatic paid retry")


def _request(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int = 180,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    # A generation POST may already be billable when its response is lost.
    # Neither official/custom gateways nor both protocols share a verified
    # idempotency contract. One reservation therefore permits ONE transport
    # attempt. The caller retains it on all ambiguous failures for reconciliation.
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
            if not isinstance(value, dict):
                raise ProviderError("API response was not a JSON object; reconcile billing before retry")
            return value
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"API HTTP {exc.code}; no automatic generation retry; reconcile billing") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderError("API response unavailable; no automatic generation retry; reconcile billing") from exc


def _get_json(
    url: str, headers: dict[str, str], timeout: int = 30
) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"API HTTP {exc.code}: {detail[:1000]}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ProviderError(f"API request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise ProviderError("API response was not a JSON object")
    return value


def _openai_text(data: dict[str, Any]) -> str:
    text = data.get("output_text")
    if isinstance(text, str) and text:
        return text
    chunks: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for part in item.get("content", []):
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    text = "\n".join(chunks)
    if not text:
        raise ProviderError("OpenAI Responses payload contained no text")
    return text


def _chat_completions_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("OpenAI Chat Completions payload contained no choices")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str) and content:
        return content
    if isinstance(content, list):
        chunks = [
            str(item.get("text"))
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        if chunks:
            return "\n".join(chunks)
    raise ProviderError("OpenAI Chat Completions payload contained no text")


def _anthropic_text(data: dict[str, Any]) -> str:
    parts = [
        part.get("text", "")
        for part in data.get("content", [])
        if isinstance(part, dict) and part.get("type") == "text"
    ]
    text = "\n".join(part for part in parts if part)
    if not text:
        raise ProviderError("Anthropic Messages payload contained no text")
    return text


def _reported_model(data: dict[str, Any]) -> str | None:
    value = data.get("model")
    return value if isinstance(value, str) and value.strip() else None


def _strict_model_check(requested: str, reported: str | None) -> None:
    strict = os.environ.get("UUAPI_STRICT_MODEL_ID", "true").lower()
    if strict in {"0", "false", "no"}:
        return
    if not reported:
        raise ProviderError(
            "UUAPI response omitted the model ID, so model identity cannot be "
            "verified. Keep UUAPI_STRICT_MODEL_ID=true and contact the gateway."
        )
    if reported != requested:
        raise ProviderError(
            "UUAPI reported a different model ID: "
            f"requested={requested!r}, reported={reported!r}. "
            "Use the reported ID in UUAPI_*_MODEL, or explicitly set "
            "UUAPI_STRICT_MODEL_ID=false after reviewing the gateway mapping."
        )


def _safe_endpoint_for_audit(raw: str) -> str:
    """Strip credentials and query parameters before persisting an endpoint."""

    parsed = urlsplit(raw)
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def provider_family(provider: str) -> str:
    """Return the model/protocol family used for independence checks."""

    if provider in {"anthropic", "uuapi-anthropic"}:
        return "anthropic"
    if provider in {"openai", "uuapi-openai"}:
        return "openai"
    raise ProviderError(f"Unknown provider: {provider}")


def _validated_https_root(raw: str, name: str = "UUAPI_BASE_URL") -> str:
    # Validate before normalization: urlsplit silently strips some whitespace.
    if any(ch.isspace() or ord(ch) < 32 for ch in raw.strip()):
        raise ProviderError(f"{name} must be a valid HTTPS root")
    try:
        parsed = urlsplit(raw.strip())
        port = parsed.port
    except ValueError as exc:
        raise ProviderError(f"{name} must be a valid HTTPS root") from exc
    if parsed.scheme != "https" or not parsed.hostname or port == 0:
        raise ProviderError(f"{name} must be a valid HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError(f"{name} must not contain credentials, query or fragment")
    path = parsed.path.rstrip("/")
    if path.endswith(("/responses", "/chat/completions", "/messages", "/usage")):
        raise ProviderError(f"{name} needs the HTTPS root or /v1 base, not a full API endpoint")
    if path.endswith("/v1"):
        path = path[:-3]
    return urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))


def _uuapi_setting_names(provider: str | None, environment: Mapping[str, str]) -> tuple[str, str]:
    if provider in {"uuapi-openai", "uuapi-anthropic"}:
        prefix = "UUAPI_OPENAI" if provider == "uuapi-openai" else "UUAPI_ANTHROPIC"
        names = (f"{prefix}_API_KEY", f"{prefix}_BASE_URL")
        # An override is an atomic pair. Never send a shared key to a new host
        # (or a new key to the old host) because one half was left empty.
        if any(environment.get(name, "").strip() for name in names):
            return names
    return "UUAPI_API_KEY", "UUAPI_BASE_URL"


def _uuapi_root(provider: str | None = None, environment: Mapping[str, str] | None = None) -> str:
    env = os.environ if environment is None else environment
    _, name = _uuapi_setting_names(provider, env)
    value = env.get(name, "").strip()
    if not value:
        raise ProviderError(f"{name} is not configured; supply the exact HTTPS root or /v1 base")
    return _validated_https_root(value, name)


def _uuapi_endpoint(path: str, provider: str | None = None,
                    environment: Mapping[str, str] | None = None) -> str:
    return f"{_uuapi_root(provider, environment)}/v1/{path.lstrip('/')}"


def _uuapi_key(provider: str | None = None, environment: Mapping[str, str] | None = None) -> str:
    env = os.environ if environment is None else environment
    name, _ = _uuapi_setting_names(provider, env)
    key = env.get(name, "").strip()
    if not key:
        raise ProviderError(f"{name} is not configured")
    if any(ch.isspace() or ord(ch) < 32 for ch in key):
        raise ProviderError(f"{name} must not contain whitespace")
    return key


def _openai_protocol(environment: Mapping[str, str]) -> tuple[str, str]:
    protocol = (environment.get("UUAPI_OPENAI_PROTOCOL") or "responses").strip().lower()
    field = (environment.get("UUAPI_OPENAI_CHAT_TOKEN_FIELD") or "max_completion_tokens").strip()
    if protocol not in {"responses", "chat_completions"}:
        raise ProviderError("UUAPI_OPENAI_PROTOCOL must be responses or chat_completions")
    if field not in {"max_completion_tokens", "max_tokens"}:
        raise ProviderError("UUAPI_OPENAI_CHAT_TOKEN_FIELD must be max_completion_tokens or max_tokens")
    return protocol, field


def _uuapi_headers(protocol: str) -> dict[str, str]:
    provider = "uuapi-anthropic" if protocol == "anthropic_messages" else "uuapi-openai"
    key = _uuapi_key(provider)
    if protocol == "anthropic_messages":
        return {
            "Authorization": f"Bearer {key}",
            "x-api-key": key,
            "anthropic-version": os.environ.get("UUAPI_ANTHROPIC_VERSION") or "2023-06-01",
            "User-Agent": os.environ.get("UUAPI_ANTHROPIC_USER_AGENT") or UUAPI_ANTHROPIC_UA,
        }
    return {
        "Authorization": f"Bearer {key}",
        "User-Agent": os.environ.get("UUAPI_OPENAI_USER_AGENT") or UUAPI_OPENAI_UA,
    }


def call_openai(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_output_tokens: int = 8000,
    timeout: int = 180,
) -> ModelResult:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ProviderError("OPENAI_API_KEY is not configured")
    model = model or os.environ.get("OPENAI_MODEL", "gpt-5.6")
    content: Any = prompt
    if system:
        content = [
            {"role": "developer", "content": system},
            {"role": "user", "content": prompt},
        ]
    endpoint = os.environ.get(
        "OPENAI_BASE_URL", "https://api.openai.com/v1/responses"
    )
    data = _request(
        endpoint,
        {"Authorization": f"Bearer {key}"},
        {
            "model": model,
            "input": content,
            "max_output_tokens": max_output_tokens,
        },
        timeout,
    )
    return ModelResult(
        "openai",
        model,
        _openai_text(data),
        data.get("usage", {}) or {},
        data.get("id"),
        _reported_model(data),
        "openai_responses",
        _safe_endpoint_for_audit(endpoint),
        "official-or-custom",
        completion_status=completion_status(data, "openai_responses"),
    )


def call_anthropic(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_output_tokens: int = 8000,
    timeout: int = 180,
) -> ModelResult:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ProviderError("ANTHROPIC_API_KEY is not configured")
    model = model or os.environ.get("ANTHROPIC_MODEL")
    if not model:
        raise ProviderError(
            "ANTHROPIC_MODEL is not configured; set it to a current model ID"
        )
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_output_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    endpoint = os.environ.get(
        "ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1/messages"
    )
    data = _request(
        endpoint,
        {
            "x-api-key": key,
            "anthropic-version": os.environ.get(
                "ANTHROPIC_VERSION", "2023-06-01"
            ),
        },
        payload,
        timeout,
    )
    return ModelResult(
        "anthropic",
        model,
        _anthropic_text(data),
        data.get("usage", {}) or {},
        data.get("id"),
        _reported_model(data),
        "anthropic_messages",
        _safe_endpoint_for_audit(endpoint),
        "official-or-custom",
        completion_status=completion_status(data, "anthropic_messages"),
    )


def call_uuapi_openai(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_output_tokens: int = 8000,
    timeout: int = 180,
) -> ModelResult:
    model = model or os.environ.get("UUAPI_OPENAI_MODEL", "").strip()
    if not model:
        raise ProviderError("UUAPI_OPENAI_MODEL is not configured")
    protocol, token_field = _openai_protocol(os.environ)
    if protocol == "chat_completions":
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            token_field: max_output_tokens,
        }
        endpoint = _uuapi_endpoint("chat/completions", "uuapi-openai")
        audit_protocol = "openai_chat_completions"
    else:
        content: Any = prompt
        if system:
            content = [
                {"role": "developer", "content": system},
                {"role": "user", "content": prompt},
            ]
        payload = {
            "model": model,
            "input": content,
            "max_output_tokens": max_output_tokens,
            "store": False,
        }
        endpoint = _uuapi_endpoint("responses", "uuapi-openai")
        audit_protocol = "openai_responses"
    data = _request(
        endpoint,
        _uuapi_headers(audit_protocol),
        payload,
        timeout,
    )
    reported = _reported_model(data)
    _strict_model_check(model, reported)
    return ModelResult(
        "uuapi-openai",
        model,
        _chat_completions_text(data) if protocol == "chat_completions" else _openai_text(data),
        data.get("usage", {}) or {},
        data.get("id"),
        reported,
        audit_protocol,
        endpoint,
        "uuapi",
        completion_status=completion_status(data, audit_protocol),
    )


def call_uuapi_anthropic(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_output_tokens: int = 8000,
    timeout: int = 180,
) -> ModelResult:
    model = model or os.environ.get("UUAPI_ANTHROPIC_MODEL", "").strip()
    if not model:
        raise ProviderError("UUAPI_ANTHROPIC_MODEL is not configured")
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_output_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    endpoint = _uuapi_endpoint("messages", "uuapi-anthropic")
    data = _request(
        endpoint,
        _uuapi_headers("anthropic_messages"),
        payload,
        timeout,
    )
    reported = _reported_model(data)
    _strict_model_check(model, reported)
    return ModelResult(
        "uuapi-anthropic",
        model,
        _anthropic_text(data),
        data.get("usage", {}) or {},
        data.get("id"),
        reported,
        "anthropic_messages",
        endpoint,
        "uuapi",
        completion_status=completion_status(data, "anthropic_messages"),
    )


def uuapi_usage(timeout: int = 30) -> dict[str, Any]:
    """Return UUAPI's non-generation wallet/quota response."""

    return _get_json(
        _uuapi_endpoint("usage"),
        {
            "Authorization": f"Bearer {_uuapi_key()}",
            "User-Agent": "doctoral-research-os/1.1",
        },
        timeout,
    )


def configuration(provider: str, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Describe configuration without exposing credentials."""

    env = os.environ if environment is None else environment
    if provider == "openai":
        return {
            "provider": provider,
            "configured": bool(env.get("OPENAI_API_KEY")),
            "model": env.get("OPENAI_MODEL", "gpt-5.6"),
            "protocol": "openai_responses",
            "endpoint": _safe_endpoint_for_audit(
                env.get(
                    "OPENAI_BASE_URL", "https://api.openai.com/v1/responses"
                )
            ),
        }
    if provider == "anthropic":
        return {
            "provider": provider,
            "configured": bool(
                env.get("ANTHROPIC_API_KEY")
                and env.get("ANTHROPIC_MODEL")
            ),
            "model": env.get("ANTHROPIC_MODEL"),
            "protocol": "anthropic_messages",
            "endpoint": _safe_endpoint_for_audit(
                env.get(
                    "ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1/messages"
                )
            ),
        }
    if provider in {"uuapi-openai", "uuapi-anthropic"}:
        model_key = "UUAPI_OPENAI_MODEL" if provider == "uuapi-openai" else "UUAPI_ANTHROPIC_MODEL"
        key_name, base_name = _uuapi_setting_names(provider, env)
        errors: list[str] = []
        endpoint: str | None = None
        token_field: str | None = None
        protocol = "anthropic_messages"
        path = "messages"
        if provider == "uuapi-openai":
            try:
                selected, token_field = _openai_protocol(env)
                path = "chat/completions" if selected == "chat_completions" else "responses"
                protocol = "openai_chat_completions" if selected == "chat_completions" else "openai_responses"
                if selected == "responses":
                    token_field = "max_output_tokens"
            except ProviderError as exc:
                errors.append(str(exc))
        try:
            endpoint = _uuapi_endpoint(path, provider, env)
        except ProviderError as exc:
            errors.append(str(exc))
        try:
            _uuapi_key(provider, env)
        except ProviderError as exc:
            errors.append(str(exc))
        model = env.get(model_key, "").strip()
        if not model:
            errors.append(f"{model_key} is not configured")
        elif any(ch.isspace() or ord(ch) < 32 for ch in model):
            errors.append(f"{model_key} must be an exact model ID without whitespace")
        return {
            "provider": provider,
            "configured": not errors,
            "model": model,
            "protocol": protocol,
            "endpoint": endpoint,
            "max_tokens_field": token_field if provider == "uuapi-openai" else "max_tokens",
            "key_setting": key_name,
            "base_setting": base_name,
            "configuration_error": "; ".join(errors) or None,
            "strict_model_id": (env.get("UUAPI_STRICT_MODEL_ID") or "true").strip().lower()
            not in {"0", "false", "no"},
        }
    raise ProviderError(f"Unknown provider: {provider}")


def call(provider: str, prompt: str, **kwargs: Any) -> ModelResult:
    if provider == "openai":
        return call_openai(prompt, **kwargs)
    if provider == "anthropic":
        return call_anthropic(prompt, **kwargs)
    if provider == "uuapi-openai":
        return call_uuapi_openai(prompt, **kwargs)
    if provider == "uuapi-anthropic":
        return call_uuapi_anthropic(prompt, **kwargs)
    raise ProviderError(f"Unknown provider: {provider}")
