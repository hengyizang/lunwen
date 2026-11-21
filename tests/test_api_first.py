import json
import os
import tempfile
import unittest
from pathlib import Path
from tests import research_cycle_fixtures as cycle_fixtures
from unittest.mock import patch

from scripts import api_orchestrator
from scripts.ai_providers import ModelResult, ProviderError


class ApiFirstTests(unittest.TestCase):
    def test_scientific_reply_requires_one_unambiguous_json_object(self):
        from scripts.research_artifacts import strict_json
        text = '{"finding":"uncertain","value":1.25}'
        for reply in (text, "```json\n" + text + "\n```", "```\n" + text + "\n```"):
            self.assertEqual(api_orchestrator._json_object(reply, "Scientific reply"), json.loads(text))
        for bad in ('{"finding":"uncertain","finding":"supported"}', '{"value":NaN}',
                    '{"value":1e999}', '{"nested":{"value":-1e999}}',
                    "Support is unverified. " + text, text + " Unsupported conclusion.",
                    "```json\n" + text, "```json\n" + text + "\n```\n" + text):
            with self.subTest(reply=bad), self.assertRaises(ValueError):
                api_orchestrator._json_object(bad, "Scientific reply")
        with self.assertRaises(ValueError):
            strict_json("```json\n" + text + "\n```", duplicate_error="duplicate")

    def test_actual_findings_alone_trigger_remediation(self):
        audit={"verdict":"pass-with-conditions","fatal_findings":[],"major_findings":[],"minor_findings":[],
               "missing_evidence":[],"remediation_steps":[],"uncertainty":["Known limits remain."]}
        self.assertFalse(api_orchestrator.remediation_required(audit,"topic-intelligence"))
        self.assertFalse(api_orchestrator.remediation_required(audit,"writing-and-review"))
        for field in ("fatal_findings","major_findings","minor_findings","missing_evidence","remediation_steps"):
            self.assertTrue(api_orchestrator.remediation_required({**audit,field:["Actual unresolved finding."]},"topic-intelligence"))
        self.assertFalse(api_orchestrator.remediation_required({**audit,"verdict":"revise"},"topic-intelligence"))
        for stage in ("topic-intelligence", "experiment-design", "scientific-writing"):
            self.assertFalse(api_orchestrator.remediation_required(audit, stage,
                ["The scientific interpretation remains provisional."]))
            self.assertTrue(api_orchestrator.remediation_required(audit, stage,
                ["unresolved: the writer identified an unsupported mechanism."]))
            with self.assertRaises(ValueError):
                api_orchestrator.validate_remediation_notes({"stage": stage, "notes": ["Unstructured response."]},
                    {**audit, "major_findings": ["The comparison is missing."]})

    def test_g5_revision_baseline_preserves_included_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "projects" / "demo"
            state = project / "state"
            manuscript_dir = project / "papers" / "P01" / "manuscript"
            state.mkdir(parents=True)
            manuscript_dir.mkdir(parents=True)
            (state / "run.json").write_text(
                json.dumps({"active_paper": "P01", "writing_phases":{"P01":"submission"}}), encoding="utf-8"
            )
            (manuscript_dir / "main.tex").write_text(
                "\\documentclass{article}\\begin{document}\\input{results}\\end{document}",
                encoding="utf-8",
            )
            (manuscript_dir / "results.tex").write_text(
                "The model may improve accuracy by 10 percent.", encoding="utf-8"
            )
            with patch.object(api_orchestrator, "ROOT", root):
                first = api_orchestrator.prepare_revision_baseline(
                    "demo", "writing-and-review"
                )
                (manuscript_dir / "results.tex").write_text(
                    "The model proves accuracy improved by 12 percent.", encoding="utf-8"
                )
                second = api_orchestrator.prepare_revision_baseline(
                    "demo", "writing-and-review"
                )
            baseline = project / "papers" / "P01" / "reviews" / "revision-base"
            self.assertTrue((baseline / "main.tex").is_file())
            self.assertIn("10 percent", (baseline / "results.tex").read_text(encoding="utf-8"))
            self.assertEqual(first, second)

    def test_g5_refreshes_a_local_style_audit_without_detector_scoring(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "projects" / "demo"
            state = project / "state"
            manuscript = project / "papers" / "P01" / "manuscript" / "main.tex"
            state.mkdir(parents=True)
            manuscript.parent.mkdir(parents=True)
            (state / "run.json").write_text(
                json.dumps({"active_paper": "P01", "writing_phases":{"P01":"submission"}}), encoding="utf-8"
            )
            manuscript.write_text(
                " ".join(
                    f"Analysis group {index} compares documented observations with the registered baseline and reports uncertainty."
                    for index in range(80)
                ),
                encoding="utf-8",
            )
            with patch.object(api_orchestrator, "ROOT", root):
                summary = api_orchestrator.refresh_academic_style_audit(
                    "demo", "writing-and-review"
                )
            self.assertIsNotNone(summary)
            self.assertFalse(summary["detector_score_used"])
            self.assertTrue(
                (project / "papers" / "P01" / "style" / "academic-style-audit.json").is_file()
            )

    def test_writer_prompt_keeps_explicit_topic_criteria_without_loading_all_stage_rules(self):
        context="Compare novelty, doctoral contribution, no-laboratory feasibility, employment/salary, sample/unit adequacy and leakage."
        prompt=api_orchestrator.writer_prompt("missing-project","topic-intelligence",context)
        self.assertIn(context,prompt)
        self.assertIn("unknowns",prompt)
        self.assertNotIn("owner-supplied G0 weights",prompt)

    def test_experiment_context_preserves_exploration_and_frozen_history(self):
        prompt=api_orchestrator.writer_prompt("missing-project","experiment-execution","Inspect failed baseline run")
        self.assertIn("research_phase='exploratory'",prompt)
        self.assertIn("Do not relabel historical runs",prompt)
        self.assertNotIn("baseline-reproduction.json",prompt)

    def test_writing_and_review_preserve_evidence_without_prior_verdict(self):
        writer=api_orchestrator.writer_prompt("missing-project","writing-and-review","Explain the strongest supported contribution")
        critic=api_orchestrator.critic_prompt("missing-project","writing-and-review","my-preferred-verdict")
        self.assertIn("strongest supported contribution",writer)
        self.assertIn("contrary evidence",writer)
        self.assertIn("uncertainty",critic)
        self.assertNotIn("my-preferred-verdict",critic)

    def test_automatic_data_failure_stops_before_paid_model_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "stages.json").write_text(
                json.dumps(
                    {
                        "stages": {
                            "topic-intelligence": {
                                "gate": "G1",
                                "contract": "Topic intelligence — G1",
                                "author_task": "Research candidates",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            state = root / "projects" / "demo" / "state"
            state.mkdir(parents=True)
            (state / "run.json").write_text(
                json.dumps(
                    {
                        "stage": "topic-intelligence",
                        "gate": "G1",
                        "status": "awaiting_work",
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(api_orchestrator, "ROOT", root), patch.object(
                api_orchestrator,
                "run_automatic_dataset_discovery",
                side_effect=ValueError("all sources offline"),
            ), patch("scripts.api_orchestrator.ai_providers.call") as model_call:
                with self.assertRaisesRegex(ValueError, "Automatic dataset discovery failed"):
                    api_orchestrator.run_cycle(
                        "demo",
                        "topic-intelligence",
                        "uuapi-anthropic",
                        "uuapi-openai",
                        "uuapi-anthropic",
                        "",
                        "",
                        automatic_data=True,
                    )
            model_call.assert_not_called()
            errors = list((root / "projects" / "demo" / "api_runs").glob(
                "*/automatic-data-discovery-error.txt"
            ))
            self.assertEqual(len(errors), 1)

    def test_experiment_design_receives_latest_broad_dataset_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "projects" / "demo" / "data"
            data.mkdir(parents=True)
            (data / "discovery-broad-20260901T000000Z.json").write_text(
                json.dumps(
                    {
                        "created_at": "2026-09-01T00:00:00+00:00",
                        "queries": ["bearing vibration dataset"],
                        "candidate_count": 1,
                        "ranking_note": "metadata overlap only",
                        "warning": "human review required",
                        "candidates": [
                            {
                                "provider": "Zenodo",
                                "title": "Bearing benchmark",
                                "landing_url": "https://zenodo.org/records/1",
                                "doi": "10.1/example",
                                "license_claim": "CC-BY-4.0",
                                "metadata_relevance_score": 82,
                                "screening_reasons": ["title-term match"],
                                "fitness_status": "candidate_only_requires_source_bound_scientific_review",
                                "automatic_screening": {
                                    "rank": 1,
                                    "status": "metadata_shortlist",
                                    "metadata_score": 82,
                                    "scientific_fitness_assessed": False,
                                },
                            }
                        ],
                        "automatic_screening_summary": {
                            "method": "deterministic_metadata_screening",
                            "minimum_metadata_score": 25,
                            "maximum_shortlist": 80,
                            "shortlist_count": 1,
                            "deprioritized_count": 0,
                            "criteria": ["metadata overlap"],
                            "not_automatically_decided": ["scientific fitness"],
                            "human_review_required": True,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(api_orchestrator, "ROOT", root):
                evidence = json.loads(
                    api_orchestrator.discover_context(
                        "demo", "experiment-design", ""
                    )
                )
            saved = evidence["saved_broad_dataset_discovery"]
            self.assertEqual(saved["included_candidate_count"], 1)
            self.assertEqual(
                saved["candidates"][0]["automatic_screening"]["status"],
                "metadata_shortlist",
            )
            self.assertFalse(
                saved["automatic_screening_summary"]["human_review_required"]
            )
            self.assertTrue(saved["automatic_screening_summary"]["scientific_review_required"])
            self.assertTrue(json.loads((root / "projects/demo" / saved["source_file"]).read_text())["automatic_screening_summary"]["human_review_required"])
            self.assertEqual(saved["candidates"][0]["title"], "Bearing benchmark")
            self.assertEqual(
                saved["candidates"][0]["license_claim_unverified"], "CC-BY-4.0"
            )

    def test_safe_target_rejects_traversal(self):
        for relative in ("../escape.txt", "C:\\escape.txt", "."):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                api_orchestrator.safe_target("demo", relative)

    def test_safe_target_rejects_state(self):
        for relative in ("state/run.json", "state/model-note.json"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                api_orchestrator.safe_target("demo", relative)

    def test_safe_target_rejects_hidden_and_run_artifacts(self):
        for relative in (".hidden/note.md", "api_runs/fake/manifest.json"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                api_orchestrator.safe_target("demo", relative)

    def test_safe_target_accepts_scientific_artifact(self):
        target = api_orchestrator.safe_target("demo", "papers/P01/manuscript.md")
        self.assertEqual(target.parts[-5:], ("projects", "demo", "papers", "P01", "manuscript.md"))

    def test_extract_bundle(self):
        value = api_orchestrator.extract_json(json.dumps({
            "schema_version": "1.0", "stage": "intake",
            "artifacts": [{"path": "research-brief.md", "content": "hello"}],
            "notes": []
        }))
        self.assertEqual(value["stage"], "intake")

    def test_extract_bundle_rejects_invalid_schema(self):
        with self.assertRaises(ValueError):
            api_orchestrator.extract_json('{"schema_version":"9.0","stage":"intake","artifacts":[],"notes":[]}')

    def test_extract_bundle_rejects_extra_fields(self):
        with self.assertRaises(ValueError):
            api_orchestrator.extract_json(
                '{"schema_version":"1.0","stage":"intake","artifacts":[],"notes":[],"command":"rm"}'
            )

    def test_provider_call_rejects_unknown_provider(self):
        with self.assertRaises(ProviderError):
            from scripts import ai_providers
            ai_providers.call("unknown", "hello")

    def test_apply_bundle_does_not_write_protected_state(self):
        bundle = {"stage": "intake", "artifacts": [
            {"path": "state/run.json", "content": "{}"}
        ]}
        with self.assertRaises(ValueError):
            api_orchestrator.apply_bundle("demo", bundle)

    def test_apply_bundle_prevalidates_without_partial_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            bundle={"stage":"intake","artifacts":[{"path":"intake/ok.txt","content":"written"},{"path":"state/run.json","content":"{}"}]}
            with patch.object(api_orchestrator,"ROOT",root),self.assertRaises(ValueError):api_orchestrator.apply_bundle("demo",bundle)
            self.assertFalse((root/"projects"/"demo"/"intake"/"ok.txt").exists())

    def test_apply_bundle_rejects_duplicate_paths(self):
        bundle={"stage":"intake","artifacts":[{"path":"intake/a.txt","content":"one"},{"path":"intake/a.txt","content":"two"}]}
        with self.assertRaisesRegex(ValueError,"Duplicate"):
            api_orchestrator.apply_bundle("demo",bundle)

    def test_safe_target_protects_independent_review_files(self):
        for relative in (
            "reviews/codex/G1-fake-final.json",
            "reviews/independent/G1-fake-final.json",
            "reviews/decision-log.md",
        ):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                api_orchestrator.safe_target("demo", relative)

    def test_safe_target_protects_automatic_discovery_evidence(self):
        for relative in (
            "data/discovery-broad-auto-20260902T000000Z.json",
            "evidence/dataset-search-log.jsonl",
            "evidence/search-log.jsonl",
            "evidence/literature-api-ledger.jsonl",
            "evidence/literature/raw/receipt.json",
            "evidence/ai4science-ledger.jsonl",
            "program/venue-candidates.json",
        ):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                api_orchestrator.safe_target("demo", relative)

    def test_safe_target_protects_deterministic_style_audit(self):
        with self.assertRaisesRegex(ValueError, "style audit"):
            api_orchestrator.safe_target(
                "demo", "papers/P01/style/academic-style-audit.json"
            )

    def test_safe_target_protects_citation_and_revision_controls(self):
        for relative in (
            "program/journal-screening.json",
            "papers/P01/reviews/ref-verify.json",
            "papers/P01/reviews/revision-trace.json",
            "papers/P01/reviews/revision-integrity.json",
            "papers/P01/reviews/reporting-guideline.json",
            "papers/P01/reviews/revision-authorizations.json",
            "papers/P01/reviews/revision-base.tex",
            "papers/P01/reviews/revision-base/main.tex",
        ):
            with self.assertRaises(ValueError):
                api_orchestrator.safe_target("demo", relative)

    def test_safe_target_protects_deterministic_research_quality_records(self):
        for relative in (
            "data/quality/d1.json",
            "data/quality/d1-confirmation.json",
            "papers/P01/power-analysis.json",
            "papers/P01/preregistration.json",
            "papers/P01/reproduction-confirmation.json",
            "reports/runtime-evidence-catalog.json",
        ):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                api_orchestrator.safe_target("demo", relative)

    def test_snapshot_includes_content_and_excludes_sensitive_areas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "projects" / "demo"
            (project / "program").mkdir(parents=True)
            (project / "data" / "raw").mkdir(parents=True)
            (project / "api_runs" / "old").mkdir(parents=True)
            (project / "reviews").mkdir(parents=True)
            (project / "program" / "topic.md").write_text(
                "scientific content", encoding="utf-8"
            )
            (project / "data" / "raw" / "private.txt").write_text(
                "private payload", encoding="utf-8"
            )
            (project / "api_runs" / "old" / "response.txt").write_text(
                "feedback loop", encoding="utf-8"
            )
            (project / ".env").write_text("KEY=secret", encoding="utf-8")
            (project / "reviews" / "decision-log.md").write_text(
                "prior verdict", encoding="utf-8"
            )
            with patch.object(api_orchestrator, "ROOT", root):
                snapshot = api_orchestrator.project_snapshot(
                    "demo", exclude_reviews=True, source_paths=["program/topic.md"]
                )
            self.assertIn("scientific content", snapshot)
            self.assertNotIn("private payload", snapshot)
            self.assertNotIn("feedback loop", snapshot)
            self.assertNotIn("KEY=secret", snapshot)
            self.assertNotIn("prior verdict", snapshot)

    def test_writing_snapshot_keeps_active_paper_and_other_contracts_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "projects" / "demo"
            (project / "state").mkdir(parents=True)
            (project / "state" / "run.json").write_text(
                json.dumps({"active_paper": "P01"}), encoding="utf-8"
            )
            for paper in ("P01", "P02"):
                (project / "papers" / paper / "manuscript").mkdir(parents=True)
                (project / "papers" / paper / "reviews").mkdir(parents=True)
                (project / "papers" / paper / "paper-contract.json").write_text(
                    json.dumps({"paper_id": paper, "marker": f"{paper} contract"}),
                    encoding="utf-8",
                )
            (project / "papers" / "P01" / "manuscript" / "main.tex").write_text(
                "active manuscript", encoding="utf-8"
            )
            (project / "papers" / "P02" / "manuscript" / "main.tex").write_text(
                "inactive manuscript", encoding="utf-8"
            )
            (project / "papers" / "P01" / "reviews" / "round.md").write_text(
                "duplicated review", encoding="utf-8"
            )
            with patch.object(api_orchestrator, "ROOT", root):
                snapshot = api_orchestrator.project_snapshot(
                    "demo", stage="writing-and-review", exclude_reviews=True
                )
            self.assertIn("active manuscript", snapshot)
            self.assertNotIn("P02 contract", snapshot)
            self.assertNotIn("inactive manuscript", snapshot)
            self.assertNotIn("duplicated review", snapshot)

    def test_extract_audit_requires_exact_schema(self):
        audit = cycle_fixtures.independent_audit('revise', major_findings=['missing baseline'], remediation_steps=['add baseline'])
        self.assertEqual(
            api_orchestrator.extract_audit_json(json.dumps(audit)), audit
        )
        audit["unexpected"] = []
        with self.assertRaises(ValueError):
            api_orchestrator.extract_audit_json(json.dumps(audit))

    def test_extract_semantic_plan_requires_non_prose_structure(self):
        plan = cycle_fixtures.semantic_plan('intake', objectives=['capture constraints'])
        self.assertEqual(api_orchestrator.extract_plan_json(json.dumps(plan)), plan)

    def test_long_claude_phrase_copy_is_rejected(self):
        source = {
            "idea": "one two three four five six seven eight nine ten eleven twelve thirteen"
        }
        target = {
            "artifacts": [
                {
                    "content": "one two three four five six seven eight nine ten eleven twelve",
                }
            ]
        }
        api_orchestrator.reject_long_source_copy(source, target, "plan")

    def test_long_cjk_claude_phrase_copy_is_rejected(self):
        source = {"idea": "这是一个用于验证长中文原文复制检测功能是否能够正常工作的测试句子"}
        target = {"content": "用于验证长中文原文复制检测功能是否能够正常工作的测试句子"}
        api_orchestrator.reject_long_source_copy(source, target, "plan")

    def test_cycle_persists_gate_audits_and_decision_log(self):
        self._assert_cycle_records()

    def test_clean_initial_review_completes_three_call_cycle(self):
        self._assert_cycle_records(clean_initial=True)

    def test_clean_review_preserves_ordinary_uncertainty_notes_without_an_extra_model_call(self):
        self._assert_cycle_records(clean_initial=True,
            writer_notes=["The scientific interpretation remains provisional."])

    def test_missing_cycle_decision_remains_repairable_work(self):
        self._assert_cycle_records(with_decision=False)

    def test_current_independent_assessment_errors_are_not_replaced_by_the_prereview_record(self):
        self._assert_cycle_records(clean_initial=True, review_problem="the final critic assessed another cycle")

    def _assert_cycle_records(self, clean_initial=False, with_decision=True, writer_notes=None, review_problem=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project=root/"projects/demo";state=project/"state/run.json"
            state.parent.mkdir(parents=True)
            initial_state={"stage":"intake","gate":"G0","status":"awaiting_approval"}
            state.write_text(json.dumps(initial_state))
            initial=cycle_fixtures.independent_audit("pass-with-conditions" if clean_initial else "revise",
                major_findings=[] if clean_initial else ["missing comparison"])
            final=cycle_fixtures.independent_audit("pass-with-conditions",uncertainty=[review_problem or "Evidence remains provisional"])
            payloads={
                "semantic-planner":cycle_fixtures.semantic_plan("topic-intelligence",objectives=["compare candidates"]),
                "persistent-writer":cycle_fixtures.artifact_bundle("topic-intelligence",artifacts=[{"path":"program/topic.md","content":"draft"}],notes=writer_notes or []),
                "independent-critic-initial":initial,
                "persistent-remediator":cycle_fixtures.artifact_bundle("topic-intelligence",artifacts=[{"path":"program/topic.md","content":"revised"}],notes=["fixed: added the requested comparison"]),
                "independent-critic-final":final}
            def respond(_project,**kwargs):
                role=kwargs["role"];provider=kwargs["provider"];model="claude-fixture" if "anthropic" in provider else "gpt-fixture"
                return ModelResult(provider,model,json.dumps(payloads[role]),{},reported_model=model,completion_status="completed",request_id=role)
            with patch.dict(os.environ,{"DR_OS_ROUTING_PROFILE":"legacy"},clear=True),patch.object(api_orchestrator,"ROOT",root), \
                 patch("scripts.model_runtime.preflight_route",return_value={}),patch("scripts.model_runtime.budget_status",return_value={}), \
                 patch("scripts.model_runtime.call",side_effect=respond) as model_call:
                manifest=api_orchestrator.run_cycle("demo","topic-intelligence","uuapi-anthropic","uuapi-openai","uuapi-anthropic", "Compare candidates", "",
                    planning=True,review=True,remediate=True)
            self.assertEqual([row.kwargs["max_output_tokens"] for row in model_call.call_args_list],
                             [4000,12000,4000] if clean_initial else [4000,12000,4000,12000,4000])
            self.assertEqual(len(manifest["reviews"]),1 if clean_initial else 2)
            self.assertEqual(json.loads(state.read_text()),initial_state)
            self.assertFalse(manifest["scientific_completion_verified"])
            self.assertNotIn("research_decision",manifest)
            self.assertEqual(manifest["notes"],writer_notes or [] if clean_initial else ["fixed: added the requested comparison"])
            for row in manifest["reviews"]:
                self.assertFalse(row["identity"]["cache_hit"])
                self.assertEqual(row["sources"][0]["path"],"program/topic.md")
                self.assertTrue((project/row["audit"]["path"]).is_file())
                self.assertEqual(len(row["prompt_sha256"]),64)
            provenance=json.loads((project/"state/output-provenance.json").read_text())
            self.assertEqual(provenance["files"]["program/topic.md"]["family"],"openai")

    def test_cycle_requires_current_initialized_stage(self):
        with self.assertRaises(ValueError):
            api_orchestrator.run_cycle(
                "not-initialized",
                "intake",
                "uuapi-anthropic",
                "uuapi-openai",
                "uuapi-anthropic",
                "",
                "",
            )

    def test_old_approval_status_is_readable_context_not_writing_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/"projects/demo/state/run.json";state.parent.mkdir(parents=True)
            value={"stage":"intake","gate":"G0","status":"awaiting_approval"};state.write_text(json.dumps(value))
            with patch.object(api_orchestrator,"ROOT",root):
                self.assertEqual(api_orchestrator.require_current_stage("demo","different-context"),value)
