#!/usr/bin/env python3
"""Reviewed, credential-free public API subset of ToolUniverse 1.5.1."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import hashlib
import importlib
import os
import re
import sys
from importlib import metadata
from pathlib import Path
from typing import Any
from unittest.mock import patch


SDK_VERSION = "1.5.1"
TOOL_NAME = "UniProt_get_entry_by_accession"
ENDPOINT = "https://rest.uniprot.org/uniprotkb/{accession}.json"
SOURCE_SHA256 = "4b973f7fd3a3c5e7a6fc99c7661ea944cf2fa34b41474ae3ba605c912d695cb9"
CONFIG_SHA256 = "120f482e08674ea3f8680e861037fc400e4970649dd6fc7267f22a7c8e9f2a74"
ACCESSION = re.compile(r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})")


def validate_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"name", "arguments"}:
        raise ValueError("request must contain exactly name and arguments")
    if value["name"] != TOOL_NAME:
        raise ValueError("ToolUniverse tool is outside the reviewed public API allowlist; a metered cost adapter is required")
    arguments = value["arguments"]
    if not isinstance(arguments, dict) or set(arguments) not in ({"accession"}, {"accession", "compact"}):
        raise ValueError("UniProt arguments must contain accession and optionally compact=true")
    if not isinstance(arguments["accession"], str) or not ACCESSION.fullmatch(arguments["accession"]):
        raise ValueError("UniProt accession must be a canonical 6 or 10 character accession")
    if arguments.get("compact", True) is not True:
        raise ValueError("only compact=true is allowed for bounded UniProt output")
    return value


def public_api_policy(request: dict[str, Any]) -> dict[str, Any]:
    validate_request(request)
    return {
        "policy": "tooluniverse-uniprot-public-v1",
        "sdk_version": SDK_VERSION,
        "tool_type": "UniProtRESTTool",
        "implementation_sha256": SOURCE_SHA256,
        "configuration_sha256": CONFIG_SHA256,
        "method": "GET",
        "url": ENDPOINT.format(**request["arguments"]),
        "max_http_attempts": 1,
        "model_calls": 0,
        "model_api_cost_cny": 0,
        "public_api_cost_cny": 0,
        "cost_basis": "Unauthenticated public UniProt REST retrieval; no model or paid API is invoked. Hosting/network costs are excluded.",
        "access_documentation": "https://rest.uniprot.org/help/api_queries",
        "data_license": "CC BY 4.0",
        "license_source": "https://rest.uniprot.org/help/license",
        "attribution": "UniProt Consortium; https://www.uniprot.org/help/publications",
    }


def json_default(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value, key=str)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    raise TypeError(f"ToolUniverse returned a non-JSON value: {type(value).__name__}")


def read_request(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 16 * 1024:
        raise ValueError("ToolUniverse request exceeds 16 KiB")
    value = json.loads(path.read_text(encoding="utf-8"))
    return validate_request(value)


def execute(request: dict[str, Any], attempts: list[dict[str, Any]]) -> Any:
    policy = public_api_policy(request)
    distribution = metadata.distribution("tooluniverse")
    if distribution.version != SDK_VERSION:
        raise ValueError(f"reviewed ToolUniverse version {SDK_VERSION} is required")
    source = Path(distribution.locate_file("tooluniverse/uniprot_tool.py"))
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("ToolUniverse UniProt implementation differs from the reviewed source")
    config_bytes = Path(distribution.locate_file("tooluniverse/data/uniprot_tools.json")).read_bytes()
    if hashlib.sha256(config_bytes).hexdigest() != CONFIG_SHA256:
        raise ValueError("ToolUniverse UniProt metadata differs from the reviewed configuration")
    configs = json.loads(config_bytes)
    matches = [item for item in configs if item.get("name") == TOOL_NAME]
    if len(matches) != 1 or matches[0].get("type") != "UniProtRESTTool":
        raise ValueError("ToolUniverse public tool type differs from the reviewed implementation")
    config = matches[0]
    fields = config.get("fields", {})
    if fields.get("endpoint") != ENDPOINT or any(fields.get(key) for key in ("search_type", "mapping_type", "extract_path")):
        raise ValueError("ToolUniverse public tool endpoint/operation differs from the reviewed configuration")
    # Import only the audited concrete SDK class, without discovery, remote tools,
    # cache hooks, agents or model providers.
    os.environ["TOOLUNIVERSE_LIGHT_IMPORT"] = "true"
    uniprot_tool = importlib.import_module("tooluniverse.uniprot_tool")

    if Path(uniprot_tool.__file__).resolve() != source.resolve():
        raise ValueError("ToolUniverse import does not match the reviewed installed source")
    tool = uniprot_tool.UniProtRESTTool(config)
    resolved_fields = tool.tool_config.get("fields", {})
    if (type(tool).__module__ != "tooluniverse.uniprot_tool" or tool.endpoint != ENDPOINT or tool.extract_path
            or any(resolved_fields.get(key) for key in ("search_type", "mapping_type", "extract_path"))):
        raise ValueError("ToolUniverse resolved an unexpected implementation")
    request_get = uniprot_tool.requests.get

    def public_get(url: str, **kwargs: Any) -> Any:
        if attempts or url != policy["url"] or kwargs != {"timeout": 15}:
            raise ValueError("ToolUniverse attempted an unreviewed HTTP request")
        attempt = {"method": "GET", "url": url, "status": "started"}
        attempts.append(attempt)
        try:
            response = request_get(url, timeout=15, allow_redirects=False)
        except Exception:
            attempt["status"] = "failed"
            # Proxy URLs may contain credentials; keep transport exception text
            # out of the evidence logs while retaining the failed attempt.
            raise RuntimeError("UniProt public HTTPS transport failed") from None
        attempt.update(status="completed", http_status=response.status_code)
        return response

    with patch.object(uniprot_tool.requests, "get", public_get):
        result = tool.run({**request["arguments"], "compact": True})
    if not isinstance(result, dict) or result.get("status") == "error" or "error" in result:
        raise ValueError(f"UniProt retrieval failed: {result}")
    if not isinstance(result.get("data"), dict) or not result["data"].get("primaryAccession"):
        raise ValueError("UniProt returned no identifiable protein entry")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: tooluniverse_worker.py REQUEST.json", file=sys.stderr)
        return 2
    attempts: list[dict[str, Any]] = []
    try:
        request = read_request(Path(arguments[0]))
        # Keep library progress messages out of the machine-readable stdout.
        with contextlib.redirect_stdout(sys.stderr):
            result = execute(request, attempts)
        print(
            json.dumps(
                {"tool": request["name"], "result": result, "http_attempts": attempts},
                ensure_ascii=False,
                sort_keys=True,
                default=json_default,
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "http_attempts": attempts}, sort_keys=True))
        print(f"ToolUniverse execution failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
