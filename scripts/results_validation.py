#!/usr/bin/env python3
"""Validate G4 experiment attempts and claim-to-evidence traceability."""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from scripts.research_artifacts import sha as sha256_file
except ImportError:  # Direct execution from scripts/.
    from research_artifacts import sha as sha256_file


STATUS_VALUES = {"succeeded", "failed", "timed_out"}
SUPPORT_VALUES = {"supported", "partially_supported", "not_supported", "contradicted", "inconclusive"}
CLAIM_COLUMNS = {
    "claim_id", "paper_id", "claim", "evidence_ids", "analysis_ids",
    "support", "uncertainty", "status",
}


from scripts.paper_execution import artifact_path as experiment_path, paper_scoped


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
    project: Path, plan: dict[str, Any], registry: list[dict[str, Any]], *, require_successful_retries: bool = True
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
    plan_path = experiment_path(project, 'experiments/plan.json')
    current_plan_hash = sha256_file(plan_path) if plan_path.is_file() else ""
    approval_hash = None
    state_path = project / "state" / "run.json"
    if state_path.is_file():
        import json
        try:
            json.loads(state_path.read_text(encoding="utf-8"))
            from scripts.paper_execution import approval as paper_approval
            approval = paper_approval(project, "G3")
            approval_hash = approval.get("experiment_plan_sha256") if isinstance(approval, dict) else None
        except (OSError, ValueError):
            errors.append("state/run.json cannot establish the G3-approved plan")
    if not approval_hash or approval_hash != current_plan_hash:
        errors.append("current experiment plan does not match the recorded G3 protocol decision")

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
            if entry.get("status") in {"failed", "timed_out"}:
                from scripts.primary_recovery import preserved_output
                try:
                    path = preserved_output(project, entry, output)
                except (ValueError, OSError, KeyError) as exc:
                    errors.append(f"{label}: {exc}")
                    path = None
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
    from scripts.primary_recovery import selected_attempt, latest_attempt
    select = selected_attempt if require_successful_retries else latest_attempt
    for run_id in planned:
        if len([r for r in registry if r.get("run_id") == run_id]) > 1:
            try:
                select(project, run_id, registry, plan_sha256=current_plan_hash)
            except (ValueError, OSError, KeyError) as exc:
                errors.append(f"{run_id}: {exc}")
    return errors


def _ids(value: str | None) -> set[str]:
    return {item.strip() for item in re.split(r"[;,]", value or "") if item.strip()}


def _outcome_error(status: str, comparisons: list[dict], *, empirical: bool) -> str | None:
    """Prevent stronger numeric labels; negative/uncertain interpretations stay possible."""
    if status not in SUPPORT_VALUES:
        return "invalid formal claim result_status"
    confirmatory = [c for c in comparisons if c.get("analysis_phase", "confirmatory") in {"confirmatory", "formal_verification"}]
    primary = [c for c in confirmatory if c.get("role") in {"primary", "main"}]
    passing = {"meets_preregistered_threshold", "kernel_checked"}
    if status == "supported" and (not primary or any(c.get("decision") not in passing for c in confirmatory)):
        return "supported claim does not meet every confirmatory threshold"
    if status == "partially_supported" and not any(c.get("decision") in passing for c in primary):
        return "partial support needs a passing confirmatory primary comparison"
    if status == "contradicted" and empirical:
        opposite = []
        for comp in primary:
            low, high, margin = comp.get("ci_low"), comp.get("ci_high"), comp.get("minimum_effect")
            if not all(type(value) in (int, float) and math.isfinite(value) for value in (low, high, margin)):
                continue
            if comp.get("decision_rule") == "equivalence":
                opposite.append(low > margin or high < -margin)
            else:
                opposite.append(high < -margin)
        if not any(opposite):
            return "contradicted claim needs a confirmatory primary interval establishing the opposite; absence of significance is insufficient"
    return None


@paper_scoped
def claim_outcomes(project: Path, paper_id: str) -> dict:
    """Read the existing matrix and recompute its sealed evidence for one paper.

    This is a current view, never a new ledger. Exact same claim IDs and all
    comparisons/attempts remain visible, including adverse and exploratory work.
    """
    from scripts import experiment_evidence as evidence, study_routes
    contract = evidence.read(project / "papers" / paper_id / "paper-contract.json")
    expected = set(evidence.strings(contract.get("independence", {}).get("unique_claim_ids"), "contract claim IDs"))
    report = evidence.build_report(project, paper_id)
    evidence.need(report.get("status") == "complete" and not report.get("errors"),
                  "current outcome evidence is blocked: " + "; ".join(report.get("errors", [])))
    matrix = experiment_path(project, "claims/claim-evidence.csv")
    with matrix.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        evidence.need(CLAIM_COLUMNS.issubset(reader.fieldnames or []), "formal claim matrix has missing columns")
        rows = [row for row in reader if row.get("paper_id") == paper_id]
    evidence.need(len(rows) == len(expected) and {r.get("claim_id") for r in rows} == expected,
                  "formal claim matrix must cover every paper claim exactly once")
    empirical = study_routes.route(project, paper_id) == "empirical"
    registry = [json.loads(line) for line in experiment_path(project, "experiments/registry.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    known_runs = {row.get("run_id") for row in registry if row.get("paper_id") == paper_id}
    claims = {}
    for row in rows:
        claim = row["claim_id"]
        linked = [c for c in report["comparisons"] if claim in c.get("claim_ids", [])]
        comparison_ids = {c["comparison_id"] for c in linked}
        evidence.need(bool(linked) and _ids(row.get("comparison_ids")) == comparison_ids,
                      claim + ": retain every actual comparison in the formal matrix")
        sources = {s["run_id"] for c in linked for s in c.get("sources", [])}
        actual_ids = _ids(row.get("analysis_ids"))
        evidence.need(sources <= actual_ids <= known_runs,
                      claim + ": formal matrix omits actual result runs or references an unknown/wrong-paper run")
        error = _outcome_error(row.get("support", ""), linked, empirical=empirical)
        evidence.need(error is None, claim + ": " + str(error))
        claims[claim] = {"result_status": row["support"], "comparison_ids": sorted(comparison_ids),
                         "analysis_ids": sorted(sources)}
    protocol = (project / "papers" / paper_id / evidence.PLAN if empirical else
                study_routes.protocol_path(project, paper_id))
    return {"paper_id": paper_id, "claim_matrix_sha256": evidence.sha(matrix),
            "evidence_plan_sha256": evidence.sha(protocol), "claims": claims}


@paper_scoped
def validate_result_statuses(project: Path, paper_id: str, alignments: list[dict] | None = None) -> list[str]:
    """G4/G5 adapter; manuscript tags must match current formal numeric outcomes."""
    try:
        current = claim_outcomes(project, paper_id)
        if alignments is None:
            return []
        if not isinstance(alignments, list) or any(not isinstance(row, dict) for row in alignments):
            return ["claim_alignment must contain current claim objects"]
        claims = current["claims"]
        if len(alignments) != len(claims) or {r.get("claim_id") for r in alignments} != set(claims):
            return ["manuscript claim_alignment must cover every formal paper claim exactly once"]
        return [str(row["claim_id"]) + ": manuscript result_status differs from its current formal outcome"
                for row in alignments if row.get("result_status") != claims[row["claim_id"]]["result_status"]]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, csv.Error) as exc:
        return [str(exc)]


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
    from scripts.paper_execution import papers
    selected_papers = set(papers(project))
    for contract_path in sorted((project / "papers").glob("P[0-9][0-9]/paper-contract.json")):
        if contract_path.parent.name not in selected_papers:
            continue
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
        from scripts import study_routes
        if paper_id and study_routes.route(project, paper_id) != "empirical":
            from scripts import experiment_evidence as evidence
            if paper_id not in evidence_cache:
                evidence_cache[paper_id] = (evidence.validate_report(project, paper_id), evidence.build_report(project, paper_id))
            validation, report = evidence_cache[paper_id]
            errors.extend(f"row {index}: {issue}" for issue in validation)
            linked = [c for c in report["comparisons"] if claim_id in c["claim_ids"]]
            if not linked or _ids(row.get("comparison_ids")) != {c["comparison_id"] for c in linked}:
                errors.append(f"row {index}: comparison_ids must retain every study outcome/proof obligation")
            if not {s["run_id"] for c in linked for s in c["sources"]} <= analysis_ids:
                errors.append(f"row {index}: analysis_ids omit the original or isolated replay")
            main = [c for c in linked if c["role"] in {"main", "primary"}]
            passed = [c for c in main if c["decision"] in {"kernel_checked", "meets_preregistered_threshold"}]
            if support == "supported" and (not main or len(passed) != len(main)):
                errors.append(f"row {index}: supported study claim lacks its preregistered evidence")
            if support == "partially_supported" and not passed:
                errors.append(f"row {index}: partial study support needs a passing primary result")
        elif paper_id and (project / "papers" / paper_id / "experiment-evidence-plan.json").is_file():
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
