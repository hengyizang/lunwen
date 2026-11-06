"""Shared storage must retain each trial's original ledger and error boundary."""
import base64
import hashlib
import json
import unittest
from unittest.mock import patch

from scripts import argon_native_probe as probe, gateway_trial
from scripts import model_comparison as comparison, model_comparison_clarified as clarified
from scripts import writing_comparison as writing


def blob(value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    return {"sha": sha, "encoding": "base64", "content": base64.b64encode(raw).decode()}


class TrialStorageTests(unittest.TestCase):
    def test_single_file_trials_keep_their_write_scope_and_previous_cas(self):
        for module in (comparison, clarified, probe):
            with self.subTest(trial=module.FILE):
                state = module.CloudState("fixture-token")
                with patch.object(gateway_trial.CloudState, "read", return_value=({}, "a" * 40)):
                    state.load()
                state.branch = "unrelated-branch"
                value = {"entries": []}
                fresh = blob(value)
                with patch.object(state, "api", side_effect=[{"content": {"sha": fresh["sha"]}}, fresh]) as api:
                    state.save(value)
                path, body, method = api.call_args_list[0].args
                self.assertEqual((path, body["branch"], body["sha"], method),
                    ("contents/trial-state/" + module.FILE, comparison.STATE, "a" * 40, "PUT"))
                self.assertEqual(state.expected_sha, fresh["sha"])
                self.assertEqual(api.call_args_list[1].args, ("git/blobs/" + fresh["sha"],))

    def test_readback_mismatch_retains_original_error_type_and_cas(self):
        for module, error in ((comparison, comparison.ComparisonError),
                              (clarified, clarified.ClarifiedError), (probe, probe.ProbeError)):
            with self.subTest(trial=module.FILE):
                state = module.CloudState("fixture-token")
                with patch.object(gateway_trial.CloudState, "read", return_value=({}, "a" * 40)):
                    state.load()
                wrong = blob({"entries": ["unexpected"]})
                with patch.object(state, "api", side_effect=[{"content": {"sha": wrong["sha"]}}, wrong]):
                    with self.assertRaises(error):
                        state.save({"entries": []})
                self.assertEqual(state.expected_sha, "a" * 40)

    def test_writing_storage_preserves_nested_directory_and_named_file_cas(self):
        state = writing.State("fixture-token", branch="cloud-state/fixture", directory="nested/trial-state")
        previous = blob({"entries": []})
        loaded = [{"tree": [{"path": "nested", "sha": "tree1"}]},
                  {"tree": [{"path": "trial-state", "sha": "tree2"}]},
                  {"tree": [{"path": "fixture.json", "sha": previous["sha"]}]}, previous]
        with patch.object(state, "api", side_effect=loaded):
            self.assertEqual(state.load("fixture.json"), {"entries": []})
        value = {"entries": [{"call_id": "software-fixture"}]}
        fresh = blob(value)
        with patch.object(state, "api", side_effect=[{"content": {"sha": fresh["sha"]}}, fresh]) as api:
            state.save("fixture.json", value)
        path, body, _ = api.call_args_list[0].args
        self.assertEqual(path, "contents/nested/trial-state/fixture.json")
        self.assertEqual(body["branch"], "cloud-state/fixture")
        self.assertEqual(body["sha"], previous["sha"])
        self.assertEqual(state.expected["fixture.json"], fresh["sha"])
        with patch.object(state, "api") as api:
            with self.assertRaisesRegex(ValueError, "read state before writing"):
                state.save("unread.json", value)
            api.assert_not_called()
