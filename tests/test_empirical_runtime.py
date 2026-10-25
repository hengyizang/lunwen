"""Synthetic numerical references and counterexamples, run only by cloud CI."""
import copy
import csv
import importlib.util
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import empirical_runtime as runtime
from scripts.research_artifacts import sha, write
from tests import test_empirical_design as fixtures

NUMERIC = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("scipy") is not None
REFERENCE = importlib.util.find_spec("statsmodels") is not None


@unittest.skipUnless(NUMERIC, "numerical estimator checks run on the cloud scientific runtime")
class EmpiricalRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        self.card = fixtures.make_project(self.project)
        self.spec = self.card["specifications"][0]
        self.data = self.project / self.card["data"]["path"]

    def calculate(self):
        return runtime.calculate(self.card, self.spec, self.data, design_path=self.project / "papers/P01/empirical-design.json")

    def csv(self, header, rows):
        with self.data.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle); writer.writerow(header); writer.writerows(rows)
        self.card["data"]["sha256"] = sha(self.data)

    def iv(self):
        self.card["sample"]["cluster_column"] = None
        self.spec = {"id": "iv", "run_id": "iv-main", "method": "iv_2sls", "phase": "confirmatory", "family": "iv",
                     "claim_ids": ["C1"], "output": "papers/P01/results/iv.json", "outcome": "y", "covariates": [],
                     "confidence_level": 0.95, "covariance": "homoskedastic", "endogenous": "x", "instruments": ["z"],
                     "minimum_first_stage_f": 10, "threshold_rationale": "Synthetic prespecified relevance stop; not a validity certificate."}
        self.card["specifications"] = [self.spec]
        rows = []
        for index in range(160):
            z = math.sin(index * 0.31) + index / 50
            v = math.sin(index * 1.37)
            x = 1.5 * z + v
            y = 0.7 + 2.2 * x + 0.6 * v + math.cos(index * 0.79)
            rows.append([f"u{index}", z, x, y])
        self.csv(["unit", "z", "x", "y"], rows)
        return rows

    def rdd(self):
        self.card["sample"]["cluster_column"] = None
        self.spec = {"id": "rdd", "run_id": "rdd-main", "method": "sharp_rdd", "phase": "confirmatory", "family": "rdd",
                     "claim_ids": ["C1"], "output": "papers/P01/results/rdd.json", "outcome": "y", "covariates": [],
                     "confidence_level": 0.95, "covariance": "HC1", "treatment": "treated", "running": "running",
                     "cutoff": 0, "bandwidth": 1.5, "kernel": "triangular", "minimum_side_observations": 10}
        self.card["specifications"] = [self.spec]
        rows = []
        for index in range(100):
            x = (index - 49.5) / 25
            treated = int(x >= 0)
            y = 1 + 1.8 * treated + 0.4 * x - 0.2 * x * treated + 0.1 * math.sin(index * 1.1)
            rows.append([f"u{index}", x, treated, y])
        self.csv(["unit", "running", "treated", "y"], rows)
        return rows

    def test_did_agrees_with_analytic_difference_in_differences(self):
        result = self.calculate()
        self.assertAlmostEqual(result["estimate"], 1.7, places=10)
        self.assertEqual(result["n_observations"], 40)
        self.assertEqual(result["n_units"], 20)
        self.assertEqual(result["diagnostics"]["parallel_trends"], "not_testable_with_one_pre_period")
        self.assertFalse(result["causal_identification_verified"])
        self.assertEqual(result["records"][0]["estimate"], result["estimate"])

    @unittest.skipUnless(REFERENCE, "independent statsmodels reference runs on the cloud scientific job")
    def test_did_cluster_covariance_agrees_with_independent_statsmodels_implementation(self):
        import numpy as np
        import statsmodels.api as sm
        rows = runtime._rows(self.data)
        x = np.asarray([[1, float(r["treated"]), int(r["period"] == "post"), float(r["treated"]) * int(r["period"] == "post")] for r in rows])
        fit = sm.OLS([float(r["outcome"]) for r in rows], x).fit().get_robustcov_results(
            cov_type="cluster", groups=[r["unit"] for r in rows], use_correction=True, df_correction=True, use_t=True)
        result = self.calculate()
        self.assertAlmostEqual(result["estimate"], fit.params[3], places=10)
        self.assertAlmostEqual(result["standard_error"], fit.bse[3], places=10)
        self.assertAlmostEqual(result["p_value"], fit.pvalues[3], places=10)

    def test_did_refuses_staggered_timing_duplicates_and_missing_unit_period(self):
        rows = runtime._rows(self.data)
        for mutate in (lambda changed: changed[0].update(period="third-period"),
                       lambda changed: changed[1].update(period="pre"),
                       lambda changed: changed[1].update(treated="0")):
            changed = copy.deepcopy(rows); mutate(changed)
            self.csv(list(changed[0]), [list(row.values()) for row in changed])
            with self.assertRaises(ValueError):
                self.calculate()

    def test_did_refuses_insufficient_clusters_and_blank_or_nonfinite_values(self):
        self.spec["minimum_clusters"] = 30
        with self.assertRaisesRegex(ValueError, "insufficient independent clusters"):
            self.calculate()
        self.spec["minimum_clusters"] = 10
        rows = runtime._rows(self.data)
        for value in ("", "NaN", "Inf", "not-measured"):
            changed = copy.deepcopy(rows); changed[0]["outcome"] = value
            self.csv(list(changed[0]), [list(row.values()) for row in changed])
            with self.assertRaisesRegex(ValueError, "finite numeric"):
                self.calculate()

    @unittest.skipUnless(REFERENCE, "independent statsmodels IV reference runs on cloud scientific job")
    def test_iv_estimate_and_homoskedastic_standard_error_match_statsmodels_iv2sls(self):
        import numpy as np
        from statsmodels.sandbox.regression.gmm import IV2SLS
        rows = self.iv()
        x = np.asarray([[1, row[2]] for row in rows])
        z = np.asarray([[1, row[1]] for row in rows])
        fit = IV2SLS([row[3] for row in rows], x, z).fit()
        result = self.calculate()
        self.assertAlmostEqual(result["estimate"], fit.params[1], places=10)
        self.assertAlmostEqual(result["standard_error"], fit.bse[1], places=10)
        self.assertAlmostEqual(result["p_value"], fit.pvalues[1], places=10)
        self.assertEqual(result["diagnostics"]["weak_iv_robust_confidence_set"], "not_implemented")
        self.assertFalse(result["diagnostics"]["instrument_validity_verified"])

    def test_weak_iv_and_heteroskedastic_route_cannot_silently_pass(self):
        self.iv()
        self.spec["minimum_first_stage_f"] = 10 ** 10
        with self.assertRaisesRegex(ValueError, "weak-IV-robust"):
            self.calculate()
        self.spec["minimum_first_stage_f"] = 10
        self.spec["covariance"] = "HC1"
        with self.assertRaisesRegex(ValueError, "homoskedastic"):
            self.calculate()

    @unittest.skipUnless(REFERENCE, "independent statsmodels WLS reference runs on cloud scientific job")
    def test_fixed_bandwidth_sharp_rdd_matches_independent_wls_hc1(self):
        import numpy as np
        import statsmodels.api as sm
        rows = self.rdd()
        selected = [row for row in rows if abs(row[1]) < 1.5]
        x = np.asarray([[1, row[2], row[1], row[1] * row[2]] for row in selected])
        fit = sm.WLS([row[3] for row in selected], x, weights=[1 - abs(row[1]) / 1.5 for row in selected]).fit(cov_type="HC1", use_t=True)
        result = self.calculate()
        self.assertAlmostEqual(result["estimate"], fit.params[1], places=10)
        self.assertAlmostEqual(result["standard_error"], fit.bse[1], places=10)
        self.assertAlmostEqual(result["p_value"], fit.pvalues[1], places=10)
        self.assertEqual(result["n_observations"], len(selected))
        self.assertEqual(result["diagnostics"]["outside_bandwidth_observations"], len(rows) - len(selected))
        self.assertFalse(result["diagnostics"]["bias_corrected_interval"])

    def test_fuzzy_rdd_and_empty_bandwidth_are_refused(self):
        rows = self.rdd(); rows[0][2] = 1
        self.csv(["unit", "running", "treated", "y"], rows)
        with self.assertRaisesRegex(ValueError, "fuzzy RDD"):
            self.calculate()
        self.rdd(); self.spec["bandwidth"] = 0.01
        with self.assertRaisesRegex(ValueError, "insufficient RDD"):
            self.calculate()

    def test_collinear_controls_cannot_receive_a_pseudoinverse_result(self):
        self.spec["covariates"] = ["treated"]
        with self.assertRaisesRegex(ValueError, "collinear"):
            self.calculate()

    def test_runtime_requires_matching_executor_and_preserves_existing_outputs(self):
        args = ["runtime", "--design", "papers/P01/empirical-design.json", "--data", self.card["data"]["path"],
                "--spec", self.spec["id"], "--output", self.spec["output"]]
        with patch.object(sys, "argv", args), patch.object(runtime.Path, "cwd", return_value=self.project), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "approved cloud executor"):
                runtime.main()
        with patch.object(sys, "argv", args), patch.object(runtime.Path, "cwd", return_value=self.project), patch.dict(os.environ, {"RESEARCH_OS_RUN_ID": self.spec["run_id"]}):
            runtime.main()
            before = (self.project / self.spec["output"]).read_bytes()
            with self.assertRaisesRegex(ValueError, "never overwrite"):
                runtime.main()
            self.assertEqual((self.project / self.spec["output"]).read_bytes(), before)

    def test_same_input_recomputation_is_deterministic_and_source_change_fails(self):
        first = self.calculate(); second = self.calculate()
        self.assertEqual(first, second)
        self.data.write_bytes(self.data.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "hash changed"):
            self.calculate()


if __name__ == "__main__":
    unittest.main()
