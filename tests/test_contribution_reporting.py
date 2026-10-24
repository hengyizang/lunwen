"""Synthetic software contracts; these fixtures establish no research result."""
import copy
import json
from pathlib import Path
import unittest

from scripts import contribution_reporting as reporting, manuscript_audit
from scripts.research_artifacts import read, sha, write
from tests.figure_lineage_fixtures import sealed_run
from tests import test_closest_work_axes as axis_fixtures


class ContributionReportingTests(unittest.TestCase):
    def setUp(self):
        fixture = axis_fixtures.ClosestWorkAxesTests("test_legacy_comparison_is_retained_but_axes_are_not_assessed")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.project = fixture.project
        self.comparison = fixture.fixture()
        matrix = read(self.project/"program/novelty-claim-matrix.json")
        matrix["claims"][0]["closest_work_ids"] = ["W1"]
        fixture.update_context(self.comparison, "novelty_matrix", matrix)
        self.values = {"finding": "A bounded synthetic observation.", "magnitude": "1.2",
                       "uncertainty": "[0.2, 2.2]", "comparison": "synthetic baseline",
                       "heterogeneity": "synthetic heterogeneity 0.1", "bias": "synthetic bias assessment",
                       "proposition": "Synthetic proposition under A", "assumptions": "Synthetic assumption A",
                       "proof": "synthetic kernel check passed", "scope": "synthetic scope A"}
        _, _, self.receipt = sealed_run(self.project, output="results/contribution.json", body=json.dumps(self.values))
        self.output = "results/contribution.json"
        self.planned = {"path": "analysis/executor-fixture.py", "sha256": sha(self.project/"analysis/executor-fixture.py")}
        self.quote = "Synthetic preapproved executor fixture"
        self.spec = {"schema_version": "1.0", "facts": [], "claim_alignment": [], "measurement": [],
                     "measurement_not_applicable_reason": "Synthetic software fixture has no measured constructs.",
                     "argument_ledger": [], "glossary": [], "symbols": [], "ignored_symbols": []}
        self.prepare("empirical")

    def prepare(self, kind):
        from scripts.research_identity import template, PRIMARY
        family = "case-study" if kind == "qualitative" else kind
        identity = template("P01")
        identity.update(design_family=family, research_kind="primary" if family in PRIMARY else "secondary_quantitative")
        write(self.project/"papers/P01/research-identity.json", identity)
        roles = sorted(reporting.ROLES[kind])
        self.spec["facts"] = [{"id": "F"+str(i), "statement": self.values[role], "source_path": self.output,
            "source_sha256": sha(self.project/self.output), "location": role,
            "verbatim_evidence": (self.project/self.output).read_text()} for i, role in enumerate(roles)]
        self.link = {"claim_id": "C1", "research_question": "A synthetic software question.",
            "canonical_claim": self.values["finding"], "allowed_inference": "descriptive", "claim_strength": "descriptive",
            "result_status": "supported", "evidence_ids": [f["id"] for f in self.spec["facts"]],
            "sections": {key: self.values["finding"] for key in ("title", "abstract", "question", "results", "conclusion")},
            "contribution_detail": {"kind": kind, "subject": "Synthetic test records", "finding": self.values["finding"],
                "conditions": "Synthetic fixture scope only", "scientific_answer": "This checks a software binding only.",
                "fact_roles": [{"role": role, "fact_id": "F"+str(i), "value": self.values[role]} for i, role in enumerate(roles)],
                "execution": [{"run_id": "r1", "path": self.output, "sha256": sha(self.project/self.output)}],
                "expectation_review": {"planned_source": self.planned, "planned_quote": self.quote,
                    "observed_status": "supported", "decision": "retain", "reason": "Synthetic mapping is unchanged.", "scope": "Synthetic software scope only."}}}
        self.spec["claim_alignment"] = [self.link]
        self.spec["argument_ledger"] = [{"paragraph_id": "p1", "section": "results", "function": "result", "claim_id": "C1",
            "inference_boundary": "Synthetic software scope only", "transition": "Return to the synthetic question", "evidence_ids": ["F0"], "text_anchor": self.values["finding"]}]
        write(self.project/"program/research-extensions.json", {"schema_version": "1.0", "comparisons": [self.comparison]})

    def test_actual_sealed_findings_and_three_axes_prepare_review_not_science(self):
        result = reporting.audit(self.project, "P01", self.spec)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["status"], "ready_for_scientific_review")
        self.assertFalse(result["semantic_support_verified"])
        self.assertFalse(result["scientific_completion_verified"])

    def test_legacy_claims_remain_explicitly_unassessed(self):
        del self.link["contribution_detail"]
        result = reporting.audit(self.project, "P01", self.spec)
        self.assertEqual(result["status"], "needs_preparation")
        self.assertEqual(result["claims"][0]["status"], "not_assessed")

    def test_missing_uncertainty_or_fabricated_value_blocks_preparation(self):
        for mutate in (lambda d: d["fact_roles"].pop(), lambda d: d["fact_roles"][0].update(value="invented value")):
            spec = copy.deepcopy(self.spec)
            mutate(spec["claim_alignment"][0]["contribution_detail"])
            self.assertTrue(reporting.audit(self.project, "P01", spec)["errors"])

    def test_unsealed_and_changed_results_cannot_become_findings(self):
        spec = copy.deepcopy(self.spec)
        spec["claim_alignment"][0]["contribution_detail"]["execution"][0]["run_id"] = "not-executed"
        self.assertTrue(reporting.audit(self.project, "P01", spec)["errors"])
        (self.project/self.output).write_text("changed actual output")
        self.assertTrue(reporting.audit(self.project, "P01", self.spec)["errors"])

    def test_frozen_expectation_and_actual_outcome_cannot_be_rewritten_as_success(self):
        spec = copy.deepcopy(self.spec)
        link = spec["claim_alignment"][0]
        link["result_status"] = "contradicted"
        self.assertTrue(reporting.audit(self.project, "P01", spec)["errors"])
        review = link["contribution_detail"]["expectation_review"]
        review.update(observed_status="contradicted", decision="retain")
        self.assertTrue(reporting.audit(self.project, "P01", spec)["errors"])
        review.update(decision="unsupported", reason="Synthetic observation contradicts the original success claim.")
        self.assertEqual(reporting.audit(self.project, "P01", spec)["errors"], [])
        review["planned_quote"] = "not in the approved source"
        self.assertTrue(reporting.audit(self.project, "P01", spec)["errors"])

    def test_claim_needs_every_declared_closest_work_comparison(self):
        matrix = read(self.project/"program/novelty-claim-matrix.json")
        matrix["claims"][0]["closest_work_ids"].append("W2")
        write(self.project/"program/novelty-claim-matrix.json", matrix)
        self.comparison["closest_work"]["context"]["novelty_matrix"] = self.fixture.binding("program/novelty-claim-matrix.json")
        write(self.project/"program/research-extensions.json", {"schema_version": "1.0", "comparisons": [self.comparison]})
        result = reporting.audit(self.project, "P01", self.spec)
        self.assertTrue(result["errors"])

    def test_meta_reports_heterogeneity_and_bias_in_addition_to_effects(self):
        self.prepare("meta-analysis")
        self.assertEqual(reporting.audit(self.project, "P01", self.spec)["errors"], [])
        self.link["contribution_detail"]["fact_roles"].pop()
        self.assertTrue(reporting.audit(self.project, "P01", self.spec)["errors"])

    def test_qualitative_scope_does_not_require_invented_effect_sizes(self):
        self.prepare("qualitative")
        self.assertEqual(reporting.audit(self.project, "P01", self.spec)["errors"], [])
        self.assertEqual({r["role"] for r in self.link["contribution_detail"]["fact_roles"]}, {"finding", "scope"})

    def test_theory_uses_frozen_propositions_and_kernel_outputs_without_effect_sizes(self):
        self.prepare("theoretical")
        source = self.project/"experiments/plan.json"
        for role in self.link["contribution_detail"]["fact_roles"]:
            if role["role"] not in {"proposition", "assumptions"}:
                continue
            role["value"] = "analysis/executor-fixture.py" if role["role"] == "proposition" else "seed"
            fact = next(row for row in self.spec["facts"] if row["id"] == role["fact_id"])
            fact.update(source_path="experiments/plan.json", source_sha256=sha(source), verbatim_evidence=source.read_text())
        result = reporting.audit(self.project, "P01", self.spec)
        self.assertEqual(result["errors"], [])
        self.assertNotIn("magnitude", result["claims"][0]["fact_roles"])

    def test_unread_unknown_axes_cannot_complete_the_final_contribution(self):
        for axis in self.comparison["closest_work"]["axes"].values():
            axis["disposition"] = "insufficient_evidence"
            axis["conclusion_kind"] = "none"
            axis["prior"] = {"status": "unknown", "scope": "Original has not been inspected.",
                             "missing_reason": "Full text still needs reading", "evidence": []}
        write(self.project/"program/research-extensions.json", {"schema_version": "1.0", "comparisons": [self.comparison]})
        self.assertTrue(reporting.audit(self.project, "P01", self.spec)["errors"])

    def test_existing_manuscript_audit_carries_current_contribution_checks(self):
        paper = self.project/"papers/P01"
        manuscript = paper/"manuscript/main.tex"
        manuscript.parent.mkdir(parents=True, exist_ok=True)
        claim = self.values["finding"]
        manuscript.write_text("\\title{"+claim+"}\n\\begin{abstract}"+claim+"\\end{abstract}\n\\section{Introduction}\n"+claim+"\n\\section{Results}\n"+claim+"\n\\section{Conclusion}\n"+claim+"\n")
        spec = paper/"reviews/paper-facts.json"
        write(spec, self.spec)
        report = manuscript_audit.audit(self.project, manuscript, spec)
        self.assertEqual(report["contribution_reporting"]["status"], "ready_for_scientific_review")
        write(paper/"reviews/manuscript-audit.json", report)
        del self.link["contribution_detail"]
        write(spec, self.spec)
        errors = manuscript_audit.validate_saved_report(paper)
        self.assertTrue(any("contribution" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
