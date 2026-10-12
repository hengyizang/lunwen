"""Configured-detector boundaries and opt-in real offline CPU regression."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import output_provenance, statistical_watermarks as wm
from scripts.research_artifacts import read, sha, write


class StatisticalWatermarkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name) / "demo"
        self.paper = self.project / "papers/P01"
        self.source = self.paper / "manuscript/main.tex"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("Synthetic manuscript text for engineering tests only.\n", encoding="utf-8")
        output_provenance.record_model_writes(self.project, [self.source], family="openai", provider="fixture",
            model="fixture", role="writer", run_id="fixture")
        environment = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1", "DR_OS_WATERMARK_KEY_TEST": "15485863"})
        environment.start()
        self.addCleanup(environment.stop)

    def profile(self):
        assets = self.project / "evidence/watermark-assets"
        assets.mkdir(parents=True, exist_ok=True)
        write(assets / "config.json", {"model_type": "gpt2", "vocab_size": 258})
        write(assets / "tokenizer.json", {"version": "1.0"})
        evidence = self.project / "evidence/applicability.txt"
        evidence.write_text("Synthetic fixture: the CPU greenlist configuration and tokenizer are supplied by its generator.\n", encoding="utf-8")
        output_provenance.attest_human_files(self.project, [evidence], actor="Fixture author", note="Synthetic configuration evidence only.")
        value = {"schema_version": "1.0", "detector": wm.DETECTOR,
            "applicability": {"scheme": "hf-greenlist", "generation_device": "cpu", "tokenizer_and_config_match": True,
                "evidence": {"path": "evidence/applicability.txt", "sha256": sha(evidence), "locator": "line 1"}},
            "assets_dir": "evidence/watermark-assets", "asset_sha256": {p.name: sha(p) for p in assets.iterdir()},
            "key_env": "DR_OS_WATERMARK_KEY_TEST", "key_version": "synthetic-v1",
            "watermark": {"greenlist_ratio": 0.25, "bias": 2.0, "seeding_scheme": "lefthash", "context_width": 2},
            "z_threshold": 3.5, "min_scored_tokens": 100, "sources": ["papers/P01/manuscript/main.tex"]}
        write(self.paper / "watermark-assessment.json", value)
        return value

    def test_unconfigured_is_unknown_without_importing_a_runtime_or_calling_a_provider(self):
        with patch.object(wm, "_execute", side_effect=AssertionError("no configured detector")), \
             patch("scripts.model_runtime.call", side_effect=AssertionError("no paid call")):
            result = wm.refresh(self.project, "P01")
            self.assertEqual(wm.validate_saved_report(self.project, "P01"), [])
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["watermark_absence_verified"])
        self.assertFalse(result["all_watermark_types_assessed"])
        self.assertEqual(result["paid_calls"], 0)

    def test_unknown_coverage_stays_bound_to_all_current_sources(self):
        wm.refresh(self.project, "P01")
        self.source.write_text("Changed after assessment.\n", encoding="utf-8")
        self.assertTrue(wm.validate_saved_report(self.project, "P01"))

    def test_forged_absence_or_report_provenance_cannot_pass(self):
        wm.refresh(self.project, "P01")
        target = self.project / wm.review_binding(self.project, "P01")["path"]
        value = read(target)
        value["watermark_absence_verified"] = True
        write(target, value)
        self.assertTrue(wm.validate_saved_report(self.project, "P01"))

    def test_missing_key_or_pinned_runtime_blocks_configured_assessment(self):
        self.profile()
        with patch.dict(os.environ, {"DR_OS_WATERMARK_KEY_TEST": ""}):
            result = wm.refresh(self.project, "P01")
        self.assertEqual(result["status"], "error")
        self.assertTrue(wm.validate_saved_report(self.project, "P01"))
        with patch.object(wm, "runtime_available", return_value=False):
            self.assertEqual(wm.audit(self.project, "P01")["status"], "error")

    def test_adapter_rejects_unsupported_scheme_remote_code_or_partial_sources(self):
        original = self.profile()
        for mutate in (lambda v: v.update(detector="any-provider"),
                       lambda v: v.update(sources=[]),
                       lambda v: v["watermark"].update(seeding_scheme="custom"),
                       lambda v: v.update(assets_dir="../outside")):
            value = copy.deepcopy(original)
            mutate(value)
            write(self.paper / "watermark-assessment.json", value)
            self.assertEqual(wm.audit(self.project, "P01")["status"], "error")
        write(self.paper / "watermark-assessment.json", original)
        write(self.project / "evidence/watermark-assets/config.json", {"auto_map": {"AutoConfig": "malicious.py"}})
        self.assertEqual(wm.audit(self.project, "P01")["status"], "error")

    def test_applicability_requires_real_human_attestation(self):
        profile = self.profile()
        target = self.project / profile["applicability"]["evidence"]["path"]
        output_provenance.record_model_writes(self.project, [target], family="openai", provider="fixture", model="fixture", role="writer", run_id="fixture")
        self.assertEqual(wm.audit(self.project, "P01")["status"], "error")

    def test_positive_and_short_results_block_but_negative_never_claims_absence(self):
        self.profile()
        for status in ("detected", "insufficient_length", "not_detected"):
            outcome = {"status": status, "token_count": 600, "scored_tokens": 500}
            with self.subTest(status=status), patch.object(wm, "runtime_available", return_value=True), \
                 patch.object(wm, "_execute", return_value=outcome):
                result = wm.refresh(self.project, "P01")
                self.assertEqual(bool(wm.validate_saved_report(self.project, "P01")), status != "not_detected")
                self.assertFalse(result["watermark_absence_verified"])
                self.assertFalse(result["statistical_watermark_removal_verified"])

    def test_worker_errors_do_not_expose_secret_or_dependency_exceptions(self):
        self.profile()
        with patch.object(wm, "runtime_available", return_value=True), \
             patch.object(wm, "_execute", side_effect=ValueError("private key 15485863")):
            result = wm.audit(self.project, "P01")
        self.assertNotIn("15485863", json.dumps(result))
        self.assertEqual(result["status"], "error")

    def test_cloud_guard_and_profile_ownership(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(ValueError, "cloud"):
                wm.refresh(self.project, "P01")
        from scripts import api_orchestrator
        with patch.object(api_orchestrator, "project_root", return_value=self.project):
            # The author bundle cannot remove or replace an applicable profile.
            with self.assertRaisesRegex(ValueError, "protected"):
                api_orchestrator.safe_target("demo", "papers/P01/watermark-assessment.json")

    @unittest.skipUnless(os.environ.get("DR_OS_TEST_WATERMARK_RUNTIME") == "1", "separate pinned offline CPU job")
    def test_real_offline_cpu_positive_and_negative_without_model_weights(self):
        self.assertTrue(wm.runtime_available(), "the opt-in job must install the exact CPU dependency versions")
        import torch
        from tokenizers import Tokenizer, models, pre_tokenizers
        from transformers import GPT2Config, PreTrainedTokenizerFast, WatermarkLogitsProcessor
        self.profile()
        assets = self.project / "evidence/watermark-assets"
        vocab = {"[UNK]": 0, **{f"v{i}": i + 1 for i in range(256)}, "[PAD]": 257}
        backend = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
        backend.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
        tokenizer = PreTrainedTokenizerFast(tokenizer_object=backend, unk_token="[UNK]", pad_token="[PAD]")
        tokenizer.save_pretrained(assets)
        GPT2Config(vocab_size=258, bos_token_id=None, eos_token_id=None, n_layer=1, n_head=1, n_embd=16).to_json_file(assets / "config.json")
        profile = read(self.paper / "watermark-assessment.json")
        profile["asset_sha256"] = {p.name: sha(p) for p in assets.iterdir()}
        write(self.paper / "watermark-assessment.json", profile)
        processor = WatermarkLogitsProcessor(vocab_size=258, device="cpu", hashing_key=15485863, **profile["watermark"])
        generator = torch.Generator(device="cpu").manual_seed(23)
        ids = [1, 2]
        for _ in range(600):
            scores = torch.zeros((1, 258))
            scores[0, 0] = scores[0, 257] = -100
            marked = processor(torch.tensor([ids], dtype=torch.long), scores)
            ids.append(int(torch.multinomial(marked.softmax(-1), 1, generator=generator)[0, 0]))
        for expected, values in (("detected", ids), ("not_detected", torch.randint(1, 257, (602,), generator=generator).tolist())):
            self.source.write_text(" ".join(tokenizer.convert_ids_to_tokens(values)) + "\n", encoding="utf-8")
            with self.subTest(expected=expected), patch("socket.create_connection", side_effect=AssertionError("no network")):
                result = wm.refresh(self.project, "P01")
                self.assertEqual(result["status"], expected, result["errors"])
                self.assertGreaterEqual(result["result"]["scored_tokens"], 100)
                self.assertEqual(bool(wm.validate_saved_report(self.project, "P01")), expected == "detected")
                self.assertFalse(result["watermark_absence_verified"])


if __name__ == "__main__":
    unittest.main()
