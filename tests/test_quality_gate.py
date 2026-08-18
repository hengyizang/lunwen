import unittest
from scripts.quality_gate import validate_report
BASE={"schema_version":"1.0","status":"ready_for_review","novelty_claim":"Comparative gap supported by primary studies.","feasibility_claim":"Executable with public data and bounded compute.","scientific_contribution":"A falsifiable methodological contribution.","novelty_basis":"comparative_primary_literature","novelty_is_absence_only":False,"evidence":[{"id":"E1","source":"doi:1","claim_supported":"gap","source_date":"2026-01-01"},{"id":"E2","source":"doi:2","claim_supported":"baseline","source_date":"2026-02-01"},{"id":"E3","source":"doi:3","claim_supported":"trend","source_date":"2026-03-01"}],"q1_target":{"candidate_venues":[{"quartile":"Q1","indexing":"SCIE","source_url":"https://example.org/jcr-a"},{"quartile":"Q1","indexing":"SCIE","source_url":"https://example.org/jcr-b"}],"current_verification_required":True},"blockers":[],"human_review_required":True}
D={"G1":("novelty","doctoral_depth","significance","feasibility","evidence_strength","publication_potential"),"G2":("novelty","distinct_contribution","significance","feasibility","methodological_rigor","q1_fit"),"G3":("novelty","feasibility","methodological_rigor","statistical_rigor","data_quality","reproducibility","q1_fit"),"G4":("novelty_supported","effect_robustness","statistical_rigor","reproducibility","claim_evidence_strength","q1_fit"),"G5":("novelty","scientific_contribution","methodological_rigor","evidence_strength","q1_fit","review_resilience","writing_quality")}
def report(g):
 r=dict(BASE);r["gate"]=g;r["scores"]={x:9.0 for x in D[g]};return r
class QualityGateTests(unittest.TestCase):
 def test_all_gates_pass(self):
  for g in D:self.assertEqual(validate_report(report(g),g),[])
 def test_low_novelty_blocks(self):self.assertTrue(any("novelty" in e for e in validate_report({**report("G1"),"scores":{**report("G1")["scores"],"novelty":7.9}},"G1")))
 def test_low_overall_blocks(self):
  r=report("G3");r["scores"]={k:8.0 for k in r["scores"]};self.assertTrue(any("overall mean" in e for e in validate_report(r,"G3")))
 def test_absence_only_blocks(self):
  r=report("G2");r["novelty_is_absence_only"]=True;self.assertTrue(any("absence_only" in e for e in validate_report(r,"G2")))
 def test_non_q1_blocks(self):
  r=report("G5");r["q1_target"]["candidate_venues"][0]["quartile"]="Q2";self.assertTrue(any("Q1" in e for e in validate_report(r,"G5")))
if __name__=="__main__":unittest.main()
