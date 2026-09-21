from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import model_runtime
from scripts.ai_providers import ModelResult


class ModelRuntimeTests(unittest.TestCase):
    def test_exact_request_cache_avoids_a_second_paid_call(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "demo"
            (project / "state").mkdir(parents=True)
            (project / "state" / "run.json").write_text(json.dumps({"active_paper": "P01"}), encoding="utf-8")
            result = ModelResult(
                "uuapi-openai", "gpt-test", "answer", {"input_tokens": 100, "output_tokens": 20},
                "r1", "gpt-test", "openai_responses", "https://gateway.example/v1/responses", "uuapi",
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


if __name__ == "__main__":
    unittest.main()
