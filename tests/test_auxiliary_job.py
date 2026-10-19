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
        self.assertEqual(run.call_args.kwargs,{"attachments":None,"source_contract":None})
        self.assertEqual(result["status"],"internal_candidate_requires_review")

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


if __name__=="__main__":
    unittest.main()
