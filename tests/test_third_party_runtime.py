"""Regression tests for the owner-authorized third-party runtime registry."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import third_party_runtime as t  # noqa: E402

ORIGINAL = (t.ROOT, t.REGISTRY, t.REPORTS)
REGISTRY_TEMPLATE = Path(__file__).resolve().parents[1] / "integrations" / "third-party-runtime.json"


def ns(**kwargs):
    return argparse.Namespace(**kwargs)


class ThirdPartyRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="third-party-runtime-test-"))
        t.ROOT = self.tmp
        t.REGISTRY = self.tmp / "integrations" / "third-party-runtime.json"
        t.REPORTS = self.tmp / "reports"
        t.REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        t.REGISTRY.write_text(REGISTRY_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")

    def tearDown(self):
        t.ROOT, t.REGISTRY, t.REPORTS = ORIGINAL
        shutil.rmtree(self.tmp, ignore_errors=True)

    def register(self, identity="demo-tool", **overrides):
        values = dict(id=identity, repo="https://github.com/example/demo", ref="main",
                      tier="local-readonly", license="MIT", license_url="", access_date="",
                      capability=["search"], endpoint=[], note="test")
        values.update(overrides)
        return t.cmd_register(ns(**values))

    def test_register_verify_and_authorization_deployment_separation(self):
        self.assertEqual(self.register(), 0)
        self.assertEqual(t.cmd_verify(ns()), 0)
        row = t._load()["tools"][0]
        self.assertTrue(row["deployment_authorized"])
        self.assertFalse(row["standalone_runtime_deployed"])
        self.assertEqual(t.cmd_mark_deployed(ns(id="demo-tool", deployed=True)), 0)
        self.assertTrue(t._load()["tools"][0]["standalone_runtime_deployed"])
        self.assertEqual(t.cmd_mark_deployed(ns(id="demo-tool", deployed=False)), 0)
        self.assertFalse(t._load()["tools"][0]["standalone_runtime_deployed"])

    def test_register_rejects_duplicate_bad_url_and_bad_tier(self):
        self.register()
        with self.assertRaises(ValueError):
            self.register()
        with self.assertRaises(ValueError):
            self.register(identity="other", repo="http://example.com/demo")
        with self.assertRaises(ValueError):
            self.register(identity="other", tier="unreviewed")

    def test_dry_run_has_no_receipt_and_execute_is_advisory(self):
        self.register()
        argv = ["--", sys.executable, "-c", "print('ok')"]
        self.assertEqual(t.cmd_run(ns(id="demo-tool", cwd="", timeout=30,
                                      execute=False, argv=argv)), 0)
        self.assertFalse((t.REPORTS / "receipts").exists())
        self.assertEqual(t.cmd_run(ns(id="demo-tool", cwd="", timeout=30,
                                      execute=True, argv=argv)), 0)
        receipts = list((t.REPORTS / "receipts").glob("run-*.json"))
        self.assertEqual(len(receipts), 1)
        body = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(body["exit_code"], 0)
        self.assertTrue(body["advisory_only"])
        self.assertFalse(body["gate_authority"])
        self.assertFalse(body["registered_experiment"])
        self.assertFalse(body["scientific_evidence"])
        self.assertNotIn("API_KEY", " ".join(body["env_keys"]))

    def test_bind_output_hashes_file_and_refuses_escape(self):
        self.register()
        target = self.tmp / "result.json"
        target.write_text('{"value": 1}\n', encoding="utf-8")
        self.assertEqual(t.cmd_bind_output(ns(id="demo-tool", file="result.json")), 0)
        receipts = list((t.REPORTS / "receipts").glob("output-*.json"))
        self.assertEqual(len(receipts), 1)
        body = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(body["sha256"], t._sha_file(target))
        self.assertTrue(body["advisory_only"])
        with self.assertRaises(ValueError):
            t.cmd_bind_output(ns(id="demo-tool", file="../outside.json"))

    def test_registry_starts_empty_in_repository(self):
        self.assertEqual(t._load()["tools"], [])
        self.assertEqual(t._load()["owner_decision"]["status"], "active")
        self.assertEqual(t._load()["guardrails"]["approves_gates"], False)

    def _upstream(self):
        folder = self.tmp / "upstream"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "cli.py").write_text(
            "import json, sys\n"
            "from pathlib import Path\n"
            "src = Path(sys.argv[1]).read_text(encoding='utf-8')\n"
            "Path(sys.argv[2]).write_text(json.dumps({'echo': src}), encoding='utf-8')\n"
            "print('adapted-ok')\n", encoding="utf-8")
        (self.tmp / "input.json").write_text('{"query": "x"}', encoding="utf-8")
        return folder

    def _configure(self, upstream, **overrides):
        path = t.ROOT / "adapters" / "demo-tool" / "launch.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config.update({
            "tool_root": str(upstream),
            "argv": [sys.executable, "{tool_root}/cli.py", "{input}", "{output}"],
            "output_path": "reports/third-party/demo-tool/result.json",
            "env_keys": list(t.SAFE_ENV),
        })
        config.update(overrides)
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        return path

    def test_scaffold_wrap_end_to_end(self):
        self.register()
        upstream = self._upstream()
        self.assertEqual(t.cmd_scaffold(ns(id="demo-tool", kind="launch", force=False)), 0)
        folder = t.ROOT / "adapters" / "demo-tool"
        self.assertTrue((folder / "launch.json").is_file())
        self.assertTrue((folder / "README.md").is_file())
        self._configure(upstream)

        self.assertEqual(t.cmd_wrap(ns(id="demo-tool", config="", input="input.json",
                                       execute=False)), 0)
        self.assertFalse((t.REPORTS / "receipts").exists())
        self.assertEqual(t.cmd_wrap(ns(id="demo-tool", config="", input="input.json",
                                       execute=True)), 0)
        receipts = list((t.REPORTS / "receipts").glob("adapt-*.json"))
        self.assertEqual(len(receipts), 1)
        body = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(body["exit_code"], 0)
        self.assertEqual(body["adaptation"], "launch")
        self.assertTrue(body["output_exists"])
        self.assertEqual(body["output_sha256"],
                         t._sha_file(t.ROOT / "reports/third-party/demo-tool/result.json"))
        self.assertTrue(body["advisory_only"])
        self.assertFalse(body["registered_experiment"])
        self.assertFalse(body["scientific_evidence"])
        self.assertIn("auto_submit", body["declared_disabled_upstream_behaviors"])
        self.assertEqual(t.cmd_verify(ns()), 0)

    def test_scaffold_fork_records_patches_and_refuses_overwrite(self):
        self.register()
        self.assertEqual(t.cmd_scaffold(ns(id="demo-tool", kind="fork", force=False)), 0)
        self.assertTrue((t.ROOT / "adapters/demo-tool/PATCHES.md").is_file())
        with self.assertRaises(ValueError):
            t.cmd_scaffold(ns(id="demo-tool", kind="launch", force=False))
        self.assertEqual(t.cmd_scaffold(ns(id="demo-tool", kind="launch", force=True)), 0)

    def test_wrap_rejects_state_output_and_unknown_placeholder(self):
        self.register()
        upstream = self._upstream()
        t.cmd_scaffold(ns(id="demo-tool", kind="wrapper", force=False))
        self._configure(upstream, output_path="projects/my-phd/state/run.json")
        with self.assertRaises(ValueError):
            t.cmd_wrap(ns(id="demo-tool", config="", input="input.json", execute=False))
        self._configure(upstream, argv=[sys.executable, "{mystery}/cli.py"])
        with self.assertRaises(ValueError):
            t.cmd_wrap(ns(id="demo-tool", config="", input="input.json", execute=False))
        self._configure(upstream)
        self.assertEqual(t.cmd_verify(ns()), 0)

    def test_promote_creates_candidate_without_claim_link(self):
        self.register()
        upstream = self._upstream()
        t.cmd_scaffold(ns(id="demo-tool", kind="launch", force=False))
        self._configure(upstream)
        t.cmd_wrap(ns(id="demo-tool", config="", input="input.json", execute=True))
        receipt = list((t.REPORTS / "receipts").glob("adapt-*.json"))[0]
        self.assertEqual(t.cmd_promote(ns(id="demo-tool", receipt=str(receipt),
                                          authorized_by="Owner")), 0)
        candidates = list((t.ROOT / "evidence/candidates").glob("*.json"))
        self.assertEqual(len(candidates), 1)
        body = json.loads(candidates[0].read_text(encoding="utf-8"))
        self.assertEqual(body["status"], "candidate_unverified")
        self.assertFalse(body["source_verified"])
        self.assertFalse(body["claim_linked"])
        self.assertEqual(body["authorized_by"], "Owner")
        self.assertTrue(body["source_receipt_sha256"])
        with self.assertRaises(ValueError):
            t.cmd_promote(ns(id="demo-tool", receipt=str(receipt), authorized_by="  "))

    def _fake_receipt(self, tool_id, output_value, input_sha="same-input"):
        folder = t.ROOT / "reports/third-party/receipts"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"fake-{tool_id}-{abs(hash(output_value))}.json"
        path.write_text(json.dumps({
            "schema_version": "1.0",
            "recorded_at": "2026-11-09T00:00:00Z",
            "advisory_only": True,
            "tool_id": tool_id,
            "input_sha256": input_sha,
            "output_sha256": hashlib.sha256(output_value.encode()).hexdigest(),
            "exit_code": 0,
        }), encoding="utf-8")
        return path

    def _comparison(self, outputs=("a", "b")):
        self.register()
        self.register(identity="other-tool", repo="https://github.com/example/other")
        receipts = [str(self._fake_receipt("demo-tool", outputs[0])),
                    str(self._fake_receipt("other-tool", outputs[1]))]
        assert t.cmd_compare(ns(receipt=receipts, decision="G1 closest-work gap",
                                stage="G1")) == 0
        reports = list((t.ROOT / "reports/third-party/comparisons").glob("*.json"))
        assert len(reports) == 1
        return reports[0]

    def test_compare_preserves_disagreement_without_voting(self):
        path = self._comparison(("a", "b"))
        body = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(body["same_input"])
        self.assertEqual(body["distinct_output_count"], 2)
        self.assertEqual(body["agreement_count"], 0)
        self.assertEqual(body["adoption"], "pending")
        self.assertTrue(body["advisory_only"])
        self.assertFalse(body["gate_authority"])
        self.assertEqual(len(body["receipts"]), 2)

    def test_compare_detects_agreement(self):
        path = self._comparison(("same", "same"))
        body = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(body["distinct_output_count"], 1)
        self.assertEqual(body["agreement_count"], 1)

    def test_compare_rejects_single_receipt_and_unregistered_tool(self):
        self.register()
        one = str(self._fake_receipt("demo-tool", "a"))
        with self.assertRaises(ValueError):
            t.cmd_compare(ns(receipt=[one], decision="x", stage="G1"))
        unknown = str(self._fake_receipt("not-registered", "b"))
        with self.assertRaises(ValueError):
            t.cmd_compare(ns(receipt=[one, unknown], decision="x", stage="G1"))

    def test_adopt_records_verdict_and_requires_reason(self):
        path = self._comparison()
        assert t.cmd_adopt(ns(comparison=str(path), tool_id="demo-tool",
                              verdict="adopted", reason="found a missing rival",
                              by="Owner")) == 0
        records = list((t.ROOT / "reports/third-party/adoptions").glob("*.json"))
        self.assertEqual(len(records), 1)
        body = json.loads(records[0].read_text(encoding="utf-8"))
        self.assertEqual(body["verdict"], "adopted")
        self.assertEqual(body["tool_id"], "demo-tool")
        self.assertTrue(body["comparison_sha256"])
        with self.assertRaises(ValueError):
            t.cmd_adopt(ns(comparison=str(path), tool_id="ghost", verdict="rejected",
                           reason="x", by="Owner"))
        with self.assertRaises(ValueError):
            t.cmd_adopt(ns(comparison=str(path), tool_id="demo-tool",
                           verdict="rejected", reason="  ", by="Owner"))

    def _free_argv(self):
        return ["--", sys.executable, "-c", "print('free-ok')"]

    def test_free_runs_without_any_registry_entry(self):
        argv = self._free_argv()
        assert t.cmd_free(ns(source="https://github.com/example/anything", cwd="",
                             timeout=30, execute=False, no_receipt=False,
                             argv=argv)) == 0
        self.assertFalse((t.REPORTS / "receipts").exists())
        assert t.cmd_free(ns(source="https://github.com/example/anything", cwd="",
                             timeout=30, execute=True, no_receipt=False,
                             argv=argv)) == 0
        receipts = list((t.REPORTS / "receipts").glob("free-*.json"))
        self.assertEqual(len(receipts), 1)
        body = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertTrue(body["no_registry_entry"])
        self.assertTrue(body["advisory_only"])
        self.assertEqual(t._load()["tools"], [])

    def test_free_can_skip_the_optional_receipt(self):
        assert t.cmd_free(ns(source="", cwd="", timeout=30, execute=True,
                             no_receipt=True, argv=self._free_argv())) == 0
        self.assertFalse((t.REPORTS / "receipts").exists())

    def test_verify_detects_broken_adapter(self):
        self.register()
        t.cmd_scaffold(ns(id="demo-tool", kind="launch", force=False))
        self.assertEqual(t.cmd_verify(ns()), 0)
        path = t.ROOT / "adapters/demo-tool/launch.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["argv"] = ["python3", "{unknown_flag}"]
        path.write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(t.cmd_verify(ns()), 1)


if __name__ == "__main__":
    unittest.main()
