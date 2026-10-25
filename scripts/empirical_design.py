"""Optional bounded causal designs inside the existing approved experiment plan.

This is a preparation/freshness audit, not a test of causal identification.
All estimates and diagnostic runs still require the native G3 executor.
"""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

from scripts.research_artifacts import path_in, read, sha, write, record

METHODS = {"did_2x2", "iv_2sls", "sharp_rdd"}
MODULE = "scripts/empirical_design.py"


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 12000:
        raise ValueError(label + " needs explicit bounded text")
    return value


def _ids(value, label, *, empty=False):
    if (not isinstance(value, list) or len(value) > 100 or (not value and not empty)
            or any(not isinstance(x, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", x) for x in value)
            or len(set(value)) != len(value)):
        raise ValueError(label + " needs unique bounded IDs")
    return value


def _finite(value, label, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(label + " needs a finite" + (" positive" if positive else "") + " number")
    return value


def validate_specification(spec, sample):
    """Validate only estimator variants actually implemented by this runtime."""
    if not isinstance(spec, dict) or spec.get("method") not in METHODS:
        raise ValueError("unsupported empirical method; staggered DID, dynamic DID and fuzzy RDD need another reviewed adapter")
    if not isinstance(sample, dict):
        raise ValueError("sample contract must be an object")
    _ids([spec.get("id")], "specification ID")
    _ids([spec.get("run_id")], "run ID")
    _ids(spec.get("claim_ids"), "claim IDs")
    for field in ("family", "outcome", "output"):
        _text(spec.get(field), field)
    _ids(spec.get("covariates"), "covariates", empty=True)
    if spec.get("phase") not in {"confirmatory", "exploratory"}:
        raise ValueError("explicit confirmatory/exploratory phase required")
    level = _finite(spec.get("confidence_level"), "confidence level")
    if not 0.8 <= level < 1:
        raise ValueError("confidence level must lie in [0.8,1)")
    if spec["outcome"] in spec["covariates"]:
        raise ValueError("outcome cannot be a covariate")
    method = spec["method"]
    if method == "did_2x2":
        for key in ("treatment", "period", "pre_value", "post_value"):
            _text(spec.get(key), key)
        if spec["pre_value"] == spec["post_value"]:
            raise ValueError("DID needs distinct pre/post periods")
        if (spec.get("covariance") != "cluster" or sample.get("cluster_column") != sample.get("unit_column")
                or type(spec.get("minimum_clusters")) is not int or spec["minimum_clusters"] < 10):
            raise ValueError("2x2 DID requires unit clustering and at least ten declared clusters")
    elif method == "iv_2sls":
        _text(spec.get("endogenous"), "endogenous variable")
        _ids(spec.get("instruments"), "excluded instruments")
        if (spec.get("covariance") != "homoskedastic" or sample.get("cluster_column") is not None
                or set(spec["instruments"]) & {spec["endogenous"], spec["outcome"], *spec["covariates"]}):
            raise ValueError("reviewed IV route is independent homoskedastic 2SLS with genuinely excluded instruments")
        if _finite(spec.get("minimum_first_stage_f"), "first-stage threshold") < 10:
            raise ValueError("predeclare a first-stage stop threshold at least ten; it cannot verify instrument validity")
        _text(spec.get("threshold_rationale"), "first-stage threshold rationale")
    else:
        for key in ("treatment", "running"):
            _text(spec.get(key), key)
        _finite(spec.get("cutoff"), "cutoff")
        _finite(spec.get("bandwidth"), "fixed bandwidth", positive=True)
        if (spec.get("covariance") != "HC1" or spec.get("kernel") != "triangular" or spec["covariates"]
                or sample.get("cluster_column") is not None or type(spec.get("minimum_side_observations")) is not int
                or spec["minimum_side_observations"] < 10):
            raise ValueError("reviewed sharp RDD is independent local-linear triangular HC1 with no covariates and at least ten rows per side")
    return spec


def _binding(project, value, label):
    if not isinstance(value, dict):
        raise ValueError(label + " binding required")
    path = path_in(project, value.get("path", ""))
    if value.get("sha256") != sha(path):
        raise ValueError(label + " hash changed")
    return {"path": value["path"], "sha256": value["sha256"]}


def _anchor(project, value):
    bound = _binding(project, value, "assumption source")
    _text(value.get("locator"), "source locator")
    quote = _text(value.get("quote"), "source quote")
    source = path_in(project, bound["path"])
    if source.stat().st_size > 4_000_000 or source.read_text(encoding="utf-8").count(quote) != 1:
        raise ValueError("assumption quote must occur once in its bounded current source")
    return {**bound, "locator": value["locator"], "quote": quote}


def audit(project: Path, paper_id: str, *, require_frozen=False) -> dict:
    if not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("explicit paper ID required")
    relative = f"papers/{paper_id}/empirical-design.json"
    target = path_in(project, relative, exists=False)
    result = {"schema_version": "1.0", "paper_id": paper_id, "pass": True,
              "status": "not_configured", "errors": [], "sources": [], "specifications": [],
              "scientific_validity_verified": False, "causal_identification_verified": False,
              "execution_started": False, "implementation_sha256": sha(Path(__file__))}
    if not target.is_file():
        if (project / f"papers/{paper_id}/reviews/empirical-design.json").is_file():
            result.update(status="blocked", errors=["do not remove an existing empirical design card"], **{"pass": False})
        return result
    try:
        value = read(target)
        if value.get("schema_version") != "1.0" or value.get("paper_id") != paper_id:
            raise ValueError("empirical design identity differs")
        _ids([value.get("dataset_id")], "dataset ID")
        estimand = value.get("estimand", {})
        if not isinstance(estimand, dict):
            raise ValueError("estimand must be an object")
        for key in ("outcome", "population", "exposure", "contrast", "time_horizon", "inference_boundary"):
            _text(estimand.get(key), "estimand." + key)
        assignment = value.get("assignment", {})
        if not isinstance(assignment, dict):
            raise ValueError("assignment must be an object")
        for key in ("mechanism", "comparison_group", "timing"):
            _text(assignment.get(key), "assignment." + key)
        sample = value.get("sample", {})
        if not isinstance(sample, dict):
            raise ValueError("sample must be an object")
        for key in ("inclusion_rule", "exclusion_rule", "missingness_rule", "unit_column"):
            _text(sample.get(key), "sample." + key)
        if sample.get("cluster_column") is not None:
            _text(sample["cluster_column"], "cluster column")
        policy = value.get("specification_policy", {})
        if not isinstance(policy, dict):
            raise ValueError("specification policy must be an object")
        if policy.get("selection_rule") != "report_all_preregistered" or policy.get("changes_require_amendment") is not True:
            raise ValueError("report every registered specification; changes require the native amendment route")
        _text(policy.get("exploratory_rule"), "exploratory separation rule")
        result["sources"] = [{"path": relative, "sha256": sha(target)}]
        result["sources"].extend(_binding(project, value.get(key), key) for key in ("data", "runtime"))
        runtime = value["runtime"]
        if runtime["sha256"] != sha(Path(__file__).with_name("empirical_runtime.py")):
            raise ValueError("copied empirical runtime differs from the reviewed implementation")
        if not value["data"]["path"].endswith(".csv"):
            raise ValueError("empirical runtime uses an explicit finite CSV contract")
        with path_in(project, value["data"]["path"]).open(encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), [])
        if not header or len(set(header)) != len(header):
            raise ValueError("CSV header must be nonempty and unique")
        assumptions = value.get("assumptions")
        if not isinstance(assumptions, list) or not 1 <= len(assumptions) <= 40 or any(not isinstance(row, dict) for row in assumptions):
            raise ValueError("explicit bounded identifying assumptions required")
        _ids([row.get("id") for row in assumptions], "assumption IDs")
        for row in assumptions:
            _text(row.get("statement"), "identifying assumption")
            if row.get("status") not in {"proposed", "source_supported", "unresolved"}:
                raise ValueError("assumptions cannot self-certify truth")
            anchors = row.get("evidence", [])
            if not isinstance(anchors, list) or len(anchors) > 10 or (row["status"] == "source_supported" and not anchors):
                raise ValueError("source-supported assumptions need located evidence")
            for anchor in anchors:
                result["sources"].append(_anchor(project, anchor))
        rivals = value.get("rival_explanations")
        if not isinstance(rivals, list) or not 1 <= len(rivals) <= 20 or any(not isinstance(row, dict) for row in rivals):
            raise ValueError("explicit rival explanations and discriminating tests required")
        _ids([row.get("id") for row in rivals], "rival IDs")
        for row in rivals:
            _text(row.get("explanation"), "rival explanation")
            _text(row.get("discriminating_test"), "discriminating test")
        plan_path = path_in(project, "experiments/plan.json")
        result["plan_sha256"] = sha(plan_path)
        plan = read(plan_path)
        planned = {row["run_id"]: row for row in plan.get("runs", [])}
        specifications = value.get("specifications")
        if not isinstance(specifications, list) or not 1 <= len(specifications) <= 100 or any(not isinstance(row, dict) for row in specifications):
            raise ValueError("bounded prespecified estimates required")
        _ids([row.get("id") for row in specifications], "specification IDs")
        _ids([row.get("run_id") for row in specifications], "specification run IDs")
        if len({row.get("output") for row in specifications}) != len(specifications):
            raise ValueError("each specification needs its own immutable output")
        for family in {row.get("family") for row in specifications}:
            levels = {row.get("confidence_level") for row in specifications if row.get("family") == family}
            if len(levels) != 1:
                raise ValueError("each declared multiplicity family needs a common confidence level")
        contract = read(path_in(project, f"papers/{paper_id}/paper-contract.json"))
        actual_claims = set(contract.get("independence", {}).get("unique_claim_ids", []))
        for spec in specifications:
            validate_specification(spec, sample)
            if not set(spec["claim_ids"]).issubset(actual_claims):
                raise ValueError("specification claims must belong to this paper contract")
            run = planned.get(spec["run_id"], {})
            if run.get("paper_id") != paper_id or run.get("cwd") != "." or spec["output"] not in run.get("expected_outputs", []):
                raise ValueError("specification must bind its own approved-plan run and output with project-root cwd")
            output = path_in(project, spec["output"], exists=False)
            if not spec["output"].startswith(f"papers/{paper_id}/results/") or output.suffix != ".json":
                raise ValueError("empirical outputs belong to this paper's results JSON directory")
            inputs = {item["path"]: item["sha256"] for item in run.get("inputs", [])}
            for source in result["sources"][:3]:
                if inputs.get(source["path"]) != source["sha256"]:
                    raise ValueError("each estimation run must hash-declare the current design, CSV and reviewed runtime")
            argv = run.get("argv", [])
            expected = [runtime["path"], "--design", relative, "--data", value["data"]["path"],
                        "--spec", spec["id"], "--output", spec["output"]]
            if len(argv) != len(expected) + 1 or argv[1:] != expected:
                raise ValueError("run command differs from the exact bounded empirical adapter command")
            columns = {spec["outcome"], sample["unit_column"], *spec["covariates"]}
            for key in ("treatment", "period", "running", "endogenous"):
                if key in spec:
                    columns.add(spec[key])
            columns.update(spec.get("instruments", []))
            if columns - set(header):
                raise ValueError("empirical specification references absent CSV columns")
            result["specifications"].append({key: spec[key] for key in ("id", "run_id", "method", "phase", "family", "claim_ids", "output")})
        diagnostics = value.get("diagnostics")
        if not isinstance(diagnostics, list) or not 1 <= len(diagnostics) <= 60 or any(not isinstance(row, dict) for row in diagnostics):
            raise ValueError("explicit diagnostic/falsification runs required")
        _ids([row.get("id") for row in diagnostics], "diagnostic IDs")
        for row in diagnostics:
            for key in ("test", "purpose", "failure_action", "run_id", "output"):
                _text(row.get(key), "diagnostic." + key)
            run = planned.get(row["run_id"], {})
            if run.get("paper_id") != paper_id or row["output"] not in run.get("expected_outputs", []):
                raise ValueError("diagnostic must identify an actual planned run/output for this paper")
        result["diagnostics"] = diagnostics
        frozen_path = path_in(project, f"papers/{paper_id}/preregistration.json", exists=False)
        result["preregistered"] = frozen_path.is_file()
        if frozen_path.is_file():
            frozen = {row["path"]: row["sha256"] for row in read(frozen_path).get("files", [])}
            if any(frozen.get(item["path"]) != item["sha256"] for item in result["sources"][:3]):
                raise ValueError("empirical design, data or runtime changed after preregistration")
            result["preregistration_sha256"] = sha(frozen_path)
        elif require_frozen:
            raise ValueError("empirical execution/reporting needs a current native preregistration")
        result["status"] = "ready_for_scientific_review"
    except (OSError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        result["errors"].append(str(exc))
        result["status"] = "blocked"
        result["pass"] = False
    return result


def refresh(project: Path, paper_id: str) -> dict:
    report = audit(project, paper_id)
    if report["status"] != "not_configured":
        target = path_in(project, f"papers/{paper_id}/reviews/empirical-design.json", exists=False)
        write(target, report)
        record(project, [target], MODULE)
    return report


def validate_saved_report(project: Path, paper_id: str) -> list[str]:
    current = audit(project, paper_id, require_frozen=True)
    if current["status"] == "not_configured":
        return []
    target = path_in(project, f"papers/{paper_id}/reviews/empirical-design.json", exists=False)
    if not target.is_file():
        return ["current empirical design audit missing"]
    from scripts.output_provenance import current_origin
    origin = current_origin(project, target)
    errors = list(current["errors"])
    if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane":
        errors.append("empirical design audit provenance changed")
    if read(target) != current:
        errors.append("empirical design audit stale; refresh current source and specification checks")
    return errors
