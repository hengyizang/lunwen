from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import scientific_scope
from scripts.research_artifacts import read, write, sha
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
            for relative in ("program/core-thesis.json", "program/extension-thesis.json", "papers/P01/paper-contract.json"):
                value = read(project / relative)
                value.update(status="writing", working_title="New precise writing title")
                write(project / relative, value)
            for gate in ("G2", "G3", "G4", "G5"):
                self.assertEqual(scientific_scope.validate(project, gate, "P01"), [])

    def test_drift_in_doctoral_question_extension_or_other_paper_mapping_blocks_later_work(self):
        for relative, field in (("program/core-thesis.json", "doctoral_question"), ("program/extension-thesis.json", "distinct_contribution"),
                                ("papers/P06/paper-contract.json", "research_question")):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temp:
                project, _ = self.fixture(Path(temp))
                value = read(project / relative)
                value[field] = "Unauthorized different scientific scope"
                write(project / relative, value)
                self.assertTrue(scientific_scope.validate(project, "G5", "P01"))
        with tempfile.TemporaryDirectory() as temp:
            project, _ = self.fixture(Path(temp))
            mapping = read(project / "program/paper-map.json")
            mapping["thesis_synthesis"]["integrated_contribution"] = "Unrelated six-paper story"
            write(project / "program/paper-map.json", mapping)
            self.assertTrue(scientific_scope.validate(project, "G3"))

    def test_legacy_approval_without_scope_seal_never_silently_migrates(self):
        with tempfile.TemporaryDirectory() as temp:
            project, _ = self.fixture(Path(temp))
            (project / "state/scientific-scope/G1.json").unlink()
            self.assertTrue(any("lacks a protected scope seal" in e for e in scientific_scope.validate(project, "G3")))

    def test_human_amendment_preserves_history_and_demands_fresh_gate_approval(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            project, original = self.fixture(Path(temp))
            core = read(project / "program/core-thesis.json")
            core["doctoral_question"] = "A genuinely changed synthetic doctoral question?"
            write(project / "program/core-thesis.json", core)
            source = "program/scope-amendment.json"
            write(project / source, {"schema_version": "1.0", "id": "changed-doctoral-scope", "gate": "G1",
                "reason": "The human requests a synthetic changed doctoral question after a documented evidence reassessment.",
                "expected_seal_sha256": sha(project / "state/scientific-scope/G1.json"),
                "proposed_projection": scientific_scope.projection(project, "G1")})
            scientific_scope.apply_amendment(project, source, "Named human", "a" * 64, "cloud-fixture-run", "Reopen G1 for scientific reapproval")
            current = read(project / "state/run.json")
            self.assertEqual(current["gate"], "G1")
            self.assertEqual(current["approvals"], original["approvals"])
            self.assertEqual(current["approved_gates"], [])
            self.assertEqual(scientific_scope.validate(project, "G1"), [])
            self.assertTrue(scientific_scope.validate(project, "G2"))
            approval = {"gate": "G1", "actor": "Named human", "artifact_sha256": "b" * 64}
            scientific_scope.seal_approval(project, "G1", "Named human", approval)
            current["approved_gates"].append("G1")
            current["approvals"].append(approval)
            write(project / "state/run.json", current)
            self.assertTrue(scientific_scope.validate(project, "G3"))
            second = {"gate": "G2", "actor": "Named human", "artifact_sha256": "c" * 64}
            scientific_scope.seal_approval(project, "G2", "Named human", second)
            current["approved_gates"].append("G2")
            current["approvals"].append(second)
            write(project / "state/run.json", current)
            self.assertEqual(scientific_scope.validate(project, "G3"), [])

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
            self.assertTrue(any("after the named human amendment" in e for e in scientific_scope.validate(project, "G1")))


if __name__ == "__main__":
    unittest.main()
