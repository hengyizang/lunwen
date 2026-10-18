"""No network or real credentials. Run only in cloud CI for this project."""
import json
import os
from pathlib import Path
import hashlib
import io
import unittest
from unittest.mock import patch

from scripts import gateway_trial as trial


class TrialControlsTests(unittest.TestCase):
    def ledger(self):
        return {'trial_id':trial.TRIAL,'limit_cny':30.0,'plan_sha256':'test','entries':[]}

    def test_failed_persistence_cannot_reach_transport(self):
        def fail(_):
            raise OSError('storage unavailable')
        with self.assertRaises(OSError):
            trial.reserve(self.ledger(),'r',.5,fail)

    def test_cumulative_cap_and_idempotence_include_unknown_failures(self):
        ledger=self.ledger()
        saved=[]
        self.assertTrue(trial.reserve(ledger,'first',29.9,lambda x:saved.append(json.loads(json.dumps(x)))))
        ledger['entries'][0]['status']='ambiguous_failure_reservation_retained'
        self.assertFalse(trial.reserve(ledger,'second',.2,lambda x:None))
        self.assertFalse(trial.reserve(ledger,'first',.01,lambda x:None))
        self.assertEqual(len(saved),1)
        self.assertEqual(len(ledger['entries']),1)

    def test_ledger_tampering_and_nan_rejected(self):
        for amount in (-1,float('nan'),float('inf'),True):
            ledger=self.ledger();ledger['entries']=[{'call_id':'x','reserved_ceiling_cny':amount}]
            with self.assertRaises(trial.TrialError):
                trial.validate_ledger(ledger,'test')
        ledger=self.ledger();ledger['limit_cny']=300
        with self.assertRaises(trial.TrialError):
            trial.validate_ledger(ledger,'test')

    def test_only_independent_debit_releases_reservation(self):
        ledger=self.ledger()
        trial.reserve(ledger,'first',29,lambda x:None)
        entry=ledger['entries'][0]
        entry['gateway_debit_cny']=.001
        self.assertFalse(trial.reserve(ledger,'next',2,lambda x:None))
        trial.settle_debit(entry,.001,{'source':'independent test meter','exactly_one_new_gateway_request':True})
        self.assertTrue(trial.reserve(ledger,'next',2,lambda x:None))
        self.assertAlmostEqual(trial.committed_cost(ledger),2.001)
        trial.validate_ledger(ledger,'test')

    def test_invalid_debit_cannot_release_or_exceed_reservation(self):
        for amount in (-1,float('nan'),float('inf'),True,2):
            entry={'reserved_ceiling_cny':1}
            with self.assertRaises(trial.TrialError):
                trial.settle_debit(entry,amount,{'source':'test'})

    def test_concurrent_gateway_request_prevents_settlement(self):
        entry={'call_id':'codekey-gemini|gemini-4-argon|evidence','reserved_ceiling_cny':1}
        before={'kind':'codekey_total_actual_cost','requests':0,'cost_cny':0}
        after={'kind':'codekey_total_actual_cost','requests':2,'cost_cny':.01}
        group={'root':'https://codekey.ai'}
        with patch.object(trial,'meter',return_value=after),patch.object(trial.time,'sleep'),self.assertRaises(trial.TrialError):
            trial.settle_after_call(group,'fake',{'entries':[entry]},entry,before)
        self.assertNotIn('gateway_debit_cny',entry)

    def test_public_billing_diagnostics_omit_credentials_and_identifiers(self):
        self.assertEqual(trial.numeric_tree({'user_id':13,'token_id':9,'balance':30,
            'key':'never store','data':{'cache_tokens':14,'cost':.02,'remaining':8}}),
            {'data':{'cache_tokens':14,'cost':.02}})

    def test_no_local_or_pr_event_execution(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(trial.TrialError):
            trial.main()

    def test_credentials_and_redirects_never_in_urls(self):
        for url in ('http://cheapai.info/v1/models','https://evil.example/v1/models',
                    'https://cheapai.info/v1/models?key=fake','https://user@cheapai.info/v1/models'):
            with self.assertRaises(trial.TrialError):
                trial.http_json(url)
        with self.assertRaises(trial.TrialError):
            trial.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.example')

    def test_redaction_and_no_untrusted_usage_fields(self):
        self.assertEqual(trial.safe_text('private-value sk-1234567890123456', ['private-value']),
                         '[REDACTED] [REDACTED]')
        self.assertEqual(trial.receipt_numbers({'input_tokens':23,'secret':'do not store',
            'input_tokens_details':{'cached_tokens':4,'malicious':'echo'}}),
            {'input_tokens':23,'input_tokens_details':{'cached_tokens':4}})

    def test_scientific_fixture_rejects_fabrication_and_false_positive(self):
        good={'primary_effect':.3,'primary_ci':[-.2,.8],'primary_significant':False,
              'subgroup_confirmatory':False,'doi':None,'source_ids':['S1','S2','S3'],'conclusion':'Uncertain primary effect.'}
        self.assertTrue(trial.grade(json.dumps(good),'evidence')['passed'])
        for key,value in (('primary_significant',True),('doi','10.0000/invented'),('primary_effect',1.3)):
            bad={**good,key:value}
            self.assertFalse(trial.grade(json.dumps(bad),'evidence')['passed'])

    def test_reasoning_count_is_output_once(self):
        route={'family':'google'}
        response={'candidates':[{'content':{'parts':[{'text':'{}'}]},'finishReason':'STOP'}],
                  'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':30,'thoughtsTokenCount':20},
                  'modelVersion':'gemini-4-argon'}
        _,usage,_,complete=trial.decode(route,response)
        self.assertEqual(usage['output_tokens'],50)
        self.assertTrue(complete)

    def test_only_actions_secrets_with_exact_key_binding_accepted(self):
        plan={'key_binding_salt':'salt','groups':[
            {'id':g,'key_sha256':hashlib.sha256(('salt:fake-'+g).encode()).hexdigest()}
            for g in trial.SECRET_ENVS]}
        env={v:'fake-'+k for k,v in trial.SECRET_ENVS.items()}
        with patch.dict(os.environ,env,clear=True),patch('sys.stdout',io.StringIO()):
            self.assertEqual(len(trial.receive_credentials(plan)),10)
        for changed in ('missing','different-key'):
            bad={**env}
            first=next(iter(env))
            if changed=='missing':
                del bad[first]
            else:
                bad[first]='wrong'
            with patch.dict(os.environ,bad,clear=True),self.assertRaises(trial.TrialError):
                trial.receive_credentials(plan)


if __name__=='__main__':
    unittest.main()
