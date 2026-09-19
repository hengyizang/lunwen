#!/usr/bin/env python3
"""Run auditable live acceptance checks for literature APIs and containers."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.literature_evidence import (
        PROVIDERS,
        LiteratureEvidenceError,
        execute_citation_graph,
        execute_search,
    )
except ImportError:
    from literature_evidence import (  # type: ignore
        PROVIDERS,
        LiteratureEvidenceError,
        execute_citation_graph,
        execute_search,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = (
    "python:3.10.21-slim-bookworm@"
    "sha256:54b4fc9408ea4f5d1b1b9c63c7ef1968d46d3b927e00df8ab1f09364593f979f"
)
IMAGE_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
DEFAULT_QUERY = "machine learning scientific research"
DEFAULT_DOI = "10.1038/s41586-021-03819-2"


class AcceptanceError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def kernel_text() -> str:
    values: list[str] = []
    for path in (Path("/proc/sys/kernel/osrelease"), Path("/proc/version")):
        try:
            values.append(path.read_text(encoding="utf-8", errors="replace").strip())
        except OSError:
            continue
    return " | ".join(values)


def environment_report() -> dict[str, Any]:
    kernel = kernel_text()
    lowered = kernel.lower()
    is_wsl = "microsoft" in lowered or bool(os.environ.get("WSL_INTEROP"))
    is_wsl2 = is_wsl and ("wsl2" in lowered or "microsoft-standard" in lowered)
    engines = [name for name in ("docker", "podman") if shutil.which(name)]
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "kernel": kernel,
        "is_wsl": is_wsl,
        "is_wsl2": is_wsl2,
        "container_engines": engines,
    }


def literature_acceptance(
    evidence_project: Path,
    providers: list[str],
    *,
    query: str,
    limit: int,
    include_opencitations: bool,
    citation_doi: str,
) -> dict[str, Any]:
    evidence_project.mkdir(parents=True, exist_ok=False)
    started_at = now()
    checks: list[dict[str, Any]] = []
    for provider in providers:
        started = time.monotonic()
        try:
            receipt = execute_search(
                evidence_project,
                provider,
                query,
                query_family="acceptance-smoke",
                date_range="all years",
                filters="public API acceptance; no human screening decision",
                limit=limit,
            )
        except (LiteratureEvidenceError, OSError, ValueError) as exc:
            checks.append(
                {
                    "provider": provider,
                    "status": "failed",
                    "runtime_seconds": round(time.monotonic() - started, 6),
                    "error": str(exc),
                }
            )
            continue
        passed = (
            receipt.get("status") == "success"
            and isinstance(receipt.get("http_status"), int)
            and 200 <= receipt["http_status"] < 300
            and receipt.get("result_count", 0) >= 1
        )
        checks.append(
            {
                "provider": provider,
                "status": "passed" if passed else "failed",
                "runtime_seconds": round(time.monotonic() - started, 6),
                "http_status": receipt.get("http_status"),
                "content_type": receipt.get("content_type"),
                "result_count": receipt.get("result_count"),
                "receipt_id": receipt.get("receipt_id"),
                "response_sha256": receipt.get("response_sha256"),
                "normalized_results_sha256": receipt.get(
                    "normalized_results_sha256"
                ),
                "raw_response_path": receipt.get("raw_response_path"),
                "normalized_results_path": receipt.get(
                    "normalized_results_path"
                ),
                "error": None if passed else "provider returned no normalized records",
            }
        )
    if include_opencitations:
        started = time.monotonic()
        try:
            receipt = execute_citation_graph(
                evidence_project,
                citation_doi,
                "citations",
                date_range="all years",
                filters="public API acceptance; DOI metadata is not treated as screened",
            )
        except (LiteratureEvidenceError, OSError, ValueError) as exc:
            checks.append(
                {
                    "provider": "opencitations",
                    "status": "failed",
                    "runtime_seconds": round(time.monotonic() - started, 6),
                    "error": str(exc),
                }
            )
        else:
            passed = (
                receipt.get("status") == "success"
                and isinstance(receipt.get("http_status"), int)
                and 200 <= receipt["http_status"] < 300
                and receipt.get("result_count", 0) >= 1
            )
            checks.append(
                {
                    "provider": "opencitations",
                    "status": "passed" if passed else "failed",
                    "runtime_seconds": round(time.monotonic() - started, 6),
                    "http_status": receipt.get("http_status"),
                    "content_type": receipt.get("content_type"),
                    "result_count": receipt.get("result_count"),
                    "receipt_id": receipt.get("receipt_id"),
                    "response_sha256": receipt.get("response_sha256"),
                    "normalized_results_sha256": receipt.get(
                        "normalized_results_sha256"
                    ),
                    "raw_response_path": receipt.get("raw_response_path"),
                    "normalized_results_path": receipt.get(
                        "normalized_results_path"
                    ),
                    "error": None if passed else "provider returned no citation edges",
                }
            )
    return {
        "status": "passed"
        if checks and all(item["status"] == "passed" for item in checks)
        else "failed",
        "started_at": started_at,
        "completed_at": now(),
        "query": query,
        "limit_per_provider": limit,
        "evidence_directory": str(evidence_project),
        "checks": checks,
    }


CONTAINER_PROBE = """
import json
import pathlib
import socket

root_read_only = False
try:
    pathlib.Path('/acceptance-root-write').write_text('unexpected')
except OSError:
    root_read_only = True

tmp_writable = False
try:
    marker = pathlib.Path('/tmp/acceptance-write')
    marker.write_text('ok')
    tmp_writable = marker.read_text() == 'ok'
except OSError:
    pass

network_blocked = False
sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect(('1.1.1.1', 443))
except OSError:
    network_blocked = True
finally:
    sock.close()

print(json.dumps({
    'root_read_only': root_read_only,
    'tmp_writable': tmp_writable,
    'network_blocked': network_blocked,
}))
raise SystemExit(0 if root_read_only and tmp_writable and network_blocked else 1)
""".strip()


def container_acceptance(
    image: str,
    *,
    engine: str | None = None,
    require_wsl2: bool,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    started_at = now()
    environment = environment_report()
    if require_wsl2 and not environment["is_wsl2"]:
        return {
            "status": "blocked",
            "started_at": started_at,
            "completed_at": now(),
            "error": "this check requires a real WSL2 kernel",
            "environment": environment,
        }
    if not IMAGE_RE.fullmatch(image):
        return {
            "status": "blocked",
            "started_at": started_at,
            "completed_at": now(),
            "error": "container image must be pinned as name@sha256:<64 hex>",
            "environment": environment,
        }
    selected = engine or next(iter(environment["container_engines"]), None)
    if selected not in {"docker", "podman"} or not shutil.which(selected):
        return {
            "status": "blocked",
            "started_at": started_at,
            "completed_at": now(),
            "error": "Docker or Podman is not available",
            "environment": environment,
        }
    command = [
        selected,
        "run",
        "--rm",
        "--pull=missing",
        "--network=none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=16m",
        "--cap-drop=ALL",
        "--security-opt",
        "no-new-privileges:true",
        image,
        "python",
        "-I",
        "-c",
        CONTAINER_PROBE,
    ]
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "failed",
            "started_at": started_at,
            "completed_at": now(),
            "engine": selected,
            "image": image,
            "argv": command[:-1] + ["<probe>"],
            "error": str(exc),
            "environment": environment,
        }
    probe: dict[str, Any] | None = None
    try:
        value = json.loads(result.stdout.strip().splitlines()[-1])
        if isinstance(value, dict):
            probe = value
    except (IndexError, json.JSONDecodeError):
        pass
    passed = result.returncode == 0 and probe == {
        "root_read_only": True,
        "tmp_writable": True,
        "network_blocked": True,
    }
    return {
        "status": "passed" if passed else "failed",
        "started_at": started_at,
        "completed_at": now(),
        "engine": selected,
        "image": image,
        "argv": command[:-1] + ["<probe>"],
        "exit_code": result.returncode,
        "probe": probe,
        "stdout": result.stdout[-16384:],
        "stderr": result.stderr[-16384:],
        "error": None if passed else "container isolation probe failed",
        "environment": environment,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    literature = sub.add_parser("literature")
    literature.add_argument("--provider", action="append", choices=PROVIDERS)
    literature.add_argument("--query", default=DEFAULT_QUERY)
    literature.add_argument("--limit", type=int, default=1)
    literature.add_argument("--skip-opencitations", action="store_true")
    literature.add_argument("--citation-doi", default=DEFAULT_DOI)
    literature.add_argument("--output", type=Path, required=True)

    container = sub.add_parser("container")
    container.add_argument("--image", default=DEFAULT_IMAGE)
    container.add_argument("--engine", choices=("docker", "podman"))
    container.add_argument("--require-wsl2", action="store_true")
    container.add_argument("--timeout", type=int, default=180)
    container.add_argument("--output", type=Path, required=True)

    wsl = sub.add_parser("wsl")
    wsl.add_argument("--provider", action="append", choices=PROVIDERS)
    wsl.add_argument("--query", default=DEFAULT_QUERY)
    wsl.add_argument("--limit", type=int, default=1)
    wsl.add_argument("--skip-opencitations", action="store_true")
    wsl.add_argument("--citation-doi", default=DEFAULT_DOI)
    wsl.add_argument("--image", default=DEFAULT_IMAGE)
    wsl.add_argument("--engine", choices=("docker", "podman"))
    wsl.add_argument("--timeout", type=int, default=180)
    wsl.add_argument("--output", type=Path, required=True)
    return root


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    output = args.output.resolve()
    acceptance_id = (
        f"{datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz')}-"
        f"{uuid.uuid4().hex[:10]}"
    )
    run_root = output.parent / f"{output.stem}-evidence" / acceptance_id
    common = {
        "schema_version": "1.0",
        "acceptance_id": acceptance_id,
        "command": args.command,
        "environment": environment_report(),
        "started_at": now(),
    }
    if args.command == "literature":
        literature = literature_acceptance(
            run_root / "literature-project",
            args.provider or list(PROVIDERS),
            query=args.query,
            limit=args.limit,
            include_opencitations=not args.skip_opencitations,
            citation_doi=args.citation_doi,
        )
        report = {**common, "literature": literature, "container": None}
        status = literature["status"]
    elif args.command == "container":
        container = container_acceptance(
            args.image,
            engine=args.engine,
            require_wsl2=args.require_wsl2,
            timeout_seconds=args.timeout,
        )
        report = {**common, "literature": None, "container": container}
        status = container["status"]
    else:
        literature = literature_acceptance(
            run_root / "literature-project",
            args.provider or list(PROVIDERS),
            query=args.query,
            limit=args.limit,
            include_opencitations=not args.skip_opencitations,
            citation_doi=args.citation_doi,
        )
        container = container_acceptance(
            args.image,
            engine=args.engine,
            require_wsl2=True,
            timeout_seconds=args.timeout,
        )
        statuses = {literature["status"], container["status"]}
        status = "blocked" if "blocked" in statuses else (
            "passed" if statuses == {"passed"} else "failed"
        )
        report = {**common, "literature": literature, "container": container}
    report["status"] = status
    report["completed_at"] = now()
    write_report(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"acceptance report: {output}", file=sys.stderr)
    return 0 if status == "passed" else (2 if status == "blocked" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
