import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.quality_gate import DIMENSIONS, validate_report, validate_file


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
                "jcr_year": date.today().year,
                "source_url": "https://example.org/jcr-a",
                "scope_fit": "Industrial AI",
                "article_type": "Original article",
            },
            {
                "name": "Journal B",
                "quartile": "Q1",
                "indexing": "SCIE",
                "category": "Engineering",
                "jcr_year": date.today().year,
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
    def test_only_topic_quality_records_require_human_review(self):
        for gate in ("G1", "G2", "G3", "G4", "G5"):
            value = report(gate)
            value["human_review_required"] = False
            errors = validate_report(value, gate)
            if gate in {"G1", "G2"}:
                self.assertTrue(any("topic decisions" in error for error in errors))
            else:
                self.assertEqual(errors, [])

    def test_current_factual_assessments_replace_scores_and_bind_real_evidence(self):
        import tempfile
        from pathlib import Path
        from scripts.research_artifacts import sha
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / "facts.txt"
            source.write_text("Synthetic evidence for a controlled factual assessment.\n", encoding="utf-8")
            value = report("G3")
            value["schema_version"] = "1.2"
            value["human_review_required"] = False
            value.pop("scores")
            value["assessments"] = {key: {"status": "satisfied", "rationale": "Synthetic located criterion evidence",
                "source_anchors": [{"path": "facts.txt", "sha256": sha(source), "locator": "L1",
                                    "excerpt": "Synthetic evidence for a controlled factual assessment."}]}
                for key in DIMENSIONS["G3"]}
            self.assertEqual(validate_report(value, "G3", project=project, require_facts=True), [])
            value["assessments"]["leakage_control"]["status"] = "unresolved"
            self.assertTrue(validate_report(value, "G3", project=project, require_facts=True))
            value["assessments"]["leakage_control"]["status"] = "satisfied"
            source.write_text("Changed source bytes\n", encoding="utf-8")
            self.assertTrue(validate_report(value, "G3", project=project, require_facts=True))
        warnings = []
        self.assertEqual(validate_report(report("G3"), "G3", require_facts=True, warnings=warnings), [])
        self.assertTrue(any("migration" in note for note in warnings))

    def test_source_bound_novelty_version_preserves_reopened_history_and_blocks_final(self):
        from scripts.research_quality import validate_novelty_claim_matrix
        from tests.test_research_quality import ResearchQualityTests
        originality, matrix = ResearchQualityTests().novelty_inputs()
        matrix.update(schema_version="1.1", status="in_progress")
        saturation = matrix["search_saturation"]
        saturation.update(status="reopened", stopping_rule="time_limit",
            consecutive_no_material_new_work_rounds=0, current_no_material_new_work_round_ids=[],
            affected_claim_ids=["N1"], next_searches=["Read the newly located adjacent work."],
            unresolved_search_gaps=["That work may invalidate the current distinction."])
        retained = copy.deepcopy(matrix)
        self.assertEqual(validate_novelty_claim_matrix(matrix, originality, require_saturation=False), [])
        self.assertEqual(matrix, retained)
        self.assertEqual(len(saturation["no_material_new_work_rounds"]), 2)
        matrix["status"] = "ready_for_review"
        self.assertTrue(any("not currently saturated" in error
                            for error in validate_novelty_claim_matrix(matrix, originality)))

    def test_required_text_rejects_null_and_non_strings(self):
        value = report("G1")
        value["evidence"][0]["source"] = None
        value["novelty_claim"] = None
        value["originality_assessment"]["closest_prior_work_ids"][0] = None
        value["doctoral_readiness"]["unifying_thesis"] = 42
        value["venue_readiness"]["candidate_venues"][0]["name"] = None
        warnings = []
        errors = validate_report(value, "G1", warnings=warnings)
        for expected in ("evidence[1] needs source", "novelty_claim", "closest_prior_work_ids", "unifying_thesis"):
            self.assertTrue(any(expected in error for error in errors), errors)
        self.assertTrue(any("candidate venue 1 needs name" in note for note in warnings))
    def test_all_gates_pass(self):
        for gate in DIMENSIONS:
            self.assertEqual(validate_report(report(gate), gate), [])

    def test_low_novelty_is_an_observation(self):
        value = report("G1")
        value["scores"]["novelty"] = 7.9
        warnings = []
        self.assertEqual(validate_report(value, "G1", warnings=warnings), [])
        self.assertTrue(any("novelty" in note for note in warnings))

    def test_low_overall_is_an_observation(self):
        value = report("G3")
        value["scores"] = {key: 8.0 for key in value["scores"]}
        warnings = []
        self.assertEqual(validate_report(value, "G3", warnings=warnings), [])
        self.assertTrue(any("overall mean" in note for note in warnings))

    def test_absence_only_blocks(self):
        value = report("G2")
        value["novelty_is_absence_only"] = True
        self.assertTrue(any("absence_only" in error for error in validate_report(value, "G2")))

    def test_q1_candidates_are_accepted(self):
        self.assertEqual(validate_report(report("G5"), "G5"), [])

    def test_early_q2_candidate_is_an_observation(self):
        value = report("G5")
        value["venue_readiness"]["candidate_venues"][1]["quartile"] = "Q2"
        warnings = []
        self.assertEqual(validate_report(value, "G5", warnings=warnings), [])
        self.assertTrue(any("JCR Q1 target" in note for note in warnings))

    def test_declared_q2_floor_accepts_q1_and_q2_candidates(self):
        value = report("G5")
        value["venue_readiness"]["minimum_jcr_quartile"] = "Q2"
        value["venue_readiness"]["candidate_venues"][1]["quartile"] = "Q2"
        self.assertEqual(validate_report(value, "G5"), [])

    def test_stale_early_jcr_candidate_year_is_an_observation(self):
        value=report("G1");value["venue_readiness"]["candidate_venues"][0]["jcr_year"]=2020
        warnings = []
        self.assertEqual(validate_report(value, "G1", warnings=warnings), [])
        self.assertTrue(any("current or immediately previous" in note for note in warnings))

    def test_missing_or_malformed_scores_and_early_venues_never_force_fabricated_readiness(self):
        for gate in DIMENSIONS:
            value = report(gate)
            value.pop("scores")
            value.pop("venue_readiness")
            warnings = []
            self.assertEqual(validate_report(value, gate, require_facts=True, warnings=warnings), [])
            self.assertTrue(any("scores" in note for note in warnings))
            self.assertTrue(any("venue_readiness" in note for note in warnings))
            value["scores"] = {field: "unknown" for field in DIMENSIONS[gate]}
            value["venue_readiness"] = {"minimum_jcr_quartile": [], "candidate_venues": 7}
            self.assertEqual(validate_report(value, gate, warnings=warnings), [])

    def test_factual_assessments_need_science_not_early_publication_materials(self):
        from scripts.quality_gate import OBSERVATIONAL_CRITERIA
        from scripts.research_artifacts import sha
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            facts = project / "facts.txt"
            facts.write_text("Synthetic controlled scientific evidence.\n", encoding="utf-8")
            style = project / "style.txt"
            style.write_text("Synthetic optional venue note.\n", encoding="utf-8")
            for gate in DIMENSIONS:
                value = report(gate)
                value["schema_version"] = "1.2"
                value.pop("scores")
                value.pop("venue_readiness")
                value["assessments"] = {key: {"status": "satisfied", "rationale": "Synthetic located scientific evidence",
                    "source_anchors": [{"path": "facts.txt", "sha256": sha(facts), "locator": "L1",
                                        "excerpt": "Synthetic controlled scientific evidence."}]}
                    for key in DIMENSIONS[gate] if key not in OBSERVATIONAL_CRITERIA}
                warnings = []
                self.assertEqual(validate_report(value, gate, project=project, require_facts=True, warnings=warnings), [])
                value["assessments"]["venue_fit"] = {"status": "unresolved"}
                self.assertEqual(validate_report(value, gate, project=project, require_facts=True, warnings=warnings), [])
                self.assertTrue(any("venue_fit" in note for note in warnings))
                value["assessments"]["venue_fit"]["source_anchors"] = [{"path": "style.txt", "sha256": "0" * 64,
                    "locator": "L1", "excerpt": "Synthetic optional venue note."}]
                self.assertTrue(any("stale source hash" in error for error in
                    validate_report(value, gate, project=project, require_facts=True, warnings=warnings)))
                value["assessments"].pop("venue_fit")
                value["assessments"][next(iter(value["assessments"]))]["status"] = "failed"
                self.assertTrue(validate_report(value, gate, project=project, require_facts=True, warnings=warnings))

    def test_file_api_returns_warnings_and_keeps_real_blockers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quality.json"
            value = report("G3")
            value["scores"] = {key: 1 for key in value["scores"]}
            path.write_text(json.dumps(value), encoding="utf-8")
            warnings = []
            self.assertEqual(validate_file(path, "G3", warnings=warnings), [])
            self.assertTrue(warnings)
            value["blockers"] = ["The held-out data may have leaked into training."]
            path.write_text(json.dumps(value), encoding="utf-8")
            self.assertTrue(any("unresolved blockers" in error for error in validate_file(path, "G3", warnings=warnings)))

    def test_legacy_schema_cannot_hide_a_forged_source_anchor(self):
        from scripts.research_artifacts import sha
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            source = project / "facts.txt"
            source.write_text("Synthetic controlled source.\n", encoding="utf-8")
            value = report("G1")
            value["assessments"] = {"novelty": {"status": "satisfied", "rationale": "Synthetic located fact",
                "source_anchors": [{"path": "facts.txt", "sha256": sha(source), "locator": "L1",
                                    "excerpt": "Synthetic controlled source."}]}}
            self.assertEqual(validate_report(value, "G1", project=project), [])
            source.write_text("Changed source bytes.\n", encoding="utf-8")
            self.assertTrue(any("stale source hash" in error for error in validate_report(value, "G1", project=project)))

    def test_doctoral_case_is_required(self):
        value = report("G1")
        value["doctoral_readiness"]["unifying_thesis"] = ""
        self.assertTrue(any("unifying_thesis" in error for error in validate_report(value, "G1")))


if __name__ == "__main__":
    unittest.main()
