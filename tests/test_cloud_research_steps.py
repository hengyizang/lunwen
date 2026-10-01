import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_research_steps as steps, cloud_checkpoint as cp, direction_evidence as directions
from scripts import api_orchestrator, literature_evidence
from tests.test_dataset_fetch import valid_manifest


class ControlledResearchTests(unittest.TestCase):
    def test_model_declared_license_does_not_authorize_download_and_changed_manifest_invalidates_review(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);path=project/'data/manifests/example.json';manifest=valid_manifest()
            payload=b'a,b\n1,2\n';manifest['download'].update(sha256=hashlib.sha256(payload).hexdigest(),expected_bytes=len(payload))
            steps.write(path,manifest)
            with patch.object(steps.dataset_fetch,'download_dataset') as fetch:
                self.assertEqual(steps.acquire_data(project)['blockers'][0]['kind'],'data_rights_review')
                fetch.assert_not_called()
            steps.authorize_data(project,'data/manifests/example.json',cp.sha(path),'Fixture reviewer','123')
            def download(_manifest,destination,*args):
                destination.mkdir(parents=True,exist_ok=True);target=destination/'data.csv';target.write_bytes(payload);return target
            with patch.object(steps.dataset_fetch,'download_dataset',side_effect=download) as fetch:
                first=steps.acquire_data(project);steps.acquire_data(project)
                self.assertEqual(fetch.call_count,1)
                self.assertEqual(first['acquired'][0]['sha256'],hashlib.sha256(payload).hexdigest())
                # Raw data is absent on a new runner and is rehydrated under the
                # same exact authorization, while the acquisition receipt stays.
                (project/first['acquired'][0]['path']).unlink();steps.acquire_data(project)
                self.assertEqual(fetch.call_count,2)
            path.write_text(path.read_text()+'\n')
            self.assertEqual(steps.acquire_data(project)['blockers'][0]['kind'],'data_rights_review')

    def test_literature_failure_does_not_suppress_other_databases_or_repeat_failed_first_six(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory)
            requests=[{'provider':'crossref','query':'q'+str(i),'query_family':'direct','limit':1} for i in range(9)]
            steps.write(project/'program/literature-search-plan.json',{'searches':requests})
            with patch.object(literature_evidence,'execute_search',side_effect=literature_evidence.LiteratureEvidenceError('fixture outage')) as fetch:
                first=steps.literature_context(project,'unused');second=steps.literature_context(project,'unused')
            self.assertEqual(first['new_search_calls'],6);self.assertEqual(first['pending_searches'],3)
            self.assertEqual(second['new_search_calls'],3);self.assertEqual(second['pending_searches'],0)
            self.assertEqual(fetch.call_count,9)

    def test_no_literature_receipts_prevents_paid_model_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project=root/'projects/demo'
            steps.write(root/'config/stages.json',{'stages':{'topic-intelligence':{'gate':'G1'}}})
            steps.write(project/'state/run.json',{'stage':'topic-intelligence','gate':'G1','status':'awaiting_work'})
            with patch.object(api_orchestrator,'ROOT',root),patch.object(api_orchestrator,'prepare_discovery_evidence',return_value=(json.dumps({'literature':{'receipts':[],'pending_searches':0}}),None)),patch.object(api_orchestrator.model_runtime,'call') as model:
                result=api_orchestrator.run_cycle('demo','topic-intelligence','uuapi-anthropic','uuapi-openai','uuapi-anthropic','','',automatic_data=False)
            model.assert_not_called();self.assertFalse(result['paid_model_cycle'])
            self.assertEqual(result['controlled_steps']['blockers'][0]['kind'],'literature_service_unavailable')

    def direction_fixture(self,project):
        now=datetime.now(timezone.utc);today=now.date()
        steps.write(project/'intake/constraints.json',{'ranking_weights':dict(zip(directions.FACTORS,directions.EXPECTED_WEIGHTS))})
        quote='Synthetic role with fully funded doctoral support. Gross annual salary CNY 300000. Career outlook and eligibility evidence for the fixture.'
        url='https://www.oecd.org/synthetic-fixture'
        def fetch(_url,**kwargs):return ('<p>'+quote+'</p>').encode(),url,200,'text/html'
        ledger=directions.fetch_sources(project,[url],fetcher=fetch)
        evidence={'url':url,'quote':quote};constraints=cp.sha(project/'intake/constraints.json')
        observations=[{'kind':'funded_phd','employer':'Fixture University','title':'Synthetic role','country':'Fixture',
            'eligible':True,'fully_funded':True,'observed_date':today.isoformat(),'evidence':evidence,
            'funding_evidence':evidence,'eligibility_rationale':'Synthetic matching background','constraints_sha256':constraints},
            {'kind':'job','employer':'Fixture Employer','title':'Synthetic role','country':'Fixture','eligible':True,
             'observed_date':today.isoformat(),'evidence':evidence,'eligibility_rationale':'Synthetic entry-level role','constraints_sha256':constraints,
             'salary':{'amount':300000,'currency':'CNY','basis':'gross','career_stage':'entry','period':'year','evidence':evidence}}]
        factors={k:{'score':3,'method':'assessment','confidence':'low','rationale':'Synthetic test assessment',
                    'anchor_description':'Test only','evidence':[evidence],'constraints_sha256':constraints} for k in directions.FACTORS[2:]}
        candidates=[{'id':str(i),'cloud_feasible':True,'no_future_lab_dependency':True,'authorized_data_plan':'Synthetic plan',
            'cloud_compute_plan':'Synthetic plan','career_stage':'entry','observations':copy.deepcopy(observations),
            'assessments':copy.deepcopy(factors)} for i in range(3)]
        assessment={'window_start':(today-timedelta(days=30)).isoformat(),'window_end':today.isoformat(),'candidates':candidates}
        return assessment,ledger,url

    def test_direction_weights_counts_and_missing_salary_are_not_fabricated(self):
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);assessment,ledger,url=self.direction_fixture(project)
            assessment['candidates'][0]['observations'].append(copy.deepcopy(assessment['candidates'][0]['observations'][0]))
            result=directions.rank(project,assessment,ledger)
            self.assertEqual(result['status'],'ready_for_human_review');self.assertEqual(len(result['sensitivity']),14)
            self.assertEqual(result['candidates'][0]['observed_funded_positions'],1)
            self.assertEqual(result['weights']['funded_position_supply'],result['weights']['job_market_and_salary'])
            self.assertFalse(result['novelty_is_a_tradeable_score'])
            del assessment['candidates'][0]['observations'][1]['salary']
            self.assertEqual(directions.rank(project,assessment,ledger)['status'],'blocked')
            ledger['sources'][url]['retrieved_at']=(datetime.now(timezone.utc)-timedelta(days=15)).isoformat()
            self.assertEqual(directions.rank(project,assessment,ledger)['status'],'blocked')
            self.assertFalse(directions.number_supported(100,'The salary is 2100 per month.'))
            self.assertFalse(directions.number_supported(float('inf'),'infinity'))

    def test_optional_web_search_uses_shared_reservation_and_never_retries_ambiguous_call(self):
        from scripts import web_research,model_spend
        import os
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);model_spend.write(project,model_spend.initial())
            model_spend.grant(project,new_ceiling_cny=300,actor='Fixture',run_id='123')
            with patch.dict(os.environ,{'TAVILY_API_KEY':'synthetic-key','DR_OS_TAVILY_CREDIT_CNY':'0.1'},clear=True),patch.object(web_research.urllib.request,'build_opener') as opener:
                opener.return_value.open.side_effect=TimeoutError('lost response')
                with self.assertRaisesRegex(RuntimeError,'ambiguous'):
                    web_research.search('funded doctoral positions',project_root=project)
                with self.assertRaisesRegex(RuntimeError,'reconciliation'):
                    web_research.search('funded doctoral positions',project_root=project)
                self.assertEqual(opener.return_value.open.call_count,1)
            self.assertEqual(len(model_spend.read(project)['reservations']),1)

    def test_jev_uses_only_receipt_metadata_and_keeps_ordinary_review_leads(self):
        from scripts import lead_triage,free_jev_probe
        import os
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);raw=project/'evidence/literature/raw/fixture.json';normalized=project/'evidence/literature/normalized/fixture.json'
            steps.write(raw,{'fixture':True});steps.write(normalized,{'works':[{'title':'Public title','abstract':'Public abstract','private_field':'must not leave'}]})
            receipt={'receipt_id':'fixture','status':'success','completed_at':datetime.now(timezone.utc).isoformat(),
                     'raw_response_path':raw.relative_to(project).as_posix(),'response_sha256':cp.sha(raw),
                     'normalized_results_path':normalized.relative_to(project).as_posix(),'normalized_results_sha256':cp.sha(normalized)}
            (project/'evidence/literature-api-ledger.jsonl').write_text(json.dumps(receipt)+'\n')
            with patch.dict(os.environ,{'OPENROUTER_API_KEY':'fixture-only'},clear=True),patch.object(free_jev_probe,'probe',return_value={'status':'passed','triage_label':'ordinary_review','total_cost_usd':0}) as call:
                report=lead_triage.triage(project,'fixture','openrouter');lead_triage.triage(project,'fixture','openrouter')
                self.assertEqual(call.call_count,1)
                self.assertEqual(call.call_args.kwargs['public_metadata'],{'title':'Public title','description':'Public abstract'})
            self.assertTrue(report['all_records_retained']);self.assertFalse(report['labels'][0]['scientific_evidence'])
