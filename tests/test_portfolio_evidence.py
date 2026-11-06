"""Synthetic cross-record tests; no research, model call or scientific clearance."""
from __future__ import annotations

import copy
import itertools
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import research_design as design, research_increments as increments
from scripts.research_artifacts import read, write, sha, record
from tests.test_research_design import negative_plan, paper_contract, experiment_design


class PortfolioEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.paper_ids = [f"P{n:02}" for n in range(1, 7)]
        self.papers = [{"paper_id": pid, "theme_id": "A" if n < 4 else "B", "target_jcr_quartile": "Q1" if n < 4 else "Q2",
                       "portfolio_role": "Synthetic bounded contribution", "distinct_contribution": "Different measured endpoint",
                       "unique_claim_ids": [f"C{n}"], "shared_assets": [], "dependencies": []}
                      for n, pid in enumerate(self.paper_ids, 1)]
        self.mapping = {"schema_version": "2.0", "status": "ready_for_review", "papers": self.papers,
            "pairwise_distinctness": [{"paper_a": a, "paper_b": b, "distinct_research_questions": True,
                "distinct_primary_claims": True, "independent_primary_evidence": True, "standalone_scientific_value": True,
                "shared_primary_outcome": False, "shared_outcome_justification": "Synthetic independent outcomes",
                "overlap_risk": "low", "why_separate": "Different outcome and inference unit",
                "merge_trigger": "Merge if they become the same scientific question"}
                for a, b in itertools.combinations(self.paper_ids, 2)],
            "thesis_synthesis": {**{k: "Synthetic unified doctoral contribution" for k in
                ("core_thesis", "extension_thesis", "cumulative_progression", "integrated_contribution", "dependency_logic")},
                "argument_links": [{"step_id": "combined-question", "claim_ids": [f"C{n}" for n in range(1, 7)],
                    "contribution": "All endpoints test the same overarching question",
                    "what_changes_if_unsupported": "Report the boundary and uncertainty without a success narrative"}],
                "evidence_alignment": []}}
        write(self.project / "state/run.json", {"paper_count": 6, "active_paper": "P02", "gate": "G5",
            "paper_statuses": {pid: "active" if pid == "P02" else "planned" for pid in self.paper_ids}})
        self.contracts = {}
        for n, pid in enumerate(self.paper_ids, 1):
            contract = paper_contract()
            contract.update(paper_id=pid, dependencies=[], dependency_bindings=[])
            contract["independence"]["unique_claim_ids"] = [f"C{n}"]
            self.contracts[pid] = contract
        self.actual = {pid: {"paper_id": pid, "claim_matrix_sha256": "a" * 64, "evidence_plan_sha256": "b" * 64,
            "claims": {f"C{n}": {"result_status": "supported", "comparison_ids": [f"cmp-{n}"], "analysis_ids": [f"run-{n}"]}}}
            for n, pid in enumerate(self.paper_ids, 1)}
        self.align("P02")
        self.save()

    def align(self, pid, disposition="retain"):
        actual = self.actual[pid]
        claim, outcome = next(iter(actual["claims"].items()))
        self.mapping["thesis_synthesis"]["evidence_alignment"] = [{"claim_id": claim,
            "result_status": outcome["result_status"], "comparison_ids": outcome["comparison_ids"],
            "claim_matrix_sha256": actual["claim_matrix_sha256"], "evidence_plan_sha256": actual["evidence_plan_sha256"],
            "disposition": disposition, "claim_boundary": "Only the registered synthetic conditions are addressed"}]

    def save(self):
        write(self.project / "program/paper-map.json", self.mapping)
        for pid, contract in self.contracts.items():
            write(self.project / "papers" / pid / "paper-contract.json", contract)

    def check(self, pid="P02"):
        with patch("scripts.results_validation.claim_outcomes", side_effect=lambda project, key: self.actual[key]) as measured:
            result = design.validate_portfolio_evidence(self.project, pid)
            return result, [call.args[1] for call in measured.call_args_list]

    def dependency(self, kind="shared_asset"):
        source = self.project / "evidence/shared.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("Synthetic shared asset, not a scientific finding.\n", encoding="utf-8")
        child = self.project / "papers/P02/dependency.txt"
        child.write_text("Synthetic child consumes this declared source.\n", encoding="utf-8")
        spec = increments.initialize(self.project)
        spec["dependencies"] = [{"id": "G1", "nodes": [
            {"id": "source", "kind": "shared_asset" if kind == "shared_asset" else "claim", "meaning": "Declared source premise",
             "paper_ids": ["P01"], "depends_on": [], "source": {"path": "evidence/shared.txt", "sha256": sha(source)}},
            {"id": "consumer", "kind": "text", "meaning": "Bounded inherited use in child",
             "paper_ids": ["P02"], "depends_on": ["source"],
             "source": {"path": "papers/P02/dependency.txt", "sha256": sha(child)}}]}]
        write(self.project / increments.PLAN, spec)
        self.papers[1]["dependencies"] = ["P01"]
        self.contracts["P02"]["dependencies"] = ["P01"]
        self.contracts["P02"]["dependency_bindings"] = [{"paper_id": "P01", "kind": kind,
            "claim_ids": ["C1"] if kind == "scientific_premise" else [], "graph_id": "G1", "node_ids": ["consumer"],
            "rationale": "Synthetic evidence relationship", "inherited_scope": "Only the declared source boundary"}]
        self.save()
        return source

    def test_synthesis_joins_actual_results_without_waiting_for_final_papers(self):
        self.assertEqual(self.check()[0], [])

    def test_normal_forward_dependency_has_no_all_paper_ready_deadlock(self):
        self.dependency()
        errors, calls = self.check()
        self.assertEqual(errors, [])
        self.assertEqual(calls, ["P02"])

    def test_shared_asset_survives_parent_negative_result_but_changed_bytes_block(self):
        source = self.dependency()
        self.actual["P01"]["claims"]["C1"]["result_status"] = "not_supported"
        self.assertEqual(self.check()[0], [])
        source.write_text("Changed source bytes", encoding="utf-8")
        self.assertTrue(any("dependency evidence changed" in e for e in self.check()[0]))

    def test_scientific_premise_needs_the_specific_supported_parent_claim(self):
        self.dependency("scientific_premise")
        self.assertEqual(self.check()[0], [])
        self.actual["P01"]["claims"]["C1"]["result_status"] = "partially_supported"
        self.assertTrue(any("inherited scientific premise" in e for e in self.check()[0]))

    def test_adverse_result_can_contribute_without_retaining_success_story(self):
        self.actual["P02"]["claims"]["C2"]["result_status"] = "not_supported"
        self.align("P02", "retain")
        self.save()
        self.assertTrue(any("cannot retain" in e for e in self.check()[0]))
        self.align("P02", "reframe")
        self.save()
        self.assertEqual(self.check()[0], [])

    def test_thesis_status_and_numeric_source_hash_cannot_be_self_reported(self):
        row = self.mapping["thesis_synthesis"]["evidence_alignment"][0]
        row["result_status"] = "contradicted"
        row["evidence_plan_sha256"] = "0" * 64
        self.save()
        errors, _ = self.check()
        self.assertTrue(any("contradicts actual" in e for e in errors))
        self.assertTrue(any("stale result bindings" in e for e in errors))

    def test_dependency_unknown_self_cycle_and_contract_map_mismatch(self):
        for parents in (["P99"], ["P02"]):
            value = copy.deepcopy(self.mapping)
            value["papers"][1]["dependencies"] = parents
            self.assertTrue(any("self-reference or unknown" in e for e in design.validate_paper_map(value, self.paper_ids)))
        value = copy.deepcopy(self.mapping)
        value["papers"][0]["dependencies"] = ["P02"]
        value["papers"][1]["dependencies"] = ["P01"]
        self.assertTrue(any("acyclic" in e for e in design.validate_paper_map(value, self.paper_ids)))
        self.contracts["P02"]["dependencies"] = ["P01"]
        self.save()
        self.assertTrue(any("dependencies disagree" in e for e in design.validate_portfolio_evidence(self.project, gate="G2")))


class TopicEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        source = self.project / "evidence/official.txt"
        source.parent.mkdir(parents=True)
        source.write_text("Synthetic metadata records data access, rights and measured costs.\n", encoding="utf-8")
        record(self.project, [source], "synthetic-acquisition-fixture")
        anchor = {"path": "evidence/official.txt", "sha256": sha(source), "locator": "Synthetic metadata line 1",
                  "quote": "Synthetic metadata records data access, rights and measured costs."}
        self.shortlist = {"candidates": [{"candidate_id": key} for key in ("A", "B", "C")],
            "selection_decision": {"chosen_candidate_id": "A", "strongest_rival_candidate_id": "B",
                "why_selected_over_rival": "The synthetic contrast is observable within the data source.",
                "change_of_mind_evidence": "Choose B if that contrast is not identifiable."},
            "selected_direction_cloud_feasibility": {"current_papers_feasible": True, "no_future_lab_dependency": True,
                "authorized_data_plan": "Read the saved metadata and verify source rights.",
                "cloud_experiment_plan": "Prepare a bounded approved experiment.", "current_paper_scope": "Only the stated feasible question.",
                "feasibility_evidence": {"data_access": [anchor], "research_rights": [copy.deepcopy(anchor)],
                    "compute_cost": [copy.deepcopy(anchor)], "pilot": {"status": "not_run", "limitation": "No pilot execution is claimed."}}}}

    def test_located_feasibility_keeps_unexecuted_pilot_honest(self):
        self.assertEqual(design.validate_selected_direction_cloud_feasibility(self.shortlist, self.project), [])
        self.shortlist["selected_direction_cloud_feasibility"]["feasibility_evidence"]["pilot"] = {"status": "executed", "attempt_id": "invented"}
        self.assertTrue(design.validate_selected_direction_cloud_feasibility(self.shortlist, self.project))

    def test_missing_changed_and_unquoted_feasibility_sources_fail(self):
        anchor = self.shortlist["selected_direction_cloud_feasibility"]["feasibility_evidence"]["data_access"][0]
        for field, value in (("path", "evidence/missing.txt"), ("sha256", "0" * 64), ("quote", "This statement is not in the source.")):
            original = anchor[field]
            anchor[field] = value
            self.assertTrue(design.validate_selected_direction_cloud_feasibility(self.shortlist, self.project))
            anchor[field] = original

    def test_negative_result_plan_does_not_promise_publication(self):
        self.assertEqual(design.validate_negative_result_plan(negative_plan()), [])
        value = negative_plan()
        value.pop("precision_limitations")
        self.assertTrue(design.validate_negative_result_plan(value))

    def test_model_written_feasibility_assertion_cannot_attest_its_own_source(self):
        from scripts import output_provenance
        source = self.project / "evidence/official.txt"
        output_provenance.record_model_writes(self.project, [source], family="openai", provider="synthetic-writer",
            model="synthetic-model", role="persistent-writer", run_id="synthetic-no-model-call")
        self.assertTrue(any("not model self-attestation" in error for error in
            design.validate_selected_direction_cloud_feasibility(self.shortlist, self.project)))

    def test_structured_primary_binding_cannot_quietly_change_the_contract(self):
        value = paper_contract()
        self.assertEqual(design.validate_scientific_bindings(value), [])
        value["scientific_bindings"]["hypotheses"][0]["primary_outcome_statement"] = "A different endpoint"
        self.assertTrue(any("original primary outcome" in e for e in design.validate_scientific_bindings(value)))


class ExecutedPortfolioJoinTests(unittest.TestCase):
    def test_actual_synthetic_attempts_feed_synthesis_and_changed_outputs_invalidate_it(self):
        from scripts import experiment_evidence as evidence, experiment_evidence_acceptance as acceptance
        from scripts import experiment_runner as runner, results_validation as results, scientific_scope
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "synthetic-portfolio"
            acceptance.fixture(project, current_protocol=True)
            mapping = read(project / "program/paper-map.json")
            mapping["thesis_synthesis"]["argument_links"] = [{"step_id": "synthetic-test", "claim_ids": ["C1"],
                "contribution": "Test whether all registered outcomes remain visible",
                "what_changes_if_unsupported": "Report the adverse comparisons and retain the uncertainty"}]
            write(project / "program/paper-map.json", mapping)
            # This isolated software fixture has no real project authorization.
            state = read(project / "state/run.json")
            approval = next(row for row in state["approvals"] if row["gate"] == "G2")
            approval["artifact_sha256"] = sha(project / "program/paper-map.json")
            for vote in approval["paper_topic_approvals"]:
                vote["artifact_sha256"] = approval["artifact_sha256"]
            write(project / "state/run.json", state)
            # Recreate this temporary synthetic topic receipt before execution;
            # never migrate an existing real project's approval this way.
            (project / "state/scientific-scope/G2.json").unlink()
            with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
                scientific_scope.seal_approval(project, "G2", approval["actor"], approval)
            runner.execute(project.name, project_root=project)
            report = evidence.build_report(project, "P01")
            (project / "claims").mkdir(exist_ok=True)
            shutil.copyfile(acceptance.claim_matrix(project, report), project / "claims/claim-evidence.csv")
            actual = results.claim_outcomes(project, "P01")
            outcome = actual["claims"]["C1"]
            mapping["thesis_synthesis"]["evidence_alignment"] = [{"claim_id": "C1", **outcome,
                "claim_matrix_sha256": actual["claim_matrix_sha256"], "evidence_plan_sha256": actual["evidence_plan_sha256"],
                "disposition": "narrow", "claim_boundary": "Synthetic software checks only; no scientific result is asserted"}]
            # analysis_ids are already bound inside the formal matrix, not a new alignment field.
            mapping["thesis_synthesis"]["evidence_alignment"][0].pop("analysis_ids")
            write(project / "program/paper-map.json", mapping)
            self.assertEqual(design.validate_portfolio_evidence(project, "P01"), [])
            (project / "results/proposed-11.csv").write_text("unit,value\nu0,999\n", encoding="utf-8")
            self.assertTrue(design.validate_portfolio_evidence(project, "P01"))


class ModelSelectionDeclarationTests(unittest.TestCase):
    def setUp(self):
        self.design = experiment_design()
        self.runs = {f"run-{seed}": {"run_id": f"run-{seed}", "paper_id": "P01", "seed": seed,
            "cwd": "env-b" if seed == 3 else "env-a", "isolation": {"kind": "container"} if seed == 3 else {"kind": "host"}}
            for seed in (1, 2, 3)}

    def check(self):
        return design.validate_experiment_design(self.design, "P01", self.runs)

    def tuned(self):
        row = {"status": "tuned", "selection_split": "validation", "selection_metric": "validation loss",
            "search_space": {"learning_rate": [0.001, 0.01]}, "run_ids": ["run-1"],
            "rationale": "Choose on the registered validation units before the locked final test"}
        self.design["data_protocol"]["model_selection"] = row
        return row

    def test_fixed_and_not_applicable_models_need_no_fictional_search(self):
        self.assertEqual(self.check(), [])
        self.design["data_protocol"]["model_selection"] = {
            "status": "not_applicable", "rationale": "This analysis uses a fixed analytical estimator without hyperparameters"}
        self.assertEqual(self.check(), [])

    def test_tuned_model_declares_space_metric_and_same_design_runs(self):
        row = self.tuned()
        self.assertEqual(self.check(), [])
        row["run_ids"] = ["a-different-paper-run"]
        self.assertTrue(any("belong to this declared paper design" in e for e in self.check()))

    def test_test_final_and_holdout_selection_are_rejected(self):
        row = self.tuned()
        for split in ("test", "final", "holdout", "validation+test"):
            row["selection_split"] = split
            self.assertTrue(any("never test/final/holdout" in e for e in self.check()), split)

    def test_missing_or_nonfinite_search_space_and_invented_untuned_run_fail(self):
        row = self.tuned()
        row["search_space"] = {}
        self.assertTrue(self.check())
        row["search_space"] = {"rate": [float("nan")]}
        self.assertTrue(self.check())
        row["status"] = "not_tuned"
        self.assertTrue(any("must not invent" in e for e in self.check()))


if __name__ == "__main__":
    unittest.main()
