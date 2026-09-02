from __future__ import annotations

import sys
import time
import unittest

from scripts.dashboard import (
    JobManager,
    SessionConfig,
    build_command,
    update_config,
)


class DashboardTests(unittest.TestCase):
    def test_public_configuration_never_contains_api_key(self) -> None:
        config = SessionConfig(api_key="super-secret", base_url="https://gateway.example", anthropic_model="claude", openai_model="gpt")
        public = config.public()
        self.assertTrue(public["key_configured"])
        self.assertNotIn("super-secret", str(public))
        self.assertNotIn("api_key", public)

    def test_configuration_requires_https_and_keeps_blank_key(self) -> None:
        config = SessionConfig(api_key="existing")
        with self.assertRaises(ValueError):
            update_config(config, {"base_url": "http://unsafe.example"})
        update_config(
            config,
            {
                "api_key": "",
                "base_url": "https://gateway.example/v1/",
                "anthropic_model": "claude-model",
                "openai_model": "gpt-model",
                "strict_model_id": True,
            },
        )
        self.assertEqual(config.api_key, "existing")
        self.assertEqual(config.base_url, "https://gateway.example/v1")

    def test_job_log_redacts_session_secrets(self) -> None:
        manager = JobManager(SessionConfig(api_key="secret-token", tavily_key="tavily-secret"))
        value = manager.redact("Authorization: Bearer secret-token api_key=tavily-secret")
        self.assertNotIn("secret-token", value)
        self.assertNotIn("tavily-secret", value)

    def test_queued_job_can_be_cancelled_before_process_start(self) -> None:
        manager = JobManager(SessionConfig())
        for _ in range(3):
            manager.capacity.acquire()
        try:
            job = manager.start(
                "test",
                "queued test",
                [sys.executable, "-c", "raise SystemExit(99)"],
                None,
            )
            manager.cancel(job.job_id)
        finally:
            for _ in range(3):
                manager.capacity.release()
        deadline = time.monotonic() + 2
        while job.status == "queued" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(job.status, "cancelled")
        self.assertIsNone(job.return_code)

    def test_start_command_is_argument_safe_and_role_separated(self) -> None:
        command, label, project = build_command(
            "start",
            {"project": "dashboard-new-test", "context": "No lab; public data only."},
        )
        self.assertEqual(command[:3], ["bash", "scripts/start.sh", "dashboard-new-test"])
        self.assertEqual(command[-1], "No lab; public data only.")
        self.assertEqual(project, "dashboard-new-test")
        self.assertIn("G0", label)

    def test_project_slug_rejects_shell_metacharacters(self) -> None:
        with self.assertRaises(ValueError):
            build_command("start", {"project": "bad;touch-x", "context": "test"})


if __name__ == "__main__":
    unittest.main()
