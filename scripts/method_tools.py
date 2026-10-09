"""Pinned paper-method contracts. Execution always delegates to experiment_runner."""
from __future__ import annotations

import json
import re
import math
from pathlib import Path
from scripts.research_artifacts import path_in, read, sha, write, record, bound_source

TEST_KINDS = {"original_example", "unseen_input", "invalid_input", "reference_comparison"}


def qualification(project: Path, tool: dict, plan: dict) -> dict:
    registry_path = project / "experiments/registry.jsonl"
    if not registry_path.is_file():
        return {"status": "pending_cloud_validation", "errors": []}
    registry = [json.loads(line) for line in registry_path.read_text().splitlines() if line.strip()]
    from scripts.results_validation import validate_registry
    errors = validate_registry(project, plan, registry)
    receipts = []
    for test in tool["validation"]:
        try:
            attempts = [r for r in registry if r["run_id"] == test["run_id"]]
            if not attempts:
                raise ValueError("validation run has not executed")
            # A later successful retry never erases a failed validation attempt.
            if any(r["status"] != "succeeded" for r in attempts):
                raise ValueError("failed validation attempt needs scientific disposition before qualification")
            attempt = attempts[-1]
            output = next(r for r in attempt["outputs"] if r["path"] == test["output"])
            receipt_path = path_in(project, output["path"])
            if sha(receipt_path) != output["sha256"]:
                raise ValueError("validation output hash changed")
            payload = read(receipt_path)
            if payload.get("method_tool_id") != tool["id"] or payload.get("validation_kind") != test["kind"] or payload.get("passed") is not True:
                raise ValueError("validation output has wrong identity or did not pass")
            checks = payload.get("checks", [])
            if not isinstance(checks, list) or not checks:
                raise ValueError("validation output needs actual assertions, not a bare pass flag")
            reference = read(path_in(project, test["reference"]["path"])) if test["kind"] == "reference_comparison" else None
            for check in checks:
                observed, expected = check["actual"], check["expected"]
                if reference is not None:
                    expected = reference["expected_values"][check["name"]]
                    tolerance = test["absolute_tolerance"]
                else:
                    tolerance = 0
                if isinstance(observed, (int, float)) and not isinstance(observed, bool):
                    if not isinstance(expected, (int, float)) or isinstance(expected, bool) or not math.isfinite(observed) or not math.isfinite(expected) or abs(observed - expected) > tolerance:
                        raise ValueError("observed validation value does not meet the frozen reference tolerance")
                elif observed != expected:
                    raise ValueError("validation assertion differs")
            receipts.append({"kind": test["kind"], "attempt_id": attempt["attempt_id"], "output": output})
        except (KeyError, ValueError, TypeError, OSError, StopIteration) as exc:
            errors.append(f"{test['kind']}: {exc}")
    return {"status": "cloud_checks_passed" if not errors else "pending_cloud_validation", "errors": errors,
            "receipts": receipts, "scientific_applicability_verified": False, "human_review_required": True}


def inspect(project: Path) -> dict:
    manifest = read(path_in(project, "program/method-tools.json"))
    tools, errors, seen = [], [], set()
    plan = read(path_in(project, "experiments/plan.json"))
    planned = {r["run_id"]: r for r in plan.get("runs", [])}
    for tool in manifest.get("tools", []):
        try:
            identifier = tool["id"]
            if not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", identifier) or identifier in seen:
                raise ValueError("method tool needs a unique safe ID")
            seen.add(identifier)
            source = tool["source"]
            if not re.fullmatch(r"[0-9a-f]{40}", source.get("commit", "")) or not str(source.get("repository", "")).startswith("https://github.com/"):
                raise ValueError("method source must be a repository pinned to a full commit")
            if not str(source.get("paper_url", "")).startswith("https://") or not tool.get("applicability") or not tool.get("limitations"):
                raise ValueError("method needs a paper source, applicability and limitations")
            licence = bound_source(project, tool["license"])
            entry = bound_source(project, tool["entrypoint"])
            if not isinstance(tool.get("run_ids"), list) or not tool["run_ids"] or not set(tool["run_ids"]).issubset(planned):
                raise ValueError("method run IDs must exist in the frozen experiment plan")
            for run_id in tool["run_ids"]:
                run = planned[run_id]
                inputs = {i["path"]: i["sha256"] for i in run.get("inputs", [])}
                if inputs.get(entry["path"]) != entry["sha256"] or entry["path"] not in run["argv"]:
                    raise ValueError("method entrypoint must be a pinned input and explicit approved command argument")
            tests = tool.get("validation", [])
            if not isinstance(tests, list) or {t.get("kind") for t in tests} != TEST_KINDS:
                raise ValueError("method requires original, unseen, invalid and independent reference validation plans")
            for test in tests:
                if test.get("run_id") not in tool["run_ids"] or not test.get("success_rule") or test.get("output") not in planned[test["run_id"]].get("expected_outputs", []):
                    raise ValueError("method validation must bind a planned run and a prespecified success rule")
                if test["kind"] == "reference_comparison":
                    bound_source(project, test["reference"])
                    if not isinstance(test.get("absolute_tolerance"), (int, float)) or isinstance(test["absolute_tolerance"], bool) or test["absolute_tolerance"] < 0 or not test.get("tolerance_rationale"):
                        raise ValueError("reference comparison needs a justified non-negative absolute tolerance")
            tools.append({**tool, "license": licence, "entrypoint": entry,
                          "qualification": qualification(project, tool, plan), "scientific_completion_verified": False})
        except (KeyError, ValueError, TypeError, OSError) as exc:
            errors.append(str(exc))
    return {"schema_version": "1.0", "tools": tools, "errors": errors,
            "status": "contract_ready" if not errors else "blocked", "execution_started": False,
            "scientific_completion_verified": False}


def refresh(project: Path) -> dict:
    value = inspect(project)
    output = project / "reports/method-tools.json"
    write(output, value)
    record(project, [output], "scripts/method_tools.py")
    return value


def execute(project: Path, identifier: str, run_ids: list[str] | None = None):
    report = inspect(project)
    if report["errors"]:
        raise ValueError("method contract is blocked: " + "; ".join(report["errors"]))
    tool = next((item for item in report["tools"] if item["id"] == identifier), None)
    if tool is None:
        raise ValueError("unknown method tool")
    selected = run_ids if run_ids is not None else tool["run_ids"]
    if not selected or not set(selected).issubset(tool["run_ids"]):
        raise ValueError("method execution cannot request undeclared runs")
    from scripts.experiment_runner import execute as run_approved
    # The existing runner enforces cloud isolation, G3 hashes, cumulative compute
    # budget, dependencies, immutable inputs, logs and retention of every attempt.
    return run_approved(project.name, selected, project_root=project)
