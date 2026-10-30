"""Operational review observes evidence; it grants neither calls nor scientific acceptance."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import dynamic_routing, model_routing, model_spend, route_review as routing
from scripts.research_artifacts import write


class RouteReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        self.root = Path(self.temporary.name) / "code"
        for relative in (routing.POLICY, "config/model-routing.json"):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(routing.ROOT / relative, target)
        model_spend.write(self.project, model_spend.initial())
        model_spend.amend_ceiling(self.project, new_ceiling_cny=500, actor="Synthetic owner", run_id="fixture-amendment",
            authorization_note="Synthetic fixture only; no real spending is authorized.")
        self.now = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
        self.profile = {"task_class": "routine-implementation", "science_risk": "routine", "priority": "quality"}
        self.baseline = json.loads((self.root / "config/model-routing.json").read_text())["models"]

    def append(self, relative, rows):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def row(self, **changes):
        route = self.baseline["sol"]
        return {"provider": route["provider"], "model": route["model"], "requested_model": route["model"],
            "requested_reasoning_effort": route["reasoning_effort"], "stage": "experiment-execution", "role": "persistent-writer",
            "run_id": "fixture-1", "at": self.now.isoformat(), "completion_status": "completed", "cost_status": "settled_gateway_debit",
            "cost_cny": .1, "duration_seconds": 5, "cache_hit": False, "billing_quote_sha256": "a" * 64, **changes}

    def review(self, **changes):
        return routing.review(self.project, task_profile=self.profile, stage="experiment-execution", role="persistent-writer",
            now=self.now, root=self.root, **changes)

    def codes(self, result):
        return {r["code"] for r in result["triggers"]}

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}

    def test_review_is_read_only_and_never_calls_a_provider_or_claims_authority(self):
        self.append("state/model-usage.jsonl", [self.row()])
        before = self.snapshot()
        with patch("scripts.ai_providers.call", side_effect=AssertionError("status cannot call models")):
            result = self.review()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(result["paid_calls"], 0)
        self.assertFalse(result["state_changed"])
        self.assertFalse(result["authorizes_paid_request"])
        self.assertFalse(result["scientific_equivalence_verified"])
        self.assertIn("no extra model judge", result["selection_policy"]["normal_review"])

    def test_known_scientific_tasks_cannot_be_labeled_routine_and_no_route_override_is_accepted(self):
        result = routing.classify({"task_class": "novelty", "science_risk": "routine"}, stage="topic-intelligence", root=self.root)
        self.assertEqual(result["effective_task_profile"]["science_risk"], "critical")
        self.assertTrue(result["risk_floor_applied"])
        self.assertEqual(result["definition"]["baseline_model_key"], "astra")
        for changed in ({"model": "cheap"}, {"min_output_tokens": "large"}, {"deadline_seconds": True}, {"priority": []}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                routing.classify({**self.profile, **changed}, root=self.root)
        unknown = routing.classify(None, stage="writing-and-review", root=self.root)
        self.assertEqual(unknown["effective_task_profile"]["science_risk"], "critical")

    def test_runtime_profile_floor_reaches_actual_astra_opus_routes_without_model_calls(self):
        declaration = {"task_class": "cloud-feasibility", "science_risk": "auxiliary", "priority": "cost"}
        environment = {"DR_OS_ROUTING_PROFILE": "production", "DR_OS_DYNAMIC_ROUTING": "production",
            "DR_OS_ROUTING_CONFIG": str(self.root / "config/model-routing.json")}
        with patch.dict(os.environ, environment), patch("scripts.ai_providers.call", side_effect=AssertionError("route selection is free")):
            profile = dynamic_routing.validate_profile(declaration, stage="intake", role="persistent-writer")
            self.assertEqual(profile["science_risk"], "critical")
            self.assertEqual(profile["priority"], "cost")
            for role, expected_model, provider in (("persistent-writer", "gpt-6-astra", "cheapai-gpt-pro"),
                                                    ("semantic-planner", "claude-opus-5-5", "codekey-kiro-enterprise")):
                with self.subTest(role=role):
                    kind = model_routing.effective_task_kind("intake", role, task_profile=declaration)
                    self.assertEqual(kind, "scientific-judgment")
                    actual = model_routing.resolve_call("intake", role, provider, task_profile=declaration)
                    self.assertEqual(actual["model"], expected_model)
                    self.assertEqual(actual["reasoning_effort"], "high")
        self.assertEqual(declaration["science_risk"], "auxiliary")

    def test_runtime_unknown_explicit_classes_and_unclassified_late_work_keep_existing_policy(self):
        environment = {"DR_OS_ROUTING_PROFILE": "production", "DR_OS_DYNAMIC_ROUTING": "production",
            "DR_OS_ROUTING_CONFIG": str(self.root / "config/model-routing.json")}
        unknown = {"task_class": "custom-supplied-task", "science_risk": "routine"}
        with patch.dict(os.environ, environment):
            checked = dynamic_routing.validate_profile(unknown, stage="intake", role="persistent-writer")
            self.assertEqual(checked["science_risk"], "routine")
            self.assertIsNone(model_routing.effective_task_kind("intake", "persistent-writer", task_profile=unknown))
            self.assertEqual(model_routing.resolve_call("intake", "persistent-writer", "cheapai-gpt-pro", task_profile=unknown)["model"], "gpt-6.1-sol")
            self.assertEqual(model_routing.effective_task_kind("writing-and-review", "persistent-writer"), "scientific-judgment")

    def test_unknown_catalog_and_old_receipts_are_unassessed_not_failed(self):
        self.append("state/model-usage.jsonl", [self.row(at=(self.now - timedelta(hours=25)).isoformat())])
        result = self.review()
        self.assertIn("normal_operational_review_due", self.codes(result))
        self.assertNotIn("catalog_model_absent", self.codes(result))
        sol = next(row for row in result["route_states"] if row["model"] == "gpt-6.1-sol")
        self.assertIsNone(sol["catalog_available"])
        self.assertFalse(sol["scientific_quality_verified"])

    def test_catalog_and_identity_incidents_require_review_not_paid_fallback(self):
        self.append("state/model-usage.jsonl", [self.row(model="unexpected-version")])
        result = self.review(catalogs={"cheapai-gpt-pro": []})
        self.assertIn("catalog_model_absent", self.codes(result))
        self.assertIn("model_identity_review_required", self.codes(result))
        self.assertEqual(result["status"], "incident_review")
        self.assertIn("never automatic fallback POST", result["selection_policy"]["after_possible_billing"])
        self.assertFalse(result["authorizes_paid_request"])

    def test_old_catalog_incident_is_superseded_only_by_later_actual_completed_generation(self):
        old = self.row(at=(self.now - timedelta(hours=1)).isoformat(), availability_error="model_not_advertised", generation_sent=False)
        self.append("state/model-route-decisions.jsonl", [old])
        self.assertIn("last_catalog_preflight_failed", self.codes(self.review()))
        self.append("state/model-usage.jsonl", [self.row(cache_hit=True, at=(self.now - timedelta(minutes=45)).isoformat())])
        self.assertIn("last_catalog_preflight_failed", self.codes(self.review()))
        self.append("state/model-usage.jsonl", [self.row(run_id="actual-recovery", at=(self.now - timedelta(minutes=30)).isoformat())])
        result = self.review()
        self.assertNotIn("last_catalog_preflight_failed", self.codes(result))
        route = next(row for row in result["route_states"] if row["model"] == "gpt-6.1-sol")
        self.assertIsNone(route["catalog_available"])
        newer = {**old, "at": (self.now - timedelta(minutes=10)).isoformat(), "run_id": "new-outage"}
        self.append("state/model-route-decisions.jsonl", [newer])
        self.assertIn("last_catalog_preflight_failed", self.codes(self.review()))

    def test_unknown_charge_and_reservations_block_even_when_a_good_alternative_exists(self):
        self.append("state/model-usage.jsonl", [self.row(cost_status="unknown_reconcile_required", reservation_id="hold-1")])
        result = self.review(catalogs={"cheapai-gpt-pro": ["gpt-6.1-sol", "gpt-6-astra"]})
        self.assertTrue(result["billing_blocks_new_paid_work"])
        self.assertEqual(result["status"], "blocked")
        state = model_spend.read(self.project)
        state["reconciliation_events"].append({"receipt_id": "hold-1", "note": "Synthetic reconciliation."})
        model_spend.write(self.project, state)
        self.assertFalse(self.review()["billing_blocks_new_paid_work"])
        model_spend.reserve(self.project, max_cost_cny=1, paper_id=None, paper_limit_cny=0, run_id="pending")
        self.assertTrue(self.review()["billing_blocks_new_paid_work"])

    def test_incomplete_quality_failures_and_duplicate_validation_rows_preserve_one_attempt(self):
        first = self.row(completion_status="truncated")
        second = self.row(validation_status="source_contract_failed_no_retry", cost_status=None, cost_cny=0)
        self.append("state/model-usage.jsonl", [first, second])
        result = self.review()
        self.assertIn("recent_request_failure", self.codes(result))
        self.assertIn("source_quality_review_required", self.codes(result))
        route = next(row for row in result["route_states"] if row["model"] == "gpt-6.1-sol")
        self.assertEqual(route["recent_unique_attempts"], 1)
        self.assertEqual(route["recent_failed_attempts"], 1)
        self.assertEqual(route["recent_completed_attempts"], 0)

    def test_latency_cost_and_quote_drift_trigger_review_without_promoting_a_model(self):
        rows = [self.row(run_id="run-" + str(i), duration_seconds=(5 if i < 2 else 15), cost_cny=(.1 if i < 2 else .5)) for i in range(4)]
        self.append("state/model-usage.jsonl", rows)
        result = self.review(quote_hashes={"cheapai-gpt-pro/gpt-6.1-sol/high": "b" * 64})
        self.assertTrue({"latency_regression_review", "cost_regression_review", "price_contract_changed"} <= self.codes(result))
        self.assertFalse(result["authorizes_paid_request"])
        self.assertIn("scoped candidates", result["selection_policy"]["new_models"])

    def test_old_acceptance_and_malformed_receipts_never_self_certify_current_quality(self):
        write(self.project / "state/dynamic-routing-acceptances.json", {"acceptances": [{"candidate_id": "fixture-candidate",
            "accepted_at": (self.now - timedelta(days=8)).isoformat()}]})
        self.assertIn("acceptance_review_due", self.codes(self.review()))
        self.append("state/model-usage.jsonl", [None])
        result = self.review()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("routing_evidence_unreadable", self.codes(result))

    def test_no_spending_authority_cannot_become_permission(self):
        (self.project / model_spend.FILE).unlink()
        result = self.review()
        self.assertIn("spending_authority_unavailable", self.codes(result))
        self.assertFalse(result["authorizes_paid_request"])

    def test_inventory_covers_scientific_roles_and_scripts_without_approving_new_models(self):
        tasks = routing.load_policy(self.root)["tasks"]
        self.assertGreaterEqual(len(tasks), 40)
        by_id = {row["task_class"]: row for row in tasks}
        self.assertEqual(by_id["experiment-execution"]["execution"], "deterministic")
        self.assertEqual(by_id["final-independent-review"]["baseline_model_key"], "opus")
        self.assertEqual(by_id["metadata-extraction"]["baseline_model_key"], "luna")
        self.assertFalse({"terra", "kimi"} & {row["baseline_model_key"] for row in tasks})


if __name__ == "__main__":
    unittest.main()

