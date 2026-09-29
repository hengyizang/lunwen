#!/usr/bin/env python3
"""One bounded OpenRouter Jev Router probe with a server-side zero-spend key.

This is a transport and billing check on a fixed, synthetic metadata example.
It is not a source selector, author, critic, or scientific gate.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable


BASE = "https://openrouter.ai/api/v1"
ROUTER = "typesafe/jev-router"
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
LABELS = {"prioritize", "ordinary_review", "uncertain"}
Transport = Callable[[str, str, dict | None, str], dict]


class ProbeError(RuntimeError):
    pass


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ProbeError(f"{label} was missing or invalid")
    return value


def _zero(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProbeError(f"{label} was not a finite numeric amount")
    if value != 0:
        raise ProbeError(f"{label} was nonzero; no further model request is allowed")
    return float(value)


def http_json(method: str, path: str, payload: dict | None, key: str) -> dict:
    """Use only the fixed OpenRouter API host; never include key or response in errors."""
    if not path.startswith("/") or path.startswith("//") or not re.fullmatch(r"/[A-Za-z0-9_/?=&.%-]+", path):
        raise ProbeError("invalid API path")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "X-OpenRouter-Metadata": "enabled", "User-Agent": "DoctoralResearchOS/2.3 free-jev-probe"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read(65537)
    except urllib.error.HTTPError as exc:
        raise ProbeError(f"OpenRouter returned HTTP {exc.code} for {method} {path.split('?')[0]}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProbeError(f"OpenRouter transport failed for {method} {path.split('?')[0]}") from None
    if len(raw) > 65536:
        raise ProbeError("API response exceeds 64 KiB")
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeError("API returned invalid JSON") from None
    if not isinstance(result, dict):
        raise ProbeError("API returned a non-object response")
    return result


def _key_status(transport: Transport, key: str) -> dict:
    data = transport("GET", "/key", None, key).get("data")
    if not isinstance(data, dict):
        raise ProbeError("API key status was unavailable")
    # A dedicated free-tier key must have a hard zero-credit cap, including BYOK.
    if data.get("is_free_tier") is not True or data.get("include_byok_in_limit") is not True:
        raise ProbeError("a dedicated free-tier key with BYOK included in its limit is required")
    _zero(data.get("limit"), "API key spending limit")
    _zero(data.get("limit_remaining"), "API key remaining spending limit")
    return data


def probe(key: str, transport: Transport = http_json) -> dict:
    if not key or len(key) < 8:
        raise ProbeError("OPENROUTER_API_KEY is not configured")
    before = _key_status(transport, key)
    request = {
        "model": ROUTER,
        "messages": [{"role": "user", "content": (
            "Public synthetic metadata for a transport check: Title: Cloud robotics dataset index. "
            "Description: A list of downloadable simulation benchmarks. "
            "Return exactly one label: prioritize, ordinary_review, or uncertain.")}],
        "max_tokens": 12,
        "stream": False,
        "provider": {"max_price": {"prompt": 0, "completion": 0, "request": 0, "image": 0}},
    }
    response = transport("POST", "/chat/completions", request, key)
    generation_id = _identifier(response.get("id"), "generation ID")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProbeError("chat response has no choice")
    message = choices[0].get("message")
    answer = message.get("content", "") if isinstance(message, dict) else ""
    if not isinstance(answer, str) or answer.strip().lower() not in LABELS:
        raise ProbeError("chat response did not contain one of the fixed triage labels")
    record = transport("GET", "/generation?" + urllib.parse.urlencode({"id": generation_id}), None, key).get("data")
    if not isinstance(record, dict):
        raise ProbeError("generation billing record is unavailable")
    _zero(record.get("total_cost"), "generation total cost")
    actual_model = _identifier(record.get("model"), "actual serving model")
    provider = _identifier(record.get("provider_name"), "actual provider")
    if actual_model == ROUTER or record.get("is_byok") is not False:
        raise ProbeError("actual model or non-BYOK provider identity is unverified")
    response_model = response.get("model")
    if response_model not in (ROUTER, actual_model):
        raise ProbeError("response and generation record model IDs disagree")
    after = _key_status(transport, key)
    if any(not isinstance(d.get("usage"), (int, float)) or isinstance(d["usage"], bool)
           or not math.isfinite(d["usage"]) for d in (before, after)):
        raise ProbeError("API key usage totals are unavailable")
    if after["usage"] > before["usage"]:
        raise ProbeError("API key usage increased despite the zero-cost generation record")
    return {"schema_version": "1.0", "status": "passed", "public_synthetic_input": True,
            "requested_model": ROUTER, "actual_model": actual_model, "provider": provider,
            "generation_id": generation_id, "total_cost_usd": 0, "triage_label": answer.strip().lower(),
            "note": "Transport/billing check only; label has no scientific evidentiary value."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = probe(os.environ.get("OPENROUTER_API_KEY", ""))
    except ProbeError as exc:
        print(f"free Jev probe: {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Free Jev probe passed: exact serving model and zero generation cost recorded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
