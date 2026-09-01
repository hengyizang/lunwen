import copy
import unittest

from scripts.quality_gate import DIMENSIONS, validate_report


EVIDENCE = [
    {
        "id": f"E{index}",
        "source": f"https://example.org/primary-{index}",
        "claim_supported": f"claim-{index}",
        "source_date": f"2026-0{index}-01",
    }
    for index in range(1, 6)
]

BASE = {
    "schema_version": "1.1",
    "status": "ready_for_review",
    "novelty_claim": "Comparative gap supported by primary studies.",
    "feasibility_claim": "Executable with public data and bounded compute.",
    "scientific_contribution": "A falsifiable methodological contribution.",
    "novelty_basis": "comparative_primary_literature",
    "novelty_is_absence_only": False,
    "evidence": EVIDENCE,
    "originality_assessment": {
        "closest_prior_work_ids": ["W1", "W2", "W3"],
        "adjacent_fields_checked": ["field-a", "field-b", "field-c"],
        "non_novel_elements": ["standard encoder"],
        "differentiating_claims": ["new falsifiable mechanism"],
        "counterevidence_considered": True,
        "residual_risk": "A neighboring field may contain an equivalent formulation.",
    },
    "doctoral_readiness": {
        "unifying_thesis": "A coherent thesis.",
        "original_knowledge_contribution": "A new body of knowledge.",
        "synthesis_beyond_individual_papers": "Cross-paper synthesis.",
        "methodological_progression": "Increasingly demanding validation.",
        "scope_boundaries": "Bounded to authorized industrial datasets.",
        "examiner_challenges": ["novelty", "causality", "generalization"],
    },
    "venue_readiness": {
        "minimum_jcr_quartile": "Q1",
        "preferred_jcr_quartile": "Q1",
        "candidate_venues": [
            {
                "name": "Journal A",
                "quartile": "Q1",
                "indexing": "SCIE",
                "category": "Engineering",
                "jcr_year": 2026,
                "source_url": "https://example.org/jcr-a",
                "scope_fit": "Industrial AI",
                "article_type": "Original article",
            },
            {
                "name": "Journal B",
                "quartile": "Q1",
                "indexing": "SCIE",
                "category": "Engineering",
                "jcr_year": 2026,
                "source_url": "https://example.org/jcr-b",
                "scope_fit": "Predictive maintenance",
                "article_type": "Original article",
            },
        ],
        "current_verification_required": True,
        "venue_specific_guidelines_required": True,
    },
    "blockers": [],
    "human_review_required": True,
}


def report(gate):
    value = copy.deepcopy(BASE)
    value["gate"] = gate
    value["scores"] = {field: 9.0 for field in DIMENSIONS[gate]}
    return value


class QualityGateTests(unittest.TestCase):
    def test_all_gates_pass(self):
        for gate in DIMENSIONS:
            self.assertEqual(validate_report(report(gate), gate), [])

    def test_low_novelty_blocks(self):
        value = report("G1")
        value["scores"]["novelty"] = 7.9
        self.assertTrue(any("novelty" in error for error in validate_report(value, "G1")))

    def test_low_overall_blocks(self):
        value = report("G3")
        value["scores"] = {key: 8.0 for key in value["scores"]}
        self.assertTrue(any("overall mean" in error for error in validate_report(value, "G3")))

    def test_absence_only_blocks(self):
        value = report("G2")
        value["novelty_is_absence_only"] = True
        self.assertTrue(any("absence_only" in error for error in validate_report(value, "G2")))

    def test_q1_candidates_are_accepted(self):
        self.assertEqual(validate_report(report("G5"), "G5"), [])

    def test_q2_candidate_blocks(self):
        value = report("G5")
        value["venue_readiness"]["candidate_venues"][1]["quartile"] = "Q2"
        self.assertTrue(any("current JCR Q1" in error for error in validate_report(value, "G5")))

    def test_doctoral_case_is_required(self):
        value = report("G1")
        value["doctoral_readiness"]["unifying_thesis"] = ""
        self.assertTrue(any("unifying_thesis" in error for error in validate_report(value, "G1")))


if __name__ == "__main__":
    unittest.main()
