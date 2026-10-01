#!/usr/bin/env python3
"""Check the official Bocha Jev API, then optionally make one free-policy trial.

Only synthetic public metadata is sent. This is a transport check, not a
scientific decision or a replacement for a human research gate.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable


BASE = "https://jev.bocha.cn"
MODEL = "bocha-jev-v1"
LABELS = {"prioritize", "ordinary_review", "uncertain"}
Transport = Callable[[str, str, dict | None, str], tuple[int, dict]]


class ProbeError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        # Never forward an Authorization header to another host.
        return None


def http_json(method: str, path: str, payload: dict | None, key: str) -> tuple[int, dict]:
    """Fixed host and paths; never reflect credentials or response text in errors."""
    if (method, path) not in {("GET", "/v1/models"), ("POST", "/v1/systemone")}:
        raise ProbeError("unsupported Bocha request")
    headers = {"Accept": "application/json", "User-Agent": "DoctoralResearchOS/2.3 bocha-jev-probe"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            code, raw = response.status, response.read(65537)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raw = b""
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProbeError(f"Bocha transport failed for {method} {path}") from None
    if len(raw) > 65536:
        raise ProbeError("Bocha response exceeds 64 KiB")
    if code != 200:
        # Error bodies can contain request details and must not enter logs.
        return code, {}
    try:
        result = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeError("Bocha returned invalid JSON") from None
    if not isinstance(result, dict):
        raise ProbeError("Bocha returned a non-object response")
    return code, result


def connectivity(transport: Transport = http_json) -> dict:
    code, _ = transport("GET", "/v1/models", None, "")
    if code not in {200, 401, 403}:
        raise ProbeError(f"Bocha models endpoint returned unexpected HTTP {code}")
    return {"schema_version": "1.0", "provider": "bocha-official", "endpoint": BASE + "/v1/models",
            "http_status": code, "status": {200: "public_models", 401: "auth_required", 403: "access_forbidden"}[code],
            "model_call_made": False, "cost_cny": 0}


def trial(key: str, policy_checked_on: str, transport: Transport = http_json,
          today: dt.date | None = None, *, public_metadata: dict | None = None) -> dict:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    if policy_checked_on != today.isoformat():
        raise ProbeError("the official no-charge Jev policy must be checked again today")
    if not key or len(key) < 8:
        raise ProbeError("BOCHA_JEV_API_KEY is not configured")
    if public_metadata is not None and (set(public_metadata) != {"title", "description"}
            or any(not isinstance(v, str) or len(v) > 2000 for v in public_metadata.values())):
        raise ProbeError("public metadata must contain bounded title and description strings")
    code, models = transport("GET", "/v1/models", None, key)
    if code != 200:
        raise ProbeError(f"authenticated Bocha model query returned HTTP {code}")
    entries = models.get("models")
    if not isinstance(entries, list) or MODEL not in [item.get("name") for item in entries if isinstance(item, dict)]:
        raise ProbeError("the exact Bocha Jev model was absent from the authenticated model list")
    request = {"model": MODEL,
               "state": public_metadata or {"title": "Cloud simulation benchmark catalogue",
                         "description": "A public index of reproducible simulation datasets."},
               "questions": {"triage": {"type": "choice",
                                       "instructions": "Choose a provisional metadata review queue label; do not assert scientific merit.",
                                       "criteria": {
                                           "prioritize": "Review this public record earlier",
                                           "ordinary_review": "Review in the ordinary queue",
                                           "uncertain": "Insufficient metadata; flag for human review"}}}}
    code, result = transport("POST", "/v1/systemone", request, key)
    if code != 200:
        raise ProbeError(f"Bocha decision endpoint returned HTTP {code}")
    if result.get("model") != MODEL:
        raise ProbeError("actual serving model does not match bocha-jev-v1")
    answers = result.get("answers")
    answer = answers.get("triage") if isinstance(answers, dict) else None
    if not isinstance(answer, dict) or answer.get("type") != "choice" or answer.get("choice") not in LABELS:
        raise ProbeError("Bocha returned an invalid triage choice")
    usage = result.get("usage")
    if (not isinstance(usage, dict) or type(usage.get("input_tokens")) is not int
            or usage["input_tokens"] < 0 or usage.get("output_tokens") != 0):
        raise ProbeError("Bocha token usage is unavailable or inconsistent")
    probabilities = answer.get("probabilities")
    if (not isinstance(probabilities, dict) or set(probabilities) != LABELS
            or any(type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1
                   for value in probabilities.values())
            or abs(sum(probabilities.values()) - 1) > 0.02):
        raise ProbeError("Bocha candidate probabilities are invalid")
    return {"schema_version": "1.0", "provider": "bocha-official", "status": "passed",
            "requested_model": MODEL, "actual_model": result["model"],
            "public_synthetic_input": public_metadata is None, "model_call_made": True,
            "triage_label": answer["choice"], "input_tokens": usage["input_tokens"],
            "output_tokens": 0, "free_policy_checked_on": policy_checked_on,
            "billing_receipt_available": False,
            "note": "The official documentation says Jev currently does not charge; usage is not a billing receipt. This label has no scientific evidentiary value."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--free-policy-checked-on", default="")
    args = parser.parse_args()
    try:
        result = (trial(os.environ.get("BOCHA_JEV_API_KEY", ""), args.free_policy_checked_on)
                  if args.live else connectivity())
    except ProbeError as exc:
        print(f"Bocha Jev probe: {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Bocha Jev probe: {result['status']} (no credentials or response body logged).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
