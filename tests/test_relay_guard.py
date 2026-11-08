"""Real shared relay control with an isolated CAS store; no external services."""
from __future__ import annotations
import base64
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ai_providers,model_runtime,model_spend,relay_billing,relay_guard as guard
from scripts.research_artifacts import write
from tests.relay_guard_fixtures import MemoryStore

PROVIDER="codekey-gemini"
KEY_SETTING=ai_providers.PRODUCTION_PROVIDERS[PROVIDER]["key_setting"]
COMPARISON="model-comparison-20261020"
CLARIFIED="model-comparison-clarified-20261020"


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

    def import_holds(self):
        """Fixture snapshot of previously imported history, never a new lease."""
        _,name,value,_=guard.load(PROVIDER,store=self.store)
        self.store.put(guard.BRANCH,"relay-guard",name,value)

    def legacy_active(self,*,provider=PROVIDER,scope=None,model="gemini-4-argon",before=None,store=None):
        """Retained historical ticket data; this helper authorizes no transport."""
        store=self.store if store is None else store
        ticket={"id":"synthetic-retained-legacy-ticket","provider":provider,"credential_sha256":guard.fingerprint(provider),
            "scope":scope or {"project":"original-project","reservation_id":"local-reservation"},"max_cost_cny":1,"run_id":"123"}
        store.put(guard.BRANCH,"relay-guard",ticket["credential_sha256"]+".json",{
            "schema_version":"1.0","credential_sha256":ticket["credential_sha256"],"legacy_holds":{},"active":ticket,
            "active_meter":{"model":model,"before":self.meter() if before is None else before},"events":[]})
        return ticket

    def meter(self):
        return {"provider":PROVIDER,"kind":"codekey_total_actual_cost","requests":20,"cost_cny":2.0}

    def debit(self,cost=0.125):
        return {"actual_cost_cny":cost,"debit_evidence":{"source":"https://codekey.ai/v1/usage",
            "before":{"requests":20,"cost_cny":2.0},"after":{"requests":21,"cost_cny":2.0+cost},"exactly_one_new_gateway_request":True}}

    def active(self):
        return self.store.read(guard.BRANCH,"relay-guard",guard.fingerprint(PROVIDER)+".json")[0]

    def test_historical_unknown_remains_held_after_readonly_catalog_success(self):
        self.historical()
        self.import_holds()
        with patch("scripts.production_readiness.catalog",return_value={"gemini-4-argon"}) as catalog:
            self.assertIn("gemini-4-argon",catalog(PROVIDER,dict(os.environ)))
            self.assertFalse(guard.inspect(PROVIDER,store=self.store)["inference_eligible"])
        self.assertEqual(len(self.active()["legacy_holds"]),1)
        self.assertIsNone(self.active()["active"])

    def test_same_credential_across_different_group_imports_original_holds(self):
        other="codekey-codex-pro"
        with patch.dict(os.environ,{ai_providers.PRODUCTION_PROVIDERS[other]["key_setting"]:os.environ[KEY_SETTING]}):
            self.historical(other)
            self.import_holds()
        self.assertEqual(next(iter(self.active()["legacy_holds"].values()))["provider"],other)

    def test_closed_trial_authorization_never_clears_existing_holds(self):
        holds={"44064d7e5133c1c82704269da0095f60541c12e8c24be1560eac5e67920f46e9":{"reserved_ceiling_cny":.431508},
            "f6da77fa19739e14aedd1e040301f29d85ee7f899c840b2fd7138cc7dc44b5e9":{"reserved_ceiling_cny":9.1521024}}
        self.store.put(guard.BRANCH,"relay-guard",guard.fingerprint(PROVIDER)+".json",{
            "schema_version":"1.0","credential_sha256":guard.fingerprint(PROVIDER),"legacy_holds":holds,"active":None,"events":[]})
        for trial,setting in (("writing-comparison-20261027","WRITING_COMPARISON_AUTHORIZATION"),
                              (guard.EVALUATION_TRIAL,"MODEL_EVALUATION_AUTHORIZATION")):
            authorization=trial+"-owner-paid-with-legacy-holds"
            with self.subTest(trial=trial),patch.dict(os.environ,{setting:authorization,"GITHUB_ACTOR":"hengyizang",
                    "GITHUB_REF":"refs/heads/codex/"+trial,"GITHUB_EVENT_NAME":"workflow_dispatch"}):
                self.assertFalse(guard.inspect(PROVIDER,store=self.store)["inference_eligible"])
            self.assertEqual(self.active()["legacy_holds"],holds)
            self.assertIsNone(self.active()["active"])
            self.assertIsNone(guard._TICKET.get())

    def test_cloud_store_requires_exact_blob_identity_and_put_readback(self):
        store=guard.CloudStore()
        with patch.object(store,"api",side_effect=[{"sha":"a"*40},{"content":base64.b64encode(b"{}").decode()}]):
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

    def test_cheapai_receipt_must_match_the_retained_before_snapshot_and_model(self):
        provider="cheapai-gpt-pro";key=ai_providers.PRODUCTION_PROVIDERS[provider]["key_setting"]
        with patch.dict(os.environ,{key:"synthetic-cheapai-key"}):
            before={"provider":provider,"kind":"cheapai_quota_history","quota_per_unit":500000,"rows":[]}
            meter={"model":"gpt-6.1-sol","before":before}
            settlement={"actual_cost_cny":0.1,"debit_evidence":{"source":"https://cheapai.info/api/log/token","exactly_one_new_gateway_request":True,
                "before_snapshot_sha256":relay_billing._fingerprint({"rows":[]}),"row":{"model_name":"gpt-6-astra","quota":50000}}}
            with self.assertRaisesRegex(guard.RelayGuardError,"before meter/model"):
                guard.validate_debit(meter,settlement)
            settlement["debit_evidence"]["row"]["model_name"]="gpt-6.1-sol"
            guard.validate_debit(meter,settlement)

    def proposal(self,project,value):
        path=project/"program/reconcile.json";write(path,value);return "program/reconcile.json"

    def test_rotated_credential_requires_owner_attestation_and_preserves_the_original_hold(self):
        self.historical()
        self.import_holds()
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
        self.import_holds()
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
        self.import_holds()
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
        self.import_holds()
        held=list(self.active()["legacy_holds"])
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"original-project"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_legacy","credential_sha256":guard.fingerprint(PROVIDER),"hold_ids":held})
            with self.assertRaisesRegex(guard.RelayGuardError,"still lacks independent debit"):
                guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)

    def test_review_snapshot_changes_when_remote_source_proof_changes(self):
        self.historical()
        self.import_holds()
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
        self.import_holds()
        held=list(self.active()["legacy_holds"])
        entry["model"]="gemini-4-argon-high"
        self.store.put(branch,"trial-state",name,{"entries":[entry]})
        self.import_holds()
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
            self.import_holds()
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

    def pin_trial(self,trial,ledger,store=None):
        store=self.store if store is None else store
        branch,name=guard.TRIAL_SOURCES[trial]
        original=store.put(branch,"trial-state",name,ledger)
        pinned=patch.dict(guard.TRIAL_ORIGINALS,{trial:original})
        pinned.start();self.addCleanup(pinned.stop)
        return original

    def trial(self):
        """Frozen native ledger shape; never call an old generator or quote."""
        call_id="synthetic-argon-high|synthetic-case"
        ticket=self.legacy_active(scope={"trial":COMPARISON,"call_id":call_id})
        entry={"provider":PROVIDER,"call_id":call_id,"candidate_id":"synthetic-argon-high","model":"gemini-4-argon","effort":"high",
            "case_id":"synthetic-case","case_sha256":"a"*64,"quote_sha256":"b"*64,"run_id":"123",
            "reserved_ceiling_cny":1,"meter_before":self.meter(),"billing_status":"settled","actual_cost_cny":0.125,
            "generation_status":"response_failed","debit_evidence":self.debit()["debit_evidence"]}
        prefix={**entry,"call_id":"synthetic-prefix|case","text":"Retained original synthetic response"}
        ledger={"schema_version":"1.0","trial_id":COMPARISON,"authorization_id":"synthetic-owner-authorized-scope",
            "authorization":{"max_calls":2},"limit_cny":2,"plan_sha256":"c"*64,"status":"closed_with_holds",
            "entries":[prefix,entry],"production_routing_changed":False,"scientific_completion":False,
            "full_matrix_authorization":{"original_entries_count":1,"original_entries_sha256":guard._digest([prefix]),
                "scope_contract":{"plan_sha256":"c"*64,"ceiling_cny":2,"max_calls":2,"paid_retries_authorized":False}}}
        self.pin_trial(COMPARISON,ledger)
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
                branch,name=guard.TRIAL_SOURCES[COMPARISON]
                self.assertEqual(resolved["source_blob_sha"],self.store.read(branch,"trial-state",name)[1])
                self.assertEqual(resolved["original_trial_blob_sha"],guard.TRIAL_ORIGINALS[COMPARISON])
                guard.reconcile(project,source,"Synthetic Owner","c"*64,"123","Synthetic exact comparison debit review")
                post.assert_not_called();budget.assert_not_called()
            self.assertIsNone(self.active()["active"])
            self.assertEqual(self.active()["events"][-2]["status"],"owner_settled_trial")
            self.assertEqual(self.store.read(branch,"trial-state",name)[0],original)

    def test_trial_owner_release_rejects_wrong_ticket_before_meter_and_independent_fee(self):
        ticket,ledger,entry=self.trial()
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"owner-control-project"
            proposal={"provider":PROVIDER,"kind":"settled_trial","credential_sha256":guard.fingerprint(PROVIDER),"ticket_id":"wrong"}
            source=self.proposal(project,proposal)
            with self.assertRaisesRegex(guard.RelayGuardError,"exact shared comparison ticket"):
                guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
            proposal["ticket_id"]=ticket["id"];self.proposal(project,proposal)
            state=self.active();state["active_meter"]["before"]["requests"]=19
            self.store.put(guard.BRANCH,"relay-guard",guard.fingerprint(PROVIDER)+".json",state)
            with self.assertRaisesRegex(guard.RelayGuardError,"exact shared ticket"):
                guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
            state["active_meter"]["before"]=self.meter()
            self.store.put(guard.BRANCH,"relay-guard",guard.fingerprint(PROVIDER)+".json",state)
            with patch.object(relay_billing,"settle",return_value=self.debit(0.2)):
                with self.assertRaisesRegex(guard.RelayGuardError,"original accounted trial cost"):
                    guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
            self.assertEqual(self.active()["active"],ticket)

    def test_frozen_trial_rejects_nonbilling_changes_and_rewriting_a_settled_charge(self):
        ticket,ledger,_=self.trial();branch,name=guard.TRIAL_SOURCES[COMPARISON]
        changes=[("authorization",lambda value:value["full_matrix_authorization"]["scope_contract"].update(max_calls=3)),
            ("bool as number",lambda value:value.update(scientific_completion=0)),
            ("integer as float",lambda value:value["entries"][-1].update(reserved_ceiling_cny=1.0)),
            ("absent as null",lambda value:value["entries"][-1].update(request_id=None)),
            ("deleted field",lambda value:value["entries"][-1].pop("effort")),
            ("quote",lambda value:value["entries"][-1].update(quote_sha256="d"*64)),
            ("old settled cost",lambda value:value["entries"][-1].update(actual_cost_cny=.2)),
            ("other response",lambda value:value["entries"][0].update(text="Changed original response")),
            ("reordered attempts",lambda value:value["entries"].reverse())]
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"owner-control-project"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_trial",
                "credential_sha256":guard.fingerprint(PROVIDER),"ticket_id":ticket["id"],"original_blob_sha":"0"*40})
            with patch.object(relay_billing,"settle") as meter:
                for label,change in changes:
                    changed=copy.deepcopy(ledger);change(changed);self.store.put(branch,"trial-state",name,changed)
                    with self.subTest(change=label),self.assertRaisesRegex(guard.RelayGuardError,"immutable original"):
                        guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
                    self.assertEqual(self.active()["active"],ticket)
                meter.assert_not_called()

    def test_original_reserved_trial_can_only_gain_an_independently_verified_settlement(self):
        ticket,current,_=self.trial();branch,name=guard.TRIAL_SOURCES[COMPARISON]
        original=copy.deepcopy(current);entry=original["entries"][-1]
        entry["billing_status"]="reserved";entry.pop("actual_cost_cny");entry.pop("debit_evidence")
        original_blob=self.pin_trial(COMPARISON,original)
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"owner-control-project"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_trial",
                "credential_sha256":guard.fingerprint(PROVIDER),"ticket_id":ticket["id"]})
            with patch.object(relay_billing,"settle") as meter:
                with self.assertRaisesRegex(guard.RelayGuardError,"independent debit"):
                    guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
                meter.assert_not_called()
            self.store.put(branch,"trial-state",name,current)
            with patch.object(relay_billing,"settle",return_value=self.debit()):
                proposal=guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)[0]
            self.assertEqual(proposal["resolved_trial"]["original_trial_blob_sha"],original_blob)
            self.assertNotEqual(proposal["resolved_trial"]["source_blob_sha"],original_blob)
            self.assertEqual(self.active()["active"],ticket)

    def test_clarified_settlement_uses_immutable_original_parent_after_current_parent_changes(self):
        store=MemoryStore();parent_branch,parent_name=guard.TRIAL_SOURCES[COMPARISON]
        parent={"trial_id":COMPARISON,"status":"closed_with_holds","plan_sha256":"c"*64,
            "entries":[{"call_id":"synthetic-held-prefix","billing_status":"reserved","reserved_ceiling_cny":.5}],
            "full_matrix_authorization":{"scope_contract":{"max_calls":128,"ceiling_cny":241.09388247}}}
        parent_blob=self.pin_trial(COMPARISON,parent,store)
        provider="codekey-deepseek";call_id="synthetic-deepseek-high|synthetic-case"
        setting=ai_providers.PRODUCTION_PROVIDERS[provider]["key_setting"]
        before={**self.meter(),"provider":provider}
        with patch.dict(os.environ,{setting:"synthetic-clarified-history-key"}):
            ticket=self.legacy_active(provider=provider,scope={"trial":CLARIFIED,"call_id":call_id},model="deepseek-v3.2",before=before,store=store)
            ledger={"trial_id":CLARIFIED,"status":"closed","scope":{"authorization_id":"synthetic-clarified-owner-scope",
                "parent_blob_sha":parent_blob,"parent_ledger_sha256":guard._digest(parent),"parent_plan_sha256":parent["plan_sha256"],
                "parent_attempts":1,"parent_outstanding_holds_cny":.5,"fixture_sha256":"a"*64,
                "quote_sha256_by_candidate":{"synthetic-deepseek-high":"b"*64},"max_calls":16,"max_combined_calls":128},
                "entries":[{"provider":provider,"call_id":call_id,"candidate_id":"synthetic-deepseek-high","model":"deepseek-v3.2","effort":"high",
                    "case_id":"synthetic-case","case_sha256":"a"*64,"run_id":"123","quote_sha256":"b"*64,"reserved_ceiling_cny":1,
                    "meter_before":before,"billing_status":"settled","actual_cost_cny":0.125,"debit_evidence":self.debit()["debit_evidence"]}]}
            original_blob=self.pin_trial(CLARIFIED,ledger,store)
            current={**parent,"operator_reviews":[{"note":"Later legitimate independent billing reconciliation."}]}
            current_blob=store.put(parent_branch,"trial-state",parent_name,current)
            self.assertNotEqual(parent_blob,current_blob)
            with tempfile.TemporaryDirectory() as temporary:
                project=Path(temporary)/"owner-control-project"
                source=self.proposal(project,{"provider":provider,"kind":"settled_trial","credential_sha256":guard.fingerprint(provider),"ticket_id":ticket["id"]})
                with patch.object(relay_billing,"settle",return_value=self.debit()),patch.object(model_runtime,"pricing") as price, \
                        patch.object(store,"read_blob",wraps=store.read_blob) as original_read:
                    proposal=guard.prepare_reconciliation(project,source,"Synthetic Owner",store=store)[0]
                    price.assert_not_called()
                self.assertEqual(proposal["resolved_trial"]["original_parent_blob_sha"],parent_blob)
                self.assertEqual([call.args for call in original_read.call_args_list],[(original_blob,),(parent_blob,)])
                self.assertEqual(store.read(parent_branch,"trial-state",parent_name)[1],current_blob)
                branch,name=guard.TRIAL_SOURCES[CLARIFIED]
                for field,value in (("parent_blob_sha","0"*40),("parent_ledger_sha256","0"*64),("parent_plan_sha256","0"*64)):
                    malformed=copy.deepcopy(ledger);malformed["scope"][field]=value
                    # Stub a malformed authenticated original as well: the
                    # original-parent contract must still be internally exact.
                    store.blobs[original_blob]=copy.deepcopy(malformed)
                    store.put(branch,"trial-state",name,malformed)
                    with self.subTest(field=field),self.assertRaisesRegex(guard.RelayGuardError,"original parent"):
                        guard.prepare_reconciliation(project,source,"Synthetic Owner",store=store)
                store.blobs[original_blob]=copy.deepcopy(ledger);store.put(branch,"trial-state",name,ledger)
                store.blobs.pop(parent_blob)
                with self.assertRaisesRegex(guard.RelayGuardError,"original historical blob unavailable"):
                    guard.prepare_reconciliation(project,source,"Synthetic Owner",store=store)

    def evaluation_trial(self):
        """Real retained format with synthetic requests, meters and immutable IO."""
        import hashlib
        plan=json.loads((guard.ROOT/"config/model-evaluation-20261029.json").read_text())
        route=next(row for row in plan["routes"] if row["id"]=="argon-native-high")
        case=next(row for row in plan["cases"] if row["id"]=="discriminating-experiment")
        reservation="f705e87ba4514cb99c961768f59f4278"
        request={"call_id":route["id"]+"|"+case["id"],"route_id":route["id"],"case_id":case["id"],
            "case_sha256":guard._digest(case),"max_output_tokens":plan["max_output_tokens"],
            "timeout":300,"reserved_ceiling_cny":.4321632}
        entry={**{key:request[key] for key in ("call_id","route_id","case_id","case_sha256","reserved_ceiling_cny")},
            "task_class":case["task_class"],"partition":case["partition"],"provider":route["provider"],
            "requested_model":route["model"],"requested_effort":route["effort"],"project_reservation_id":reservation,
            "meter_before":self.meter(),"billing_status":"reserved","generation_status":"failed","run_id":"123",
            "code_sha":"a"*40,"diagnostic":"Synthetic failed response; its charge remains unknown.","duration_seconds":1.2}
        earlier={**entry,"call_id":"earlier-synthetic-call","generation_status":"completed","text":"Retained synthetic prior response",
            "billing_status":"settled","actual_cost_cny":.02}
        original={"trial_id":guard.EVALUATION_TRIAL,"status":"stopped","entries":[earlier,entry],
            "legacy_budget_reservations":{"gemini":"2b9e5e82da8a4f0bb9bfb6520ba814d1","deepseek":"b"*32},
            "scope":{"authorization":plan["authorization"],"project":"my-phd","project_ceiling_cny":500,"max_calls":40,
                "code_sha":"a"*40,"plan_sha256":guard._digest(plan),"routes":plan["routes"],"queue":[request],
                "prices_sha256":hashlib.sha256((guard.ROOT/"config/model-evaluation-pricing-20261029.json").read_bytes()).hexdigest()}}
        scope={"trial":guard.EVALUATION_TRIAL,"call_id":entry["call_id"],"authorization":plan["authorization"],
            "project_reservation_id":reservation,"legacy_budget_reservation_id":original["legacy_budget_reservations"]["gemini"]}
        ticket={"id":guard.EVALUATION_TICKET,"provider":PROVIDER,"credential_sha256":guard.fingerprint(PROVIDER),
            "scope":scope,"run_id":"123","max_cost_cny":entry["reserved_ceiling_cny"]}
        self.store.put(guard.BRANCH,"relay-guard",guard.fingerprint(PROVIDER)+".json",{
            "schema_version":"1.0","credential_sha256":guard.fingerprint(PROVIDER),"legacy_holds":{"retained-old-hold":{"provider":PROVIDER}},
            "active":ticket,"active_meter":{"model":entry["requested_model"],"before":self.meter()},"events":[]})
        current=copy.deepcopy(original)
        current["entries"][-1].update(billing_status="settled",actual_cost_cny=.125,
            debit_evidence=self.debit()["debit_evidence"],reconciled_at="2026-11-07T00:00:00Z")
        branch,name=guard.TRIAL_SOURCES[guard.EVALUATION_TRIAL]
        self.store.put(branch,"trial-state",name,current)
        budget={"reservations":{"unrelated-retained-hold":{}},"reconciliation_events":[{"receipt_id":reservation,"actual_cost_cny":.125}]}
        return original,current,ticket,budget

    def test_oct29_settlement_never_reopens_generation_or_discards_other_holds(self):
        original,current,ticket,budget=self.evaluation_trial()
        retained=copy.deepcopy(self.active()["legacy_holds"])
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"my-phd"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_trial",
                "credential_sha256":guard.fingerprint(PROVIDER),"ticket_id":ticket["id"]})
            with patch.object(self.store,"read_blob",return_value=original,create=True) as immutable, \
                 patch.object(guard,"CloudStore",return_value=self.store), \
                 patch.object(relay_billing,"settle",return_value=self.debit()), \
                 patch.object(model_spend,"read",return_value=budget), \
                 patch.object(model_spend,"write",side_effect=AssertionError("no budget writes")), \
                 patch.object(ai_providers,"call_production",side_effect=AssertionError("no generation")):
                before=copy.deepcopy(self.active())
                snapshot=guard.reconciliation_snapshot(project,source,"Synthetic Owner",store=self.store)
                self.assertEqual(snapshot["resolved_proposal"]["resolved_trial"]["original_trial_blob_sha"],guard.EVALUATION_ORIGINAL_BLOB)
                self.assertEqual(self.active(),before)
                guard.reconcile(project,source,"Synthetic Owner","c"*64,"123","Synthetic immutable debit-only review")
                self.assertTrue(all(call.args==(guard.EVALUATION_ORIGINAL_BLOB,) for call in immutable.call_args_list))
            self.assertIsNone(self.active()["active"])
            self.assertEqual(self.active()["legacy_holds"],retained)
            self.assertEqual(self.store.read(*guard.TRIAL_SOURCES[guard.EVALUATION_TRIAL][:1],"trial-state","ledger.json")[0],current)
            self.assertNotIn(guard.TRIAL_SOURCES[guard.EVALUATION_TRIAL],guard.SOURCES)

    def test_oct29_source_mutations_and_unknown_billing_never_release_the_active_ticket(self):
        original,current,ticket,budget=self.evaluation_trial()
        branch,name=guard.TRIAL_SOURCES[guard.EVALUATION_TRIAL]
        mutations=[("scope",lambda value:value["scope"].update(code_sha="b"*40)),
            ("other response",lambda value:value["entries"][0].update(text="Changed original response")),
            ("new target response",lambda value:value["entries"][-1].update(text="Invented accepted response")),
            ("removed target data",lambda value:value["entries"][-1].pop("diagnostic")),
            ("unknown bill",lambda value:value["entries"][-1].update(billing_status="reserved")),
            ("excess charge",lambda value:value["entries"][-1].update(actual_cost_cny=2)),
            ("extra metadata",lambda value:value.update(automatic_promotion=True)),
            ("extra source call",lambda value:value["entries"].append(copy.deepcopy(value["entries"][0])))]
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"my-phd"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_trial",
                "credential_sha256":guard.fingerprint(PROVIDER),"ticket_id":ticket["id"]})
            with patch.object(self.store,"read_blob",return_value=original,create=True), \
                 patch.object(model_spend,"read",return_value=budget),patch.object(relay_billing,"settle") as meter:
                for label,mutate in mutations:
                    with self.subTest(change=label):
                        changed=copy.deepcopy(current);mutate(changed)
                        self.store.put(branch,"trial-state",name,changed)
                        with self.assertRaises(guard.RelayGuardError):
                            guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
                        self.assertEqual(self.active()["active"],ticket)
                meter.assert_not_called()

    def test_oct29_requires_original_blob_plan_partition_ticket_and_independent_project_cost(self):
        original,current,ticket,budget=self.evaluation_trial()
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/"my-phd"
            source=self.proposal(project,{"provider":PROVIDER,"kind":"settled_trial",
                "credential_sha256":guard.fingerprint(PROVIDER),"ticket_id":ticket["id"]})
            def check():return guard.prepare_reconciliation(project,source,"Synthetic Owner",store=self.store)
            with patch.object(self.store,"read_blob",return_value=original,create=True) as immutable, \
                 patch.object(model_spend,"read",return_value=budget),patch.object(relay_billing,"settle",return_value=self.debit()) as meter:
                immutable.side_effect=guard.RelayGuardError("immutable original unavailable")
                with self.assertRaisesRegex(guard.RelayGuardError,"immutable original"):check()
                immutable.side_effect=None
                bad_original=copy.deepcopy(original);bad_original["scope"]["project"]="other-project"
                immutable.return_value=bad_original
                with self.assertRaisesRegex(guard.RelayGuardError,"immutable original"):check()
                immutable.return_value=original
                for change in ("ticket","before","model","reservation","case","partition"):
                    state=copy.deepcopy(self.active())
                    if change=="ticket":state["active"]["id"]="0"*32
                    elif change=="before":state["active_meter"]["before"]["requests"]-=1
                    elif change=="model":state["active_meter"]["model"]="different-model"
                    elif change=="reservation":state["active"]["scope"]["project_reservation_id"]="0"*32
                    else:
                        bad=copy.deepcopy(original);bad["scope"]["queue"][0]["case_sha256"]="0"*64
                        if change=="partition":bad["entries"][-1]["partition"]="unknown"
                        immutable.return_value=bad
                        self.store.put(*guard.TRIAL_SOURCES[guard.EVALUATION_TRIAL][:1],"trial-state","ledger.json",{
                            **bad,"entries":[bad["entries"][0],{**bad["entries"][-1],**{key:current["entries"][-1][key]
                                for key in ("billing_status","actual_cost_cny","debit_evidence","reconciled_at")}}]})
                    self.store.put(guard.BRANCH,"relay-guard",guard.fingerprint(PROVIDER)+".json",state)
                    with self.subTest(change=change),self.assertRaises(guard.RelayGuardError):check()
                    immutable.return_value=original
                    self.store.put(*guard.TRIAL_SOURCES[guard.EVALUATION_TRIAL][:1],"trial-state","ledger.json",current)
                    state["active"]=copy.deepcopy(ticket);state["active_meter"]={"model":"gemini-4-argon","before":self.meter()}
                    self.store.put(guard.BRANCH,"relay-guard",guard.fingerprint(PROVIDER)+".json",state)
                for changed_budget in ({**budget,"reservations":{ticket["scope"]["project_reservation_id"]:{}}},
                                       {**budget,"reconciliation_events":[]}):
                    with patch.object(model_spend,"read",return_value=changed_budget),self.assertRaises(guard.RelayGuardError):check()
                meter.return_value=self.debit(.2)
                with self.assertRaisesRegex(guard.RelayGuardError,"original accounted trial cost"):check()
                self.assertEqual(self.active()["active"],ticket)

    def test_owner_active_reconciliation_needs_original_project_and_matching_budget_event(self):
        ticket=self.legacy_active()
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

    def test_historical_shared_hold_does_not_add_a_project_payment_gate(self):
        provider="cheapai-gpt-pro";key=ai_providers.PRODUCTION_PROVIDERS[provider]["key_setting"]
        self.historical(provider)
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{key:"synthetic-production-key","DR_OS_ROUTING_PROFILE":"production","DR_OS_REQUIRE_MODEL_AUTH":"1","DR_OS_REQUIRE_REMOTE_RESERVATION":"1"}):
            project=Path(temporary)/"production-fixture";write(project/"state/run.json",{"active_paper":"P01"})
            model_spend.write(project,model_spend.initial());model_spend.grant(project,new_ceiling_cny=300,actor="Synthetic Owner",run_id="fixture-only")
            def reply(provider,prompt,**kwargs):
                return ai_providers.ModelResult(provider,kwargs["model"],"Synthetic reply",{"input_tokens":10,"output_tokens":5},
                    "fixture-request",kwargs["model"],completion_status="completed")
            with patch.object(guard,"CloudStore",return_value=self.store) as shared,patch("scripts.production_readiness.catalog") as catalog, \
                    patch("scripts.cloud_checkpoint.sync_billing"),patch.object(relay_billing,"read_meter",side_effect=relay_billing.BillingReconciliationError("Synthetic meter unavailable")) as meter,patch.object(ai_providers,"call",side_effect=reply) as post:
                model_runtime.call(project,run_id="fixture",stage="intake",role="persistent-writer",provider="openai",prompt="Synthetic work only",max_output_tokens=100)
                shared.assert_not_called();catalog.assert_not_called();meter.assert_called_once();post.assert_called_once()
            state=model_spend.read(project)
            self.assertGreater(state["spent_cny"],0);self.assertEqual(state["reservations"],{})
            self.assertEqual(model_runtime.ledger_entries(project)[0]["cost_status"],"estimated_upper_bound")

