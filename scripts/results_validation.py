#!/usr/bin/env python3
"""Validate G4 experiment attempts and claim-to-evidence traceability."""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any


STATUS_VALUES = {"succeeded", "failed", "timed_out"}
SUPPORT_VALUES = {"supported", "partially_supported", "not_supported", "contradicted"}
CLAIM_COLUMNS = {
    "claim_id", "paper_id", "claim", "evidence_ids", "analysis_ids",
    "support", "uncertainty", "status",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(project: Path, value: Any, field: str, errors: list[str]) -> Path | None:
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
        errors.append(f"{field} must be a non-empty project-relative path")
        return None
    target = (project / value).resolve()
    root = project.resolve()
    if target == root or root not in target.parents:
        errors.append(f"{field} escapes the project directory")
        return None
    return target


def validate_registry(
    project: Path, plan: dict[str, Any], registry: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    run_values = plan.get("runs")
    if not isinstance(run_values, list):
        return ["approved plan runs must be an array"]
    planned = {
        str(run.get("run_id")): run
        for run in run_values
        if isinstance(run, dict) and run.get("run_id")
    }
    plan_path = project / "experiments" / "plan.json"
    current_plan_hash = sha256_file(plan_path) if plan_path.is_file() else ""
    approval_hash = None
    state_path = project / "state" / "run.json"
    if state_path.is_file():
        import json
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            approval = next(
                (item for item in reversed(state.get("approvals", [])) if item.get("gate") == "G3"),
                None,
            )
            approval_hash = approval.get("experiment_plan_sha256") if isinstance(approval, dict) else None
        except (OSError, ValueError):
            errors.append("state/run.json cannot establish the G3-approved plan")
    if not approval_hash or approval_hash != current_plan_hash:
        errors.append("current experiment plan does not match the recorded G3 human approval")

    seen_attempts: set[str] = set()
    attempted: set[str] = set()
    for index, entry in enumerate(registry):
        label = f"entry {index + 1}"
        run_id = entry.get("run_id")
        attempt_id = entry.get("attempt_id")
        if not isinstance(run_id, str) or run_id not in planned:
            errors.append(f"{label}: run_id is absent from the approved plan")
            continue
        attempted.add(run_id)
        run = planned[run_id]
        if not isinstance(attempt_id, str) or not attempt_id.strip():
            errors.append(f"{label}: attempt_id must be non-empty")
        elif attempt_id in seen_attempts:
            errors.append(f"{label}: duplicate attempt_id {attempt_id}")
        else:
            seen_attempts.add(attempt_id)
        if entry.get("schema_version") != "1.0":
            errors.append(f"{label}: schema_version must be 1.0")
        if entry.get("status") not in STATUS_VALUES:
            errors.append(f"{label}: status must be succeeded, failed or timed_out")
        if entry.get("paper_id") != run.get("paper_id"):
            errors.append(f"{label}: paper_id differs from the approved run")
        if entry.get("seed") != run.get("seed"):
            errors.append(f"{label}: seed differs from the approved run")
        if entry.get("approved_plan_sha256") != current_plan_hash:
            errors.append(f"{label}: approved_plan_sha256 is stale or incorrect")
        for field in ("started_at","finished_at"):
            if not isinstance(entry.get(field),str) or not entry[field].strip():errors.append(f"{label}: {field} must be non-empty")
        if not isinstance(entry.get("runtime_seconds"),(int,float)) or isinstance(entry.get("runtime_seconds"),bool) or entry.get("runtime_seconds",-1)<0:errors.append(f"{label}: runtime_seconds must be non-negative")
        if entry.get("argv")!=run.get("argv"):errors.append(f"{label}: argv differs from the approved run")
        if entry.get("cwd")!=run.get("cwd","."):errors.append(f"{label}: cwd differs from the approved run")
        if entry.get("timeout_seconds")!=run.get("timeout_seconds"):errors.append(f"{label}: timeout differs from the approved run")
        if entry.get("estimated_cost_usd")!=float(run.get("estimated_cost_usd",0)):errors.append(f"{label}: estimated cost differs from the approved run")
        if not isinstance(entry.get("timed_out"),bool) or (entry.get("status")=="timed_out")!=entry.get("timed_out"):errors.append(f"{label}: timed_out flag is inconsistent")
        inputs=entry.get("inputs") if isinstance(entry.get("inputs"),list) else []
        expected_inputs={str(item.get("path")):str(item.get("sha256")).lower() for item in run.get("inputs",[]) if isinstance(item,dict)}
        actual_inputs={str(item.get("path")):str(item.get("sha256")).lower() for item in inputs if isinstance(item,dict)}
        if actual_inputs!=expected_inputs:errors.append(f"{label}: inputs differ from the approved run")
        integrity = entry.get("input_integrity")
        if not isinstance(integrity, dict):
            errors.append(f"{label}: post-run input integrity receipt is missing")
        else:
            if integrity.get("verified_after_run") is not True:
                errors.append(f"{label}: inputs were not verified after execution")
            changed_inputs = integrity.get("mutated_or_missing")
            if not isinstance(changed_inputs, list):
                errors.append(f"{label}: mutated_or_missing must be an array")
            if not isinstance(integrity.get("passed"), bool):
                errors.append(f"{label}: input integrity passed must be boolean")
            elif isinstance(changed_inputs, list) and bool(changed_inputs) == integrity["passed"]:
                errors.append(f"{label}: input integrity pass flag is inconsistent")
            if entry.get("status") == "succeeded" and integrity.get("passed") is not True:
                errors.append(f"{label}: successful run has changed approved inputs")
        for input_path,input_hash in actual_inputs.items():
            path=_resolve(project,input_path,f"{label}.inputs",errors)
            if path is None or not path.is_file():errors.append(f"{label}: recorded input is missing: {input_path}")
            elif sha256_file(path).lower()!=input_hash:errors.append(f"{label}: recorded input hash changed: {input_path}")
        outputs = entry.get("outputs")
        if not isinstance(outputs, list):
            errors.append(f"{label}: outputs must be an array")
            outputs = []
        output_paths: set[str] = set()
        for output_index, output in enumerate(outputs):
            if not isinstance(output, dict):
                errors.append(f"{label}: outputs[{output_index}] must be an object")
                continue
            path = _resolve(project, output.get("path"), f"{label}.outputs[{output_index}].path", errors)
            if isinstance(output.get("path"), str):
                output_paths.add(output["path"])
            if path is None or not path.is_file():
                errors.append(f"{label}: recorded output is missing: {output.get('path')}")
            elif output.get("sha256") != sha256_file(path):
                errors.append(f"{label}: recorded output hash changed: {output.get('path')}")
        if entry.get("status") == "succeeded":
            expected = set(str(item) for item in run.get("expected_outputs", []))
            if output_paths != expected:
                errors.append(f"{label}: successful output set does not match the approved run")
            if entry.get("missing_outputs"):
                errors.append(f"{label}: successful run cannot report missing outputs")
    missing = sorted(set(planned) - attempted)
    if missing:
        errors.append(f"planned runs without registry attempts: {', '.join(missing)}")
    return errors


def _ids(value: str | None) -> set[str]:
    return {item.strip() for item in re.split(r"[;,]", value or "") if item.strip()}


def validate_claim_evidence(
    project: Path, path: Path, registry: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    if not path.is_file() or path.stat().st_size == 0:
        return ["file is missing or empty"]
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not CLAIM_COLUMNS.issubset(reader.fieldnames):
                return ["header must include " + ", ".join(sorted(CLAIM_COLUMNS))]
            rows = list(reader)
    except (OSError, csv.Error) as exc:
        return [f"cannot read CSV: {exc}"]
    expected: dict[str, str] = {}
    for contract_path in sorted((project / "papers").glob("P[0-9][0-9]/paper-contract.json")):
        import json
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            errors.append(f"cannot read {contract_path.relative_to(project)}")
            continue
        independence = contract.get("independence") if isinstance(contract.get("independence"), dict) else {}
        for claim_id in independence.get("unique_claim_ids", []) if isinstance(independence.get("unique_claim_ids"), list) else []:
            expected[str(claim_id)] = contract_path.parent.name
    seen: set[str] = set()
    known_runs = {str(item.get("run_id")) for item in registry if item.get("run_id")}
    successful_runs = {
        str(item.get("run_id")) for item in registry if item.get("status") == "succeeded"
    }
    evidence_cache: dict[str, tuple] = {}
    for index, row in enumerate(rows, 2):
        claim_id = (row.get("claim_id") or "").strip()
        if not claim_id:
            errors.append(f"row {index}: claim_id is required")
            continue
        if claim_id in seen:
            errors.append(f"row {index}: duplicate claim_id {claim_id}")
        seen.add(claim_id)
        if claim_id not in expected:
            errors.append(f"row {index}: claim_id is not contracted")
        elif row.get("paper_id") != expected[claim_id]:
            errors.append(f"row {index}: paper_id does not match the paper contract")
        for field in ("claim", "uncertainty", "status"):
            if not (row.get(field) or "").strip():
                errors.append(f"row {index}: {field} is required")
        support = (row.get("support") or "").strip()
        if support not in SUPPORT_VALUES:
            errors.append(f"row {index}: support must be one of {', '.join(sorted(SUPPORT_VALUES))}")
        analysis_ids = _ids(row.get("analysis_ids"))
        unknown = sorted(analysis_ids - known_runs)
        if unknown:
            errors.append(f"row {index}: unknown analysis_ids: {', '.join(unknown)}")
        wrong_paper = {r["run_id"] for r in registry if r.get("run_id") in analysis_ids
                       and r.get("paper_id") != row.get("paper_id")}
        if wrong_paper:
            errors.append(f"row {index}: analysis_ids belong to a different paper")
        paper_id = expected.get(claim_id)
        if paper_id and (project / "papers" / paper_id / "experiment-evidence-plan.json").is_file():
            from scripts import experiment_evidence as evidence
            if paper_id not in evidence_cache:
                validation = evidence.validate_report(project, paper_id)
                report = evidence.build_report(project, paper_id)
                evidence_cache[paper_id] = (validation, report)
            validation, report = evidence_cache[paper_id]
            errors.extend(f"row {index}: {issue}" for issue in validation)
            linked = [c for c in report["comparisons"] if claim_id in c["claim_ids"]]
            required_comparisons = {c["comparison_id"] for c in linked}
            if not required_comparisons or _ids(row.get("comparison_ids")) != required_comparisons:
                errors.append(f"row {index}: comparison_ids must include every preregistered comparison for this claim")
            source_runs = {source["run_id"] for comp in linked for source in comp.get("sources", [])}
            if not source_runs <= analysis_ids:
                errors.append(f"row {index}: analysis_ids omit registered comparison sources")
            confirmatory = [c for c in linked if c["analysis_phase"] == "confirmatory"]
            supported = [c for c in confirmatory if c.get("decision") == "meets_preregistered_threshold"]
            if support == "supported" and (not confirmatory or len(supported) != len(confirmatory)):
                errors.append(f"row {index}: supported claim does not meet every confirmatory threshold")
            if support == "partially_supported" and not any(c["role"] == "primary" for c in supported):
                errors.append(f"row {index}: partial support needs a passing confirmatory primary comparison")
        if support in {"supported", "partially_supported"} and not (analysis_ids & successful_runs):
            errors.append(f"row {index}: supported claim needs a successful referenced run")
    missing = sorted(set(expected) - seen)
    extra = sorted(seen - set(expected))
    if missing:
        errors.append(f"contracted claims missing from matrix: {', '.join(missing)}")
    if extra:
        errors.append(f"uncontracted claims in matrix: {', '.join(extra)}")
    if not rows:
        errors.append("at least one claim row is required")
    return errors
