#!/usr/bin/env python3
"""Run explicitly approved experiment commands and register every attempt."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import platform
import signal
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.research_artifacts import sha as sha256_file
except ImportError:  # Direct execution from scripts/.
    from research_artifacts import sha as sha256_file


ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))
PROJECTS_ROOT = ROOT / "projects"
RUN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")
PAPER_RE = re.compile(r"^P[0-9]{2}$")
DEFAULT_EXECUTABLES = {"python", "python3", "Rscript", "julia"}
MAX_LOG_BYTES = 2 * 1024 * 1024
DEFAULT_RESOURCES = {"cpu": 2, "memory_gb": 4, "gpu": 0}
FILE_ARGUMENT_SUFFIXES = {
    ".py", ".r", ".jl", ".json", ".jsonl", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".csv", ".tsv", ".parquet", ".npy", ".npz",
    ".h5", ".hdf5", ".wav", ".txt", ".lean",
}


from scripts.paper_execution import artifact_path as experiment_path

class ExperimentError(RuntimeError):
    pass


class ProcessTreeTerminationError(ExperimentError):
    pass


def positive_finite_number(value: Any) -> bool:
    return type(value) in (int, float) and 0 < value <= sys.float_info.max


def requested_resources(run: dict[str, Any]) -> dict[str, Any]:
    """Resources belong to the existing frozen run, never to a spending grant."""
    value = run.get("resources", {})
    if not isinstance(value, dict) or set(value) - set(DEFAULT_RESOURCES):
        raise ExperimentError("resources must contain only cpu, memory_gb and gpu")
    result = {**DEFAULT_RESOURCES, **value}
    for key in ("cpu", "memory_gb"):
        amount = result[key]
        if not positive_finite_number(amount):
            raise ExperimentError(f"resources.{key} must be a finite positive number")
    memory_bytes=result["memory_gb"] * 1024**3
    if not positive_finite_number(memory_bytes) or memory_bytes < 1:
        raise ExperimentError("resources.memory_gb must represent a finite positive byte count")
    if type(result["gpu"]) is not int or result["gpu"] < 0:
        raise ExperimentError("resources.gpu must be a non-negative integer count")
    isolation = run.get("isolation", {})
    if not isinstance(isolation,dict):isolation={}
    if "resources" in run and isolation.get("kind") != "container":
        raise ExperimentError("explicit resource limits require the isolated container executor")
    if result["gpu"] and isolation.get("engine") != "docker":
        raise ExperimentError("GPU execution requires the reviewed Docker NVIDIA runtime")
    return result


def runner_capabilities(engine: str = "docker") -> dict[str, Any]:
    """Inspect this runner and its local daemon; never start or rent hardware."""
    try:cpu = float(len(os.sched_getaffinity(0))) if hasattr(os, "sched_getaffinity") else os.cpu_count()
    except OSError:cpu = os.cpu_count()
    memory = None
    try:memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):pass
    for name in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            limit = int(Path(name).read_text().strip())
            if limit > 0:memory = min(memory, limit) if memory is not None else limit
        except (OSError, ValueError):pass
    for quota_path, period_path in (
        ("/sys/fs/cgroup/cpu.max", None),
        ("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", "/sys/fs/cgroup/cpu/cpu.cfs_period_us"),
        ("/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us", "/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_period_us"),
    ):
        try:
            quota, period = (Path(quota_path).read_text().split() if period_path is None
                             else (Path(quota_path).read_text(), Path(period_path).read_text()))
            if int(quota) > 0 and int(period) > 0:
                limit = int(quota) / int(period)
                cpu = min(cpu, limit) if cpu is not None else limit
        except (OSError, ValueError):pass
    environment = {key:value for key,value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "TZ"}}
    def inspect(argv):
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=10, check=False, env=environment)
            return result.stdout.strip() if result.returncode == 0 and len(result.stdout) <= 100_000 else None
        except (OSError, ValueError, subprocess.SubprocessError):return None
    daemon = None
    if engine in {"docker", "podman"} and shutil.which(engine):
        raw = inspect([engine, "info", "--format", "{{json .}}"])
        try:daemon = json.loads(raw) if raw else None
        except (ValueError, TypeError):pass
    runtime_verified = False
    if isinstance(daemon, dict):
        host = daemon if engine == "docker" else daemon.get("host")
        if isinstance(host, dict):
            daemon_cpu = host.get("NCPU" if engine == "docker" else "cpus")
            daemon_memory = host.get("MemTotal" if engine == "docker" else "memTotal")
            runtime_verified = (positive_finite_number(daemon_cpu)
                                and type(daemon_memory) is int and daemon_memory > 0)
            if runtime_verified:
                cpu = min(cpu, daemon_cpu) if cpu is not None else daemon_cpu
                memory = min(memory, daemon_memory) if memory is not None else daemon_memory
    # Podman's resource controls are supported, but no unverified GPU/CDI device
    # mount is inferred from the mere presence of a graphics card.
    gpu_count = None
    if shutil.which("nvidia-smi"):
        value = inspect(["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"])
        if value is not None:
            identifiers = [line.strip() for line in value.splitlines() if line.strip()]
            if all(re.fullmatch(r"(?:GPU|MIG)-[A-Za-z0-9/-]+",item) for item in identifiers):gpu_count=len(set(identifiers))
    runtimes=daemon.get("Runtimes",{}) if isinstance(daemon,dict) else {}
    gpu_runtime_verified = engine == "docker" and runtime_verified and isinstance(runtimes,dict) and "nvidia" in runtimes
    # Rootless Docker can report host capacity while discarding --cpus/--memory.
    # Presence of a daemon or sufficient host RAM does not establish cgroup
    # enforcement. Unknown support is never promoted to a verified limit.
    resource_limits_verified = (runtime_verified and all(daemon.get(key) is True for key in
                                ("MemoryLimit", "CpuCfsQuota", "CpuCfsPeriod"))) if engine == "docker" else None
    return {"cpu":cpu,"memory_gb":memory / 1024**3 if memory is not None else None,
            "gpu":gpu_count,"engine":engine,"container_runtime_verified":runtime_verified,
            "container_resource_limits_verified":resource_limits_verified,
            "gpu_runtime_verified":gpu_runtime_verified,"observed_at":now(),
            "hardware_provisioned":False,"new_spending_authority":False}


def resource_errors(run: dict[str, Any], capabilities: dict[str, Any] | None = None) -> list[str]:
    try:requested = requested_resources(run)
    except ExperimentError as exc:return [str(exc)]
    if not isinstance(run.get("isolation"),dict) or run["isolation"].get("kind") != "container":return []
    actual = capabilities if capabilities is not None else runner_capabilities(run["isolation"]["engine"])
    errors=[]
    if actual.get("engine") != run["isolation"].get("engine"):
        errors.append("resource observation belongs to a different container engine; inspect the run's actual executor")
    if actual.get("container_runtime_verified") is not True:
        errors.append("container runtime capacity cannot be verified; restore the local Docker/Podman daemon before starting the frozen run")
    if run["isolation"].get("engine") == "docker" and actual.get("container_resource_limits_verified") is not True:
        errors.append("Docker CPU/memory limits are unsupported or unverified; use a daemon with memory and CPU CFS cgroups before starting the frozen run")
    for key in ("cpu", "memory_gb"):
        available=actual.get(key)
        if not positive_finite_number(available):
            errors.append(f"runner {key} capacity is unknown; inspect the controlled runner before execution")
        elif requested[key] > available:
            errors.append(f"run requests {requested[key]:g} {key}, but the controlled runner exposes {available:g}; use a capable runner or revise the protocol before a new G3 freeze")
    if requested["gpu"] and (actual.get("gpu_runtime_verified") is not True or type(actual.get("gpu")) is not int or actual["gpu"] < requested["gpu"]):
        errors.append(f"run requests {requested['gpu']} GPU(s); a verified NVIDIA Docker runtime with that many visible devices is required; no GPU service was provisioned")
    return errors


def allowed_executable(value: str) -> bool:
    name = Path(value).name
    if name.lower().endswith(".exe"):
        name = name[:-4]
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
    from scripts.research_phase import plan_errors
    errors: list[str] = plan_errors(plan)
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
        if type(timeout) is not int or not 1 <= timeout <= 7 * 24 * 60 * 60:
            errors.append(f"{prefix}.timeout_seconds must be between 1 and 604800")
        estimate = run.get("estimated_cost_usd")
        if not isinstance(estimate, (int, float)) or isinstance(estimate, bool) or not math.isfinite(estimate) or estimate < 0:
            errors.append(f"{prefix}.estimated_cost_usd must be non-negative")
        isolation = run.get("isolation")
        if not isinstance(isolation, dict) or isolation.get("kind") not in {"host", "git_worktree", "container"}:
            errors.append(f"{prefix}.isolation must select host, git_worktree or container")
        elif isolation.get("kind") == "container":
            if isolation.get("engine") not in {"docker", "podman"}:
                errors.append(f"{prefix}.isolation.engine must be docker or podman")
            if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", str(isolation.get("image", ""))):
                errors.append(f"{prefix}.isolation.image must be pinned by sha256 digest")
        try:requested_resources(run)
        except ExperimentError as exc:errors.append(f"{prefix}.{exc}")
        if "runtime" in run:
            from scripts.study_environment import definition
            runtime = run["runtime"]
            if (not isinstance(runtime, dict) or runtime.get("profile") not in {"meta_analysis", "theory"}
                    or set(runtime) != {"profile", "definition_sha256", "base_image", "environment_sha256"}
                    or runtime.get("definition_sha256") != definition(runtime["profile"])
                    or not re.fullmatch(r"[0-9a-f]{64}", str(runtime.get("environment_sha256", "")))
                    or not isinstance(isolation, dict) or runtime.get("base_image") != isolation.get("image")):
                errors.append(f"{prefix}.runtime must match the exact reviewed environment")
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
    earlier: dict[str, str] = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        parents = run.get("depends_on", [])
        if (not isinstance(parents, list) or any(not isinstance(p, str) for p in parents)
                or len(set(parents)) != len(parents)):
            errors.append("depends_on must be a unique string array")
        else:
            for parent in parents:
                if parent not in earlier or earlier[parent] != run.get("paper_id"):
                    errors.append("dependencies must name earlier runs of the same paper")
        if isinstance(run.get("run_id"), str):
            earlier[run["run_id"]] = run.get("paper_id")
    output_owners = {}
    for run in runs:
        if not isinstance(run, dict):
            continue
        for output in run.get("expected_outputs", []) if isinstance(run.get("expected_outputs"), list) else []:
            if not isinstance(output, str):
                continue
            if any(c in output for c in (",", ":", "\\")):
                errors.append("output paths cannot contain container mount delimiters")
            if output in output_owners and output_owners[output] != run.get("run_id"):
                errors.append("different runs must use distinct output paths to preserve earlier results")
            output_owners[output] = run.get("run_id")
        for item in run.get("inputs", []) if isinstance(run.get("inputs"), list) else []:
            if isinstance(item, dict) and any(c in str(item.get("path", "")) for c in (",", ":", "\\")):
                errors.append("input paths cannot contain container mount delimiters")
    return errors


def budget_ceiling(budget: dict[str, Any]) -> float:
    if budget.get("status") != "ready_for_review":
        raise ExperimentError("experiments/budget.json status must be ready_for_review")
    value = budget.get("hard_ceiling_usd")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ExperimentError("budget hard_ceiling_usd must be non-negative")
    return float(value)


def compute_budget_authority(project: Path, budget: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Check planned costs against the existing project total, without paid reviews.

    The frozen budget remains a protocol input, but a smaller per-plan value
    is informational. It cannot impose another spending approval boundary.
    """
    budget_ceiling(budget)
    authority = _compute_total_authority(project)
    ceiling = authority["cloud_compute_budget_usd"]
    if authority["cash_budget_usd"] is not None:
        ceiling = min(ceiling, authority["cash_budget_usd"])
    errors = validate_plan(plan)
    if errors:
        raise ExperimentError("; ".join(errors))
    if sum(float(run["estimated_cost_usd"]) for run in plan["runs"]) > ceiling:
        raise ExperimentError("planned experiment estimates exceed the project total compute or cash USD ceiling")
    return authority


def _compute_total_authority(project: Path) -> dict[str, Any]:
    constraints_path = resolve_inside(compute_project(project), "intake/constraints.json", "compute total")
    constraints = read_json(constraints_path)
    owner_ceiling = constraints.get("cloud_compute_budget_usd")
    cash_ceiling = constraints.get("cash_budget_usd")
    for name, value in (("cloud_compute_budget_usd", owner_ceiling), ("cash_budget_usd", cash_ceiling)):
        if name == "cash_budget_usd" and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ExperimentError("owner " + name + " must be a finite non-negative USD ceiling")
    return {"constraints_sha256": sha256_file(constraints_path), "actor": "project-total-cost-control",
            "cloud_compute_budget_usd": owner_ceiling, "cash_budget_usd": cash_ceiling}


def compute_project(project: Path) -> Path:
    """Use the parent total for the existing supplemental study layout."""
    if len(project.parents) >= 5:
        root = project.parents[4]
        if re.fullmatch(r"experiments/supplemental/P[0-9]{2}/[RI][0-9]{3}/s[0-9]{3}", project.relative_to(root).as_posix()):
            return root
    return project


def project_compute_ceiling(project: Path, budget: dict[str, Any]) -> float:
    budget_ceiling(budget)
    root = compute_project(project)
    if not (root / "intake/constraints.json").is_file():
        # Existing sealed projects without intake retain their one recorded
        # total ceiling; absence of a new per-plan value never means unlimited.
        from scripts.paper_execution import enabled
        if enabled(root):
            # The retained master is the legacy total authority. A new paper's
            # editable budget copy cannot increase it without owner intake.
            authority_budget = read_json(root / "experiments/budget.json")
        else:
            authority_budget = read_json(experiment_path(root, 'experiments/budget.json')) if root != project else budget
        ceiling = budget_ceiling(authority_budget)
        from scripts.primary_recovery import histories
        previous = histories(root)
        return min([ceiling, *(float(row["compute_ceiling_usd"]) for row in previous)])
    authority = _compute_total_authority(root)
    values = [authority["cloud_compute_budget_usd"]]
    if authority["cash_budget_usd"] is not None:
        values.append(authority["cash_budget_usd"])
    return float(min(values))


def approved_plan(project: Path, plan_path: Path, budget_path: Path) -> tuple[dict[str, Any], float]:
    state = read_json(project / "state" / "run.json")
    from scripts.scientific_scope import validate as scope_errors
    errors = scope_errors(project, "G4")
    if errors:
        raise ExperimentError("; ".join(errors))
    if (
        state.get("stage") != "experiment-execution"
        or state.get("gate") != "G4"
        or state.get("status") != "awaiting_work"
    ):
        raise ExperimentError(
            "Experiments may run only during the open G4 experiment-execution stage"
        )
    from scripts.paper_execution import approval as paper_approval, plan_errors
    approval = paper_approval(project, "G3")
    if not approval:
        raise ExperimentError("G3 has no recorded checked protocol seal")
    expected_plan = approval.get("experiment_plan_sha256")
    expected_budget = approval.get("experiment_budget_sha256")
    if not expected_plan or not expected_budget:
        raise ExperimentError("G3 seal predates the executable plan contract; rerun the current G3 checks and sealing")
    if sha256_file(plan_path) != expected_plan or sha256_file(budget_path) != expected_budget:
        raise ExperimentError("Experiment plan or budget changed after G3 approval")
    plan = read_json(plan_path)
    from scripts.research_phase import exposure_errors
    errors = validate_plan(plan) + plan_errors(project, plan) + exposure_errors(project, plan)
    from scripts.research_phase import exploratory, design_errors
    if exploratory(project):
        errors.extend(design_errors(project))
    if errors:
        raise ExperimentError("; ".join(errors))
    budget = read_json(budget_path)
    ceiling = project_compute_ceiling(project, budget)
    frozen = approval.get("frozen_protocol_sha256")
    required = {f"papers/{run['paper_id']}/preregistration.json" for run in plan["runs"]}
    if not isinstance(frozen, dict) or not required <= set(frozen):
        raise ExperimentError("G3 seal has no frozen protocol hashes; rerun the current G3 checks and sealing")
    for relative in sorted(required):
        path = resolve_inside(project, relative, "frozen protocol")
        if not path.is_file() or sha256_file(path) != frozen[relative]:
            raise ExperimentError("Frozen protocol changed after G3 approval")
        protocol = read_json(path)
        files = protocol.get("files")
        if protocol.get("status") != "frozen" or not isinstance(files, list) or not files:
            raise ExperimentError("Frozen protocol has no locked inputs")
        for item in files:
            locked = resolve_inside(project, item["path"], "preregistered input")
            if not locked.is_file() or sha256_file(locked) != item.get("sha256"):
                raise ExperimentError("Preregistered input changed after G3 approval")
    from scripts.primary_recovery import gate_errors
    recovery_errors = gate_errors(project, "G4")
    if recovery_errors:
        raise ExperimentError("; ".join(recovery_errors))
    from scripts.empirical_workflow import preflight_run
    for run in plan["runs"]:
        try:
            preflight_run(project, run)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ExperimentError("empirical input preflight failed: " + str(exc)) from exc
    return plan, ceiling


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


def container_user() -> str:
    """Use the cloud runner's file owner without restoring DAC override powers."""
    if not hasattr(os, "getuid") or not hasattr(os, "getgid"):
        raise ExperimentError("container execution requires a POSIX cloud runner")
    return f"{os.getuid()}:{os.getgid()}"


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
        isolation["engine"], "run", "--rm", "--user", container_user(), "--network=none", "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=512m", "--security-opt", "no-new-privileges",
        "--cap-drop=ALL", "--pids-limit=256",
        "-v", f"{project.resolve()}:/workspace:ro", "-w", workdir,
    ]
    resources=requested_resources(run)
    memory=f"{resources['memory_gb']:g}g" if float(resources["memory_gb"]).is_integer() else str(int(resources["memory_gb"] * 1024**3))
    command.extend([f"--cpus={resources['cpu']:g}",f"--memory={memory}"])
    if resources["gpu"]:command.extend(["--gpus",f"count={resources['gpu']}"])
    for item in run["inputs"]:
        source = resolve_inside(project, item["path"], f"{run['run_id']}.inputs")
        target = f"/workspace/{Path(item['path']).as_posix()}"
        command.extend(["--mount", f"type=bind,src={source},dst={target},readonly"])
    for value in run["expected_outputs"]:
        source = resolve_inside(project, value, f"{run['run_id']}.expected_outputs")
        if "," in str(source) or ":" in value or "\\" in value:
            raise ExperimentError("container output path contains mount delimiters")
        source.parent.mkdir(parents=True, exist_ok=True)
        # Only named output files are writable; the model-authored script cannot
        # alter approvals, budgets, the registry, code or another result file.
        source.touch(exist_ok=True)
        command.extend(["--mount", f"type=bind,src={source},dst=/workspace/{Path(value).as_posix()}"])
    for key in ("RESEARCH_OS_RUN_ID", "RESEARCH_OS_SEED", "PYTHONHASHSEED"):
        command.extend(["-e", f"{key}={environment[key]}"])
    if run.get("runtime"):
        from scripts.study_environment import prepare
        binding, vendor = prepare(run["runtime"]["profile"], run["runtime"])
        if binding["base_image"] != isolation["image"]:
            raise ExperimentError("approved runtime base image differs from the executor image")
        command.extend(["--mount", f"type=bind,src={vendor.resolve()},dst=/opt/research-runtime,readonly"])
        if binding["profile"] == "meta_analysis":
            command.extend(["-e", "PYTHONPATH=/opt/research-runtime", "-e", "PYTHONDONTWRITEBYTECODE=1"])
        else:
            command.extend(["-e", "PATH=/opt/research-runtime/bin:/usr/local/bin:/usr/bin:/bin"])
    command.extend([isolation["image"], *run["argv"]])
    return command, project, environment


def read_capped(path: Path, limit: int = MAX_LOG_BYTES) -> tuple[str, bool]:
    with path.open("rb") as handle:
        payload = handle.read(limit + 1)
    truncated = len(payload) > limit
    return payload[:limit].decode("utf-8", errors="replace"), truncated


def read_capped_stream(handle, limit: int = MAX_LOG_BYTES) -> tuple[str, bool]:
    handle.seek(0)
    payload = handle.read(limit + 1)
    return payload[:limit].decode("utf-8", errors="replace"), len(payload) > limit


class WindowsProcessJob:
    def __init__(self, process: subprocess.Popen, *, suspended: bool = False):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ProcessTreeTerminationError("could not create Windows job")
        if not kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            self.close()
            raise ProcessTreeTerminationError("could not assign process to Windows job")
        if suspended:
            try:
                self._resume_primary_thread(process.pid)
            except Exception:
                try:
                    self.terminate()
                finally:
                    self.close()
                raise

    def _resume_primary_thread(self, process_id: int) -> None:
        """Resume only after job assignment, before any experiment code runs.

        Popen closes the initial thread handle. Toolhelp supplies that thread's
        ID while CREATE_SUSPENDED guarantees it has not started experiment code.
        https://learn.microsoft.com/en-us/windows/win32/procthread/thread-walking
        """
        import ctypes
        from ctypes import wintypes

        class ThreadEntry(ctypes.Structure):
            _fields_ = [(name, kind) for name, kind in (
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD))]

        kernel = self.kernel
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        for name in ("Thread32First", "Thread32Next"):
            operation = getattr(kernel, name)
            operation.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
            operation.restype = wintypes.BOOL
        kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenThread.restype = wintypes.HANDLE
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD
        snapshot = kernel.CreateToolhelp32Snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise ProcessTreeTerminationError("could not inspect the suspended experiment thread")
        try:
            entry = ThreadEntry()
            entry.dwSize = ctypes.sizeof(entry)
            available = kernel.Thread32First(snapshot, ctypes.byref(entry))
            thread_ids = []
            while available:
                if entry.th32OwnerProcessID == process_id:
                    thread_ids.append(entry.th32ThreadID)
                entry.dwSize = ctypes.sizeof(entry)
                available = kernel.Thread32Next(snapshot, ctypes.byref(entry))
            if ctypes.get_last_error() != 18 or len(thread_ids) != 1:  # ERROR_NO_MORE_FILES
                raise ProcessTreeTerminationError("could not identify one suspended experiment thread")
            thread = kernel.OpenThread(0x0002, False, thread_ids[0])  # THREAD_SUSPEND_RESUME
            if not thread:
                raise ProcessTreeTerminationError("could not open the suspended experiment thread")
            try:
                if kernel.ResumeThread(thread) != 1:
                    raise ProcessTreeTerminationError("could not resume the assigned experiment thread")
            finally:
                kernel.CloseHandle(thread)
        finally:
            kernel.CloseHandle(snapshot)

    def terminate(self) -> None:
        if not self.kernel.TerminateJobObject(self.handle, 1):
            raise ProcessTreeTerminationError("could not terminate the Windows job")

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def terminate_process_tree(process: subprocess.Popen, job: WindowsProcessJob | None = None) -> None:
    if os.name == "nt":
        if job is not None:
            job.terminate()
            return
        # taskkill /T targets descendants before the parent, including children
        # that would survive process.kill(). Do not invoke a command shell.
        try:
            result = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, check=False, timeout=15)
        except (OSError, subprocess.SubprocessError) as exc:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise ProcessTreeTerminationError("could not terminate the complete Windows process tree") from exc
        if result.returncode:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise ProcessTreeTerminationError("could not terminate the complete Windows process tree")
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as exc:
            if process.poll() is None:
                process.kill()
                process.wait()
            raise ProcessTreeTerminationError("could not terminate the complete process group") from exc


def append_registry(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def accounted_run_cost(entry: dict[str, Any]) -> float:
    """Charge every finished attempt conservatively; never invent actual billing."""
    estimate = entry.get("estimated_cost_usd")
    actual = entry.get("reported_cost_usd")
    if type(estimate) not in (int, float) or not math.isfinite(estimate) or estimate < 0:
        raise ExperimentError("experiment ledger needs finite non-negative estimated costs")
    if actual is not None and (type(actual) not in (int, float) or not math.isfinite(actual) or actual < 0):
        raise ExperimentError("experiment ledger has invalid reported costs")
    return max(float(estimate), float(actual) if actual is not None else 0.0)


def prior_estimated_cost(registry: Path) -> float:
    if not registry.is_file():
        return 0.0
    total = 0.0
    for line in registry.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExperimentError("experiment cost ledger contains invalid JSON") from exc
        total += accounted_run_cost(entry)
    return total


def verify_dependencies(project: Path, run: dict, registry: Path, plan_sha256: str) -> None:
    """Check immutable successful receipts before any dependent process starts."""
    parents = run.get("depends_on", [])
    if not parents:
        return
    records = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()
               if line.strip()] if registry.is_file() else []
    plan = read_json(experiment_path(project, 'experiments/plan.json'))
    planned = {r["run_id"]: r for r in plan["runs"]}
    pending, visited = list(parents), set()
    while pending:
        parent = pending.pop()
        if parent in visited:
            continue
        visited.add(parent)
        if parent not in planned or planned[parent].get("paper_id") != run["paper_id"]:
            raise ExperimentError("Dependency is absent from the approved same-paper plan")
        pending.extend(planned[parent].get("depends_on", []))
        from scripts.primary_recovery import selected_attempt
        try:
            receipt = selected_attempt(project, parent, records, plan_sha256=plan_sha256)
        except ValueError as exc:
            raise ExperimentError(f"Dependency {parent}: {exc}") from exc
        if (receipt.get("status") != "succeeded" or receipt.get("paper_id") != run["paper_id"]
                or receipt.get("approved_plan_sha256") != plan_sha256
                or not receipt.get("input_integrity", {}).get("passed")):
            raise ExperimentError(f"Dependency {parent} did not succeed under the approved plan")
        path = resolve_inside(project, f"experiments/runs/{receipt['attempt_id']}/run.json", "dependency receipt")
        if not path.is_file() or read_json(path) != receipt or not receipt.get("outputs"):
            raise ExperimentError(f"Dependency {parent} has no matching executor receipt")
        for item in receipt["outputs"]:
            path = resolve_inside(project, item["path"], "dependency output")
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                raise ExperimentError(f"Dependency {parent} output changed")


def preflight_run(project: Path, run: dict[str, Any], registry: Path, plan_sha256: str, *, include_resources: bool = False):
    """Reject an unstartable attempt before arming a cost reservation."""
    from scripts.primary_recovery import require_next_attempt, records
    try:
        require_next_attempt(project, run["run_id"], records(project), plan_sha256)
    except ValueError as exc:
        raise ExperimentError(str(exc)) from exc
    verify_dependencies(project, run, registry, plan_sha256)
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
    container=run.get("isolation",{}).get("kind")=="container"
    actual=runner_capabilities(run["isolation"]["engine"]) if container else None
    errors=resource_errors(run,actual)
    if os.environ.get("GITHUB_ACTIONS")=="true" or os.environ.get("DR_OS_CLOUD_EXECUTOR")=="1":
        from scripts.cloud_runtime import execution_window
        window=execution_window()
        if run["timeout_seconds"] > window["max_run_timeout_seconds"]:
            errors.append(f"run timeout {run['timeout_seconds']}s exceeds the current cloud execution window of {window['max_run_timeout_seconds']}s; split the prospective run or use a controlled runner/workflow with a sufficient actual deadline")
    if errors:raise ExperimentError("; ".join(errors))
    allocation={"requested":requested_resources(run),"observed":actual,"container_limits_configured":container,
                "actual_resource_use_measured":False}
    return (cwd,outputs,input_records,allocation) if include_resources else (cwd,outputs,input_records)


def run_one(
    project: Path, run: dict[str, Any], registry: Path, plan_sha256: str
) -> dict[str, Any]:
    # Recheck immediately before execution as inputs may change while a remote
    # reservation is being persisted.
    cwd, outputs, input_records, allocation = preflight_run(project, run, registry, plan_sha256, include_resources=True)
    run_id = run["run_id"]
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
    previous_outputs = []
    for output in outputs:
        if output.is_file():
            old_hash = sha256_file(output)
            snapshot = log_dir / "previous-outputs" / (old_hash + output.suffix)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(output.read_bytes())
            previous_outputs.append({"path": output.relative_to(project).as_posix(),
                                     "snapshot_path": snapshot.relative_to(project).as_posix(), "sha256": old_hash})
            output.unlink()
    started = now()
    monotonic_start = time.monotonic()
    status = "failed"
    exit_code: int | None = None
    error: str | None = None
    timed_out = False
    launch = {"process_started": False, "failure_kind": None, "os_error_errno": None}
    environment = safe_environment(run_id, run["seed"])
    isolation = isolation_record(project, cwd, run["isolation"], attempt_id)
    if run.get("runtime"):
        isolation["reviewed_runtime"] = run["runtime"]
    with tempfile.NamedTemporaryFile("w+b") as stdout, tempfile.NamedTemporaryFile("w+b") as stderr:
        try:
            command, execution_cwd, execution_environment = execution_command(
                project, cwd, run, environment
            )
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
                    creationflags=0x00000004 if os.name == "nt" else 0,  # CREATE_SUSPENDED
                )
            except OSError as exc:
                launch.update(failure_kind="process_launch_oserror", os_error_errno=exc.errno)
                raise
            launch["process_started"] = True
            job = None
            try:
                if os.name == "nt":
                    try:
                        job = WindowsProcessJob(process, suspended=True)
                    except ProcessTreeTerminationError:
                        process.kill()
                        process.wait()
                        raise
                try:
                    exit_code = process.wait(timeout=run["timeout_seconds"])
                except subprocess.TimeoutExpired as exc:
                    terminate_process_tree(process, job)
                    process.wait()
                    status = "timed_out"
                    timed_out = True
                    error = str(exc)
                else:
                    status = "succeeded" if exit_code == 0 else "failed"
            finally:
                if job is not None:
                    try:
                        # A parent exiting successfully must not leave workers
                        # changing files after the executor seals its receipt.
                        job.terminate()
                    finally:
                        job.close()
        except ProcessTreeTerminationError:
            raise
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            status = "failed"
            error = str(exc)
        stdout.flush()
        stderr.flush()
        stdout_text, stdout_truncated = read_capped_stream(stdout)
        stderr_text, stderr_truncated = read_capped_stream(stderr)
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
        if output.is_file() and output.stat().st_size > 0:
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
        "launch": launch,
        "exit_code": exit_code,
        "estimated_cost_usd": float(run["estimated_cost_usd"]),
        "reported_cost_usd": None,
        "cost_accounting": {"basis": "conservative_plan_estimate", "actual_cost_known": False,
                            "accounted_cost_usd": float(run["estimated_cost_usd"])},
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
        "resource_allocation": allocation,
        "outputs": output_records,
        "missing_outputs": missing_outputs,
        "preexisting_output_snapshots": previous_outputs,
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


def execute(project_slug: str, selected_run_ids: Iterable[str] | None = None,
            *, project_root: Path | None = None) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", project_slug):
        raise ExperimentError("Invalid project slug")
    project = project_root or PROJECTS_ROOT / project_slug
    if project.name != project_slug or project.is_symlink():
        raise ExperimentError("project root does not match the requested slug")
    # Boundary helpers return resolved paths; keep their project base absolute too.
    project = project.resolve()
    lease = project / "state" / "experiment-execution-lease.json"
    try:
        descriptor = os.open(lease, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ExperimentError("another execution or an unresolved interrupted execution exists; reconcile its lease before continuing") from exc
    armed = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"status": "checking", "started_at": now()}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        return _execute_locked(project, selected_run_ids, lease)
    finally:
        # An armed lease survives exceptions and process termination. Its cost
        # may be unknown, so another run must not silently reuse the budget.
        if lease.exists():
            try:
                armed = read_json(lease).get("status") in {"running", "completed"}
            except ExperimentError:
                armed = True
            if not armed:
                lease.unlink()


def _execute_locked(project: Path, selected_run_ids: Iterable[str] | None, lease: Path) -> list[dict[str, Any]]:
    plan_path = experiment_path(project, 'experiments/plan.json')
    budget_path = experiment_path(project, 'experiments/budget.json')
    plan, ceiling = approved_plan(project, plan_path, budget_path)
    plan_sha256 = sha256_file(plan_path)
    selected = set(selected_run_ids or [])
    runs = [run for run in plan["runs"] if not selected or run["run_id"] in selected]
    missing = selected - {run["run_id"] for run in runs}
    if missing:
        raise ExperimentError(f"Unknown run ids: {', '.join(sorted(missing))}")
    registry = experiment_path(project, 'experiments/registry.jsonl')
    from scripts.supplemental_experiments import all_compute_cost
    committed = all_compute_cost(compute_project(project))
    requested = sum(float(run["estimated_cost_usd"]) for run in runs)
    if committed + requested > ceiling:
        raise ExperimentError(
            f"Budget ceiling exceeded: prior {committed:.2f} + requested {requested:.2f} "
            f"> approved {ceiling:.2f} USD"
        )
    results: list[dict[str, Any]] = []
    from scripts.cloud_checkpoint import CheckpointError, sync_experiment_reservation
    for run in runs:
        preflight_run(project, run, registry, plan_sha256)
        with lease.open("w", encoding="utf-8") as handle:
            json.dump({"status": "running", "run_id": run["run_id"],
                       "estimated_cost_usd": run["estimated_cost_usd"],
                       "approved_plan_sha256": plan_sha256, "started_at": now()}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            sync_experiment_reservation(project, completed=False)
        except CheckpointError as exc:
            raise ExperimentError(str(exc)) from exc
        entry = run_one(project, run, registry, plan_sha256)
        results.append(entry)
        with lease.open("w", encoding="utf-8") as handle:
            receipt = project / "experiments" / "runs" / entry["attempt_id"] / "run.json"
            json.dump({"status": "completed", "run_id": run["run_id"],
                       "attempt_id": entry["attempt_id"],
                       "estimated_cost_usd": run["estimated_cost_usd"],
                       "approved_plan_sha256": plan_sha256,
                       "receipt_sha256": sha256_file(receipt),
                       "registry_sha256": sha256_file(registry)}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            sync_experiment_reservation(project, completed=True)
        except CheckpointError as exc:
            raise ExperimentError(str(exc)) from exc
        with lease.open("w", encoding="utf-8") as handle:
            json.dump({"status": "checking"}, handle)
            handle.flush()
            os.fsync(handle.fileno())
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
