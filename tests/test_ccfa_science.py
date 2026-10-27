"""Cloud-run synthetic CCFA contract checks; not scientific validation."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ccfa_science as science, literature_evidence, literature_workbench, output_provenance, source_scope
from scripts.research_artifacts import read, sha, write


class CCFAScienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1", "GITHUB_ACTIONS": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.question = "When does calibration transfer across devices?"
        self.primary = self.text("evidence/sources/a.md", "# Mechanism\nA held-out device tests transfer.\n# Evidence\nCalibration fails under sensor drift.\n")
        self.claim = self.json("program/novelty-claim-matrix.json", {"schema_version": "1.0", "claims": [
            {"claim_id": "C1", "paper_ids": ["P01"], "claim": "Calibration transfers across devices", "precise_difference": "Adapt to drift"}]})

    def track(self, target, *, family="openai", model="fixture-writer", provider="fixture"):
        output_provenance.record_model_writes(self.project, [target], family=family, provider=provider,
            model=model, role="writer", run_id="synthetic-ccfa-test")
        return {"path": target.relative_to(self.project).as_posix(), "sha256": sha(target)}

    def text(self, path, text):
        target = self.project / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return self.track(target)

    def json(self, path, value, **kwargs):
        target = self.project / path
        write(target, value)
        return self.track(target, **kwargs)

    def anchor(self, binding=None, line=2):
        binding = binding or self.primary
        lines = (self.project / binding["path"]).read_text(encoding="utf-8").splitlines()
        return {**binding, "locator": f"L{line}", "excerpt": lines[line - 1].strip()}

    def claim_anchor(self):
        lines = (self.project / self.claim["path"]).read_text(encoding="utf-8").splitlines()
        line = next(i + 1 for i, value in enumerate(lines) if "Calibration transfers" in value)
        return {**self.claim, "locator": f"L{line}", "excerpt": "Calibration transfers across devices"}

    def request(self, operation, data, *, identifier="case", previous=None, **changes):
        value = {"schema_version": "1.0", "operation": operation, "id": identifier,
                 "doctoral_question": self.question, "paper_ids": ["P01"], "data": data, **changes}
        relative = f"program/ccfa-inputs/{operation}-{identifier}.json"
        target = self.project / relative
        expected = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        origin = output_provenance.current_origin(self.project, target) if target.is_file() else {}
        # An exact queue replay reuses the existing authored input. Re-recording
        # identical bytes would create a new provenance event across a clock tick.
        if (target.is_file() and target.read_bytes() == expected
                and all(origin.get(key) == item for key, item in {
                    "status": "tracked", "family": "openai", "provider": "fixture",
                    "model": "fixture-writer", "role": "writer", "run_id": "synthetic-ccfa-test"}.items())):
            binding = {"path": relative, "sha256": sha(target)}
        else:
            binding = self.json(relative, value)
        return {"schema_version": "1.0", "id": identifier, "source": binding["path"],
            "expected_source_sha256": binding["sha256"], "expected_previous_sha256": previous}

    def run_op(self, operation, data, **kwargs):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid calls")):
            return science.execute(self.project, operation, self.request(operation, data, **kwargs))

    def continuity(self):
        return {"goal_revision": 1, "objective": "Verify the transfer mechanism under drift.",
            "constraints": ["Keep six papers under one doctoral question", "Cloud execution only"],
            "acceptance": ["Source-bound tests and no invented results"], "authoritative_inputs": [self.claim],
            "route": {"id": "compare", "summary": "Compare measurement and device effects."},
            "next_action": "Read the held-out-device protocol.", "mode": "normal", "open_items": ["Resolve split unit"],
            "artifacts": [{"file": self.primary, "status": "executed"}]}

    def test_cloud_only_and_bounded_operation_envelope(self):
        request = self.request("continuity", self.continuity())
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(ValueError, "cloud"):
                science.execute(self.project, "continuity", request)
        for change in ({"source": "../secrets.json"}, {"id": "../../escape"}, {"approve": True}):
            with self.assertRaises(ValueError):
                science.execute(self.project, "continuity", {**request, **change})

    def test_continuity_is_bound_and_reused_without_new_history(self):
        request = self.request("continuity", self.continuity())
        result = science.execute(self.project, "continuity", request)
        request["expected_previous_sha256"] = result["sha256"]
        repeated = science.execute(self.project, "continuity", request)
        self.assertTrue(repeated["reused"])
        self.assertEqual(result["sha256"], repeated["sha256"])
        self.assertFalse((self.project / science.PREFIX / "history").exists())
        self.assertFalse(result["report"]["result"]["replaces_existing_project_state"])
        self.assertEqual(science.current(self.project, "continuity", "case"), result["report"])

    def test_exact_initial_queue_request_replays_without_changing_cas_or_report(self):
        request = self.request("continuity", self.continuity())
        first = science.execute(self.project, "continuity", request)
        original = (self.project / first["path"]).read_bytes()
        second = science.execute(self.project, "continuity", request)
        self.assertTrue(second["reused"])
        self.assertTrue(second["exact_request_replay"])
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual((self.project / first["path"]).read_bytes(), original)
        self.assertFalse((self.project / science.PREFIX / "history").exists())

    def test_replay_does_not_accept_different_source_stale_cas_or_changed_evidence(self):
        data = self.continuity()
        request = self.request("continuity", data)
        first = science.execute(self.project, "continuity", request)
        data["next_action"] = "Inspect the newly supplied alternative protocol."
        different = self.request("continuity", data)
        with self.assertRaisesRegex(ValueError, "previous"):
            science.execute(self.project, "continuity", different)
        different["expected_previous_sha256"] = first["sha256"]
        second = science.execute(self.project, "continuity", different)
        self.assertFalse(second["reused"])
        with self.assertRaisesRegex(ValueError, "previous|stale"):
            science.execute(self.project, "continuity", request)
        self.text(self.primary["path"], "The underlying source version changed.\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            science.execute(self.project, "continuity", different)

    def test_same_queue_twice_runs_actual_after_write_without_false_operation_error(self):
        from scripts import cloud_research_steps
        request = self.request("continuity", self.continuity())
        self.json("program/cloud-operations.json", {"operations": [{"stage": "paper-architecture", "action": "ccfa_science",
            "operation": "continuity", "request": request}]})
        first = cloud_research_steps.after_write(self.project, "paper-architecture")
        second = cloud_research_steps.after_write(self.project, "paper-architecture")
        self.assertEqual(first["operation_errors"], [])
        self.assertEqual(second["operation_errors"], [])
        self.assertTrue(second["ccfa"][-1]["result"]["exact_request_replay"])

    def test_exact_replay_still_requires_current_implementation_and_executor_origin(self):
        for change in ("implementation", "origin"):
            with self.subTest(change=change):
                request = self.request("continuity", self.continuity(), identifier="replay-" + change)
                first = science.execute(self.project, "continuity", request)
                target = self.project / first["path"]
                if change == "implementation":
                    report = read(target)
                    report["implementation_sha256"] = "0" * 64
                    write(target, report)
                    science.record(self.project, [target], science.MODULE)
                else:
                    self.track(target, model="fixture-writer", provider="fixture")
                with self.assertRaisesRegex(ValueError, "implementation|provenance"):
                    science.execute(self.project, "continuity", request)

    def test_source_hash_provenance_and_scope_replayed(self):
        result = self.run_op("continuity", self.continuity())
        self.text(self.primary["path"], "Changed input.\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            science.current(self.project, "continuity", "case")
        self.json("program/core-thesis.json", {"doctoral_question": "Another doctoral question"})
        with self.assertRaisesRegex(ValueError, "doctoral question"):
            self.run_op("continuity", self.continuity(), identifier="new")
        self.assertTrue((self.project / result["path"]).is_file())

    def test_new_canonical_scope_invalidates_pre_scope_cached_report(self):
        result = self.run_op("continuity", self.continuity())
        self.json("program/core-thesis.json", {"doctoral_question": self.question})
        with self.assertRaisesRegex(ValueError, "scope changed"):
            science.current(self.project, "continuity", "case")
        refreshed = self.run_op("continuity", self.continuity(), previous=result["sha256"])
        self.assertFalse(refreshed["reused"])
        self.assertEqual(refreshed["report"]["scope"]["status"], "current_question_bound_not_gate_approval")

    def test_goal_revision_route_evidence_and_immutable_history(self):
        data = self.continuity()
        before = self.run_op("continuity", data)
        data["objective"] = "Narrow the transfer claim to sensor drift."
        with self.assertRaisesRegex(ValueError, "revision"):
            self.run_op("continuity", data, previous=before["sha256"])
        data["goal_revision"] = 2
        with self.assertRaisesRegex(ValueError, "transition"):
            self.run_op("continuity", data, previous=before["sha256"])
        data["transition"] = {"basis": "intent_correction", "reason": "The recorded scope was broader than the supplied question.", "evidence": [self.anchor()]}
        after = self.run_op("continuity", data, previous=before["sha256"])
        history_path = self.project / after["report"]["previous"]["path"]
        self.assertEqual(sha(history_path), before["sha256"])
        report_bytes = (self.project / after["path"]).read_bytes()
        history_bytes = history_path.read_bytes()
        replay = self.run_op("continuity", data, previous=before["sha256"])
        self.assertTrue(replay["reused"])
        self.assertTrue(replay["exact_request_replay"])
        self.assertEqual(replay["sha256"], after["sha256"])
        self.assertEqual((self.project / after["path"]).read_bytes(), report_bytes)
        self.assertEqual(history_path.read_bytes(), history_bytes)
        self.assertEqual(list(history_path.parent.iterdir()), [history_path])
        data["next_action"] = "Compare the revised drift protocol with the held-out-device procedure."
        with self.assertRaisesRegex(ValueError, "previous"):
            self.run_op("continuity", data, previous=before["sha256"])
        self.assertEqual((self.project / after["path"]).read_bytes(), report_bytes)
        self.assertEqual(history_path.read_bytes(), history_bytes)

    def test_revision_queue_replay_reuses_source_provenance_across_clock_ticks(self):
        data = self.continuity()
        with patch.object(output_provenance, "utc_now", return_value="2026-10-01T00:00:00+00:00"):
            before = self.run_op("continuity", data)
        data.update(goal_revision=2, objective="Narrow the transfer claim to sensor drift.",
            transition={"basis": "intent_correction", "reason": "Align the plan to the supplied scope.", "evidence": [self.anchor()]})
        with patch.object(output_provenance, "utc_now", return_value="2026-10-01T00:00:01+00:00"):
            after = self.run_op("continuity", data, previous=before["sha256"])
        source = self.project / after["report"]["source"]["path"]
        origin = output_provenance.current_origin(self.project, source)
        report_bytes = (self.project / after["path"]).read_bytes()
        with patch.object(output_provenance, "utc_now", return_value="2026-10-01T00:00:02+00:00"):
            replay = self.run_op("continuity", data, previous=before["sha256"])
        self.assertTrue(replay["exact_request_replay"])
        self.assertTrue(replay["reused"])
        self.assertEqual(output_provenance.current_origin(self.project, source), origin)
        self.assertEqual((self.project / after["path"]).read_bytes(), report_bytes)
        self.assertEqual(sha(self.project / after["report"]["previous"]["path"]), before["sha256"])

    def test_material_route_change_and_recovery_need_fresh_basis(self):
        data = self.continuity()
        data["mode"] = "focused"
        before = self.run_op("continuity", data)
        data["mode"] = "normal"
        data["transition"] = {"basis": "new_evidence", "reason": "The parser output was repaired.", "evidence": [self.anchor()]}
        with self.assertRaisesRegex(ValueError, "basis"):
            self.run_op("continuity", data, previous=before["sha256"])
        data["transition"]["basis"] = "recovery_check"
        self.run_op("continuity", data, previous=before["sha256"])

    def test_verified_artifact_needs_real_current_check_not_model_assertion(self):
        data = self.continuity()
        data["artifacts"][0]["status"] = "verified"
        with self.assertRaises(ValueError):
            self.run_op("continuity", data)
        check = self.json("reports/fixture-check.json", {"passed": True, "inputs": [self.primary]})
        data["artifacts"][0]["checks"] = [check]
        with self.assertRaisesRegex(ValueError, "native deterministic"):
            self.run_op("continuity", data)
        check = self.track(self.project / check["path"], family="other", model="scripts/ref_verify.py", provider="deterministic-control-plane")
        data["artifacts"][0]["checks"] = [check]
        result = self.run_op("continuity", data)
        self.assertEqual(result["report"]["result"]["artifacts"][0]["status"], "verified")
        self.assertFalse(result["report"]["limits"]["scientific_completion_verified"])

    def test_claude_persistent_source_and_tampered_output_rejected(self):
        request = self.request("continuity", self.continuity())
        self.track(self.project / request["source"], family="anthropic")
        with self.assertRaisesRegex(ValueError, "non-Claude"):
            science.execute(self.project, "continuity", request)
        result = self.run_op("continuity", self.continuity())
        self.json(result["path"], {"operation": "continuity"})
        with self.assertRaisesRegex(ValueError, "provenance"):
            science.current(self.project, "continuity", "case")

    def seed(self, identifier="A"):
        return {"id": identifier, "parents": [], "operator": "seed", "premise": "Calibration changes under drift.",
            "new_inference": "The adaptation timescale may explain transfer failure.",
            "inference_boundary": "A proposed mechanism requiring measurement.", "mechanism_change": "Separate calibration and drift timescales.",
            "component_necessity": "Without drift information the two explanations are indistinguishable.",
            "discriminator": "Hold device identity fixed and vary drift rate.", "conditions": ["Matched tuning budget"],
            "status": "exploratory", "evidence": [self.anchor()]}

    def test_lineage_records_falsifiable_operator_and_separates_proposed_from_measured(self):
        a = self.seed()
        b = {**self.seed("B"), "parents": ["A"], "operator": "refine", "mechanism_change": "Estimate drift before adaptation."}
        result = self.run_op("lineage", {"candidates": [a, b], "selected_candidate": "B", "selection_reason": "The changed timescale can distinguish the rival mechanism."})
        self.assertEqual(result["report"]["result"]["measured_candidates"], [])
        self.assertIsNone(result["report"]["result"]["best_measured_candidate"])
        self.assertFalse(result["report"]["result"]["candidates"][1]["novelty_verified"])
        for changes in ({"parents": ["missing"], "operator": "refine"}, {"parents": ["A"], "operator": "combine"}, {"status": "measured"}):
            with self.assertRaises(ValueError):
                self.run_op("lineage", {"candidates": [a, {**b, **changes}]}, identifier="bad" + str(len(changes)))

    def test_changed_mechanism_requires_new_child_and_prior_branches_preserved(self):
        a = self.seed()
        result = self.run_op("lineage", {"candidates": [a]})
        a["mechanism_change"] = "Replace calibration with a different method."
        with self.assertRaisesRegex(ValueError, "new child"):
            self.run_op("lineage", {"candidates": [a]}, previous=result["sha256"])
        b = self.seed("B")
        with self.assertRaisesRegex(ValueError, "preserve"):
            self.run_op("lineage", {"candidates": [b]}, previous=result["sha256"])

    def test_measured_lineage_uses_native_registry_and_approved_config(self):
        a = self.seed()
        config = self.json("experiments/config-A.json", {"candidate_id": "A", "method": "synthetic fixture"})
        plan = self.json("experiments/plan.json", {"runs": [{"run_id": "trial.v1", "paper_id": "P01", "inputs": [config]}]})
        measured = self.json("results/trial.json", {"synthetic": True, "metric": 0.4})
        run = {"run_id": "trial.v1", "attempt_id": "trial.v1-1", "paper_id": "P01", "status": "succeeded",
               "approved_plan_sha256": plan["sha256"], "input_integrity": {"passed": True}, "inputs": [config], "outputs": [measured]}
        receipt = self.json("experiments/runs/trial.v1-1/run.json", run)
        self.text("experiments/registry.jsonl", json.dumps(run) + "\n")
        a.update(status="measured", measurement={"receipt": receipt, "run_id": "trial.v1", "configuration": config})
        result = self.run_op("lineage", {"candidates": [a]})
        self.assertEqual(result["report"]["result"]["measured_candidates"], ["A"])
        self.text(measured["path"], "{}\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            science.current(self.project, "lineage", "case")

    def library(self):
        cfg = {"schema_version": "1.0", "doctoral_question": self.question, "papers": [
            {"id": "source-a", "title": "Calibration transfer", "source": self.primary,
             "topic_id": "calibration", "paper_ids": ["P01"], "source_scope": "full_text"}]}
        self.json(literature_workbench.CONFIG, cfg)
        literature_workbench.build(self.project)

    def watch(self):
        self.library()
        def fetch(url, **kwargs):
            return json.dumps({"data": [{"paperId": "a", "title": "Calibration transfer", "year": 2026,
                "authors": [{"name": "Synthetic Author"}], "externalIds": {"DOI": "10.1000/fixture"}}]}).encode(), url, 200, "application/json"
        receipt = literature_evidence.execute_search(self.project, "semantic-scholar", "calibration transfer", query_family="fixture",
            date_range="2026", filters="none", limit=1, fetcher=fetch)
        ledger = {"path": "evidence/literature-api-ledger.jsonl", "sha256": sha(self.project / "evidence/literature-api-ledger.jsonl")}
        now = datetime.now(timezone.utc)
        return {"window": {"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()},
            "coverage_receipts": [{"ledger": ledger, "receipt_id": receipt["receipt_id"]}], "claim_source": self.claim,
            "findings": [{"id": "O1", "claim_id": "C1", "paper_id": "source-a", "axes": ["mechanism", "claim"], "signal": "RESEARCH",
                "implication": "Compare the drift assumptions before asserting transfer novelty.", "boundary": "Text overlap is not a priority or novelty judgment.",
                "claim_evidence": [self.claim_anchor()], "source_evidence": [self.anchor()]}]}

    def test_novelty_watch_maps_actual_search_to_specific_claim_and_records_delta(self):
        data = self.watch()
        result = self.run_op("novelty_watch", data)
        body = result["report"]["result"]
        self.assertEqual(body["delta"]["new"], ["O1"])
        self.assertFalse(body["empty_scan_proves_novelty"])
        self.assertFalse(body["findings"][0]["semantic_overlap_verified"])
        data["findings"][0]["signal"] = "FOLLOW-UP"
        after = self.run_op("novelty_watch", data, previous=result["sha256"])
        self.assertEqual(after["report"]["result"]["delta"]["changed"], ["O1"])

    def test_novelty_watch_refuses_missing_claim_forged_anchor_and_unexecuted_coverage(self):
        data = self.watch()
        for mutate in (lambda d: d["findings"][0].update(claim_id="missing"),
                       lambda d: d["findings"][0]["source_evidence"][0].update(excerpt="Not in the source"),
                       lambda d: d["coverage_receipts"][0].update(receipt_id="missing")):
            bad = copy.deepcopy(data)
            mutate(bad)
            with self.assertRaises(ValueError):
                self.run_op("novelty_watch", bad)

    def test_novelty_watch_raw_response_mutation_invalidates_report(self):
        result = self.run_op("novelty_watch", self.watch())
        raw = next(b for b in result["report"]["inputs"] if b.get("kind") == "native_retrieval_raw")
        (self.project / raw["path"]).write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "raw response"):
            science.current(self.project, "novelty_watch", "case")

    def exemplar(self):
        self.library()
        receipt = source_scope.record(self.project, self.primary["path"], "full_text", "Synthetic supplied-scope fixture")
        return {"paper_id": "source-a", "scope_record": {"path": receipt.relative_to(self.project).as_posix(), "sha256": sha(receipt)},
            "article_type": "Original research", "moves": {name: [{"pattern": "State the comparison unit before interpreting transfer.",
                "purpose": "Make the inferential unit explicit.", "transfer_conditions": "Use only if supported by our actual study.",
                "evidence": [self.anchor()]}] for name in science.EXEMPLAR_MOVES},
            "do_not_copy": ["Do not transfer source claims or distinctive wording"],
            "selection_conditions": ["Use for device-level transfer papers with matched study design"]}

    def test_full_paper_exemplar_covers_seven_writing_move_families(self):
        result = self.run_op("exemplar", self.exemplar())
        body = result["report"]["result"]
        self.assertEqual(set(body["moves"]), science.EXEMPLAR_MOVES)
        self.assertFalse(body["human_reading_verified"])
        self.assertFalse(body["global_defaults_changed"])

    def test_exemplar_rejects_abstract_scope_missing_move_and_wrong_page(self):
        data = self.exemplar()
        bad = copy.deepcopy(data)
        del bad["moves"]["citations"]
        with self.assertRaises(ValueError):
            self.run_op("exemplar", bad)
        receipt = source_scope.record(self.project, self.primary["path"], "abstract", "Synthetic scope fixture")
        data["scope_record"] = {"path": receipt.relative_to(self.project).as_posix(), "sha256": sha(receipt)}
        with self.assertRaisesRegex(ValueError, "scope"):
            self.run_op("exemplar", data)

    def review(self):
        historical = self.text("papers/P01/manuscript/old.md", "# Method\nThe split unit is not specified.\n")
        current = self.text("papers/P01/manuscript/current.md", "# Method\nThe split holds out whole devices.\n")
        return {"historical": historical, "current": current, "scope": "Methods-only internal comparison",
            "criteria": [{"id": "unit", "criterion": "Specify independent split unit", "scope": "Methods"}],
            "readiness_criteria": [{"id": "evidence", "criterion": "Claims have checked evidence", "scope": "Current manuscript"}],
            "issues": [{"id": "I1", "first_seen_version": "v1", "status": "unresolved", "origin": "previously_undetected", "applies_to": "both",
                "dimensions": ["unit"], "severity": "major", "finding": "The split unit must be explicit.",
                "evidence": [self.anchor(historical), self.anchor(current)], "resolution": "Check the held-out unit against the frozen protocol."}],
            "readiness": [{"criterion_id": "evidence", "status": "needs_revision", "rationale": "The protocol still needs verification.", "evidence": [self.anchor(current)]}]}

    def test_internal_review_separates_frozen_progress_from_current_readiness(self):
        data = self.review()
        before = self.run_op("internal_review", data)
        data["issues"][0].update(status="resolved", origin="inherited", resolution="The current text now states whole-device separation.")
        after = self.run_op("internal_review", data, previous=before["sha256"])
        self.assertEqual(after["report"]["result"]["relative_progress"], "improved")
        self.assertEqual(after["report"]["result"]["current_readiness"], "revise")
        self.assertIsNone(after["report"]["result"]["acceptance_probability"])
        self.assertFalse(after["report"]["result"]["external_reviewer_round_created"])

    def test_internal_review_fixed_criteria_stable_issue_and_no_silent_deletion(self):
        data = self.review()
        before = self.run_op("internal_review", data)
        mutations = (lambda d: d["criteria"][0].update(criterion="Different standard"),
                     lambda d: d.update(issues=[]),
                     lambda d: d["issues"][0].update(first_seen_version="v2"),
                     lambda d: d["issues"][0].update(finding="Different issue"))
        for mutate in mutations:
            bad = copy.deepcopy(data)
            mutate(bad)
            with self.assertRaises(ValueError):
                self.run_op("internal_review", bad, previous=before["sha256"])

    def test_internal_review_latent_issue_cannot_only_penalize_current_and_scores_rejected(self):
        data = self.review()
        data["issues"][0]["applies_to"] = "current"
        with self.assertRaisesRegex(ValueError, "both"):
            self.run_op("internal_review", data)
        data = self.review()
        data["score"] = 95
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.run_op("internal_review", data)

    def test_internal_review_updated_manuscript_reopens_evidence_requirements(self):
        data = self.review()
        result = self.run_op("internal_review", data)
        self.text(data["current"]["path"], "Changed the current mechanism.\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            science.current(self.project, "internal_review", "case")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.run_op("internal_review", data, previous=result["sha256"])


if __name__ == "__main__":
    unittest.main()
