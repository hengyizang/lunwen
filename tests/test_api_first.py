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
        with self.assertRaises(ValueError):
            api_orchestrator.safe_target("demo", "../escape.txt")

    def test_safe_target_rejects_state(self):
        with self.assertRaises(ValueError):
            api_orchestrator.safe_target("demo", "state/run.json")

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


if __name__ == "__main__":
    unittest.main()
