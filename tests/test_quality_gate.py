import unittest

from scripts.quality_gate import validate_report


BASE = {
    "schema_version": "1.0",
    "status": "ready_for_review",
    "novelty_claim": "A comparative gap supported by primary studies.",
    "feasibility_claim": "The proposed work is executable with public data and bounded compute.",
    "scientific_contribution": "A falsifiable methodological contribution.",
    "novelty_basis": "comparative_primary_literature",
    "novelty_is_absence_only": False,
    "evidence": [
        {"id": "E1", "source": "doi:1", "claim_supported": "gap", "source_date": "2026-01-01"},
        {"id": "E2", "source": "doi:2", "claim_supported": "baseline", "source_date": "2026-02-01"},
        {"id": "E3", "source": "doi:3", "claim_supported": "trend", "source_date": "2026-03-01"},
    ],
    "q1_target": {
        "candidate_venues": [
            {"quartile": "Q1", "indexing": "SCIE", "source_url": "https://example.org/jcr-a"},
            {"quartile": "Q1", "indexing": "SCIE", "source_url": "https://example.org/jcr-b"},
        ],
        "current_verification_required": True,
    },
    "blockers": [],
    "human_review_required": True,
}


def report(gate, scores=None):
    value = dict(BASE)
    value["gate"] = gate
    names = {
        "G1": ("novelty", "doctoral_depth", "significance", "feasibility", "evidence_strength", "publication_potential"),
        "G2": ("novelty", "distinct_contribution", "significance", "feasibility", "methodological_rigor", "q1_fit"),
        "G3": ("novelty", "feasibility", "methodological_rigor", "statistical_rigor", "data_quality", "reproducibility", "q1_fit"),
        "G4": ("novelty_supported", "effect_robustness", "statistical_rigor", "reproducibility", "claim_evidence_strength", "q1_fit"),
        "G5": ("novelty", "scientific_contribution", "methodological_rigor", "evidence_strength", "q1_fit", "review_resilience", "writing_quality"),
    }
    value["scores"] = {name: 9.0 for name in names[gate]}
    if scores: value["scores"].update(scores)
    return value


class QualityGateTests(unittest.TestCase):
    def test_all_gates_pass_strong_report(self):
        for gate in ("G1", "G2", "G3", "G4", "G5"):
            self.assertEqual(validate_report(report(gate), gate), [])

    def test_low_novelty_blocks_gate(self):
        errors = validate_report(report("G1", {"novelty": 7.9}), "G1")
        self.assertTrue(any("novelty" in error for error in errors))

    def test_low_overall_blocks_gate(self):
        errors = validate_report(report("G3", {name: 8.0 for name in report("G3")["scores"]}), "G3")
        self.assertTrue(any("overall mean" in error for error in errors))

    def test_absence_only_novelty_blocks_gate(self):
        value = report("G2")
        value["novelty_is_absence_only"] = True
        self.assertTrue(any("absence_only" in error for error in validate_report(value, "G2")))

    def test_non_q1_target_blocks_gate(self):
        value = report("G5")
        value["q1_target"]["candidate_venues"][0]["quartile"] = "Q2"
        self.assertTrue(any("Q1" in error for error in validate_report(value, "G5")))


if __name__ == "__main__":
    unittest.main()
