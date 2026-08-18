#!/usr/bin/env python3
"""Dependency-free model adapters for the Doctoral Research OS.

The adapters return model text and auditable request metadata. They never
execute model-produced commands; local execution remains under the human-gated
Python control plane.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
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
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
                if not isinstance(value, dict):
                    raise ProviderError("API response was not a JSON object")
                return value
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2**attempt)
                continue
            raise ProviderError(f"API HTTP {exc.code}: {detail[:1000]}") from exc
        except ProviderError:
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < 2:
                time.sleep(2**attempt)
                continue
            raise ProviderError(f"API request failed: {exc}") from exc
    raise ProviderError(f"API request failed: {last}")


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


def _validated_https_root(raw: str) -> str:
    parsed = urlsplit(raw.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ProviderError("UUAPI_BASE_URL must be a valid HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderError(
            "UUAPI_BASE_URL must not contain credentials, query or fragment"
        )
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))


def _uuapi_root() -> str:
    value = os.environ.get("UUAPI_BASE_URL")
    if not value:
        raise ProviderError(
            "UUAPI_BASE_URL is not configured; copy the exact HTTPS root from "
            "your UUAPI dashboard"
        )
    return _validated_https_root(value)


def _uuapi_endpoint(path: str) -> str:
    return f"{_uuapi_root()}/v1/{path.lstrip('/')}"


def _uuapi_key() -> str:
    key = os.environ.get("UUAPI_API_KEY")
    if not key:
        raise ProviderError("UUAPI_API_KEY is not configured")
    return key


def _uuapi_headers(protocol: str) -> dict[str, str]:
    key = _uuapi_key()
    if protocol == "anthropic_messages":
        return {
            "Authorization": f"Bearer {key}",
            "x-api-key": key,
            "anthropic-version": os.environ.get(
                "UUAPI_ANTHROPIC_VERSION", "2023-06-01"
            ),
            "User-Agent": os.environ.get(
                "UUAPI_ANTHROPIC_USER_AGENT", UUAPI_ANTHROPIC_UA
            ),
        }
    return {
        "Authorization": f"Bearer {key}",
        "User-Agent": os.environ.get("UUAPI_OPENAI_USER_AGENT", UUAPI_OPENAI_UA),
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
    )


def call_uuapi_openai(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_output_tokens: int = 8000,
    timeout: int = 180,
) -> ModelResult:
    model = model or os.environ.get("UUAPI_OPENAI_MODEL")
    if not model:
        raise ProviderError("UUAPI_OPENAI_MODEL is not configured")
    content: Any = prompt
    if system:
        content = [
            {"role": "developer", "content": system},
            {"role": "user", "content": prompt},
        ]
    endpoint = _uuapi_endpoint("responses")
    data = _request(
        endpoint,
        _uuapi_headers("openai_responses"),
        {
            "model": model,
            "input": content,
            "max_output_tokens": max_output_tokens,
            "store": False,
        },
        timeout,
    )
    reported = _reported_model(data)
    _strict_model_check(model, reported)
    return ModelResult(
        "uuapi-openai",
        model,
        _openai_text(data),
        data.get("usage", {}) or {},
        data.get("id"),
        reported,
        "openai_responses",
        endpoint,
        "uuapi",
    )


def call_uuapi_anthropic(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    max_output_tokens: int = 8000,
    timeout: int = 180,
) -> ModelResult:
    model = model or os.environ.get("UUAPI_ANTHROPIC_MODEL")
    if not model:
        raise ProviderError("UUAPI_ANTHROPIC_MODEL is not configured")
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_output_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    endpoint = _uuapi_endpoint("messages")
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


def configuration(provider: str) -> dict[str, Any]:
    """Describe configuration without exposing credentials."""

    if provider == "openai":
        return {
            "provider": provider,
            "configured": bool(os.environ.get("OPENAI_API_KEY")),
            "model": os.environ.get("OPENAI_MODEL", "gpt-5.6"),
            "protocol": "openai_responses",
            "endpoint": _safe_endpoint_for_audit(
                os.environ.get(
                    "OPENAI_BASE_URL", "https://api.openai.com/v1/responses"
                )
            ),
        }
    if provider == "anthropic":
        return {
            "provider": provider,
            "configured": bool(
                os.environ.get("ANTHROPIC_API_KEY")
                and os.environ.get("ANTHROPIC_MODEL")
            ),
            "model": os.environ.get("ANTHROPIC_MODEL"),
            "protocol": "anthropic_messages",
            "endpoint": _safe_endpoint_for_audit(
                os.environ.get(
                    "ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1/messages"
                )
            ),
        }
    if provider in {"uuapi-openai", "uuapi-anthropic"}:
        model_key = (
            "UUAPI_OPENAI_MODEL"
            if provider == "uuapi-openai"
            else "UUAPI_ANTHROPIC_MODEL"
        )
        path = "responses" if provider == "uuapi-openai" else "messages"
        endpoint: str | None = None
        endpoint_error: str | None = None
        try:
            endpoint = _uuapi_endpoint(path)
        except ProviderError as exc:
            endpoint_error = str(exc)
        return {
            "provider": provider,
            "configured": bool(
                os.environ.get("UUAPI_API_KEY")
                and os.environ.get("UUAPI_BASE_URL")
                and os.environ.get(model_key)
                and not endpoint_error
            ),
            "model": os.environ.get(model_key),
            "protocol": (
                "openai_responses"
                if provider == "uuapi-openai"
                else "anthropic_messages"
            ),
            "endpoint": endpoint,
            "configuration_error": endpoint_error,
            "strict_model_id": os.environ.get(
                "UUAPI_STRICT_MODEL_ID", "true"
            ).lower()
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
