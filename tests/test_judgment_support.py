"""Mechanical scientific-judgment support; every example is synthetic."""
import json
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import innovation_screening as innovation, literature_benchmark as benchmark
from scripts import literature_source_tasks as tasks, research_notebook as notebook, output_provenance as provenance
from scripts.research_artifacts import read, record, sha, write
from scripts import review_receipts


class JudgmentSupportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)

    def text(self, relative, text):
        target = self.project / relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8"); record(self.project, [target], "synthetic-source-fixture")
        return {"path": relative, "sha256": sha(target), "locator": "whole retained source"}

    def anchors(self, *, public=False, count=2):
        cases = []
        for index in range(count):
            partition = "holdout" if index == count - 1 or index % 3 == 2 else "calibration"
            source = self.text(f"literature/anchors/paper-{index}.txt", f"Synthetic original method {index}.")
            row = {"id": "case-" + str(index), "paper_doi": f"10.1000/fixture-{index}", "partition": partition,
                "source": source, "quote": f"Synthetic original method {index}.", "label": "should_merge",
                "question": "Does the proposed extra step change a discriminating prediction?"}
            if public:
                review_text = f"EXPECTED_LABEL_ONLY: proposal {index} should be merged."
                row["review"] = self.text(f"literature/anchors/review-{index}.txt", review_text)
                row.update(review_quote=review_text, review_url="https://public.example/review-" + str(index))
                rights_path = self.project / f"evidence/licenses/review-{index}.json"
                write(rights_path, {"reuse_allowed": True, "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "review_sha256": row["review"]["sha256"], "paper_source_sha256": source["sha256"]})
                row["rights"] = {"path": rights_path.relative_to(self.project).as_posix(), "sha256": sha(rights_path), "locator": "synthetic license fixture"}
            cases.append(row)
        path = self.project / "program/anchor-labels.json"
        write(path, {"kind": "public_review" if public else "synthetic_fixture", "cases": cases})
        return {"schema_version": "1.0", "id": "anchors", "anchor_set": {"path": "program/anchor-labels.json",
            "sha256": sha(path), "locator": "complete labeled set"}}

    def prediction(self, name, outcome):
        target = self.project / f"evidence/predictions/{name}.json"
        packet = benchmark.judgment_benchmark(self.project, {"schema_version": "1.0", "id": "anchors",
            "anchor_set": {"path": "program/anchor-labels.json", "sha256": sha(self.project / "program/anchor-labels.json"), "locator": "fixture"}})
        write(target, {"anchor_labels": [{"case_id": row["id"], "case_sha256": row["case_sha256"], "outcome": outcome,
            "rationale": "Synthetic outcome fixture, not an empirical model prediction."} for row in packet["blind_cases"]]})
        provenance.record_model_writes(self.project, [target], family="anthropic", provider="fixture",
            model=name, role="independent-critic", run_id="synthetic-prediction")
        return {"path": target.relative_to(self.project).as_posix(), "sha256": sha(target), "locator": "whole original response"}

    def test_synthetic_cases_never_become_real_calibration_and_missing_labels_are_not_zero_accuracy(self):
        result = benchmark.judgment_benchmark(self.project, self.anchors())
        self.assertEqual(result["attributed_public_paper_count"], 0)
        self.assertFalse(result["requested_anchor_design_complete"])
        self.assertEqual(result["results"], [])
        self.assertEqual(result["calibration_status"], "NOT_CALIBRATED")
        self.assertEqual(result["execution_status"], "no_predictions")

    def test_real_label_mechanism_separates_original_papers_and_review_answers(self):
        spec = self.anchors(public=True)
        request = "program/judgment-benchmark.json"; write(self.project / request, spec)
        tasks.refresh(self.project, "judgment_benchmark", request)
        blind = tasks.model_context(self.project, "judgment_benchmark", request, "critic")
        serialized = json.dumps(blind)
        self.assertNotIn("EXPECTED_LABEL_ONLY", serialized)
        self.assertNotIn("anchor-labels.json", serialized)
        self.assertNotIn("should_merge\"", serialized)
        self.assertIn("Synthetic original method", serialized)
        self.assertFalse(benchmark.judgment_benchmark(self.project, spec)["requested_anchor_design_complete"])
        prepared = tasks.prepare_panel_task(self.project, "judgment_benchmark", request)
        self.assertNotIn("partition", json.dumps(prepared["packet"]))
        self.assertNotIn("EXPECTED_LABEL_ONLY", json.dumps(prepared["packet"]))
        self.assertIn("program/anchor-labels.json", {s["path"] for s in prepared["sources"]})

    def test_wrong_predictions_are_measured_and_distinct_models_not_averaged(self):
        spec = self.anchors()
        spec["predictions"] = [self.prediction("wrong", "distinct"), self.prediction("matching", "should_merge")]
        report = benchmark.judgment_benchmark(self.project, spec)
        rows = report["results"]
        self.assertEqual(report["execution_status"], "complete")
        self.assertFalse(report["numeric_score_calibration_verified"])
        self.assertTrue(all(row["comparison_complete"] and not row["runtime_receipt_verified"] for row in rows))
        self.assertEqual([r["should_merge_detection"] for r in rows], [0, 1])
        self.assertEqual([r["partitions"]["holdout"]["agreement"] for r in rows], [0, 1])

    def test_benchmark_distinguishes_partial_predictions_and_rejects_different_case_sources(self):
        spec = self.anchors()
        prediction = self.prediction("partial", "should_merge")
        path = self.project / prediction["path"]
        payload = read(path)
        payload["anchor_labels"].pop()
        write(path, payload)
        provenance.record_model_writes(self.project, [path], family="anthropic", provider="fixture",
            model="partial", role="independent-critic", run_id="synthetic-prediction")
        prediction["sha256"] = sha(path)
        spec["predictions"] = [prediction]
        result = benchmark.judgment_benchmark(self.project, spec)
        self.assertEqual(result["execution_status"], "partial")
        self.assertEqual(result["results"][0]["partitions"]["holdout"]["missing_case_ids"], ["case-1"])
        self.assertIsNone(result["results"][0]["partitions"]["holdout"]["agreement"])
        anchor_path = self.project / spec["anchor_set"]["path"]
        anchors = read(anchor_path)
        anchors["cases"][0]["question"] = "A different scientific question with the same case ID."
        write(anchor_path, anchors)
        spec["anchor_set"]["sha256"] = sha(anchor_path)
        with self.assertRaisesRegex(ValueError, "different blind source/question"):
            benchmark.judgment_benchmark(self.project, spec)

    def test_global_benchmark_reuses_current_protected_observation_without_a_new_model_call(self):
        spec = self.anchors()
        prediction = self.prediction("existing", "should_merge")
        response = {"receipt": {"response": {"path": prediction["path"], "sha256": prediction["sha256"]},
            "identity": {"requested_model": "existing"}}, "response": read(self.project / prediction["path"])}
        with patch.object(tasks, "judgment_responses", return_value=[response]) as observations:
            report = benchmark.judgment_benchmark(self.project, spec)
        observations.assert_called_once_with(self.project, None)
        self.assertTrue(report["results"][0]["runtime_receipt_verified"])
        self.assertEqual(report["execution_status"], "complete")
        self.assertFalse(report["model_call_made"])

    def test_complete_public_design_needs_protected_runtime_before_claiming_empirical_comparison(self):
        # This is a synthetic 24-case transport fixture, not a new public corpus.
        spec = self.anchors(public=True, count=24)
        prediction = self.prediction("existing", "should_merge")
        spec["predictions"] = [prediction]
        report = benchmark.judgment_benchmark(self.project, spec)
        self.assertTrue(report["requested_anchor_design_complete"])
        self.assertEqual(report["execution_status"], "complete")
        self.assertEqual(report["calibration_status"], "NOT_CALIBRATED")
        response = {"receipt": {"response": {"path": prediction["path"], "sha256": prediction["sha256"]},
            "identity": {"requested_model": "existing"}}, "response": read(self.project / prediction["path"])}
        with patch.object(tasks, "judgment_responses", return_value=[response]):
            report = benchmark.judgment_benchmark(self.project, spec)
        self.assertEqual(report["calibration_status"], "EMPIRICAL_COMPARISON_COMPLETE")
        self.assertEqual([report["results"][0]["partitions"][part]["predictions"]
            for part in ("calibration", "holdout")], [16, 8])
        self.assertFalse(report["numeric_score_calibration_verified"])
        self.assertFalse(report["scientific_completion_verified"])

    def test_anchor_paper_identity_requires_a_real_doi_shape(self):
        for public in (False, True):
            spec = self.anchors(public=public)
            target = self.project / spec["anchor_set"]["path"]
            value = read(target); value["cases"][0]["paper_doi"] = "arbitrary-paper-name"
            write(target, value); spec["anchor_set"]["sha256"] = sha(target)
            with self.subTest(public=public), self.assertRaisesRegex(ValueError, "DOI"):
                benchmark.judgment_benchmark(self.project, spec)

    def test_same_paper_or_review_does_not_leak_into_holdout(self):
        spec = self.anchors()
        target = self.project / spec["anchor_set"]["path"]
        values = read(target); values["cases"][1]["paper_doi"] = values["cases"][0]["paper_doi"]; write(target, values)
        spec["anchor_set"]["sha256"] = sha(target)
        with self.assertRaisesRegex(ValueError, "leak"):
            benchmark.judgment_benchmark(self.project, spec)
        spec = self.anchors()
        values = read(target)
        values["cases"][1].update(source=values["cases"][0]["source"], quote=values["cases"][0]["quote"], partition="calibration")
        write(target, values)
        spec["anchor_set"]["sha256"] = sha(target)
        with self.assertRaisesRegex(ValueError, "different paper DOIs"):
            benchmark.judgment_benchmark(self.project, spec)

    def test_model_authored_text_cannot_impersonate_published_review_anchor(self):
        spec = self.anchors(public=True)
        target = self.project / read(self.project / spec["anchor_set"]["path"])["cases"][0]["review"]["path"]
        provenance.record_model_writes(self.project, [target], family="other", provider="fixture", model="custom-writer", role="writer", run_id="fixture")
        with self.assertRaisesRegex(ValueError, "model-authored or untracked"):
            benchmark.judgment_benchmark(self.project, spec)

    def test_should_merge_concern_is_retained_even_when_novelty_sources_are_incomplete(self):
        write(self.project / "program/novelty-claim-matrix.json", {"claims": [
            {"claim_id": "N1", "paper_ids": ["P01"]}, {"claim_id": "N2", "paper_ids": ["P02"]}]})
        def response(_project, _paper):
            return [{"receipt": {"response": {"path": "retained-fixture", "sha256": "a" * 64}, "identity": {"family": "anthropic"}},
                "response": {"novelty_adjudication": [{"claim_ids": ["N1", "N2"], "decision": "should_merge",
                    "rationale": "Removing the declared centering step leaves the baseline unchanged.", "shared_mechanism": "Same retained linear operation.",
                    "discriminating_prediction": "A different response under the matched input is not established.", "remaining_uncertainty": "Original source comparison still needs completion."}]}}]
        result = innovation.adjudication(self.project, {"schema_version": "1.0", "id": "merge", "paper_id": "P01",
            "pairs": [{"claim_ids": ["N1", "N2"], "question": "Does removal recover the baseline?"}]}, observed=response(self.project, "P01"))
        self.assertTrue(result["pairs"][0]["merge_concern_present"])
        self.assertEqual(result["pairs"][0]["decision"], "insufficient")
        self.assertTrue(result["source_validation_errors"])
        self.assertFalse(result["novelty_verified"])

    def test_each_novelty_pair_needs_its_own_bound_neighbours_and_adjacent_fields(self):
        claims = [{"claim_id": "N" + str(i), "paper_ids": ["P01" if i % 2 else "P02"],
                   "closest_work_ids": ["W" + str(n) for n in range(1, 4 if i <= 2 else 6)]}
                  for i in range(1, 5)]
        write(self.project / "program/novelty-claim-matrix.json", {"claims": claims})
        originality = {"closest_prior_work": [{"id": "W" + str(i), "primary_source_url": f"https://doi.org/10.1000/fixture-{i}"}
                                             for i in range(1, 6)],
                       "search_scope": {"adjacent_fields": ["Field A", "Field B", "Field C"]}}
        write(self.project / "program/originality-audit.json", originality)
        spec = {"schema_version": "1.0", "id": "pair-coverage", "paper_id": "P01", "pairs": [
            {"claim_ids": ids, "question": "Does this synthetic contrast change a prediction?"}
            for ids in (["N1", "N2"], ["N3", "N4"])]}
        observed = [{"receipt": {"response": {"path": "fixture-review", "sha256": "a" * 64},
                                 "identity": {"family": "anthropic"}},
                     "response": {"novelty_adjudication": [
                         {"claim_ids": row["claim_ids"], "decision": "distinct",
                          **dict.fromkeys(("rationale", "shared_mechanism", "discriminating_prediction", "remaining_uncertainty"),
                                          "Synthetic finding, not scientific clearance.")}
                         for row in spec["pairs"]]}}]
        # Source authenticity is separately exercised by the hard-gate tests;
        # isolate whether global coverage can conceal a deficient pair here.
        with patch.object(innovation, "validate_novelty_gate", return_value=[]):
            report = innovation.adjudication(self.project, spec, observed=observed)
            self.assertEqual(len(report["nearest_works"]), 5)
            self.assertEqual([p["decision"] for p in report["pairs"]], ["insufficient", "distinct"])
            self.assertIn("five distinct", report["pairs"][0]["coverage_gaps"][0])
            originality["search_scope"]["adjacent_fields"] = ["Field A", "field a", "Field B"]
            write(self.project / "program/originality-audit.json", originality)
            observed[0]["response"]["novelty_adjudication"][0]["decision"] = "should_merge"
            report = innovation.adjudication(self.project, spec, observed=observed)
            self.assertEqual([p["decision"] for p in report["pairs"]], ["insufficient", "insufficient"])
            self.assertTrue(report["pairs"][0]["merge_concern_present"])
            self.assertFalse(report["novelty_verified"])

    def test_failed_memory_keeps_original_evidence_and_does_not_recycle_model_text_as_fact(self):
        original = self.text("results/failed-check.txt", "The discriminating check did not resolve the mechanism.")
        generated = self.text("literature/notes/model-memory.txt", "The model previously declared a scientific conclusion.")
        provenance.record_model_writes(self.project, [self.project / generated["path"]], family="openai", provider="fixture", model="fixture", role="writer", run_id="fixture")
        decision = {"id": "failed-idea", "phase": "failed", "outcome": "failed", "decision": "Revisit only with a new discriminating measurement.",
            "rationale": "The existing check did not distinguish the hypotheses.", "evidence_ids": ["original", "summary"],
            "failure_condition": "No separation under the stated contrast.", "stop_rule": "Do not repeat the same uninformative design."}
        write(self.project / notebook.NOTEBOOK, {"questions": [{"id": "unknown", "question": "Which mechanism explains the observed result?",
            "evidence": [{"id": "original", "stance": "contradicts", "observation": "Observed failed distinction.", "read_scope": "experiment", "source": original},
                {"id": "summary", "stance": "unknown", "observation": "Model memory only.", "read_scope": "abstract", "source": generated}], "decisions": [decision]}]})
        result = notebook.failed_memory(self.project, {"schema_version": "1.0", "id": "failures"})
        entry = result["failed_or_stopped_ideas"][0]
        self.assertEqual(len(entry["original_evidence"]), 1)
        self.assertTrue(entry["missing_evidence"])
        self.assertEqual(entry["decision"], decision)
        self.assertFalse(entry["interpretation_verified"])

    def selected_novelty(self):
        write(self.project / "state/run.json", {"stage": "topic-intelligence", "gate": "G1"})
        write(self.project / "program/novelty-claim-matrix.json", {"claims": [
            {"claim_id": "N1", "paper_ids": ["P01"]}, {"claim_id": "N2", "paper_ids": ["P02"]}]})
        spec = {"schema_version": "1.0", "id": "merge", "paper_id": "P01",
            "pairs": [{"claim_ids": ["N1", "N2"], "question": "Does removal recover the baseline?"}]}
        write(self.project / "program/novelty-task.json", spec)
        write(self.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "novelty_adjudication",
            "request_file": "program/novelty-task.json", "stages": ["topic-intelligence", "paper-architecture"]}]})
        return spec

    def seal_observation(self, *, stage="topic-intelligence"):
        audit_path = self.project / "reviews/independent/current-observation.json"
        audit = {"verdict": "revise", **{key: [] for key in review_receipts.FIELDS - {"verdict"}},
            "novelty_assessment": [{"claim_id": "N1", "decision": "overlap", "rationale": "Removing the extra step preserves the mechanism."}]}
        write(audit_path, audit)
        identity = {"provider": "synthetic-critic", "family": "anthropic", "requested_model": "fixture",
            "reported_model": "fixture", "completion_status": "completed", "cache_hit": False}
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}):
            return review_receipts.seal_phase(self.project, stage=stage, run_id="current", phase="observation",
                audit_path=audit_path, prompt=json.dumps(tasks.selected_context(self.project, stage), ensure_ascii=False),
                identity=identity, writer_family="openai",
                materials=review_receipts.material_snapshot(self.project, stage))

    def test_g1_and_g2_consume_current_source_bound_observation_without_final_panel(self):
        spec = self.selected_novelty()
        self.assertEqual(tasks.judgment_responses(self.project, "P01"), [])
        prepared = tasks.selected_context(self.project, "topic-intelligence")
        self.assertEqual(prepared["tasks"][0]["operation"], "novelty_adjudication")
        self.assertEqual(prepared["tasks"][0]["packet"]["claim_novelty_judgments"], [])
        self.seal_observation()
        assessed = innovation.adjudication(self.project, spec)
        self.assertEqual(assessed["claim_novelty_judgments"][0]["decision"], "overlap")
        write(self.project / "state/run.json", {"stage": "paper-architecture", "gate": "G2"})
        self.seal_observation(stage="paper-architecture")
        self.assertEqual(len(innovation.adjudication(self.project, spec)["claim_novelty_judgments"]), 1)

    def test_existing_stale_tampered_or_orphaned_observation_is_never_preparation(self):
        self.selected_novelty()
        self.seal_observation()
        source = self.project / "program/novelty-claim-matrix.json"
        original = source.read_bytes(); source.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            tasks.judgment_responses(self.project, "P01")
        source.write_bytes(original)
        audit = self.project / "reviews/independent/current-observation.json"
        original_audit = audit.read_bytes(); audit.write_bytes(original_audit + b"\n")
        with self.assertRaises(ValueError): tasks.judgment_responses(self.project, "P01")
        audit.write_bytes(original_audit)
        (self.project / "state/review-receipts/G1/observation-latest.json").unlink()
        with self.assertRaisesRegex(ValueError, "pointer is missing"):
            tasks.judgment_responses(self.project, "P01")

    def claim_observation(self, *, bind_prompt=True):
        from tests.test_claim_evidence import ClaimEvidenceTests
        from tests.test_review_panel import ReviewPanelTests, panel_inputs
        from scripts import api_orchestrator as api
        fixture = ClaimEvidenceTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        case = ReviewPanelTests(); case.setUp(); self.addCleanup(case.doCleanups)
        case.project = fixture.project
        main = fixture.paper / "main.tex"
        main.write_text("\\documentclass{article}\n\\begin{document}\n" + main.read_text() + "\n\\end{document}\n")
        panel_inputs(fixture.project)
        state = {"stage": "writing-and-review", "gate": "G5", "active_paper": "P01", "paper_count": 6,
                 "writing_phases": {"P01": "scientific"}}
        write(fixture.project / "state/run.json", state)
        request = "program/claim-task.json"
        write(fixture.project / request, fixture.spec)
        write(fixture.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "claim_evidence",
            "request_file": request, "paper_id": "P01", "stages": ["writing-and-review"]}]})
        audit = {"verdict": "revise", **{key: [] for key in review_receipts.FIELDS - {"verdict"}},
                 **fixture.response("supports")["response"]}
        audit["fatal_findings"] = ["ORDINARY_OPINION_MUST_NOT_LEAK_TO_PANEL"]
        path = fixture.project / "reviews/independent/source-observation.json"
        write(path, audit)
        with patch.object(api, "project_root", return_value=fixture.project):
            prompt = api.critic_prompt("fixture", "writing-and-review", "") if bind_prompt else "Legacy unbound prompt"
        identity = {"provider": "synthetic-critic", "family": "anthropic", "requested_model": "fixture",
            "reported_model": "fixture", "completion_status": "completed", "cache_hit": False}
        binding = review_receipts.seal_phase(fixture.project, stage="writing-and-review", run_id="source-reading", phase="observation",
            audit_path=path, prompt=prompt, identity=identity, writer_family="openai",
            materials=review_receipts.material_snapshot(fixture.project, "writing-and-review", "P01"))
        return fixture, case, state, binding

    def test_task_bound_claim_judgment_survives_submission_phase_and_final_panel_without_leaking_opinions(self):
        from scripts import claim_evidence, review_panel, model_runtime
        fixture, case, state, binding = self.claim_observation()
        project = fixture.project
        receipt = read(project / binding["path"])
        self.assertEqual(len(receipt["source_task_bindings"]), 1)
        self.assertEqual(claim_evidence.build(project, fixture.spec)["claims"][0]["outcome"], "supports")
        state["writing_phases"]["P01"] = "submission"
        write(project / "state/run.json", state)
        write(project / "papers/P01/venue.json", {"venue_id": "synthetic-B-preparation-only"})
        self.assertFalse(review_receipts.materials_match(receipt["materials"],
            review_receipts.material_snapshot(project, "writing-and-review", "P01")))
        responses = tasks.judgment_responses(project, "P01")
        self.assertEqual(set(responses[0]["response"]), {"claim_evidence"})
        self.assertFalse(responses[0]["receipt"]["gate_authority"])
        self.assertTrue(responses[0]["receipt"]["reused_source_task_bindings"])
        with patch.object(model_runtime, "call", side_effect=case.response) as calls:
            review_panel.run(project, "P01", "final-isolated-views")
        self.assertEqual(calls.call_count, 3)
        for call in calls.call_args_list:
            self.assertNotIn("ORDINARY_OPINION_MUST_NOT_LEAK_TO_PANEL", call.kwargs["prompt"])
            self.assertNotIn("The original PDF reports a controlled method.", call.kwargs["prompt"])
            self.assertNotIn('"claim_evidence"', call.kwargs["prompt"])
        self.assertEqual(len(tasks.judgment_responses(project, "P01")), 4)
        self.assertEqual(claim_evidence.build(project, fixture.spec)["claims"][0]["outcome"], "supports")
        self.assertTrue(review_receipts.validate_gate(project, "G5", "P01"))  # Source-only reuse grants no gate.
        state["stage"] = "submission-ready"
        write(project / "state/run.json", state)
        self.assertEqual(claim_evidence.build(project, fixture.spec)["claims"][0]["outcome"], "supports")
        original = fixture.reader.read_bytes(); fixture.reader.write_bytes(original + b"\nChanged source.\n")
        with self.assertRaises(ValueError): claim_evidence.build(project, fixture.spec)
        fixture.reader.write_bytes(original)
        self.assertEqual(claim_evidence.build(project, fixture.spec)["claims"][0]["outcome"], "supports")
        changed = read(project / "program/claim-task.json")
        changed["claims"][0]["claim"] += " changed scientific packet"
        write(project / "program/claim-task.json", changed)
        with self.assertRaises(ValueError): tasks.judgment_responses(project, "P01")

    def test_unbound_legacy_observation_does_not_acquire_a_reusable_task_binding(self):
        from scripts import claim_evidence
        fixture, case, state, binding = self.claim_observation(bind_prompt=False)
        receipt = read(fixture.project / binding["path"])
        self.assertNotIn("source_task_bindings", receipt)
        self.assertTrue(review_receipts.materials_match(receipt["materials"],
            review_receipts.material_snapshot(fixture.project, "writing-and-review", "P01")))
        responses = tasks.judgment_responses(fixture.project, "P01")
        self.assertNotIn("claim_evidence", responses[0]["response"])
        self.assertEqual(responses[0]["response"]["fatal_findings"], ["ORDINARY_OPINION_MUST_NOT_LEAK_TO_PANEL"])
        self.assertEqual(claim_evidence.build(fixture.project, fixture.spec)["claims"][0]["outcome"], "insufficient")
        self.assertTrue(any("unverified or insufficient" in error
            for error in tasks.integrity_errors(fixture.project, "P01", require_support=True)))
        state["writing_phases"]["P01"] = "submission"
        write(fixture.project / "state/run.json", state)
        with self.assertRaisesRegex(ValueError, "no unchanged task binding"):
            tasks.judgment_responses(fixture.project, "P01")
        self.assertNotIn("source_task_bindings", read(fixture.project / binding["path"]))

    def test_blind_tasks_hide_answer_key_everywhere_and_do_not_add_model_invocations(self):
        spec = self.anchors(public=True)
        write(self.project / "program/benchmark-task.json", spec)
        write(self.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "judgment_benchmark",
            "request_file": "program/benchmark-task.json", "stages": ["topic-intelligence"], "panel_views": ["domain"]}]})
        context = tasks.selected_context(self.project, "topic-intelligence")
        self.assertIn("program/anchor-labels.json", context["hidden_paths"])
        self.assertIn("literature/anchors/review-0.txt", context["hidden_paths"])
        self.assertNotIn("EXPECTED_LABEL_ONLY", json.dumps(context["tasks"]))
        self.assertEqual(tasks.selected_context(self.project, "topic-intelligence", seat="statistics")["tasks"], [])
        self.assertEqual(len(tasks.selected_context(self.project, "topic-intelligence", seat="domain")["tasks"]), 1)

    def test_actual_panel_does_not_claim_it_reviewed_an_unseen_notebook_decision(self):
        from tests.test_review_panel import ReviewPanelTests
        from tests.research_cycle_fixtures import pending_decision
        case = ReviewPanelTests(); case.setUp(); self.addCleanup(case.doCleanups)
        pending_decision(case.project, "writing-and-review", "first", "P01")
        case.run_panel("first")
        result = notebook.cycle_assessment(case.project, "writing-and-review", "first", paper_id="P01")
        self.assertEqual(result["status"], "recorded_with_limited_panel_observations")
        self.assertIsNone(result["independent_review"])
        self.assertFalse(result["scientific_completion_verified"])
        self.assertFalse(result["current_stage_authorized"])
        self.assertIn("not_notebook_decision_validation", result["assessment_scope"])

    def citation_job(self):
        from tests.test_review_panel import ReviewPanelTests
        case = ReviewPanelTests(); case.setUp(); self.addCleanup(case.doCleanups)
        case.stack.enter_context(patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production", "DR_OS_REQUIRE_REMOTE_RESERVATION": "1"}))
        target = case.project / "papers/P01/manuscript/references.bib"
        target.write_text("@article{work,doi={10.1000/source},title={Actual source title},year={2024},author={Example}}", encoding="utf-8")
        source = {"path": target.relative_to(case.project).as_posix(), "sha256": sha(target), "locator": "complete bibliography"}
        spec = {"schema_version": "1.0", "id": "bibliography", "paper_id": "P01", "source": source}
        write(case.project / "program/citation-task.json", spec)
        write(case.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "citation_crosscheck",
            "request_file": "program/citation-task.json", "paper_id": "P01", "stages": ["writing-and-review"],
            "panel_views": ["domain", "statistics"]}]})
        profile = {"task_class": "citation-crosscheck", "science_risk": "critical", "priority": "quality"}
        return case, source, spec, profile

    def citation_response(self, source, project, **kwargs):
        from scripts import ai_providers, model_runtime
        self.assertIn("Actual source title", kwargs["prompt"])
        self.assertNotIn("invented-comparator", kwargs["prompt"])
        self.assertNotIn("EXTRACTOR_ONE_ONLY_MARKER", kwargs["prompt"])
        self.assertFalse(kwargs["use_cache"])
        self.assertEqual(kwargs["task_profile"]["science_risk"], "critical")
        inflight = [read(path) for path in (project / "evidence/auxiliary").glob("*.json")]
        self.assertTrue(any(report["status"] == "in_progress" and any(
            attempt["run_id"] == kwargs["run_id"] and attempt["source"] == source
            and attempt["prompt_sha256"] == hashlib.sha256(kwargs["prompt"].encode()).hexdigest()
            for attempt in report["attempts"]) for report in inflight))
        first = kwargs["role"] == "scientific-judgment"
        value = {"citation_extraction": {"source": source, "records": [{"citation_key": "work",
            "doi": "10.1000/source" if first else "10.1000/invented-comparator",
            "title": "Actual source title", "year": 2024,
            "authors": ["EXTRACTOR_ONE_ONLY_MARKER"] if first else ["Example"]}]}}
        request_id = "synthetic-" + kwargs["role"]
        model_runtime._append(model_runtime._ledger(project), {"fixture": True, "run_id": kwargs["run_id"],
            "stage": "auxiliary", "role": kwargs["role"], "provider": kwargs["provider"],
            "requested_model": kwargs["model"], "model": kwargs["model"], "request_id": request_id,
            "prompt_sha256": hashlib.sha256(kwargs["prompt"].encode()).hexdigest(), "cache_hit": False,
            "cache_policy": "fresh_required_or_explicit", "completion_status": "completed",
            "task_profile": kwargs["task_profile"], "cost_cny": 0, "cost_status": "synthetic_unit_fixture_not_actual_charge"})
        return ai_providers.ModelResult(kwargs["provider"], kwargs["model"], json.dumps(value), {"input_tokens": 2},
            request_id=request_id, reported_model=kwargs["model"], completion_status="completed", cache_hit=False)

    def test_explicit_auxiliary_roles_extract_blindly_and_real_difference_reaches_integrity_check(self):
        from scripts import citation_audit, model_runtime
        case, source, spec, profile = self.citation_job()
        destination = case.project / "evidence/auxiliary/dual-extraction.json"
        with patch.object(model_runtime, "call", side_effect=lambda p, **k: self.citation_response(source, p, **k)) as calls:
            execution = tasks.run_citation_crosscheck(case.project, destination, "a" * 64,
                request_file="program/citation-task.json", task_profile=profile, execute=True)
        self.assertEqual(calls.call_count, 2)  # Explicit source job only; ordinary cycles and final panel do not call it.
        self.assertEqual([call.kwargs["role"] for call in calls.call_args_list], list(tasks.CITATION_ROLES))
        self.assertEqual(calls.call_args_list[0].kwargs["prompt"], calls.call_args_list[1].kwargs["prompt"])
        self.assertEqual(execution["calls_attempted"], 2)
        self.assertEqual(execution["status"], "complete")
        report = citation_audit.crosscheck(case.project, spec)
        self.assertEqual(report["status"], "differences_need_source_review")
        self.assertEqual(report["differences"][0]["field"], "doi")
        self.assertTrue(any("bibliographic differences" in error for error in tasks.integrity_errors(case.project, "P01")))
        self.assertFalse(report["semantic_support_verified"])
        self.assertTrue(report["runtime_extractions_verified"])
        self.assertEqual(len(tasks.citation_extractions(case.project, spec)), 2)
        for row in tasks.citation_extractions(case.project, spec):
            self.assertEqual(row["receipt"]["usage_receipt"]["cost_cny"], 0)
            self.assertEqual(provenance.current_origin(case.project, case.project / row["binding"]["path"])["model"], tasks.CITATION_MODULE)
        # A genuine later ledger change cannot borrow the protected extraction.
        ledger = model_runtime._ledger(case.project)
        values = [json.loads(line) for line in ledger.read_text().splitlines()]
        values[0]["cache_hit"] = True
        ledger.write_text("".join(json.dumps(row) + "\n" for row in values))
        with self.assertRaisesRegex(ValueError, "runtime billing receipt"):
            citation_audit.crosscheck(case.project, spec)

    def test_selected_crosscheck_requires_both_extractors_to_cover_the_source_population(self):
        from scripts import citation_audit, model_runtime
        case, source, spec, profile = self.citation_job()
        bibliography = case.project / source["path"]
        bibliography.write_text(bibliography.read_text() + '\n@article{omitted,doi={10.1000/second},title={Second source},year={2023},author={Another}}')
        source["sha256"] = sha(bibliography)
        write(case.project / "program/citation-task.json", spec)
        report = citation_audit.crosscheck(case.project, spec)
        self.assertEqual(report["source_population"]["citation_keys"], ["omitted", "work"])
        self.assertEqual(report["status"], "awaiting_two_independent_extractions")
        self.assertEqual(tasks.integrity_errors(case.project, "P01"), [])
        self.assertTrue(any("awaiting_two_independent_extractions" in error
            for error in tasks.integrity_errors(case.project, "P01", require_support=True)))
        for mode in ("both_omit", "unexpected_key", "both_unknown", "complete"):
            def response(project, **kwargs):
                result = self.citation_response(source, project, **kwargs)
                value = json.loads(result.text)
                row = value["citation_extraction"]["records"][0]
                row.update(doi="10.1000/source", authors=["Example"])
                if mode != "both_omit":
                    value["citation_extraction"]["records"].append({"citation_key": "omitted", "doi": "10.1000/second",
                        "title": "Second source", "year": 2023, "authors": ["Another"]})
                if mode == "unexpected_key":
                    value["citation_extraction"]["records"].append({**row, "citation_key": "invented"})
                if mode == "both_unknown":
                    row.update(doi=None, title=None, year=None, authors=None)
                result.text = json.dumps(value)
                return result
            with self.subTest(mode=mode), patch.object(model_runtime, "call", side_effect=response) as calls:
                tasks.run_citation_crosscheck(case.project, case.project / ("evidence/auxiliary/" + mode + ".json"), "a" * 64,
                    request_file="program/citation-task.json", task_profile=profile, execute=True)
                self.assertEqual(calls.call_count, 2)
            report = citation_audit.crosscheck(case.project, spec)
            self.assertTrue(report["runtime_extractions_verified"])
            errors = tasks.integrity_errors(case.project, "P01", require_support=True)
            self.assertEqual(report["status"], "fields_agree" if mode == "complete" else "incomplete_extraction")
            self.assertEqual(errors == [], mode == "complete", errors)
            if mode == "both_omit":
                self.assertTrue(all(row["missing_citation_keys"] == ["omitted"] for row in report["coverage"]["extractions"]))
            if mode == "unexpected_key":
                self.assertTrue(all(row["unexpected_citation_keys"] == ["invented"] for row in report["coverage"]["extractions"]))
            if mode == "both_unknown": self.assertEqual(len(report["unknown_fields"]), 4)
            self.assertEqual(tasks.integrity_errors(case.project, "P01"), [])

    def test_unknown_source_population_never_becomes_complete_because_extractors_agree(self):
        from scripts import citation_audit
        case, source, spec, profile = self.citation_job()
        for text in ('@article{work,title={Unclosed}', '@article{work,title={One}} @article(work,title={Unsupported})',
                     '@article{work,title={One}} @article{work,title={Duplicate}}'):
            target = case.project / source["path"]
            target.write_text(text); source["sha256"] = sha(target)
            write(case.project / "program/citation-task.json", spec)
            extractions = []
            for name in ("one", "two"):
                path = case.project / ("evidence/extractions/" + name + ".json")
                write(path, {"source": source, "extractor": name, "records": [{"citation_key": "work",
                    "doi": "10.1000/source", "title": "One", "year": 2024, "authors": ["Example"]}]})
                provenance.record_model_writes(case.project, [path], family="other", provider="fixture",
                    model="independent-" + name, role="independent-extractor", run_id="synthetic-only")
                extractions.append({"path": path.relative_to(case.project).as_posix(), "sha256": sha(path), "locator": "synthetic extraction"})
            manual = {**spec, "extractions": extractions}
            write(case.project / "program/citation-task.json", manual)
            report = citation_audit.crosscheck(case.project, manual)
            self.assertEqual(report["status"], "coverage_unknown")
            self.assertIsNone(report["source_population"]["citation_keys"])
            self.assertFalse(report["runtime_extractions_verified"])
            self.assertEqual(tasks.integrity_errors(case.project, "P01"), [])
            self.assertTrue(any("coverage_unknown" in error for error in tasks.integrity_errors(case.project, "P01", require_support=True)))

    def test_citation_job_dry_run_and_failure_preserve_attempts_without_retry(self):
        from scripts import model_runtime
        case, source, spec, profile = self.citation_job()
        with patch.object(model_runtime, "call") as calls:
            result = tasks.run_citation_crosscheck(case.project, case.project / "evidence/auxiliary/preview.json", "a" * 64,
                request_file="program/citation-task.json", task_profile=profile)
        calls.assert_not_called(); self.assertEqual(result["calls_attempted"], 0)
        def failing(project, **kwargs):
            result = self.citation_response(source, project, **kwargs)
            if kwargs["role"] == "independent-critique": result.reported_model = "mismatched-model"
            return result
        destination = case.project / "evidence/auxiliary/failed.json"
        with patch.object(model_runtime, "call", side_effect=failing) as calls:
            with self.assertRaisesRegex(ValueError, "identity changed"):
                tasks.run_citation_crosscheck(case.project, destination, "a" * 64,
                    request_file="program/citation-task.json", task_profile=profile, execute=True)
        self.assertEqual(calls.call_count, 2)
        saved = read(destination)
        self.assertEqual(saved["status"], "partial_failed_no_retry")
        self.assertEqual(len(saved["attempts"]), 2)
        self.assertTrue(all(attempt["raw_response"] and attempt["usage_receipts"] for attempt in saved["attempts"]))
        self.assertEqual(len(saved["extractions"]), 1)
        with self.assertRaisesRegex(ValueError, "latest pointer is missing"):
            tasks.citation_extractions(case.project, spec)
        with patch.object(model_runtime, "call") as calls:
            with self.assertRaisesRegex(ValueError, "new auxiliary diagnostic"):
                tasks.run_citation_crosscheck(case.project, destination, "a" * 64,
                    request_file="program/citation-task.json", task_profile=profile, execute=True)
        calls.assert_not_called()

    def test_changed_source_stops_before_a_second_citation_call_and_writer_cannot_be_extractor(self):
        from scripts import model_runtime, citation_audit
        case, source, spec, profile = self.citation_job()
        def mutate(project, **kwargs):
            result = self.citation_response(source, project, **kwargs)
            (project / source["path"]).write_text("Changed after a real response.")
            return result
        destination = case.project / "evidence/auxiliary/source-changed.json"
        with patch.object(model_runtime, "call", side_effect=mutate) as calls:
            with self.assertRaisesRegex(ValueError, "output changed"):
                tasks.run_citation_crosscheck(case.project, destination, "a" * 64,
                    request_file="program/citation-task.json", task_profile=profile, execute=True)
        self.assertEqual(calls.call_count, 1)
        self.assertTrue(read(destination)["attempts"][0]["raw_response"])
        for name in ("one", "two"):
            target = self.project / f"evidence/extractions/{name}.json"
            write(target, {"source": source, "extractor": "independent " + name, "records": []})
            provenance.record_model_writes(self.project, [target], family="openai", provider="fixture", model="writer", role="writer", run_id="fixture")
        # The source itself must still be valid before the writer-origin test.
        source = self.text("papers/P01/manuscript/references.bib", "@article{x,title={Original}}")
        with self.assertRaisesRegex(ValueError, "writer cannot"):
            citation_audit.crosscheck(self.project, {"schema_version": "1.0", "id": "forged", "source": source,
                "extractions": [{"path": f"evidence/extractions/{name}.json", "sha256": sha(self.project / f"evidence/extractions/{name}.json"),
                                 "locator": "synthetic writer attempt"} for name in ("one", "two")]})

    def test_citation_task_cannot_deliver_prior_judgments_private_or_unregistered_sources(self):
        from scripts import citation_audit
        for relative in ("reviews/independent/prior.json", "papers/P01/manuscript/private/values.txt",
                         "papers/P01/manuscript/apikey.txt", "evidence/innocent.txt",
                         "papers/P01/manuscript/renamed-judgment.txt", "program/old-result.json"):
            binding = self.text(relative, "PRIOR_JUDGMENT_OR_PRIVATE_MARKER")
            spec = {"schema_version": "1.0", "id": "blocked", "paper_id": "P01", "source": binding}
            write(self.project / "program/citation-request.json", spec)
            write(self.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "citation_crosscheck",
                "request_file": "program/citation-request.json", "paper_id": "P01", "stages": ["writing-and-review"],
                "panel_views": ["domain"]}]})
            with self.subTest(relative=relative), patch("scripts.model_runtime.call") as call:
                with self.assertRaises(ValueError):
                    tasks.selected_context(self.project, "writing-and-review", "P01", seat="domain")
                with self.assertRaises(ValueError):
                    citation_audit.crosscheck(self.project, spec)
                call.assert_not_called()

    def test_citation_panel_rejects_other_paper_even_without_declared_owner(self):
        binding = self.text("papers/P02/manuscript/references.bib", "@article{x,title={Other paper bibliography}}")
        write(self.project / "program/citation-request.json", {"schema_version": "1.0", "id": "other", "source": binding})
        write(self.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "citation_crosscheck",
            "request_file": "program/citation-request.json", "stages": ["writing-and-review"], "panel_views": ["domain"]}]})
        with self.assertRaisesRegex(ValueError, "current panel paper"):
            tasks.selected_context(self.project, "writing-and-review", "P01", seat="domain")

    def test_hidden_source_and_renamed_review_cannot_impersonate_canonical_bibliography(self):
        source = self.text("papers/P01/manuscript/references.bib", "@article{x,title={Canonical bibliography}}")
        spec = {"schema_version": "1.0", "id": "current", "paper_id": "P01", "source": source}
        self.assertEqual(tasks.citation_source(self.project, spec), source)
        # An answer key selected by another task stays hidden even when it uses
        # an otherwise valid canonical scientific filename.
        write(self.project / "program/label-task.json", {"sample_labels": source["path"]})
        write(self.project / tasks.CONTROL, {"scientific_judgments": [{"operation": "claim_evidence",
            "request_file": "program/label-task.json", "stages": ["writing-and-review"], "panel_views": []}]})
        with self.assertRaisesRegex(ValueError, "hidden judgment"):
            tasks.citation_source(self.project, spec)
        write(self.project / tasks.CONTROL, {})
        prior = self.project / "reviews/independent/prior.json"
        write(prior, {"preferred_verdict": "RENAMED_PRIOR_MARKER"})
        provenance.record_model_writes(self.project, [prior], family="anthropic", provider="fixture",
            model="critic", role="independent-critic", run_id="prior")
        canonical = self.project / source["path"]
        canonical.write_bytes(prior.read_bytes()); spec["source"]["sha256"] = sha(canonical)
        with self.assertRaisesRegex(ValueError, "renamed copy"):
            tasks.citation_source(self.project, spec)

    def test_registered_native_original_reader_remains_available_to_citation_extraction(self):
        from tests.test_claim_evidence import ClaimEvidenceTests
        fixture = ClaimEvidenceTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        source = {"path": fixture.reader.relative_to(fixture.project).as_posix(), "sha256": sha(fixture.reader),
                  "locator": "original extracted PDF source"}
        spec = {"schema_version": "1.0", "id": "original", "paper_id": "P01", "source": source}
        write(fixture.project / "program/citation-original.json", spec)
        packet = tasks.prepare_panel_task(fixture.project, "citation_crosscheck", "program/citation-original.json", paper_id="P01")
        self.assertIn("The original PDF reports a controlled method.", packet["packet"]["source_text"])
        self.assertIn("literature/metadata/W1.json", {row["path"] for row in packet["sources"]})
