from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import scientific_scope
from scripts.research_artifacts import read, write, sha, record
from tests.review_scope_fixtures import prepare_scope


class ScientificScopeTests(unittest.TestCase):
    def fixture(self, root):
        project = root / "scope-fixture"
        state = {"paper_count": 6, "active_paper": "P01", "stage": "writing-and-review", "gate": "G5",
                 "approvals": [], "approved_gates": [], "paper_statuses": {f"P{n:02d}": "active" for n in range(1, 7)}}
        write(project / "state/run.json", state)
        prepare_scope(project, state)
        return project, state

    def test_all_six_papers_share_current_approved_scope_and_progress_can_update(self):
        with tempfile.TemporaryDirectory() as temp:
            project, _ = self.fixture(Path(temp))
            for relative in ("program/core-thesis.json", "program/extension-thesis.json"):
                value = read(project / relative)
                value.update(status="writing", working_title="New precise writing title")
                write(project / relative, value)
            for gate in ("G2", "G3", "G4", "G5"):
                self.assertEqual(scientific_scope.validate(project, gate, "P01"), [])

    def test_scientific_changes_are_visible_without_blocking_unrelated_work(self):
        with tempfile.TemporaryDirectory() as temp:
            project,_=self.fixture(Path(temp));before=scientific_scope.review_binding(project,"P01")
            path=project/"papers/P06/paper-contract.json";value=read(path)
            value["research_question"]="A revised P06 question";write(path,value)
            self.assertEqual(scientific_scope.review_binding(project,"P01"),before)
            self.assertTrue(scientific_scope.changes(project,"P06"))
            self.assertEqual(scientific_scope.validate(project,"G5","P01"),[])
            path=project/"papers/P01/paper-contract.json";value=read(path)
            value.update(working_title="A clearer title",target_jcr_quartile="Q2");write(path,value)
            self.assertEqual(scientific_scope.review_binding(project,"P01"),before)
            value["research_question"]="A revised local question";write(path,value)
            self.assertNotEqual(scientific_scope.review_binding(project,"P01"),before)

    def test_measured_synthesis_progress_does_not_create_another_topic_vote(self):
        with tempfile.TemporaryDirectory() as temp:
            project, _ = self.fixture(Path(temp))
            mapping = read(project / "program/paper-map.json")
            mapping["thesis_synthesis"]["evidence_alignment"] = [{"claim_id": "SYNTHETIC_P01", "result_status": "not_supported"}]
            write(project / "program/paper-map.json", mapping)
            self.assertEqual(scientific_scope.validate(project, "G5", "P01"), [])

    def test_primary_endpoint_is_topic_scope_but_statistical_parameters_are_g3_details(self):
        with tempfile.TemporaryDirectory() as temp:
            project, _ = self.fixture(Path(temp))
            target = project / "papers/P01/paper-contract.json"
            contract = read(target)
            contract["hypotheses"] = [{"id": "H1", "statement": "A bounded testable hypothesis", "primary_outcome": "Registered outcome"}]
            contract["scientific_bindings"] = {"hypotheses": [{"hypothesis_id": "H1", "primary_metric": "original_metric", "minimum_effect": 0}]}
            write(target, contract)
            frozen = scientific_scope.projection(project, "G2")
            contract["scientific_bindings"]["hypotheses"][0].update(minimum_effect=0.2, aggregation="A declared aggregation")
            write(target, contract)
            self.assertEqual(scientific_scope.projection(project, "G2"), frozen)
            contract["scientific_bindings"]["hypotheses"][0]["primary_metric"] = "different_metric"
            write(target, contract)
            self.assertNotEqual(scientific_scope.projection(project, "G2"), frozen)

    def test_legacy_missing_scope_record_is_not_invented_or_a_work_prerequisite(self):
        with tempfile.TemporaryDirectory() as temp:
            project,_=self.fixture(Path(temp));target=project/"state/scientific-scope/G1.json";target.unlink()
            before=(project/"state/run.json").read_bytes()
            self.assertEqual(scientific_scope.validate(project,"G3"),[])
            self.assertFalse(target.exists());self.assertEqual((project/"state/run.json").read_bytes(),before)

    def test_recorded_scope_change_preserves_other_papers_and_existing_approvals(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{"DR_OS_CLOUD_EXECUTOR":"1"}):
            project,original=self.fixture(Path(temp))
            core=read(project/"program/core-thesis.json");core["doctoral_question"]="A changed question";write(project/"program/core-thesis.json",core)
            source="program/scope-amendment.json"
            write(project/source,{"schema_version":"1.0","id":"changed-scope","gate":"G1","reason":"The user changes the question after inspecting the actual evidence.","expected_seal_sha256":sha(project/"state/scientific-scope/G1.json"),"proposed_projection":scientific_scope.projection(project,"G1")})
            receipt=scientific_scope.apply_amendment(project,source,"Named human","a"*64,"fixture-run","Record the new question")
            current=read(project/"state/run.json")
            for key in ("gate","stage","active_paper","paper_statuses","approvals","approved_gates"):
                self.assertEqual(current[key],original[key])
            self.assertEqual(receipt["status"],"recorded")
            self.assertEqual(scientific_scope.validate(project,"G5","P01"),[])

    def test_amendment_cas_and_subsequent_candidate_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project, _ = self.fixture(Path(temp))
            core = read(project / "program/core-thesis.json")
            core["doctoral_question"] = "New candidate doctoral question?"
            write(project / "program/core-thesis.json", core)
            proposal = {"schema_version": "1.0", "id": "scope-cas", "gate": "G1", "reason": "Synthetic changed doctoral question requires explicit human reapproval.",
                        "expected_seal_sha256": "0" * 64, "proposed_projection": scientific_scope.projection(project, "G1")}
            write(project / "program/scope-amendment.json", proposal)
            with self.assertRaisesRegex(ValueError, "CAS"):
                scientific_scope.prepare_amendment(project, "program/scope-amendment.json", "Human")
            proposal["expected_seal_sha256"] = sha(project / "state/scientific-scope/G1.json")
            write(project / "program/scope-amendment.json", proposal)
            scientific_scope.apply_amendment(project, "program/scope-amendment.json", "Human", "a" * 64, "cloud-fixture", "Human amendment")
            core["doctoral_question"] = "A further unreviewed candidate change?"
            write(project / "program/core-thesis.json", core)
            self.assertTrue(scientific_scope.changes(project))
            self.assertEqual(scientific_scope.validate(project,"G1"),[])

    def test_exact_human_approved_supplement_inherits_parent_without_new_thesis(self):
        with tempfile.TemporaryDirectory() as temp:
            parent, _ = self.fixture(Path(temp))
            child = parent / "experiments/supplemental/P01/R001/s001"
            write(parent / "experiments/plan.json", {"synthetic": "original frozen plan"})
            write(parent / "papers/P01/preregistration.json", {"synthetic": "original frozen protocol"})
            approval = {"gate": "G3", "actor": "Synthetic supplement owner", "cloud_review_sha256": "a" * 64}
            state = {"stage": "experiment-execution", "gate": "G4", "active_paper": "P01", "approvals": [approval],
                "supplemental_context": {"parent_project": parent.name, "paper_id": "P01", "round_id": "R001", "scope_id": "s001"}}
            write(child / "state/run.json", state)
            write(child / "papers/P01/paper-contract.json", {"independence": {"unique_claim_ids": ["SYNTHETIC_P01"]}})
            control = parent / "state/supplemental-experiments/P01/R001/s001.json"
            write(control, {"paper_id": "P01", "round_id": "R001", "scope_id": "s001",
                "scope_root": child.relative_to(parent).as_posix(), "child_state_sha256": sha(child / "state/run.json"), "approval": approval,
                "proposal": {"original_plan_sha256": sha(parent / "experiments/plan.json"), "original_preregistration_sha256": sha(parent / "papers/P01/preregistration.json")}})
            record(parent, [control], "scripts/supplemental_experiments.py")
            self.assertEqual(scientific_scope.validate(child, "G4", "P01"), [])
            core = read(parent / "program/core-thesis.json")
            core["doctoral_question"] = "Unapproved changed parent doctoral question"
            write(parent / "program/core-thesis.json", core)
            self.assertEqual(scientific_scope.validate(child,"G4","P01"),[])
            write(parent/"experiments/plan.json",{"changed":"execution inputs"})
            self.assertTrue(scientific_scope.validate(child,"G4","P01"))

    def test_synthetic_helper_refuses_actual_repository_project_paths(self):
        from scripts.acceptance_scope import prepare_scope
        production = Path(scientific_scope.__file__).resolve().parents[1] / "projects/never-created-scope-test"
        with self.assertRaisesRegex(ValueError, "real repository project"):
            prepare_scope(production, {"paper_count": 1})
