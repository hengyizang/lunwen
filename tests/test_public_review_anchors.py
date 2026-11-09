"""Public corpus contracts; synthetic transport fixtures do not measure judgment."""
import copy
import json
import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import public_review_anchors as corpus, literature_benchmark as benchmark
from scripts import ai_providers, model_routing, model_runtime


class PublicReviewAnchorTests(unittest.TestCase):
    def test_complete_fenced_response_preserves_exact_labels_and_rejects_ambiguous_output(self):
        cases = [{"case_id": "paper", "case_sha256": "a" * 64}]
        row = {**cases[0], "outcome": "incomplete", "rationale": "The located comparison is incomplete."}
        text = json.dumps({"anchor_labels": [row]})
        for fenced in (text, "```json\n" + text + "\n```", "\n```\r\n" + text + "\r\n```\n"):
            self.assertEqual(corpus.calibration_predictions(fenced, cases), [row])
        for bad in ("Unverified judgment.\n" + text, "```json\n" + text,
                    "```json\n" + text + "\n```\n" + text,
                    '```json\n{"anchor_labels":[],"anchor_labels":[]}\n```'):
            with self.subTest(text=bad), self.assertRaises(ValueError):
                corpus.calibration_predictions(bad, cases)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.candidate = {"id": "12345", "version": 1, "assessment_doi": "10.7554/eLife.12345.1.sa0", "partition": "holdout"}
        self.rights = {"DOI": self.candidate["assessment_doi"], "type": "peer-review", "license": [{"URL": corpus.LICENSE}]}
        self.article = {"id": "12345", "version": 1, "doi": "10.7554/eLife.12345", "authorLine": "Synthetic fixture",
            "copyright": {"license": "CC-BY-4.0"}, "title": "Synthetic source fixture",
            "abstract": [{"text": "A synthetic bounded abstract."}], "body": [{"text": "Measured fictional source content. " * 220}],
            "elifeAssessment": {"doi": self.candidate["assessment_doi"], "strength": ["solid"], "content": [{"text": "Fixture public assessment ANSWER_KEY_TEXT."}]}}
        self.calls = []

    def fetch(self, url, path):
        self.calls.append(url)
        value = {"message": self.rights} if "crossref" in url else self.article
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return copy.deepcopy(value)

    def acquire(self, candidate=None):
        with patch.object(corpus, "_fetch", side_effect=self.fetch):
            return corpus._acquire(self.root / "project", candidate or self.candidate, self.root / "originals")

    def calibration_collection(self, cache, frozen):
        source_project = cache / "project"
        rows, self.calibration_cases = [], []
        for identifier, partition in (("a", "calibration"), ("b", "holdout")):
            source = source_project / f"evidence/{identifier}.json"
            corpus.write(source, {"body": [{"text": "Synthetic scientific source only."}]})
            review = source.with_suffix(".txt")
            review.write_text("Synthetic external assessment key.")
            binding = {"path": source.relative_to(source_project).as_posix(), "sha256": corpus.sha(source)}
            row = {"id": identifier, "partition": partition, "label": "solid", "source": binding,
                   "review": {"path": review.relative_to(source_project).as_posix()}}
            rows.append(row)
            self.calibration_cases.append({**row, "case_sha256": identifier * 64})
        corpus.write(source_project / "program/public-review-anchors.json", {"cases": rows})
        corpus.write(source_project / "program/judgment-benchmark.json", {})
        return {"public_papers": 2}

    def calibration_call(self, project, **request):
        route = model_routing.select("auxiliary", "independent-critique")
        self.assertEqual(request["max_output_tokens"], 12000)
        self.assertEqual(route["max_output_tokens"], 12000)
        ledger = project / "state/model-usage.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        row = {"run_id": request["run_id"], "requested_model": request["model"], "provider": request["provider"],
               "route_id": route["route_id"], "prompt_sha256": hashlib.sha256(request["prompt"].encode()).hexdigest(),
               "cost_cny": .4, "cost_status": "estimated_upper_bound"}
        with ledger.open("a") as stream:
            stream.write(json.dumps(row) + "\n")
        labels = [{**json.loads(line[5:]), "outcome": "solid", "rationale": "Synthetic transport fixture."}
                  for line in request["prompt"].splitlines() if line.startswith("CASE ")] if self.valid_calibration_response else []
        return ai_providers.ModelResult(provider=request["provider"], model=request["model"], reported_model=request["model"],
            text=json.dumps({"anchor_labels": labels}), usage={}, requested_effort="high", route_id=route["route_id"],
            routing_policy_sha256=route["policy_sha256"], response_metadata={"metadata_only": True,"diagnostics": {"stop_reason": "end_turn"}})

    def test_review_license_is_verified_before_acquiring_article_body(self):
        self.rights["license"] = []
        with self.assertRaisesRegex(ValueError, "license"):
            self.acquire()
        self.assertEqual(len(self.calls), 1)
        self.assertIn("api.crossref.org", self.calls[0])

    def test_original_answer_payloads_stay_outside_the_blind_project(self):
        self.article["body"].extend([{"type": "equation", "tex": "E=mc^2"},
            {"type": "table", "rows": [["comparison", "estimate"], ["adverse", "-0.4"]]}])
        case, receipt = self.acquire()
        primary = (self.root / "project" / case["source"]["path"]).read_text()
        self.assertNotIn("ANSWER_KEY_TEXT", primary)
        self.assertEqual(json.loads(primary)["body"], self.article["body"])
        self.assertEqual(receipt["label"], "solid")
        self.assertFalse(list((self.root / "project").rglob("article.json")))
        self.assertTrue((self.root / "originals/12345/article.json").is_file())
        changed = {**self.candidate, "primary_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "frozen public anchor changed"):
            self.acquire(changed)

    def test_public_assessment_categories_are_not_relabelled_as_claim_support(self):
        for label in ("solid", "incomplete+solid"):
            self.assertTrue(benchmark._anchor_label(label, "elife_evidence_strength"))
        for label in ("supports", "solid+incomplete", "solid+solid", ""):
            self.assertFalse(benchmark._anchor_label(label, "elife_evidence_strength"))
        self.assertFalse(benchmark._anchor_label("solid", "claim_support_and_novelty"))

    def test_rate_limited_public_request_preserves_its_failed_attempt(self):
        url = "https://api.crossref.org/works/10.7554/eLife.12345.1.sa0"
        target = self.root / "originals/crossref.json"
        responses = [HTTPError(url, 429, "Too Many Requests", {"Retry-After": "7"}, None),
                     (b'{"source":"synthetic transport fixture"}', url, 200, "application/json"),
                     (b'{"source":"synthetic transport fixture"}', url, 200, "application/json")]
        with patch.object(corpus, "fetch_bytes", side_effect=responses), patch("scripts.literature_evidence.time.sleep") as sleep:
            self.assertEqual(corpus._fetch(url, target), {"source": "synthetic transport fixture"})
            self.assertEqual(corpus._fetch(url, target), {"source": "synthetic transport fixture"})
        attempts = json.loads(target.with_name("crossref-attempts.json").read_text())["attempts"]
        self.assertEqual([row["status"] for row in attempts], [429, 200, 200])
        self.assertEqual(attempts[0]["retry_after"], "7")
        self.assertIn(7, [call.args[0] for call in sleep.call_args_list])

    def test_elife_transport_negotiates_the_publishers_vendor_json(self):
        url = "https://api.elifesciences.org/articles/12345/versions/1"
        def transport(request_url, **kwargs):
            self.assertEqual(kwargs["headers"]["Accept"], "*/*")
            return b'{"source":"vendor JSON fixture"}', request_url, 200, "application/vnd.elife.article+json; version=8"
        with patch.object(corpus, "fetch_bytes", side_effect=transport):
            self.assertEqual(corpus._fetch(url, self.root / "article.json"), {"source": "vendor JSON fixture"})

    def test_scientific_json_keeps_original_number_lexemes_and_excludes_review_keys(self):
        raw = '{"body":{"estimate":1.0000000000000000001,"quote":"x,{}"},"elifeAssessment":{"answer":"hidden"}}'
        result = corpus.primary_json(raw)
        self.assertIn('1.0000000000000000001', result)
        self.assertNotIn('hidden', result)
        self.assertIn('"quote":"x,{}"', result)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            corpus.primary_json('{"body":[],"body":[]}')

    def test_calibration_blinds_answers_and_keeps_full_primary_and_official_definitions(self):
        case, _ = self.acquire()
        case["case_sha256"] = "a" * 64
        batch = corpus.calibration_batches(self.root / "project", [case])[0]
        self.assertNotIn("ANSWER_KEY_TEXT", batch["prompt"])
        self.assertNotIn('"partition"', batch["prompt"])
        self.assertNotIn('"label"', batch["prompt"])
        self.assertIn((self.root / "project" / case["source"]["path"]).read_text(), batch["prompt"])
        self.assertIn(corpus.EVIDENCE_RUBRIC["convincing"], batch["prompt"])
        self.assertEqual(batch["cases"], [{"case_id": case["id"], "case_sha256": "a" * 64}])

    def test_small_batches_keep_complete_sources_and_the_same_case_population(self):
        case, _ = self.acquire()
        case["case_sha256"] = "a" * 64
        second = copy.deepcopy(case)
        second.update(id="second-case", case_sha256="b" * 64)
        ordinary = corpus.calibration_batches(self.root / "project", [case, second])
        small = corpus.calibration_batches(self.root / "project", [case, second], max_cases=1)
        self.assertEqual(len(ordinary), 1)
        self.assertEqual(len(small), 2)
        self.assertEqual([c for batch in ordinary for c in batch["cases"]], [c for batch in small for c in batch["cases"]])
        for batch in small:
            self.assertIn((self.root / "project" / case["source"]["path"]).read_text(), batch["prompt"])
            self.assertNotIn("ANSWER_KEY_TEXT", batch["prompt"])
            self.assertEqual(len(batch["cases"]), 1)
        for maximum in (0, 9, True, 1.0, "1", None):
            with self.subTest(maximum=maximum), self.assertRaisesRegex(ValueError, "batch cases"):
                corpus.calibration_batches(self.root / "project", [case], max_cases=maximum)

    def test_selected_batch_keeps_its_canonical_index_identity_and_quote(self):
        batches = [{"prompt": "First full source fixture", "cases": [{"case_id": "a", "case_sha256": "a" * 64}]},
                   {"prompt": "Second full source fixture", "cases": [{"case_id": "b", "case_sha256": "b" * 64}]}]
        with patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production"}), patch.object(model_runtime, "call") as call:
            complete = corpus.calibration_plan(batches, "domain", max_output_tokens=12000)
            selected = corpus.calibration_plan(batches, "domain", max_output_tokens=12000, batch_index=2)
            self.assertEqual(selected, [complete[1]])
            self.assertEqual(selected[0]["batch"], 2)
            for index in (0, 3, True, 1.0, "1"):
                with self.subTest(index=index), self.assertRaisesRegex(ValueError, "actual canonical batch"):
                    corpus.calibration_plan(batches, "domain", batch_index=index)
        call.assert_not_called()

    def test_calibration_rejects_missing_duplicate_wrong_hash_and_foreign_labels_but_allows_abstention(self):
        cases = [{"case_id": "paper", "case_sha256": "a" * 64}]
        row = {**cases[0], "outcome": None, "rationale": "The linked evidence is not available to assess this claim."}
        self.assertEqual(corpus.calibration_predictions(json.dumps({"anchor_labels": [row]}), cases)[0]["outcome"], None)
        for rows in ([], [row, row], [{**row, "case_sha256": "b" * 64}], [{**row, "outcome": "supports"}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                corpus.calibration_predictions(json.dumps({"anchor_labels": rows}), cases)

    def test_explicit_output_capacity_binds_scope_plan_and_price_without_changing_default(self):
        batch = {"prompt": "Complete source fixture", "cases": [{"case_id": "a", "case_sha256": "a" * 64}]}
        with patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production", "DR_OS_CLOUD_EXECUTOR": "1"}):
            default = corpus.calibration_plan([batch], "domain")[0]
            with model_routing.public_review_calibration_route("domain", "a" * 64, max_output_tokens=12000):
                route = model_routing.select("auxiliary", "independent-critique")
                enlarged = corpus.calibration_plan([batch], "domain", route, max_output_tokens=12000)[0]
                self.assertEqual(route["validation_scope"]["max_output_tokens"], 12000)
                with self.assertRaisesRegex(ValueError, "cap differ"):
                    corpus.calibration_plan([batch], "domain", route)
            self.assertEqual(model_routing.select("writing-and-review", "independent-critic-panel-domain")["max_output_tokens"], 4000)
        self.assertEqual((default["max_output_tokens"], enlarged["max_output_tokens"]), (4000, 12000))
        self.assertAlmostEqual(enlarged["reserved_upper_bound_cny"] - default["reserved_upper_bound_cny"], .056)

    def test_calibration_holdout_baseline_uses_training_only_and_missing_coverage_stays_unknown(self):
        anchors = [{"id": "a", "partition": "calibration", "label": "solid"},
                   {"id": "b", "partition": "holdout", "label": "convincing"}]
        report = corpus.calibration_metrics(anchors, [{"case_id": "a", "outcome": "solid"}])
        self.assertEqual(report["majority_class_from_calibration_only"], "solid")
        self.assertIsNone(report["partitions"]["holdout"]["exact_agreement"])
        self.assertEqual(report["partitions"]["holdout"]["majority_baseline_agreement"], 0)
        report = corpus.calibration_metrics(anchors, [{"case_id": "b", "outcome": None}])
        self.assertEqual(report["partitions"]["holdout"]["abstentions"], 1)
        self.assertEqual(report["partitions"]["holdout"]["exact_agreement"], 0)
        anchors.append({"id": "c", "partition": "calibration", "label": "convincing"})
        report = corpus.calibration_metrics(anchors, [{"case_id": "a", "outcome": "solid"}])
        self.assertIsNone(report["partitions"]["calibration"]["exact_agreement"])
        self.assertEqual(report["partitions"]["calibration"]["observed_subset_exact_agreement"], 1)
        self.assertIsNone(report["partitions"]["holdout"]["observed_subset_exact_agreement"])

    def test_calibration_costs_do_not_turn_missing_bills_or_unknown_holds_into_zero(self):
        for row in ({}, {"cost_cny": None}, {"cost_cny": 0, "cost_status": "accounted_upper_bound", "reserved_cost_cny": .4}):
            report = corpus.calibration_costs([{"run_id": "synthetic-attempt", "usage_receipts": [row]}])
            self.assertIsNone(report["accounted_amount_cny"])
            self.assertFalse(report["accounting_coverage_complete"])
            self.assertFalse(report["provider_fee_fully_verified"])
        report = corpus.calibration_costs([{"run_id": "synthetic-attempt", "usage_receipts": [
            {"cost_cny": .4, "cost_status": "estimated_upper_bound"}]}])
        self.assertEqual(report["accounted_amount_cny"], .4)
        self.assertFalse(report["provider_fee_fully_verified"])

    def test_paid_response_validation_failure_preserves_raw_answer_and_central_bill_without_retry(self):
        destination = self.root / "budget-project/evidence/auxiliary/synthetic-attempt.json"
        self.valid_calibration_response = False
        env = {"DR_OS_ROUTING_PROFILE": "production", "DR_OS_CLOUD_EXECUTOR": "1", "DR_OS_REQUIRE_REMOTE_RESERVATION": "1",
               "DR_OS_CLOUD_COMMAND_DEADLINE_EPOCH": str(time.time() + 3600)}
        with patch.dict(os.environ, env), patch.object(corpus, "__file__", str(self.root / "scripts/public_review_anchors.py")), \
             patch.object(corpus, "collect", side_effect=self.calibration_collection), \
             patch.object(corpus, "judgment_benchmark", side_effect=lambda *a, **k: {"blind_cases": self.calibration_cases}), \
             patch.object(model_runtime, "preflight_route"), \
             patch.object(model_runtime, "budget_status", return_value={"project_remaining": 500}), \
             patch.object(model_runtime, "call", side_effect=self.calibration_call) as execute:
            with self.assertRaisesRegex(ValueError, "omitted"):
                corpus.run_calibration(destination.parents[2], destination, "c" * 64, seat="domain", execute=True, max_output_tokens=12000)
        execute.assert_called_once()
        report = json.loads(destination.read_text())
        self.assertEqual(report["status"], "partial_failed_no_retry")
        self.assertEqual(report["model_predictions"], 0)
        self.assertTrue(all(row["max_output_tokens"] == 12000 for row in report["model_plan"]))
        self.assertEqual(report["accounting"]["accounted_amount_cny"], .4)
        self.assertFalse(report["accounting"]["provider_fee_fully_verified"])
        attempt = report["attempt_receipts"][0]
        self.assertEqual(attempt["status"], "response_received")
        response = self.root / ".runtime/cloud-artifact" / attempt["response_artifact"]
        self.assertEqual(corpus.sha(response), attempt["response_sha256"])
        self.assertEqual(json.loads(response.read_text())["provider_response_metadata"]["diagnostics"]["stop_reason"], "end_turn")

    def test_retained_live_manifest_has_24_distinct_licensed_partitioned_papers(self):
        path = Path(__file__).resolve().parents[1] / "docs/acceptance/elife-public-anchors-2026-11-07.json"
        report = json.loads(path.read_text())
        self.assertEqual(len({row["paper_doi"] for row in report["anchors"]}), 24)
        self.assertEqual(sum(row["partition"] == "holdout" for row in report["anchors"]), 8)
        self.assertTrue(all(row["license_url"] == corpus.LICENSE for row in report["anchors"]))
        self.assertEqual(report["calibration_status"], "NOT_CALIBRATED")
        self.assertIsNone(report["human_claim_sample_agreement"])
        self.assertEqual(report["model_predictions"], 0)

    def test_single_batch_success_preserves_full_population_and_stays_uncalibrated(self):
        self.valid_calibration_response = True
        env = {"DR_OS_ROUTING_PROFILE": "production", "DR_OS_CLOUD_EXECUTOR": "1", "DR_OS_REQUIRE_REMOTE_RESERVATION": "1",
               "DR_OS_CLOUD_COMMAND_DEADLINE_EPOCH": str(time.time() + 3600)}
        scopes = []
        for selected_index, expected_calls in ((2, 1), (None, 2)):
            destination = self.root / "budget-project/evidence/auxiliary" / f"synthetic-success-{selected_index}.json"
            with patch.dict(os.environ, env), patch.object(corpus, "__file__", str(self.root / "scripts/public_review_anchors.py")), \
                 patch.object(corpus, "collect", side_effect=self.calibration_collection), \
                 patch.object(corpus, "judgment_benchmark", side_effect=lambda *a, **k: {"blind_cases": self.calibration_cases}), \
                 patch.object(model_runtime, "preflight_route"), \
                 patch.object(model_runtime, "budget_status", return_value={"project_remaining": 500}), \
                 patch.object(model_runtime, "call", side_effect=self.calibration_call) as execute:
                report = corpus.run_calibration(destination.parents[2], destination, "c" * 64, seat="domain", execute=True,
                    max_output_tokens=12000, batch_cases=1, batch_index=selected_index)
            self.assertEqual(execute.call_count, expected_calls)
            self.assertEqual(report["calls_attempted"], expected_calls)
            self.assertEqual(report["model_predictions"], expected_calls)
            self.assertEqual(report["corpus_case_count"], 2)
            self.assertEqual(report["canonical_batch_count"], 2)
            self.assertEqual(report["corpus_coverage_complete"], selected_index is None)
            self.assertFalse(report["numeric_score_calibration_verified"])
            self.assertFalse(report["scientific_completion_verified"])
            self.assertEqual(report["calibration_status"], "EMPIRICAL_COMPARISON_COMPLETE" if selected_index is None else "NOT_CALIBRATED")
            result = report["results"]["domain"]
            if selected_index is not None:
                self.assertEqual(report["status"], "bounded_batch_complete")
                self.assertEqual([row["case_id"] for row in result["predictions"]], ["b"])
                self.assertIsNone(result["metrics"]["partitions"]["calibration"]["exact_agreement"])
                self.assertEqual(report["model_plan"][0]["batch"], 2)
            scopes.append(report["scope_sha256"])
        self.assertNotEqual(*scopes)
