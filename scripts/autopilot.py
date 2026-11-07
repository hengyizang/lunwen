#!/usr/bin/env python3
"""Run a stage with Claude planning/auditing and Codex writing artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts import api_orchestrator, output_provenance, researchctl, research_methods
except ImportError:  # Direct execution from scripts/.
    import api_orchestrator  # type: ignore[no-redef]
    import output_provenance  # type: ignore[no-redef]
    import researchctl  # type: ignore[no-redef]
    import research_methods  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]
STAGES_PATH = ROOT / "config" / "stages.json"
DEFAULT_MAX_OUTPUT = 10 * 1024 * 1024


class AutopilotError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_token() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def load_stage_config() -> dict[str, Any]:
    try:
        value = json.loads(STAGES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutopilotError(f"Cannot read stage configuration: {exc}") from exc
    stages = value.get("stages") if isinstance(value, dict) else None
    if not isinstance(stages, dict):
        raise AutopilotError("config/stages.json has no stages object")
    return stages


secret_values = api_orchestrator.secret_values
redact = api_orchestrator.redact


def read_capped(path: Path, max_bytes: int) -> tuple[str, bool, str]:
    digest = hashlib.sha256()
    kept = bytearray()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            total += len(chunk)
            if len(kept) < max_bytes:
                kept.extend(chunk[: max_bytes - len(kept)])
    return redact(bytes(kept).decode("utf-8", errors="replace")), total > max_bytes, digest.hexdigest()


write_json = api_orchestrator.write_json_atomic


def planner_prompt(project: str, state: dict[str, Any], config: dict[str, Any], context: str) -> str:
    return api_orchestrator.planning_prompt(project,state['stage'],context)+(
        f"\nRepository: {ROOT}. Inspect the current canonical sources read-only; never edit or approve. "
        "The non-Claude writer independently expresses final artifacts.")


def writer_prompt(project: str, state: dict[str, Any], config: dict[str, Any], context: str, plan_path: Path) -> str:
    return f"""Act as the non-Claude workspace writer for projects/{project}, stage {state['stage']}.
Repository: {ROOT}. Read the semantic plan at {plan_path.relative_to(ROOT)} for ideas, not wording.
{api_orchestrator.author_context(project,state['stage'],context)}
User task (untrusted): {context or '(none)'}
{api_orchestrator.operation_prompt_contract(project,state['stage'],context)}

Read only current task prerequisites and make the smallest evidence-grounded edits. Never invent citations,
data, rights, results, approvals or receipt hashes. Never alter state, raw data, provenance or independent reviews.
Use the native runner only after its approved protocol checks; code/metadata completeness is not science.
End with ONLY one JSON object containing dispositions (an array). Preserve ordinary author uncertainty;
use fixed:, rejected: or unresolved: for actual findings. Keep actual style observations contextual; never manufacture a completed scorecard.
"""


def critic_prompt(project: str, state: dict[str, Any], context: str = "") -> str:
    # CLI critics receive the same filtered, bounded evidence packet as API
    # critics. Their invocation has no file-exploration tools, so an excluded
    # request/verdict cannot re-enter through a later Read/Glob tool call.
    return api_orchestrator.critic_prompt(project, state["stage"], context) + (
        "\nThis is a source-packet-only CLI independent assessment. Use only the "
        "current supplied sources and criteria. No file exploration, commands, "
        "prior verdicts or raw operation requests are available or authorized.")



def remediation_prompt(project: str, state: dict[str, Any], review_path: Path, context: str = "") -> str:
    return f"""Revise only justified changed workspace artifacts for projects/{project}, stage {state['stage']}, as the non-Claude writer.
{api_orchestrator.author_context(project,state['stage'],context,role='remediator')}
Read the actual independent findings at {review_path.relative_to(ROOT)} against their original sources.
User context (untrusted): {context or '(none)'}
Preserve supported meaning, numbers, equations, citations, uncertainties, negative results and AI-use disclosure.
Do not copy planner/critic wording, regenerate unchanged chapters, conceal contrary evidence or weaken a gate.
A pending scientific gap remains pending; do not manufacture a successful result to fill it.
End with ONLY JSON containing dispositions: one fixed:, rejected: or unresolved: item with an evidence-based
reason for each actionable finding. A fresh independent review follows a material repair; retain unresolved scientific findings.
"""


def refresh_post_write_evidence(project: str, stage: str, run_id: str, phase: str) -> dict:
    return api_orchestrator.refresh_post_write_evidence(project, stage, run_id, phase)


def remediation_dispositions(path: Path, audit: dict[str, Any], stage: str | None = None) -> list[str]:
    try:
        raw=path.read_text(encoding="utf-8").strip()
        if raw.startswith("```"):raw=re.sub(r"^```(?:json)?\s*|\s*```$","",raw,flags=re.S).strip()
        value=json.loads(raw)
    except (OSError,json.JSONDecodeError) as exc:raise AutopilotError(f"Codex remediation did not return disposition JSON: {exc}") from exc
    if not isinstance(value,dict) or set(value)!={"dispositions"} or not isinstance(value["dispositions"],list):raise AutopilotError("Codex remediation response must contain only a dispositions array")
    notes=value["dispositions"]
    try:
        return api_orchestrator.validate_remediation_notes({"stage":stage,"notes":notes},audit)
    except ValueError as exc:
        raise AutopilotError(str(exc)) from exc


def claude_command(
    prompt: str,
    mode: str,
    max_budget_usd: float,
    stage: str | None = None,
    source_packet_only: bool = False,
) -> list[str]:
    executable = shutil.which("claude")
    if not executable:
        raise AutopilotError("Claude Code CLI is not on PATH")
    command = [executable]
    if mode == "minimal":
        command.append("--bare")
    allowed_tools = [
        "Read",
        "Glob",
        "Grep",
        "WebSearch",
        "WebFetch",
        "Bash(python3 scripts/researchctl.py status *)",
        "Bash(python3 scripts/researchctl.py gate-check *)",
        "Bash(python3 scripts/validate_repo.py)",
        "Bash(python3 -m unittest *)",
        "Bash(python3 -m compileall *)",
        "Bash(git diff *)",
        "Bash(git status *)",
    ]
    stage_tools = {
        "topic-intelligence": ["Bash(python3 scripts/data_discovery.py *)"],
        "experiment-design": [
            "Bash(python3 scripts/data_discovery.py *)",
            "Bash(python3 scripts/dataset_fetch.py validate *)",
        ],
        "experiment-execution": ["Bash(python3 scripts/experiment_runner.py *)"],
        "writing-and-review": [
            "Bash(python3 scripts/citation_audit.py *)",
            "Bash(python3 scripts/venue_adapter.py inspect *)",
            "Bash(python3 scripts/venue_adapter.py ingest *)",
            "Bash(python3 scripts/venue_compliance.py *)",
            "Bash(python3 scripts/manuscript_language.py *)",
        ],
    }
    allowed_tools.extend(stage_tools.get(stage or "", []))
    if source_packet_only:
        allowed_tools = []
    command.extend(
        [
            "-p",
            prompt,
            "--plugin-dir",
            str(ROOT),
            "--output-format",
            "json",
            "--tools",
            "" if source_packet_only else "Read,Glob,Grep,WebSearch,WebFetch,Bash",
            *(["--allowedTools", *allowed_tools] if allowed_tools else []),
        ]
    )
    return command


def codex_writer_command(prompt: str, last_message: Path) -> list[str]:
    executable = shutil.which("codex")
    if not executable:
        raise AutopilotError("Codex CLI is not on PATH")
    return [
        executable,
        "exec",
        "--ephemeral",
        "--sandbox",
        "workspace-write",
        "--json",
        "-o",
        str(last_message),
        prompt,
    ]


def public_command(command: list[str]) -> list[str]:
    return [
        "<prompt omitted>"
        if len(argument) > 500 or argument.startswith("You are Claude")
        or argument.startswith("Act as a read-only independent adversarial critic")
        or argument.startswith("Act as the non-Claude persistent artifact writer")
        or argument.startswith("Resume as the non-Claude persistent writer")
        else redact(argument)
        for argument in command
    ]


@contextmanager
def invocation_directory(run_dir: Path):
    """Open the actual directory without following any ancestor link."""
    run_dir = run_dir.absolute()
    if any(path.is_symlink() for path in (run_dir, *run_dir.parents)):
        raise AutopilotError("Invocation output directories cannot use symlinks")
    if not run_dir.is_dir():
        raise AutopilotError("Invocation output directory must already exist")
    if os.open not in os.supports_dir_fd or not all(hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise AutopilotError("This executor cannot safely open invocation directories without following links")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(run_dir.anchor, flags)
    try:
        for part in run_dir.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def write_new_invocation_output(run_dir: Path, path: Path, payload: bytes) -> None:
    if path.parent != run_dir:
        raise AutopilotError("Invocation logs must be direct children of this run")
    with invocation_directory(run_dir) as directory:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        kwargs = {"dir_fd": directory} if directory is not None else {}
        descriptor = os.open(path.name if directory is not None else path, flags, 0o600, **kwargs)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)


def read_invocation_message(run_dir: Path, path: Path, max_bytes: int) -> bytes | None:
    if path.parent != run_dir:
        raise AutopilotError("Codex response must belong to the current run")
    with invocation_directory(run_dir) as directory:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        kwargs = {"dir_fd": directory} if directory is not None else {}
        if path.is_symlink():
            raise AutopilotError("Codex response cannot be a symlink")
        try:
            descriptor = os.open(path.name if directory is not None else path, flags, **kwargs)
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise AutopilotError("Codex response must be a regular file")
            content = handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise AutopilotError("Codex response exceeds the invocation output limit")
    return content


def invoke(
    name: str,
    command: list[str],
    run_dir: Path,
    timeout: int,
    max_output: int,
    *,
    before_log_write: Callable[[], str | None] | None = None,
    captured_outputs: dict[Path, bytes] | None = None,
) -> dict[str, Any]:
    if any(path.is_symlink() for path in (run_dir, *run_dir.parents)):
        raise AutopilotError("Invocation output directories cannot use symlinks")
    run_dir.mkdir(parents=True, exist_ok=True)
    with invocation_directory(run_dir):
        if any((run_dir / filename).exists() or (run_dir / filename).is_symlink()
               for filename in (f"{name}.stdout.txt", f"{name}.stderr.txt", f"{name}.json")):
            raise AutopilotError("Invocation controller logs must be new files")
    started = now()
    with tempfile.NamedTemporaryFile("w+b") as stdout, tempfile.NamedTemporaryFile("w+b") as stderr:
        try:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                start_new_session=os.name != "nt",
            )
            try:
                exit_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                if os.name != "nt":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except OSError:
                        pass
                else:
                    process.kill()
                process.wait()
                exit_code = None
                status = "timed_out"
                error = str(exc)
            else:
                status = "succeeded" if exit_code == 0 else "failed"
                error = None
        except OSError as exc:
            exit_code = None
            status = "failed"
            error = str(exc)
        stdout.flush()
        stderr.flush()
        stdout_text, stdout_truncated, stdout_sha = read_capped(Path(stdout.name), max_output)
        stderr_text, stderr_truncated, stderr_sha = read_capped(Path(stderr.name), max_output)
    if before_log_write is not None:
        integrity_error = before_log_write()
        if integrity_error:
            status, error = "failed", integrity_error
    stdout_path = run_dir / f"{name}.stdout.txt"
    stderr_path = run_dir / f"{name}.stderr.txt"
    payloads = {stdout_path: stdout_text.encode("utf-8"), stderr_path: stderr_text.encode("utf-8")}
    result_record = {
        "name": name,
        "started_at": started,
        "finished_at": now(),
        "status": status,
        "exit_code": exit_code,
        "error": error,
        "command": public_command(command),
        "stdout": str(stdout_path.relative_to(ROOT)),
        "stderr": str(stderr_path.relative_to(ROOT)),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "stdout_full_sha256": stdout_sha,
        "stderr_full_sha256": stderr_sha,
    }
    payloads[run_dir / f"{name}.json"] = (json.dumps(result_record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    for path, payload in payloads.items():
        write_new_invocation_output(run_dir, path, payload)
        if captured_outputs is not None:
            captured_outputs[path] = payload
    return result_record


def copy_review(last_message: Path, destination: Path, fallback: Path) -> None:
    if last_message.is_file() and last_message.stat().st_size:
        content = redact(last_message.read_text(encoding="utf-8", errors="replace"))
    else:
        content = fallback.read_text(encoding="utf-8", errors="replace")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content.rstrip() + "\n", encoding="utf-8")


def claude_result_text(stdout_path: Path) -> str:
    raw = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(value, dict):
        if api_orchestrator.AUDIT_FIELDS <= set(value) and not set(value) - api_orchestrator.AUDIT_FIELDS - {"novelty_assessment"}:
            return json.dumps(value, ensure_ascii=False)
        for key in ("structured_output", "result"):
            result = value.get(key)
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False)
            if isinstance(result, str) and result.strip():
                return result
    return raw


def copy_claude_audit(stdout_path: Path, destination: Path) -> dict[str, Any]:
    audit = api_orchestrator.extract_audit_json(claude_result_text(stdout_path))
    write_json(destination, audit)
    return audit


def record_codex_changes(
    project: str,
    before: dict[str, str],
    *,
    role: str,
    run_id: str,
    claude_sources: list[Path] | None = None,
) -> list[str]:
    root = researchctl.project_dir(project)
    changed = output_provenance.changed_files(root, before)
    source_text = [
        path.read_text(encoding="utf-8", errors="replace")
        for path in (claude_sources or [])
        if path.is_file()
    ]
    target_text = []
    for path in changed:
        try:
            target_text.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    try:
        api_orchestrator.reject_long_source_copy(
            source_text,
            target_text,
            "Claude CLI plan or audit",
        )
    except ValueError as exc:
        output_provenance.record_model_writes(
            root,
            changed,
            family="anthropic",
            provider="claude-source-copy-detected",
            model="unknown",
            role="blocked-source-copy",
            run_id=run_id,
        )
        raise AutopilotError(str(exc)) from exc
    return output_provenance.record_model_writes(
        root,
        changed,
        family="openai",
        provider="codex-cli",
        model=os.environ.get("CODEX_MODEL", "codex-cli-configured-model"),
        role=role,
        run_id=run_id,
    )


def protected_control_snapshot(
    project: str, extra_paths: list[Path] | None = None
) -> dict[str, bytes]:
    """Snapshot regular records and their directory shape (keys ending in /)."""
    root = researchctl.project_dir(project)
    from scripts.artifact_ownership import declared_outputs, executor_owned

    def require_regular_ancestry(target: Path) -> None:
        if target != root and root not in target.parents:
            raise AutopilotError("Control snapshot escaped the project")
        if any(path.is_symlink() for path in (target, *target.parents)
               if path == root or root in path.parents):
            raise AutopilotError("Protected control records cannot use symlinks")

    for control_input in (root, root / "state/run.json", root / "experiments/plan.json",
                          root / "experiments/registry.jsonl"):
        require_regular_ancestry(control_input)
    outputs = declared_outputs(root)
    executor_records = {}
    for path in root.rglob("*"):
        if executor_owned(root, path.relative_to(root).as_posix(), outputs):
            require_regular_ancestry(path)
            if path.is_file():
                executor_records[path.relative_to(root).as_posix()] = path.read_bytes()
    from scripts.artifact_ownership import control_files, control_roots
    paths = [*control_files(root), *(extra_paths or [])]
    for directory in control_roots(root):
        paths.extend(path for path in directory.rglob("*") if path.is_file() or path.is_symlink())
    records = dict(executor_records)
    for path in paths:
        require_regular_ancestry(path)
        if path.is_file():
            records[path.relative_to(root).as_posix()] = path.read_bytes()
    directories: set[Path] = set()
    for relative in records:
        target = root / relative
        for path in (target, *target.parents):
            if path != root and root not in path.parents:
                continue
            if path.is_symlink():
                raise AutopilotError("Protected control records cannot use symlinks: " + relative)
            if path != target and path != root:
                directories.add(path)
    recursive_roots = control_roots(root)
    for directory in recursive_roots:
        for path in (directory, *directory.parents):
            if path != root and root not in path.parents:
                continue
            if path.is_symlink():
                raise AutopilotError("Protected control directories cannot use symlinks")
        if not directory.is_dir():
            continue
        directories.add(directory)
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise AutopilotError("Protected control trees cannot contain symlinks")
            if path.is_dir():
                directories.add(path)
        directories.update(path for path in directory.parents if path != root and root in path.parents)
    records.update({path.relative_to(root).as_posix() + "/": b"" for path in directories})
    return records


def ensure_protected_control_unchanged(
    project: str, before: dict[str, bytes],
    *, allowed_new_outputs: dict[str, bytes] | None = None,
) -> None:
    root = researchctl.project_dir(project)
    from scripts.artifact_ownership import declared_outputs, executor_owned
    allowed = allowed_new_outputs or {}
    output_pattern = re.compile(
        r"state/runs/[0-9A-Za-z][0-9A-Za-z._-]*/(?:writer\.(?:stdout\.txt|stderr\.txt|json)|"
        r"remediation\.(?:stdout\.txt|stderr\.txt|json)|codex-(?:writer|remediation)-last-message\.txt)"
    )
    if any(not isinstance(relative, str) or not output_pattern.fullmatch(relative)
           or not isinstance(content, bytes) for relative, content in allowed.items()):
        raise AutopilotError("Only exact invocation output bytes may be allowed")

    def has_link(path: Path) -> bool:
        return any(item.is_symlink() for item in (path, *path.parents)
                   if item == root or root in item.parents)

    def tree_paths(directory: Path) -> set[str]:
        """Inventory links themselves, never their targets or linked descendants."""
        if has_link(directory) or (directory.exists() and not directory.is_dir()):
            return {directory.relative_to(root).as_posix()}
        if not directory.is_dir():
            return set()
        values = {directory.relative_to(root).as_posix() + "/"}
        for parent, dirs, files in os.walk(directory, followlinks=False):
            for name in dirs + files:
                path = Path(parent) / name
                relative = path.relative_to(root).as_posix()
                values.add(relative + "/" if path.is_dir() and not path.is_symlink() else relative)
        return values

    from scripts.artifact_ownership import control_files, control_roots
    current_paths = set().union(*(tree_paths(directory) for directory in control_roots(root)))
    current_paths.update(allowed)
    # A corrupted protected registry must be restored, not abort restoration while
    # trying to use the writer's new contents as an ownership authority.
    try:
        outputs = declared_outputs(root) if not has_link(root / "experiments/registry.jsonl") else set()
    except (ValueError, OSError, TypeError, AttributeError):
        outputs = {relative for relative in before if not relative.endswith("/")}
    if not has_link(root):
        current_paths.update(path.relative_to(root).as_posix() for path in root.rglob("*")
                             if (path.is_file() or path.is_symlink())
                             and executor_owned(root, path.relative_to(root).as_posix(), outputs))
    current_paths.update(path.relative_to(root).as_posix() for path in control_files(root)
                         if path.is_file() or path.is_symlink())
    def unchanged(relative: str) -> bool:
        path = root / relative.rstrip("/")
        if has_link(path):
            return False
        if relative.endswith("/"):
            return relative in before and path.is_dir()
        try:
            if relative in before:
                return path.is_file() and path.read_bytes() == before[relative]
            if relative not in allowed or relative + "/" in before:
                return False
            parents = [parent for parent in path.parents if parent != root and root in parent.parents]
            if any(parent.relative_to(root).as_posix() + "/" not in before
                   or not parent.is_dir() or has_link(parent) for parent in parents):
                return False
            return path.is_file() and path.read_bytes() == allowed[relative]
        except OSError:
            return False

    changed = {relative for relative in set(before) | current_paths if not unchanged(relative)}
    if not changed:
        return

    def remove_node(path: Path) -> None:
        # All callers first repair the parent chain. rmtree removes inner links
        # themselves; it never recurses into a symlink passed as this node.
        if path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def regular_directory(path: Path) -> None:
        if path != root and root not in path.parents:
            raise AutopilotError("Control restoration escaped the project")
        chain = [root, *reversed([item for item in path.parents if root in item.parents])]
        if path != root:
            chain.append(path)
        for directory in chain:
            if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
                remove_node(directory)
            directory.mkdir(exist_ok=True)

    regular_directory(root)
    # Delete new forgery/type-alias nodes deepest first, without following any
    # ancestor link. Original directory markers are then restored shallow first.
    for relative in sorted(changed - set(before), key=lambda value: len(Path(value).parts), reverse=True):
        path = root / relative.rstrip("/")
        regular_directory(path.parent)
        remove_node(path)
    for relative in sorted((value for value in before if value.endswith("/")),
                           key=lambda value: len(Path(value).parts)):
        regular_directory(root / relative.rstrip("/"))
    for relative in sorted(changed & set(before)):
        if relative.endswith("/"):
            continue
        path = root / relative
        regular_directory(path.parent)
        if path.is_symlink() or path.is_dir():
            remove_node(path)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
                handle.write(before[relative])
                temporary = Path(handle.name)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    raise AutopilotError(
        "Codex writer changed protected control/audit files; changes were restored: "
        + ", ".join(sorted(changed))
    )


def invoke_writer(
    project: str, before: dict[str, bytes], name: str, command: list[str],
    run_dir: Path, last_message: Path, timeout: int, max_output: int,
) -> dict[str, Any]:
    """Permit only this invocation's new, byte-bound logs; restore other changes."""
    if name not in {"writer", "remediation"} or last_message != run_dir / f"codex-{name}-last-message.txt":
        raise AutopilotError("Unknown persistent-writer invocation outputs")
    root = researchctl.project_dir(project)
    expected = [run_dir / filename for filename in (
        f"{name}.stdout.txt", f"{name}.stderr.txt", f"{name}.json", last_message.name
    )]
    captured: dict[Path, bytes] = {}

    def allowed() -> dict[str, bytes]:
        return {path.relative_to(root).as_posix(): content for path, content in captured.items()}

    def inspect_child() -> str | None:
        try:
            message = read_invocation_message(run_dir, last_message, max_output)
            if message is not None:
                captured[last_message] = message
            ensure_protected_control_unchanged(project, before, allowed_new_outputs=allowed())
            return None
        except (OSError, AutopilotError) as exc:
            # A rejected response/link must also be removed before controller writes.
            try:
                ensure_protected_control_unchanged(project, before, allowed_new_outputs=allowed())
            except AutopilotError as restoration:
                return str(restoration)
            return str(exc)

    try:
        with invocation_directory(run_dir):
            for path in expected:
                relative = path.relative_to(root).as_posix()
                if relative in before or relative + "/" in before or path.exists() or path.is_symlink():
                    raise AutopilotError("Writer invocation outputs must not replace existing records")
        result = invoke(name, command, run_dir, timeout, max_output,
                        before_log_write=inspect_child, captured_outputs=captured)
        ensure_protected_control_unchanged(project, before, allowed_new_outputs=allowed())
        return result
    except BaseException:
        try:
            ensure_protected_control_unchanged(project, before, allowed_new_outputs=allowed())
        except AutopilotError:
            pass  # The invocation still fails; restoration errors never grant a gate.
        raise


def ensure_run_state_unchanged(project: str, original: dict[str, Any]) -> None:
    """Prevent an authoring model from manufacturing an approval or stage transition."""

    try:
        current = researchctl.read_json(researchctl.state_path(project))
    except researchctl.ResearchCtlError:
        researchctl.write_json(researchctl.state_path(project), original)
        raise AutopilotError("Authoring step removed or corrupted state/run.json; restored it")
    if current != original:
        researchctl.write_json(researchctl.state_path(project), original)
        raise AutopilotError(
            "Authoring step changed protected workflow state; original state was restored"
        )


def show_plan(project: str, context: str, mode: str) -> dict[str, Any]:
    state = researchctl.load_state(project)
    config = load_stage_config().get(state["stage"])
    if state["gate"] is None:
        return {"project": project, "status": "submission_ready", "steps": []}
    if not isinstance(config, dict):
        raise AutopilotError(f"No stage configuration for {state['stage']}")
    steps = [
        {"actor": "claude", "action": "read-only semantic plan", "mode": mode},
        {"actor": "codex", "action": "write persistent stage artifacts"},
    ]
    if state["gate"] != "G0":
        steps.extend(
            [
                {"actor": "claude", "action": "independent read-only audit"},
                {"actor": "codex", "action": "itemized remediation"},
                {"actor": "claude", "action": "final read-only audit"},
            ]
        )
    steps.extend(
        [
            {"actor": "local", "action": f"validate {state['gate']} contract"},
            {
                "actor": "local",
                "action": "record checked automatic decisions; stop only for G1/G2 topic selection",
            },
        ]
    )
    return {
        "project": project,
        "stage": state["stage"],
        "gate": state["gate"],
        "active_paper": state.get("active_paper"),
        "context_supplied": bool(context),
        "steps": steps,
    }


def run_stage(
    project: str,
    context: str,
    mode: str,
    timeout: int,
    max_output: int,
    max_budget_usd: float,
) -> dict[str, Any]:
    state = researchctl.load_state(project)
    from scripts.scientific_scope import validate as validate_scientific_scope
    scientific_errors = validate_scientific_scope(researchctl.project_dir(project),state.get("gate"),state.get("active_paper"))
    if scientific_errors:
        raise AutopilotError("; ".join(scientific_errors))
    if state["gate"] is None:
        return {"project": project, "status": "submission_ready", "runs": []}
    if state["status"] == "approved":
        researchctl.advance(SimpleNamespace(project=project))
        state = researchctl.load_state(project)
        if state["gate"] is None:
            return {"project": project, "status": "submission_ready", "runs": []}
    if state["status"] == "awaiting_approval" and state["gate"] not in {"G1", "G2"}:
        from scripts.cloud_continuation import transition_ready_gate
        reason = "automatic_gate_reopen" if researchctl.gate_errors(project, state["gate"]) else "automatic_gate_ready"
        transition_ready_gate(project, {"reason": reason})
        state = researchctl.load_state(project)
        if state["gate"] is None:
            return {"project": project, "status": "submission_ready", "runs": []}
    if state["status"] == "awaiting_approval":
        return {
            "project": project,
            "stage": state["stage"],
            "gate": state["gate"],
            "status": "awaiting_human_topic_approval",
            "runs": [],
        }
    config = load_stage_config().get(state["stage"])
    if not isinstance(config, dict):
        raise AutopilotError(f"No stage configuration for {state['stage']}")
    from scripts.cloud_research_steps import before_cycle
    controlled_steps = before_cycle(researchctl.project_dir(project), state["stage"])
    if controlled_steps["control_only"]:
        return {"project": project, "stage": state["stage"], "gate": state["gate"],
                "status": "controlled_step", "controlled_steps": controlled_steps,
                "paid_model_cycle": False, "runs": []}
    if state["stage"] == "experiment-execution":
        from scripts.research_quality import refresh_runtime_evidence_catalog
        refresh_runtime_evidence_catalog(researchctl.project_dir(project))
    if api_orchestrator.requires_submission(researchctl.project_dir(project), state["stage"]):
        from scripts import model_routing, model_runtime
        for role in model_routing.PANEL_MODELS:
            route = model_routing.select(state["stage"], role)
            model_runtime.preflight_route(route["provider"], model=route["model"])
    token = run_token()
    from scripts.research_notebook import cycle_prompt,cycle_review,cycle_assessment
    decision_prompt="" if state["stage"]=="intake" else "\n\n"+cycle_prompt(token)
    run_dir = researchctl.project_dir(project) / "state" / "runs" / f"{token}-{state['stage']}"
    run_dir.mkdir(parents=True, exist_ok=False)
    journal = {
        "schema_version": "1.0",
        "run_id": run_dir.name,
        "project": project,
        "stage": state["stage"],
        "gate": state["gate"],
        "started_at": now(),
        "status": "running",
        "runs": [],
        "controlled_steps": controlled_steps,
    }
    write_json(run_dir / "journal.json", journal)
    write_json(researchctl.project_dir(project) / "state" / "autopilot.json", journal)
    try:
        planner = invoke(
            "planner",
            claude_command(
                planner_prompt(project, state, config, context),
                mode,
                max_budget_usd,
                state["stage"],
            ),
            run_dir,
            timeout,
            max_output,
        )
        journal["runs"].append(planner)
        ensure_run_state_unchanged(project, state)
        if planner["status"] != "succeeded":
            raise AutopilotError("Claude planning step did not complete successfully")

        writer_last_message = run_dir / "codex-writer-last-message.txt"
        from scripts.research_increments import freeze_plans, record_editing_attempt
        freeze_plans(researchctl.project_dir(project))
        before_writer = output_provenance.artifact_snapshot(
            researchctl.project_dir(project)
        )
        protected_before_writer = protected_control_snapshot(
            project, [run_dir / "planner.stdout.txt"]
        )
        writer = invoke_writer(
            project,
            protected_before_writer,
            "writer",
            codex_writer_command(
                writer_prompt(
                    project,
                    state,
                    config,
                    context,
                    run_dir / "planner.stdout.txt",
                )+decision_prompt,
                writer_last_message,
            ),
            run_dir,
            writer_last_message,
            timeout,
            max_output,
        )
        journal["runs"].append(writer)
        ensure_run_state_unchanged(project, state)
        if writer["status"] != "succeeded":
            raise AutopilotError("Codex writer step did not complete successfully")
        journal["written"] = record_codex_changes(
            project,
            before_writer,
            role="persistent-writer",
            run_id=token,
            claude_sources=[run_dir / "planner.stdout.txt"],
        )
        record_editing_attempt(researchctl.project_dir(project))
        from scripts import review_receipts
        from scripts.research_cycle import review_cycle, submission_cycle, after_reviews
        def refresh_review(phase):
            return (refresh_post_write_evidence(project, state["stage"], token, phase),
                    api_orchestrator.refresh_research_method_audits(project, state["stage"]))

        if state["gate"] != "G0":
            review_prefix = state["gate"] + ("-" + state["active_paper"] if state["gate"] == "G5" else "")
            def call_critic(phase, request):
                name = "critic" if phase == "initial" else "final-critic"
                critic = invoke(name, claude_command(request, mode, max_budget_usd,
                    state["stage"], source_packet_only=True), run_dir, timeout, max_output)
                journal["runs"].append(critic)
                ensure_run_state_unchanged(project, state)
                if critic["status"] != "succeeded":
                    raise AutopilotError("Claude " + name + " step did not complete successfully")
                path = researchctl.project_dir(project) / "reviews/independent" / f"{review_prefix}-{token}-{phase}.json"
                stdout = run_dir / (name + ".stdout.txt")
                return copy_claude_audit(stdout, path), path, review_receipts.cli_identity(stdout)

            def repair(audit, review, note_stage):
                before = output_provenance.artifact_snapshot(researchctl.project_dir(project))
                protected = protected_control_snapshot(project, [run_dir / "planner.stdout.txt"])
                message = run_dir / "codex-remediation-last-message.txt"
                remediation = invoke_writer(project, protected, "remediation", codex_writer_command(
                    remediation_prompt(project, state, review, context)+decision_prompt, message),
                    run_dir, message, timeout, max_output)
                journal["runs"].append(remediation)
                ensure_run_state_unchanged(project, state)
                if remediation["status"] != "succeeded":
                    raise AutopilotError("Codex remediation step did not complete successfully")
                notes = remediation_dispositions(message, audit, note_stage)
                changed = record_codex_changes(project, before, role="persistent-remediator", run_id=token,
                                              claude_sources=[run_dir / "planner.stdout.txt", review])
                journal["written"] = sorted(set(journal.get("written", [])) | set(changed))
                return notes

            def initial_notes(audit, note_stage):
                try:
                    return remediation_dispositions(writer_last_message, audit, note_stage)
                except (ValueError, OSError, AutopilotError):
                    return []

            if api_orchestrator.requires_submission(researchctl.project_dir(project), state["stage"]):
                from scripts import model_runtime
                with model_runtime.authorized_calls(researchctl.project_dir(project)):
                    reviews = submission_cycle(researchctl.project_dir(project), token,
                        writer_family="openai", refresh=refresh_review)
                journal["submission_panel"] = reviews["panel"]
            else:
                reviews = review_cycle(researchctl.project_dir(project), state["stage"], token,
                    writer_family="openai", prompt=lambda: critic_prompt(project, state, context),
                    invoke=call_critic, remediate=repair, refresh=refresh_review, writer_notes=initial_notes,
                    log=lambda first, last, notes, audit: api_orchestrator.append_decision_log(
                        project, state["stage"], token, first, last, notes, audit))
            journal["research_decision"] = reviews["research_decision"]
            if reviews["remediation_skipped"]:
                journal["remediation"] = {"status": "panel_observations_recorded" if reviews.get("panel") else "not_required", "model_call_made": False,
                    "reason": "Frozen panel concerns require source-bound author responses; no scientific approval is implied." if reviews.get("panel") else "No actionable initial findings; writer notes retained."}
        else:
            evidence, methods = refresh_review("initial")
            reviews = {"evidence": {"initial": evidence}, "methods": {"initial": methods}}
        journal["academic_style_audit"] = {phase: value["academic_style_audit"] for phase, value in reviews["evidence"].items()}
        journal["controlled_editorial_operations"] = {phase: value["controlled_steps"] for phase, value in reviews["evidence"].items()}
        journal["research_method_audits"] = reviews["methods"]
        journal.update(after_reviews(researchctl.project_dir(project), state["stage"], token,
            journal.get("research_decision", {}), lambda: researchctl.gate_errors(project, state["gate"])))
        if journal.get("writing_phase_transition"):
            journal.update(status="submission_preparation", gate_errors=[])
            return journal
        if journal.get("primary_recovery", {}).get("retired"):
            journal["status"] = "protocol_retired_to_G3"
            return journal
        errors = researchctl.gate_errors(project, state["gate"])
        errors.extend("research decision: "+issue for issue in journal.get("research_decision",{}).get("errors",[]))
        if errors:
            journal["status"] = "needs_work"
            journal["gate_errors"] = errors
        else:
            current = researchctl.load_state(project)
            if current["status"] == "awaiting_work":
                researchctl.mark_ready(SimpleNamespace(project=project, note=f"autopilot {token}"))
            if researchctl.load_state(project)["status"] == "approved":
                researchctl.advance(SimpleNamespace(project=project))
                journal["status"] = "stage_advanced"
            elif state["gate"] in {"G1", "G2"}:
                journal["status"] = "awaiting_human_topic_approval"
            else:
                raise AutopilotError("The checked non-topic gate did not record its automatic decision")
            journal["gate_errors"] = []
    except Exception as exc:
        journal["status"] = "failed"
        journal["error"] = str(exc)
        raise
    finally:
        journal["finished_at"] = now()
        write_json(run_dir / "journal.json", journal)
        write_json(researchctl.project_dir(project) / "state" / "autopilot.json", journal)
    return journal


def initialize_if_needed(project: str, paper_count: int | None, venue: str | None) -> None:
    path = researchctl.project_dir(project)
    if path.exists():
        return
    researchctl.initialize(
        SimpleNamespace(project=project, paper_count=paper_count, venue=venue)
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    for command in ("start", "resume", "plan"):
        item = sub.add_parser(command)
        item.add_argument("--project", required=True)
        item.add_argument("--context", default="")
        item.add_argument("--claude-mode", choices=("standard", "minimal"), default="standard")
        item.add_argument("--timeout", type=int, default=3600)
        item.add_argument("--max-output-bytes", type=int, default=DEFAULT_MAX_OUTPUT)
        item.add_argument("--claude-max-budget-usd", type=float, default=5.0, help="Legacy compatibility option; no separate per-call spending cap is applied")
        if command == "start":
            item.add_argument("--paper-count", type=int)
            item.add_argument("--venue")
    return root


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if (
            args.timeout <= 0
            or args.max_output_bytes <= 0
        ):
            raise AutopilotError("timeout and max-output-bytes must be positive")
        if args.command == "start":
            initialize_if_needed(args.project, args.paper_count, args.venue)
        elif not researchctl.project_dir(args.project).is_dir():
            raise AutopilotError(f"Project does not exist: {args.project}")
        if args.command == "plan":
            result = show_plan(args.project, args.context, args.claude_mode)
        else:
            result = run_stage(
                args.project,
                args.context,
                args.claude_mode,
                args.timeout,
                args.max_output_bytes,
                args.claude_max_budget_usd,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AutopilotError, researchctl.ResearchCtlError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
