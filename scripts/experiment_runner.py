#!/usr/bin/env python3
"""Run explicitly approved experiment commands and register every attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import platform
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
RUN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
PAPER_RE = re.compile(r"^P[0-9]{2}$")
DEFAULT_EXECUTABLES = {"python", "python3", "Rscript", "julia"}
MAX_LOG_BYTES = 2 * 1024 * 1024
FILE_ARGUMENT_SUFFIXES = {
    ".py", ".r", ".jl", ".json", ".jsonl", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".csv", ".tsv", ".parquet", ".npy", ".npz",
    ".h5", ".hdf5", ".wav", ".txt",
}


class ExperimentError(RuntimeError):
    pass


def allowed_executable(value: str) -> bool:
    name = Path(value).name
    return name in DEFAULT_EXECUTABLES or bool(re.fullmatch(r"python(?:3(?:\.\d+)?)?", name))


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExperimentError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ExperimentError(f"Expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_inside(root: Path, relative: Any, field: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ExperimentError(f"{field} must be a non-empty relative path")
    candidate = Path(relative)
    if candidate.is_absolute():
        raise ExperimentError(f"{field} must be relative to the project")
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ExperimentError(f"{field} escapes the project directory")
    return resolved


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if plan.get("status") != "ready_for_review":
        errors.append("status must remain ready_for_review after G3 approval")
    runs = plan.get("runs")
    if not isinstance(runs, list) or not runs:
        return errors + ["runs must be a non-empty array"]
    seen: set[str] = set()
    for index, run in enumerate(runs):
        prefix = f"runs[{index}]"
        if not isinstance(run, dict):
            errors.append(f"{prefix} must be an object")
            continue
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            errors.append(f"{prefix}.run_id is invalid")
        elif run_id in seen:
            errors.append(f"duplicate run_id: {run_id}")
        else:
            seen.add(run_id)
        if not PAPER_RE.fullmatch(str(run.get("paper_id", ""))):
            errors.append(f"{prefix}.paper_id must look like P01")
        argv = run.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(value, str) or not value for value in argv)
        ):
            errors.append(f"{prefix}.argv must be a non-empty string array")
        elif not allowed_executable(argv[0]):
            errors.append(
                f"{prefix}.argv executable must be Python, Rscript, or Julia"
            )
        timeout = run.get("timeout_seconds")
        if not isinstance(timeout, int) or not 1 <= timeout <= 7 * 24 * 60 * 60:
            errors.append(f"{prefix}.timeout_seconds must be between 1 and 604800")
        estimate = run.get("estimated_cost_usd")
        if not isinstance(estimate, (int, float)) or isinstance(estimate, bool) or estimate < 0:
            errors.append(f"{prefix}.estimated_cost_usd must be non-negative")
        isolation = run.get("isolation")
        if not isinstance(isolation, dict) or isolation.get("kind") not in {"host", "git_worktree", "container"}:
            errors.append(f"{prefix}.isolation must select host, git_worktree or container")
        elif isolation.get("kind") == "container":
            if isolation.get("engine") not in {"docker", "podman"}:
                errors.append(f"{prefix}.isolation.engine must be docker or podman")
            if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", str(isolation.get("image", ""))):
                errors.append(f"{prefix}.isolation.image must be pinned by sha256 digest")
        seed = run.get("seed")
        if not isinstance(seed, int):
            errors.append(f"{prefix}.seed must be an integer")
        outputs = run.get("expected_outputs")
        if not isinstance(outputs, list) or not outputs or any(not isinstance(item, str) or not item.strip() for item in outputs):
            errors.append(f"{prefix}.expected_outputs must be a non-empty string array")
        elif len(outputs)!=len(set(outputs)) or any(Path(item).is_absolute() or ".." in Path(item).parts for item in outputs):
            errors.append(f"{prefix}.expected_outputs must be unique project-relative paths")
        inputs = run.get("inputs")
        if not isinstance(inputs, list):
            errors.append(f"{prefix}.inputs must be an array")
        else:
            for input_index, item in enumerate(inputs):
                if not isinstance(item, dict):
                    errors.append(f"{prefix}.inputs[{input_index}] must be an object")
                    continue
                checksum = item.get("sha256")
                if (
                    not isinstance(item.get("path"), str)
                    or not isinstance(checksum, str)
                    or not re.fullmatch(r"[0-9a-fA-F]{64}", checksum)
                ):
                    errors.append(
                        f"{prefix}.inputs[{input_index}] needs relative path and SHA-256"
                    )
                elif Path(item["path"]).is_absolute() or ".." in Path(item["path"]).parts:
                    errors.append(f"{prefix}.inputs[{input_index}].path must be project-relative")
            input_paths = {
                item.get("path")
                for item in inputs
                if isinstance(item, dict) and isinstance(item.get("path"), str)
            }
            output_paths = {
                item for item in outputs if isinstance(item, str)
            } if isinstance(outputs, list) else set()
            if input_paths.intersection(output_paths):
                errors.append(f"{prefix}.inputs and expected_outputs must be disjoint")
            if isinstance(argv, list):
                for argument_index, argument in enumerate(argv[1:], 1):
                    if not isinstance(argument, str) or argument.startswith("-"):
                        continue
                    argument_path = Path(argument)
                    if argument_path.is_absolute():
                        if isinstance(isolation, dict) and isolation.get("kind") != "container":
                            errors.append(
                                f"{prefix}.argv[{argument_index}] absolute file paths require a pinned container"
                            )
                    elif (
                        argument_path.suffix.lower() in FILE_ARGUMENT_SUFFIXES
                        and argument not in input_paths
                        and argument not in output_paths
                    ):
                        errors.append(
                            f"{prefix}.argv[{argument_index}] file argument must be hash-declared in inputs"
                        )
        cwd = run.get("cwd", ".")
        if not isinstance(cwd, str) or Path(cwd).is_absolute() or ".." in Path(cwd).parts:
            errors.append(f"{prefix}.cwd must be a relative string")
    return errors


def budget_ceiling(budget: dict[str, Any]) -> float:
    if budget.get("status") != "ready_for_review":
        raise ExperimentError("experiments/budget.json status must be ready_for_review")
    value = budget.get("hard_ceiling_usd")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ExperimentError("budget hard_ceiling_usd must be non-negative")
    return float(value)


def approved_plan(project: Path, plan_path: Path, budget_path: Path) -> tuple[dict[str, Any], float]:
    state = read_json(project / "state" / "run.json")
    if (
        state.get("stage") != "experiment-execution"
        or state.get("gate") != "G4"
        or state.get("status") != "awaiting_work"
    ):
        raise ExperimentError(
            "Experiments may run only during the open G4 experiment-execution stage"
        )
    approval = next(
        (item for item in reversed(state.get("approvals", [])) if item.get("gate") == "G3"),
        None,
    )
    if not approval:
        raise ExperimentError("G3 has no recorded human approval")
    expected_plan = approval.get("experiment_plan_sha256")
    expected_budget = approval.get("experiment_budget_sha256")
    if not expected_plan or not expected_budget:
        raise ExperimentError("G3 approval predates the executable plan contract; approve G3 again")
    if sha256_file(plan_path) != expected_plan or sha256_file(budget_path) != expected_budget:
        raise ExperimentError("Experiment plan or budget changed after G3 approval")
    plan = read_json(plan_path)
    errors = validate_plan(plan)
    if errors:
        raise ExperimentError("; ".join(errors))
    return plan, budget_ceiling(read_json(budget_path))


def safe_environment(run_id: str, seed: int) -> dict[str, str]:
    allowed = {
        "PATH",
        "LANG",
        "LC_ALL",
        "TZ",
        "TMPDIR",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "CUDA_VISIBLE_DEVICES",
        "OMP_NUM_THREADS",
    }
    environment = {key: value for key, value in os.environ.items() if key in allowed}
    environment.update(
        {
            "RESEARCH_OS_RUN_ID": run_id,
            "RESEARCH_OS_SEED": str(seed),
            "PYTHONHASHSEED": str(seed),
        }
    )
    return environment


def git_commit(cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def git_path(cwd: Path, argument: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", argument], cwd=cwd, check=True,
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    if not value:
        return None
    path = Path(value)
    return str((cwd / path).resolve() if not path.is_absolute() else path.resolve())


def isolation_record(
    project: Path, cwd: Path, specification: dict[str, Any], attempt_id: str
) -> dict[str, Any]:
    kind = specification["kind"]
    record: dict[str, Any] = {
        "kind": kind,
        "instance_id": attempt_id,
        "checkout_root": git_path(cwd, "--show-toplevel"),
        "git_dir": git_path(cwd, "--git-dir"),
        "git_common_dir": git_path(cwd, "--git-common-dir"),
    }
    if kind == "git_worktree":
        if not record["checkout_root"] or not record["git_dir"] or not record["git_common_dir"]:
            raise ExperimentError("git_worktree isolation requires an actual Git worktree")
        if record["git_dir"] == record["git_common_dir"]:
            raise ExperimentError("git_worktree isolation requires a linked worktree, not the primary checkout")
        record.update(
            {
                "isolated_executor": False,
                "separate_checkout": True,
                "network_disabled": False,
                "read_only_root": False,
            }
        )
    elif kind == "container":
        record.update(
            {
                "isolated_executor": True,
                "separate_checkout": False,
                "network_disabled": True,
                "read_only_root": True,
                "engine": specification["engine"],
                "image": specification["image"],
                "image_digest": specification["image"].rsplit("@sha256:", 1)[1],
            }
        )
    else:
        record.update(
            {
                "isolated_executor": False,
                "separate_checkout": False,
                "network_disabled": False,
                "read_only_root": False,
            }
        )
    fingerprint_value = {
        key: record.get(key)
        for key in ("kind", "checkout_root", "git_dir", "git_common_dir", "engine", "image_digest")
    }
    record["fingerprint"] = hashlib.sha256(
        json.dumps(fingerprint_value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return record


def execution_command(
    project: Path,
    cwd: Path,
    run: dict[str, Any],
    environment: dict[str, str],
) -> tuple[list[str], Path, dict[str, str]]:
    isolation = run["isolation"]
    if isolation["kind"] != "container":
        return list(run["argv"]), cwd, environment
    relative_cwd = cwd.relative_to(project).as_posix()
    workdir = "/workspace" if relative_cwd == "." else f"/workspace/{relative_cwd}"
    command = [
        isolation["engine"], "run", "--rm", "--network=none", "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec", "--security-opt", "no-new-privileges",
        "-v", f"{project.resolve()}:/workspace:rw", "-w", workdir,
    ]
    for item in run["inputs"]:
        source = resolve_inside(project, item["path"], f"{run['run_id']}.inputs")
        target = f"/workspace/{Path(item['path']).as_posix()}"
        command.extend(["--mount", f"type=bind,src={source},dst={target},readonly"])
    for key in ("RESEARCH_OS_RUN_ID", "RESEARCH_OS_SEED", "PYTHONHASHSEED"):
        command.extend(["-e", f"{key}={environment[key]}"])
    command.extend([isolation["image"], *run["argv"]])
    return command, project, environment


def read_capped(path: Path, limit: int = MAX_LOG_BYTES) -> tuple[str, bool]:
    with path.open("rb") as handle:
        payload = handle.read(limit + 1)
    truncated = len(payload) > limit
    return payload[:limit].decode("utf-8", errors="replace"), truncated


def append_registry(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def prior_estimated_cost(registry: Path) -> float:
    if not registry.is_file():
        return 0.0
    total = 0.0
    for line in registry.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("status") in {"succeeded", "failed", "timed_out"}:
            value = entry.get("estimated_cost_usd", 0)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += float(value)
    return total


def run_one(
    project: Path, run: dict[str, Any], registry: Path, plan_sha256: str
) -> dict[str, Any]:
    run_id = run["run_id"]
    cwd = resolve_inside(project, run.get("cwd", "."), f"{run_id}.cwd")
    if not cwd.is_dir():
        raise ExperimentError(f"Run cwd does not exist: {cwd}")
    outputs = [
        resolve_inside(project, value, f"{run_id}.expected_outputs")
        for value in run["expected_outputs"]
    ]
    input_records: list[dict[str, Any]] = []
    for item in run["inputs"]:
        path = resolve_inside(project, item["path"], f"{run_id}.inputs")
        if not path.is_file():
            raise ExperimentError(f"Approved input is missing: {path}")
        actual = sha256_file(path)
        if actual.lower() != item["sha256"].lower():
            raise ExperimentError(f"Approved input hash changed: {path}")
        input_records.append(
            {
                "path": path.relative_to(project).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": actual,
            }
        )
    attempt = 1
    if registry.is_file():
        for line in registry.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("run_id") == run_id:
                    attempt += 1
            except json.JSONDecodeError:
                continue
    attempt_id = f"{run_id}-attempt-{attempt:03d}"
    log_dir = project / "experiments" / "runs" / attempt_id
    log_dir.mkdir(parents=True, exist_ok=False)
    started = now()
    monotonic_start = time.monotonic()
    status = "failed"
    exit_code: int | None = None
    error: str | None = None
    timed_out = False
    environment = safe_environment(run_id, run["seed"])
    isolation = isolation_record(project, cwd, run["isolation"], attempt_id)
    command, execution_cwd, execution_environment = execution_command(
        project, cwd, run, environment
    )
    with tempfile.NamedTemporaryFile("w+b") as stdout, tempfile.NamedTemporaryFile("w+b") as stderr:
        try:
            process = subprocess.Popen(
                command,
                cwd=execution_cwd,
                env=execution_environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                start_new_session=os.name != "nt",
            )
            try:
                exit_code = process.wait(timeout=run["timeout_seconds"])
            except subprocess.TimeoutExpired as exc:
                if os.name != "nt":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except OSError:
                        pass
                else:
                    process.kill()
                process.wait()
                status = "timed_out"
                timed_out = True
                error = str(exc)
            else:
                status = "succeeded" if exit_code == 0 else "failed"
        except OSError as exc:
            status = "failed"
            error = str(exc)
        stdout.flush()
        stderr.flush()
        stdout_text, stdout_truncated = read_capped(Path(stdout.name))
        stderr_text, stderr_truncated = read_capped(Path(stderr.name))
    (log_dir / "stdout.txt").write_text(stdout_text, encoding="utf-8")
    (log_dir / "stderr.txt").write_text(stderr_text, encoding="utf-8")
    changed_inputs: list[dict[str, Any]] = []
    for original in input_records:
        input_path = resolve_inside(project, original["path"], f"{run_id}.inputs")
        if not input_path.is_file():
            changed_inputs.append({"path": original["path"], "reason": "missing"})
            continue
        current_hash = sha256_file(input_path)
        if current_hash != original["sha256"]:
            changed_inputs.append(
                {
                    "path": original["path"],
                    "reason": "hash_changed",
                    "expected_sha256": original["sha256"],
                    "actual_sha256": current_hash,
                }
            )
    if changed_inputs:
        status = "failed"
        integrity_error = "Approved inputs changed during execution"
        error = f"{error}; {integrity_error}" if error else integrity_error
    output_records = []
    missing_outputs = []
    for output in outputs:
        if output.is_file():
            output_records.append(
                {
                    "path": output.relative_to(project).as_posix(),
                    "bytes": output.stat().st_size,
                    "sha256": sha256_file(output),
                }
            )
        else:
            missing_outputs.append(output.relative_to(project).as_posix())
    if status == "succeeded" and missing_outputs:
        status = "failed"
        error = "Expected outputs are missing"
    entry = {
        "schema_version": "1.0",
        "run_id": run_id,
        "attempt_id": attempt_id,
        "paper_id": run["paper_id"],
        "started_at": started,
        "finished_at": now(),
        "runtime_seconds": round(time.monotonic() - monotonic_start, 6),
        "status": status,
        "argv": run["argv"],
        "cwd": cwd.relative_to(project).as_posix() or ".",
        "seed": run["seed"],
        "timeout_seconds": run["timeout_seconds"],
        "timed_out": timed_out,
        "exit_code": exit_code,
        "estimated_cost_usd": float(run["estimated_cost_usd"]),
        "reported_cost_usd": None,
        "git_commit": git_commit(cwd),
        "approved_plan_sha256": plan_sha256,
        "inputs": input_records,
        "input_integrity": {
            "verified_after_run": True,
            "passed": not changed_inputs,
            "mutated_or_missing": changed_inputs,
        },
        "runtime": {
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "platform": platform.platform(),
        },
        "executor_isolation": isolation,
        "outputs": output_records,
        "missing_outputs": missing_outputs,
        "logs": {
            "stdout": (log_dir / "stdout.txt").relative_to(project).as_posix(),
            "stderr": (log_dir / "stderr.txt").relative_to(project).as_posix(),
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        },
        "error": error,
    }
    append_registry(registry, entry)
    (log_dir / "run.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return entry


def execute(project_slug: str, selected_run_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", project_slug):
        raise ExperimentError("Invalid project slug")
    project = PROJECTS_ROOT / project_slug
    plan_path = project / "experiments" / "plan.json"
    budget_path = project / "experiments" / "budget.json"
    plan, ceiling = approved_plan(project, plan_path, budget_path)
    plan_sha256 = sha256_file(plan_path)
    selected = set(selected_run_ids or [])
    runs = [run for run in plan["runs"] if not selected or run["run_id"] in selected]
    missing = selected - {run["run_id"] for run in runs}
    if missing:
        raise ExperimentError(f"Unknown run ids: {', '.join(sorted(missing))}")
    registry = project / "experiments" / "registry.jsonl"
    committed = prior_estimated_cost(registry)
    requested = sum(float(run["estimated_cost_usd"]) for run in runs)
    if committed + requested > ceiling:
        raise ExperimentError(
            f"Budget ceiling exceeded: prior {committed:.2f} + requested {requested:.2f} "
            f"> approved {ceiling:.2f} USD"
        )
    results: list[dict[str, Any]] = []
    for run in runs:
        results.append(run_one(project, run, registry, plan_sha256))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--run", action="append", dest="runs")
    args = parser.parse_args()
    try:
        results = execute(args.project, args.runs)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if all(item["status"] == "succeeded" for item in results) else 1
    except ExperimentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
