"""Planning estimates keep unknown charges and owner preferences explicit."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cost_audit, direction_evidence, intake_validation


class PlanningCostsTests(unittest.TestCase):
    def test_default_discovery_reaches_all_available_public_sources_without_inventing_saturation(self):
        from scripts import cloud_research_steps as steps, literature_evidence
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {}, clear=True):
            with patch.object(literature_evidence, 'execute_search', side_effect=ValueError('fixture source unavailable')):
                report = steps.literature_context(Path(directory), 'Population ecology')
            self.assertEqual(set(report['planned_providers']), set(literature_evidence.DEFAULT_SEARCH_PROVIDERS) - {'openalex'})
            self.assertEqual(report['new_search_calls'], 12)
            self.assertEqual(report['pending_searches'], 6)
            self.assertEqual(report['searched_providers'], [])
            self.assertFalse(report['novelty_proven'])

    def test_six_paper_counts_and_observed_role_costs_are_separate_from_success(self):
        rows = [{"role": role, "cost_cny": cost, "duration_seconds": seconds,
                 "cost_status": "settled_gateway_debit"}
                for role, cost, seconds in (("read-only-planner", 1, 10), ("persistent-writer", 2, 20),
                                             ("independent-critic", 3, 30))]
        report = cost_audit.portfolio_forecast(rows)
        scenario = report['scenarios'][1]
        self.assertEqual(scenario['model_calls'], 147)
        self.assertEqual(scenario['cost_cny']['observed_median'], 45 + 90 + 57 * 3)
        self.assertEqual(report['observed_role_allocation']['writer']['known_recorded_cost_cny'], 2)
        self.assertFalse(report['scientific_success_or_acceptance_predicted'])

    def test_missing_or_failed_billing_is_not_an_estimated_free_portfolio(self):
        for rows in ([], [{"role": 'persistent-writer', 'cost_cny': None}],
                     [{"role": 'persistent-writer', 'cost_cny': float('nan')}],
                     [{"role": 'persistent-writer', 'cost_cny': 0, 'cache_hit': True}]):
            report = cost_audit.portfolio_forecast(rows)
            self.assertTrue(all(row['cost_cny'] is None for row in report['scenarios']))
        report = cost_audit.portfolio_forecast([{'role': 'independent-critic', 'cost_cny': 2,
            'duration_seconds': 4, 'transport_error_type': 'TimeoutError', 'cost_status': 'estimated_upper_bound'}])
        self.assertEqual(report['observed_role_allocation']['critic']['attempts'], 1)
        self.assertEqual(report['observed_role_allocation']['critic']['estimated_billing_attempts'], 1)

    def test_intake_guidance_does_not_supply_original_users_domains_or_routes(self):
        report = intake_validation.guidance({'research_goal': 'Population ecology', 'preferred_domains': ['Ecology']})
        self.assertNotIn('research', [row['group'] for row in report['questions']])
        self.assertFalse(report['domain_or_application_route_assumed'])
        self.assertNotIn('robotics', json.dumps(report))

    def test_actual_transport_failure_zero_placeholders_remain_unknown(self):
        rows = [{'role': role, 'cost_cny': 0.0, 'reserved_cost_cny': 7.5,
                 'cost_status': 'accounted_upper_bound', 'zero_cost_not_confirmed': True,
                 'transport_error_type': 'TimeoutError', 'duration_seconds': 15}
                for role in ('semantic-planner', 'persistent-writer', 'independent-critic')]
        report = cost_audit.portfolio_forecast(rows)
        self.assertTrue(all(row['cost_cny'] is None for row in report['scenarios']))
        for role in ('planner', 'writer', 'critic'):
            self.assertEqual(report['observed_role_allocation'][role]['cost_unknown_attempts'], 1)
            self.assertEqual(report['observed_role_allocation'][role]['estimated_billing_attempts'], 1)
        rows[0].update(cost_cny=10 ** 1000, cost_status='settled_gateway_debit', zero_cost_not_confirmed=False)
        self.assertIsNone(cost_audit.portfolio_forecast(rows)['scenarios'][1]['cost_cny'])

    def test_direction_ranking_accepts_owner_weights_without_historical_default(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            from tests.test_cloud_research_steps import ControlledResearchTests
            assessment, ledger, _ = ControlledResearchTests().direction_fixture(project)
            weights = {key: 0 for key in direction_evidence.FACTORS}
            weights['background_fit'] = 1
            (project / 'intake/constraints.json').write_text(json.dumps({'ranking_weights': weights}))
            fingerprint = direction_evidence.sha(project / 'intake/constraints.json')
            for candidate in assessment['candidates']:
                candidate['assessments']['background_fit']['constraints_sha256'] = fingerprint
                for observation in candidate['observations']:
                    observation['constraints_sha256'] = fingerprint
            ranked = direction_evidence.rank(project, assessment, ledger)
            self.assertEqual(ranked['status'], 'ready_for_human_review')
            self.assertEqual(ranked['weights'], weights)
            self.assertTrue(all(row['weighted_score'] == row['scores']['background_fit'] for row in ranked['candidates']))
            for invalid in (float('nan'), -.1, True):
                bad = copy.deepcopy(weights)
                bad['background_fit'] = invalid
                (project / 'intake/constraints.json').write_text(json.dumps({'ranking_weights': bad}))
                with self.assertRaises(direction_evidence.DirectionEvidenceError):
                    direction_evidence.rank(project, {}, {})
