#!/usr/bin/env python3
"""Small dependency-free API adapters for the Doctoral Research OS.

The adapters deliberately return model text plus usage metadata. They never
execute model-produced commands. Tool use and local execution remain under the
existing human-gated Python control plane.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class ProviderError(RuntimeError):
    pass


@dataclass
class ModelResult:
    provider: str
    model: str
    text: str
    usage: dict[str, Any]
    request_id: str | None = None


def _request(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={**headers, "Content-Type": "application/json"}, method="POST")
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ProviderError(f"API HTTP {exc.code}: {detail[:1000]}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ProviderError(f"API request failed: {exc}") from exc
    raise ProviderError(f"API request failed: {last}")


def call_openai(prompt: str, *, model: str | None = None, system: str | None = None,
                max_output_tokens: int = 8000, timeout: int = 180) -> ModelResult:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ProviderError("OPENAI_API_KEY is not configured")
    model = model or os.environ.get("OPENAI_MODEL", "gpt-5.6")
    content = prompt if not system else [{"role": "developer", "content": system}, {"role": "user", "content": prompt}]
    payload = {"model": model, "input": content, "max_output_tokens": max_output_tokens}
    data = _request(os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/responses"),
                    {"Authorization": f"Bearer {key}"}, payload, timeout)
    text = data.get("output_text")
    if not isinstance(text, str):
        chunks: list[str] = []
        for item in data.get("output", []):
            for part in item.get("content", []) if isinstance(item, dict) else []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        text = "\n".join(chunks)
    if not text:
        raise ProviderError("OpenAI response contained no text")
    return ModelResult("openai", model, text, data.get("usage", {}) or {}, data.get("id"))


def call_anthropic(prompt: str, *, model: str | None = None, system: str | None = None,
                   max_tokens: int = 8000, timeout: int = 180) -> ModelResult:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ProviderError("ANTHROPIC_API_KEY is not configured")
    model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    data = _request(os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1/messages"),
                    {"x-api-key": key, "anthropic-version": os.environ.get("ANTHROPIC_VERSION", "2023-06-01")}, payload, timeout)
    parts = [p.get("text", "") for p in data.get("content", []) if isinstance(p, dict) and p.get("type") == "text"]
    text = "\n".join(p for p in parts if p)
    if not text:
        raise ProviderError("Anthropic response contained no text")
    return ModelResult("anthropic", model, text, data.get("usage", {}) or {}, data.get("id"))


def call(provider: str, prompt: str, **kwargs: Any) -> ModelResult:
    if provider == "openai":
        return call_openai(prompt, **kwargs)
    if provider == "anthropic":
        return call_anthropic(prompt, **kwargs)
    raise ProviderError(f"Unknown provider: {provider}")
