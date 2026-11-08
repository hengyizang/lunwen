from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ai_providers, auxiliary_job


class AuxiliaryJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project=Path(self.temporary.name)
        (self.project/"evidence"/"requests").mkdir(parents=True)
        (self.project/"evidence"/"requests"/"prompt.txt").write_text("Diagnose the supplied candidate without claiming a verified scientific result.")
        self.environment=patch.dict(os.environ,{"DR_OS_ROUTING_PROFILE":"production"})
        self.environment.start();self.addCleanup(self.environment.stop)
        self.policy=patch.object(auxiliary_job.model_routing,"load_policy",return_value=({},"fake-policy"))
        self.policy.start();self.addCleanup(self.policy.stop)

    def manifest(self,**overrides):
        data={"schema_version":"1.0","kind":"engineering-diagnosis","prompt_file":"evidence/requests/prompt.txt"}
        data.update(overrides)
        path=self.project/"evidence"/"requests"/"request.json"
        path.write_text(json.dumps(data),encoding="utf-8")
        return "evidence/requests/request.json"

    def test_dry_run_calls_only_plan_and_preserves_input_hashes(self):
        manifest=self.manifest()
        with patch.object(auxiliary_job.task_router,"plan",return_value={"model":"chosen-by-policy"}) as plan, \
             patch.object(auxiliary_job.task_router,"run") as execute:
            result=auxiliary_job.run(self.project,manifest,"evidence/auxiliary/preview.json")
        execute.assert_not_called();plan.assert_called_once()
        self.assertEqual(result["status"],"dry_run_no_model_call")
        report=json.loads((self.project/result["output"]).read_text())
        self.assertEqual(report["budget_granted_cny"],0)
        self.assertFalse(report["automatic_acceptance"])
        self.assertEqual(report["input_receipts"][1]["sha256"],hashlib.sha256((self.project/"evidence/requests/prompt.txt").read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError,"overwrite"):
            auxiliary_job.run(self.project,manifest,"evidence/auxiliary/preview.json",execute=True)

    def test_execution_uses_task_router_without_model_or_budget_override(self):
        manifest=self.manifest(max_output_tokens=900)
        with patch.object(auxiliary_job.task_router,"plan",return_value={"model":"chosen-by-policy"}), \
             patch.object(auxiliary_job.task_router,"run",return_value={"result":"api_runs/fake/result.json"}) as run:
            result=auxiliary_job.run(self.project,manifest,"evidence/auxiliary/result.json",execute=True)
        self.assertEqual(run.call_args.args[:3],(self.project,"engineering-diagnosis","deepseek"))
        self.assertEqual(run.call_args.args[4],900)
        self.assertEqual(run.call_args.kwargs,{"attachments":None,"source_contract":None,
            "task_profile":{"task_class":"unspecified","science_risk":"auxiliary","priority":"quality"}})
        self.assertEqual(result["status"],"internal_candidate_requires_review")

    def test_calibration_seat_cannot_override_other_helpers_and_requires_a_critical_profile(self):
        with self.assertRaisesRegex(ValueError, "allowed only"):
            auxiliary_job.load(self.project, self.manifest(calibration_seat="statistics"))
        with self.assertRaisesRegex(ValueError, "critical scientific"):
            auxiliary_job.load(self.project, self.manifest(kind="public-review-calibration", calibration_seat="domain"))
        profile = {"task_class": "public-review-calibration", "science_risk": "critical", "priority": "quality"}
        with self.assertRaisesRegex(ValueError, "one fixed"):
            auxiliary_job.load(self.project, self.manifest(kind="public-review-calibration", task_profile=profile, calibration_seat="all"))
        manifest = self.manifest(kind="public-review-calibration", task_profile=profile, calibration_seat="domain", max_output_tokens=4000)
        with patch("scripts.public_review_anchors.run_calibration", return_value={"status": "dry_run_no_model_call", "calls_planned": 8,
                    "calls_attempted": 0, "reserved_upper_bound_cny": 13}) as calibration, patch.object(auxiliary_job.task_router, "run") as ordinary:
            auxiliary_job.run(self.project, manifest, "evidence/auxiliary/calibration.json")
        ordinary.assert_not_called()
        self.assertEqual(calibration.call_args.kwargs["seat"], "domain")
        self.assertFalse(calibration.call_args.kwargs["execute"])
        self.assertEqual(calibration.call_args.kwargs["max_output_tokens"], 4000)
        manifest = self.manifest(kind="public-review-calibration", task_profile=profile, calibration_seat="domain", max_output_tokens=12000)
        with patch("scripts.public_review_anchors.run_calibration", return_value={"status": "dry_run_no_model_call", "calls_planned": 8,
                    "calls_attempted": 0, "reserved_upper_bound_cny": 14}) as calibration:
            auxiliary_job.run(self.project, manifest, "evidence/auxiliary/calibration-12000.json")
        self.assertEqual(calibration.call_args.kwargs["max_output_tokens"], 12000)
        for kind in ("public-review-calibration", "g1-transport-validation"):
            for tokens in (3999, 8000, True):
                with self.subTest(kind=kind, tokens=tokens), self.assertRaises(ValueError):
                    auxiliary_job.load(self.project, self.manifest(kind=kind, task_profile={**profile, "task_class": kind}, max_output_tokens=tokens))

    def test_citation_crosscheck_binds_only_its_explicit_scientific_source_task(self):
        profile = {"task_class": "citation-crosscheck", "science_risk": "critical", "priority": "quality"}
        task = self.project / "program/citation-task.json"
        task.parent.mkdir(parents=True)
        task.write_text('{"schema_version":"1.0","id":"synthetic-citation-task"}')
        with self.assertRaisesRegex(ValueError, "allowed only"):
            auxiliary_job.load(self.project, self.manifest(source_task_file="program/citation-task.json"))
        with self.assertRaisesRegex(ValueError, "program/.*json"):
            auxiliary_job.load(self.project, self.manifest(kind="citation-crosscheck", task_profile=profile,
                                                         source_task_file="evidence/citation-task.json"))
        manifest = self.manifest(kind="citation-crosscheck", task_profile=profile, source_task_file="program/citation-task.json")
        request = auxiliary_job.load(self.project, manifest)
        self.assertEqual(request["inputs"][-1]["sha256"], hashlib.sha256(task.read_bytes()).hexdigest())
        with patch("scripts.literature_source_tasks.run_citation_crosscheck", create=True,
                   return_value={"status": "dry_run_no_model_call", "calls_planned": 2, "calls_attempted": 0}) as bridge:
            result = auxiliary_job.run(self.project, manifest, "evidence/auxiliary/citations.json")
        self.assertEqual(result["calls_planned"], 2)
        self.assertEqual(bridge.call_args.kwargs["request_file"], "program/citation-task.json")
        self.assertFalse(bridge.call_args.kwargs["execute"])
        self.assertNotIn("prompt", bridge.call_args.kwargs)

    def test_g1_validation_delegates_one_native_cycle_and_preserves_approvals_and_receipts(self):
        from scripts import api_orchestrator, model_runtime
        profile = {"task_class": "g1-transport-validation", "science_risk": "critical", "priority": "quality"}
        state = self.project / "state/run.json"; state.parent.mkdir()
        scope = {"stage": "topic-intelligence", "gate": "G1", "status": "awaiting_work", "approved_gates": ["G0"], "paper_count": 6}
        state.write_text(json.dumps(scope))
        policy_bytes = auxiliary_job.model_routing.DEFAULT_POLICY.read_bytes()
        policy = (json.loads(policy_bytes), hashlib.sha256(policy_bytes).hexdigest())
        manifest = self.manifest(kind="g1-transport-validation", task_profile=profile)
        def native_cycle(*args, **kwargs):
            route = auxiliary_job.model_routing.select("topic-intelligence", "persistent-writer", "scientific-judgment")
            self.assertEqual((route["provider"], route["model"], route["reasoning_effort"]), ("codekey-codex-pro", "gpt-6-astra", "high"))
            self.assertTrue(kwargs["automatic_data"])
            with self.assertRaisesRegex(ValueError, "additional paid helpers"):
                auxiliary_job.model_routing.resolve_call("auxiliary", "evidence-synthesis", "openai", project_root=self.project)
            row = {"run_id": "synthetic-g1", "role": "persistent-writer", "routing_policy_sha256": route["policy_sha256"],
                   "cost_cny": .4, "cost_status": "estimated_upper_bound"}
            (self.project / "state/model-usage.jsonl").write_text(json.dumps(row) + "\n")
            return {"run_id": "synthetic-g1", "stage": "topic-intelligence", "gate_authority": False}
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1", "DR_OS_REQUIRE_REMOTE_RESERVATION": "1"}), \
             patch.object(auxiliary_job.model_routing, "load_policy", return_value=policy), \
             patch.object(api_orchestrator, "project_root", return_value=self.project), \
             patch.object(api_orchestrator, "run_cycle", side_effect=native_cycle) as native, \
             patch.object(model_runtime, "budget_status", return_value={"project_remaining": 500}):
            result = auxiliary_job.run(self.project, manifest, "evidence/auxiliary/g1.json", execute=True)
            self.assertEqual(auxiliary_job.model_routing.select("topic-intelligence", "persistent-writer")["provider"], "cheapai-gpt-pro")
        native.assert_called_once()
        self.assertEqual(native.call_args.args[1], "topic-intelligence")
        self.assertEqual(json.loads(state.read_text()), scope)
        report = json.loads((self.project / result["output"]).read_text())
        self.assertFalse(report["topic_approval_granted"])
        self.assertEqual(report["calls_attempted"], 1)
        self.assertEqual(report["maximum_calls"], 5)
        self.assertAlmostEqual(report["maximum_reserved_upper_bound_cny"], 49.2684244)
        self.assertFalse(report["accounting"]["provider_fee_fully_verified"])
        manifest = self.manifest(kind="g1-transport-validation", task_profile=profile, max_output_tokens=12000)
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), \
             patch.object(auxiliary_job.model_routing, "load_policy", return_value=policy):
            result = auxiliary_job.run(self.project, manifest, "evidence/auxiliary/g1-12000.json")
        report = json.loads((self.project / result["output"]).read_text())
        self.assertAlmostEqual(report["maximum_reserved_upper_bound_cny"], 49.4364244)
        self.assertTrue(all(row["max_output_tokens"] == 12000 for row in report["model_plan"]))
        manifest = self.manifest(kind="g1-transport-validation", task_profile=profile, max_output_tokens=12000, validation_roster="astra-argon")
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), \
             patch.object(auxiliary_job.model_routing, "load_policy", return_value=policy):
            result = auxiliary_job.run(self.project, manifest, "evidence/auxiliary/g1-astra-argon.json")
        report = json.loads((self.project / result["output"]).read_text())
        self.assertAlmostEqual(report["maximum_reserved_upper_bound_cny"], 53.5104264)
        ordinary = [row for row in report["model_plan"] if row["role"] in ("semantic-planner", "persistent-writer", "independent-critic-initial")]
        self.assertAlmostEqual(sum(row["reserved_upper_bound_cny"] for row in ordinary), 34.8492172)
        self.assertEqual([row["planned_route"]["model"] for row in report["model_plan"]],
                         ["gpt-6-astra", "gpt-6-astra", "gemini-4-argon", "gpt-6-astra", "gemini-4-argon"])
        for fields in ({"validation_roster": "astra-argon"}, {"kind": "g1-transport-validation", "task_profile": profile, "validation_roster": "other"}):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, "validation_roster"):
                auxiliary_job.load(self.project, self.manifest(**fields))

    def test_manifest_rejects_unknown_fields_roles_duplicate_json_and_legacy(self):
        for field in ("provider","model","reasoning_effort","allow_paid","budget_cny"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    auxiliary_job.load(self.project,self.manifest(**{field:"override"}))
        for kind in ("scientific-judgment","evidence-synthesis","independent-critique"):
            with self.assertRaisesRegex(ValueError,"bounded auxiliary"):
                auxiliary_job.load(self.project,self.manifest(kind=kind))
        manifest=self.manifest()
        (self.project/manifest).write_text('{"schema_version":"1.0","kind":"format-conversion","kind":"engineering-diagnosis","prompt_file":"evidence/requests/prompt.txt"}')
        with self.assertRaisesRegex(ValueError,"duplicate"):
            auxiliary_job.load(self.project,manifest)
        with patch.dict(os.environ,{"DR_OS_ROUTING_PROFILE":"legacy"}):
            with self.assertRaisesRegex(ValueError,"production"):
                auxiliary_job.load(self.project,manifest)

    def test_private_escape_absolute_ads_and_symlink_paths_are_rejected(self):
        for path in ("../outside.txt","/tmp/outside.txt","C:/outside.txt","evidence/../state/run.json",
                     "state/run.json","private/prompt.txt","evidence/.env","evidence/api.txt",
                     "evidence/prompt.txt:stream","evidence\\prompt.txt","evidence//prompt.txt"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    auxiliary_job.load(self.project,self.manifest(prompt_file=path))
        source=self.project/"evidence"/"requests"/"prompt.txt"
        alias=self.project/"evidence"/"alias.txt"
        try:
            alias.symlink_to(source)
        except (OSError,NotImplementedError):
            return
        with self.assertRaisesRegex(ValueError,"symlink"):
            auxiliary_job.load(self.project,self.manifest(prompt_file="evidence/alias.txt"))

    def test_metadata_requires_valid_contract_and_forbids_cross_role_contract(self):
        with self.assertRaisesRegex(ValueError,"requires source_contract_file"):
            auxiliary_job.load(self.project,self.manifest(kind="metadata-extraction"))
        contract={"sources":[{"source_id":"S1","text":"The sample included 120 adults.","locator":"PDF page 2"}],"fields":["sample_n"]}
        (self.project/"evidence"/"requests"/"contract.json").write_text(json.dumps(contract))
        request=auxiliary_job.load(self.project,self.manifest(kind="metadata-extraction",source_contract_file="evidence/requests/contract.json"))
        self.assertEqual(request["source_contract"],contract)
        self.assertEqual(request["inputs"][2]["role"],"source_contract")
        with self.assertRaisesRegex(ValueError,"only for metadata"):
            auxiliary_job.load(self.project,self.manifest(source_contract_file="evidence/requests/contract.json"))

    def test_multimodal_loads_only_explicit_files_and_validates_hash_and_mime(self):
        image=self.project/"evidence"/"sample.png"
        raw=b"\x89PNG\r\n\x1a\nsynthetic-input"
        image.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,"requires 1..5"):
            auxiliary_job.load(self.project,self.manifest(kind="multimodal-inspection"))
        manifest=self.manifest(kind="multimodal-inspection",attachments=[{"path":"evidence/sample.png","mime_type":"image/png"}])
        with patch.object(auxiliary_job.ai_providers,"validate_attachments",wraps=ai_providers.validate_attachments) as validate:
            request=auxiliary_job.load(self.project,manifest)
        validate.assert_called_once()
        self.assertEqual(request["attachments"][0]["sha256"],hashlib.sha256(raw).hexdigest())
        self.assertEqual(base64.b64decode(request["attachments"][0]["data_base64"]),raw)
        with patch.object(auxiliary_job.task_router,"plan",return_value={"within_estimated_budget":True}), \
             patch.object(auxiliary_job.task_router,"run") as run:
            result=auxiliary_job.run(self.project,manifest,"evidence/auxiliary/media-preview.json")
        run.assert_not_called()
        report=json.loads((self.project/result["output"]).read_text())
        self.assertIsNone(report["plan"]["within_estimated_budget"])
        self.assertFalse(report["plan"]["estimated_cost_complete"])
        self.assertNotIn("data_base64",json.dumps(report))
        bad=self.manifest(kind="multimodal-inspection",attachments=[{"path":"evidence/sample.png","mime_type":"application/pdf"}])
        with self.assertRaises(ai_providers.ProviderError):
            auxiliary_job.load(self.project,bad)

    def test_mutated_input_blocks_transport_and_output_overwrite(self):
        manifest=self.manifest()
        def change_source(*args,**kwargs):
            (self.project/"evidence"/"requests"/"prompt.txt").write_text("changed source")
            return {}
        with patch.object(auxiliary_job.task_router,"plan",side_effect=change_source), \
             patch.object(auxiliary_job.task_router,"run") as execute:
            with self.assertRaisesRegex(ValueError,"source changed"):
                auxiliary_job.run(self.project,manifest,"evidence/auxiliary/changed.json",execute=True)
        execute.assert_not_called()
        self.assertFalse((self.project/"evidence/auxiliary/changed.json").exists())
