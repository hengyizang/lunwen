from __future__ import annotations

import copy
import tempfile
import threading
import unittest
from pathlib import Path

from scripts import model_spend


class ExactOwnerCeilingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        model_spend.write(self.project, model_spend.initial())
        model_spend.grant(self.project, new_ceiling_cny=300, actor="Synthetic owner", run_id="first-grant")

    def amend(self, amount=500, **overrides):
        arguments = {"new_ceiling_cny": amount, "actor": "Synthetic owner",
                     "run_id": "owner-amendment", "authorization_note": "Explicit approval of the cumulative ceiling."}
        arguments.update(overrides)
        return model_spend.amend_ceiling(self.project, **arguments)

    def test_one_persisted_reservation_can_only_be_claimed_by_one_transport(self):
        receipt=model_spend.reserve(self.project,max_cost_cny=1,paper_id=None,paper_limit_cny=0,run_id="transport-race")
        barrier=threading.Barrier(2);claimed=[];rejected=[]
        def compete():
            barrier.wait()
            try:
                claimed.append(model_spend.claim_transport(self.project,receipt,max_cost_cny=1,
                    paper_id=None,run_id="transport-race",binding={"provider":"synthetic","model":"synthetic"}))
            except model_spend.SpendControlError as error:
                rejected.append(error)
        workers=[threading.Thread(target=compete) for _ in range(2)]
        for worker in workers:worker.start()
        for worker in workers:worker.join(timeout=5)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual(len(claimed),1);self.assertEqual(len(rejected),1)
        state=model_spend.read(self.project)
        self.assertEqual(state["reservations"][receipt],claimed[0])
        self.assertEqual(state["spent_cny"],0);self.assertEqual(model_spend.reserved(state),1)

    def test_exact_500_preserves_all_existing_costs_holds_and_history(self):
        settled = model_spend.reserve(self.project, max_cost_cny=4, paper_id="P01", paper_limit_cny=60, run_id="completed")
        model_spend.settle(self.project, settled, actual_cost_cny=3.25)
        held = model_spend.reserve(self.project, max_cost_cny=12.5, paper_id="P02", paper_limit_cny=60, run_id="unresolved")
        before = model_spend.read(self.project, required=True)
        before["paper_limits_cny"] = {"P01": 60, "P02": 40}
        before["unrecognized_future_metadata"] = {"retain": True}
        model_spend.write(self.project, before)

        changed = self.amend()
        expected = copy.deepcopy(before)
        expected["authorized_ceiling_cny"] = 500
        expected["authorization_events"].append(changed["authorization_events"][-1])
        self.assertEqual(changed, expected)
        self.assertEqual(model_spend.read(self.project, required=True), expected)
        self.assertEqual(changed["spent_cny"], 3.25)
        self.assertIn(held, changed["reservations"])
        self.assertEqual(model_spend.reserved(changed), 12.5)
        self.assertEqual(changed["authorization_events"][:-1], before["authorization_events"])
        event = changed["authorization_events"][-1]
        self.assertEqual(event["previous_ceiling_cny"], 300)
        self.assertEqual(event["ceiling_cny"], 500)
        self.assertEqual(event["kind"], "ceiling_amendment")
        self.assertTrue(event["authorization_note"])

    def test_lower_ceiling_cannot_erase_spend_or_outstanding_reservations(self):
        settled = model_spend.reserve(self.project, max_cost_cny=35, paper_id="P01", paper_limit_cny=60, run_id="settled")
        model_spend.settle(self.project, settled, actual_cost_cny=35)
        held = model_spend.reserve(self.project, max_cost_cny=15.1, paper_id="P02", paper_limit_cny=60, run_id="held")
        original = (self.project / model_spend.FILE).read_bytes()
        with self.assertRaises(model_spend.SpendControlError):
            self.amend(50)
        self.assertEqual((self.project / model_spend.FILE).read_bytes(), original)
        changed = self.amend(51)
        self.assertEqual(changed["authorized_ceiling_cny"], 51)
        self.assertIn(held, changed["reservations"])
        with self.assertRaises(model_spend.SpendControlError):
            model_spend.reserve(self.project, max_cost_cny=1, paper_id=None, paper_limit_cny=60, run_id="over-ceiling")

    def test_a_ceiling_equal_to_existing_commitments_is_valid_but_allows_no_extra_call(self):
        model_spend.reserve(self.project, max_cost_cny=50, paper_id=None, paper_limit_cny=60, run_id="held")
        self.amend(50)
        with self.assertRaises(model_spend.SpendControlError):
            model_spend.reserve(self.project, max_cost_cny=0.01, paper_id=None, paper_limit_cny=60, run_id="extra")

    def test_commitment_floor_does_not_round_away_a_recorded_fraction(self):
        state = model_spend.read(self.project)
        state["spent_cny"] = 50.000000001
        model_spend.write(self.project, state)
        original = (self.project / model_spend.FILE).read_bytes()
        with self.assertRaises(model_spend.SpendControlError):
            self.amend(50)
        self.assertEqual((self.project / model_spend.FILE).read_bytes(), original)

    def test_recorded_provider_overage_is_preserved_when_owner_raises_ceiling(self):
        reservation = model_spend.reserve(self.project, max_cost_cny=1, paper_id="P01", paper_limit_cny=60, run_id="overage")
        with self.assertRaises(model_spend.SpendControlError):
            model_spend.settle(self.project, reservation, actual_cost_cny=301)
        before = model_spend.read(self.project)
        result = self.amend(500)
        self.assertEqual(result["spent_cny"], 301)
        self.assertEqual(result["paper_spent_cny"], {"P01": 301})
        self.assertEqual(result["settlement_events"], before["settlement_events"])
        model_spend.reserve(self.project, max_cost_cny=1, paper_id="P01", paper_limit_cny=60, run_id="remaining-total")

    def test_only_500_total_budget_is_enforced_across_paper_allocations(self):
        self.amend()
        original = (self.project / model_spend.FILE).read_bytes()
        for maximum, paper_id in ((500.01, None), (500.01, "P01")):
            with self.subTest(maximum=maximum, paper=paper_id), self.assertRaises(model_spend.SpendControlError):
                model_spend.reserve(self.project, max_cost_cny=maximum, paper_id=paper_id,
                                    paper_limit_cny=60, run_id="blocked")
            self.assertEqual((self.project / model_spend.FILE).read_bytes(), original)
        model_spend.reserve(self.project, max_cost_cny=200, paper_id="P01", paper_limit_cny=60, run_id="first-paper")
        model_spend.reserve(self.project, max_cost_cny=300, paper_id="P01", paper_limit_cny=60, run_id="same-paper-total")
        with self.assertRaises(model_spend.SpendControlError):
            model_spend.reserve(self.project, max_cost_cny=0.01, paper_id=None, paper_limit_cny=60, run_id="extra")

    def test_invalid_or_unchanged_ceiling_never_writes(self):
        original = (self.project / model_spend.FILE).read_bytes()
        for amount in (0, -1, True, False, 500.0, "500", None, float("inf"), float("nan"), 300):
            with self.subTest(amount=amount), self.assertRaises(model_spend.SpendControlError):
                self.amend(amount)
            self.assertEqual((self.project / model_spend.FILE).read_bytes(), original)

    def test_owner_run_and_explicit_note_are_required_and_trimmed(self):
        original = (self.project / model_spend.FILE).read_bytes()
        for field in ("actor", "run_id", "authorization_note"):
            for value in ("", " \n\t", None, 123, True):
                with self.subTest(field=field, value=value), self.assertRaises(model_spend.SpendControlError):
                    self.amend(**{field: value})
                self.assertEqual((self.project / model_spend.FILE).read_bytes(), original)
        changed = self.amend(actor=" Owner ", run_id=" run-123 ", authorization_note=" Approve 500 CNY. ")
        event = changed["authorization_events"][-1]
        self.assertEqual((event["actor"], event["run_id"], event["authorization_note"]),
                         ("Owner", "run-123", "Approve 500 CNY."))

    def test_total_configuration_is_not_restricted_to_300_tranches(self):
        model_spend.grant(self.project, new_ceiling_cny=600, actor="Owner", run_id="old-second")
        self.assertEqual(model_spend.read(self.project)["authorized_ceiling_cny"], 600)
        self.amend(500)
        model_spend.grant(self.project, new_ceiling_cny=725, actor="Owner", run_id="exact-total")
        result = model_spend.read(self.project, required=True)
        self.assertEqual(result["authorized_ceiling_cny"], 725)
        self.assertEqual([item["ceiling_cny"] for item in result["authorization_events"]], [300, 600, 500, 725])

    def test_concurrent_reservations_cannot_overbook_the_total_or_lose_charges(self):
        barrier = threading.Barrier(6)
        accepted, rejected = [], []
        def reserve(index):
            barrier.wait()
            try:
                accepted.append(model_spend.reserve(self.project, max_cost_cny=100, paper_id="P01",
                    paper_limit_cny=1, run_id=str(index)))
            except model_spend.SpendControlError:
                rejected.append(index)
        threads = [threading.Thread(target=reserve, args=(index,)) for index in range(6)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(15)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual((len(accepted), len(rejected)), (3, 3))
        state = model_spend.read(self.project)
        self.assertEqual(set(accepted), set(state["reservations"]))
        self.assertEqual(model_spend.reserved(state), 300)

    def test_actual_cost_above_reservation_only_blocks_when_total_is_exhausted(self):
        receipt = model_spend.reserve(self.project, max_cost_cny=1, paper_id="P01", paper_limit_cny=1, run_id="estimate")
        model_spend.settle(self.project, receipt, actual_cost_cny=10)
        model_spend.reserve(self.project, max_cost_cny=290, paper_id="P01", paper_limit_cny=1, run_id="remaining")
        with self.assertRaises(model_spend.SpendControlError):
            model_spend.reserve(self.project, max_cost_cny=0.01, paper_id=None, paper_limit_cny=1, run_id="exhausted")

    def test_nontranche_ceiling_needs_a_valid_complete_authorization_chain(self):
        self.amend()
        good = model_spend.read(self.project, required=True)
        variants = []
        for field, value in (("previous_ceiling_cny", 0), ("previous_ceiling_cny", 300.0),
                             ("kind", "unapproved"), ("authorization_note", " "),
                             ("actor", None), ("run_id", " "), ("ceiling_cny", 500.0),
                             ("ceiling_cny", 0), ("ceiling_cny", 300)):
            variant = copy.deepcopy(good)
            variant["authorization_events"][-1][field] = value
            variants.append(variant)
        missing = copy.deepcopy(good)
        del missing["authorization_events"][-1]["authorization_note"]
        variants.append(missing)
        unapproved = copy.deepcopy(good)
        unapproved["authorization_events"].pop()
        variants.append(unapproved)
        wrong_current = copy.deepcopy(good)
        wrong_current["authorized_ceiling_cny"] = 501
        variants.append(wrong_current)
        grant_disguised = copy.deepcopy(good)
        del grant_disguised["authorization_events"][-1]["kind"]
        variants.append(grant_disguised)
        for index, variant in enumerate(variants):
            with self.subTest(index=index):
                model_spend.write(self.project, variant)
                with self.assertRaises(model_spend.SpendControlError):
                    model_spend.read(self.project, required=True)

    def test_explicit_initial_amendment_does_not_fabricate_old_tranches(self):
        model_spend.write(self.project, model_spend.initial())
        result = self.amend()
        self.assertEqual(len(result["authorization_events"]), 1)
        self.assertEqual(result["authorization_events"][0]["previous_ceiling_cny"], 0)
        self.assertEqual(model_spend.read(self.project)["authorized_ceiling_cny"], 500)

    def test_amendment_requires_existing_authorization_state(self):
        (self.project / model_spend.FILE).unlink()
        with self.assertRaises(model_spend.SpendControlError):
            self.amend()
        self.assertFalse((self.project / model_spend.FILE).exists())
