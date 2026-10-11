"""Known-value, adverse, non-paired and pseudoreplication checks for Welch analysis."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scipy import stats
from scripts import experiment_evidence as evidence
from scripts.research_artifacts import sha


class IndependentStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.a, self.b = [1, 3, 6, 8], [0, 1, 3, 4, 6]
        for arm, values, prefix in (("treatment", self.a, "T"), ("comparator", self.b, "C")):
            (self.project / f"{arm}.csv").write_text("unit,value\n" + ''.join(f"{prefix}{i},{v}\n" for i,v in enumerate(values)))
        self.comp = {"analysis_mode": "welch_t", "unit_design": "independent", "unit_column": "unit", "value_column": "value",
                     "direction": "higher", "minimum_units": 3, "alpha": .05, "minimum_effect": 0, "decision_rule": "superiority",
                     "aggregation": "mean_within_unit_then_mean_across_seeds", "pairs": [
                         {"seed": seed, "treatment": {"output": "treatment.csv"}, "comparator": {"output": "comparator.csv"}}
                         for seed in (1, 2, 3)]}

    def measure(self, family=1):
        def bound(project, item, registry, plan_hash):
            target = project / item["output"]
            return target, {"path": item["output"], "sha256": sha(target)}
        with patch.object(evidence, "_bound_output", side_effect=bound):
            return evidence._measure(self.project, self.comp, [], "synthetic", family)

    def test_unequal_arm_sizes_match_independent_scipy_reference(self):
        row = self.measure()
        expected = stats.ttest_ind(self.a, self.b, equal_var=False)
        interval = expected.confidence_interval()
        self.assertAlmostEqual(row["ci_low"], interval.low)
        self.assertAlmostEqual(row["ci_high"], interval.high)
        self.assertAlmostEqual(row["p_value"], stats.ttest_ind(self.a, self.b, equal_var=False, alternative="greater").pvalue)
        self.assertEqual(row["independent_units"], 9)
        self.assertEqual(row["independent_units_by_arm"], {"treatment": 4, "comparator": 5})
        self.assertEqual(row["seeds"], 3)

    def test_threshold_tost_direction_and_family_coverage(self):
        self.comp.update(minimum_effect=1.5)
        row = self.measure(family=3)
        shifted = [x - 1.5 for x in self.a]
        self.assertAlmostEqual(row["p_value"], stats.ttest_ind(shifted, self.b, equal_var=False, alternative="greater").pvalue)
        self.assertAlmostEqual(row["ci_confidence"], 1-.05/3)
        self.comp.update(decision_rule="equivalence", minimum_effect=5)
        expected = max(stats.ttest_ind([x+5 for x in self.a], self.b, equal_var=False, alternative="greater").pvalue,
                       stats.ttest_ind([x-5 for x in self.a], self.b, equal_var=False, alternative="less").pvalue)
        self.assertAlmostEqual(self.measure()["p_value"], expected)
        before = self.measure()
        self.comp["direction"] = "lower"
        after = self.measure()
        self.assertAlmostEqual(after["estimate"], -before["estimate"])
        self.assertAlmostEqual(after["ci_low"], -before["ci_high"])

    def test_overlapping_units_and_insufficient_arm_are_rejected(self):
        path = self.project / 'comparator.csv'
        path.write_text(path.read_text().replace('C0', 'T0'))
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.measure()
        path.write_text('unit,value\nC0,0\nC1,1\n')
        with self.assertRaisesRegex(ValueError, "per arm"):
            self.measure()

    def test_changing_unit_coverage_is_not_silently_dropped(self):
        (self.project / 'other.csv').write_text('unit,value\nZ1,1\nZ2,2\nZ3,3\n')
        self.comp['pairs'][1]['treatment']['output'] = 'other.csv'
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.measure()

    def test_unregistered_mode_and_nonfinite_values_are_rejected(self):
        self.comp['analysis_mode'] = 'invented_test'
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.measure()
        self.comp['analysis_mode'] = 'welch_t'
        path = self.project / 'treatment.csv'
        path.write_text(path.read_text().replace('T0,1', 'T0,nan'))
        with self.assertRaises(ValueError):
            self.measure()
