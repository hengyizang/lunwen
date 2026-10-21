"""Cloud-only, read-only diagnostics for the configured Gemini relay catalog.

No inference, pagination, redirect, spending grant, reservation, or project edit.
Only bounded model identifiers and controlled transport diagnostics are emitted.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from scripts import ai_providers
from scripts.production_readiness import NoRedirect


# Both roots are explicitly shown in the user's CodeKey API console. The US
# host is a diagnostic transport only and does not become a production route.
CATALOG_ROOTS = frozenset({"https://codekey.ai", "https://api.codekey.ai"})


def _model_id(value, *, native=False):
    if not isinstance(value, str):
        raise ValueError("malformed model ID")
    if native:
        if not value.startswith("models/"):
            raise ValueError("unexpected native model name")
        value = value[len("models/"):]
    if (not value or len(value) > 160 or "/" in value
            or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError("malformed model ID")
    return value


def _inspect(root, path, key, *, schema):
    if root not in CATALOG_ROOTS:
        raise ValueError("catalog diagnostic root is not explicitly allowed")
    allowed_path = {
        "openai-list": "/v1/models",
        "google-list": "/v1beta/models",
        "google-model": "/v1beta/models/" + _model_id(ai_providers.PRODUCTION_PROVIDERS["codekey-gemini"]["model"]),
    }.get(schema)
    if path != allowed_path or allowed_path is None:
        raise ValueError("catalog diagnostic path is not explicitly allowed")
    native = schema != "openai-list"
    header = {"x-goog-api-key": key} if native else {"Authorization": "Bearer " + key}
    request = urllib.request.Request(root + path, method="GET", headers={
        **header, "User-Agent": "lunwen-production-research/1.0", "Accept": "application/json"})
    result = {"root": root, "path": path, "method": "GET", "schema": schema,
              "http_status": None, "metadata_access_verified": False, "model_ids": []}
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            result["http_status"] = response.status
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("catalog size limit")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("success") is False or data.get("error"):
            raise ValueError("malformed catalog envelope")
        if schema == "openai-list":
            rows = data.get("data")
            field = "id"
        elif schema == "google-list":
            rows = data.get("models")
            field = "name"
            result["additional_pages_advertised"] = bool(data.get("nextPageToken"))
        else:
            rows, field = [data], "name"
        if not isinstance(rows, list) or len(rows) > 10_000:
            raise ValueError("malformed catalog rows")
        identifiers = {_model_id(row.get(field), native=native) for row in rows if isinstance(row, dict)}
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError("malformed catalog row")
        result.update(metadata_access_verified=True, model_ids=sorted(identifiers))
    except urllib.error.HTTPError as exc:
        result.update(http_status=exc.code, diagnostic="http_error")
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError):
        result["diagnostic"] = "catalog_unavailable_or_malformed"
    return result


def report(environment=None, *, include_us_host=False):
    env = os.environ if environment is None else environment
    if env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != "hengyizang/lunwen":
        raise ValueError("catalog diagnostic requires the repository cloud runner")
    spec = ai_providers.PRODUCTION_PROVIDERS["codekey-gemini"]
    if spec["root"] != "https://codekey.ai" or spec["family"] != "google":
        raise ValueError("unexpected configured Gemini relay")
    key = env.get(spec["key_setting"], "")
    if not isinstance(key, str) or not key.strip() or any(ch.isspace() or ord(ch) < 32 for ch in key.strip()):
        raise ValueError("Gemini diagnostic credential missing or invalid")
    model = _model_id(spec["model"])
    roots = [spec["root"]]
    if include_us_host:
        roots.append("https://api.codekey.ai")
    endpoints = []
    for root in roots:
        endpoints.extend([
            _inspect(root, "/v1/models", key.strip(), schema="openai-list"),
            _inspect(root, "/v1beta/models", key.strip(), schema="google-list"),
            _inspect(root, "/v1beta/models/" + model, key.strip(), schema="google-model"),
        ])
    return {"schema_version": "1.0", "provider": "codekey-gemini", "requested_model": model,
            "endpoints": endpoints, "model_generation_calls": 0, "new_spending_authority": False,
            "inference_access_verified": False, "scientific_completion": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-us-host", action="store_true",
                        help="also inspect the exact US API host shown in the CodeKey console; GET metadata only")
    args = parser.parse_args()
    try:
        value = report(include_us_host=args.include_us_host)
    except ValueError:
        value = {"diagnostic": "cloud_or_credential_precondition_failed", "model_generation_calls": 0}
        print(json.dumps(value))
        return 1
    serialized = json.dumps(value, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
