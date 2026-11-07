"""Actual controller paths with mocked transports; no scientific acceptance or spend."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ai_providers, api_orchestrator as api, review_panel, model_runtime, research_cycle
from scripts.research_artifacts import read, write, sha


def panel_inputs(project):
    rows = {}
    for seat, kinds in review_panel.VIEWS.items():
        rows[seat] = []
        for kind in sorted(kinds):
            target = project / f"papers/P01/manuscript/{kind}.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"SYNTHETIC {kind} source, no actual experiment.\n", encoding="utf-8")
            rows[seat].append({"kind": kind, "path": target.relative_to(project).as_posix(),
                "sha256": sha(target), "start_line": 1, "end_line": 1})
    write(project / review_panel.request_path("P01"), {"paper_id": "P01", "views": rows})


class ReviewPanelTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.project = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        write(self.project / "state/run.json", {"stage":"writing-and-review", "gate":"G5", "active_paper":"P01",
            "writing_phases":{"P01":"submission"}})
        panel_inputs(self.project)
        self.stack.enter_context(patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR":"1"}))
        self.stack.enter_context(patch.object(model_runtime, "preflight_route", return_value={}))

    def response(self, project, **kwargs):
        seat = kwargs["role"].removeprefix("independent-critic-panel-")
        body = {"view": seat, "findings": [], "uncertainty": ["Synthetic software fixture; no scientific conclusion."]}
        if seat == "domain":
            path = f"papers/P01/manuscript/methods.txt:L1-L1"
            body["findings"] = [{"id":"rival-1", "claim_pointer":path, "evidence_pointer":path,
                "gap":"Rival explanation remains", "minimum_test":"Compare an independent outcome",
                "severity":"major", "rationale":"Supplied fixture contains no experiment."}]
        return ai_providers.ModelResult(kwargs["provider"], kwargs["model"], json.dumps(body), {"input_tokens":2},
            request_id="synthetic-" + seat, reported_model=kwargs["model"], completion_status="completed", cache_hit=False)

    def run_panel(self, run="first"):
        with patch.object(model_runtime, "call", side_effect=self.response) as calls:
            result = review_panel.run(self.project, "P01", run)
        return result, calls

    def test_three_blind_distinct_families_freeze_before_synthesis_and_reuse_unchanged(self):
        result, calls = self.run_panel()
        self.assertEqual(calls.call_count, 3)
        self.assertEqual(result["paid_calls"], 3)
        records = review_panel.responses(self.project, "P01")
        self.assertEqual({r["receipt"]["identity"]["family"] for r in records}, {"anthropic", "google", "deepseek"})
        for call in calls.call_args_list:
            self.assertFalse(call.kwargs["use_cache"])
            self.assertEqual(call.kwargs["task_profile"]["science_risk"], "critical")
            seat = call.kwargs["role"].removeprefix("independent-critic-panel-")
            for other in set(review_panel.VIEWS) - {seat}:
                unique = review_panel.VIEWS[other] - review_panel.VIEWS[seat]
                self.assertFalse(any("SYNTHETIC " + k + " source" in call.kwargs["prompt"] for k in unique))
            self.assertNotIn("Rival explanation remains", call.kwargs["prompt"])
        self.assertFalse(result["scientific_completion_verified"])
        self.assertFalse(result["gate_authority"])
        self.assertEqual(result["findings"][0]["severity"], "major")
        reused, calls = self.run_panel("different-run")
        self.assertEqual(reused["paid_calls"], 0)
        self.assertEqual(calls.call_count, 0)
        self.assertEqual(reused["findings"], result["findings"])
        self.assertTrue(result["record_errors"])
        self.assertIn("Rival explanation remains", review_panel.author_context(self.project, "P01"))

    def test_private_other_paper_control_and_prior_review_paths_never_reach_transport(self):
        for relative in ("data/private/raw.csv", "papers/P02/manuscript/main.tex", "reviews/prior.json",
                         "papers/P01/manuscript/private/labels.txt", "program/answer-key.json", ".env"):
            with self.subTest(relative=relative):
                target = self.project / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("secret answer or unrelated paper", encoding="utf-8")
                spec = read(self.project / review_panel.request_path("P01"))
                spec["views"]["domain"][0].update(path=relative, sha256=sha(target))
                write(self.project / review_panel.request_path("P01"), spec)
                with patch.object(model_runtime, "call") as call, self.assertRaises(ValueError):
                    review_panel.run(self.project, "P01", "unsafe")
                call.assert_not_called()

    def test_partial_failure_retained_and_same_id_never_repaid(self):
        count = 0
        def fail(project, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise ValueError("synthetic transport failure")
            return self.response(project, **kwargs)
        with patch.object(model_runtime, "call", side_effect=fail), self.assertRaisesRegex(ValueError, "transport failure"):
            review_panel.run(self.project, "P01", "partial")
        directory = self.project / review_panel.PREFIX / "P01/partial"
        self.assertTrue((directory / "domain.json").is_file())
        self.assertTrue((directory / "failure.json").is_file())
        self.assertFalse((directory.parent / "latest.json").exists())
        with patch.object(model_runtime, "call") as call, self.assertRaisesRegex(ValueError, "already attempted"):
            review_panel.run(self.project, "P01", "partial")
        call.assert_not_called()

    def test_identity_mismatch_retains_actual_failed_response(self):
        def mismatch(project, **kwargs):
            result = self.response(project, **kwargs)
            result.reported_model = "unexpected"
            return result
        with patch.object(model_runtime, "call", side_effect=mismatch), self.assertRaisesRegex(ValueError, "mismatch"):
            review_panel.run(self.project, "P01", "identity")
        self.assertTrue((self.project / review_panel.PREFIX / "P01/identity/domain-actual-response.json").is_file())
        self.assertTrue(review_panel.submission_errors(self.project, "P01"))

    def test_stale_sources_require_new_call_and_retained_disagreement(self):
        self.run_panel()
        path = self.project / "papers/P01/manuscript/methods.txt"
        path.write_text(path.read_text() + "A second synthetic source line.\n")
        self.assertTrue(review_panel.submission_errors(self.project, "P01"))
        spec = read(self.project / review_panel.request_path("P01"))
        for row in spec["views"]["domain"]:
            if row["kind"] == "methods": row["sha256"] = sha(path)
        spec["dispositions"] = [{"finding_id":"first:domain:rival-1", "status":"maintained", "rationale":"No discriminating experiment exists", "evidence":[]}]
        write(self.project / review_panel.request_path("P01"), spec)
        result, calls = self.run_panel("second")
        manifest = read(self.project / result["manifest"]["path"])
        self.assertEqual(calls.call_count, 3)
        self.assertEqual(len(manifest["prior_findings"]), 1)
        self.assertNotEqual(manifest["prior_findings"][0]["finding_id"], manifest["findings"][0]["finding_id"])
        self.assertEqual(manifest["prior_findings"][0]["local_finding_id"], manifest["findings"][0]["local_finding_id"])
        self.assertEqual(manifest["author_dispositions"], spec["dispositions"])
        self.assertIsNone(manifest["acceptance_probability"])

    def test_tampered_frozen_report_never_becomes_cache_miss_or_new_paid_call(self):
        result, _ = self.run_panel()
        target = self.project / result["manifest"]["path"]
        target.write_text(target.read_text() + "\n")
        with patch.object(model_runtime, "call") as call, self.assertRaises(ValueError):
            review_panel.run(self.project, "P01", "changed")
        call.assert_not_called()

    def test_shared_submission_adapter_does_not_create_ordinary_critic(self):
        with patch.object(research_cycle, "research_decision", return_value={"status":"recorded", "scientific_completion_verified":False}), \
                patch.object(model_runtime, "call", side_effect=self.response) as calls:
            result = research_cycle.submission_cycle(self.project, "adapter", writer_family="openai",
                refresh=lambda phase: ({"controlled_steps":{}, "academic_style_audit":{}}, {}))
        self.assertEqual(calls.call_count, 3)
        self.assertEqual(result["audits"], {})
        self.assertFalse(result["research_decision"]["scientific_completion_verified"])
        self.assertFalse((self.project / "state/review-receipts/G5-P01").exists())

    def test_model_cannot_overwrite_controller_finding_identity(self):
        result = self.response(self.project, role="independent-critic-panel-domain", provider="codekey-kiro-enterprise", model="claude-opus-5-5")
        response = json.loads(result.text)
        for field in ("finding_id", "source_run_id", "view", "local_finding_id"):
            forged = {**response, "findings":[{**response["findings"][0], field:"forged"}]}
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "read-only schema"):
                review_panel._response(forged, "domain")

    def test_pointer_must_be_inside_supplied_range(self):
        for pointer in ("papers/P01/manuscript/methods.txt:L999999", "papers/P01/manuscript/methods.txt:Lgarbage",
                        "papers/P01/manuscript/methods.txt:L1-L2", "papers/P01/manuscript/methods.txt"):
            with self.subTest(pointer=pointer):
                self.assertFalse(review_panel._pointer_in_view(pointer, review_panel.prepare(self.project, "P01")["views"]["domain"]["sources"]))
        self.assertTrue(review_panel._pointer_in_view("papers/P01/manuscript/methods.txt:L1-L1",
            review_panel.prepare(self.project, "P01")["views"]["domain"]["sources"]))

    def test_author_disposition_alone_does_not_repeat_paid_panel(self):
        result, _ = self.run_panel()
        spec = read(self.project / review_panel.request_path("P01"))
        spec["dispositions"] = [{"finding_id":result["findings"][0]["finding_id"], "status":"maintained",
            "rationale":"No discriminating evidence has arrived", "evidence":[{"path":"papers/P01/manuscript/methods.txt", "sha256":sha(self.project / "papers/P01/manuscript/methods.txt")}]}]
        write(self.project / review_panel.request_path("P01"), spec)
        reused, calls = self.run_panel("author-response")
        self.assertEqual(calls.call_count, 0)
        self.assertEqual(reused["author_dispositions"], spec["dispositions"])
        self.assertEqual(review_panel.submission_errors(self.project, "P01"), [])
        self.assertFalse(reused["scientific_completion_verified"])
        self.assertEqual(reused["findings"][0]["severity"], "major")

    def test_context_plan_cannot_reintroduce_hidden_answers(self):
        from scripts import evidence_context
        target = self.project / "evidence/answer.txt"
        target.parent.mkdir()
        target.write_text("Hidden expected judgment")
        write(self.project / "program/context-plan.json", {"schema_version":"1.0", "stages":{
            "writing-and-review":{"question":"Inspect evidence", "items":[{"path":"evidence/answer.txt", "reason":"try", "stance":"neutral"}]}}})
        with self.assertRaisesRegex(ValueError, "hidden judgment"):
            evidence_context.build(self.project, "writing-and-review", excluded_paths={"evidence/answer.txt"})

if __name__ == "__main__":
    unittest.main()
