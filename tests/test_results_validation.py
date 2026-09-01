from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.results_validation import validate_claim_evidence,validate_registry


class ResultsValidationTests(unittest.TestCase):
    def test_registry_and_claims_form_a_current_evidence_chain(self)->None:
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp)/"study";(project/"experiments").mkdir(parents=True);(project/"state").mkdir();(project/"claims").mkdir();(project/"papers"/"P01").mkdir(parents=True);(project/"results").mkdir()
            output=project/"results"/"metrics.json";output.write_text("{}",encoding="utf-8");output_hash=hashlib.sha256(output.read_bytes()).hexdigest()
            plan={"status":"ready_for_review","runs":[{"run_id":"r1","paper_id":"P01","argv":["python3","analysis.py"],"cwd":".","seed":1,"timeout_seconds":60,"estimated_cost_usd":0,"inputs":[],"expected_outputs":["results/metrics.json"]}]}
            plan_path=project/"experiments"/"plan.json";plan_path.write_text(json.dumps(plan),encoding="utf-8");plan_hash=hashlib.sha256(plan_path.read_bytes()).hexdigest()
            (project/"state"/"run.json").write_text(json.dumps({"approvals":[{"gate":"G3","experiment_plan_sha256":plan_hash}]}),encoding="utf-8")
            registry=[{"schema_version":"1.0","run_id":"r1","attempt_id":"r1-attempt-001","paper_id":"P01","started_at":"2026-01-01T00:00:00+00:00","finished_at":"2026-01-01T00:00:01+00:00","runtime_seconds":1,"status":"succeeded","argv":["python3","analysis.py"],"cwd":".","seed":1,"timeout_seconds":60,"timed_out":False,"estimated_cost_usd":0.0,"inputs":[],"approved_plan_sha256":plan_hash,"outputs":[{"path":"results/metrics.json","sha256":output_hash}],"missing_outputs":[]}]
            contract={"independence":{"unique_claim_ids":["C1"]}};(project/"papers"/"P01"/"paper-contract.json").write_text(json.dumps(contract),encoding="utf-8")
            claim=project/"claims"/"claim-evidence.csv";claim.write_text("claim_id,paper_id,claim,evidence_ids,analysis_ids,support,uncertainty,status\nC1,P01,Improves performance,E1,r1,supported,Sampling uncertainty,ready\n",encoding="utf-8")
            self.assertEqual(validate_registry(project,plan,registry),[])
            self.assertEqual(validate_claim_evidence(project,claim,registry),[])
            output.write_text('{"changed":true}',encoding="utf-8")
            self.assertTrue(any("hash changed" in error for error in validate_registry(project,plan,registry)))


if __name__=="__main__":unittest.main()
