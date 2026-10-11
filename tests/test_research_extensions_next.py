"""Synthetic boundary tests; no study results or paid providers."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import research_extensions as extensions, evidence_context, calibration_analysis
from scripts import review_packets, output_provenance, artifact_ownership, api_orchestrator, word_render
from scripts.research_artifacts import read, sha, write


class ExtensionFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)

    def source(self, relative, content):
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": relative, "sha256": sha(target), "locator": "synthetic source", "quote": content}


class ExtensionTests(ExtensionFixture):
    def comparison(self):
        condition = {key: "matched synthetic condition" for key in extensions.DIMENSIONS}
        return {"id": "comparison", "question": "What explains the disagreement?", "disposition": "comparable",
                "left": {"conditions": condition.copy(), "evidence": [self.source("evidence/left.txt", "Observed left effect.")]},
                "right": {"conditions": condition.copy(), "evidence": [self.source("evidence/right.txt", "Observed right effect.")]},
                "discriminating_test": {"hypothesis": "Two competing synthetic explanations", "design": "Frozen contrast",
                    "observable": "Held-out metric", "failure_condition": "Both predictions contradicted", "stop_rule": "Frozen sample size",
                    "predictions": [{"explanation": "A", "expected_observation": "Positive effect"},
                                    {"explanation": "B", "expected_observation": "No effect"}]}}

    def test_comparison_records_but_does_not_resolve_conflict(self):
        row = extensions.comparison(self.project, self.comparison())
        self.assertFalse(row["comparability_verified"])
        self.assertFalse(row["experiment_executed"])
        self.assertFalse(row["conflict_resolution_verified"])

    def test_changed_conditions_need_explanation(self):
        row = self.comparison()
        row["right"]["conditions"]["split"] = "Different testing set"
        with self.assertRaisesRegex(ValueError, "explanation"):
            extensions.comparison(self.project, row)
        row["difference_explanations"] = {"split": "The datasets differ; compare only within the same split."}
        row["disposition"] = "not_comparable"
        self.assertEqual(extensions.comparison(self.project, row)["different_conditions"], ["split"])

    def test_unknown_conditions_cannot_be_declared_comparable(self):
        row = self.comparison()
        row["left"]["conditions"]["leakage"] = "unknown"
        with self.assertRaisesRegex(ValueError, "unknown"):
            extensions.comparison(self.project, row)

    def test_predictions_must_discriminate_and_source_must_be_current(self):
        row = self.comparison()
        row["discriminating_test"]["predictions"][1]["expected_observation"] = "Positive effect"
        with self.assertRaisesRegex(ValueError, "identical"):
            extensions.comparison(self.project, row)
        row = self.comparison()
        (self.project / "evidence/left.txt").write_text("Changed evidence.")
        with self.assertRaisesRegex(ValueError, "hash"):
            extensions.comparison(self.project, row)

    def test_missing_real_methods_remain_missing(self):
        self.assertEqual(extensions.refresh(self.project)["status"], "needs_inputs")
        write(self.project / "papers/P01/paper-contract.json", {"research_question": ""})
        with self.assertRaisesRegex(ValueError, "actual paper"):
            extensions.method(self.project, {"paper_id": "P01"})

    def test_method_adoption_binds_actual_baseline_and_run_membership(self):
        write(self.project / "papers/P01/paper-contract.json", {"research_question": "Synthetic question only"})
        write(self.project / "papers/P01/experiments/design.json", {"baselines": [{"id": "strong", "class": "strong_recent"}], "run_ids": ["pilot"]})
        row = {"id": "adoption", "paper_id": "P01", "baseline_class": "strong-recent", "baseline_id": "strong",
               "fair_comparison": "Same held-out data", "resource_rationale": "Bounded CPU fixture",
               "transfer_limitations": "No scientific applicability claimed", "method_tool_id": "method",
               "design_path": "papers/P01/experiments/design.json", "evidence": [self.source("evidence/method.txt", "Synthetic method statement.")]}
        contract = {"errors": [], "tools": [{"id": "method", "run_ids": ["pilot"],
                    "qualification": {"status": "pending_cloud_validation"}}]}
        with patch("scripts.method_tools.inspect", return_value=contract):
            result = extensions.method(self.project, row)
            self.assertFalse(result["scientific_applicability_verified"])
            row["baseline_class"] = "simple"
            with self.assertRaisesRegex(ValueError, "class differs"):
                extensions.method(self.project, row)
            row["baseline_class"] = "strong-recent"
            row["baseline_id"] = "nonexistent"
            with self.assertRaisesRegex(ValueError, "baseline"):
                extensions.method(self.project, row)

    def test_reading_anchor_checks_real_pdf_page_and_quote(self):
        import fitz
        from scripts.paper_reader import build
        pdf = self.project / "evidence/paper.pdf"
        pdf.parent.mkdir(parents=True)
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((72,72), "Figure 1. Synthetic evidence for reader verification.")
            doc.save(pdf)
        output = self.project / "literature/readers/paper.md"
        build(self.project, pdf, output)
        receipt = output.with_suffix(".reader.json")
        row = {"id": "figure", "kind": "figure", "page": 1, "label": "Figure 1",
               "quote": "Synthetic evidence", "interpretation": "Reading illustration only", "inference_boundary": "No scientific claim",
               "pdf": {"path": "evidence/paper.pdf", "sha256": sha(pdf), "locator": "page 1"},
               "reader_receipt": {"path": receipt.relative_to(self.project).as_posix(), "sha256": sha(receipt), "locator": "reader"}}
        self.assertEqual(extensions.reading_anchor(self.project, row)["semantic_verification"], "needs_human_review")
        row["quote"] = "Unobserved claim"
        with self.assertRaisesRegex(ValueError, "absent"):
            extensions.reading_anchor(self.project, row)

    def test_critic_worklist_cannot_self_certify_resolution(self):
        row = {"id": "review", "perspective": "statistics", "severity": "major", "status": "verified_resolved",
               "question": "Is n independent?", "required_action": "Verify actual unit IDs",
               "evidence": [self.source("evidence/review.txt", "Synthetic design concern.")],
               "response_evidence": [self.source("evidence/response.txt", "Synthetic response awaiting review.")]}
        with self.assertRaisesRegex(ValueError, "existing independent audit"):
            extensions.review(self.project, row)

    def context(self):
        write(self.project / "state/run.json", {"stage": "topic-intelligence", "approved_gates": ["G0"]})
        write(self.project / "intake/constraints.json", {"execution_mode": "cloud_only"})
        source = self.source("evidence/text.md", "First line.\nCounterevidence remains.\n")
        value = {"schema_version": "1.0", "stages": {"topic-intelligence": {"question": "Synthetic task",
                 "items": [{"path": source["path"], "reason": "actual evidence", "stance": "contradicts"}]}}}
        write(self.project / evidence_context.PLAN, value)
        return value, source

    def test_context_preserves_constraints_and_full_hashes(self):
        _, source = self.context()
        result = evidence_context.build(self.project, "topic-intelligence")
        self.assertIn("cloud_only", result["context"])
        self.assertIn(source["sha256"], result["context"])
        original = result["fingerprint"]
        (self.project / source["path"]).write_text("New counterevidence")
        self.assertNotEqual(original, evidence_context.build(self.project, "topic-intelligence")["fingerprint"])

    def test_context_refuses_silent_truncation_stale_sources_and_private_files(self):
        value, source = self.context()
        with self.assertRaisesRegex(ValueError, "budget"):
            evidence_context.build(self.project, "topic-intelligence", max_bytes=10)
        item = value["stages"]["topic-intelligence"]["items"][0]
        item["expected_sha256"] = "0" * 64
        write(self.project / evidence_context.PLAN, value)
        with self.assertRaisesRegex(ValueError, "changed"):
            evidence_context.build(self.project, "topic-intelligence")
        item.pop("expected_sha256")
        item["path"] = "state/api_runs/secret.json"
        write(self.project / evidence_context.PLAN, value)
        with self.assertRaisesRegex(ValueError, "private"):
            evidence_context.build(self.project, "topic-intelligence")

    def test_counterevidence_cannot_be_hidden_in_a_partial_snippet(self):
        value, source = self.context()
        write(self.project / "program/research-notebook.json", {"questions": [{"evidence": [
            {"id": "contra", "stance": "contradicts", "source": source}]}]})
        value["stages"]["topic-intelligence"]["items"][0].update(start_line=1, end_line=1)
        write(self.project / evidence_context.PLAN, value)
        with self.assertRaisesRegex(ValueError, "counterevidence"):
            evidence_context.build(self.project, "topic-intelligence")

    def test_extension_reports_cannot_be_written_by_the_model(self):
        for path in ("reports/research-extensions/audit.json", "reports/word-render/x/receipt.json",
                     "reports/review-packets/blind/analysis.json", "papers/P01/reviews/cloud-word-build.json"):
            self.assertTrue(artifact_ownership.executor_owned(self.project, path))
            with patch.object(api_orchestrator, "project_root", return_value=self.project):
                with self.assertRaises(ValueError):
                    api_orchestrator.safe_target("sample", path)

    def test_word_render_refuses_local_execution(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "cloud"):
                word_render.render(self.project, "P01")


class CalibrationTests(ExtensionFixture):
    def fixture(self):
        rubric = {"dimensions": [{"id": "fidelity", "description": "Meaning preserved", "value_type": "integer", "min": 0, "max": 4}],
                  "critical_errors": [{"id": "false-fact", "criterion": "Invented factual claim"}]}
        cases = []
        for number in (1, 2):
            source = self.source(f"evidence/source{number}.txt", f"Synthetic source number {number}.")
            candidate = self.source(f"api_runs/text{number}.txt", f"Synthetic revised sentence {number}.")
            failure = self.source(f"api_runs/failure{number}.txt", "Synthetic failed attempt.")
            shared = {"author_id": "author", "authorized_for_internal_review": True, "authorization_note": "synthetic internal fixture"}
            cases.append({"id": f"case-{number}", "sources": [source], "candidates": [
                {"id": "edited", "artifact": candidate, "status": "success", "run_ids": [f"run-{number}"], **shared},
                {"id": "failure", "status": "failed", "failure_receipt": failure, "failure_reason": "synthetic", "run_ids": [f"run-{number}"], **shared}]})
        packet = {"id": "blind", "kind": "calibration", "rubric": rubric, "cases": cases,
                  "analysis": {"minimum_raters": 2, "qualification_thresholds": {"fidelity": 3},
                               "case_partitions": {"case-1": "calibration", "case-2": "holdout"}, "cost_run_ids": ["run-1", "run-2"]}}
        write(self.project / review_packets.INPUT, {"schema_version": "1.0", "packets": [packet]})
        self.assertEqual(review_packets.refresh(self.project)["status"], "pass")
        return packet

    def rate(self, rater, critical=False, scope=None):
        snapshot = review_packets.review_snapshot(self.project, "blind")
        observations = []
        for row in snapshot["roster"]:
            item = {"case_label": row["case_label"], "candidate_label": row["candidate_label"], "rationale": "Synthetic judgment"}
            if row["status"] == "failed":
                item["status"] = "unscorable_failed"
            else:
                item.update(ratings={"fidelity": 4}, critical_errors={"false-fact": critical})
            observations.append(item)
        value = {"rater_id": rater, "independent": True, "independence_note": "Synthetic independent rater", "observations": observations}
        if scope:
            value["cost_scope_confirmation"] = scope
        target, receipt = review_packets.create_confirmation(self.project, "blind", rater, value)
        write(target, receipt)

    def test_partial_ratings_are_not_disclosed_and_failures_stay_in_denominator(self):
        self.fixture()
        self.rate("rater-one")
        report = calibration_analysis.summarize(self.project, "blind")
        self.assertEqual(report["status"], "awaiting_ratings")
        self.assertEqual(report["candidate_results"], [])
        self.rate("rater-two")
        report = calibration_analysis.refresh(self.project, "blind")
        self.assertEqual(report["qualification_rate"], .5)
        self.assertEqual(report["failed_attempts"], 2)
        self.assertEqual(report["calibration_status"], "NOT_CALIBRATED")
        self.assertIsNone(report["costs"]["total_cash_cost_per_qualified_candidate_cny"])

    def test_critical_error_is_never_averaged_away(self):
        self.fixture()
        self.rate("rater-one", critical=True)
        self.rate("rater-two")
        report = calibration_analysis.summarize(self.project, "blind")
        self.assertEqual(report["qualified_candidates"], 0)
        self.assertEqual(report["exact_pairwise_rating_agreement"], 0)

    def test_duplicate_rater_with_whitespace_cannot_count_twice(self):
        self.fixture()
        self.rate("reviewer-one")
        self.rate("  REVIEWER-ONE  ")
        with self.assertRaisesRegex(ValueError, "multiple owner"):
            calibration_analysis.summarize(self.project, "blind")

    def test_default_snapshot_excludes_blind_answer_key(self):
        self.fixture()
        self.rate("reviewer-one")
        answer_path = self.project / "reports/review-packets/blind/answer-key.json"
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        registry = self.project / "state/output-provenance.json"
        original_registry_hash = sha(registry)
        with patch.object(api_orchestrator, "project_root", return_value=self.project):
            content = api_orchestrator.project_snapshot("synthetic", stage="topic-intelligence", exclude_reviews=True)
        # Keep the complete audit registry on disk, outside model-facing contexts.
        self.assertNotIn("--- FILE reports/review-packets/", content)
        self.assertNotIn("--- FILE state/output-provenance.json", content)
        self.assertNotIn(answer["seed"], content)
        for row in answer["answer_key"]:
            self.assertNotIn(row["candidate_label"], content)
        self.assertEqual(sha(registry), original_registry_hash)
        with self.assertRaisesRegex(ValueError, "private"):
            evidence_context.safe_text(self.project, "state/output-provenance.json", lambda text: text)

    def test_source_leakage_and_post_rating_rubric_change_are_rejected(self):
        packet = self.fixture()
        altered = copy.deepcopy(packet)
        altered["cases"][1]["sources"] = altered["cases"][0]["sources"]
        with self.assertRaisesRegex(ValueError, "leak"):
            calibration_analysis.protocol(altered)
        self.rate("one")
        self.rate("two")
        packet["analysis"]["qualification_thresholds"]["fidelity"] = 2
        write(self.project / review_packets.INPUT, {"schema_version": "1.0", "packets": [packet]})
        with self.assertRaises(ValueError):
            calibration_analysis.summarize(self.project, "blind")

    def test_costs_include_retries_and_need_explicit_scope_reconciliation(self):
        packet = self.fixture()
        self.rate("one")
        ledger = self.project / "state/model-usage.jsonl"
        ledger.write_text('\n'.join(json.dumps({**r, "cost_status": "settled_usage_receipt"}) for r in [
            {"run_id": "run-1", "cost_cny": 1.0}, {"run_id": "run-1", "cost_cny": .5},
            {"run_id": "run-2", "cost_cny": 2.5}]))
        scope = {"analysis_sha256": review_packets.digest(packet["analysis"]),
                 "ledger_sha256": sha(ledger),
                 "all_calls_retries_tools_compute_and_validation_included": True, "no_double_counting": True}
        self.rate("two", scope=scope)
        report = calibration_analysis.summarize(self.project, "blind")
        self.assertEqual(report["costs"]["recorded_calls"], 3)
        self.assertEqual(report["costs"]["total_cash_cost_per_qualified_candidate_cny"], 2)
        with ledger.open("a") as handle:
            handle.write('\n' + json.dumps({"run_id": "run-2", "cost_cny": 0, "cost_status": "unknown_reconcile_required"}))
        self.assertIsNone(calibration_analysis.summarize(self.project, "blind")["costs"]["total_recorded_cash_cost_cny"])
