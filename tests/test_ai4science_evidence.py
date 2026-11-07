from __future__ import annotations

import tempfile
import unittest
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

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

    def test_paperqa_adapter_executes_and_never_records_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            corpus = project / "papers"
            corpus.mkdir(parents=True)
            (corpus / "paper.pdf").write_bytes(b"real local corpus bytes")
            with (
                patch("scripts.ai4science_evidence.metadata.version", return_value="2026.08.12"),
                patch("scripts.ai4science_evidence.run_process", return_value=self.completed(b"Grounded answer [1]\n")) as invoke,
                patch.dict(os.environ, {"OPENAI_API_KEY": "do-not-record-this-value"}),
            ):
                receipt = execute_paperqa(
                    project,
                    "papers",
                    "What evidence contradicts the proposed mechanism?",
                    "Researcher",
                    "Contradiction scan over a human-owned corpus.",
                    executable="/opt/venv/bin/pqa",
                )
            self.assertEqual(receipt["schema_version"], "1.1")
            self.assertEqual(receipt["status"], "succeeded")
            self.assertEqual(receipt["execution"]["argv"][0], "pqa")
            self.assertIn("OPENAI_API_KEY", receipt["execution"]["secret_environment_names"])
            self.assertNotIn("do-not-record-this-value", json.dumps(receipt))
            self.assertEqual(validate(project, [receipt]), [])
            self.assertEqual(invoke.call_args.kwargs["cwd"], corpus)

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
