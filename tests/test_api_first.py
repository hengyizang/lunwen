import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator
from scripts.ai_providers import ModelResult, ProviderError


class ApiFirstTests(unittest.TestCase):
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

    def test_safe_target_protects_independent_review_files(self):
        for relative in (
            "reviews/codex/G1-fake-final.json",
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
            author_bundle = json.dumps(
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
                ModelResult("uuapi-anthropic", "claude-test", author_bundle, {}),
                ModelResult("uuapi-openai", "gpt-test", initial_audit, {}),
                ModelResult("uuapi-anthropic", "claude-test", remediation, {}),
                ModelResult("uuapi-openai", "gpt-test", final_audit, {}),
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
                    "",
                    "",
                )
            reviews = list((root / "projects" / "demo" / "reviews" / "codex").glob("*.json"))
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

    def test_cycle_requires_current_initialized_stage(self):
        with self.assertRaises(ValueError):
            api_orchestrator.run_cycle(
                "not-initialized",
                "intake",
                "uuapi-anthropic",
                "uuapi-openai",
                "",
                "",
            )


if __name__ == "__main__":
    unittest.main()
