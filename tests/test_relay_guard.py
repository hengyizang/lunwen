"""Real shared relay control with an isolated CAS store; no external services."""
from __future__ import annotations
from contextvars import Context
import base64
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ai_providers,model_runtime,model_spend,relay_billing,relay_guard as guard,model_comparison as comparison,model_comparison_clarified as clarified
from scripts.research_artifacts import write
from tests.relay_guard_fixtures import MemoryStore

PROVIDER="codekey-gemini"
KEY_SETTING=ai_providers.PRODUCTION_PROVIDERS[PROVIDER]["key_setting"]


class RelayGuardTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{"GITHUB_ACTIONS":"true","GITHUB_REPOSITORY":guard.REPOSITORY,
            "GITHUB_RUN_ID":"123",KEY_SETTING:"synthetic-shared-key"},clear=True)
        self.env.start();self.addCleanup(self.env.stop)
        guard._TICKET.set(None);self.addCleanup(lambda:guard._TICKET.set(None))
        self.store=MemoryStore()

    def historical(self,provider=PROVIDER):
        branch,name=guard.SOURCES[1]
        self.store.put(branch,"trial-state",name,{"entries":[{"provider":provider,"call_id":provider+"|historical-unknown",
            "billing_status":"unknown_held","reserved_ceiling_cny":0.431508}]})

    def begin(self,**kwargs):
        return guard.begin(PROVIDER,scope={"project":"original-project","reservation_id":"local-reservation"},max_cost_cny=1,store=self.store,**kwargs)

    def meter(self):
        return {"provider":PROVIDER,"kind":"codekey_total_actual_cost","requests":20,"cost_cny":2.0}

    def bind(self,ticket):
        guard.bind_meter(ticket,"gemini-4-argon",self.meter(),store=self.store)

    def send(self):
        guard.authorize_transport("https://codekey.ai/v1beta/models/gemini-4-argon:generateContent",{"x-goog-api-key":os.environ[KEY_SETTING]})

    def debit(self,cost=0.125):
        return {"actual_cost_cny":cost,"debit_evidence":{"source":"https://codekey.ai/v1/usage",
            "before":{"requests":20,"cost_cny":2.0},"after":{"requests":21,"cost_cny":2.0+cost},"exactly_one_new_gateway_request":True}}

    def active(self):
        return self.store.read(guard.BRANCH,"relay-guard",guard.fingerprint(PROVIDER)+".json")[0]

    def test_historical_unknown_remains_held_after_readonly_catalog_success(self):
        self.historical()
        with patch("scripts.production_readiness.catalog",return_value={"gemini-4-argon"}) as catalog:
            self.assertIn("gemini-4-argon",catalog(PROVIDER,dict(os.environ)))
            self.assertFalse(guard.inspect(PROVIDER,store=self.store)["inference_eligible"])
            with self.assertRaisesRegex(guard.RelayGuardError,"historical"):
                self.begin()
        self.assertEqual(len(self.active()["legacy_holds"]),1)
        self.assertIsNone(self.active()["active"])

    def test_same_credential_across_different_group_imports_original_holds(self):
        other="codekey-codex-pro"
        with patch.dict(os.environ,{ai_providers.PRODUCTION_PROVIDERS[other]["key_setting"]:os.environ[KEY_SETTING]}):
            self.historical(other)
            with self.assertRaisesRegex(guard.RelayGuardError,"historical"):
                self.begin()
        self.assertEqual(next(iter(self.active()["legacy_holds"].values()))["provider"],other)

    def test_cas_lease_stops_concurrent_jobs_and_a_different_project(self):
        competing=Context()
        self.store.before_write=lambda:competing.run(lambda:guard.begin(PROVIDER,scope={"project":"competing-project"},max_cost_cny=1,store=self.store))
        with self.assertRaisesRegex(guard.RelayGuardError,"CAS conflict"):
            self.begin()
        self.assertEqual(self.active()["active"]["scope"]["project"],"competing-project")
        with self.assertRaisesRegex(guard.RelayGuardError,"concurrent"):
            guard.begin(PROVIDER,scope={"project":"brand-new-project"},max_cost_cny=0.5,store=self.store)
        self.assertIsNone(guard._TICKET.get())

    def test_failed_durable_lease_never_authorizes_a_post(self):
        self.store.fail_write=True
        with self.assertRaises(guard.RelayGuardError):self.begin()
        with self.assertRaisesRegex(guard.RelayGuardError,"durable"):
            self.send()

    def test_cloud_store_requires_exact_blob_identity_and_put_readback(self):
        store=guard.CloudStore()
        with patch.object(store,"api",side_effect=[{"tree":[{"path":"relay-guard","sha":"tree"}]},
                {"tree":[{"path":"fixture.json","sha":"a"*40}]},{"content":base64.b64encode(b"{}").decode()}]):
            with self.assertRaisesRegex(guard.RelayGuardError,"blob identity"):
                store.read(guard.BRANCH,"relay-guard","fixture.json")
        with patch.object(store,"api",side_effect=[{"object":{"sha":"main"}},{"content":{"sha":"b"*40}}]), \
                patch.object(store,"read_blob",return_value={"different":"bytes"}):
            with self.assertRaisesRegex(guard.RelayGuardError,"readback"):
                store.write("fixture.json",{"intended":"bytes"},None)

    def test_write_verifies_immutable_put_result_despite_a_stale_branch_tree(self):
        store=guard.CloudStore()
        with patch.object(store,"api",side_effect=[{"object":{"sha":"main"}},{"content":{"sha":"b"*40}}]), \
                patch.object(store,"read",side_effect=AssertionError("moving refs may be stale")), \
                patch.object(store,"read_blob",return_value={"intended":"bytes"}) as exact:
            self.assertEqual(store.write("fixture.json",{"intended":"bytes"},None),"b"*40)
        exact.assert_called_once_with("b"*40)

    def test_cloud_store_historical_blob_checks_immutable_git_identity(self):
        import hashlib
        raw=json.dumps({"original":"bound parent ledger"}).encode()
        blob=hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
        data={"sha":blob,"encoding":"base64","content":base64.b64encode(raw).decode()}
        store=guard.CloudStore()
        with patch.object(store,"api",return_value=data) as api:
            self.assertEqual(store.read_blob(blob),{"original":"bound parent ledger"})
            api.assert_called_once_with("git/blobs/"+blob)
        data["content"]=base64.b64encode(b'{"changed":"parent"}').decode()
        with patch.object(store,"api",return_value=data):
            with self.assertRaisesRegex(guard.RelayGuardError,"blob identity"):
                store.read_blob(blob)

    def test_transport_requires_durably_bound_before_meter_and_exact_key_once(self):
        ticket=self.begin()
        with self.assertRaisesRegex(guard.RelayGuardError,"durable"):self.send()
        self.bind(ticket)
        self.assertEqual(self.active()["active_meter"]["before"],self.meter())
        with self.assertRaises(guard.RelayGuardError):
            guard.authorize_transport("https://codekey.ai/v1beta/models/gemini-4-argon:generateContent",{"x-goog-api-key":"different-synthetic-key"})
        self.send()
        with self.assertRaisesRegex(guard.RelayGuardError,"unused"):
            self.send()

    def test_exact_independent_settlement_releases_lease_and_nothing_else(self):
        ticket=self.begin();self.bind(ticket);self.send()
        for settlement in (None,{"actual_cost_cny":0.1,"debit_evidence":{}},self.debit(2),
                {**self.debit(),"actual_cost_cny":True}):
            with self.assertRaises(guard.RelayGuardError):guard.finish(ticket,settlement,store=self.store)
            self.assertEqual(self.active()["active"],ticket)
        wrong=self.debit();wrong["debit_evidence"]["before"]["requests"]=19
        with self.assertRaisesRegex(guard.RelayGuardError,"different before meter"):
            guard.finish(ticket,wrong,store=self.store)
        guard.finish(ticket,self.debit(),store=self.store)
        self.assertIsNone(self.active()["active"])
        self.assertEqual(self.active()["events"][-1]["status"],"settled")
        self.assertIsNone(guard._TICKET.get())
        self.assertIsNotNone(self.begin())

    def test_unsent_cancellation_never_releases_a_possibly_sent_call(self):
        ticket=self.begin();guard.finish(ticket,not_sent=True,store=self.store)
        self.assertIsNone(self.active()["active"])
        ticket=self.begin();self.bind(ticket);self.send()
        with self.assertRaisesRegex(guard.RelayGuardError,"possibly sent"):
            guard.finish(ticket,not_sent=True,store=self.store)
        self.assertEqual(self.active()["active"],ticket)

    def test_an_unsent_call_cannot_be_labeled_paid_and_release_its_meter(self):
        ticket=self.begin();self.bind(ticket)
        with self.assertRaisesRegex(guard.RelayGuardError,"unsent"):
            guard.finish(ticket,self.debit(),store=self.store)
        self.assertEqual(self.active()["active"],ticket)

    def test_cheapai_receipt_must_match_the_retained_before_snapshot_and_model(self):
        provider="cheapai-gpt-pro";key=ai_providers.PRODUCTION_PROVIDERS[provider]["key_setting"]
        with patch.dict(os.environ,{key:"synthetic-cheapai-key"}):
            before={"provider":provider,"kind":"cheapai_quota_history","quota_per_unit":500000,"rows":[]}
            ticket=guard.begin(provider,scope={"project":"fixture"},max_cost_cny=1,store=self.store)
            guard.bind_meter(ticket,"gpt-6.1-sol",before,store=self.store)
            guard.authorize_transport("https://cheapai.info/v1/responses",{"Authorization":"Bearer synthetic-cheapai-key"})
            settlement={"actual_cost_cny":0.1,"debit_evidence":{"source":"https://cheapai.info/api/log/token","exactly_one_new_gateway_request":True,
                "before_snapshot_sha256":relay_billing._fingerprint({"rows":[]}),"row":{"model_name":"gpt-6-astra","quota":50000}}}
            with self.assertRaisesRegex(guard.RelayGuardError,"before meter/model"):
                guard.finish(ticket,settlement,store=self.store)
            settlement["debit_evidence"]["row"]["model_name"]="gpt-6.1-sol"
            guard.finish(ticket,settlement,store=self.store)
            self.assertIsNone(self.store.read(guard.BRANCH,"relay-guard",guard.fingerprint(provider)+".json")[0]["active"])

    def proposal(self,project,value):
        path=project/"program/reconcile.json";write(path,value);return "program/reconcile.json"

    def test_rotated_credential_requires_owner_attestation_and_preserves_the_original_hold(self):
        self.historical()
        with self.assertRaises(guard.RelayGuardError):self.begin()
        old_id=guard.fingerprint(PROVIDER);old=copy.deepcopy(self.active())
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{KEY_SETTING:"different-newly-issued-fixture-key"}):
            project=Path(temporary)/"original-project"
            value={"provider":PROVIDER,"kind":"new_credential","credential_sha256":guard.fingerprint(PROVIDER),"previous_credential_sha256":old_id,
                "attestation":"Different newly issued credential; prior charges remain held on the original credential."}
            source=self.proposal(project,value)
            with patch.object(guard,"CloudStore",return_value=self.store):
                guard.reconcile(project,source,"Synthetic Owner","a"*64,"123","Synthetic credential rotation test only")
            self.assertTrue(guard.inspect(PROVIDER,store=self.store)["inference_eligible"])
            retained,_=self.store.read(guard.BRANCH,"relay-guard",old_id+".json")
            self.assertEqual(retained,old)
            self.assertTrue(retained["legacy_holds"])

    def test_owner_cannot_clear_legacy_holds_while_original_ledger_is_unknown(self):
        self.historical()
        with self.assertRaises(guard.RelayGuardError):self.begin()
        held=list(self.active()["legacy_holds"])
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"original-project"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_legacy","credential_sha256":guard.fingerprint(PROVIDER),"hold_ids":held})
            with self.assertRaisesRegex(guard.RelayGuardError,"still lacks independent debit"):
                guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
            branch,name=guard.SOURCES[1]
            self.store.put(branch,"trial-state",name,{"entries":[{"provider":PROVIDER,"call_id":PROVIDER+"|historical-unknown","billing_status":"settled",
                "model":"gemini-4-argon","meter_before":self.meter(),"actual_cost_cny":0.125,
                "reserved_ceiling_cny":0.431508,"debit_evidence":self.debit()["debit_evidence"]}]})
            with patch.object(guard,"CloudStore",return_value=self.store):
                guard.reconcile(project,source,"Synthetic Owner","a"*64,"123","Synthetic exact legacy reconciliation")
            self.assertTrue(guard.inspect(PROVIDER,store=self.store)["inference_eligible"])
            self.assertEqual(self.active()["reconciled_legacy_ids"],held)

    def test_legacy_source_deletion_relabel_and_duplicate_never_prove_settlement(self):
        self.historical()
        with self.assertRaises(guard.RelayGuardError):self.begin()
        held=list(self.active()["legacy_holds"])
        branch,name=guard.SOURCES[1]
        entry={"provider":PROVIDER,"call_id":PROVIDER+"|historical-unknown","billing_status":"settled",
            "model":"gemini-4-argon","meter_before":self.meter(),"actual_cost_cny":0.125,
            "reserved_ceiling_cny":0.431508,"debit_evidence":self.debit()["debit_evidence"]}
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"original-project"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_legacy","credential_sha256":guard.fingerprint(PROVIDER),"hold_ids":held})
            for rows in ([],[{**entry,"provider":"codekey-deepseek"}],[entry,copy.deepcopy(entry)]):
                with self.subTest(rows=len(rows)):
                    self.store.put(branch,"trial-state",name,{"entries":rows})
                    with self.assertRaisesRegex(guard.RelayGuardError,"missing, duplicated or assigned"):
                        guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
                    self.assertEqual(list(self.active()["legacy_holds"]),held)

    def test_malformed_settled_proof_remains_held_on_first_import_and_owner_release(self):
        branch,name=guard.SOURCES[1]
        entry={"provider":PROVIDER,"call_id":PROVIDER+"|malformed","billing_status":"settled",
            "model":"gemini-4-argon","meter_before":self.meter(),"actual_cost_cny":0.125,
            "reserved_ceiling_cny":1,"debit_evidence":{"anything":True}}
        self.store.put(branch,"trial-state",name,{"entries":[entry]})
        with self.assertRaises(guard.RelayGuardError):self.begin()
        held=list(self.active()["legacy_holds"])
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"original-project"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_legacy","credential_sha256":guard.fingerprint(PROVIDER),"hold_ids":held})
            with self.assertRaisesRegex(guard.RelayGuardError,"still lacks independent debit"):
                guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)

    def test_review_snapshot_changes_when_remote_source_proof_changes(self):
        self.historical()
        with self.assertRaises(guard.RelayGuardError):self.begin()
        held=list(self.active()["legacy_holds"]);branch,name=guard.SOURCES[1]
        entry={"provider":PROVIDER,"call_id":PROVIDER+"|historical-unknown","billing_status":"settled",
            "model":"gemini-4-argon","meter_before":self.meter(),"actual_cost_cny":0.125,
            "reserved_ceiling_cny":0.431508,"debit_evidence":self.debit()["debit_evidence"]}
        self.store.put(branch,"trial-state",name,{"entries":[entry]})
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"original-project"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_legacy","credential_sha256":guard.fingerprint(PROVIDER),"hold_ids":held})
            first=guard.reconciliation_snapshot(project,source,"Synthetic Owner",store=self.store)
            entry["debit_evidence"]["proof_note"]="A second independently reviewed source receipt."
            self.store.put(branch,"trial-state",name,{"entries":[entry]})
            second=guard.reconciliation_snapshot(project,source,"Synthetic Owner",store=self.store)
            self.assertEqual(first["state"],second["state"])
            a=first["resolved_proposal"]["resolved_legacy"][0];b=second["resolved_proposal"]["resolved_legacy"][0]
            self.assertNotEqual(a["source_blob_sha"],b["source_blob_sha"])
            self.assertNotEqual(a["entry_sha256"],b["entry_sha256"])

    def test_legacy_request_binding_cannot_be_rewritten_during_unknown_charge_import(self):
        branch,name=guard.SOURCES[1]
        entry={"provider":PROVIDER,"call_id":PROVIDER+"|original-bound-call","billing_status":"reserved",
            "model":"gemini-4-argon","meter_before":self.meter(),"reserved_ceiling_cny":1}
        self.store.put(branch,"trial-state",name,{"entries":[entry]})
        with self.assertRaises(guard.RelayGuardError):self.begin()
        held=list(self.active()["legacy_holds"])
        entry["model"]="gemini-4-argon-high"
        self.store.put(branch,"trial-state",name,{"entries":[entry]})
        with self.assertRaises(guard.RelayGuardError):self.begin()
        self.assertEqual(self.active()["legacy_holds"][held[0]]["request_binding"]["model"],"gemini-4-argon")
        entry.update(billing_status="settled",actual_cost_cny=0.125,debit_evidence=self.debit()["debit_evidence"])
        self.store.put(branch,"trial-state",name,{"entries":[entry]})
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"original-project"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_legacy","credential_sha256":guard.fingerprint(PROVIDER),"hold_ids":held})
            with self.assertRaisesRegex(guard.RelayGuardError,"original held request/model/before-meter"):
                guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)

    def test_legacy_reconciliation_checks_the_held_alias_provider_not_the_selected_group(self):
        other="codekey-codex-pro";setting=ai_providers.PRODUCTION_PROVIDERS[other]["key_setting"]
        with patch.dict(os.environ,{setting:os.environ[KEY_SETTING]}):
            self.historical(other)
            with self.assertRaises(guard.RelayGuardError):self.begin()
            held=list(self.active()["legacy_holds"]);branch,name=guard.SOURCES[1]
            with tempfile.TemporaryDirectory() as temporary:
                project=Path(temporary)/"original-project"
                source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_legacy","credential_sha256":guard.fingerprint(PROVIDER),"hold_ids":held})
                with self.assertRaisesRegex(guard.RelayGuardError,"still lacks independent debit"):
                    guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
                entry={"provider":other,"call_id":other+"|historical-unknown","model":"gpt-6.1-sol",
                    "billing_status":"settled","actual_cost_cny":0.125,"reserved_ceiling_cny":0.431508,
                    "meter_before":{**self.meter(),"provider":other},"debit_evidence":self.debit()["debit_evidence"]}
                self.store.put(branch,"trial-state",name,{"entries":[entry]})
                resolved=guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)[0]
                self.assertEqual(resolved["resolved_legacy"][0]["provider"],other)

    def test_original_cheapai_whole_key_proofs_and_old_codekey_counters_remain_supported(self):
        cheap="cheapai-gpt-pro";setting=ai_providers.PRODUCTION_PROVIDERS[cheap]["key_setting"]
        branch,name=guard.SOURCES[0]
        with patch.dict(os.environ,{setting:"synthetic-old-cheapai-key"}):
            entry={"call_id":cheap+"|gpt-6.1-sol|evidence","status":"gateway_debit_verified",
                "gateway_debit_cny":0.000388,"reserved_ceiling_cny":1,"debit_evidence":{
                    "source":"https://cheapai.info/api/log/token","unit_source":"https://cheapai.info/api/status",
                    "quota_per_unit":500000,"model":"gpt-6.1-sol","quota":194,"created_at":1792341993,
                    "prompt_tokens":165,"completion_tokens":143,"all_key_debits_match_attempt_count":True,"no_generation_retry":True}}
            self.store.put(branch,"trial-state",name,{"entries":[entry]})
            self.assertEqual(guard.source_holds(cheap,self.store),[])
            broken=copy.deepcopy(entry);broken["debit_evidence"]["no_generation_retry"]=False
            self.store.put(branch,"trial-state",name,{"entries":[broken]})
            self.assertEqual(len(guard.source_holds(cheap,self.store)),1)
        old={"kind":"codekey_total_actual_cost","requests":20,"cost_cny":2.0,"currency_rule":"Synthetic old format"}
        proof=self.debit()["debit_evidence"];proof["before"]={**old};proof["after"]={**old,"requests":21,"cost_cny":2.125}
        self.store.put(branch,"trial-state",name,{"entries":[{"call_id":PROVIDER+"|gemini-4-argon|evidence",
            "status":"gateway_debit_verified","gateway_debit_cny":0.125,"reserved_ceiling_cny":1,
            "gateway_meter_before":old,"debit_evidence":proof}]})
        self.assertEqual(guard.source_holds(PROVIDER,self.store),[])

    def test_original_cheapai_whole_key_prefix_survives_later_per_call_receipts(self):
        cheap="cheapai-gpt-pro";branch,name=guard.SOURCES[0]
        prefix=[]
        for model,quota,at in (("gpt-6.1-sol",194,1792341993),("gpt-6-astra",1238,1792341999)):
            prefix.append({"call_id":cheap+"|"+model+"|evidence","status":"gateway_debit_verified",
                "gateway_debit_cny":quota/500000,"reserved_ceiling_cny":1,"debit_evidence":{
                    "source":"https://cheapai.info/api/log/token","quota_per_unit":500000,
                    "model":model,"quota":quota,"created_at":at,"prompt_tokens":165,"completion_tokens":143,
                    "all_key_debits_match_attempt_count":True,"no_generation_retry":True}})
        before_rows=[guard._row(entry["debit_evidence"]) for entry in prefix]
        later={"call_id":cheap+"|gpt-6.1-sol|engineering","status":"gateway_debit_verified",
            "gateway_debit_cny":284/500000,"reserved_ceiling_cny":1,
            "gateway_meter_before":{"kind":"cheapai_quota_history","quota_per_unit":500000,"rows":before_rows},
            "debit_evidence":{"source":"https://cheapai.info/api/log/token","quota_per_unit":500000,
                "model":"gpt-6.1-sol","quota":284,"created_at":1792344019,"prompt_tokens":147,"completion_tokens":229,
                "exactly_one_new_gateway_request":True}}
        entries=prefix+[later]
        self.store.put(branch,"trial-state",name,{"entries":entries})
        self.assertEqual(guard.source_holds(cheap,self.store),[])
        # A later unaccounted call remains held independently; valid old debits
        # must not become unknown merely because the trial has been extended.
        unknown={"call_id":cheap+"|gpt-6-astra|later-unknown","reserved_ceiling_cny":1,"status":"reserved_before_transport"}
        self.store.put(branch,"trial-state",name,{"entries":entries+[unknown]})
        self.assertEqual([row["call_id"] for row in guard.source_holds(cheap,self.store)],[unknown["call_id"]])
        # The first incremental snapshot must contain the complete original
        # bijection, and whole-key flags cannot resume after incremental calls.
        missing=copy.deepcopy(entries);missing[-1]["gateway_meter_before"]["rows"].pop()
        self.store.put(branch,"trial-state",name,{"entries":missing})
        self.assertTrue({e["call_id"] for e in prefix} <= {h["call_id"] for h in guard.source_holds(cheap,self.store)})
        resumed=copy.deepcopy(prefix[0]);resumed["call_id"]=cheap+"|gpt-6.1-sol|resumed-batch"
        self.store.put(branch,"trial-state",name,{"entries":entries+[resumed]})
        self.assertTrue({e["call_id"] for e in prefix} <= {h["call_id"] for h in guard.source_holds(cheap,self.store)})

    def trial(self):
        plan=json.loads((comparison.ROOT/"config/model-comparison-20261020.json").read_text(encoding="utf-8"))
        route=next(r for r in plan["candidates"] if r["provider"]==PROVIDER)
        case=route["screening_cases"][0];call_id=route["id"]+"|"+case
        ticket=guard.begin(PROVIDER,scope={"trial":comparison.TRIAL,"call_id":call_id},max_cost_cny=1,store=self.store)
        guard.bind_meter(ticket,route["model"],self.meter(),store=self.store);self.send()
        ledger=comparison.new_ledger(plan)
        entry={"provider":PROVIDER,"call_id":call_id,"candidate_id":route["id"],"model":route["model"],"effort":route["effort"],
            "case_id":case,"case_sha256":comparison.digest(comparison.fixtures.case(case)),"run_id":"123",
            "reserved_ceiling_cny":1,"meter_before":self.meter(),"billing_status":"settled","actual_cost_cny":0.125,
            "generation_status":"response_failed","debit_evidence":self.debit()["debit_evidence"]}
        ledger["entries"].append(entry)
        self.store.put(comparison.STATE,"trial-state",comparison.FILE,ledger)
        return ticket,ledger,entry

    def test_exact_accounted_trial_settlement_releases_shared_ticket_without_budget_or_generation(self):
        ticket,ledger,entry=self.trial();original=copy.deepcopy(ledger)
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"owner-control-project"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_trial","credential_sha256":guard.fingerprint(PROVIDER),"ticket_id":ticket["id"]})
            with patch.object(guard,"CloudStore",return_value=self.store),patch.object(relay_billing,"settle",return_value=self.debit()), \
                    patch.object(ai_providers,"call_production") as post,patch.object(model_spend,"write") as budget:
                snapshot=guard.reconciliation_snapshot(project,source,"Synthetic Owner")
                resolved=snapshot["resolved_proposal"]["resolved_trial"]
                self.assertEqual(resolved["entry_sha256"],relay_billing._fingerprint(entry))
                self.assertEqual(resolved["source_blob_sha"],self.store.read(comparison.STATE,"trial-state",comparison.FILE)[1])
                guard.reconcile(project,source,"Synthetic Owner","c"*64,"123","Synthetic exact comparison debit review")
                post.assert_not_called();budget.assert_not_called()
            self.assertIsNone(self.active()["active"])
            self.assertEqual(self.active()["events"][-2]["status"],"owner_settled_trial")
            self.assertEqual(self.store.read(comparison.STATE,"trial-state",comparison.FILE)[0],original)

    def test_trial_owner_release_rejects_wrong_ticket_before_meter_and_independent_fee(self):
        ticket,ledger,entry=self.trial()
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"owner-control-project"
            proposal={"provider":PROVIDER,"kind":"settled_trial","credential_sha256":guard.fingerprint(PROVIDER),"ticket_id":"wrong"}
            source=self.proposal(project,proposal)
            with self.assertRaisesRegex(guard.RelayGuardError,"exact shared comparison ticket"):
                guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
            proposal["ticket_id"]=ticket["id"];self.proposal(project,proposal)
            entry["meter_before"]={**self.meter(),"requests":19}
            self.store.put(comparison.STATE,"trial-state",comparison.FILE,ledger)
            with self.assertRaisesRegex(guard.RelayGuardError,"exact shared ticket"):
                guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
            entry["meter_before"]=self.meter();self.store.put(comparison.STATE,"trial-state",comparison.FILE,ledger)
            with patch.object(relay_billing,"settle",return_value=self.debit(0.2)):
                with self.assertRaisesRegex(guard.RelayGuardError,"original accounted trial cost"):
                    guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
            self.assertEqual(self.active()["active"],ticket)

    def test_clarified_settlement_uses_immutable_original_parent_after_current_parent_changes(self):
        class ArchiveStore(MemoryStore):
            def __init__(self):
                self.archives={};self.blob_reads=[];super().__init__()
            def put(self,*args):
                blob=super().put(*args);self.archives[blob]=copy.deepcopy(args[-1]);return blob
            def read_blob(self,blob):
                self.blob_reads.append(blob)
                if blob not in self.archives:raise guard.RelayGuardError("original parent blob unavailable")
                return copy.deepcopy(self.archives[blob])
        store=ArchiveStore()
        plan=json.loads((comparison.ROOT/"config/model-comparison-20261020.json").read_text(encoding="utf-8"))
        with patch.object(model_runtime,"pricing",return_value={"quote_sha256":"b"*64}), \
                patch.object(model_runtime,"reservation_bound",return_value=1.0):
            parent=comparison.new_ledger(plan)
            comparison.authorize_complete(plan,parent,"a"*40,"a"*40,comparison.FULL_AUTHORIZATION,lambda _:None)
            parent["status"]="closed"
            parent_blob=store.put(comparison.STATE,"trial-state",comparison.FILE,parent)
            contract=clarified.scope(plan,parent,parent_blob)
        route=next(r for r in contract["configurations"] if r["provider"]=="codekey-deepseek")
        provider=route["provider"];case=clarified.CASE_IDS[0];call_id=route["id"]+"|"+case
        setting=ai_providers.PRODUCTION_PROVIDERS[provider]["key_setting"]
        before={**self.meter(),"provider":provider}
        with patch.dict(os.environ,{setting:"synthetic-clarified-history-key"}):
            ticket=guard.begin(provider,scope={"trial":clarified.TRIAL,"call_id":call_id},max_cost_cny=1,store=store)
            guard.bind_meter(ticket,route["model"],before,store=store)
            guard.authorize_transport("https://codekey.ai/v1/chat/completions",{"Authorization":"Bearer synthetic-clarified-history-key"})
            ledger=clarified.new_ledger(contract,parent)
            ledger["entries"].append({"provider":provider,"call_id":call_id,"candidate_id":route["id"],"model":route["model"],"effort":route["effort"],
                "case_id":case,"case_sha256":clarified.digest(clarified.fixtures.case(case)),"run_id":"123",
                "quote_sha256":contract["quote_sha256_by_candidate"][route["id"]],"reserved_ceiling_cny":1,
                "meter_before":before,"billing_status":"settled","actual_cost_cny":0.125,"debit_evidence":self.debit()["debit_evidence"]})
            store.put(comparison.STATE,"trial-state",clarified.FILE,ledger)
            current={**parent,"operator_reviews":[{"note":"Later legitimate independent billing reconciliation."}]}
            current_blob=store.put(comparison.STATE,"trial-state",comparison.FILE,current)
            self.assertNotEqual(parent_blob,current_blob)
            with tempfile.TemporaryDirectory() as temporary:
                project=Path(temporary)/"owner-control-project"
                source=self.proposal(project,{"provider":provider,"kind":"settled_trial","credential_sha256":guard.fingerprint(provider),"ticket_id":ticket["id"]})
                with patch.object(relay_billing,"settle",return_value=self.debit()),patch.object(model_runtime,"pricing") as price:
                    proposal=guard.prepare_reconciliation(project,source,"Synthetic Owner",store=store)[0]
                    price.assert_not_called()
                self.assertEqual(proposal["resolved_trial"]["original_parent_blob_sha"],parent_blob)
                self.assertEqual(store.blob_reads,[parent_blob])
                self.assertEqual(store.read(comparison.STATE,"trial-state",comparison.FILE)[1],current_blob)
                store.archives.pop(parent_blob)
                with self.assertRaisesRegex(guard.RelayGuardError,"original parent blob unavailable"):
                    guard.prepare_reconciliation(project,source,"Synthetic Owner",store=store)

    def test_owner_active_reconciliation_needs_original_project_and_matching_budget_event(self):
        ticket=self.begin();self.bind(ticket);self.send()
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"original-project"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_active","credential_sha256":guard.fingerprint(PROVIDER),"ticket_id":ticket["id"]})
            budget={"reservations":{},"reconciliation_events":[],"settlement_events":[]}
            with patch.object(relay_billing,"settle",return_value=self.debit()),patch.object(model_spend,"read",return_value=budget):
                with self.assertRaisesRegex(guard.RelayGuardError,"project reconciliation"):
                    guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
                budget["settlement_events"]=[{"receipt_id":"local-reservation","actual_cost_cny":0.125}]
                with patch.object(guard,"CloudStore",return_value=self.store):
                    guard.reconcile(project,source,"Synthetic Owner","b"*64,"123","Synthetic original-project exact debit confirmation")
            self.assertIsNone(self.active()["active"])
            self.assertEqual(self.active()["events"][-2]["status"],"owner_settled_active")

    def test_real_production_runtime_catalog_pass_cannot_bypass_historical_unknown_hold(self):
        provider="cheapai-gpt-pro";key=ai_providers.PRODUCTION_PROVIDERS[provider]["key_setting"]
        self.historical(provider)
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{key:"synthetic-production-key","DR_OS_ROUTING_PROFILE":"production","DR_OS_REQUIRE_MODEL_AUTH":"1","DR_OS_REQUIRE_REMOTE_RESERVATION":"1"}):
            project=Path(temporary)/"production-fixture";write(project/"state/run.json",{"active_paper":"P01"})
            model_spend.write(project,model_spend.initial());model_spend.grant(project,new_ceiling_cny=300,actor="Synthetic Owner",run_id="fixture-only")
            with patch.object(guard,"CloudStore",return_value=self.store),patch("scripts.production_readiness.catalog",return_value={"gpt-6.1-sol"}) as catalog, \
                    patch("scripts.cloud_checkpoint.sync_billing"),patch.object(relay_billing,"read_meter") as meter,patch.object(ai_providers,"call") as post:
                with self.assertRaisesRegex(guard.RelayGuardError,"historical"):
                    model_runtime.call(project,run_id="fixture",stage="intake",role="persistent-writer",provider="openai",prompt="Synthetic work only",max_output_tokens=100)
                catalog.assert_called_once();meter.assert_not_called();post.assert_not_called()
            state=model_spend.read(project)
            self.assertEqual(state["spent_cny"],0);self.assertEqual(state["reservations"],{})
            self.assertEqual(len(state["unsent_events"]),1)


if __name__=="__main__":unittest.main()

