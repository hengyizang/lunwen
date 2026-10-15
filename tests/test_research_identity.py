"""Synthetic policy fixtures, not genuine studies or publisher classifications."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import research_identity as policy, researchctl
from scripts.research_artifacts import read, sha, write


class ResearchIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "identity-study"
        self.paper = self.project / "papers/P01"
        self.now = datetime.now(timezone.utc).isoformat()
        self.source = self.project / "evidence/category.txt"
        self.source.parent.mkdir(parents=True)
        self.quote = "Research Article includes primary studies and appropriately validated secondary quantitative studies in this synthetic test only."
        self.source.write_text(self.quote + "\n", encoding="utf-8")
        self.names = ["Synthetic Journal A", "Synthetic Journal B"]
        targets = [{"name": name, "article_type": "Research Article"} for name in self.names]
        write(self.paper / "paper-contract.json", {"target_venues": targets, "independence": {"unique_claim_ids": ["C1"]}})
        write(self.project / "state/run.json", {"stage_index": 2, "stage": "paper-architecture", "gate": "G2",
            "paper_count": 1, "active_paper": "P01", "status": "awaiting_work", "approvals": [], "approved_gates": []})
        write(self.project / "program/venue-candidates.json", {"papers": [{"paper_id": "P01", "candidates": [
            {**target, "official_guidelines_url": "https://publisher.example/guidelines",
             "policy_source_url": "https://publisher.example/policy"} for target in targets]}]})
        write(self.paper / "venue.json", {"name": self.names[0]})
        self.identity = policy.template("P01")
        self.identity.update(research_kind="primary", design_family="computational", methods=["controlled_computation"],
            reporting_description="computational experimental study",
            new_analysis_rationale="This synthetic fixture tests identity binding only and does not assert a genuine novel scientific contribution.",
            validation_plan="Use independently reviewed computational comparisons with all failures and uncertainty retained; this is a fixture only.",
            claim_ids=["C1"], venue_classifications=[{
                "venue_name": name, "article_type": "Research Article", "official_url": "https://publisher.example/policy",
                "checked_at": self.now, "research_article_eligible": True, "design_eligible": True,
                "rationale": "This synthetic policy fixture exercises source binding, not genuine journal policy or doctoral eligibility.",
                "evidence": {"path": "evidence/category.txt", "sha256": sha(self.source), "start_line": 1, "end_line": 1, "quote": self.quote}
            } for name in self.names])
        self.save()

    def save(self):
        write(self.paper / "research-identity.json", self.identity)

    def secondary(self):
        self.identity.update(research_kind="secondary_quantitative", design_family="meta-analysis",
            methods=["meta_analysis"], reporting_description="systematic review and meta-analysis",
            secondary_protocol={key: "Synthetic protocol detail for " + key + "; substantive appropriateness requires independent human scientific review."
                                for key in policy.PROTOCOL_FIELDS})
        self.save()

    def final(self):
        excerpt = "We conducted a " + self.identity["reporting_description"] + " using the explicitly specified protocol."
        manuscript = self.paper / "manuscript/main.tex"
        manuscript.parent.mkdir(parents=True, exist_ok=True)
        manuscript.write_text("\\documentclass{article}\n\\begin{document}\n" + excerpt + "\n\\end{document}\n", encoding="utf-8")
        self.identity["reporting_statement"] = {"excerpt": excerpt, "location": {"kind": "source_lines", "path": "manuscript/main.tex",
            "sha256": sha(manuscript), "start_line": 3, "end_line": 3}}
        write(self.paper / "reviews/pre-submission-checklist.json", {"article_type": "review" if self.identity["research_kind"] == "secondary_quantitative" else "computational"})
        self.save()

    def receipt(self):
        plan_path = self.project / "experiments/plan.json"
        output = self.paper / "tables/secondary-analysis.csv"
        output.parent.mkdir(parents=True)
        output.write_text("fixture_effect,fixture_standard_error\n0.2,0.1\n", encoding="utf-8")
        relative = output.relative_to(self.project).as_posix()
        write(plan_path, {"runs": [{"run_id": "synthesis", "paper_id": "P01", "expected_outputs": [relative]}]})
        receipt = {"run_id": "synthesis", "paper_id": "P01", "attempt_id": "synthesis-attempt-001",
            "status": "succeeded", "approved_plan_sha256": sha(plan_path), "outputs": [{"path": relative, "sha256": sha(output)}]}
        write(self.project / "experiments/runs/synthesis-attempt-001/run.json", receipt)
        (self.project / "experiments/registry.jsonl").write_text(json.dumps(receipt) + "\n", encoding="utf-8")
        state = read(self.project / "state/run.json")
        state.update(approved_gates=["G3"], approvals=[{"gate": "G3", "actor": "Synthetic human", "experiment_plan_sha256": sha(plan_path)}])
        write(self.project / "state/run.json", state)
        self.identity["analysis_evidence"] = [{"attempt_id": receipt["attempt_id"], "path": relative, "sha256": sha(output)}]
        self.save()
        return output

    def test_primary_proposal_passes_identity_only_without_spending_or_mutation(self):
        before = {p: p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        self.assertEqual(policy.validate(self.project, "P01", "G2"), [])
        self.assertEqual(before, {p: p.read_bytes() for p in self.project.rglob("*") if p.is_file()})

    def test_g1_does_not_invent_a_type_and_unassigned_g2_blocks(self):
        write(self.paper / "research-identity.json", policy.template("P01"))
        self.assertEqual(policy.validate(self.project, "P01", "G1"), [])
        self.assertIn("assign original", " ".join(policy.validate(self.project, "P01", "G2")))

    def test_narrative_or_summary_review_cannot_be_renamed_primary(self):
        for kind, design, methods in [("primary", "narrative-review", ["summary"]),
                ("secondary_quantitative", "systematic-review", ["systematic_review"]),
                ("primary", "computational", ["meta_analysis"]),
                ("primary", "computational", ["Meta-Analysis"]),
                ("primary", "computational", ["systematic review and meta analysis"])]:
            self.identity.update(research_kind=kind, design_family=design, methods=methods)
            self.save()
            self.assertTrue(policy.validate(self.project, "P01", "G2"))

    def test_secondary_requires_a_substantive_protocol_not_just_meta_name(self):
        self.secondary()
        self.assertEqual(policy.validate(self.project, "P01", "G2"), [])
        for field in policy.PROTOCOL_FIELDS:
            value = self.identity["secondary_protocol"].pop(field)
            self.save()
            self.assertTrue(policy.validate(self.project, "P01", "G2"), field)
            self.identity["secondary_protocol"][field] = value

    def test_meta_method_and_description_must_be_truthful(self):
        self.secondary()
        self.identity["reporting_description"] = "new primary experimental study"
        self.save()
        self.assertIn("Meta analysis must", " ".join(policy.validate(self.project, "P01", "G2")))

    def test_actual_review_category_is_rejected_not_relabelled(self):
        for category in ["Review", "Systematic Review", "Survey", "Perspective"]:
            self.identity["venue_classifications"][0]["article_type"] = category
            contract = read(self.paper / "paper-contract.json")
            contract["target_venues"][0]["article_type"] = category
            write(self.paper / "paper-contract.json", contract)
            registry = read(self.project / "program/venue-candidates.json")
            registry["papers"][0]["candidates"][0]["article_type"] = category
            write(self.project / "program/venue-candidates.json", registry)
            self.save()
            self.assertIn("excludes", " ".join(policy.validate(self.project, "P01", "G2")))

    def test_renamed_category_missing_target_and_wrong_claims_block(self):
        original = copy.deepcopy(self.identity)
        for change in [lambda: self.identity["venue_classifications"][0].update(article_type="Original Article"),
                       lambda: self.identity["venue_classifications"].pop(),
                       lambda: self.identity.update(claim_ids=["OTHER"])]:
            self.identity = copy.deepcopy(original)
            change()
            self.save()
            self.assertTrue(policy.validate(self.project, "P01", "G2"))

    def test_policy_requires_actual_current_official_source(self):
        original = copy.deepcopy(self.identity)
        for change in [lambda row: row.update(official_url="https://unrelated.example/policy"),
                       lambda row: row.update(checked_at=(datetime.now(timezone.utc)-timedelta(days=31)).isoformat()),
                       lambda row: row.update(design_eligible=False),
                       lambda row: row["evidence"].update(sha256="0"*64),
                       lambda row: row["evidence"].update(start_line=2),
                       lambda row: row["evidence"].update(quote="The source did not say this at all.")]:
            self.identity = copy.deepcopy(original)
            change(self.identity["venue_classifications"][0])
            self.save()
            self.assertTrue(policy.validate(self.project, "P01", "G2"))

    def test_secondary_completion_without_real_attempt_is_blocked(self):
        self.secondary()
        self.final()
        self.assertIn("executor-issued", " ".join(policy.validate(self.project, "P01", "G5")))

    def test_secondary_success_is_bound_to_current_approved_plan_receipt_and_output(self):
        self.secondary()
        output = self.receipt()
        self.final()
        self.assertEqual(policy.validate(self.project, "P01", "G5"), [])
        output.write_text("changed", encoding="utf-8")
        self.assertIn("output is stale", " ".join(policy.validate(self.project, "P01", "G5")))

    def test_wrong_paper_or_attempt_status_cannot_satisfy_secondary_evidence(self):
        self.secondary()
        self.receipt()
        receipt_path = self.project / "experiments/runs/synthesis-attempt-001/run.json"
        original = read(receipt_path)
        for fields in [{"paper_id": "P02"}, {"status": "failed"}, {"approved_plan_sha256": "0"*64}]:
            changed = {**original, **fields}
            write(receipt_path, changed)
            (self.project / "experiments/registry.jsonl").write_text(json.dumps(changed)+"\n", encoding="utf-8")
            self.assertTrue(policy.validate(self.project, "P01", "G4"))

    def test_secondary_cannot_waive_its_review_scientific_checklist(self):
        self.secondary()
        self.receipt()
        self.final()
        write(self.paper / "reviews/pre-submission-checklist.json", {"article_type": "empirical"})
        self.assertIn("checklist must match", " ".join(policy.validate(self.project, "P01", "G5")))

    def test_final_manuscript_must_really_declare_its_design(self):
        self.final()
        self.assertEqual(policy.validate(self.project, "P01", "G5"), [])
        self.identity["reporting_statement"]["location"]["start_line"] = 1
        self.identity["reporting_statement"]["location"]["end_line"] = 1
        self.save()
        self.assertTrue(policy.validate(self.project, "P01", "G5"))

    def test_identity_and_external_policy_source_are_bound_to_g5_hash(self):
        with patch.object(researchctl, "PROJECTS_ROOT", self.project.parent):
            before = researchctl.paper_artifact_hash("identity-study", "P01")
            self.source.write_text(self.quote + "\nChanged official evidence.\n", encoding="utf-8")
            self.assertNotEqual(before, researchctl.paper_artifact_hash("identity-study", "P01"))

    def test_missing_identity_reaches_the_real_human_gate_checker(self):
        (self.paper / "research-identity.json").unlink()
        with patch.object(researchctl, "PROJECTS_ROOT", self.project.parent):
            errors = researchctl.gate_errors("identity-study", "G2")
        self.assertTrue(any("original-research policy" in x for x in errors))

    def test_secondary_completion_needs_named_human_and_current_receipt(self):
        self.secondary()
        self.receipt()
        state_path = self.project / "state/run.json"
        state = read(state_path)
        state["approvals"][0]["actor"] = ""
        write(state_path, state)
        self.assertIn("named human", " ".join(policy.validate(self.project, "P01", "G4")))
        state["approvals"][0]["actor"] = "Synthetic human"
        write(state_path, state)
        receipt_path = self.project / "experiments/runs/synthesis-attempt-001/run.json"
        receipt = read(receipt_path)
        receipt["status"] = "failed"
        write(receipt_path, receipt)
        self.assertIn("executor receipt", " ".join(policy.validate(self.project, "P01", "G4")))

    def test_new_six_paper_portfolio_stays_unassigned_without_approval_or_budget_grant(self):
        with patch.object(researchctl, "PROJECTS_ROOT", self.project.parent), patch("builtins.print"):
            researchctl.initialize(SimpleNamespace(project="new-portfolio", paper_count=6, venue=None))
        project = self.project.parent / "new-portfolio"
        for number in range(1, 7):
            identity = read(project / f"papers/P{number:02d}/research-identity.json")
            self.assertEqual(identity["research_kind"], "unassigned")
            self.assertEqual(identity["design_family"], "unassigned")
        self.assertEqual(read(project / "state/run.json")["approved_gates"], [])
        self.assertEqual(read(project / "state/model-spend-control.json")["authorized_ceiling_cny"], 0)


if __name__ == "__main__":
    unittest.main()
