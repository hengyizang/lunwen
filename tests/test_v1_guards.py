import json,tempfile,unittest
from pathlib import Path
from scripts import api_orchestrator
from scripts.researchctl import ResearchCtlError
from scripts.submission_guard import verify_jcr
class V1GuardTests(unittest.TestCase):
    def test_jcr_rejects_if_not_above_one(self):
        p={"database":"Clarivate Journal Citation Reports","verification_year":2026,"impact_factor":1.0,"quartile":"Q1","category":"Engineering, Mechanical","indexing":"SCIE","source_url":"https://example.org/jcr","verified_by":"tester","verified_at":"2026-08-18T00:00:00+00:00"}
        with self.assertRaises(ResearchCtlError):verify_payload(p)
    def test_jcr_rejects_q2_even_with_high_if(self):
        p={"database":"Clarivate Journal Citation Reports","verification_year":2026,"impact_factor":9.9,"quartile":"Q2","category":"Engineering, Mechanical","indexing":"SCIE","source_url":"https://example.org/jcr","verified_by":"tester","verified_at":"2026-08-18T00:00:00+00:00"}
        with self.assertRaises(ResearchCtlError):verify_payload(p)
    def test_jcr_accepts_q1_with_if_above_one(self):
        p={"database":"Clarivate Journal Citation Reports","verification_year":2026,"impact_factor":1.01,"quartile":"Q1","category":"Engineering, Mechanical","indexing":"SCIE","source_url":"https://example.org/jcr","verified_by":"tester","verified_at":"2026-08-18T00:00:00+00:00"}
        verify_payload(p)
    def test_api_path_protection(self):
        with self.assertRaises(ValueError):api_orchestrator.safe_target("demo","../outside.txt")
        with self.assertRaises(ValueError):api_orchestrator.safe_target("demo",".env")
def verify_payload(payload):
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/"jcr.json";path.write_text(json.dumps(payload),encoding="utf-8");verify_jcr(path)
if __name__=="__main__":unittest.main()
