"""Task comparisons include actual relay debits and rejected-response costs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import calibration_analysis


class ProductionCalibrationCostTests(unittest.TestCase):
    def row(self, cost=0.12, provider="codekey-deepseek"):
        return {"run_id":"R1","request_id":"request-1","provider":provider,
                "model":"fixture-model","stage":"auxiliary","role":"fixture-role",
                "cost_cny":cost,"usage_estimated":False,"cost_status":"settled_gateway_debit",
                "billing":{"independent_gateway_debit":{"actual_cost_cny":cost,"debit_evidence":{
                    "source":"https://cheapai.info/api/log/token" if provider.startswith("cheapai-") else "https://codekey.ai/v1/usage",
                    "exactly_one_new_gateway_request":True}}}}

    def summary(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);(project/"state").mkdir()
            (project/"state/model-usage.jsonl").write_text("\n".join(json.dumps(r) for r in rows),encoding="utf-8")
            return calibration_analysis.cost_summary(project,{"cost_run_ids":["R1"]},
                {"answer_key":[{"candidate":{"run_ids":["R1"]}}]},1)

    def test_actual_relay_costs_and_cache_hits_are_counted_without_claiming_total_scope(self):
        rows=[self.row(),self.row(0.03,"cheapai-gpt-pro"),{"run_id":"R1","cache_hit":True,"cost_cny":0}]
        value=self.summary(rows)
        self.assertTrue(value["model_cost_coverage_complete"])
        self.assertEqual(value["known_model_cost_cny"],0.15)
        self.assertEqual(value["model_cost_per_qualified_candidate_cny"],0.15)
        self.assertEqual(value["recorded_calls"],3)
        self.assertIsNone(value["total_cash_cost_per_qualified_candidate_cny"])
        self.assertFalse(value["scope_confirmed_by_owner_record"])

    def test_unverified_or_mismatched_gateway_labels_are_not_settled_costs(self):
        variants=[]
        row=self.row();row.pop("billing");variants.append(row)
        row=self.row();row["billing"]["independent_gateway_debit"]["actual_cost_cny"]=0.5;variants.append(row)
        row=self.row();row["billing"]["independent_gateway_debit"]["debit_evidence"]["exactly_one_new_gateway_request"]=False;variants.append(row)
        row=self.row();row["billing"]["independent_gateway_debit"]["debit_evidence"]["source"]="https://other.example";variants.append(row)
        row=self.row();row["usage_estimated"]=True;variants.append(row)
        row=self.row();row["cost_cny"]=True;variants.append(row)
        row=self.row();row.update(cost_cny=0,cache_hit=True,cost_status="unknown_reconcile_required");variants.append(row)
        row=self.row();row.update(cost_cny=0,cache_hit=True);row.pop("billing");variants.append(row)
        for row in variants:
            with self.subTest(row=row):
                value=self.summary([row])
                self.assertFalse(value["model_cost_coverage_complete"])
                self.assertIsNone(value["model_cost_per_qualified_candidate_cny"])

    def diagnostic(self, row):
        return {**{k:row[k] for k in ("run_id","request_id","provider","model","stage","role")},
                "cost_cny":0,"validation_status":"source_contract_failed_no_retry","not_scientific_evidence":True}

    def test_rejected_answer_retains_its_actual_cost_without_double_counting_diagnostic(self):
        row=self.row();value=self.summary([row,self.diagnostic(row)])
        self.assertTrue(value["model_cost_coverage_complete"])
        self.assertEqual(value["known_model_cost_cny"],0.12)
        self.assertEqual(value["recorded_calls"],1)
        self.assertEqual(value["linked_validation_diagnostics"],1)

    def test_orphan_or_different_request_diagnostic_does_not_hide_an_unknown_cost(self):
        row=self.row();diagnostic=self.diagnostic(row)
        for rows in ([diagnostic],[row,{**diagnostic,"request_id":"different"}],
                     [row,{**diagnostic,"role":"different"}]):
            value=self.summary(rows)
            self.assertFalse(value["model_cost_coverage_complete"])
            self.assertEqual(value["linked_validation_diagnostics"],0)

    def test_unknown_hold_retains_known_cost_but_blocks_cost_ranking(self):
        row=self.row();unknown=copy.deepcopy(row)
        unknown.update(cost_cny=0,cost_status="unknown_reconcile_required",request_id="failed-request")
        value=self.summary([row,unknown])
        self.assertEqual(value["known_model_cost_cny"],0.12)
        self.assertFalse(value["model_cost_coverage_complete"])
        self.assertIsNone(value["model_cost_per_qualified_candidate_cny"])


if __name__=="__main__":
    unittest.main()
