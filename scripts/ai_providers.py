#!/usr/bin/env python3
"""Dependency-free model adapters for the Doctoral Research OS.

The adapters return model text and auditable request metadata. They never
execute model-produced commands; local execution remains under the human-gated
Python control plane.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import http.client
import json
import os
import re
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote, urlsplit, urlunsplit


PROVIDERS = (
    "anthropic",
    "openai",
    "uuapi-anthropic",
    "uuapi-openai",
    "cheapai-gpt-pro",
    "cheapai-gpt-discount",
    "cheapai-kiro-discount",
    "cheapai-ccmax",
    "codekey-codex-pro",
    "codekey-codex-discount",
    "codekey-kiro-enterprise",
    "codekey-kiro-standard",
    "codekey-deepseek",
    "codekey-gemini",
    "codekey-gemini-chat",
    "codekey-kimi",
)
# Exact transport routes, not assertions about gateway authenticity or quality.
# UUAPI remains a deprecated compatibility adapter for historical run receipts.
PRODUCTION_PROVIDERS = {
    "cheapai-gpt-pro": {
        "family": "openai", "root": "https://cheapai.info", "path": "/v1/responses",
        "key_setting": "DR_OS_CHEAPAI_GPT_PRO_KEY", "model": "gpt-6.1-sol",
        "protocol": "openai_responses", "models": ("gpt-6.1-sol", "gpt-6-astra", "gpt-5.6-luna", "gpt-6.1-terra"),
    },
    "cheapai-gpt-discount": {
        "family": "openai", "root": "https://cheapai.info", "path": "/v1/responses",
        "key_setting": "DR_OS_CHEAPAI_GPT_DISCOUNT_KEY", "model": "gpt-5.6-luna",
        "protocol": "openai_responses", "models": ("gpt-5.6-luna", "gpt-6.1-sol", "gpt-6-astra", "gpt-6.1-terra"),
    },
    "cheapai-kiro-discount": {
        "family": "anthropic", "root": "https://cheapai.info", "path": "/v1/messages",
        "key_setting": "DR_OS_CHEAPAI_KIRO_DISCOUNT_KEY", "model": "claude-sonnet-5-5",
        "protocol": "anthropic_messages", "models": ("claude-sonnet-5-5", "claude-opus-5-5"),
    },
    "cheapai-ccmax": {
        "family": "anthropic", "root": "https://cheapai.info", "path": "/v1/messages",
        "key_setting": "DR_OS_CHEAPAI_CCMAX_KEY", "model": "claude-sonnet-5-5",
        "protocol": "anthropic_messages", "models": ("claude-sonnet-5-5", "claude-opus-5-5"),
    },
    "codekey-codex-pro": {
        "family": "openai", "root": "https://codekey.ai", "path": "/v1/responses",
        "key_setting": "DR_OS_CODEKEY_CODEX_PRO_KEY", "model": "gpt-6.1-sol",
        "protocol": "openai_responses", "models": ("gpt-6.1-sol", "gpt-6-astra", "gpt-5.6-luna", "gpt-6.1-terra"),
    },
    "codekey-codex-discount": {
        "family": "openai", "root": "https://codekey.ai", "path": "/v1/responses",
        "key_setting": "DR_OS_CODEKEY_CODEX_DISCOUNT_KEY", "model": "gpt-6.1-sol",
        "protocol": "openai_responses", "models": ("gpt-6.1-sol", "gpt-6-astra", "gpt-5.6-luna", "gpt-6.1-terra"),
    },
    "codekey-kiro-enterprise": {
        "family": "anthropic", "root": "https://codekey.ai", "path": "/v1/messages",
        "key_setting": "DR_OS_CODEKEY_KIRO_ENTERPRISE_KEY", "model": "claude-sonnet-5-5",
        "protocol": "anthropic_messages", "models": ("claude-sonnet-5-5", "claude-opus-5-5"),
    },
    "codekey-kiro-standard": {
        "family": "anthropic", "root": "https://codekey.ai", "path": "/v1/messages",
        "key_setting": "DR_OS_CODEKEY_KIRO_STANDARD_KEY", "model": "claude-sonnet-5-5",
        "protocol": "anthropic_messages", "models": ("claude-sonnet-5-5", "claude-opus-5-5"),
    },
    "codekey-deepseek": {
        "family": "deepseek", "root": "https://codekey.ai", "path": "/v1/chat/completions",
        "key_setting": "DR_OS_CODEKEY_DEEPSEEK_KEY", "model": "deepseek-v4.1-flash",
        "protocol": "deepseek_chat_completions", "models": ("deepseek-v4.1-flash",),
    },
    "codekey-gemini": {
        "family": "google", "root": "https://codekey.ai", "path": "/v1beta/models/{model}:generateContent",
        "key_setting": "DR_OS_CODEKEY_GEMINI_KEY", "model": "gemini-4-argon",
        "protocol": "gemini_generate_content", "models": ("gemini-4-argon", "gemini-4-argon-high"),
    },
    # Explicit diagnostic transport: never an automatic native-Gemini fallback.
    # Both Gemini routes share one credential and its central spending guard.
    "codekey-gemini-chat": {
        "family": "google", "root": "https://codekey.ai", "path": "/v1/chat/completions",
        "key_setting": "DR_OS_CODEKEY_GEMINI_KEY", "model": "gemini-4-argon",
        "protocol": "openai_chat_completions", "models": ("gemini-4-argon", "gemini-4-argon-high"),
    },
    "codekey-kimi": {
        "family": "moonshot", "root": "https://codekey.ai", "path": "/v1/chat/completions",
        "key_setting": "DR_OS_CODEKEY_KIMI_KEY", "model": "kimi-k3.1-pro",
        "protocol": "openai_chat_completions", "models": ("kimi-k3.1-pro",),
    },
}
UUAPI_ANTHROPIC_UA = "claude-cli/2.0.76 (external, cli)"
UUAPI_OPENAI_UA = "codex_cli_rs/0.77.0 (external, cli)"


class ProviderError(RuntimeError):
    """A provider configuration, transport or response failure."""


class _ProductionPayload(dict):
    """Decoded JSON plus provenance of the HTTP bytes actually read."""


def _response_evidence(data, *, headers=None, body=None, http_status=None, complete=True):
    """Private, redacted failure material; never include it in exception text."""
    from scripts.cloud_retry import redact
    if data is None and body is not None and complete:
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError):
            pass
    secrets = [value.removeprefix("Bearer ") for name, value in (headers or {}).items()
               if name.casefold() in {"authorization", "x-api-key", "x-goog-api-key"} and value]
    sensitive = {"authorization", "apikey", "accesstoken", "refreshtoken", "secret", "password", "token",
                 "credential", "accountid", "userid", "organizationid", "email", "thinking", "reasoningcontent", "signature"}

    def clean(value):
        if isinstance(value, dict):
            private_reasoning = {"text"} if value.get("thought") is True else {"summary", "content", "text"} if value.get("type") == "reasoning" else set()
            return {clean(str(key)): "[REDACTED]" if re.sub(r"[^a-z]", "", str(key).casefold()) in sensitive or key in private_reasoning else clean(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "[REDACTED]").replace(quote(secret, safe=""), "[REDACTED]")
            return redact(value)
        if isinstance(value, float) and not math.isfinite(value):
            return "[NONFINITE]"
        return value

    try:
        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode() if data is not None else None
    except (ValueError, TypeError, RecursionError):
        canonical = None
    metadata = dict(getattr(data, "http_evidence", {}))
    if body is not None:
        metadata = {"http_status": http_status if type(http_status) is int else None,
            "http_body_capture_complete": complete, "captured_http_body_bytes": len(body),
            "raw_http_body_sha256": hashlib.sha256(body).hexdigest() if complete else None,
            "captured_http_body_prefix_sha256": hashlib.sha256(body).hexdigest() if not complete else None}
    try:
        sanitized = clean(data) if isinstance(data, dict) else {"response_body_not_stored": "unparsed or non-object body omitted; capture metadata and hashes retained"}
    except RecursionError:
        sanitized = {"response_not_stored": "nested response exceeded safe diagnostic traversal"}
    source = sanitized if isinstance(sanitized, dict) else {}
    def label(value):
        return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:/-]{1,160}", value) else None
    def counts(value):
        fields = {"input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens", "cached_tokens", "reasoning_tokens",
                  "cache_read_input_tokens", "cache_creation_input_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
                  "promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "totalTokenCount", "cachedContentTokenCount",
                  "ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"}
        containers = {"input_tokens_details", "output_tokens_details", "prompt_tokens_details", "completion_tokens_details", "cache_creation"}
        if not isinstance(value, dict):
            return None
        return {key: item if key in fields else counts(item) for key, item in value.items()
                if key in fields and type(item) is int and item >= 0 or key in containers and isinstance(item, dict)}
    diagnostics = {key: label(source.get(key)) for key in ("model", "modelVersion", "id", "responseId", "stop_reason", "status") if key in source}
    diagnostics.update({key: counts(source[key]) for key in ("usage", "usageMetadata") if key in source})
    parts = [part for key in ("content", "output") for part in (source.get(key) if isinstance(source.get(key), list) else []) if isinstance(part, dict)]
    for candidate in source.get("candidates", []) if isinstance(source.get("candidates"), list) else []:
        content = candidate.get("content") if isinstance(candidate, dict) else None
        if isinstance(content, dict) and isinstance(content.get("parts"), list):
            parts.extend({"type": "thinking" if part.get("thought") is True else "text" if "text" in part else "other"}
                         for part in content["parts"] if isinstance(part, dict))
    diagnostics["content_block_types"] = [label(part.get("type")) for part in parts]
    diagnostics["finish_reasons"] = [label(row.get("finish_reason", row.get("finishReason")))
        for key in ("choices", "candidates") for row in (source.get(key) if isinstance(source.get(key), list) else []) if isinstance(row, dict)]
    return {"schema_version": "1.0", "response": sanitized, "diagnostics": diagnostics,
            "canonical_json_sha256": hashlib.sha256(canonical).hexdigest() if canonical is not None else None,
            "canonical_json_hash_available": canonical is not None, "http_evidence": metadata or {
                "raw_http_body_sha256": None, "http_body_capture_complete": None},
            "stored_body_is_redacted": True, "not_scientific_evidence": True}


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
    requested_effort: str | None = None
    # Requested effort is auditable intent, never an attestation of actual effort.
    attachment_sha256: tuple[str, ...] = ()
    route_id: str | None = None
    dynamic_candidate_id: str | None = None
    routing_policy_sha256: str | None = None
    response_metadata: dict[str, Any] | None = None


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

    if provider in PRODUCTION_PROVIDERS:
        return PRODUCTION_PROVIDERS[provider]["family"]
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


def _responses_payload(prompt: str, model: str, system: str | None, limit: int) -> dict[str, Any]:
    content = ([{"role": "developer", "content": system}, {"role": "user", "content": prompt}]
               if system else prompt)
    return {"model": model, "input": content, "max_output_tokens": limit}


def _anthropic_payload(prompt: str, model: str, system: str | None, limit: int) -> dict[str, Any]:
    payload = {"model": model, "max_tokens": limit, "messages": [{"role": "user", "content": prompt}]}
    if system:
        payload["system"] = system
    return payload


def _compatibility_result(provider: str, model: str, data: dict[str, Any],
                          protocol: str, endpoint: str) -> ModelResult:
    reported = _reported_model(data)
    gateway = provider.startswith("uuapi-")
    if gateway:
        _strict_model_check(model, reported)
    reader = {"openai_responses": _openai_text, "openai_chat_completions": _chat_completions_text,
              "anthropic_messages": _anthropic_text}[protocol]
    return ModelResult(provider, model, reader(data), data.get("usage", {}) or {}, data.get("id"),
        reported, protocol, endpoint if gateway else _safe_endpoint_for_audit(endpoint),
        "uuapi" if gateway else "official-or-custom", completion_status=completion_status(data, protocol))


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
    endpoint = os.environ.get(
        "OPENAI_BASE_URL", "https://api.openai.com/v1/responses"
    )
    data = _request(
        endpoint,
        {"Authorization": f"Bearer {key}"},
        _responses_payload(prompt, model, system, max_output_tokens),
        timeout,
    )
    return _compatibility_result("openai", model, data, "openai_responses", endpoint)


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
        _anthropic_payload(prompt, model, system, max_output_tokens),
        timeout,
    )
    return _compatibility_result("anthropic", model, data, "anthropic_messages", endpoint)


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
        payload = {**_responses_payload(prompt, model, system, max_output_tokens), "store": False}
        endpoint = _uuapi_endpoint("responses", "uuapi-openai")
        audit_protocol = "openai_responses"
    data = _request(
        endpoint,
        _uuapi_headers(audit_protocol),
        payload,
        timeout,
    )
    return _compatibility_result("uuapi-openai", model, data, audit_protocol, endpoint)


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
    endpoint = _uuapi_endpoint("messages", "uuapi-anthropic")
    data = _request(
        endpoint,
        _uuapi_headers("anthropic_messages"),
        _anthropic_payload(prompt, model, system, max_output_tokens),
        timeout,
    )
    return _compatibility_result("uuapi-anthropic", model, data, "anthropic_messages", endpoint)


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


class _NoGenerationRedirect(urllib.request.HTTPRedirectHandler):
    """Do not replay a billable POST or forward credentials to another URL."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        raise ProviderError("generation redirect refused; reconcile billing before retry")


def _responses_sse(body, headers, status, *, complete=True):
    """Use the full response.completed object, never assembled text deltas.

    Contract: https://developers.openai.com/api/reference/resources/responses/streaming-events
    and openai/openai-python ResponseCompletedEvent (read 2026-11-08).
    """
    value, terminal, name, data, identity, stream_error = None, None, None, [], {}, False
    authoritative = {"response.created", "response.in_progress", "response.completed", "response.failed", "response.incomplete"}
    try:
        for raw_line in body.removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n"):
            line = raw_line.decode("utf-8")
            if not line:
                if data:
                    content = "\n".join(data)
                    if content == "[DONE]" and name:
                        raise ValueError("typed DONE is not a terminal response event")
                    if content != "[DONE]":
                        event = json.loads(content)
                        kind = event.get("type") if isinstance(event, dict) else None
                        if not isinstance(kind, str) or (name and name != kind) or terminal:
                            raise ValueError("invalid or post-terminal SSE event")
                        if kind in authoritative:
                            if kind in {"response.completed", "response.failed", "response.incomplete"}:
                                terminal = kind
                            if not isinstance(event.get("response"), dict):
                                raise ValueError("authoritative SSE event lacks its response")
                            value = event["response"]
                            if (value.get("object") != "response" or not isinstance(value.get("output"), list)
                                    or type(event.get("sequence_number")) is not int or event["sequence_number"] < 0):
                                raise ValueError("invalid authoritative SSE response shape")
                            for key in ("model", "id"):
                                actual = value.get(key)
                                if (not isinstance(actual, str) or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,160}", actual)
                                        or key in identity and identity[key] != actual):
                                    raise ValueError("SSE response identity changed or was malformed")
                                identity[key] = actual
                            if kind in {"response.created", "response.in_progress"}:
                                if value.get("status") not in {"queued", "in_progress"}:
                                    raise ValueError("invalid nonterminal SSE response status")
                            elif value.get("status") != kind.removeprefix("response."):
                                raise ValueError("invalid terminal response status")
                        elif kind == "error":
                            value, stream_error = event, True
                            raise ValueError("SSE error event")
                name, data = None, []
            elif not line.startswith(":"):
                field, _, content = line.partition(":")
                content = content.removeprefix(" ")
                if field == "event":
                    name = content
                elif field == "data":
                    data.append(content)
        if data or terminal != "response.completed" or not complete:
            raise ValueError("SSE ended without a complete terminal response")
    except (ValueError, TypeError, RecursionError):
        error = ProviderError("Responses SSE was incomplete or invalid; no automatic generation retry; reconcile billing")
        error.response_evidence = _response_evidence(value, headers=headers, body=body, http_status=status, complete=complete)
        if stream_error:
            code = _response_evidence({"id": value.get("code")}, headers=headers)["diagnostics"].get("id")
            error.response_evidence["response"] = {"type": "error", "code": code}
            error.response_evidence["diagnostics"]["error_code"] = code
        error.response_evidence["http_evidence"].update(response_format="sse", sse_terminal_event=terminal)
        initial = _response_evidence(identity, headers=headers)["diagnostics"]
        error.response_evidence["http_evidence"]["sse_initial_identity"] = {key: initial[key] for key in ("model", "id") if key in initial}
        raise error from None
    return value


def _sse_failure_evidence(body, headers, status):
    try:
        _responses_sse(body, headers, status, complete=False)
    except ProviderError as error:
        return error.response_evidence


def _production_request(url: str, headers: dict[str, str], payload: dict[str, Any],
                        timeout: int) -> dict[str, Any]:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ProviderError("production generation is restricted to the authorized cloud runner")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc not in {"cheapai.info", "codekey.ai"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ProviderError("production generation requires an exact configured HTTPS endpoint")
    streaming = payload.get("stream") is True
    if streaming:
        from scripts.model_routing import g1_response_streaming_active
        if url != "https://codekey.ai/v1/responses" or payload.get("model") != "gpt-6-astra" or not g1_response_streaming_active():
            raise ProviderError("Responses streaming requires the scoped Astra G1 transport")
    from scripts.relay_guard import authorize_transport
    authorize_transport(url, headers, payload=payload)
    request = urllib.request.Request(url, data=json.dumps(payload, allow_nan=False).encode("utf-8"),
                                     headers={**headers, "Content-Type": "application/json",
                                              "User-Agent": "lunwen-production-research/1.0",
                                              "Accept": "text/event-stream" if streaming else "application/json"}, method="POST")
    # One reservation permits one POST. No retries, protocol fallbacks or paid
    # warm-ups. A lost response remains an outstanding spend reservation.
    body = None
    status = None
    deadline = time.monotonic() + timeout
    try:
        with urllib.request.build_opener(_NoGenerationRedirect()).open(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if streaming:
                body = bytearray()
                while len(body) <= 4 * 1024 * 1024:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("bounded stream deadline")
                    socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
                    if socket is not None:
                        socket.settimeout(remaining)
                    chunk = response.read1(min(65536, 4 * 1024 * 1024 + 1 - len(body)))
                    if not chunk:
                        remaining_length = getattr(response, "length", None)
                        if remaining_length is not None and remaining_length > 0:
                            raise http.client.IncompleteRead(b"", remaining_length)
                        break
                    body.extend(chunk)
                body = bytes(body)
            else:
                body = response.read(4 * 1024 * 1024 + 1)
            if len(body) > 4 * 1024 * 1024:
                error = ProviderError("generation response exceeded size limit; reconcile billing")
                error.response_evidence = (_sse_failure_evidence(body, headers, status) if streaming else
                    _response_evidence(None, headers=headers, body=body, http_status=status, complete=False))
                raise error
            if streaming:
                if response.headers.get("Content-Type", "").split(";")[0].strip().lower() != "text/event-stream":
                    error = ProviderError("Responses stream has the wrong content type; reconcile billing")
                    error.response_evidence = _response_evidence(None, headers=headers, body=body, http_status=status)
                    raise error
                value = _responses_sse(body, headers, status)
            else:
                value = json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error = ProviderError(f"API HTTP {exc.code}; no automatic generation retry; reconcile billing")
        try:
            body = exc.read(4 * 1024 * 1024 + 1)
        except (OSError, AttributeError):
            body = None
        error.response_evidence = _response_evidence(None, headers=headers, body=body, http_status=exc.code,
                                                    complete=body is not None and len(body) <= 4 * 1024 * 1024)
        raise error from None
    except (OSError, http.client.HTTPException, ValueError, RecursionError) as exc:
        error = ProviderError("API response unavailable; no automatic generation retry; reconcile billing")
        if body is not None:
            error.response_evidence = (_sse_failure_evidence(body, headers, status) if streaming else
                _response_evidence(None, headers=headers, body=body, http_status=status))
            error.response_evidence["http_evidence"]["response_error_type"] = type(exc).__name__
        raise error from None
    if not isinstance(value, dict) or value.get("error"):
        error = ProviderError("generation response was not a successful JSON object; reconcile billing")
        error.response_evidence = _response_evidence(value, headers=headers, body=body, http_status=status)
        raise error
    captured = _ProductionPayload(value)
    captured.http_evidence = {"http_status": status if type(status) is int else None,
        "http_body_capture_complete": True, "captured_http_body_bytes": len(body),
        "raw_http_body_sha256": hashlib.sha256(body).hexdigest()}
    if streaming:
        captured.http_evidence.update(response_format="sse", sse_terminal_event="response.completed")
    return captured


def _production_identity(requested: str, reported: Any) -> str:
    # An exact echo is a traceability condition, not proof of genuine weights.
    if not isinstance(reported, str) or reported != requested:
        error = ProviderError("production response model ID missing or mismatched; quarantine route and reconcile billing")
        # Diagnostic identity only; the caller must still reject the response.
        error.reported_model = reported if isinstance(reported, str) and re.fullmatch(r"[A-Za-z0-9._/-]{1,160}", reported) else None
        raise error
    return reported


def _token_count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderError(f"invalid {name} usage receipt; reconcile billing")
    return value


def _production_usage(data: dict[str, Any], family: str, protocol: str | None = None) -> dict[str, Any]:
    native_google = family == "google" and protocol != "openai_chat_completions"
    raw = data.get("usageMetadata" if native_google else "usage")
    if not isinstance(raw, dict):
        raise ProviderError("missing production token usage; reconcile billing")
    usage = dict(raw)
    if family == "deepseek" or protocol == "openai_chat_completions":
        inputs = _token_count(raw.get("prompt_tokens"), "prompt_tokens")
        outputs = _token_count(raw.get("completion_tokens"), "completion_tokens")
        prompt_details = raw.get("prompt_tokens_details", {})
        if not isinstance(prompt_details, dict):
            raise ProviderError("malformed prompt token details; reconcile billing")
        detail_cached = _token_count(prompt_details.get("cached_tokens", 0), "cached_tokens")
        cached = _token_count(raw.get("prompt_cache_hit_tokens", detail_cached), "prompt_cache_hit_tokens")
        if "prompt_cache_hit_tokens" in raw and "cached_tokens" in prompt_details and cached != detail_cached:
            raise ProviderError("cache usage receipts disagree; reconcile billing")
        if cached > inputs:
            raise ProviderError("cache hit tokens exceed total input; reconcile billing")
        if "prompt_cache_miss_tokens" in raw:
            missed = _token_count(raw["prompt_cache_miss_tokens"], "prompt_cache_miss_tokens")
            if missed + cached != inputs:
                raise ProviderError("cache hit/miss tokens differ from input total; reconcile billing")
        usage.update(input_tokens=inputs, output_tokens=outputs,
                     input_tokens_details={"cached_tokens": cached})
        # completion_tokens already includes reasoning. Never add it again.
        details = raw.get("completion_tokens_details", {})
        if not isinstance(details, dict):
            raise ProviderError("malformed completion token details; reconcile billing")
        reasoning = _token_count(details.get("reasoning_tokens", 0), "reasoning_tokens")
        if reasoning > outputs:
            raise ProviderError("reasoning tokens exceed output total; reconcile billing")
        usage["output_tokens_details"] = {"reasoning_tokens": reasoning}
    elif native_google:
        inputs = _token_count(raw.get("promptTokenCount"), "promptTokenCount")
        candidates = _token_count(raw.get("candidatesTokenCount"), "candidatesTokenCount")
        thoughts = _token_count(raw.get("thoughtsTokenCount", 0), "thoughtsTokenCount")
        cached = _token_count(raw.get("cachedContentTokenCount", 0), "cachedContentTokenCount")
        if cached > inputs:
            raise ProviderError("cached content exceeds prompt tokens; reconcile billing")
        if "totalTokenCount" in raw and _token_count(raw["totalTokenCount"], "totalTokenCount") != inputs + candidates + thoughts:
            raise ProviderError("Google token components differ from total; reconcile billing")
        usage.update(input_tokens=inputs, output_tokens=candidates + thoughts,
                     input_tokens_details={"cached_tokens": cached},
                     output_tokens_details={"reasoning_tokens": thoughts})
    else:
        _token_count(raw.get("input_tokens"), "input_tokens")
        _token_count(raw.get("output_tokens"), "output_tokens")
    return usage


def _validated_attachments(attachments: Any) -> list[dict[str, Any]]:
    if attachments is None:
        return []
    if not isinstance(attachments, list) or len(attachments) > 5:
        raise ProviderError("attachments must be a list of at most five inline files")
    result = []
    size = 0
    allowed = {"application/pdf", "text/plain", "image/png", "image/jpeg", "image/webp"}
    for item in attachments:
        if (not isinstance(item, dict) or set(item) - {"mime_type", "data_base64", "sha256", "filename"}
                or not isinstance(item.get("mime_type"), str)
                or item.get("mime_type") not in allowed):
            raise ProviderError("unsupported attachment fields or MIME type")
        encoded = item.get("data_base64")
        if not isinstance(encoded, str) or len(encoded) > 14 * 1024 * 1024:
            raise ProviderError("attachment requires bounded base64 data")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ProviderError("attachment base64 data is invalid") from None
        size += len(decoded)
        if not decoded or size > 10 * 1024 * 1024:
            raise ProviderError("attachments must be nonempty and at most 10 MiB total")
        digest = hashlib.sha256(decoded).hexdigest()
        if item.get("sha256") != digest:
            raise ProviderError("attachment content differs from its declared SHA-256")
        mime = item["mime_type"]
        signatures = {"application/pdf": decoded.startswith(b"%PDF-"),
                      "image/png": decoded.startswith(b"\x89PNG\r\n\x1a\n"),
                      "image/jpeg": decoded.startswith(b"\xff\xd8\xff"),
                      "image/webp": decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP"}
        if mime in signatures and not signatures[mime]:
            raise ProviderError("attachment MIME type differs from its file signature")
        if mime == "text/plain":
            try:
                decoded.decode("utf-8")
            except UnicodeDecodeError:
                raise ProviderError("text attachment must contain UTF-8 text") from None
        filename = item.get("filename", "attachment.pdf" if mime == "application/pdf" else "attachment")
        if (not isinstance(filename, str) or not filename or len(filename) > 120
                or any(ch in filename for ch in "/\\") or any(ord(ch) < 32 for ch in filename)):
            raise ProviderError("attachment filename must be a simple bounded name")
        result.append({**item, "filename": filename, "decoded": decoded})
    return result


def _google_text(data: dict[str, Any]) -> tuple[str, str]:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], dict):
        raise ProviderError("Google response must contain one candidate; reconcile billing")
    candidate = candidates[0]
    content = candidate.get("content")
    if not isinstance(content, dict):
        raise ProviderError("malformed Google response content; reconcile billing")
    parts = content.get("parts", [])
    if not isinstance(parts, list):
        raise ProviderError("malformed Google response parts; reconcile billing")
    # Internal thought parts never become persistent scientific prose.
    text = "\n".join(part["text"] for part in parts
                     if isinstance(part, dict) and isinstance(part.get("text"), str) and not part.get("thought"))
    if not text:
        raise ProviderError("Google response contained no final text; reconcile billing")
    stop = candidate.get("finishReason")
    status = "completed" if stop == "STOP" else str(stop or "unknown")
    if any(isinstance(part, dict) and "functionCall" in part for part in parts):
        status = "tool_use"
    return text, status


def validate_attachments(attachments: Any) -> list[dict[str, Any]]:
    """Validate inline files before budget reservation; never perform network IO.

    Returned records include decoded bytes for bounded input-cost estimation.
    Persist only their hashes and sizes, never their encoded/raw content.
    """
    return _validated_attachments(attachments)


def production_models(provider: str) -> tuple[str, ...]:
    """Include explicit owner-local IDs without mutating native allowlists."""
    spec = PRODUCTION_PROVIDERS.get(provider)
    if spec is None:
        return ()
    from scripts.model_routing import local_model_overrides
    local = (model for route, model, family in local_model_overrides().values()
             if route == provider and family == spec["family"])
    return tuple(dict.fromkeys((*spec["models"], *local)))


def production_supported_efforts(provider: str, model: str) -> tuple[str, ...]:
    """Describe implemented native payloads, not relay quality or acceptance.

    Optional groups are transport candidates only. Catalog access, a known
    model ID and this effort allowlist cannot authorize spending or establish
    that a relay actually honors the requested effort.
    """
    spec = PRODUCTION_PROVIDERS.get(provider)
    if spec is None or model not in production_models(provider):
        raise ProviderError("model is not explicitly allowed on the selected production route")
    if spec["family"] == "openai" or (spec["family"] == "google" and model == "gemini-4-argon"):
        return ("low", "medium", "high")
    # A high-suffixed API ID cannot be combined with a conflicting lower
    # thinking level. Native base payload support does not establish acceptance.
    # Retain tested native high payloads for Claude and DeepSeek. Lower efforts
    # require a separate native protocol and relay acceptance before enablement.
    return ("high",)


def production_endpoint(provider: str, model: str | None = None) -> str:
    """Resolve one allowlisted native endpoint without aliasing model IDs."""
    spec = PRODUCTION_PROVIDERS.get(provider)
    if spec is None:
        raise ProviderError("provider is not a configured production route")
    selected = spec["model"] if model is None else model
    if not isinstance(selected, str) or selected not in production_models(provider):
        raise ProviderError("model is not explicitly allowed on the selected production route")
    return spec["root"] + spec["path"].format(model=selected)


def call_production(provider: str, prompt: str, *, model: str | None = None,
                    system: str | None = None, max_output_tokens: int = 8000,
                    timeout: int = 180, reasoning_effort: str | None = None,
                    attachments: Any = None, stream: bool = False) -> ModelResult:
    spec = PRODUCTION_PROVIDERS[provider]
    model = spec["model"] if model is None else model
    if type(stream) is not bool:
        raise ProviderError("stream must be an explicit boolean")
    if stream:
        from scripts.model_routing import g1_response_streaming_active
        if provider != "codekey-codex-pro" or model != "gpt-6-astra" or not g1_response_streaming_active():
            raise ProviderError("Responses streaming is restricted to the explicit Astra G1 validation sample")
    if model not in production_models(provider):
        raise ProviderError("model is not explicitly allowed on the selected production route")
    if not isinstance(prompt, str) or not prompt or (system is not None and not isinstance(system, str)):
        raise ProviderError("generation prompt and optional system must be text")
    if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or not 1 <= max_output_tokens <= 32768:
        raise ProviderError("max_output_tokens must be an integer from 1 to 32768")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 600:
        raise ProviderError("timeout must be an integer from 1 to 600 seconds")
    effort = ("medium" if model == "gpt-5.6-luna" else "high") if reasoning_effort is None else reasoning_effort
    family = spec["family"]
    supported_efforts = production_supported_efforts(provider, model)
    if not isinstance(effort, str) or effort not in supported_efforts:
        raise ProviderError("reasoning effort is not supported by this production route")
    media = _validated_attachments(attachments)
    native_google = spec["protocol"] == "gemini_generate_content"
    chat_protocol = spec["protocol"] in {"deepseek_chat_completions", "openai_chat_completions"}
    if media and family != "openai" and not native_google:
        raise ProviderError("attachments are not supported on this production route")
    key = os.environ.get(spec["key_setting"], "").strip()
    if not key or any(ch.isspace() or ord(ch) < 32 for ch in key):
        raise ProviderError(f"{spec['key_setting']} is not configured as a valid key")
    endpoint = production_endpoint(provider, model)
    headers = {"Authorization": f"Bearer {key}"}
    if family == "openai":
        user_parts: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for item in media:
            data_url = f"data:{item['mime_type']};base64,{item['data_base64']}"
            if item["mime_type"].startswith("image/"):
                user_parts.append({"type": "input_image", "image_url": data_url})
            elif item["mime_type"] == "application/pdf":
                user_parts.append({"type": "input_file", "filename": item["filename"], "file_data": data_url})
            else:
                user_parts.append({"type": "input_text", "text": item["decoded"].decode("utf-8")})
        messages = ([{"role": "developer", "content": system}] if system else [])
        messages.append({"role": "user", "content": user_parts})
        payload = {"model": model, "input": messages, "max_output_tokens": max_output_tokens,
                   "reasoning": {"effort": effort}, "store": False, "tools": [], "service_tier": "default"}
        if stream:
            payload["stream"] = True
    elif family == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        payload = {**_anthropic_payload(prompt, model, system, max_output_tokens),
                   "thinking": {"type": "adaptive"}, "output_config": {"effort": effort}, "tools": []}
    elif chat_protocol:
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": prompt})
        payload = {"model": model, "messages": messages, "max_tokens": max_output_tokens,
                   "reasoning_effort": effort}
        if family == "deepseek":
            payload["thinking"] = {"type": "enabled"}
        elif family == "moonshot":
            # K3.1 Pro is always-thinking; its documented cap includes reasoning
            # and answer tokens. Do not send an undocumented thinking toggle.
            payload["max_completion_tokens"] = payload.pop("max_tokens")
    elif native_google:
        headers = {"x-goog-api-key": key}
        parts = [{"text": prompt}] + [{"inlineData": {"mimeType": item["mime_type"], "data": item["data_base64"]}} for item in media]
        payload = {"contents": [{"role": "user", "parts": parts}],
                   "generationConfig": {"maxOutputTokens": max_output_tokens,
                                        "thinkingConfig": {"thinkingLevel": effort.upper()}}, "tools": []}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
    else:
        raise ProviderError("unsupported production transport protocol")
    data = None
    try:
        data = _production_request(endpoint, headers, payload, timeout)
        reported = _production_identity(model, data.get("modelVersion") if native_google else data.get("model"))
        if native_google:
            text, status = _google_text(data)
        else:
            protocol = "openai_chat_completions" if chat_protocol else spec["protocol"]
            if chat_protocol:
                choices = data.get("choices")
                if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                    raise ProviderError("chat response requires one choice; reconcile billing")
                message = choices[0].get("message")
                if not isinstance(message, dict) or message.get("tool_calls") or message.get("function_call"):
                    raise ProviderError("unexpected chat tool response; reconcile billing")
            text = (_anthropic_text(data) if family == "anthropic" else
                    _chat_completions_text(data) if chat_protocol else _openai_text(data))
            status = completion_status(data, protocol)
        if status != "completed":
            raise ProviderError("production model response did not complete; reconcile billing")
        result = ModelResult(provider, model, text, _production_usage(data, family, spec["protocol"]),
                           data.get("responseId") if native_google else data.get("id"),
                           reported, spec["protocol"], endpoint,
                           "cheapai" if provider.startswith("cheapai-") else "codekey",
                           completion_status=status, requested_effort=effort,
                           attachment_sha256=tuple(item["sha256"] for item in media))
        evidence = _response_evidence(data, headers=headers)
        result.response_metadata = {key: evidence[key] for key in (
            "diagnostics", "canonical_json_sha256", "canonical_json_hash_available", "http_evidence")}
        result.response_metadata.update(metadata_only=True, original_response_body_retained=False)
        return result
    except (ProviderError, TypeError, ValueError, KeyError, IndexError) as exc:
        error = exc if isinstance(exc, ProviderError) else ProviderError("malformed production model response; reconcile billing")
        if data is not None:
            error.response_evidence = _response_evidence(data, headers=headers)
            if hasattr(error, "reported_model"):
                diagnostic = error.response_evidence["diagnostics"]
                error.reported_model = diagnostic.get("modelVersion") if native_google else diagnostic.get("model")
        raise error from None


def configuration(provider: str, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Describe configuration without exposing credentials."""

    env = os.environ if environment is None else environment
    if provider in PRODUCTION_PROVIDERS:
        spec = PRODUCTION_PROVIDERS[provider]
        key = env.get(spec["key_setting"], "").strip()
        valid = bool(key) and not any(ch.isspace() or ord(ch) < 32 for ch in key)
        return {"provider": provider, "family": spec["family"], "root": spec["root"],
                "configured": valid, "model": spec["model"], "protocol": spec["protocol"],
                "endpoint": production_endpoint(provider),
                "key_setting": spec["key_setting"], "strict_model_id": True,
                "billing_identity": {"plan": "production", "group": provider, "mode": "standard"},
                "allowed_models": list(production_models(provider)),
                "allowed_reasoning_efforts": list(production_supported_efforts(provider, spec["model"])),
                "configuration_error": None if valid else f"{spec['key_setting']} is not configured as a valid key"}
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
    if provider in PRODUCTION_PROVIDERS:
        return call_production(provider, prompt, **kwargs)
    for name in ("reasoning_effort", "attachments"):
        if kwargs.get(name) is None:
            kwargs.pop(name, None)
        elif name in kwargs:
            raise ProviderError(f"{name} requires a configured production route")
    if provider == "openai":
        return call_openai(prompt, **kwargs)
    if provider == "anthropic":
        return call_anthropic(prompt, **kwargs)
    if provider == "uuapi-openai":
        return call_uuapi_openai(prompt, **kwargs)
    if provider == "uuapi-anthropic":
        return call_uuapi_anthropic(prompt, **kwargs)
    raise ProviderError(f"Unknown provider: {provider}")

