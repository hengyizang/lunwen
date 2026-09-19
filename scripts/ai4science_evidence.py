#!/usr/bin/env python3
"""Execute and hash-bind reviewed optional AI4Science tools.

This adapter deliberately does not make an AI-generated answer authoritative.
It executes PaperQA2 and ToolUniverse without a shell, records every attempt,
and binds package versions plus exact local input/output files. Results remain
advisory until a human checks them against primary sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
PACKAGES = {
    "tooluniverse": "tooluniverse",
    "paperqa2": "paper-qa",
    "kdense-scientific-agent-skills": "scientific-agent-skills",
}
ADAPTER_VERSION = "1.0"
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 24 * 60 * 60
TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
SETTING_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
BASE_ENV_NAMES = {
    "PATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
}
SECRET_ENV_NAMES = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "AZURE_API_KEY",
    "NVIDIA_API_KEY",
    "HF_TOKEN",
    "HUGGINGFACE_API_KEY",
    "NCBI_API_KEY",
    "SEMANTIC_SCHOLAR_API_KEY",
    "CROSSREF_API_KEY",
    "FDA_API_KEY",
}


class AI4ScienceEvidenceError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_path(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", slug):
        raise AI4ScienceEvidenceError("invalid project slug")
    project = PROJECTS_ROOT / slug
    if not project.is_dir():
        raise AI4ScienceEvidenceError(f"project does not exist: {slug}")
    return project


def safe_file(project: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise AI4ScienceEvidenceError("files must be project-relative and cannot contain ..")
    path = (project / relative).resolve()
    if project.resolve() not in path.parents or not path.is_file() or path.is_symlink():
        raise AI4ScienceEvidenceError(f"not a regular project file: {value}")
    return path


def file_record(project: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(project).as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def safe_directory(project: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise AI4ScienceEvidenceError(
            "directories must be project-relative and cannot contain .."
        )
    path = (project / relative).resolve()
    if project.resolve() not in path.parents or not path.is_dir() or path.is_symlink():
        raise AI4ScienceEvidenceError(f"not a regular project directory: {value}")
    return path


def directory_records(project: Path, directory: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise AI4ScienceEvidenceError(
                f"AI4Science inputs cannot contain symlinks: {path.relative_to(project)}"
            )
        if path.is_file() and (path.name == ".env" or path.name.startswith(".env.")):
            raise AI4ScienceEvidenceError(
                "PaperQA2 corpus directories cannot contain environment credential files"
            )
        if path.is_file():
            records.append(file_record(project, path))
    if not records:
        raise AI4ScienceEvidenceError("the PaperQA2 corpus directory contains no files")
    return records


def package_version(tool: str) -> tuple[str, str]:
    if tool not in PACKAGES:
        raise AI4ScienceEvidenceError("unsupported tool")
    package = PACKAGES[tool]
    try:
        return package, metadata.version(package)
    except metadata.PackageNotFoundError as exc:
        raise AI4ScienceEvidenceError(
            f"{package} is not installed in this environment; no execution was started"
        ) from exc


def safe_environment(project: Path, tool: str) -> tuple[dict[str, str], list[str]]:
    cache_root = project / ".cache" / "ai4science"
    home = cache_root / "home"
    home.mkdir(parents=True, exist_ok=True)
    environment = {
        name: value for name, value in os.environ.items() if name in BASE_ENV_NAMES
    }
    present_secrets = sorted(name for name in SECRET_ENV_NAMES if os.environ.get(name))
    for name in present_secrets:
        environment[name] = os.environ[name]
    environment.update(
        {
            "HOME": str(home),
            "XDG_CACHE_HOME": str(cache_root / "xdg"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
    )
    if tool == "paperqa2":
        pqa_home = cache_root / "paperqa"
        pqa_home.mkdir(parents=True, exist_ok=True)
        environment["PQA_HOME"] = str(pqa_home)
    return environment, present_secrets


def _read_capped(path: Path, max_bytes: int) -> tuple[bytes, bool, str]:
    digest = hashlib.sha256()
    captured = bytearray()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            if len(captured) < max_bytes:
                captured.extend(chunk[: max_bytes - len(captured)])
    return bytes(captured), path.stat().st_size > max_bytes, digest.hexdigest()


def run_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    max_capture_bytes: int = MAX_CAPTURE_BYTES,
) -> dict[str, Any]:
    if not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise AI4ScienceEvidenceError(
            f"timeout must be between 1 and {MAX_TIMEOUT_SECONDS} seconds"
        )
    started_at = now()
    monotonic_start = time.monotonic()
    exit_code: int | None = None
    timed_out = False
    error: str | None = None
    with tempfile.NamedTemporaryFile("w+b") as stdout, tempfile.NamedTemporaryFile(
        "w+b"
    ) as stderr:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                start_new_session=os.name != "nt",
            )
            try:
                exit_code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                error = str(exc)
                if os.name != "nt":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except OSError:
                        process.kill()
                else:
                    process.kill()
                process.wait()
        except OSError as exc:
            error = str(exc)
        stdout.flush()
        stderr.flush()
        stdout_bytes, stdout_truncated, stdout_full_sha256 = _read_capped(
            Path(stdout.name), max_capture_bytes
        )
        stderr_bytes, stderr_truncated, stderr_full_sha256 = _read_capped(
            Path(stderr.name), max_capture_bytes
        )
    if timed_out:
        status = "timed_out"
    elif exit_code == 0 and error is None:
        status = "succeeded"
    else:
        status = "failed"
    return {
        "started_at": started_at,
        "completed_at": now(),
        "runtime_seconds": round(time.monotonic() - monotonic_start, 6),
        "status": status,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "error": error,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "stdout_full_sha256": stdout_full_sha256,
        "stderr_full_sha256": stderr_full_sha256,
    }


def _receipt_id(tool: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    return f"{timestamp}-{tool}-{uuid.uuid4().hex[:10]}"


def _unchanged_inputs(project: Path, records: list[dict[str, Any]]) -> list[str]:
    changed: list[str] = []
    for item in records:
        try:
            path = safe_file(project, str(item["path"]))
        except (AI4ScienceEvidenceError, KeyError):
            changed.append(str(item.get("path", "<missing>")))
            continue
        if sha256_file(path) != item.get("sha256") or path.stat().st_size != item.get(
            "bytes"
        ):
            changed.append(str(item["path"]))
    return changed


def _finish_execution(
    *,
    project: Path,
    tool: str,
    package: str,
    version: str,
    actor: str,
    purpose: str,
    inputs: list[dict[str, Any]],
    public_argv: list[str],
    cwd: Path,
    timeout_seconds: int,
    environment: dict[str, str],
    secret_names: list[str],
    result: dict[str, Any],
    receipt_id: str,
    output_name: str,
    parse_json_output: bool,
) -> dict[str, Any]:
    run_dir = project / "evidence" / "ai4science" / receipt_id
    run_dir.mkdir(parents=True, exist_ok=False)
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    stdout_path.write_bytes(result["stdout_bytes"])
    stderr_path.write_bytes(result["stderr_bytes"])
    changed_inputs = _unchanged_inputs(project, inputs)
    status = result["status"]
    error = result["error"]
    if result["stdout_truncated"] or result["stderr_truncated"]:
        status = "failed"
        error = "captured output exceeded the 8 MiB safety limit"
    if changed_inputs:
        status = "failed"
        error = "AI4Science input files changed during execution"
    output_record: dict[str, Any] | None = None
    if status == "succeeded":
        output_path = run_dir / output_name
        if parse_json_output:
            try:
                parsed = json.loads(result["stdout_bytes"].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                status = "failed"
                error = f"ToolUniverse adapter did not return valid JSON: {exc}"
            else:
                output_path.write_text(
                    json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                output_record = file_record(project, output_path)
        else:
            if not result["stdout_bytes"].strip():
                status = "failed"
                error = "PaperQA2 returned an empty answer"
            else:
                output_path.write_bytes(result["stdout_bytes"])
                output_record = file_record(project, output_path)
    receipt = {
        "schema_version": "1.1",
        "receipt_id": receipt_id,
        "tool": tool,
        "package": package,
        "package_version": version,
        "recorded_at": now(),
        "recorded_by": actor.strip(),
        "purpose": purpose.strip(),
        "status": status,
        "output": output_record,
        "inputs": inputs,
        "execution": {
            "adapter_version": ADAPTER_VERSION,
            "started_at": result["started_at"],
            "completed_at": result["completed_at"],
            "runtime_seconds": result["runtime_seconds"],
            "subprocess_status": result["status"],
            "argv": public_argv,
            "cwd": cwd.relative_to(project).as_posix(),
            "timeout_seconds": timeout_seconds,
            "timed_out": result["timed_out"],
            "exit_code": result["exit_code"],
            "error": error,
            "environment_names": sorted(environment),
            "secret_environment_names": secret_names,
            "stdout": file_record(project, stdout_path),
            "stderr": file_record(project, stderr_path),
            "stdout_truncated": result["stdout_truncated"],
            "stderr_truncated": result["stderr_truncated"],
            "stdout_full_sha256": result["stdout_full_sha256"],
            "stderr_full_sha256": result["stderr_full_sha256"],
            "input_integrity": {
                "verified_after_run": True,
                "passed": not changed_inputs,
                "changed_or_missing": changed_inputs,
            },
        },
        "advisory_only": True,
        "human_verification_required": True,
    }
    append(project / "evidence" / "ai4science-ledger.jsonl", receipt)
    if status != "succeeded":
        raise AI4ScienceEvidenceError(
            f"{tool} execution {status}; receipt preserved as {receipt_id}: "
            f"{error or 'non-zero exit status'}"
        )
    return receipt


def execute_paperqa(
    project: Path,
    corpus: str,
    question: str,
    actor: str,
    purpose: str,
    *,
    settings: str = "fast",
    timeout_seconds: int = 1800,
    executable: str | None = None,
) -> dict[str, Any]:
    if not actor.strip() or not purpose.strip() or not question.strip():
        raise AI4ScienceEvidenceError("actor, purpose and question are required")
    if not SETTING_RE.fullmatch(settings):
        raise AI4ScienceEvidenceError("PaperQA2 settings name is invalid")
    package, version = package_version("paperqa2")
    corpus_path = safe_directory(project, corpus)
    inputs = directory_records(project, corpus_path)
    if executable is None:
        sibling = Path(sys.executable).with_name("pqa")
        executable = str(sibling) if sibling.is_file() else shutil.which("pqa")
    if not executable:
        raise AI4ScienceEvidenceError(
            "paper-qa is installed but the pqa executable is unavailable"
        )
    environment, secret_names = safe_environment(project, "paperqa2")
    command = [executable, "-s", settings, "ask", question.strip()]
    receipt_id = _receipt_id("paperqa2")
    result = run_process(
        command,
        cwd=corpus_path,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
    return _finish_execution(
        project=project,
        tool="paperqa2",
        package=package,
        version=version,
        actor=actor,
        purpose=purpose,
        inputs=inputs,
        public_argv=["pqa", "-s", settings, "ask", question.strip()],
        cwd=corpus_path,
        timeout_seconds=timeout_seconds,
        environment=environment,
        secret_names=secret_names,
        result=result,
        receipt_id=receipt_id,
        output_name="answer.txt",
        parse_json_output=False,
    )


def execute_tooluniverse(
    project: Path,
    request_file: str,
    actor: str,
    purpose: str,
    *,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    if not actor.strip() or not purpose.strip():
        raise AI4ScienceEvidenceError("actor and purpose are required")
    package, version = package_version("tooluniverse")
    request_path = safe_file(project, request_file)
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AI4ScienceEvidenceError(f"invalid ToolUniverse request JSON: {exc}") from exc
    if not isinstance(request, dict) or set(request) != {"name", "arguments"}:
        raise AI4ScienceEvidenceError(
            "ToolUniverse request must contain exactly name and arguments"
        )
    if not isinstance(request.get("name"), str) or not TOOL_NAME_RE.fullmatch(
        request["name"]
    ):
        raise AI4ScienceEvidenceError("ToolUniverse tool name is invalid")
    if not isinstance(request.get("arguments"), dict):
        raise AI4ScienceEvidenceError("ToolUniverse arguments must be an object")
    environment, secret_names = safe_environment(project, "tooluniverse")
    worker = ROOT / "scripts" / "tooluniverse_worker.py"
    command = [sys.executable, str(worker), str(request_path)]
    execution_cwd = project / ".cache" / "ai4science" / "tooluniverse"
    execution_cwd.mkdir(parents=True, exist_ok=True)
    receipt_id = _receipt_id("tooluniverse")
    result = run_process(
        command,
        cwd=execution_cwd,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
    return _finish_execution(
        project=project,
        tool="tooluniverse",
        package=package,
        version=version,
        actor=actor,
        purpose=purpose,
        inputs=[file_record(project, request_path)],
        public_argv=[
            "python",
            "scripts/tooluniverse_worker.py",
            request_path.relative_to(project).as_posix(),
        ],
        cwd=execution_cwd,
        timeout_seconds=timeout_seconds,
        environment=environment,
        secret_names=secret_names,
        result=result,
        receipt_id=receipt_id,
        output_name="result.json",
        parse_json_output=True,
    )


def append(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def record(
    project: Path,
    tool: str,
    output: str,
    inputs: list[str],
    actor: str,
    purpose: str,
) -> dict[str, Any]:
    if tool not in PACKAGES:
        raise AI4ScienceEvidenceError("unsupported tool")
    if not actor.strip() or not purpose.strip():
        raise AI4ScienceEvidenceError("actor and purpose are required")
    package, version = package_version(tool)
    output_path = safe_file(project, output)
    input_paths = [safe_file(project, value) for value in inputs]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    receipt = {
        "schema_version": "1.0",
        "receipt_id": f"{timestamp}-{tool}-{uuid.uuid4().hex[:10]}",
        "tool": tool,
        "package": package,
        "package_version": version,
        "recorded_at": now(),
        "recorded_by": actor.strip(),
        "purpose": purpose.strip(),
        "output": file_record(project, output_path),
        "inputs": [file_record(project, path) for path in input_paths],
        "advisory_only": True,
        "human_verification_required": True,
    }
    append(project / "evidence" / "ai4science-ledger.jsonl", receipt)
    return receipt


def read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    result: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AI4ScienceEvidenceError(f"invalid ledger JSON at line {number}: {exc}") from exc
        if not isinstance(value, dict):
            raise AI4ScienceEvidenceError(f"ledger line {number} is not an object")
        result.append(value)
    return result


def validate(project: Path, values: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        prefix = f"ai4science-ledger[{index}]"
        receipt_id = item.get("receipt_id")
        if not isinstance(receipt_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]+", receipt_id):
            errors.append(f"{prefix}.receipt_id is invalid")
        elif receipt_id in seen:
            errors.append(f"{prefix}.receipt_id is duplicated")
        else:
            seen.add(receipt_id)
        tool = item.get("tool")
        if tool not in PACKAGES or item.get("package") != PACKAGES.get(tool):
            errors.append(f"{prefix} tool/package is unsupported")
        if item.get("advisory_only") is not True or item.get("human_verification_required") is not True:
            errors.append(f"{prefix} must remain advisory and require human verification")
        schema_version = item.get("schema_version")
        if schema_version not in {"1.0", "1.1"}:
            errors.append(f"{prefix}.schema_version is unsupported")
        status = item.get("status") if schema_version == "1.1" else "succeeded"
        if status not in {"succeeded", "failed", "timed_out"}:
            errors.append(f"{prefix}.status is invalid")
        output = item.get("output")
        if status == "succeeded" and not isinstance(output, dict):
            errors.append(f"{prefix}.output is required after successful execution")
        file_groups: list[tuple[str, Any]] = [("inputs", item.get("inputs"))]
        if isinstance(output, dict):
            file_groups.append(("output", [output]))
        if schema_version == "1.1":
            execution = item.get("execution")
            if not isinstance(execution, dict):
                errors.append(f"{prefix}.execution is required")
            else:
                for label in ("stdout", "stderr"):
                    value = execution.get(label)
                    file_groups.append((f"execution.{label}", [value]))
                integrity = execution.get("input_integrity")
                if not isinstance(integrity, dict):
                    errors.append(f"{prefix}.execution.input_integrity is invalid")
                elif integrity.get("passed") is not True and status == "succeeded":
                    errors.append(f"{prefix} succeeded despite failed input integrity")
                secret_names = execution.get("secret_environment_names")
                if not isinstance(secret_names, list) or any(
                    value not in SECRET_ENV_NAMES for value in secret_names
                ):
                    errors.append(f"{prefix}.execution.secret_environment_names is invalid")
                environment_names = execution.get("environment_names")
                if not isinstance(environment_names, list) or (
                    isinstance(secret_names, list)
                    and not set(secret_names).issubset(set(environment_names))
                ):
                    errors.append(f"{prefix}.execution.environment_names is invalid")
                if status == "succeeded" and (
                    execution.get("subprocess_status") != "succeeded"
                    or execution.get("exit_code") != 0
                    or execution.get("timed_out") is not False
                    or execution.get("stdout_truncated") is not False
                    or execution.get("stderr_truncated") is not False
                ):
                    errors.append(f"{prefix} has inconsistent successful execution state")
                for stream in ("stdout", "stderr"):
                    record_value = execution.get(stream)
                    if (
                        isinstance(record_value, dict)
                        and execution.get(f"{stream}_truncated") is False
                        and execution.get(f"{stream}_full_sha256")
                        != record_value.get("sha256")
                    ):
                        errors.append(f"{prefix}.execution.{stream} full hash is inconsistent")
        for label, records in file_groups:
            if not isinstance(records, list):
                errors.append(f"{prefix}.{label} must contain file evidence")
                continue
            for file_index, file_value in enumerate(records):
                if not isinstance(file_value, dict):
                    errors.append(f"{prefix}.{label}[{file_index}] is invalid")
                    continue
                try:
                    path = safe_file(project, str(file_value.get("path")))
                except AI4ScienceEvidenceError as exc:
                    errors.append(f"{prefix}.{label}[{file_index}]: {exc}")
                    continue
                if file_value.get("sha256") != sha256_file(path) or file_value.get("bytes") != path.stat().st_size:
                    errors.append(f"{prefix}.{label}[{file_index}] is stale")
    return errors


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    item = sub.add_parser("record")
    item.add_argument("--project", required=True)
    item.add_argument("--tool", required=True, choices=sorted(PACKAGES))
    item.add_argument("--output", required=True)
    item.add_argument("--input", action="append", default=[])
    item.add_argument("--actor", required=True)
    item.add_argument("--purpose", required=True)
    paperqa = sub.add_parser("paperqa")
    paperqa.add_argument("--project", required=True)
    paperqa.add_argument("--corpus", required=True)
    paperqa.add_argument("--question", required=True)
    paperqa.add_argument("--settings", default="fast")
    paperqa.add_argument("--actor", required=True)
    paperqa.add_argument("--purpose", required=True)
    paperqa.add_argument("--timeout", type=int, default=1800)
    tooluniverse = sub.add_parser("tooluniverse")
    tooluniverse.add_argument("--project", required=True)
    tooluniverse.add_argument("--request", required=True)
    tooluniverse.add_argument("--actor", required=True)
    tooluniverse.add_argument("--purpose", required=True)
    tooluniverse.add_argument("--timeout", type=int, default=600)
    check = sub.add_parser("validate")
    check.add_argument("--project", required=True)
    return root


def main(argv: Iterable[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        project = project_path(args.project)
        if args.command == "record":
            print(json.dumps(record(project, args.tool, args.output, args.input, args.actor, args.purpose), indent=2))
        elif args.command == "paperqa":
            print(
                json.dumps(
                    execute_paperqa(
                        project,
                        args.corpus,
                        args.question,
                        args.actor,
                        args.purpose,
                        settings=args.settings,
                        timeout_seconds=args.timeout,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "tooluniverse":
            print(
                json.dumps(
                    execute_tooluniverse(
                        project,
                        args.request,
                        args.actor,
                        args.purpose,
                        timeout_seconds=args.timeout,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            errors = validate(project, read_ledger(project / "evidence" / "ai4science-ledger.jsonl"))
            print(json.dumps({"status": "pass" if not errors else "block", "errors": errors}, indent=2))
            if errors:
                raise AI4ScienceEvidenceError(f"{len(errors)} invalid receipt(s)")
        return 0
    except AI4ScienceEvidenceError as exc:
        print(f"error: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
