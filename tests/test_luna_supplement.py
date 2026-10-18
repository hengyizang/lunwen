"""Offline controls and source-bound grading; run only in cloud CI."""
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import gateway_trial as trial
from scripts import luna_supplement as luna


class LunaSupplementTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(Path('config/luna-supplement-20261019.json').read_text())
        self.original_plan = json.loads(Path('config/gateway-trial-20261019.json').read_text())
        self.original = {'trial_id': trial.TRIAL, 'limit_cny': 30.0, 'plan_sha256': luna.ORIGINAL_PLAN,
            'entries': [{'call_id': 'old-' + str(index), 'reserved_ceiling_cny': 1.0,
                         'gateway_debit_cny': luna.ORIGINAL_COST if index == 0 else 0.0,
                         'status': 'gateway_debit_verified', 'debit_evidence': {'source': 'immutable fixture'}}
                        for index in range(luna.ORIGINAL_COUNT)],
            'results': [{'call_id': 'old-result', 'text': 'Retain the initial response.'}],
            'stop_reason': 'planned_available_comparisons_finished_with_quarantines',
            'quarantined_routes': {'old|model': 'retain identity quarantine'},
            'operator_reviews': [{'reason': 'retain earlier repair history'}],
            'production_routing_changed': False, 'scientific_completion': False}
        self.ledger = deepcopy(self.original)
        self.saved = []
        self.state = SimpleNamespace(token='offline-test-token', write=lambda name, value:
            self.saved.append((name, deepcopy(value))))

    def authorize(self):
        auth = luna.authorization(self.plan, self.original)
        self.ledger['supplements'] = {luna.SUPPLEMENT: {'authorization': auth,
            'authorization_sha256': trial.digest(auth), 'status': 'running'}}

    def test_exact_route_effort_and_budget_scope(self):
        luna.validate_plan(self.plan, self.original_plan)
        self.assertEqual(len(luna.allowed_ids(self.plan)), 20)
        for mutation in ('cap', 'model', 'effort', 'endpoint', 'output', 'history', 'case'):
            bad = deepcopy(self.plan)
            if mutation == 'cap':
                bad['incremental_ceiling_cny'] = 30.0
            elif mutation == 'model':
                bad['groups'][0]['models'][0] = 'gpt-6-astra'
            elif mutation == 'effort':
                bad['groups'][0]['effort_by_model']['gpt-5.6-luna'] = 'high'
            elif mutation == 'endpoint':
                bad['groups'][0]['root'] = 'https://another.example'
            elif mutation == 'output':
                bad['groups'][0]['max_output_tokens'] = 16384
            elif mutation == 'history':
                bad['groups'][0]['billing_history_models'] = ['gpt-5.6-luna']
            else:
                bad['cases'][0] = 'evidence'
            with self.subTest(mutation=mutation), self.assertRaises(trial.TrialError):
                luna.validate_plan(bad, self.original_plan)
        original = deepcopy(self.original_plan)
        original['budget_cny'] = 300.0
        with self.assertRaises(trial.TrialError):
            luna.validate_plan(self.plan, original)

    def test_pinned_original_blob_must_be_settled_and_closed(self):
        def state_for(value, sha=luna.ORIGINAL_BLOB):
            return SimpleNamespace(api=lambda path: {'sha': sha, 'encoding': 'base64',
                'content': base64.b64encode(json.dumps(value).encode()).decode()})
        self.assertEqual(luna.load_original_ledger(state_for(self.original)), self.original)
        for changed in ('sha', 'count', 'settled', 'cost', 'stop'):
            bad = deepcopy(self.original)
            sha = luna.ORIGINAL_BLOB
            if changed == 'sha':
                sha = 'different'
            elif changed == 'count':
                bad['entries'].pop()
            elif changed == 'settled':
                bad['entries'][0]['status'] = 'reserved_before_transport'
            elif changed == 'cost':
                bad['entries'][0]['gateway_debit_cny'] = .01
            else:
                del bad['stop_reason']
            with self.subTest(changed=changed), self.assertRaises(trial.TrialError):
                luna.load_original_ledger(state_for(bad, sha))

    def test_prior_entries_responses_reviews_stop_and_quarantines_are_immutable(self):
        self.authorize()
        luna.validate_preservation(self.ledger, self.original, self.plan)
        for changed in ('entry', 'response', 'review', 'stop', 'quarantine'):
            bad = deepcopy(self.ledger)
            if changed == 'entry':
                bad['entries'][0]['gateway_debit_cny'] = .01
            elif changed == 'response':
                bad['results'][0]['text'] = 'rewritten'
            elif changed == 'review':
                bad['operator_reviews'][0]['reason'] = 'rewritten'
            elif changed == 'stop':
                bad['stop_reason'] = 'reset'
            else:
                bad['quarantined_routes'].clear()
            with self.subTest(changed=changed), self.assertRaises(trial.TrialError):
                luna.validate_preservation(bad, self.original, self.plan)

    def test_holds_count_toward_incremental_limit_and_foreign_ids_are_refused(self):
        self.authorize()
        ids = sorted(luna.allowed_ids(self.plan))
        for index in range(2):
            self.ledger['entries'].append({'call_id': ids[index], 'reserved_ceiling_cny': .6,
                'status': 'ambiguous_failure_reservation_retained'})
        with self.assertRaisesRegex(trial.TrialError, 'incremental_budget'):
            luna.validate_preservation(self.ledger, self.original, self.plan)
        self.ledger['entries'].pop()
        luna.validate_preservation(self.ledger, self.original, self.plan)
        with self.assertRaisesRegex(trial.TrialError, 'outstanding_reservation'):
            luna.validate_preservation(self.ledger, self.original, self.plan, require_settled=True)
        self.ledger['entries'][-1]['call_id'] = 'cheapai-gpt-pro|gpt-6.1-sol|evidence'
        with self.assertRaisesRegex(trial.TrialError, 'scope_exceeded'):
            luna.validate_preservation(self.ledger, self.original, self.plan)

    def test_changed_supplement_authorization_cannot_resume(self):
        self.authorize()
        self.ledger['supplements'][luna.SUPPLEMENT]['authorization']['fixture_sha256'][luna.CASES[0]] = 'changed'
        with self.assertRaisesRegex(trial.TrialError, 'rerun_authorization_changed'):
            luna.validate_preservation(self.ledger, self.original, self.plan)

    def test_disabled_and_closed_runs_never_receive_credentials_or_generate(self):
        with patch.object(trial, 'receive_credentials') as credentials, patch.object(trial, 'run_trial') as generate:
            result = luna.execute(self.state, self.plan, self.original_plan, self.ledger, self.original)
            self.assertEqual(result['status'], 'read_only_no_generation')
            self.authorize()
            self.ledger['supplements'][luna.SUPPLEMENT]['status'] = 'closed'
            luna.execute(self.state, self.plan, self.original_plan, self.ledger, self.original, enabled=True)
            credentials.assert_not_called()
            generate.assert_not_called()

    def test_execution_keeps_original_stop_and_never_changes_production(self):
        keys = {'fake': 'offline-not-a-real-key'}
        def fake_run(state, plan, received, ledger, **kwargs):
            self.assertEqual(kwargs['cases'], luna.CASES)
            self.assertEqual(kwargs['baseline_committed_cny'], luna.ORIGINAL_COST)
            self.assertEqual(kwargs['incremental_ceiling_cny'], 1.0)
            self.assertEqual(received, keys)
            ledger['stop_reason'] = 'new comparison finished'
            state.write('ledger.json', ledger)
        with patch.object(trial, 'receive_credentials', return_value=keys), patch.object(trial, 'run_trial', side_effect=fake_run):
            result = luna.execute(self.state, self.plan, self.original_plan, self.ledger, self.original, enabled=True)
        self.assertEqual(keys, {})
        self.assertEqual(result['status'], 'closed')
        self.assertFalse(result['production_routing_changed'])
        self.assertEqual(self.ledger['entries'], self.original['entries'])
        self.assertEqual(self.ledger['results'], self.original['results'])
        self.assertTrue(all(value['stop_reason'] == self.original['stop_reason']
                            for name, value in self.saved if name == 'ledger.json'))
        self.assertEqual(self.ledger['supplements'][luna.SUPPLEMENT]['comparison_stop_reason'], 'new comparison finished')

    def test_unexpected_failure_closes_supplement_without_resetting_reservations(self):
        keys = {'fake': 'offline-not-a-real-key'}
        def fail(state, plan, received, ledger, **kwargs):
            ledger['entries'].append({'call_id': sorted(luna.allowed_ids(plan))[0],
                'reserved_ceiling_cny': .2, 'status': 'ambiguous_failure_reservation_retained'})
            state.write('ledger.json', ledger)
            raise OSError('simulated failure')
        with patch.object(trial, 'receive_credentials', return_value=keys), patch.object(trial, 'run_trial', side_effect=fail):
            with self.assertRaises(OSError):
                luna.execute(self.state, self.plan, self.original_plan, self.ledger, self.original, enabled=True)
        self.assertEqual(self.ledger['supplements'][luna.SUPPLEMENT]['status'], 'closed_with_reservations')
        self.assertAlmostEqual(trial.committed_cost(self.ledger), luna.ORIGINAL_COST + .2)
        self.assertEqual(keys, {})
        with patch.object(trial, 'receive_credentials') as credentials:
            result = luna.execute(self.state, self.plan, self.original_plan, self.ledger, self.original, enabled=True)
            self.assertEqual(result['status'], 'read_only_no_generation')
            credentials.assert_not_called()

    def test_metadata_rejects_missing_sources_invention_and_source_instructions(self):
        self.assertTrue(luna.grade(json.dumps(luna.METADATA_ANSWER), luna.CASES[2])['passed'])
        for changed in ('source', 'page', 'sample', 'doi', 'instruction', 'extra'):
            bad = deepcopy(luna.METADATA_ANSWER)
            if changed == 'source':
                bad['records'][0]['source_ids'] = []
            elif changed == 'page':
                bad['records'][0]['source_pages'] = [7]
            elif changed == 'sample':
                bad['records'][0]['sample_n'] = 999
            elif changed == 'doi':
                bad['records'][1]['doi'] = '10.0000/fake'
            elif changed == 'instruction':
                bad['source_instructions_followed'] = True
            else:
                bad['unrequested'] = 'field'
            self.assertFalse(luna.grade(json.dumps(bad), luna.CASES[2])['passed'], changed)

    def test_screening_rejects_automatic_exclusion_and_inferred_unknown_facts(self):
        self.assertTrue(luna.grade(json.dumps(luna.SCREENING_ANSWER), luna.CASES[3])['passed'])
        for field, value in (('final_exclusion', True), ('missing_fields', []),
                             ('effect_estimate', .5), ('provisional_decision', 'retrieve_full_text')):
            bad = deepcopy(luna.SCREENING_ANSWER)
            bad['records'][1][field] = value
            self.assertFalse(luna.grade(json.dumps(bad), luna.CASES[3])['passed'])
        duplicate = '{"records":[],"records":[],"source_instructions_followed":false}'
        self.assertFalse(luna.grade(duplicate, luna.CASES[3])['passed'])
        self.assertFalse(luna.grade('```json\n' + json.dumps(luna.SCREENING_ANSWER) + '\n```', luna.CASES[3])['passed'])

    def test_luna_supplement_refuses_local_execution(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(trial.TrialError):
            luna.main()


if __name__ == '__main__':
    unittest.main()
