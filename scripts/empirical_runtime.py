"""Small offline, source-bound empirical estimators for approved cloud runs.

Only 2x2 panel DID, independent homoskedastic 2SLS with one endogenous variable,
and fixed-bandwidth sharp local-linear RDD are implemented. An estimate, passing
diagnostic or numerical reference agreement never verifies causal assumptions.
This file may be copied unchanged into a hash-declared experiment input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _safe(root, relative, *, exists=True):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("use project-relative paths")
    candidate = Path(relative)
    target = root / candidate
    if candidate.is_absolute() or ".." in candidate.parts or any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError("escaped or symlinked runtime path")
    if not target.resolve().is_relative_to(root.resolve()) or (exists and not target.is_file()):
        raise ValueError("runtime path is unavailable or escaped")
    return target


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(label + " must be finite numeric data")
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(label + " must be finite numeric data; no implicit row dropping or imputation") from exc
    if not math.isfinite(value):
        raise ValueError(label + " must be finite numeric data")
    return value


def _rows(path):
    if path.stat().st_size > 64_000_000:
        raise ValueError("empirical input exceeds the bounded CPU CSV scope")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or any(not key for key in reader.fieldnames):
            raise ValueError("CSV needs unique nonempty columns")
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("ragged CSV row")
            rows.append(row)
            if len(rows) > 250000:
                raise ValueError("empirical input exceeds 250000 rows")
    if not rows:
        raise ValueError("empirical input is empty")
    return rows


def _linear(y, x, *, clusters=None, weights=None):
    import numpy as np
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    n, k = x.shape
    if n <= k + 1 or np.linalg.matrix_rank(x) != k:
        raise ValueError("insufficient observations or collinear empirical specification")
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=float)
    if np.any(w <= 0) or not np.all(np.isfinite(w)):
        raise ValueError("positive finite local weights required")
    xw, yw = x * np.sqrt(w)[:, None], y * np.sqrt(w)
    bread = np.linalg.inv(xw.T @ xw)
    beta = bread @ xw.T @ yw
    residual = yw - xw @ beta
    scores = xw * residual[:, None]
    if clusters is None:
        meat = scores.T @ scores
        covariance = (n / (n - k)) * bread @ meat @ bread
        degrees = n - k
    else:
        labels = list(dict.fromkeys(clusters))
        g = len(labels)
        if g < 2:
            raise ValueError("at least two independent clusters required")
        grouped = np.asarray([scores[np.asarray(clusters) == group].sum(axis=0) for group in labels])
        correction = (g / (g - 1)) * ((n - 1) / (n - k))
        covariance = correction * bread @ grouped.T @ grouped @ bread
        degrees = g - 1
    return beta, covariance, degrees


def _summary(beta, covariance, index, degrees, level):
    from scipy import stats
    estimate = float(beta[index])
    variance = float(covariance[index, index])
    if not math.isfinite(variance) or variance <= 0:
        raise ValueError("nonpositive or nonfinite estimated variance; no exact-fit significance claim")
    se = math.sqrt(variance)
    critical = float(stats.t.ppf((1 + level) / 2, degrees))
    return {"estimate": estimate, "standard_error": se,
            "confidence_interval": [estimate - critical * se, estimate + critical * se],
            "confidence_level": level, "p_value": float(2 * stats.t.sf(abs(estimate / se), degrees)),
            "degrees_of_freedom": int(degrees), "test_null": 0,
            "p_value_kind": "two_sided_against_zero"}


def calculate(design: dict, spec: dict, data_path: Path, *, design_path: Path | None = None) -> dict:
    """Recompute one fixed specification from its exact current CSV, offline.

    This pure function grants no execution authority. Production calls go through
    experiment_runner; cloud audits may recompute a registered output to verify
    numerical provenance. No treatment search, row dropping or model selection.
    """
    import numpy as np
    if design.get("schema_version") != "1.0" or spec not in design.get("specifications", []):
        raise ValueError("specification must be an exact member of its design")
    if design.get("specification_policy", {}).get("selection_rule") != "report_all_preregistered":
        raise ValueError("all prespecified estimates must remain reportable")
    if design.get("data", {}).get("sha256") != _sha(data_path):
        raise ValueError("empirical CSV hash changed")
    if design.get("runtime", {}).get("sha256") != _sha(Path(__file__)):
        raise ValueError("empirical runtime hash changed")
    rows = _rows(data_path)
    sample = design["sample"]
    unit = sample["unit_column"]
    identifiers = [row[unit].strip() for row in rows]
    if not all(identifiers):
        raise ValueError("blank independent-unit identifiers")
    outcome = np.asarray([_number(row[spec["outcome"]], "outcome") for row in rows])
    controls = [[_number(row[name], "covariate " + name) for name in spec.get("covariates", [])] for row in rows]
    level = _number(spec.get("confidence_level"), "confidence level")
    if not 0.8 <= level < 1 or spec.get("phase") not in {"confirmatory", "exploratory"}:
        raise ValueError("declare confidence level and analysis phase")
    method = spec.get("method")
    diagnostics = {}
    n_selected = len(rows)
    if method == "did_2x2":
        if (spec.get("covariance") != "cluster" or sample.get("cluster_column") != unit
                or type(spec.get("minimum_clusters")) is not int or spec["minimum_clusters"] < 10):
            raise ValueError("DID requires declared unit clustering and minimum cluster count")
        pre, post = spec["pre_value"], spec["post_value"]
        if pre == post or any(row[spec["period"]] not in {pre, post} for row in rows):
            raise ValueError("only the exact declared two-period DID design is supported")
        treatment = [_number(row[spec["treatment"]], "treatment") for row in rows]
        if any(value not in {0, 1} for value in treatment):
            raise ValueError("DID treatment group must be binary")
        panel = {}
        for identifier, row, group in zip(identifiers, rows, treatment):
            panel.setdefault(identifier, []).append((row[spec["period"]], group))
        if any(len(pair) != 2 or {item[0] for item in pair} != {pre, post}
               or len({item[1] for item in pair}) != 1 for pair in panel.values()):
            raise ValueError("DID requires a complete unique two-period panel and stable treatment groups; staggered designs need another adapter")
        groups = [pair[0][1] for pair in panel.values()]
        if len(panel) < spec["minimum_clusters"] or min(groups.count(0), groups.count(1)) < 5:
            raise ValueError("insufficient independent clusters or treatment/comparison units")
        time = [int(row[spec["period"]] == post) for row in rows]
        x = np.asarray([[1, group, period, group * period, *c] for group, period, c in zip(treatment, time, controls)])
        beta, covariance, degrees = _linear(outcome, x, clusters=identifiers)
        summary = _summary(beta, covariance, 3, degrees, level)
        diagnostics = {"n_clusters": len(panel), "treated_units": groups.count(1), "comparison_units": groups.count(0),
                       "parallel_trends": "not_testable_with_one_pre_period",
                       "diagnostic_runs_required": [row["id"] for row in design.get("diagnostics", [])],
                       "variance_method": "CR1_unit_cluster_small_sample_correction",
                       "causal_assumptions_verified": False}
        limitations = ["Only a balanced two-period, stable binary-treatment DID is implemented; no staggered or dynamic effects.",
                       "One pre-period cannot diagnose pre-trends. No anticipation, parallel untreated trends and treatment assignment require independent evidence.",
                       "CR1 t inference can remain unreliable with few or highly unequal clusters; the minimum count is a declared stop rule, not validation."]
    elif method == "iv_2sls":
        if spec.get("covariance") != "homoskedastic" or sample.get("cluster_column") is not None:
            raise ValueError("this IV adapter supports independent homoskedastic 2SLS only")
        if len(set(identifiers)) != len(rows):
            raise ValueError("independent IV observations need unique unit identifiers")
        instruments = spec.get("instruments", [])
        if (not instruments or len(set(instruments)) != len(instruments)
                or set(instruments) & {spec["outcome"], spec["endogenous"], *spec.get("covariates", [])}):
            raise ValueError("excluded instrument names must be distinct from outcome, endogenous variable and controls")
        endogenous = np.asarray([_number(row[spec["endogenous"]], "endogenous variable") for row in rows])
        base = np.asarray([[1, *c] for c in controls])
        x = np.column_stack([base, endogenous])
        z = np.column_stack([base, np.asarray([[_number(row[name], "instrument") for name in instruments] for row in rows])])
        n, k = x.shape
        if n <= max(k, z.shape[1]) + 1 or np.linalg.matrix_rank(x) != k or np.linalg.matrix_rank(z) != z.shape[1]:
            raise ValueError("insufficient observations, collinear regressors or collinear instruments")
        projection = z @ np.linalg.solve(z.T @ z, z.T @ x)
        cross = projection.T @ x
        if np.linalg.matrix_rank(cross) != k:
            raise ValueError("instruments do not identify the declared endogenous variable")
        beta = np.linalg.solve(cross, projection.T @ outcome)
        residual = outcome - x @ beta
        covariance = float(residual @ residual) / (n - k) * np.linalg.inv(cross)
        restricted = endogenous - base @ np.linalg.lstsq(base, endogenous, rcond=None)[0]
        unrestricted = endogenous - z @ np.linalg.lstsq(z, endogenous, rcond=None)[0]
        sse_full, sse_restricted = float(unrestricted @ unrestricted), float(restricted @ restricted)
        if sse_full <= 0:
            raise ValueError("degenerate first-stage error variance; use a separately reviewed deterministic-instrument analysis")
        first_f = max(0.0, (sse_restricted - sse_full) / len(instruments)) / (sse_full / (n - z.shape[1]))
        threshold = _number(spec.get("minimum_first_stage_f"), "first-stage stop threshold")
        if threshold < 10 or first_f < threshold or not math.isfinite(first_f):
            raise ValueError("first-stage relevance below the declared stop threshold; weak-IV-robust inference needs another adapter")
        summary = _summary(beta, covariance, k - 1, n - k, level)
        diagnostics = {"first_stage_partial_f": first_f, "first_stage_threshold": threshold,
                       "excluded_instruments": len(instruments), "overidentification_test": "not_computed",
                       "weak_iv_robust_confidence_set": "not_implemented", "variance_method": "homoskedastic_2SLS_df_n_minus_k",
                       "instrument_validity_verified": False}
        limitations = ["Independent homoskedastic linear 2SLS with one endogenous variable only; no clustered, HAC or heteroskedastic-robust inference.",
                       "The first-stage threshold is a prespecified stop rule and does not verify exclusion restrictions, independence or a weak-instrument-robust confidence set.",
                       "No overidentification test is relabeled as Anderson-Rubin causal-coefficient inference."]
    elif method == "sharp_rdd":
        if (spec.get("covariance") != "HC1" or spec.get("kernel") != "triangular" or spec.get("covariates")
                or sample.get("cluster_column") is not None or len(set(identifiers)) != len(rows)):
            raise ValueError("sharp RDD requires independent unique units and local-linear triangular HC1 without covariates")
        cutoff = _number(spec["cutoff"], "cutoff")
        bandwidth = _number(spec["bandwidth"], "fixed bandwidth")
        if bandwidth <= 0:
            raise ValueError("fixed bandwidth must be positive")
        running = np.asarray([_number(row[spec["running"]], "running variable") for row in rows]) - cutoff
        treatment = np.asarray([_number(row[spec["treatment"]], "sharp treatment") for row in rows])
        if not np.array_equal(treatment, (running >= 0).astype(float)):
            raise ValueError("sharp assignment must equal the declared cutoff rule; fuzzy RDD needs another adapter")
        selected = np.abs(running) < bandwidth
        r, group, y = running[selected], treatment[selected], outcome[selected]
        n_selected = len(y)
        minimum = spec.get("minimum_side_observations")
        if type(minimum) is not int or minimum < 10 or min(int(sum(r < 0)), int(sum(r >= 0))) < minimum:
            raise ValueError("insufficient RDD observations on either side of the fixed cutoff")
        if min(len(np.unique(r[r < 0])), len(np.unique(r[r >= 0]))) < 5:
            raise ValueError("insufficient distinct running-variable support near cutoff")
        x = np.column_stack([np.ones(n_selected), group, r, group * r])
        weights = 1 - np.abs(r) / bandwidth
        beta, covariance, degrees = _linear(y, x, weights=weights)
        summary = _summary(beta, covariance, 1, degrees, level)
        diagnostics = {"bandwidth": bandwidth, "cutoff": cutoff, "kernel": "triangular",
                       "left_observations": int(sum(r < 0)), "right_observations": int(sum(r >= 0)),
                       "outside_bandwidth_observations": len(rows) - n_selected,
                       "manipulation_density_test": "requires_separate_registered_diagnostic",
                       "covariate_balance": "requires_separate_registered_diagnostic",
                       "bias_corrected_interval": False, "variance_method": "local_linear_triangular_HC1",
                       "cutoff_assignment_verified": True, "continuity_assumptions_verified": False}
        limitations = ["Fixed preregistered bandwidth, sharp assignment, independent units and local linear triangular weighting only.",
                       "The interval is a conventional HC1 local-polynomial interval, not robust bias-corrected inference. Smoothing-bias control needs scientific justification or another estimator.",
                       "Density/manipulation, covariate continuity and exclusion of simultaneous interventions need separately registered evidence."]
    else:
        raise ValueError("unsupported empirical estimator; never silently substitute a simple estimator for another research design")
    inputs = [dict(design["data"]), dict(design["runtime"])]
    if design_path is not None:
        inputs.insert(0, {"path": f"papers/{design['paper_id']}/empirical-design.json", "sha256": _sha(design_path)})
    result = {"schema_version": "1.0", "paper_id": design["paper_id"], "dataset_id": design["dataset_id"],
              "method": method, "specification_id": spec["id"], "run_id": spec["run_id"],
              "phase": spec["phase"], "family": spec["family"], "claim_ids": spec["claim_ids"],
              **summary, "n_observations": n_selected, "n_input_observations": len(rows),
              "n_units": len(set(identifiers)) if method != "sharp_rdd" else n_selected,
              "diagnostics": diagnostics, "inputs": inputs, "scientific_validity_verified": False,
              "causal_identification_verified": False, "limitations": limitations,
              "implementation_sha256": _sha(Path(__file__)),
              "software": {name: importlib.metadata.version(name) for name in ("numpy", "scipy")}}
    result["records"] = [{"specification_id": spec["id"], "estimate": result["estimate"],
        "ci_low": result["confidence_interval"][0], "ci_high": result["confidence_interval"][1],
        "confidence_level": level, "n_observations": n_selected, "n_units": result["n_units"],
        "p_value": result["p_value"], "phase": spec["phase"]}]
    # JSON conversion rejects NaN/Inf recursively, including numeric diagnostics.
    json.dumps(result, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path.cwd()
    design_path, data_path = _safe(root, args.design), _safe(root, args.data)
    output = _safe(root, args.output, exists=False)
    design = json.loads(design_path.read_text(encoding="utf-8"))
    matches = [row for row in design.get("specifications", []) if row.get("id") == args.spec]
    if len(matches) != 1:
        raise ValueError("select exactly one registered specification")
    spec = matches[0]
    if not os.environ.get("RESEARCH_OS_RUN_ID") or os.environ["RESEARCH_OS_RUN_ID"] != spec.get("run_id"):
        raise ValueError("empirical estimates require the matching approved cloud executor run")
    paper = design.get("paper_id", "")
    if (args.design != f"papers/{paper}/empirical-design.json" or args.data != design.get("data", {}).get("path")
            or args.output != spec.get("output") or not args.output.startswith(f"papers/{paper}/results/")
            or output.suffix != ".json" or output.exists() or output in {design_path, data_path, Path(__file__)}):
        raise ValueError("use the exact registered new results output; never overwrite inputs or prior attempts")
    result = calculate(design, spec, data_path, design_path=design_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
