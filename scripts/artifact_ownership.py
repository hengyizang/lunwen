"""Control-plane ownership of executed facts, including plan-declared outputs."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

EXECUTOR_ROOTS = ("experiments/runs", "results", "data/acquisition")
EXECUTOR_FILES = {"experiments/registry.jsonl"}


def declared_outputs(root: Path) -> set[str]:
    """Include old registry outputs even if a writer proposes a different plan."""
    values: set[str] = set()
    plan = root / "experiments/plan.json"
    if plan.is_file():
        try:
            value = json.loads(plan.read_text(encoding="utf-8"))
            for run in value.get("runs", []):
                values.update(p for p in run.get("expected_outputs", []) if isinstance(p, str))
            state_path = root / "state/run.json"
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
            if state.get("stage") in {"experiment-execution", "writing-and-review", "submission-ready"}:
                values.update({"experiments/plan.json", "experiments/budget.json"})
                values.update(item["path"] for run in value.get("runs", []) for item in run.get("inputs", [])
                              if isinstance(item, dict) and isinstance(item.get("path"), str))
        except (ValueError, TypeError, AttributeError):
            pass  # A draft plan can be repaired; it grants no execution authority.
    registry = root / "experiments/registry.jsonl"
    if registry.is_file():
        try:
            for line in registry.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    values.update(p["path"] for p in entry.get("outputs", [])
                                  if isinstance(p, dict) and isinstance(p.get("path"), str))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Executor registry is invalid; control-plane inspection is required") from exc
    return {PurePosixPath(p).as_posix().casefold() for p in values}


def executor_owned(root: Path, relative: str, outputs: set[str] | None = None) -> bool:
    value = PurePosixPath(relative).as_posix().casefold()
    return (value in EXECUTOR_FILES
            or any(value == prefix or value.startswith(prefix + "/") for prefix in EXECUTOR_ROOTS)
            or value in (declared_outputs(root) if outputs is None else outputs))


def executor_snapshot(root: Path) -> dict[str, bytes]:
    outputs = declared_outputs(root)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and executor_owned(root, p.relative_to(root).as_posix(), outputs)}
