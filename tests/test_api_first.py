import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator
from scripts.ai_providers import ModelResult, ProviderError


class ApiFirstTests(unittest.TestCase):
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
                                "fitness_status": "candidate_only_requires_scientific_and_human_review",
                            }
                        ],
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
        self.assertTrue(str(target).endswith("projects/demo/papers/P01/manuscript.md"))

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
                    "demo", exclude_reviews=True
                )
            self.assertIn("scientific content", snapshot)
            self.assertNotIn("private payload", snapshot)
            self.assertNotIn("feedback loop", snapshot)
            self.assertNotIn("KEY=secret", snapshot)
            self.assertNotIn("prior verdict", snapshot)

    def test_extract_audit_requires_exact_schema(self):
        audit = {
            "verdict": "revise",
            "fatal_findings": [],
            "major_findings": ["missing baseline"],
            "minor_findings": [],
            "missing_evidence": [],
            "remediation_steps": ["add baseline"],
            "uncertainty": [],
        }
        self.assertEqual(
            api_orchestrator.extract_audit_json(json.dumps(audit)), audit
        )
        audit["unexpected"] = []
        with self.assertRaises(ValueError):
            api_orchestrator.extract_audit_json(json.dumps(audit))

    def test_extract_semantic_plan_requires_non_prose_structure(self):
        plan = {
            "schema_version": "1.0",
            "stage": "intake",
            "objectives": ["capture constraints"],
            "artifact_specs": [],
            "evidence_requirements": [],
            "figure_specs": [],
            "risks": [],
            "open_questions": [],
        }
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
        with self.assertRaises(ValueError):
            api_orchestrator.reject_long_source_copy(source, target, "plan")

    def test_long_cjk_claude_phrase_copy_is_rejected(self):
        source = {"idea": "这是一个用于验证长中文原文复制检测功能是否能够正常工作的测试句子"}
        target = {"content": "用于验证长中文原文复制检测功能是否能够正常工作的测试句子"}
        with self.assertRaises(ValueError):
            api_orchestrator.reject_long_source_copy(source, target, "plan")

    def test_cycle_persists_gate_audits_and_decision_log(self):
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
            semantic_plan = json.dumps(
                {
                    "schema_version": "1.0",
                    "stage": "topic-intelligence",
                    "objectives": ["compare candidates"],
                    "artifact_specs": [],
                    "evidence_requirements": [],
                    "figure_specs": [],
                    "risks": [],
                    "open_questions": [],
                }
            )
            writer_bundle = json.dumps(
                {
                    "schema_version": "1.0",
                    "stage": "topic-intelligence",
                    "artifacts": [
                        {"path": "program/topic.md", "content": "draft"}
                    ],
                    "notes": [],
                }
            )
            initial_audit = json.dumps(
                {
                    "verdict": "revise",
                    "fatal_findings": [],
                    "major_findings": ["missing comparison"],
                    "minor_findings": [],
                    "missing_evidence": [],
                    "remediation_steps": ["add comparison"],
                    "uncertainty": [],
                }
            )
            remediation = json.dumps(
                {
                    "schema_version": "1.0",
                    "stage": "topic-intelligence",
                    "artifacts": [
                        {"path": "program/topic.md", "content": "revised"}
                    ],
                    "notes": ["fixed: added the requested comparison"],
                }
            )
            final_audit = json.dumps(
                {
                    "verdict": "pass-with-conditions",
                    "fatal_findings": [],
                    "major_findings": [],
                    "minor_findings": ["human verification remains"],
                    "missing_evidence": [],
                    "remediation_steps": [],
                    "uncertainty": ["external facts remain provisional"],
                }
            )
            responses = [
                ModelResult("uuapi-anthropic", "claude-test", semantic_plan, {}),
                ModelResult("uuapi-openai", "gpt-test", writer_bundle, {}),
                ModelResult("uuapi-anthropic", "claude-test", initial_audit, {}),
                ModelResult("uuapi-openai", "gpt-test", remediation, {}),
                ModelResult("uuapi-anthropic", "claude-test", final_audit, {}),
            ]
            with patch.object(api_orchestrator, "ROOT", root), patch(
                "scripts.api_orchestrator.ai_providers.call",
                side_effect=responses,
            ):
                manifest = api_orchestrator.run_cycle(
                    "demo",
                    "topic-intelligence",
                    "uuapi-anthropic",
                    "uuapi-openai",
                    "uuapi-anthropic",
                    "",
                    "",
                )
            reviews = list((root / "projects" / "demo" / "reviews" / "independent").glob("*.json"))
            self.assertEqual(len(reviews), 2)
            self.assertTrue(any(path.name.endswith("-initial.json") for path in reviews))
            self.assertTrue(any(path.name.endswith("-final.json") for path in reviews))
            log = (root / "projects" / "demo" / "reviews" / "decision-log.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("fixed: added the requested comparison", log)
            self.assertEqual(
                manifest["independent_audit"]["final_verdict"],
                "pass-with-conditions",
            )
            provenance = json.loads(
                (root / "projects" / "demo" / "state" / "output-provenance.json").read_text()
            )
            self.assertEqual(
                provenance["files"]["program/topic.md"]["family"], "openai"
            )

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

    def test_cycle_cannot_edit_while_awaiting_human_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"config").mkdir();(root/"projects"/"demo"/"state").mkdir(parents=True)
            (root/"config"/"stages.json").write_text(json.dumps({"stages":{"intake":{"gate":"G0"}}}),encoding="utf-8")
            (root/"projects"/"demo"/"state"/"run.json").write_text(json.dumps({"stage":"intake","gate":"G0","status":"awaiting_approval"}),encoding="utf-8")
            with patch.object(api_orchestrator,"ROOT",root),self.assertRaisesRegex(ValueError,"awaiting_work"):
                api_orchestrator.require_current_stage("demo","intake")


if __name__ == "__main__":
    unittest.main()
