"""Native quality preparation around synthetic two-phase review callbacks.

No model, paid service or scientific experiment runs in these fixtures.
"""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import ai_providers, api_orchestrator as api, artifact_ownership
from scripts import automated_quality, output_provenance, paper_execution, research_cycle
from scripts import research_quality, researchctl, review_receipts
from scripts.research_artifacts import read, sha, write
from tests import research_cycle_fixtures, test_research_exploration as exploration_fixtures


class ControlledQualityCycleTests(unittest.TestCase):
    def setUp(self):
        fixture = exploration_fixtures.NativeExplorationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.project = fixture.project
        self.slug = fixture.slug
        self.prereg = self.project / "papers/P01/preregistration.json"
        self.script = self.project / "analysis/probe.py"
        self.run_id = "controlled-quality-software-cycle"
        api_root = patch.object(api, "ROOT", self.project.parent)
        api_root.start()
        self.addCleanup(api_root.stop)
        self.writer = ai_providers.ModelResult("uuapi-openai", "synthetic-writer", "", {})
        research_cycle_fixtures.pending_decision(self.project, "experiment-design", self.run_id, "P01")
        output_provenance.record_model_writes(self.project, [self.project / "program/research-notebook.json"],
            family="openai", provider="synthetic-fixture", model="synthetic-writer", role="persistent-writer",
            run_id=self.run_id)

    def cycle(self, *, repair=False):
        callbacks = []
        initial_prereg = []
        refreshed = []
        identity = {"provider": "synthetic-anthropic", "family": "anthropic", "requested_model": "synthetic-critic",
                    "reported_model": "synthetic-critic", "completion_status": "completed", "cache_hit": False}
        clean = {"verdict": "pass-with-conditions", "fatal_findings": [], "major_findings": [], "minor_findings": [],
                 "missing_evidence": [], "remediation_steps": [], "uncertainty": ["Software callbacks are not scientific review."]}

        def refresh(phase):
            # Method preparation finishes before the shared controller seals its
            # matching inputs for either independent critic.
            if phase == "initial":
                self.assertFalse(self.prereg.exists())
            refreshed.append(phase)
            return {"method_preparation_finished": phase}, {"script_sha256": sha(self.script)}

        def invoke(phase, request):
            self.assertEqual(refreshed[-1], phase)
            self.assertTrue(self.prereg.is_file())
            frozen = read(self.prereg)
            self.assertEqual(research_quality.validate_preregistration(frozen, "P01", self.project), [])
            bound = {row["path"]: row["sha256"] for row in frozen["files"]}
            self.assertEqual(bound["analysis/probe.py"], sha(self.script))
            self.assertEqual(bound[self.fixture.plan_path.relative_to(self.project).as_posix()], sha(self.fixture.plan_path))
            origin = output_provenance.current_origin(self.project, self.prereg)
            self.assertEqual((origin["provider"], origin["model"]),
                             (automated_quality.PROVIDER, "scripts/automated_quality.py"))
            self.assertFalse(frozen["human_confirmation"])
            self.assertEqual(read(self.project / "state/run.json")["status"], "awaiting_work")
            self.assertNotIn("G3:P01", read(self.project / "state/run.json")["approved_gates"])
            callbacks.append(phase)
            if phase == "initial":
                initial_prereg.append(sha(self.prereg))
            audit = copy.deepcopy(clean)
            if phase == "initial" and repair:
                audit.update(verdict="revise", major_findings=["The synthetic probe needs its declared diagnostic recorded explicitly."])
            path = self.project / f"reviews/independent/{self.run_id}-{phase}.json"
            write(path, audit)
            return audit, path, identity

        def remediate(audit, path, note_stage):
            self.assertTrue(repair)
            self.assertTrue(paper_execution.refreshable_preregistration(self.project, "P01"))
            self.assertEqual(note_stage, "experiment-design")
            text = self.script.read_text() + "\n# Explicit synthetic diagnostic; no scientific result is asserted.\n"
            plan = read(self.fixture.plan_path)
            import hashlib
            plan["runs"][0]["inputs"][0]["sha256"] = hashlib.sha256(text.encode()).hexdigest()
            bundle = {"stage": "experiment-design", "artifacts": [
                {"path": "analysis/probe.py", "content": text},
                {"path": self.fixture.plan_path.relative_to(self.project).as_posix(), "content": json.dumps(plan)}]}
            written = api.apply_bundle(self.slug, bundle, "experiment-design")
            api.record_writer_provenance(self.slug, written, self.writer, "persistent-remediator", self.run_id)
            self.assertEqual(output_provenance.current_origin(self.project, self.script)["family"], "openai")
            self.assertTrue(research_quality.validate_preregistration(read(self.prereg), "P01", self.project))
            return ["fixed: Recorded the specific synthetic diagnostic in the declared source without claiming an observed result."]

        result = research_cycle.review_cycle(self.project, "experiment-design", self.run_id,
            writer_family="openai", prompt=lambda: "Inspect the exact current synthetic protocol and its pending scientific decision.",
            invoke=invoke, remediate=remediate, refresh=refresh, writer_notes=[],
            log=lambda first, last, notes, audit: api.append_decision_log(self.slug, "experiment-design", self.run_id,
                                                                         first, last, notes, audit))
        return result, callbacks, initial_prereg[0]

    def test_one_fresh_critic_receives_native_preregistration_after_method_refresh(self):
        result, callbacks, original = self.cycle()
        self.assertEqual(callbacks, ["initial"])
        self.assertTrue(result["remediation_skipped"])
        self.assertEqual(sha(self.prereg), original)
        self.assertIn("papers/P01/preregistration.json", result["evidence"]["initial"]["automated_quality"]["created"])
        observed = review_receipts.observation(self.project, "experiment-design", "P01")["receipt"]
        self.assertFalse(observed["gate_authority"])
        self.assertIn({"path": "papers/P01/preregistration.json", "sha256": original}, observed["materials"]["files"])
        self.assertNotIn("final", result["audits"])
        self.assertFalse(paper_execution.artifact_path(self.project, "experiments/registry.jsonl").exists())

    def test_unapproved_machine_preregistration_refreshes_after_actual_writer_remediation(self):
        result, callbacks, original = self.cycle(repair=True)
        self.assertEqual(callbacks, ["initial", "final"])
        self.assertFalse(result["remediation_skipped"])
        self.assertNotEqual(sha(self.prereg), original)
        self.assertIn("papers/P01/preregistration.json", result["evidence"]["final"]["automated_quality"]["refreshed"])
        archive = self.project / "state/automated-quality-history" / (original + ".json")
        self.assertEqual(read(archive)["sha256"], original)
        self.assertEqual(review_receipts.validate_gate(self.project, "G3"), [])
        self.assertEqual(researchctl.gate_errors(self.slug, "G3"), [])
        for relative in ("papers/P01/preregistration.json", "data/raw/forged.csv", "results/P01/forged.json"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                api.safe_target(self.slug, relative)
        researchctl.mark_ready(SimpleNamespace(project=self.slug, note="Synthetic protocol check; no scientific acceptance."))
        self.assertFalse(paper_execution.refreshable_preregistration(self.project, "P01"))
        with self.assertRaises(ValueError):
            api.safe_target(self.slug, "analysis/probe.py")

    def test_unapproved_scientific_scope_refuses_machine_preparation_without_writes(self):
        state = read(self.project / "state/run.json")
        state["approved_gates"].remove("G2")
        write(self.project / "state/run.json", state)
        before = {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        result = automated_quality.checked_run(self.project, "experiment-design")
        self.assertTrue(result["blockers"])
        self.assertFalse(self.prereg.exists())
        self.assertEqual(before, {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob("*") if p.is_file()})

    def test_checked_quality_uses_actual_stage_and_skips_nonresearch_stages(self):
        self.assertIsNone(automated_quality.checked_run(self.project, "topic-intelligence"))
        result = automated_quality.checked_run(self.project, "experiment-execution")
        self.assertTrue(result["blockers"])
        self.assertFalse(self.prereg.exists())

    def test_missing_exploratory_preregistration_returns_gate_errors_instead_of_throwing(self):
        paper_execution.prepare_datasets(self.project)
        errors = researchctl.gate_errors(self.slug, "G3")
        self.assertTrue(any("preregistration.json" in issue for issue in errors), errors)
        self.assertFalse(self.prereg.exists())

    def test_unknown_writer_origin_never_becomes_refreshable_machine_authority(self):
        result = automated_quality.checked_run(self.project, "experiment-design")
        self.assertEqual(result["blockers"], [])
        frozen = read(self.prereg)
        frozen["deviation_policy"] += " Forged direct edit."
        write(self.prereg, frozen)
        self.assertFalse(paper_execution.refreshable_preregistration(self.project, "P01"))
        result = automated_quality.checked_run(self.project, "experiment-design")
        self.assertTrue(result["blockers"])
        self.assertEqual(read(self.prereg), frozen)

    def assert_scientific_inputs_locked(self):
        self.assertFalse(paper_execution.refreshable_preregistration(self.project, "P01"))
        self.assertTrue(artifact_ownership.executor_owned(self.project, "analysis/probe.py"))
        with self.assertRaises(ValueError):
            api.safe_target(self.slug, "analysis/probe.py")

    def test_corrupt_approval_marker_without_matching_record_cannot_unlock_inputs(self):
        self.assertEqual(automated_quality.checked_run(self.project, "experiment-design")["blockers"], [])
        state = read(self.project / "state/run.json")
        self.assertFalse(any(row.get("gate") == "G3" for row in state["approvals"]))
        # A corrupt fixture marker is not a fabricated approval: it must fail closed.
        state["approved_gates"].append("G3:P01")
        write(self.project / "state/run.json", state)
        self.assert_scientific_inputs_locked()

    def test_switching_the_active_paper_keeps_earlier_machine_draft_inputs_locked(self):
        self.assertEqual(automated_quality.checked_run(self.project, "experiment-design")["blockers"], [])
        state = read(self.project / "state/run.json")
        state.update(active_paper="P02", paper_count=2)
        write(self.project / "state/run.json", state)
        self.assert_scientific_inputs_locked()

    def test_current_registry_orphan_receipt_and_execution_lease_all_prevent_draft_unlocking(self):
        self.assertEqual(automated_quality.checked_run(self.project, "experiment-design")["blockers"], [])
        registry = paper_execution.artifact_path(self.project, "experiments/registry.jsonl")
        orphan = self.project / "experiments/runs/corrupt-orphan/run.json"
        lease = self.project / "state/experiment-execution-lease.json"
        markers = (
            (registry, {"synthetic_corrupt_registry_marker": True}),
            (orphan, {"paper_id": "P01", "approved_plan_sha256": sha(self.fixture.plan_path),
                      "synthetic_orphan_marker_only": True}),
            (lease, {"status": "running", "synthetic_unresolved_lease_marker": True}),
        )
        for path, marker in markers:
            with self.subTest(marker=path.relative_to(self.project).as_posix()):
                write(path, marker)
                try:
                    if path == registry:
                        # Pretty JSON is deliberately malformed as JSONL. Both
                        # inspection-required and owned-file responses deny writes.
                        self.assertFalse(paper_execution.refreshable_preregistration(self.project, "P01"))
                        with self.assertRaisesRegex(ValueError, "Executor registry is invalid"):
                            artifact_ownership.executor_owned(self.project, "analysis/probe.py")
                        with self.assertRaises(ValueError):
                            api.safe_target(self.slug, "analysis/probe.py")
                    else:
                        self.assert_scientific_inputs_locked()
                finally:
                    path.unlink()
                self.assertTrue(paper_execution.refreshable_preregistration(self.project, "P01"))

    def test_unsealed_snapshot_metadata_refresh_rebinds_machine_protocol_without_changing_raw(self):
        from tests.test_dataset_fetch import valid_manifest
        raw = self.project / "data/raw/fixture.csv"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("value\n-1\n0\n1\n", encoding="utf-8")
        raw_hash = sha(raw)
        manifest = valid_manifest()
        manifest.update(dataset_id="fixture")
        manifest["download"].update(sha256=raw_hash, filename=raw.name, expected_bytes=raw.stat().st_size)
        source = self.project / "data/datasets.jsonl"
        source.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        contract_path = self.project / "papers/P01/paper-contract.json"
        contract = read(contract_path)
        contract["datasets"] = ["fixture"]
        write(contract_path, contract)
        plan = read(self.fixture.plan_path)
        plan["runs"][0]["inputs"].append({"path": "data/raw/fixture.csv", "sha256": raw_hash})
        write(self.fixture.plan_path, plan)
        first = automated_quality.checked_run(self.project, "experiment-design")
        self.assertEqual(first["blockers"], [], first)
        old_prereg = sha(self.prereg)
        snapshot = paper_execution.dataset_snapshot(self.project)
        old_snapshot = sha(snapshot)
        manifest["known_limitations"].append("Additional synthetic metadata warning; original bytes and rights are unchanged.")
        source.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        paper_execution.prepare_datasets(self.project)
        self.assertNotEqual(sha(snapshot), old_snapshot)
        self.assertEqual(sha(self.prereg), old_prereg)
        self.assertTrue(paper_execution.refreshable_preregistration(self.project, "P01"))
        refreshed = automated_quality.checked_run(self.project, "experiment-design")
        self.assertEqual(refreshed["blockers"], [], refreshed)
        self.assertIn("papers/P01/preregistration.json", refreshed["refreshed"])
        self.assertEqual(sha(raw), raw_hash)
        self.assertEqual(research_quality.validate_preregistration(read(self.prereg), "P01", self.project), [])
        with self.assertRaises(ValueError):
            api.safe_target(self.slug, "papers/P01/preregistration.json")
        self.fixture.audit("G3")
        self.assertEqual(researchctl.gate_errors(self.slug, "G3"), [])
        researchctl.mark_ready(SimpleNamespace(project=self.slug, note="Synthetic data-source protocol check, not scientific acceptance."))
        sealed_snapshot = sha(snapshot)
        manifest["known_limitations"].append("A later synthetic metadata update after G3 sealing.")
        source.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after protocol freezing"):
            paper_execution.prepare_datasets(self.project)
        self.assertEqual(sha(snapshot), sealed_snapshot)
        self.assertEqual(sha(raw), raw_hash)


if __name__ == "__main__":
    unittest.main()
