import unittest
from datetime import datetime,timedelta,timezone
from scripts import api_orchestrator
from scripts.jcr_verify import verify as verify_payload, JcrVerificationError
class V1GuardTests(unittest.TestCase):
    def test_actual_lower_ranking_low_if_and_ssci_are_recordable_observations(self):
        p=valid_jcr();p.update(impact_factor=0.5,quartile="Q4",indexing="SSCI")
        observations=verify_payload(p)
        self.assertTrue(any("Q4" in issue and "Q1" in issue for issue in observations))
    def test_jcr_rejects_fabricated_or_nonfinite_metrics(self):
        for value in (-1,float("nan"),float("inf"),True):
            p=valid_jcr();p["impact_factor"]=value
            with self.subTest(value=value),self.assertRaises(JcrVerificationError):verify_payload(p)
    def test_jcr_rejects_future_edition_or_verification(self):
        for update in ({"verification_year":datetime.now(timezone.utc).year+1},
                       {"verified_at":(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()}):
            p=valid_jcr();p.update(update)
            with self.subTest(update=update),self.assertRaises(JcrVerificationError):verify_payload(p)
    def test_jcr_accepts_q1_with_if_above_one(self):
        p=valid_jcr();p["impact_factor"]=1.01
        verify_payload(p)
    def test_jcr_accepts_q2_for_declared_q2_paper(self):
        p=valid_jcr();p["quartile"]="Q2"
        verify_payload(p,"Q2")
    def test_old_record_is_preserved_without_claiming_current_ranking(self):
        p=valid_jcr();p.update(verification_year=2020,verified_at="2020-11-01T00:00:00+00:00")
        self.assertTrue(any("current ranking remains unknown" in issue for issue in verify_payload(p)))
    def test_jcr_rejects_missing_category_or_invalid_quartile(self):
        p=valid_jcr();p["category"]=""
        with self.assertRaises(JcrVerificationError):verify_payload(p)
        p=valid_jcr();p["quartile"]="SJR Q1"
        with self.assertRaises(JcrVerificationError):verify_payload(p)
    def test_api_path_protection(self):
        with self.assertRaises(ValueError):api_orchestrator.safe_target("demo","../outside.txt")
        with self.assertRaises(ValueError):api_orchestrator.safe_target("demo",".env")
def valid_jcr():
    now=datetime.now(timezone.utc).replace(microsecond=0)
    return {"schema_version":"1.0","database":"Clarivate Journal Citation Reports","verification_year":now.year,"impact_factor":5.0,"quartile":"Q1","category":"Engineering, Mechanical","indexing":"SCIE","source_url":"https://example.org/jcr","verified_by":"tester","verified_at":now.isoformat()}
