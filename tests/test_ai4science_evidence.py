from __future__ import annotations

import tempfile
import unittest
import hashlib
import json
import os
import sys
import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import ai4science_evidence as adapter, ai_providers, model_runtime, model_spend, relay_billing
from scripts.ai4science_evidence import (
    AI4ScienceEvidenceError,
    execute_paperqa,
    execute_tooluniverse,
    read_ledger,
    record,
    run_process,
    validate,
)


class AI4ScienceEvidenceTests(unittest.TestCase):
    @staticmethod
    def completed(stdout: bytes, *, exit_code: int = 0, error: str | None = None):
        return {
            "started_at": "2026-09-19T00:00:00+00:00",
            "completed_at": "2026-09-19T00:00:01+00:00",
            "runtime_seconds": 1.0,
            "status": "succeeded" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "timed_out": False,
            "error": error,
            "stdout_bytes": stdout,
            "stderr_bytes": b"",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "stdout_full_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_full_sha256": hashlib.sha256(b"").hexdigest(),
        }

    def test_real_local_output_is_versioned_hash_bound_and_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            (project / "evidence").mkdir(parents=True)
            source = project / "evidence" / "papers.csv"
            output = project / "evidence" / "paperqa-answer.json"
            source.write_text("doi,title\n10.1000/example,Example\n", encoding="utf-8")
            output.write_text('{"answer":"requires primary-source review"}', encoding="utf-8")
            with patch("scripts.ai4science_evidence.metadata.version", return_value="2026.08.12"):
                receipt = record(
                    project,
                    "paperqa2",
                    "evidence/paperqa-answer.json",
                    ["evidence/papers.csv"],
                    "Researcher",
                    "Contradiction scan over the human-owned corpus.",
                )
            self.assertTrue(receipt["advisory_only"])
            self.assertEqual(validate(project, [receipt]), [])
            output.write_text("changed", encoding="utf-8")
            self.assertTrue(any("stale" in item for item in validate(project, [receipt])))

    def test_public_paperqa_cli_rejects_legacy_settings_and_missing_or_empty_budget_before_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            corpus = project / "papers"
            corpus.mkdir(parents=True)
            (corpus / "paper.md").write_text("The pilot measured 24 adults.\n", encoding="utf-8")
            argv = ["paperqa", "--project", "demo", "--corpus", "papers", "--question", "How many adults?",
                    "--actor", "Fixture Owner", "--purpose", "Synthetic boundary check"]
            with patch.object(adapter, "PROJECTS_ROOT", Path(directory)), \
                    patch.dict(os.environ, {"OPENAI_API_KEY": "raw-provider-key", "DR_OS_ROUTING_PROFILE": "production", "GITHUB_ACTIONS": "true"}, clear=True), \
                    patch.object(adapter, "run_process") as process, patch.object(ai_providers.urllib.request, "build_opener") as post:
                for settings, expected in (([], "standalone pqa"), (["--settings", "native"], "authorization state is missing")):
                    with self.subTest(settings=settings), contextlib.redirect_stderr(io.StringIO()) as error:
                        self.assertEqual(adapter.main(argv + settings), 2)
                        self.assertIn(expected, error.getvalue())
                model_spend.write(project, model_spend.initial())
                with contextlib.redirect_stderr(io.StringIO()) as error:
                    self.assertEqual(adapter.main(argv + ["--settings", "native"]), 2)
                    self.assertIn("cumulative spending ceiling", error.getvalue())
                process.assert_not_called()
                post.assert_not_called()
            self.assertFalse((project / "evidence").exists())

    def test_native_compatibility_uses_real_runtime_reservation_identity_and_source_receipt(self) -> None:
        for reported_model in ("gpt-6.1-sol", "wrong-model"):
            with self.subTest(reported_model=reported_model), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "demo"
                source = project / "papers" / "paper.md"
                source.parent.mkdir(parents=True)
                source.write_text("The pilot measured 24 adults.\n", encoding="utf-8")
                model_spend.write(project, model_spend.initial())
                model_spend.grant(project, new_ceiling_cny=300, actor="Fixture Owner", run_id="fixture")
                answer = {"answer": "The pilot measured 24 adults.", "abstain": False,
                    "statements": [{"text": "The pilot measured 24 adults.", "citation_indices": [0]}],
                    "citations": [{"source_id": "SRC001", "locator": "text, lines 1-1", "quote": "The pilot measured 24 adults."}]}
                body = {"id": "synthetic-request", "model": reported_model, "status": "completed",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}],
                    "usage": {"input_tokens": 100, "output_tokens": 30}}
                def response(request, *, timeout):
                    self.assertGreaterEqual(sync.call_count, 1)
                    reservations = list(model_spend.read(project)["reservations"].values())
                    self.assertEqual(len(reservations), 1)
                    self.assertEqual(reservations[0]["transport"]["model"], "gpt-6.1-sol")
                    self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-controlled-route-key")
                    return contextlib.nullcontext(SimpleNamespace(read=lambda limit: json.dumps(body).encode()))
                with patch.dict(os.environ, {"DR_OS_ROUTING_PROFILE": "production", "GITHUB_ACTIONS": "true",
                        "DR_OS_CHEAPAI_GPT_PRO_KEY": "synthetic-controlled-route-key", "OPENAI_API_KEY": "raw-provider-key"}, clear=True), \
                        patch("scripts.cloud_checkpoint.sync_billing") as sync, \
                        patch.object(relay_billing, "read_meter", side_effect=relay_billing.BillingReconciliationError("fixture meter unavailable")), \
                        patch.object(ai_providers.urllib.request, "build_opener", return_value=SimpleNamespace(open=response)) as post, \
                        patch.object(adapter, "run_process") as process:
                    if reported_model == "wrong-model":
                        with self.assertRaisesRegex(AI4ScienceEvidenceError, "model ID missing or mismatched"):
                            execute_paperqa(project, "papers", "How many adults were measured?", "Fixture Owner", "Synthetic reading", settings="native")
                        self.assertEqual(len(model_spend.read(project)["reservations"]), 1)
                    else:
                        result = execute_paperqa(project, "papers", "How many adults were measured?", "Fixture Owner", "Synthetic reading", settings="native")
                        self.assertTrue(result["not_paperqa2_sdk"])
                        self.assertFalse(result["legacy_pqa_agent_called"])
                        self.assertEqual(result["receipt"]["tool"], "native-source-qa")
                        self.assertEqual(validate(project, [result["receipt"]]), [])
                        self.assertNotIn("raw-provider-key", json.dumps(result))
                        self.assertNotIn("synthetic-controlled-route-key", json.dumps(result))
                        report = json.loads((project / result["output"]).read_text())
                        self.assertTrue(report["not_paperqa2_sdk"])
                        self.assertEqual(report["model_receipt"]["reported_model"], "gpt-6.1-sol")
                        self.assertGreater(model_spend.read(project)["spent_cny"], 0)
                        self.assertEqual(model_spend.read(project)["reservations"], {})
                    post.assert_called_once()
                    self.assertGreaterEqual(sync.call_count, 1)
                    process.assert_not_called()
                self.assertEqual(len(model_runtime.ledger_entries(project)), 1)

    def test_custom_paperqa_agent_and_timeout_cannot_be_silently_reinterpreted(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(adapter, "run_process") as process, \
                patch.object(adapter.paper_qa, "answer") as native:
            for options in ({"settings": "custom"}, {"settings": "native", "executable": "/fixture/pqa"},
                            {"settings": "native", "timeout_seconds": 60}):
                with self.subTest(options=options), self.assertRaisesRegex(AI4ScienceEvidenceError, "literaturectl request"):
                    execute_paperqa(Path(directory), "papers", "Question?", "Fixture Owner", "Synthetic boundary", **options)
            process.assert_not_called()
            native.assert_not_called()

    def test_tooluniverse_adapter_uses_exact_request_file_and_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            request = project / "requests" / "uniprot.json"
            request.parent.mkdir(parents=True)
            request.write_text(
                json.dumps(
                    {
                        "name": "UniProt_get_entry_by_accession",
                        "arguments": {"accession": "P12345"},
                    }
                ),
                encoding="utf-8",
            )
            payload = b'{"result":{"primaryAccession":"P12345"},"tool":"UniProt_get_entry_by_accession"}\n'
            with (
                patch("scripts.ai4science_evidence.metadata.version", return_value="1.5.1"),
                patch("scripts.ai4science_evidence.run_process", return_value=self.completed(payload)) as invoke,
                patch.dict(os.environ, {"OPENAI_API_KEY": "never-pass-model-secret", "CUSTOM_PROVIDER_TOKEN": "never-pass-custom-secret", "HTTPS_PROXY": "https://proxy.example", "REQUESTS_CA_BUNDLE": "/tmp/trusted-ca.pem"}),
            ):
                receipt = execute_tooluniverse(
                    project,
                    "requests/uniprot.json",
                    "Researcher",
                    "Retrieve an advisory public database record.",
                )
            self.assertEqual(receipt["status"], "succeeded")
            self.assertEqual(receipt["inputs"][0]["path"], "requests/uniprot.json")
            self.assertEqual(receipt["cost_accounting"]["model_calls"], 0)
            self.assertEqual(receipt["cost_accounting"]["public_api_cost_cny"], 0)
            environment = invoke.call_args.kwargs["environment"]
            self.assertNotIn("OPENAI_API_KEY", environment)
            self.assertNotIn("CUSTOM_PROVIDER_TOKEN", environment)
            self.assertEqual(environment["HTTPS_PROXY"], "https://proxy.example")
            self.assertEqual(environment["REQUESTS_CA_BUNDLE"], "/tmp/trusted-ca.pem")
            self.assertEqual(receipt["execution"]["secret_environment_names"], [])
            output = project / receipt["output"]["path"]
            self.assertEqual(json.loads(output.read_text())["result"]["primaryAccession"], "P12345")
            self.assertEqual(validate(project, [receipt]), [])

    def test_failed_execution_is_preserved_but_not_misreported_as_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            request = project / "request.json"
            request.parent.mkdir(parents=True)
            request.write_text('{"name":"UniProt_get_entry_by_accession","arguments":{"accession":"P12345"}}', encoding="utf-8")
            with (
                patch("scripts.ai4science_evidence.metadata.version", return_value="1.5.1"),
                patch(
                    "scripts.ai4science_evidence.run_process",
                    return_value=self.completed(b'{"status":"failed","http_attempts":[{"http_status":503}]}', exit_code=1, error="upstream failed"),
                ),
            ):
                with self.assertRaises(AI4ScienceEvidenceError):
                    execute_tooluniverse(
                        project,
                        "request.json",
                        "Researcher",
                        "Record a failed advisory call.",
                    )
            ledger = read_ledger(project / "evidence" / "ai4science-ledger.jsonl")
            self.assertEqual(ledger[0]["status"], "failed")
            self.assertIsNone(ledger[0]["output"])
            self.assertEqual(ledger[0]["cost_accounting"]["http_attempts"], [{"http_status": 503}])
            self.assertEqual(validate(project, ledger), [])

    def test_unreviewed_tools_and_versions_never_start_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            request = project / "request.json"
            for value, version in (({"name": "list_tools", "arguments": {}}, "1.5.1"),
                ({"name": "UniProt_get_entry_by_accession", "arguments": {"accession": "P12345"}}, "1.5.2")):
                request.write_text(json.dumps(value))
                with patch("scripts.ai4science_evidence.metadata.version", return_value=version), patch("scripts.ai4science_evidence.run_process") as invoke:
                    with self.assertRaises(AI4ScienceEvidenceError):
                        execute_tooluniverse(project, "request.json", "Researcher", "Review")
                    invoke.assert_not_called()

    def test_tooluniverse_request_mutation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            request = project / "request.json"
            request.write_text('{"name":"UniProt_get_entry_by_accession","arguments":{"accession":"P12345"}}')
            def mutate(*args, **kwargs):
                request.write_text('{"name":"UniProt_get_entry_by_accession","arguments":{"accession":"P04637"}}')
                return self.completed(b'{"result":{"primaryAccession":"P12345"}}')
            with patch("scripts.ai4science_evidence.metadata.version", return_value="1.5.1"), patch("scripts.ai4science_evidence.run_process", side_effect=mutate):
                with self.assertRaisesRegex(AI4ScienceEvidenceError, "input files changed"):
                    execute_tooluniverse(project, "request.json", "Researcher", "Review")
            self.assertEqual(read_ledger(project / "evidence/ai4science-ledger.jsonl")[0]["status"], "failed")

    def test_process_runner_uses_argv_without_shell_and_captures_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_process(
                [sys.executable, "-c", "print('adapter-smoke')"],
                cwd=Path(directory),
                environment={"PYTHONIOENCODING": "utf-8"},
                timeout_seconds=10,
            )
            self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["stdout_bytes"], ("adapter-smoke" + os.linesep).encode())
