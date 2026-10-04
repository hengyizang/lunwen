"""Bounded retries of explicitly idempotent cloud infrastructure operations.

Never use this wrapper for model calls, experiment execution, or whole jobs.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ATTEMPTS = 3
DELAYS = (2, 8)
TRANSIENT = re.compile(
    r"connection (?:reset|aborted)|could not resolve host|temporary failure in name resolution|"
    r"remote end hung up|unexpected disconnect|TLS connection was non-properly terminated|"
    r"failed to connect|connection timed out|read timed out|readtimeout|connecttimeout|"
    r"HTTP (?:error )?(?:502|503|504)|error: (?:502|503|504)|service unavailable|"
    r"network is unreachable", re.I)
PERMANENT = re.compile(
    r"non-fast-forward|fetch first|permission denied|authentication failed|repository not found|"
    r"no matching distribution|could not find a version|resolutionimpossible|"
    r"hashes? (?:do not|don't|does not) match|invalid requirement|401|403", re.I)


def redact(text: str) -> str:
    for name, value in os.environ.items():
        if len(value) >= 8 and any(x in name.upper() for x in ("KEY", "TOKEN", "SECRET", "PASSWORD", "EMAIL")):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"https?://[^\s/@]+:[^\s/@]+@", "https://[REDACTED]@", text)
    return text


def transient(text: str) -> bool:
    return bool(TRANSIENT.search(text)) and not PERMANENT.search(text)


def run(command: list[str], *, operation: str, cwd: Path,
        receipt: Path, timeout: int = 240) -> subprocess.CompletedProcess:
    """Retry only Git transport or the exact declared dependency installation."""
    git_operation = operation in {"git-ls-remote", "git-fetch", "git-push"}
    install = [__import__("sys").executable, "-m", "pip", "install", "--disable-pip-version-check",
               ".[figures,reader,research-quality,reference-tools]"]
    if not ((git_operation and command[:2] == ["git", operation[4:]]
             and not any(x.startswith("--force") or x.startswith("+") for x in command))
            or (operation == "pinned-runtime-install" and command == install)):
        raise ValueError("this operation is not an authorized idempotent infrastructure retry")
    for attempt in range(1, ATTEMPTS + 1):
        try:
            result = subprocess.run(command, cwd=cwd, text=True, capture_output=True,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            def decode(value):
                return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
            result = subprocess.CompletedProcess(command, 124, decode(exc.stdout),
                                                 decode(exc.stderr) + "\nconnection timed out")
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        retry = result.returncode != 0 and transient(output) and attempt < ATTEMPTS
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with receipt.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(),
                "operation": operation, "attempt": attempt, "exit_code": result.returncode,
                "retry": retry, "diagnostic": redact(output)[-3000:]}, ensure_ascii=False) + "\n")
        if not retry:
            return result
        time.sleep(DELAYS[attempt - 1])
    raise AssertionError("unreachable")
