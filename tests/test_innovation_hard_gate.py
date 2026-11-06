"""Synthetic controls test source integrity, never scientific novelty."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts import innovation_screening as innovation, literature_evidence as literature
from scripts.research_artifacts import read, write, record, sha
from tests import test_research_quality as quality_fixtures


class InnovationHardGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        self.originality, self.matrix, _, receipts = quality_fixtures.ResearchQualityTests().executed_saturation(self.project)
        self.matrix["schema_version"] = "1.1"
        incoming = [{"id": f"https://openalex.org/W{i}", "display_name": f"Synthetic prior {i}",
                     "doi": f"https://doi.org/10.1000/prior{i}", "publication_year": 2025}
                    for i in range(1, 4)]
        def transport(url, **_):
            return json.dumps({"results": incoming}).encode(), url, 200, "application/json"
        receipt = literature.execute_search(self.project, "openalex", "synthetic nearest mechanisms",
            query_family="exact", date_range="all indexed years", filters="none", limit=3, fetcher=transport)
        receipts.append(receipt)
        works = read(self.project / receipt["normalized_results_path"])["works"]
        literature.screen_receipt(self.project, receipt["receipt_id"], [w["id"] for w in works],
                                 ["Synthetic fixture screening; not a scientific assessment."], "Fixture Human")
        self.originality["closest_prior_work"] = [{"id": f"W{i}", "title": f"Synthetic prior {i}",
            "primary_source_url": f"https://doi.org/10.1000/prior{i}"} for i in range(1, 6)]
        papers, comparisons = [], []
        for i, work in enumerate(works, 1):
            relative = f"literature/sources/prior-{i}.txt"
            source = self.project / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("Synthetic prior mechanism uses a fixed threshold.\n", encoding="utf-8")
            record(self.project, [source], "tests.synthetic_source_import")
            binding = {"path": relative, "sha256": sha(source)}
            papers.append({"id": f"L{i}", "candidate_id": work["id"], "title": work["title"],
                           "url": f"https://doi.org/10.1000/prior{i}", "source_scope": "full_text", "source": binding})
            comparisons.append({"work_id": f"W{i}", "library_id": f"L{i}",
                "retrieval_receipt_id": receipt["receipt_id"], "retrieved_work_id": work["id"],
                "source_anchors": [{**binding, "start_line": 1, "end_line": 1,
                                    "quote": "Synthetic prior mechanism uses a fixed threshold."}],
                "already_known": "Synthetic prior fixed threshold", "precise_difference": "Synthetic adaptive threshold",
                "non_obvious_reason": "Synthetic competing mechanism must be discriminated",
                "discriminating_prediction": "Synthetic heldout shift distinguishes the threshold mechanisms",
                "disposition": "distinct", "unresolved_objections": []})
        write(self.project / "program/literature-workbench.json", {"schema_version": "1.0", "papers": papers})
        # Isolate the already-tested PDF acquisition boundary. This fixed mapping
        # cannot be altered by rebinding the model-writable library configuration.
        from unittest.mock import patch
        registered = {p["id"]: copy.deepcopy(p["source"]) for p in papers}
        for p in papers:
            write(self.project / f"literature/metadata/{p['id']}.json", {"candidate": {
                "canonical_id": p["candidate_id"], "title": p["title"], "primary_source_url": p["url"]}})
        self.basis_patch = patch("scripts.source_scope._registered_basis", side_effect=lambda project, key:
            (registered[key], {"registration_path": f"literature/metadata/{key}.json"}))
        self.basis_patch.start(); self.addCleanup(self.basis_patch.stop)
        self.matrix["claims"][0]["prior_art_comparisons"] = comparisons
        saturation = self.matrix["search_saturation"]
        saturation["supporting_search_ids"].append(receipt["receipt_id"])
        saturation["stopping_rule"] = "time_limit"
        saturation["unresolved_search_gaps"] = ["Synthetic source coverage is bounded, not exhaustive."]
        saturation["retrieval_dispositions"] = []
        returned = set()
        for r in receipts:
            for work in read(self.project / r["normalized_results_path"])["works"]:
                returned.add(work["id"])
                saturation["retrieval_dispositions"].append({"receipt_id": r["receipt_id"], "work_id": work["id"],
                    "relevance": "closest" if r == receipt else "peripheral", "rationale": "Synthetic screening decision"})
        saturation["search_rounds"] = [{"round_id": "executed-round", "search_ids": saturation["supporting_search_ids"],
            "new_work_count": len(returned), "new_closest_work_count": len(works)}]
        self.assessment = {"novelty_assessment": [{"claim_id": "N1", "inspected_work_ids": ["W1", "W2", "W3"],
            "decision": "distinct", "rationale": "Synthetic located contrast inspected",
            "remaining_uncertainty": "Synthetic fixture cannot establish scientific novelty"}]}

    def check(self, matrix=None):
        return innovation.validate_novelty_gate(self.project, matrix or self.matrix, self.originality, "G1")

    def test_bound_sources_allow_honest_bounded_search(self):
        self.assertEqual(self.check(), [])

    def test_missing_claim_forged_quote_wrong_source_and_omitted_prior_block(self):
        for case in ("claim", "quote", "source", "omit", "overlap", "identity", "count", "unassessed"):
            matrix = copy.deepcopy(self.matrix)
            item = matrix["claims"][0]
            contrast = item["prior_art_comparisons"][0]
            if case == "claim": item["claim"] = ""
            if case == "quote": contrast["source_anchors"][0]["quote"] = "No such sentence in the source"
            if case == "source": contrast["source_anchors"][0]["path"] = "missing/original.txt"
            if case == "omit": item["prior_art_comparisons"].pop()
            if case == "overlap": contrast["disposition"] = "overlap"
            if case == "identity": contrast["retrieved_work_id"] = "unretrieved-work"
            if case == "count": matrix["search_saturation"]["search_rounds"][0]["new_closest_work_count"] = 0
            if case == "unassessed": matrix["search_saturation"]["retrieval_dispositions"].pop()
            with self.subTest(case=case): self.assertTrue(self.check(matrix))

    def test_model_authored_or_changed_original_cannot_self_verify(self):
        target = self.project / "literature/sources/prior-1.txt"
        target.write_text("Synthetic modified original source.\n", encoding="utf-8")
        self.assertTrue(self.check())

    def test_library_cannot_rebind_one_papers_identity_to_another_valid_source(self):
        library = read(self.project / "program/literature-workbench.json")
        library["papers"][0]["source"] = copy.deepcopy(library["papers"][1]["source"])
        write(self.project / "program/literature-workbench.json", library)
        matrix = copy.deepcopy(self.matrix)
        matrix["claims"][0]["prior_art_comparisons"][0]["source_anchors"] = copy.deepcopy(
            matrix["claims"][0]["prior_art_comparisons"][1]["source_anchors"])
        self.assertTrue(any("protected acquisition" in e for e in self.check(matrix)))

    def test_unregistered_source_cannot_pass_the_real_acquisition_boundary(self):
        self.basis_patch.stop()
        self.assertTrue(any("executor-owned library" in e for e in self.check()))

    def test_unresolved_or_missing_independent_assessment_blocks_even_with_high_score(self):
        self.assertEqual(innovation.validate_novelty_review(self.assessment, self.matrix, "G1"), [])
        for decision in ("overlap", "unresolved"):
            audit = copy.deepcopy(self.assessment)
            audit["novelty_assessment"][0]["decision"] = decision
            audit["scores"] = {"novelty": 10}
            self.assertTrue(innovation.validate_novelty_review(audit, self.matrix, "G1"))
            self.assertEqual(innovation.validate_novelty_review(audit, self.matrix, "G1", final=False), [])
        self.assertTrue(innovation.validate_novelty_review({}, self.matrix, "G1"))

    def test_legacy_matrix_requires_explicit_migration(self):
        matrix = copy.deepcopy(self.matrix); matrix["schema_version"] = "1.0"
        self.assertTrue(any("migration" in e for e in self.check(matrix)))

    def test_actual_critic_receipts_require_current_claim_specific_assessment(self):
        from tests import test_review_receipts as fixtures
        from tests.review_scope_fixtures import seal_review
        from scripts import review_receipts
        project, state = fixtures.ReviewReceiptTests().fixture(self.project / "receipt-control")
        write(project / "program/novelty-claim-matrix.json", self.matrix)
        seal_review(project, state, run_id="missing-assessment")
        self.assertTrue(any("novelty_assessment" in e for e in review_receipts.validate_gate(project, "G5", "P01")))
        seal_review(project, state, run_id="actual-assessment", novelty_assessment=self.assessment["novelty_assessment"])
        self.assertEqual(review_receipts.validate_gate(project, "G5", "P01"), [])

    def test_gate_invokes_hard_requirements_without_optional_opt_in(self):
        from scripts import researchctl
        from unittest.mock import patch
        write(self.project / "state/run.json", {"paper_count": 1, "active_paper": "P01", "approved_gates": []})
        write(self.project / "program/novelty-claim-matrix.json", {**self.matrix, "schema_version": "1.0"})
        write(self.project / "program/originality-audit.json", self.originality)
        # Other incomplete project inputs also fail; novelty must independently fail.
        with patch.object(researchctl, "project_dir", return_value=self.project), patch.object(researchctl, "state_path", return_value=self.project / "state/run.json"):
            errors = researchctl.gate_errors("synthetic", "G1")
        self.assertTrue(any("novelty matrix migration" in e for e in errors), errors)
