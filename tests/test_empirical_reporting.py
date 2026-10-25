"""Synthetic sealed reporting checks; estimator accuracy is tested separately."""
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import empirical_reporting as reporting
from scripts.research_artifacts import read, sha, write
from scripts.statistical_reporting import display_value
from tests.figure_lineage_fixtures import sealed_run


class EmpiricalReportingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.paper = self.project/"papers/P01"; self.paper.mkdir(parents=True)
        source = self.project/"data/raw/fixture.csv"; source.parent.mkdir(parents=True)
        source.write_text("id,y\na,1\nb,2\n", encoding="utf-8")
        self.outputs = {}
        self.specs = []
        for identifier, estimate, p_value, phase in (("main", -0.4, 0.01, "confirmatory"),
                ("adverse", -0.8, 0.03, "confirmatory"), ("sensitivity", 0.5, 0.02, "confirmatory"),
                ("exploratory", 10.0, 0.001, "exploratory")):
            self.specs.append({"id": identifier, "run_id": "run-"+identifier, "method": "did_2x2", "phase": phase,
                "family": "registered-family", "output": f"papers/P01/results/{identifier}.json"})
            self.outputs[identifier] = {"paper_id": "P01", "specification_id": identifier, "estimate": estimate,
                "standard_error": 0.2, "confidence_interval": [estimate-0.4, estimate+0.4],
                "confidence_level": 0.95, "p_value": p_value, "n_observations": 40, "n_units": 20,
                "phase": phase, "scientific_validity_verified": False}
            write(self.project/self.specs[-1]["output"], self.outputs[identifier])
        self.diagnostic = {"id": "timing", "run_id": "run-diagnostic", "output": "papers/P01/results/timing.json"}
        self.diagnostic_result = {"diagnostic_id": "timing", "passed": True,
            "details": {"synthetic_fixture_only": True, "pre_periods": 1, "post_periods": 1}}
        write(self.project/self.diagnostic["output"], self.diagnostic_result)
        self.card = {"schema_version": "1.0", "paper_id": "P01", "data": {"path": "data/raw/fixture.csv", "sha256": sha(source)},
            "specifications": self.specs, "diagnostics": [self.diagnostic]}
        write(self.paper/"empirical-design.json", self.card)
        self.seal_all()
        design = patch("scripts.empirical_design.audit", return_value={"errors": [], "pass": True})
        calculate = patch("scripts.empirical_runtime.calculate", side_effect=lambda card, spec, path, **kw: copy.deepcopy(self.outputs[spec["id"]]))
        design.start(); calculate.start(); self.addCleanup(design.stop); self.addCleanup(calculate.stop)

    def seal_all(self):
        # Keep real plan, G3, preregistration, registry and per-attempt receipt
        # checks. Only causal-design and estimator arithmetic are isolated.
        first = self.specs[0]
        run, approval, receipt = sealed_run(self.project, run_id=first["run_id"], output=first["output"])
        runs, receipts = [], []
        for item in [*self.specs, self.diagnostic]:
            current = copy.deepcopy(run); current.update(run_id=item["run_id"], expected_outputs=[item["output"]])
            runs.append(current)
            recorded = copy.deepcopy(receipt); recorded.update(run_id=item["run_id"], attempt_id=item["run_id"]+"-attempt-001",
                outputs=[{"path": item["output"], "sha256": sha(self.project/item["output"])}])
            receipts.append(recorded)
        plan_path = self.project/"experiments/plan.json"
        write(plan_path, {"schema_version": "1.0", "runs": runs})
        prereg_path = self.paper/"preregistration.json"
        prereg = read(prereg_path)
        prereg["files"] = [{"path": item["path"], "sha256": sha(self.project/item["path"])} for item in prereg["files"]]
        prereg["files"].extend({"path": relative, "sha256": sha(self.project/relative)}
            for relative in ("papers/P01/empirical-design.json", "data/raw/fixture.csv"))
        write(prereg_path, prereg)
        approval["experiment_plan_sha256"] = sha(plan_path)
        approval["frozen_protocol_sha256"]["papers/P01/preregistration.json"] = sha(prereg_path)
        state = read(self.project/"state/run.json"); state["approvals"] = [approval]
        write(self.project/"state/run.json", state)
        for current in receipts:
            current["approved_plan_sha256"] = sha(plan_path)
            write(self.project/f"experiments/runs/{current['attempt_id']}/run.json", current)
        self.receipts = receipts
        self.registry = self.project/"experiments/registry.jsonl"
        self.registry.write_text("".join(json.dumps(item)+"\n" for item in receipts), encoding="utf-8")

    def rows(self):
        result = reporting.audit(self.project, "P01")
        self.assertEqual(result["errors"], [], result)
        return result["rows"]

    def prepare_map(self):
        rows = self.rows()
        lines, entries = [], []
        for row in rows:
            locations = []
            for field in (*reporting.FIELDS, "phase"):
                literal = display_value(row[field], 6)
                quote = row["specification_id"] + " " + field + " = " + literal
                lines.append(quote)
                locations.append({"field": field, "path": "papers/P01/manuscript/main.md", "locator": "L"+str(len(lines)),
                    "quote": quote, "decimals": 6})
            entries.append({"id": row["specification_id"], "locations": locations})
        manuscript = self.paper/"manuscript/main.md"; manuscript.parent.mkdir(parents=True, exist_ok=True)
        manuscript.write_text("\n".join(lines)+"\n", encoding="utf-8")
        for item in entries:
            for location in item["locations"]: location["sha256"] = sha(manuscript)
        mapping = {"schema_version": "1.0", "paper_id": "P01", "specifications": entries}
        write(self.paper/"empirical-reporting-map.json", mapping)
        return mapping, manuscript

    def test_real_seals_all_specs_negative_estimates_and_phases_are_preserved(self):
        result = reporting.audit(self.project, "P01")
        self.assertEqual(result["status"], "ready_for_scientific_review", result)
        self.assertEqual({r["specification_id"] for r in result["rows"]}, {s["id"] for s in self.specs})
        self.assertEqual(result["rows"][1]["estimate"], -0.8)
        self.assertEqual(result["rows"][-1]["phase"], "exploratory")
        self.assertTrue(all(r["executor"]["attempt_id"] for r in result["rows"]))
        self.assertFalse(result["scientific_validity_verified"])
        self.assertFalse(result["scientific_completion_verified"])
        self.assertEqual(result["paid_calls"], 0)

    def test_holm_adjustment_is_monotone_and_exploratory_family_is_separate(self):
        indexed = {row["specification_id"]: row for row in self.rows()}
        self.assertAlmostEqual(indexed["main"]["p_adjusted"], 0.03)
        self.assertAlmostEqual(indexed["sensitivity"]["p_adjusted"], 0.04)
        self.assertAlmostEqual(indexed["adverse"]["p_adjusted"], 0.04)
        self.assertAlmostEqual(indexed["exploratory"]["p_adjusted"], 0.001)

    def test_missing_or_changed_executor_output_is_blocked(self):
        source = self.project/self.specs[0]["output"]
        source.write_text('{"estimate": 999}', encoding="utf-8")
        self.assertTrue(reporting.audit(self.project, "P01")["errors"])
        source.unlink()
        self.assertTrue(reporting.audit(self.project, "P01")["errors"])

    def test_registry_forgery_disagrees_with_real_executor_receipt(self):
        altered = copy.deepcopy(self.receipts); altered[0]["exit_code"] = 1
        self.registry.write_text("".join(json.dumps(item)+"\n" for item in altered), encoding="utf-8")
        self.assertTrue(reporting.audit(self.project, "P01")["errors"])

    def test_failed_integrity_cannot_be_promoted_by_success_status(self):
        altered = copy.deepcopy(self.receipts); altered[0]["input_integrity"]["passed"] = False
        for item in altered:
            write(self.project/f"experiments/runs/{item['attempt_id']}/run.json", item)
        self.registry.write_text("".join(json.dumps(item)+"\n" for item in altered), encoding="utf-8")
        self.assertTrue(reporting.audit(self.project, "P01")["errors"])

    def test_freshly_resealed_wrong_estimate_is_rejected_by_recomputation(self):
        path = self.project/self.specs[0]["output"]
        altered = copy.deepcopy(self.outputs["main"]); altered["estimate"] = 999
        write(path, altered); self.seal_all()
        self.assertTrue(any("recomputation" in x for x in reporting.audit(self.project, "P01")["errors"]))

    def test_diagnostic_failure_missing_details_or_fake_boolean_is_blocked(self):
        for change in ({"passed": False}, {"details": {}}, {"passed": "true"}, {"diagnostic_id": "different"}):
            value = {**copy.deepcopy(self.diagnostic_result), **change}
            write(self.project/self.diagnostic["output"], value); self.seal_all()
            self.assertTrue(reporting.audit(self.project, "P01")["errors"], change)

    def test_missing_diagnostic_output_blocks_before_a_result_table_is_written(self):
        (self.project/self.diagnostic["output"]).unlink()
        result = reporting.refresh(self.project, "P01")
        self.assertTrue(result["errors"])
        self.assertFalse((self.paper/"tables/empirical-estimates.csv").exists())

    def test_table_is_deterministic_and_changed_estimate_is_rejected(self):
        first = reporting.refresh(self.project, "P01")
        table = self.paper/"tables/empirical-estimates.csv"; payload = table.read_bytes()
        second = reporting.refresh(self.project, "P01")
        self.assertEqual(first, second)
        self.assertEqual(payload, table.read_bytes())
        self.assertEqual(reporting.validate_saved_report(self.project, "P01"), [])
        values = list(csv.DictReader(io.StringIO(payload.decode())))
        self.assertEqual(len(values), 4)
        self.assertEqual(values[-1]["phase"], "exploratory")
        table.write_text(table.read_text().replace("-0.8", "0.8"), encoding="utf-8")
        self.assertTrue(any("table differs" in x for x in reporting.validate_saved_report(self.project, "P01")))

    def test_complete_source_located_map_can_be_validated(self):
        self.prepare_map()
        result = reporting.refresh(self.project, "P01", require_mapping=True)
        self.assertEqual(result["errors"], [], result)
        self.assertEqual(reporting.validate_saved_report(self.project, "P01", require_mapping=True), [])

    def test_required_mapping_is_not_optional_at_submission(self):
        self.assertTrue(reporting.audit(self.project, "P01", require_mapping=True)["errors"])

    def test_tiny_positive_p_values_can_use_verified_scientific_notation(self):
        self.outputs["main"]["p_value"] = 1e-16
        write(self.project/self.specs[0]["output"], self.outputs["main"])
        self.seal_all()
        rows = {r["specification_id"]: r for r in self.rows()}
        mapping, manuscript = self.prepare_map()
        lines = manuscript.read_text(encoding="utf-8").splitlines()
        for item in mapping["specifications"]:
            for location in item["locations"]:
                if item["id"] == "main" and location["field"] in {"p_value", "p_adjusted"}:
                    location["notation"] = "scientific"
                    location["quote"] = "main " + location["field"] + " = " + format(rows["main"][location["field"]], ".6e")
                    lines[int(location["locator"][1:])-1] = location["quote"]
        manuscript.write_text("\n".join(lines)+"\n", encoding="utf-8")
        for item in mapping["specifications"]:
            for location in item["locations"]:
                location["sha256"] = sha(manuscript)
        write(self.paper/"empirical-reporting-map.json", mapping)
        self.assertEqual(reporting.audit(self.project, "P01", require_mapping=True)["errors"], [])

    def test_map_cannot_omit_exploratory_or_unfavorable_specifications(self):
        mapping, _ = self.prepare_map()
        for identifier in ("exploratory", "adverse"):
            changed = copy.deepcopy(mapping)
            changed["specifications"] = [item for item in changed["specifications"] if item["id"] != identifier]
            write(self.paper/"empirical-reporting-map.json", changed)
            self.assertTrue(reporting.audit(self.project, "P01", require_mapping=True)["errors"])

    def test_map_wrong_literal_wrong_paper_or_stale_source_is_blocked(self):
        mapping, manuscript = self.prepare_map()
        original = manuscript.read_text()
        for mutate in (lambda value: value["specifications"][0]["locations"][0].update(path="papers/P02/manuscript/main.md"),
                       lambda value: value.update(paper_id="P02"),
                       lambda value: value["specifications"][0]["locations"][0].update(sha256="0"*64)):
            changed = copy.deepcopy(mapping); mutate(changed)
            write(self.paper/"empirical-reporting-map.json", changed)
            self.assertTrue(reporting.audit(self.project, "P01", require_mapping=True)["errors"])
        changed = copy.deepcopy(mapping)
        manuscript.write_text(original.replace("main estimate = -0.4", "main estimate = -0.3"), encoding="utf-8")
        for item in changed["specifications"]:
            for location in item["locations"]: location["sha256"] = sha(manuscript)
        changed["specifications"][0]["locations"][0]["quote"] = "main estimate = -0.3"
        write(self.paper/"empirical-reporting-map.json", changed)
        self.assertTrue(any("reported number differs" in x for x in reporting.audit(self.project, "P01", require_mapping=True)["errors"]))

    def test_map_numeric_suffix_cannot_match_a_different_literal(self):
        mapping, manuscript = self.prepare_map()
        manuscript.write_text(manuscript.read_text().replace("main estimate = -0.4", "main estimate = -0.45"), encoding="utf-8")
        for item in mapping["specifications"]:
            for location in item["locations"]: location["sha256"] = sha(manuscript)
        mapping["specifications"][0]["locations"][0]["quote"] = "main estimate = -0.45"
        write(self.paper/"empirical-reporting-map.json", mapping)
        self.assertTrue(reporting.audit(self.project, "P01", require_mapping=True)["errors"])

    def test_missing_mapped_field_and_false_analysis_phase_are_blocked(self):
        mapping, manuscript = self.prepare_map()
        incomplete = copy.deepcopy(mapping); incomplete["specifications"][0]["locations"].pop()
        write(self.paper/"empirical-reporting-map.json", incomplete)
        self.assertTrue(reporting.audit(self.project, "P01", require_mapping=True)["errors"])
        manuscript.write_text(manuscript.read_text().replace("exploratory phase = exploratory", "exploratory phase = confirmatory"), encoding="utf-8")
        for item in mapping["specifications"]:
            for location in item["locations"]: location["sha256"] = sha(manuscript)
        mapping["specifications"][-1]["locations"][-1]["quote"] = "exploratory phase = confirmatory"
        write(self.paper/"empirical-reporting-map.json", mapping)
        self.assertTrue(any("analysis phase" in x for x in reporting.audit(self.project, "P01", require_mapping=True)["errors"]))


if __name__ == "__main__": unittest.main()
