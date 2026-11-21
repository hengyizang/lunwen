"""Core validation remains useful without requiring every optional integration."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import validate_repo as validation


INTEGRATION_CHECKS = (
    "scripts.research_methods.installation_errors",
    "scripts.ccfa_runtime.installation_errors",
    "scripts.research_toolkit.installation_errors",
    "scripts.literaturectl.installation_errors",
)


class RepositoryValidationTests(unittest.TestCase):
    def test_default_validation_does_not_require_optional_installations(self):
        with ExitStack() as stack, redirect_stdout(io.StringIO()):
            for name in INTEGRATION_CHECKS:
                stack.enter_context(patch(name, side_effect=AssertionError("Unrequested installation check")))
            self.assertEqual(validation.main([]), 0)

    def test_explicit_integration_validation_reports_missing_resources(self):
        output = io.StringIO()
        with ExitStack() as stack, redirect_stderr(output):
            checks = [stack.enter_context(patch(name, return_value=[])) for name in INTEGRATION_CHECKS]
            checks[1].return_value = ["Selected optional resource is missing"]
            self.assertEqual(validation.main(["--integrations"]), 2)
            for check in checks:
                check.assert_called_once_with(validation.ROOT)
        self.assertIn("Selected optional resource is missing", output.getvalue())

    def test_custom_task_labels_do_not_require_a_fixed_stage_portfolio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "stages.json"
            source.write_text(json.dumps({"stages": {"replication-study": {
                "author_task": "Resolve the observed discrepancy using the actual data."}}}))
            errors = []
            with patch.object(validation, "ROOT", root):
                validation.validate_stage_config(source, errors)
            self.assertEqual(errors, [])

    def test_legacy_label_mismatch_and_missing_task_are_still_diagnosed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "stages.json"
            source.write_text(json.dumps({"stages": {
                "experiment-design": {"gate": "G0", "author_task": "Design the comparison"},
                "analysis": {},
            }}))
            errors = []
            with patch.object(validation, "ROOT", root):
                validation.validate_stage_config(source, errors)
            self.assertEqual(len(errors), 2)
            self.assertTrue(any("legacy label" in error for error in errors))
            self.assertTrue(any("analysis needs author_task" in error for error in errors))
