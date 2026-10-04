"""Infrastructure recovery must never replay paid requests or experiments."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_retry, cloud_job


class CloudRetryTests(unittest.TestCase):
    def invoke(self, command, results, operation="git-fetch"):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "retry.jsonl"
            with patch.object(cloud_retry.subprocess, "run", side_effect=results) as runner, \
                    patch.object(cloud_retry.time, "sleep") as sleep:
                result = cloud_retry.run(command, operation=operation, cwd=Path(directory), receipt=receipt)
            events = [json.loads(line) for line in receipt.read_text().splitlines()]
            return result, events, runner.call_count, sleep.call_args_list

    def test_transient_git_recovers_with_original_failure_receipt(self):
        bad = subprocess.CompletedProcess([], 128, "", "fatal: connection reset")
        good = subprocess.CompletedProcess([], 0, "restored", "")
        result, events, calls, sleeps = self.invoke(["git", "fetch", "origin", "refs/heads/cloud-state/my-phd"], [bad, good])
        self.assertEqual((result.returncode, result.stdout, calls), (0, "restored", 2))
        self.assertIn("connection reset", events[0]["diagnostic"])
        self.assertTrue(events[0]["retry"])
        self.assertEqual(sleeps[0].args, (2,))

    def test_retry_limit_and_backoff(self):
        bad = subprocess.CompletedProcess([], 128, "", "HTTP 503 service unavailable")
        result, events, calls, sleeps = self.invoke(["git", "fetch", "origin", "main"], [bad] * 3)
        self.assertEqual(result.returncode, 128)
        self.assertEqual(calls, 3)
        self.assertEqual([x.args for x in sleeps], [(2,), (8,)])
        self.assertEqual([x["retry"] for x in events], [True, True, False])

    def test_permanent_errors_are_not_retried(self):
        for message in ("non-fast-forward; connection reset", "permission denied", "authentication failed",
                        "No matching distribution found", "HASHES DO NOT MATCH", "ResolutionImpossible"):
            with self.subTest(message=message):
                _, _, calls, _ = self.invoke(["git", "fetch", "origin", "main"],
                    [subprocess.CompletedProcess([], 1, "", message)])
                self.assertEqual(calls, 1)

    def test_paid_calls_experiments_and_force_push_are_forbidden(self):
        for command, operation in (([sys.executable, "-m", "scripts.api_orchestrator"], "model-call"),
                                  ([sys.executable, "-m", "scripts.experiment_runner"], "experiment"),
                                  (["git", "push", "--force", "origin", "main"], "git-push"),
                                  (["git", "push", "origin", "+HEAD:main"], "git-push")):
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.invoke(command, [], operation)

    def test_pinned_install_is_repaired_without_package_upgrade(self):
        command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                   ".[figures,reader,research-quality,reference-tools]"]
        bad = subprocess.CompletedProcess([], 1, "", "ReadTimeout: read timed out")
        good = subprocess.CompletedProcess([], 0, "installed", "")
        _, events, calls, _ = self.invoke(command, [bad, good], "pinned-runtime-install")
        self.assertEqual(calls, 2)
        self.assertEqual(events[0]["operation"], "pinned-runtime-install")
        with self.assertRaises(ValueError):
            self.invoke(command + ["--upgrade"], [], "pinned-runtime-install")

    def test_timeout_preserves_partial_evidence_and_redacts_credentials(self):
        timeout = subprocess.TimeoutExpired([], 240, output=b"partial", stderr=b"token-a-long-secret")
        good = subprocess.CompletedProcess([], 0, "", "")
        with patch.dict(os.environ, {"GH_TOKEN": "token-a-long-secret"}):
            _, events, calls, _ = self.invoke(["git", "fetch", "origin", "main"], [timeout, good])
        self.assertEqual(calls, 2)
        self.assertIn("partial", events[0]["diagnostic"])
        self.assertNotIn("token-a-long-secret", json.dumps(events))

    def test_failed_model_entry_point_is_called_once(self):
        response = subprocess.CompletedProcess([], 1, "", "API response unavailable; reconcile billing")
        with patch.object(cloud_job.subprocess, "run", return_value=response) as runner:
            code, _ = cloud_job.run_command(["scripts/api_orchestrator.py", "cycle", "my-phd", "topic-intelligence"])
        self.assertEqual(code, 1)
        self.assertEqual(runner.call_count, 1)


if __name__ == "__main__":
    unittest.main()
