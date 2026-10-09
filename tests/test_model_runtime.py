from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import model_runtime, model_spend
from scripts.ai_providers import ModelResult


class ModelRuntimeTests(unittest.TestCase):
    def test_exact_request_cache_avoids_a_second_paid_call(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            (project / "state").mkdir(parents=True)
            (project / "state" / "run.json").write_text(json.dumps({"active_paper": "P01"}), encoding="utf-8")
            result = ModelResult(
                "uuapi-openai", "gpt-test", "answer", {"input_tokens": 100, "output_tokens": 20},
                "r1", "gpt-test", "openai_responses", "https://gateway.example/v1/responses", "uuapi", completion_status="completed",
            )
            configuration = {"model": "gpt-test", "protocol": "openai_responses", "endpoint": "https://gateway.example/v1/responses"}
            with patch("scripts.model_runtime.ai_providers.configuration", return_value=configuration), patch("scripts.model_runtime.ai_providers.call", return_value=result) as provider_call:
                first = model_runtime.call(project, run_id="run-1", stage="writing-and-review", role="writer", provider="uuapi-openai", prompt="same prompt", max_output_tokens=100)
                second = model_runtime.call(project, run_id="run-2", stage="writing-and-review", role="writer", provider="uuapi-openai", prompt="same prompt", max_output_tokens=100)
            self.assertFalse(first.cache_hit)
            self.assertTrue(second.cache_hit)
            self.assertEqual(provider_call.call_count, 1)
            entries = model_runtime.ledger_entries(project)
            self.assertGreater(entries[0]["cost_cny"], 0)
            self.assertEqual(entries[1]["cost_cny"], 0)

    def test_hard_project_budget_blocks_before_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            (project / "state").mkdir(parents=True)
            configuration = {"model": "gpt-test", "protocol": "openai_responses", "endpoint": "https://gateway.example/v1/responses"}
            with patch.dict(os.environ, {"DR_OS_PROJECT_BUDGET_CNY": "0.000001"}, clear=False), patch("scripts.model_runtime.ai_providers.configuration", return_value=configuration), patch("scripts.model_runtime.ai_providers.call") as provider_call:
                with self.assertRaises(model_runtime.ModelBudgetError):
                    model_runtime.call(project, run_id="run", stage="intake", role="writer", provider="uuapi-openai", prompt="large prompt " * 100, max_output_tokens=1000)
            provider_call.assert_not_called()

    def test_cloud_calls_require_initial_approval_and_keep_cumulative_spend(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            model_spend.write(project, model_spend.initial())
            result = ModelResult("uuapi-openai", "gpt-test", "answer", {"input_tokens": 100, "output_tokens": 20},
                                 "r1", "gpt-test", "openai_responses", "https://gateway.example/v1/responses", "uuapi", completion_status="completed")
            configuration = {"model": "gpt-test", "protocol": "openai_responses", "endpoint": "https://gateway.example/v1/responses"}
            with patch.dict(os.environ, {"DR_OS_REQUIRE_MODEL_AUTH": "1", "DR_OS_PROJECT_BUDGET_CNY": "10000", "DR_OS_MODEL_PRICING_JSON": '{"gpt-test":{"input_per_million":2.2,"output_per_million":11}}'}, clear=False), \
                 patch("scripts.model_runtime.ai_providers.configuration", return_value=configuration), \
                 patch("scripts.model_runtime.ai_providers.call", return_value=result) as provider_call:
                with self.assertRaises(model_runtime.ModelBudgetError):
                    model_runtime.call(project, run_id="before", stage="intake", role="writer", provider="uuapi-openai", prompt="first", max_output_tokens=100)
                provider_call.assert_not_called()
                model_spend.grant(project, new_ceiling_cny=300, actor="Hengyi", run_id="approval-1")
                model_runtime.call(project, run_id="after", stage="intake", role="writer", provider="uuapi-openai", prompt="first", max_output_tokens=100)
                first = model_runtime.budget_status(project)
                self.assertEqual(first["project_hard_limit"], 300)
                self.assertGreater(first["spent"], 0)
                (project / "state" / "model-usage.jsonl").unlink()
                self.assertEqual(model_runtime.budget_status(project)["spent"], first["spent"])
                model_spend.grant(project, new_ceiling_cny=600, actor="Hengyi", run_id="approval-2")
                self.assertEqual(model_runtime.budget_status(project)["project_hard_limit"], 600)
                with self.assertRaises(model_spend.SpendControlError):
                    model_spend.grant(project, new_ceiling_cny=1200, actor="Hengyi", run_id="skip")

    def test_ambiguous_provider_failure_keeps_cumulative_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            model_spend.write(project, model_spend.initial())
            model_spend.grant(project, new_ceiling_cny=300, actor="Hengyi", run_id="approval-1")
            configuration = {"model": "gpt-test", "protocol": "openai_responses", "endpoint": "https://gateway.example/v1/responses"}
            with patch.dict(os.environ, {"DR_OS_REQUIRE_MODEL_AUTH": "1", "DR_OS_MODEL_PRICING_JSON": '{"gpt-test":{"input_per_million":2.2,"output_per_million":11}}'}, clear=False), \
                 patch("scripts.model_runtime.ai_providers.configuration", return_value=configuration), \
                 patch("scripts.model_runtime.ai_providers.call", side_effect=RuntimeError("timeout")):
                with self.assertRaises(RuntimeError):
                    model_runtime.call(project, run_id="timeout", stage="intake", role="writer", provider="uuapi-openai", prompt="first", max_output_tokens=100)
            status = model_runtime.budget_status(project)
            self.assertGreater(status["reserved"], 0)
            self.assertEqual(status["spent"], 0)
            receipt_id = next(iter(model_spend.read(project)["reservations"]))
            model_spend.reconcile(project, receipt_id, actual_cost_cny=0, actor="Hengyi", run_id="reconcile-1",
                                  evidence_note="Gateway billing report confirms no charge.")
            self.assertEqual(model_runtime.budget_status(project)["reserved"], 0)

    def test_missing_provider_usage_keeps_reservation_for_bill_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            model_spend.write(project, model_spend.initial())
            model_spend.grant(project, new_ceiling_cny=300, actor="Hengyi", run_id="approval-1")
            result = ModelResult("uuapi-openai", "gpt-test", "answer", {},
                                 "r1", "gpt-test", "openai_responses", "https://gateway.example/v1/responses", "uuapi", completion_status="completed")
            configuration = {"model": "gpt-test", "protocol": "openai_responses", "endpoint": "https://gateway.example/v1/responses"}
            with patch.dict(os.environ, {"DR_OS_REQUIRE_MODEL_AUTH": "1", "DR_OS_MODEL_PRICING_JSON": '{"gpt-test":{"input_per_million":2.2,"output_per_million":11}}'}, clear=False), \
                 patch("scripts.model_runtime.ai_providers.configuration", return_value=configuration), \
                 patch("scripts.model_runtime.ai_providers.call", return_value=result):
                model_runtime.call(project, run_id="missing-usage", stage="intake", role="writer", provider="uuapi-openai", prompt="first", max_output_tokens=100)
            status = model_runtime.budget_status(project)
            self.assertGreater(status["reserved"], 0)
            self.assertEqual(status["spent"], 0)

    def test_reported_overage_is_recorded_and_blocks_next_call(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            model_spend.write(project, model_spend.initial())
            model_spend.grant(project, new_ceiling_cny=300, actor="Hengyi", run_id="approval-1")
            receipt_id = model_spend.reserve(project, max_cost_cny=1, paper_id=None, paper_limit_cny=60, run_id="call")
            with self.assertRaises(model_spend.SpendControlError):
                model_spend.settle(project, receipt_id, actual_cost_cny=301)
            self.assertEqual(model_runtime.budget_status(project)["spent"], 301)
            with self.assertRaises(model_spend.SpendControlError):
                model_spend.reserve(project, max_cost_cny=1, paper_id=None, paper_limit_cny=60, run_id="next")

    def test_lower_paper_hard_limit_clamps_default_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            project.mkdir()
            with patch.dict(
                os.environ,
                {"DR_OS_PAPER_BUDGET_CNY": "20"},
                clear=True,
            ):
                status = model_runtime.budget_status(project, "P01")
            self.assertEqual(status["paper_hard_limit"], 20.0)
            self.assertEqual(status["paper_warning_limit"], 20.0)

    def test_usage_summary_groups_paid_calls_and_cache_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            ledger = project / "state" / "model-usage.jsonl"
            ledger.parent.mkdir(parents=True)
            entries = [
                {
                    "paper_id": "P01",
                    "provider": "uuapi-openai",
                    "model": "gpt-test",
                    "role": "persistent-writer",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cost_cny": 0.1,
                    "cache_hit": False,
                },
                {
                    "paper_id": "P01",
                    "provider": "uuapi-openai",
                    "model": "gpt-test",
                    "role": "persistent-writer",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_cny": 0,
                    "cache_hit": True,
                },
                {
                    "paper_id": "P02",
                    "provider": "uuapi-anthropic",
                    "model": "claude-test",
                    "role": "independent-critic-final",
                    "input_tokens": 80,
                    "output_tokens": 20,
                    "cost_cny": 0.05,
                    "cache_hit": False,
                },
            ]
            ledger.write_text(
                "".join(json.dumps(item) + "\n" for item in entries),
                encoding="utf-8",
            )
            summary = model_runtime.usage_summary(project, "P01")
            self.assertEqual(summary["paid_calls"], 1)
            self.assertEqual(summary["cache_hits"], 1)
            self.assertEqual(summary["input_tokens"], 100)
            self.assertEqual(summary["output_tokens"], 50)
            self.assertEqual(summary["cost_cny"], 0.1)
            self.assertEqual(len(summary["by_provider_model_role"]), 1)


if __name__ == "__main__":
    unittest.main()
