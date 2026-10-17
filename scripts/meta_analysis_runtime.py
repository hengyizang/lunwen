"""Pinned, offline inverse-variance Meta analysis; copied into approved studies.

Inputs are independently extracted effect estimates and sampling variances.
Dependent effects, network Meta analysis and unregistered model selection are
deliberately rejected, rather than treated as independent observations.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path

STATSMODELS_VERSION = "0.15.0"


def finite(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(name + " must be finite" + (" and positive" if positive else ""))
    return float(value)


def pool(effects, variances, *, method="pm", alpha=0.05):
    import numpy as np
    from scipy import stats
    from statsmodels.stats.meta_analysis import combine_effects
    if method not in {"pm", "dl"} or len(effects) < 2 or len(effects) != len(variances):
        raise ValueError("pool needs at least two independent effects and PM or DL")
    y = np.asarray([finite(x, "effect") for x in effects])
    v = np.asarray([finite(x, "variance", positive=True) for x in variances])
    # statsmodels' untruncated DL estimator can be negative: recompute weights
    # with the scientifically meaningful nonnegative variance component.
    result = combine_effects(y, v, method_re=method, use_t=True, alpha=alpha)
    tau = max(0.0, float(result.tau2))
    w = 1 / (v + tau)
    mean = float(np.sum(w * y) / np.sum(w))
    k = len(y)
    residual_scale = float(np.sum(w * (y - mean) ** 2) / (k - 1))
    se = math.sqrt(max(1.0, residual_scale) / float(np.sum(w)))
    critical = float(stats.t.ppf(1 - alpha / 2, k - 1))
    fixed_w = 1 / v
    fixed_mean = float(np.sum(fixed_w * y) / np.sum(fixed_w))
    q = float(np.sum(fixed_w * (y - fixed_mean) ** 2))
    pi = None
    if k >= 3:
        spread = float(stats.t.ppf(1 - alpha / 2, k - 2)) * math.sqrt(tau + se ** 2)
        pi = [mean - spread, mean + spread]
    values = {"k": k, "estimate": mean, "se": se, "ci_low": mean - critical * se,
              "ci_high": mean + critical * se, "p_value": float(2 * stats.t.sf(abs(mean / se), k - 1)),
              "tau_squared": tau, "q": q, "q_p_value": float(stats.chi2.sf(q, k - 1)),
              "i_squared": max(0.0, (q - k + 1) / q) if q > 0 else 0.0,
              "prediction_interval": pi, "fixed_effect_estimate": fixed_mean,
              "interval_method": "modified_HKSJ_scale_at_least_one", "tau_method": method,
              "residual_scale": residual_scale}
    if any(not math.isfinite(x) for x in values.values() if isinstance(x, float)):
        raise ValueError("Meta analysis produced non-finite statistics")
    return values


def calculate(protocol, data):
    if importlib.metadata.version("statsmodels") != STATSMODELS_VERSION:
        raise ValueError("the reviewed statsmodels " + STATSMODELS_VERSION + " runtime is required")
    from scipy import stats
    from statsmodels.stats.multitest import multipletests
    import numpy as np
    records = data.get("records")
    outcomes = protocol.get("outcomes")
    if not isinstance(records, list) or not 2 <= len(records) <= 10000 or not isinstance(outcomes, list) or not outcomes:
        raise ValueError("bounded extraction records and preregistered outcomes required")
    if len({o["id"] for o in outcomes}) != len(outcomes):
        raise ValueError("duplicate outcome IDs")
    if any(r.get("outcome_id") not in {o["id"] for o in outcomes} for r in records):
        raise ValueError("extracted outcome is not preregistered")
    result = {"schema_version": "1.0", "route": "meta_analysis", "paper_id": protocol["paper_id"],
              "scientific_completion_verified": False, "outcomes": [],
              "software": {p: importlib.metadata.version(p) for p in ("statsmodels", "scipy", "numpy")}}
    for outcome in outcomes:
        rows = [r for r in records if r.get("outcome_id") == outcome["id"]]
        if len(rows) < 2 or len({r["study_id"] for r in rows}) != len(rows) or len({r["cohort_id"] for r in rows}) != len(rows):
            raise ValueError("each outcome needs independent studies; repeated cohorts require a separate dependency-aware method")
        if any(r.get("effect_measure") != outcome["effect_measure"] for r in rows):
            raise ValueError("incompatible effect measures cannot be pooled")
        y, v = [r["effect"] for r in rows], [r["variance"] for r in rows]
        summary = pool(y, v, alpha=outcome["alpha"])
        # PM is prespecified as primary; DL is a sensitivity, never selected
        # afterwards because it produces a preferred conclusion.
        sensitivity = {"dl": pool(y, v, method="dl", alpha=outcome["alpha"]),
                       "leave_one_out": [], "exclude_high_risk": None}
        if len(rows) >= 3:
            for i, row in enumerate(rows):
                sensitivity["leave_one_out"].append({"omitted": row["study_id"],
                    **pool(y[:i] + y[i+1:], v[:i] + v[i+1:], alpha=outcome["alpha"])})
        low_risk = [r for r in rows if r.get("risk_of_bias") != "high"]
        if len(low_risk) >= 2:
            sensitivity["exclude_high_risk"] = pool([r["effect"] for r in low_risk],
                [r["variance"] for r in low_risk], alpha=outcome["alpha"])
        bias = {"status": "not_estimated_fewer_than_10_studies", "absence_of_bias_verified": False}
        if len(rows) >= 10:
            # Egger diagnostic: no publication-bias correction or causal claim.
            se = np.sqrt(np.asarray(v)); x = 1 / se; z = np.asarray(y) / se
            if np.ptp(x) > 1e-12:
                from statsmodels.api import OLS, add_constant
                fit = OLS(z, add_constant(x)).fit()
                bias.update(status="diagnostic_only", intercept=float(fit.params[0]), p_value=float(fit.pvalues[0]))
            else:
                bias["status"] = "not_identifiable_equal_standard_errors"
        alpha = outcome["alpha"]
        if not 0 < alpha < 1 or outcome.get("direction") not in {"greater", "less"}:
            raise ValueError("declare an alpha and directional claim before execution")
        margin = finite(outcome["minimum_effect"], "practical threshold")
        if margin < 0:
            raise ValueError("practical threshold must be nonnegative")
        sign = 1 if outcome["direction"] == "greater" else -1
        threshold_t = (sign * summary["estimate"] - margin) / summary["se"]
        row = {"id": outcome["id"], "claim_ids": outcome["claim_ids"], "analysis_phase": outcome["analysis_phase"],
               "family": outcome["family"], "effect_measure": outcome["effect_measure"], "alpha": alpha,
               "direction": outcome["direction"], "minimum_effect": margin, "study_ids": [r["study_id"] for r in rows],
               "summary": summary, "sensitivity": sensitivity, "small_study_diagnostic": bias,
               "threshold_p_value": float(stats.t.sf(threshold_t, len(rows)-1)),
               "decision": "exploratory_only" if outcome["analysis_phase"] == "exploratory" else "does_not_establish_claim"}
        result["outcomes"].append(row)
    for family in {(r["family"], r["analysis_phase"]) for r in result["outcomes"]}:
        group = [r for r in result["outcomes"] if (r["family"], r["analysis_phase"]) == family]
        if len({r["alpha"] for r in group}) != 1:
            raise ValueError("one multiplicity family must use one alpha")
        adjusted = multipletests([r["threshold_p_value"] for r in group], method="holm")[1]
        for row, p in zip(group, adjusted):
            row["p_adjusted"] = float(p)
            bounds = row["summary"]
            meets = bounds["ci_low"] > row["minimum_effect"] if row["direction"] == "greater" else bounds["ci_high"] < -row["minimum_effect"]
            if row["analysis_phase"] == "confirmatory" and meets and p <= row["alpha"]:
                row["decision"] = "meets_preregistered_threshold"
    result["limitations"] = ["Independent study-level effect estimates only; dependence, causal identification and extraction validity require scientific review.",
        "Small-study diagnostics do not establish the presence or absence of publication bias.",
        "Prediction intervals and heterogeneity estimates can be unstable with few studies; all sensitivities remain visible."]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("protocol"); parser.add_argument("data"); parser.add_argument("output")
    args = parser.parse_args()
    protocol, data = Path(args.protocol), Path(args.data)
    result = calculate(json.loads(protocol.read_text(encoding="utf-8")), json.loads(data.read_text(encoding="utf-8")))
    result.update(protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),
                  input_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
                  implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
