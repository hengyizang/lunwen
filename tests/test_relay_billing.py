"""Read-only debit-meter fixtures; no real network or model calls."""
from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from unittest.mock import Mock, patch

from scripts import ai_providers, relay_billing as billing


class RelayBillingTests(unittest.TestCase):
    def test_explicit_environment_meter_does_not_read_global_credentials(self):
        env=self.environment()
        with patch.dict(os.environ,{},clear=True), patch.object(billing,"_get_json",return_value={
                "usage":{"total":{"requests":0,"actual_cost":0.0}}}) as get:
            value=billing.read_meter("codekey-deepseek",environment=env)
        self.assertEqual(value["cost_cny"],0)
        self.assertEqual(get.call_args.args[1]["Authorization"],"Bearer fixture-only-secret")

    def setUp(self):
        self.old_denomination = billing._CHEAP_DENOMINATION
        billing._CHEAP_DENOMINATION = None

    def tearDown(self):
        billing._CHEAP_DENOMINATION = self.old_denomination

    def environment(self):
        return {spec["key_setting"]: "fixture-only-secret"
                for spec in ai_providers.PRODUCTION_PROVIDERS.values()}

    def counter(self, requests=10, cost=0.02, provider="codekey-deepseek"):
        return {"provider": provider, "kind": "codekey_total_actual_cost",
                "requests": requests, "cost_cny": cost}

    def row(self, identifier=1, model="gpt-6.1-sol", quota=100, created_at=None):
        result = {"model_name": model, "quota": quota, "created_at": created_at or identifier or 1,
                  "prompt_tokens": 20, "completion_tokens": 5}
        if identifier is not None:
            result["id"] = identifier
        return result

    def history(self, rows, provider="cheapai-gpt-pro"):
        return {"provider": provider, "kind": "cheapai_quota_history",
                "quota_per_unit": 500000, "rows": rows}

    def test_codekey_meter_only_retains_actual_cost_and_request_count(self):
        raw = {"usage": {"total": {"requests": 20, "actual_cost": 0.123,
                "balance": 999, "api_key": "do-not-retain"}}, "account": "private"}
        with patch.dict(os.environ, self.environment(), clear=True), patch.object(
                billing, "_get_json", return_value=raw) as get:
            value = billing.read_meter("codekey-deepseek")
        self.assertEqual(value["requests"], 20)
        self.assertEqual(value["cost_cny"], 0.123)
        self.assertEqual(get.call_args.args[0], "https://codekey.ai/v1/usage")
        self.assertNotIn("do-not-retain", json.dumps(value))
        self.assertNotIn("private", json.dumps(value))
        self.assertNotIn("balance", value)

    def test_cheapai_meter_checks_public_units_once_and_sanitizes_rows(self):
        raw_row = {**self.row(), "type": 2, "user_id": 123, "token": "private-key", "ip": "private"}
        status = {"data": {"quota_per_unit": 500000, "quota_display_type": "USD", "unneeded": "private"}}
        logs = {"data": [raw_row, {"type": 1, "quota": 999}]}
        with patch.dict(os.environ, self.environment(), clear=True), patch.object(
                billing, "_get_json", side_effect=[status, logs, logs]) as get:
            first = billing.read_meter("cheapai-gpt-pro")
            second = billing.read_meter("cheapai-gpt-pro")
        self.assertEqual(first["rows"], [self.row()])
        self.assertEqual(first, second)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(get.call_args_list[0].args, ("https://cheapai.info/api/status",))
        self.assertNotIn("private", json.dumps(first))

    def test_denomination_change_and_malformed_costs_stop_before_generation(self):
        with patch.dict(os.environ, self.environment(), clear=True), patch.object(billing, "_get_json", return_value={
                "data": {"quota_per_unit": 1, "quota_display_type": "USD"}}):
            with self.assertRaises(billing.BillingReconciliationError):
                billing.read_meter("cheapai-gpt-pro")
        for cost in (-1, float("nan"), float("inf"), True, "0.1", None):
            with patch.dict(os.environ, self.environment(), clear=True), patch.object(billing, "_get_json", return_value={
                    "usage": {"total": {"requests": 1, "actual_cost": cost}}}):
                with self.assertRaises(billing.BillingReconciliationError):
                    billing.read_meter("codekey-deepseek")

    def test_codekey_independent_debit_matches_one_request_and_accepts_explicit_zero(self):
        for cost, expected in ((0.03, 0.01), (0.02, 0.0)):
            with patch.object(billing, "read_meter", return_value=self.counter(11, cost)):
                value = billing.settle("codekey-deepseek", "deepseek-v4.1-flash", self.counter())
            self.assertAlmostEqual(value["actual_cost_cny"], expected)
            self.assertTrue(value["debit_evidence"]["exactly_one_new_gateway_request"])

    def test_codekey_concurrency_counter_reset_and_decreasing_cost_hold(self):
        for after in (self.counter(12, 0.04), self.counter(9, 0.02), self.counter(11, 0.01)):
            with patch.object(billing, "read_meter", return_value=after) as read, patch.object(billing.time, "sleep") as sleep:
                with self.assertRaises(billing.BillingReconciliationError):
                    billing.settle("codekey-deepseek", "deepseek-v4.1-flash", self.counter())
                read.assert_called_once()
                sleep.assert_not_called()

    def test_settlement_lag_polls_only_free_metadata_twice_then_finishes(self):
        with (patch.object(billing, "read_meter", side_effect=[self.counter(), self.counter(), self.counter(11, 0.025)]) as read,
                patch.object(billing.time, "sleep") as sleep):
            value = billing.settle("codekey-deepseek", "deepseek-v4.1-flash", self.counter())
        self.assertEqual(read.call_count, 3)
        self.assertEqual([call.args for call in sleep.call_args_list], [(2,), (2,)])
        self.assertAlmostEqual(value["actual_cost_cny"], 0.005)

    def test_metadata_read_failure_is_not_retried_or_interpreted_as_zero(self):
        with (patch.object(billing, "read_meter", side_effect=billing.BillingReconciliationError("HTTP 429")) as read,
                patch.object(billing.time, "sleep") as sleep):
            with self.assertRaises(billing.BillingReconciliationError):
                billing.settle("codekey-deepseek", "deepseek-v4.1-flash", self.counter())
        read.assert_called_once()
        sleep.assert_not_called()

    def test_cheapai_matches_new_id_ignores_historical_models_and_needs_no_ttl_receipt(self):
        before = self.history([self.row(1, model="old-trial-model")])
        after = self.history([self.row(2, quota=150), self.row(1, model="old-trial-model")])
        with patch.object(billing, "read_meter", return_value=after):
            value = billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", before)
        self.assertEqual(value["actual_cost_cny"], 0.0003)
        self.assertEqual(value["debit_evidence"]["row"]["id"], 2)
        self.assertEqual(value["debit_evidence"]["quota_per_unit"], 500000)

    def test_missing_ids_use_fingerprint_multisets(self):
        prior = self.row(None, created_at=1)
        fresh = self.row(None, quota=200, created_at=2)
        with patch.object(billing, "read_meter", return_value=self.history([fresh, prior])):
            value = billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", self.history([prior]))
        self.assertEqual(value["actual_cost_cny"], 0.0004)
        sanitized = billing._rows([{**fresh, "id": "not-an-integer", "type": 2}])
        self.assertNotIn("id", sanitized[0])

    def test_actual_display_ordinal_shift_matches_only_the_new_sol_debit(self):
        # Sanitized shape observed in the cloud trial: ten prior rows become
        # positions 2..11 when the single new debit is displayed at position 1.
        prior = [self.row(i, created_at=1792500000 - i * 10) for i in range(1, 11)]
        fresh = {**self.row(1, quota=248, created_at=1792500557),
                 "prompt_tokens": 282, "completion_tokens": 169}
        shifted = [dict(row, id=row["id"] + 1) for row in prior]
        with patch.object(billing, "read_meter", return_value=self.history([fresh] + shifted)) as read:
            value = billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", self.history(prior))
        self.assertEqual(value["actual_cost_cny"], 0.000496)
        self.assertEqual(value["debit_evidence"]["row"], fresh)
        self.assertEqual(value["debit_evidence"]["row_identity_rule"],
                         "billing_fields_excluding_display_id")
        read.assert_called_once()

    def test_display_renumbering_alone_never_invents_a_debit_or_releases_a_hold(self):
        prior = [self.row(i, created_at=100 + i) for i in range(1, 11)]
        renumbered = [dict(row, id=index) for index, row in enumerate(reversed(prior), 1)]
        with (patch.object(billing, "read_meter", return_value=self.history(renumbered)) as read,
              patch.object(billing.time, "sleep") as sleep):
            with self.assertRaises(billing.BillingReconciliationError):
                billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", self.history(prior))
        self.assertEqual(read.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_changed_historical_billing_fields_remain_ambiguous_despite_new_ids(self):
        prior = [self.row(i, created_at=100 + i) for i in range(1, 11)]
        for field, value in (("quota", 999), ("prompt_tokens", 999),
                             ("completion_tokens", 999), ("created_at", 999),
                             ("model_name", "another-model")):
            with self.subTest(field=field):
                shifted = [dict(row, id=row["id"] + 1) for row in prior]
                shifted[4][field] = value
                fresh = self.row(1, quota=248, created_at=1000)
                with patch.object(billing, "read_meter", return_value=self.history([fresh] + shifted)):
                    with self.assertRaises(billing.BillingReconciliationError):
                        billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", self.history(prior))

    def test_display_ids_can_roll_over_with_the_last_hundred_without_losing_continuity(self):
        prior = [self.row(index, created_at=101 - index) for index in range(1, 101)]
        fresh = self.row(1, quota=333, created_at=101)
        shifted = [dict(row, id=row["id"] + 1) for row in prior[:-1]]
        with patch.object(billing, "read_meter", return_value=self.history([fresh] + shifted)):
            value = billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", self.history(prior))
        self.assertEqual(value["actual_cost_cny"], 333 / 500000)
        self.assertEqual(value["debit_evidence"]["row"]["created_at"], 101)

    def test_oldest_row_mutation_in_full_window_is_not_mistaken_for_rollover(self):
        prior = [self.row(index, created_at=101 - index) for index in range(1, 101)]
        after = [dict(row) for row in prior]
        after[-1]["quota"] = 999
        with patch.object(billing, "read_meter", return_value=self.history(after)):
            with self.assertRaisesRegex(billing.BillingReconciliationError, "predates"):
                billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", self.history(prior))

    def test_two_fresh_display_rows_are_still_concurrent_and_cannot_settle(self):
        prior = [self.row(i, created_at=100 + i) for i in range(1, 11)]
        after = [self.row(1, created_at=201), self.row(2, created_at=200)]
        after += [dict(row, id=row["id"] + 2) for row in prior]
        with patch.object(billing, "read_meter", return_value=self.history(after)) as read:
            with self.assertRaisesRegex(billing.BillingReconciliationError, "multiple new"):
                billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", self.history(prior))
        read.assert_called_once()

    def test_equal_core_rows_use_multiplicity_instead_of_unique_fingerprint_set(self):
        prior = [self.row(1, created_at=100), self.row(2, created_at=100)]
        after = [self.row(i, created_at=100) for i in range(1, 4)]
        with patch.object(billing, "read_meter", return_value=self.history(after)):
            value = billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", self.history(prior))
        self.assertEqual(value["actual_cost_cny"], 100 / 500000)

    def test_last_hundred_rollover_preserves_unique_new_debit(self):
        before = self.history([self.row(i) for i in range(1, 101)])
        after = self.history([self.row(i) for i in range(2, 102)])
        with patch.object(billing, "read_meter", return_value=after):
            value = billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", before)
        self.assertEqual(value["debit_evidence"]["row"]["id"], 101)

    def test_two_new_debits_or_wrong_model_never_release_a_hold(self):
        before = self.history([self.row(1)])
        for rows in ([self.row(1), self.row(2), self.row(3)],
                     [self.row(1), self.row(2, model="gpt-6-astra")]):
            with patch.object(billing, "read_meter", return_value=self.history(rows)) as read:
                with self.assertRaises(billing.BillingReconciliationError):
                    billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", before)
                read.assert_called_once()

    def test_changed_existing_id_or_lost_recent_history_is_ambiguous(self):
        for after in (self.history([self.row(1, quota=999)]), self.history([self.row(2)])):
            with patch.object(billing, "read_meter", return_value=after):
                with self.assertRaises(billing.BillingReconciliationError):
                    billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", self.history([self.row(1)]))

    def test_missing_debit_stops_after_three_free_polls(self):
        before = self.history([self.row(1)])
        with patch.object(billing, "read_meter", return_value=before) as read, patch.object(billing.time, "sleep") as sleep:
            with self.assertRaises(billing.BillingReconciliationError):
                billing.settle("cheapai-gpt-pro", "gpt-6.1-sol", before)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_route_binding_rejects_another_keys_meter(self):
        with patch.object(billing, "read_meter") as read:
            for provider, model, before in (("codekey-gemini", "gemini-4-argon-high", self.counter()),
                    ("cheapai-gpt-pro", "gpt-6.1-sol", self.counter(provider="cheapai-gpt-pro")),
                    ("codekey-deepseek", "gpt-6.1-sol", self.counter())):
                with self.assertRaises(billing.BillingReconciliationError):
                    billing.settle(provider, model, before)
            read.assert_not_called()

    def test_get_transport_is_https_only_no_redirects_no_error_body_or_retry(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError("https://codekey.ai/v1/usage", 429,
                "private error", {}, io.BytesIO(b"private secret gateway body"))
        with patch.object(billing.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(billing.BillingReconciliationError) as error:
                billing._get_json("https://codekey.ai/v1/usage", {"Authorization": "fixture-secret"})
        self.assertIn("429", str(error.exception))
        self.assertNotIn("private", str(error.exception))
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["user-agent"], "lunwen-production-research/1.0")
        self.assertEqual(headers["accept"], "application/json")
        self.assertNotIn("Python", headers["user-agent"])
        self.assertNotIn("fixture-secret", headers["user-agent"])
        self.assertNotIn("fixture-secret", request.full_url)
        with self.assertRaises(billing.BillingReconciliationError):
            billing._NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.example")
        for url in ("http://codekey.ai/v1/usage", "https://codekey.ai/v1/usage?key=secret", "https://other.example/v1/usage"):
            with self.assertRaises(billing.BillingReconciliationError):
                billing._get_json(url)


if __name__ == "__main__":
    unittest.main()
