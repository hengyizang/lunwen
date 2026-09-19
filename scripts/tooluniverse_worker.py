#!/usr/bin/env python3
"""Narrow subprocess entry point for one ToolUniverse dictionary-API call."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any


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
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"name", "arguments"}:
        raise ValueError("request must contain exactly name and arguments")
    if not isinstance(value["name"], str) or not isinstance(value["arguments"], dict):
        raise ValueError("request name must be a string and arguments must be an object")
    return value


def execute(request: dict[str, Any]) -> Any:
    from tooluniverse import ToolUniverse

    universe = ToolUniverse()
    universe.load_tools(include_tools=[request["name"]])
    return universe.run(request)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: tooluniverse_worker.py REQUEST.json", file=sys.stderr)
        return 2
    try:
        request = read_request(Path(arguments[0]))
        # Keep library progress messages out of the machine-readable stdout.
        with contextlib.redirect_stdout(sys.stderr):
            result = execute(request)
        print(
            json.dumps(
                {"tool": request["name"], "result": result},
                ensure_ascii=False,
                sort_keys=True,
                default=json_default,
            )
        )
        return 0
    except Exception as exc:
        print(f"ToolUniverse execution failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
