from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from scripts.manuscript_language import analyze
from scripts.research_design import (
    validate_experiment_design,
    validate_originality_audit,
    validate_paper_contract,
    validate_paper_map,
    validate_search_log,
)


def originality_audit():
    return {
        "schema_version": "1.0",
        "status": "ready_for_review",
        "search_scope": {
            "databases": ["WoS", "Scopus", "IEEE Xplore"],
            "adjacent_fields": ["reliability", "robotics", "operations"],
            "query_families": ["mechanism", "application", "failure mode"],
            "cutoff_date": "2026-09-01",
        },
        "closest_prior_work": [
            {
                "id": f"W{index}",
                "title": f"Prior work {index}",
                "publication_year": 2020 + index,
                "primary_source_url": f"https://example.org/work-{index}",
                "overlap": "Shared application domain.",
                "difference": "Different falsifiable mechanism.",
                "evidence_location": "Methods and results.",
            }
            for index in range(1, 6)
        ],
        "novelty_claims": [
            {
                "claim_id": "N1",
                "claim": "A new reliability mechanism.",
                "novelty_type": "methodological",
                "evidence_ids": ["W1", "W2"],
                "counterevidence": "W3 has a related but non-equivalent mechanism.",
                "residual_risk": "Unindexed industrial work may exist.",
            }
        ],
        "patent_search": {
            "status": "completed",
            "databases": ["Espacenet"],
            "queries": ["reliability mechanism"],
        },
        "doctoral_case": {
            "unifying_thesis": "A coherent reliability thesis.",
            "original_knowledge_contribution": "New validated knowledge.",
            "synthesis_beyond_individual_papers": "Cross-paper mechanisms.",
            "methodological_progression": "Benchmark to external validation.",
            "scope_boundaries": "Public industrial datasets.",
            "examiner_challenges": ["novelty", "reliability", "generalization"],
        },
        "reliability_strategy": {
            "triangulation": "Use multiple datasets and metrics.",
            "replication": "Repeat stochastic runs.",
            "sensitivity_analysis": "Vary preprocessing and hyperparameters.",
            "negative_result_policy": "Retain all failed and null results.",
            "external_validity": "Evaluate temporal and cross-domain transfer.",
        },
        "human_review_required": True,
    }


def venue(name, quartile):
    return {
        "name": name,
        "quartile": quartile,
        "indexing": "SCIE",
        "category": "Engineering",
        "jcr_year": 2026,
        "source_url": f"https://example.org/{name.lower()}",
        "scope_fit": "Industrial AI.",
        "article_type": "Original article",
    }


def paper_contract():
    return {
        "schema_version": "2.0",
        "paper_id": "P01",
        "writing_language": "en",
        "working_title": "Reliable Industrial AI",
        "research_question": "Does the proposed method generalize?",
        "distinct_contribution": "A distinct falsifiable method.",
        "relationship_to_core": "Tests the core mechanism.",
        "relationship_to_extension": "Supplies a transfer test.",
        "originality_boundary": {
            "novel_elements": ["new mechanism"],
            "reused_elements": ["standard encoder"],
            "closest_prior_work_ids": ["W1", "W2", "W3"],
            "differentiation": "Different unit of analysis and mechanism.",
            "claim_limitations": "No causal field intervention.",
        },
        "hypotheses": [
            {
                "id": "H1",
                "statement": "The method improves the primary endpoint.",
                "null_hypothesis": "There is no improvement.",
                "confirmatory": True,
                "primary_outcome": "Macro F1",
            }
        ],
        "datasets": ["D1"],
        "planned_experiments": {
            "design_ids": ["D-P01"],
            "baseline_classes": ["simple", "domain_standard", "strong_recent"],
            "ablations": ["remove reliability layer"],
            "primary_evaluation": "Locked held-out test.",
            "statistical_plan": "Paired effect sizes and intervals.",
            "external_validity_plan": "Temporal transfer cohort.",
            "reproducibility_plan": "Locked environment and seeds.",
        },
        "falsification_conditions": ["No improvement over strong baseline."],
        "dependencies": [],
        "independence": {
            "unique_claim_ids": ["C-P01"],
            "shared_assets": ["D1"],
            "overlap_with_other_papers": [],
            "why_not_merge": "Different primary claim and evaluation unit.",
        },
        "target_venues": [venue("JournalA", "Q1"), venue("JournalB", "Q1")],
        "status": "ready_for_review",
    }


def experiment_design():
    return {
        "schema_version": "1.0",
        "status": "ready_for_review",
        "paper_id": "P01",
        "design_id": "D-P01",
        "hypothesis_ids": ["H1"],
        "run_ids": ["run-1", "run-2", "run-3"],
        "stochastic": True,
        "seeds": [1, 2, 3],
        "baselines": [
            {"id": "B1", "class": "simple", "rationale": "Lower bound.", "publication_year": 2018, "primary_source_url": "https://example.org/b1", "implementation_source": "Documented local code.", "version_or_commit": "v1", "license_or_terms": "MIT", "tuning_budget": "10 trials."},
            {"id": "B2", "class": "domain_standard", "rationale": "Accepted comparator.", "publication_year": 2020, "primary_source_url": "https://example.org/b2", "implementation_source": "Official implementation.", "version_or_commit": "v2", "license_or_terms": "Apache-2.0", "tuning_budget": "10 trials."},
            {"id": "B3", "class": "strong_recent", "rationale": "Current competitive comparator.", "publication_year": 2025, "primary_source_url": "https://example.org/b3", "implementation_source": "Author implementation.", "version_or_commit": "abc123", "license_or_terms": "Research use", "tuning_budget": "10 trials."},
        ],
        "baseline_fairness": {
            "common_evaluation_protocol": "All methods use the locked split and metrics.",
            "comparable_tuning_budget": "Each trainable method receives 10 trials.",
            "leakage_isolation": "Every method fits transformations on training data only.",
            "implementation_verification": "Versions and official test cases are recorded.",
        },
        "ablations": ["Remove module A."],
        "data_protocol": {
            "datasets": ["D1"],
            "split_unit": "machine",
            "split_strategy": "Group-disjoint temporal split.",
            "leakage_controls": ["Fit preprocessing on train only.", "Keep machines disjoint."],
            "preprocessing_fit_scope": "Training partition only.",
            "external_validation": "Later time period and second plant.",
        },
        "metrics": {
            "primary": [{"name": "Macro F1", "direction": "higher", "aggregation": "per machine then mean", "uncertainty": "95% bootstrap CI", "rationale": "Class imbalance."}],
            "secondary": ["AUROC"],
        },
        "statistics": {
            "estimand": "Mean paired difference in machine-level Macro F1.",
            "unit_of_analysis": "machine",
            "effect_size": "paired Macro F1 difference",
            "confidence_interval": "95% cluster bootstrap",
            "test_or_model": "paired permutation test",
            "practical_significance_threshold": "Macro F1 difference of 0.02.",
            "assumption_checks": ["exchangeability"],
            "multiplicity_control": "Holm correction",
            "power_or_precision": "Simulation targets CI half-width <= 0.02.",
            "missing_data": "Report missingness and use locked imputation.",
            "seed_aggregation": "Mean and interval across seeds.",
        },
        "robustness_checks": ["alternate split", "hyperparameter sensitivity"],
        "negative_controls": ["permuted labels"],
        "falsification_criteria": ["CI includes zero against strong baseline."],
        "stopping_rules": ["Execute all preregistered runs."],
        "failure_analysis": "Inspect errors by machine and failure type.",
        "reproducibility": {"environment_lock": "lock file", "code_commit": "Git SHA", "config_capture": "JSON config", "output_hashes": "SHA-256 manifest"},
        "claim_limits": "Associational benchmark evidence only.",
    }


class ResearchDesignTests(unittest.TestCase):
    def test_originality_audit_passes(self):
        self.assertEqual(validate_originality_audit(originality_audit()), [])

    def test_originality_requires_five_closest_works(self):
        value = originality_audit()
        value["closest_prior_work"] = value["closest_prior_work"][:4]
        self.assertTrue(any("at least 5" in error for error in validate_originality_audit(value)))

    def test_search_log_traces_claimed_scope_and_closest_works(self):
        audit = originality_audit()
        records = [
            {
                "schema_version": "1.0",
                "search_id": f"S{index}",
                "database": database,
                "query_family": family,
                "query": f"query {index}",
                "searched_at": "2026-09-01T00:00:00Z",
                "date_range": "2020-2026",
                "filters": "primary studies",
                "result_count": 10,
                "included_work_ids": included,
                "exclusion_reasons": ["Out of scope."],
                "source_url": f"https://example.org/search-{index}",
            }
            for index, (database, family, included) in enumerate(
                zip(
                    audit["search_scope"]["databases"],
                    audit["search_scope"]["query_families"],
                    (["W1", "W2"], ["W3", "W4"], ["W5"]),
                ),
                1,
            )
        ]
        self.assertEqual(validate_search_log(records, audit), [])
        records[2]["included_work_ids"] = []
        self.assertTrue(any("W5" in error for error in validate_search_log(records, audit)))

    def test_complete_pairwise_paper_map_passes(self):
        value = {
            "schema_version": "2.0",
            "status": "ready_for_review",
            "papers": [
                {"paper_id": paper, "portfolio_role": f"Role {paper}", "distinct_contribution": f"Contribution {paper}", "unique_claim_ids": [f"C-{paper}"], "shared_assets": [], "dependencies": []}
                for paper in ("P01", "P02", "P03")
            ],
            "pairwise_distinctness": [
                {"paper_a": left, "paper_b": right, "distinct_research_questions": True, "distinct_primary_claims": True, "independent_primary_evidence": True, "standalone_scientific_value": True, "shared_primary_outcome": False, "shared_outcome_justification": "No primary outcome is shared.", "overlap_risk": "low", "why_separate": "Different claims.", "merge_trigger": "Merge if claims become identical."}
                for left, right in (("P01", "P02"), ("P01", "P03"), ("P02", "P03"))
            ],
            "thesis_synthesis": {"core_thesis": "Core.", "extension_thesis": "Extension.", "cumulative_progression": "Progression.", "integrated_contribution": "Synthesis.", "dependency_logic": "Dependencies."},
        }
        self.assertEqual(validate_paper_map(value, ("P01", "P02", "P03")), [])
        duplicate = copy.deepcopy(value)
        duplicate["papers"][1]["unique_claim_ids"] = duplicate["papers"][0]["unique_claim_ids"]
        self.assertTrue(any("repeat another paper" in error for error in validate_paper_map(duplicate, ("P01", "P02", "P03"))))
        value["pairwise_distinctness"][0]["shared_primary_outcome"] = True
        value["pairwise_distinctness"][0]["shared_outcome_justification"] = "The same safety endpoint tests independent mechanisms with separately powered evidence."
        self.assertEqual(validate_paper_map(value, ("P01", "P02", "P03")), [])
        value["pairwise_distinctness"].pop()
        self.assertTrue(any("missing" in error for error in validate_paper_map(value, ("P01", "P02", "P03"))))

    def test_paper_contract_requires_english_and_q1(self):
        value = paper_contract()
        self.assertEqual(validate_paper_contract(value, "P01"), [])
        value["writing_language"] = "zh"
        value["target_venues"][1]["quartile"] = "Q3"
        errors = validate_paper_contract(value, "P01")
        self.assertTrue(any("writing_language" in error for error in errors))
        self.assertTrue(any("current JCR Q1" in error for error in errors))

    def test_experiment_design_links_three_stochastic_seeds(self):
        runs = {f"run-{seed}": {"run_id": f"run-{seed}", "paper_id": "P01", "seed": seed} for seed in (1, 2, 3)}
        self.assertEqual(validate_experiment_design(experiment_design(), "P01", runs), [])
        value = experiment_design()
        value["run_ids"] = value["run_ids"][:2]
        self.assertTrue(any("three distinct" in error for error in validate_experiment_design(value, "P01", runs)))

    def test_experiment_design_requires_recent_traceable_strong_baseline(self):
        runs = {f"run-{seed}": {"run_id": f"run-{seed}", "paper_id": "P01", "seed": seed} for seed in (1, 2, 3)}
        value = experiment_design()
        value["baselines"][2]["publication_year"] = 2010
        value["baselines"][2]["primary_source_url"] = "unverified"
        errors = validate_experiment_design(value, "P01", runs)
        self.assertTrue(any("last five years" in error for error in errors))
        self.assertTrue(any("primary-source URL" in error for error in errors))

    def test_english_manuscript_check(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "main.tex"
            path.write_text("\\section{Introduction}\n" + "The results of this study support our careful scientific claims. " * 40, encoding="utf-8")
            self.assertEqual(analyze(path)["status"], "pass")
            path.write_text(path.read_text(encoding="utf-8") + "这不是英文正文。", encoding="utf-8")
            self.assertEqual(analyze(path)["status"], "fail")

    def test_english_manuscript_follows_safe_tex_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "sections").mkdir()
            (root / "main.tex").write_text("\\input{sections/body}\n", encoding="utf-8")
            (root / "sections" / "body.tex").write_text(
                "The transparent methods in this study support reproducible scientific conclusions. " * 40,
                encoding="utf-8",
            )
            self.assertEqual(analyze(root / "main.tex")["status"], "pass")

    def test_latin_script_alone_does_not_pass_as_english(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "main.tex"
            path.write_text(
                "Los resultados científicos muestran una evaluación rigurosa y reproducible. " * 50,
                encoding="utf-8",
            )
            self.assertEqual(analyze(path)["status"], "fail")


if __name__ == "__main__":
    unittest.main()
