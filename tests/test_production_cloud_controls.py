"""Production wiring must not grant money, continuous execution or human gates."""
from __future__ import annotations

import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ai_providers, cloud_checkpoint, cloud_continuation, cloud_job, model_spend, researchctl
from tests.test_cloud_continuation import ContinuationTests

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_KEYS = {
    "DR_OS_CHEAPAI_GPT_PRO_KEY", "DR_OS_CHEAPAI_GPT_DISCOUNT_KEY",
    "DR_OS_CODEKEY_KIRO_ENTERPRISE_KEY", "DR_OS_CODEKEY_DEEPSEEK_KEY", "DR_OS_CODEKEY_GEMINI_KEY",
}


def production_environment():
    return {"DR_OS_ROUTING_PROFILE": "production", **{
        name: f"synthetic-production-{index}-not-a-real-credential"
        for index, name in enumerate(sorted(PRODUCTION_KEYS))
    }}


class ProductionConfigurationTests(unittest.TestCase):
    def test_five_production_credentials_need_no_uuapi_or_old_global_models(self):
        env = production_environment()
        with patch.dict(os.environ, env, clear=True), patch("scripts.ai_providers.urllib.request.urlopen") as network:
            self.assertEqual(cloud_continuation.configuration_errors(env), [])
            network.assert_not_called()
        self.assertEqual({spec["key_setting"] for spec in ai_providers.PRODUCTION_PROVIDERS.values()}, PRODUCTION_KEYS)
        self.assertFalse(any(name.startswith("UUAPI") for name in env))

    def test_each_missing_production_credential_fails_without_disclosing_other_credentials(self):
        for name in sorted(PRODUCTION_KEYS):
            env = production_environment(); env.pop(name)
            with self.subTest(name=name), patch.dict(os.environ, env, clear=True):
                errors = cloud_continuation.configuration_errors(env)
                self.assertTrue(errors)
                self.assertIn(name, " ".join(errors))
                self.assertNotIn("UUAPI", " ".join(errors))
                for value in env.values():
                    if value.startswith("synthetic-production-"):
                        self.assertNotIn(value, " ".join(errors))

    def test_exact_production_quotes_cannot_be_replaced_by_empty_or_legacy_prices(self):
        for price in ("{}", '{"gpt-6.1-sol":{"input_per_million":1,"output_per_million":1}}'):
            env = {**production_environment(), "DR_OS_MODEL_PRICING_JSON": price}
            with self.subTest(price=price), patch.dict(os.environ, env, clear=True):
                self.assertTrue(cloud_continuation.configuration_errors(env))

    def test_cloud_workflows_use_production_secrets_and_do_not_start_automatic_research_by_default(self):
        for name in ("cloud-research.yml", "research-continuation.yml"):
            text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertIn("DR_OS_ROUTING_PROFILE: production", text)
                for key in PRODUCTION_KEYS:
                    self.assertIn(f"{key}: ${{{{ secrets.{key} }}}}", text)
                self.assertNotIn("UUAPI_", text)
                automatic = [line for line in text.splitlines() if "DR_OS_AUTOMATIC_RESEARCH_ENABLED:" in line]
                self.assertEqual(len(automatic), 1)
                self.assertIn("vars.DR_OS_AUTOMATIC_RESEARCH_ENABLED", automatic[0])
                self.assertNotIn("||", automatic[0])
                self.assertNotIn("authorize_budget", text)


class ProductionContinuationTests(unittest.TestCase):
    def setUp(self):
        # Reuse only the existing temporary owner-confirmed G0 fixture setup;
        # inherit none of its legacy UUAPI test methods.
        ContinuationTests.setUp(self)
        self.env = production_environment()
        self.environment = patch.dict(os.environ, self.env, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        ContinuationTests.tearDown(self)

    def test_configured_production_is_idle_until_automatic_flag_is_explicitly_true(self):
        for value in (None, "", "false", "TRUE", "1"):
            env = dict(self.env)
            if value is not None:
                env["DR_OS_AUTOMATIC_RESEARCH_ENABLED"] = value
            with self.subTest(value=value), patch("scripts.model_runtime.call") as paid_call:
                decision = cloud_continuation.evaluate("my-phd", env)
                self.assertFalse(decision["should_run"])
                self.assertEqual(decision["reason"], "production_configured_automatic_research_not_started")
                paid_call.assert_not_called()
        self.assertTrue(cloud_continuation.evaluate("my-phd", {**self.env, "DR_OS_AUTOMATIC_RESEARCH_ENABLED": "true"})["should_run"])

    def test_startup_is_read_only_and_retains_original_300_budget_and_24_hour_confirmation(self):
        control = model_spend.read(self.project, required=True)
        control["spent_cny"] = 12.5; control["paper_spent_cny"] = {"P01": 12.5}
        model_spend.write(self.project, control)
        before = {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()}
        with patch("scripts.model_runtime.call") as paid_call, patch("scripts.model_spend.grant") as grant, \
                patch("scripts.production_readiness.catalog") as catalog, patch("scripts.ai_providers.urllib.request.urlopen") as network:
            for _ in range(2):
                report = cloud_continuation.startup_report("my-phd", self.env)
                self.assertTrue(report["configuration_ready"])
                self.assertFalse(report["ready_to_continue"])
                self.assertEqual(report["paid_calls"], 0)
                self.assertFalse(report["provider_authentication_verified"])
                self.assertFalse(report["scientific_completion_verified"])
                self.assertEqual(report["budget"], {"authorized_ceiling_cny": 300, "spent_cny": 12.5, "reserved_cny": 0, "remaining_cny": 287.5})
                self.assertEqual({row["provider"] for row in report["providers"]}, set(ai_providers.PRODUCTION_PROVIDERS))
                for key in PRODUCTION_KEYS:
                    self.assertNotIn(self.env[key], json.dumps(report))
            paid_call.assert_not_called(); grant.assert_not_called(); catalog.assert_not_called(); network.assert_not_called()
        self.assertEqual(before, {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()})
        policy = json.loads((self.project / cloud_continuation.POLICY).read_text(encoding="utf-8"))
        self.assertEqual(policy["system_execution_hours_per_day"], 24)
        self.assertEqual(policy["resume_interval_minutes"], 15)
        self.assertEqual(len(model_spend.read(self.project)["authorization_events"]), 1)
        self.assertEqual(researchctl.load_state("my-phd")["approved_gates"], ["G0"])

    def test_automatic_flag_cannot_replace_original_human_continuation_or_gate_confirmation(self):
        env = {**self.env, "DR_OS_AUTOMATIC_RESEARCH_ENABLED": "true"}
        policy = dict(self.policy); policy["enabled"] = False
        researchctl.write_json(self.project / cloud_continuation.POLICY, policy)
        self.assertEqual(cloud_continuation.evaluate("my-phd", env)["reason"], "not_enabled")
        researchctl.write_json(self.project / cloud_continuation.POLICY, self.policy)
        state = researchctl.load_state("my-phd"); state["status"] = "awaiting_approval"
        researchctl.write_json(self.project / "state/run.json", state)
        self.assertEqual(cloud_continuation.evaluate("my-phd", env)["reason"], "human_gate_pending")
        self.assertEqual(model_spend.read(self.project)["authorized_ceiling_cny"], 300)

    def test_existing_unknown_charge_reservation_is_retained_and_blocks_restart(self):
        reservation = model_spend.reserve(self.project, max_cost_cny=5, paper_id="P01", paper_limit_cny=60, run_id="ambiguous-before-production")
        before = (self.project / model_spend.FILE).read_bytes()
        env = {**self.env, "DR_OS_AUTOMATIC_RESEARCH_ENABLED": "true"}
        report = cloud_continuation.startup_report("my-phd", env)
        self.assertEqual(report["continuation"]["reason"], "billing_reconciliation_pending")
        self.assertEqual(report["budget"]["reserved_cny"], 5)
        self.assertEqual(before, (self.project / model_spend.FILE).read_bytes())
        self.assertIn(reservation, model_spend.read(self.project)["reservations"])

    def test_missing_budget_is_not_recreated_by_startup_or_complete_configuration(self):
        (self.project / model_spend.FILE).unlink()
        with patch("scripts.model_spend.grant") as grant, patch("scripts.model_runtime.call") as paid_call:
            report = cloud_continuation.startup_report("my-phd", self.env)
            self.assertTrue(report["configuration_ready"])
            self.assertFalse(report["ready_to_continue"])
            self.assertEqual(report["continuation"]["reason"], "project_control_validation_failed")
            grant.assert_not_called(); paid_call.assert_not_called()
        self.assertFalse((self.project / model_spend.FILE).exists())

    def test_cycle_command_selects_production_roles_without_mutating_budget_or_policy(self):
        before = [(self.project / path).read_bytes() for path in (model_spend.FILE, cloud_continuation.POLICY, Path("state/run.json"))]
        with patch.object(cloud_job, "ROOT", self.root):
            command = cloud_job.cycle_command({"action": "cycle"}, "my-phd")
        self.assertIn("cheapai-gpt-pro", command)
        self.assertIn("codekey-kiro-enterprise", command)
        self.assertFalse(any("uuapi" in item for item in command))
        self.assertEqual(os.environ["DR_OS_REQUIRE_MODEL_AUTH"], "1")
        self.assertEqual(os.environ["DR_OS_REQUIRE_REMOTE_RESERVATION"], "1")
        self.assertEqual(before, [(self.project / path).read_bytes() for path in (model_spend.FILE, cloud_continuation.POLICY, Path("state/run.json"))])


class ProductionSecretContainmentTests(unittest.TestCase):
    def test_every_new_model_key_blocks_checkpoint_content_without_exposure(self):
        self.assertTrue(PRODUCTION_KEYS <= cloud_checkpoint.SECRET_NAMES)
        env = production_environment()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, env, clear=True):
            project = Path(directory); path = project / "reports" / "receipt.md"; path.parent.mkdir()
            for name in sorted(PRODUCTION_KEYS):
                path.write_text("receipt " + env[name], encoding="utf-8")
                with self.subTest(name=name), self.assertRaises(cloud_checkpoint.CheckpointError) as error:
                    cloud_checkpoint.check_file(path, project)
                self.assertNotIn(env[name], str(error.exception))

    def test_credential_crossing_checkpoint_read_chunk_boundary_is_rejected(self):
        env = production_environment(); value = env[sorted(PRODUCTION_KEYS)[0]].encode()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, env, clear=True):
            project = Path(directory); path = project / "boundary.json"
            path.write_bytes(b"x" * (1024 * 1024 - len(value) // 2) + value + b"end")
            with self.assertRaises(cloud_checkpoint.CheckpointError):
                cloud_checkpoint.check_file(path, project)

    def test_cloud_subprocess_receipt_redacts_all_five_new_keys(self):
        env = production_environment(); stdout = " ".join(env[name] for name in sorted(PRODUCTION_KEYS))
        result = types.SimpleNamespace(returncode=0, stdout=stdout, stderr="normal diagnostic")
        with patch.dict(os.environ, env, clear=True), patch.object(cloud_job.subprocess, "run", return_value=result):
            code, output = cloud_job.run_command(["scripts/production_readiness.py"])
        self.assertEqual(code, 0)
        self.assertIn("normal diagnostic", output)
        self.assertEqual(output.count("[REDACTED]"), 5)
        for name in PRODUCTION_KEYS:
            self.assertNotIn(env[name], output)


if __name__ == "__main__":
    unittest.main()
