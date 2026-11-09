"""Cycle decisions are real source bindings, never synthetic scientific achievements."""
import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_progress, research_notebook as notebook, researchctl
from scripts.research_artifacts import sha, write
from tests.research_cycle_fixtures import pending_decision
from tests.review_scope_fixtures import seal_review


class ResearchCycleDecisionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)/"demo"
        self.stage = "topic-intelligence"
        self.cycle = "actual-software-cycle"
        self.state = {"stage":self.stage,"stage_index":1,"gate":"G1","active_paper":"P01","paper_count":1,"status":"awaiting_work"}
        write(self.project/"state/run.json",self.state)

    def pending(self):
        return pending_decision(self.project,self.stage,self.cycle)

    def save(self,value):
        write(self.project/notebook.NOTEBOOK,value)

    def observed(self):
        value=self.pending()
        path=self.project/"evidence/negative.txt"
        path.parent.mkdir(parents=True)
        path.write_text("Synthetic negative observation: the proposed separation is not established.\n",encoding="utf-8")
        question=value["questions"][0]
        question["evidence"]=[{"id":"negative","stance":"contradicts","read_scope":"fulltext",
            "observation":"The synthetic negative observation keeps the proposed mechanism provisional.",
            "source":{"path":"evidence/negative.txt","sha256":sha(path),"locator":"line 1"}}]
        question["decisions"][0].update(outcome="changed",evidence_ids=["negative"],
            decision="Narrow the proposed mechanism claim because the distinguishing observation is absent.")
        self.save(value)
        return value,path

    def test_every_research_cycle_needs_its_own_nonempty_decision(self):
        value=self.pending()
        value["questions"][0]["decisions"]=[];self.save(value)
        with self.assertRaisesRegex(ValueError,"this research cycle"):
            notebook.cycle_review(self.project,self.stage,self.cycle)
        self.pending()
        with self.assertRaisesRegex(ValueError,"this research cycle"):
            notebook.cycle_review(self.project,self.stage,"later-cycle")
        self.assertEqual(notebook.cycle_review(self.project,"intake",self.cycle)["status"],"not_applicable")

    def test_pending_is_valid_without_fabricated_evidence_or_success(self):
        value=self.pending()
        result=notebook.cycle_review(self.project,self.stage,self.cycle)
        self.assertEqual(result["decisions"][0]["sources"],[])
        self.assertFalse(result["scientific_completion_verified"])
        value["questions"][0]["missing_evidence"]=[];self.save(value)
        with self.assertRaisesRegex(ValueError,"actual evidence"):
            notebook.cycle_review(self.project,self.stage,self.cycle)

    def test_changed_decision_needs_actual_evidence_and_discriminating_action(self):
        value=self.pending();decision=value["questions"][0]["decisions"][0]
        decision["outcome"]="changed";self.save(value)
        with self.assertRaisesRegex(ValueError,"actual evidence"):
            notebook.cycle_review(self.project,self.stage,self.cycle)
        value,_=self.observed()
        value["questions"][0]["decisions"][0]["discriminating_test"]="TBD";self.save(value)
        with self.assertRaisesRegex(ValueError,"discriminating_test"):
            notebook.cycle_review(self.project,self.stage,self.cycle)

    def test_current_paper_cannot_reuse_another_papers_decision(self):
        pending_decision(self.project,"experiment-design",self.cycle,"P02")
        with self.assertRaisesRegex(ValueError,"current paper"):
            notebook.cycle_review(self.project,"experiment-design",self.cycle)

    def test_omitted_negative_evidence_needs_explicit_scientific_disposition(self):
        value,_=self.observed()
        decision=value["questions"][0]["decisions"][0]
        decision.update(outcome="pending",evidence_ids=[]);self.save(value)
        with self.assertRaisesRegex(ValueError,"contrary evidence"):
            notebook.cycle_review(self.project,self.stage,self.cycle)
        decision["contrary_evidence_rationale"]="The negative result is retained; its different measurement does not settle this discriminator."
        self.save(value)
        self.assertEqual(notebook.cycle_review(self.project,self.stage,self.cycle)["decisions"][0]["outcome"],"pending")

    def test_only_actual_current_double_review_assesses_a_source_bound_decision(self):
        _,source=self.observed()
        self.assertEqual(notebook.cycle_assessment(self.project,self.stage,self.cycle)["status"],"pending")
        seal_review(self.project,self.state,gate="G1",run_id=self.cycle)
        result=notebook.cycle_assessment(self.project,self.stage,self.cycle)
        self.assertEqual(result["status"],"independently_reviewed",result)
        self.assertEqual(result["decisions"][0]["sources"][0]["sha256"],sha(source))
        self.assertFalse(result["scientific_completion_verified"])
        source.write_text("Changed observation after review.\n",encoding="utf-8")
        self.assertEqual(notebook.cycle_assessment(self.project,self.stage,self.cycle)["status"],"pending")

    def test_latest_review_cannot_be_reused_as_another_cycles_assessment(self):
        self.observed()
        seal_review(self.project,self.state,gate="G1",run_id="earlier-cycle")
        result=notebook.cycle_assessment(self.project,self.stage,self.cycle)
        self.assertEqual(result["status"],"awaiting_independent_review")
        self.assertTrue(any("this research cycle" in error for error in result["review_errors"]))

    def test_continuation_exposes_reviewed_negative_decision_without_certifying_science(self):
        with patch.object(researchctl,"PROJECTS_ROOT",self.project.parent),patch.object(researchctl,"gate_errors",return_value=["Science pending"]):
            before=cloud_progress.snapshot("demo")
            self.observed()
            seal_review(self.project,self.state,gate="G1",run_id=self.cycle)
            result=cloud_progress.record("demo",before,"different-github-job-id",0)
            self.assertEqual(result["semantic_progress"]["cycle_id"],self.cycle)
            self.assertEqual(result["semantic_progress"]["outcomes"][0]["outcome"],"changed")
            self.assertTrue(result["semantic_progress"]["outcomes"][0]["sources"])
            self.assertFalse(result["scientific_progress_verified"])
            repeat=cloud_progress.record("demo",cloud_progress.snapshot("demo"),"later-job",0)
            self.assertIsNone(repeat["semantic_progress"])

    def test_scientific_decision_survives_submission_transition_without_approving_submission(self):
        from scripts import research_phase, review_receipts
        from tests.test_quality_gate import report
        self.stage="writing-and-review"
        self.state.update(stage=self.stage,stage_index=5,gate="G5")
        write(self.project/"state/run.json",self.state)
        write(self.project/"papers/P01/paper-contract.json",{"paper_id":"P01"})
        quality = report("G1")
        write(self.project/"program/quality-G1.json", quality)
        with patch.object(researchctl,"PROJECTS_ROOT",self.project.parent),patch.object(researchctl,"gate_errors",return_value=["Science pending"]):
            before=cloud_progress.snapshot("demo")
            pending_decision(self.project,self.stage,self.cycle,"P01")
            seal_review(self.project,self.state,run_id=self.cycle)
            self.assertTrue(research_phase.enter_submission(self.project,[research_phase.SUBMISSION_PENDING]))
            quality["scores"]["publication_potential"] = 1
            write(self.project/"program/quality-G1.json", quality)
            self.assertTrue(review_receipts.validate_gate(self.project,"G5","P01"))
            result=cloud_progress.record("demo",before,"workflow-job",0)
        self.assertEqual(result["research_decision"]["status"],"historically_reviewed",result["research_decision"])
        self.assertFalse(result["research_decision"]["current_stage_authorized"])
        self.assertEqual(result["semantic_progress"]["assessment_scope"],"completed_scientific_writing")
        self.assertFalse(result["scientific_progress_verified"])
        write(self.project/"papers/P01/paper-contract.json",{"paper_id":"P01","changed_scientific_scope":True})
        self.assertEqual(notebook.cycle_assessment(self.project,self.stage,self.cycle)["status"],"pending")

    def test_archived_exploration_retains_its_actual_reviewed_decision(self):
        from tests.test_research_exploration import NativeExplorationTests
        from scripts import experiment_runner, research_phase, review_receipts
        case=NativeExplorationTests();case.setUp();self.addCleanup(case.doCleanups)
        case.start()
        before = {"experiment_attempts": cloud_progress.experiment_attempts(case.project)}
        experiment_runner.execute(case.slug)
        cycle="software-G4-"+sha(case.plan_path)[:12]
        pending_decision(case.project,"experiment-execution",cycle,"P01")
        case.complete()
        result=notebook.cycle_assessment(case.project,"experiment-execution",cycle,paper_id="P01")
        self.assertEqual(result["status"],"historically_reviewed",result)
        self.assertEqual(result["assessment_scope"],"archived_exploration")
        self.assertFalse(result["current_stage_authorized"])
        self.assertTrue(review_receipts.validate_gate(case.project,"G4","P01"))
        resources = cloud_progress.decision_resources(case.project, result, before,
            {"experiment_attempts": cloud_progress.experiment_attempts(case.project)})
        self.assertEqual(resources["experiments"]["new_this_cycle"]["attempt_count"], 1)
        self.assertGreater(resources["experiments"]["new_this_cycle"]["known_duration_seconds"], 0)
        self.assertEqual(resources["experiments"]["new_this_cycle"]["actual_cost_unknown_attempts"], 1)
        archive=research_phase.histories(case.project,"P01")[0]
        (case.project/archive["plan_path"]).write_text("{}",encoding="utf-8")
        self.assertEqual(notebook.cycle_assessment(case.project,"experiment-execution",cycle,paper_id="P01")["status"],"pending")

    def test_decision_resources_bind_model_cycle_and_count_failed_reservations_without_double_counting(self):
        from scripts import model_spend
        model_spend.write(self.project, model_spend.initial())
        model_spend.grant(self.project, new_ceiling_cny=300, actor="Synthetic fixture owner", run_id="fixture-grant")
        failed = model_spend.reserve(self.project, max_cost_cny=5, paper_id="P01", paper_limit_cny=300, run_id=self.cycle)
        model_spend.reserve(self.project, max_cost_cny=2, paper_id="P01", paper_limit_cny=300, run_id=self.cycle)
        rows = [
            {"run_id": self.cycle, "role": "persistent-writer", "duration_seconds": 4, "cost_cny": 2, "cost_status": "settled_gateway_debit", "completion_status": "completed"},
            {"run_id": self.cycle, "role": "independent-critic-initial", "duration_seconds": 2, "cost_cny": 0, "reserved_cost_cny": 5,
             "cost_status": "accounted_upper_bound", "reservation_id": failed, "transport_error_type": "TimeoutError", "zero_cost_not_confirmed": True},
            {"run_id": self.cycle, "role": "independent-critic-final", "duration_seconds": 3, "cost_cny": 1, "cost_status": "estimated_upper_bound"},
            {"run_id": self.cycle, "role": "persistent-writer", "duration_seconds": 4, "cost_cny": 0, "validation_status": "source_contract_failed_no_retry"},
            {"run_id": "another-cycle", "duration_seconds": 999, "cost_cny": 99, "cost_status": "settled_gateway_debit"}]
        with patch.object(researchctl,"PROJECTS_ROOT",self.project.parent), patch.object(researchctl,"gate_errors",return_value=["Science pending"]):
            # The unrelated prior cycle exists before this invocation; the
            # current cycle appends its actual usage after the controller snapshot.
            ledger = self.project / "state/model-usage.jsonl"
            ledger.write_text(json.dumps(rows[-1]) + "\n", encoding="utf-8")
            before = cloud_progress.snapshot("demo")
            with ledger.open("a", encoding="utf-8") as stream:
                stream.write("".join(json.dumps(row) + "\n" for row in rows[:-1]))
            self.pending()
            seal_review(self.project, self.state, gate="G1", run_id=self.cycle)
            report = cloud_progress.record("demo", before, "workflow-job", 0)
        resources = report["research_decision"]["resource_use"]
        self.assertEqual(resources["cycle_id"], self.cycle)
        model = resources["models"]
        self.assertEqual(model["known_duration_seconds"], 9)
        self.assertEqual(model["duration_unknown_attempts"], 1)
        self.assertEqual(model["cost_totals_cny"], {"verified_charge": 2, "estimated_or_calculated": 1, "pending_reservation": 7})
        self.assertEqual(len(model["attempts"]), 4)
        self.assertEqual(next(row for row in model["attempts"] if row.get("reservation_id") == failed)["status"], "failed")
        self.assertFalse(report["scientific_progress_verified"])
        model_spend.reconcile(self.project, failed, actual_cost_cny=4, actor="Synthetic fixture owner", run_id="fixture-reconciliation", evidence_note="Synthetic invoice fixture only.")
        reconciled = cloud_progress.decision_resources(self.project, report["research_decision"], before, report)["models"]
        self.assertEqual(reconciled["cost_totals_cny"], {"verified_charge": 6, "estimated_or_calculated": 1, "pending_reservation": 2})

    def test_confirmed_unsent_generation_is_zero_without_releasing_other_unknown_holds(self):
        from scripts import model_spend
        model_spend.write(self.project, model_spend.initial())
        model_spend.grant(self.project, new_ceiling_cny=300, actor='Synthetic fixture owner', run_id='fixture-grant')
        for index in range(3):
            model_spend.reserve(self.project, max_cost_cny=2, paper_id='P01', paper_limit_cny=300,
                                run_id='older-unknown-' + str(index))
        old_holds = model_spend.read(self.project)['reservations']
        ledger = self.project / 'state/model-usage.jsonl'
        for index in range(2):
            before = cloud_progress.snapshot(self.project)
            cycle = 'not-sent-' + str(index)
            reservation = model_spend.reserve(self.project, max_cost_cny=1, paper_id='P01', paper_limit_cny=300, run_id=cycle)
            model_spend.cancel_unsent(self.project, reservation, reason='Synthetic pre-transport claim failed; no generation request was sent.')
            with ledger.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'run_id': cycle, 'reservation_id': reservation, 'cache_hit': False,
                    'cost_cny': None, 'reserved_cost_cny': 1, 'cost_status': 'accounted_upper_bound',
                    'transport_error_type': 'SpendControlError', 'zero_cost_not_confirmed': True}) + '\n')
            raw_ledger = ledger.read_bytes()
            report = cloud_progress.record(self.project, before, cycle, 1)
            self.assertEqual(report['model_cycles'], 0)
            self.assertEqual(report['stalled_cycles'], 0)
            model = report['research_decision']['resource_use']['models']
            self.assertEqual(model['cost_totals_cny']['pending_reservation'], 0)
            self.assertEqual(model['attempts'][0]['cost_kind'], 'confirmed_not_sent')
            self.assertEqual(model['attempts'][0]['cost_cny'], 0)
            self.assertEqual(ledger.read_bytes(), raw_ledger)
            self.assertEqual(model_spend.read(self.project)['reservations'], old_holds)
        self.assertIsNone(cloud_progress.pause_reason(self.project))
        # A raw usage flag is not native cancellation evidence; its existing hold remains charged.
        before = cloud_progress.snapshot(self.project)
        unknown = model_spend.reserve(self.project, max_cost_cny=1, paper_id='P01', paper_limit_cny=300, run_id='unknown')
        with ledger.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'run_id': 'unknown', 'reservation_id': unknown, 'cache_hit': False,
                'generation_sent': False, 'cost_status': 'accounted_upper_bound', 'reserved_cost_cny': 1}) + '\n')
        report = cloud_progress.record(self.project, before, 'unknown', 1)
        self.assertEqual(report['stalled_cycles'], 1)
        self.assertEqual(report['research_decision']['resource_use']['models']['cost_totals_cny']['pending_reservation'], 1)
        for key, value in old_holds.items():
            self.assertEqual(model_spend.read(self.project)['reservations'][key], value)

    def test_decision_resources_separate_new_attempts_from_cited_prior_evidence_and_currencies(self):
        def receipt(name, cost, duration, status, actual=None):
            output = self.project / ("results/" + name + ".txt")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("Synthetic evidence only.\n", encoding="utf-8")
            item = {"attempt_id": name, "paper_id": "P01", "status": status, "runtime_seconds": duration,
                "estimated_cost_usd": cost, "reported_cost_usd": actual,
                "outputs": [{"path": output.relative_to(self.project).as_posix(), "sha256": sha(output)}]}
            write(self.project / "experiments/runs" / name / "run.json", item)
            with (self.project / "experiments/registry.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item) + "\n")
            return item["outputs"][0]
        evidence = receipt("prior", 3, 10, "succeeded", actual=4)
        receipt("unrelated-prior", 50, 100, "succeeded", actual=50)
        before = {"experiment_attempts": cloud_progress.experiment_attempts(self.project)}
        receipt("failed-new", 2, 5, "failed")
        after = {"experiment_attempts": cloud_progress.experiment_attempts(self.project)}
        decision = {"cycle_id": self.cycle, "decisions": [{"sources": [evidence, evidence]}]}
        result = cloud_progress.decision_resources(self.project, decision, before, after)
        self.assertEqual(result["models"]["currency"], "CNY")
        self.assertEqual(result["experiments"]["currency"], "USD")
        self.assertEqual(result["experiments"]["new_this_cycle"]["accounted_cost_usd"], 2)
        self.assertEqual(result["experiments"]["cited_prior_evidence"]["accounted_cost_usd"], 4)
        self.assertEqual(result["experiments"]["cited_prior_evidence"]["known_duration_seconds"], 10)
        self.assertEqual(result["experiments"]["new_this_cycle"]["actual_cost_unknown_attempts"], 1)
        self.assertEqual(len(result["experiments"]["attempts"]), 2)
        self.assertTrue(any(row["status"] == "failed" for row in result["experiments"]["attempts"]))
        (self.project / after["experiment_attempts"][-1]["receipt_path"]).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "receipt changed"):
            cloud_progress.decision_resources(self.project, decision, before, after)

    def test_failed_writer_cost_is_reported_without_a_notebook_or_final_review(self):
        ledger = self.project / "state/model-usage.jsonl"
        row = {"run_id": self.cycle, "role": "persistent-writer", "duration_seconds": 4,
               "cost_cny": 2, "cost_status": "settled_gateway_debit", "completion_status": "completed"}
        with patch.object(researchctl, "PROJECTS_ROOT", self.project.parent), patch.object(researchctl, "gate_errors", return_value=["Science pending"]):
            before = cloud_progress.snapshot("demo")
            ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
            report = cloud_progress.record("demo", before, "different-workflow-job", 1)
        decision = report["research_decision"]
        self.assertEqual(decision["status"], "pending")
        self.assertEqual(decision["decisions"], [])
        self.assertFalse((self.project / notebook.NOTEBOOK).exists())
        self.assertIsNone(report["semantic_progress"])
        resources = decision["resource_use"]
        self.assertEqual(resources["cycle_id"], self.cycle)
        self.assertEqual(resources["models"]["known_duration_seconds"], 4)
        self.assertEqual(resources["models"]["cost_totals_cny"]["verified_charge"], 2)
        self.assertEqual(len(resources["models"]["attempts"]), 1)

    def test_failed_current_cycle_cannot_reuse_an_older_review_or_its_charges(self):
        self.observed()
        seal_review(self.project, self.state, gate="G1", run_id=self.cycle)
        ledger = self.project / "state/model-usage.jsonl"
        old = {"run_id": self.cycle, "duration_seconds": 99, "cost_cny": 99, "cost_status": "settled_gateway_debit"}
        ledger.write_text(json.dumps(old) + "\n", encoding="utf-8")
        fresh = {"run_id": "new-failed-cycle", "duration_seconds": 4, "cost_cny": 2, "cost_status": "settled_gateway_debit"}
        with patch.object(researchctl, "PROJECTS_ROOT", self.project.parent), patch.object(researchctl, "gate_errors", return_value=["Science pending"]):
            before = cloud_progress.snapshot("demo")
            with ledger.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(fresh) + "\n")
                stream.write(json.dumps({**fresh, "validation_status": "source_contract_failed_no_retry"}) + "\n")
            report = cloud_progress.record("demo", before, "workflow-job", 1)
            later = [cloud_progress.record("demo", cloud_progress.snapshot("demo"), "no-new-invocation", code) for code in (0, 1)]
        decision = report["research_decision"]
        self.assertEqual((decision["status"], decision["cycle_id"]), ("pending", "new-failed-cycle"))
        self.assertIsNone(report["semantic_progress"])
        self.assertEqual(decision["resource_use"]["models"]["known_duration_seconds"], 4)
        self.assertEqual(decision["resource_use"]["models"]["cost_totals_cny"]["verified_charge"], 2)
        self.assertEqual(len(decision["resource_use"]["models"]["attempts"]), 1)
        for unchanged in later:
            self.assertIsNone(unchanged["semantic_progress"])
            self.assertIsNone(unchanged["research_decision"]["resource_use"]["cycle_id"])
            self.assertEqual(unchanged["research_decision"]["resource_use"]["models"]["attempts"], [])
            self.assertTrue(unchanged["research_decision"]["resource_use"]["unknown"])
        self.assertEqual(len(ledger.read_text().splitlines()), 3)

    def test_failed_cli_current_journal_keeps_subscription_cost_unknown(self):
        journal = {"run_id": self.cycle + "-" + self.stage, "stage": self.stage,
                   "started_at": "2026-11-06T00:00:00+00:00", "finished_at": "2026-11-06T00:00:12+00:00", "status": "failed"}
        with patch.object(researchctl, "PROJECTS_ROOT", self.project.parent), patch.object(researchctl, "gate_errors", return_value=["Science pending"]):
            before = cloud_progress.snapshot("demo")
            write(self.project / "state/autopilot.json", journal)
            write(self.project / "state/runs" / journal["run_id"] / "journal.json", journal)
            report = cloud_progress.record("demo", before, "workflow-job", 1)
        resources = report["research_decision"]["resource_use"]
        self.assertEqual(resources["cycle_id"], self.cycle)
        self.assertEqual(resources["cli"]["duration_seconds"], 12)
        self.assertIsNone(resources["cli"]["cost"])
        self.assertTrue(resources["unknown"])
        self.assertFalse(report["scientific_progress_verified"])

    def test_interrupted_call_keeps_its_new_native_reservation_without_a_usage_row(self):
        from scripts import model_spend
        model_spend.write(self.project, model_spend.initial())
        model_spend.grant(self.project, new_ceiling_cny=300, actor="Synthetic fixture owner", run_id="fixture-grant")
        with patch.object(researchctl, "PROJECTS_ROOT", self.project.parent), patch.object(researchctl, "gate_errors", return_value=["Science pending"]):
            before = cloud_progress.snapshot("demo")
            reservation = model_spend.reserve(self.project, max_cost_cny=5, paper_id="P01", paper_limit_cny=300, run_id=self.cycle)
            report = cloud_progress.record("demo", before, "workflow-job", 1)
        resources = report["research_decision"]["resource_use"]
        self.assertEqual(resources["cycle_id"], self.cycle)
        self.assertEqual(resources["models"]["cost_totals_cny"]["pending_reservation"], 5)
        self.assertEqual(resources["models"]["cost_totals_cny"]["verified_charge"], 0)
        self.assertEqual(resources["models"]["attempts"][0]["reservation_id"], reservation)
        self.assertIsNone(resources["models"]["known_duration_seconds"])
        self.assertTrue(resources["unknown"])

    def test_changed_historical_ledger_cannot_be_guessed_into_current_cycle(self):
        ledger = self.project / "state/model-usage.jsonl"
        row = {"run_id": "prior-cycle", "cost_cny": 9, "cost_status": "settled_gateway_debit"}
        ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
        with patch.object(researchctl, "PROJECTS_ROOT", self.project.parent), patch.object(researchctl, "gate_errors", return_value=["Science pending"]):
            before = cloud_progress.snapshot("demo")
            ledger.write_text(json.dumps({**row, "run_id": self.cycle}) + "\n", encoding="utf-8")
            report = cloud_progress.record("demo", before, "workflow-job", 1)
        resources = report["research_decision"]["resource_use"]
        self.assertEqual(resources["models"]["attempts"], [])
        self.assertTrue(any("prior usage ledger changed" in item for item in resources["unknown"]))

    def test_cli_subscription_and_missing_cost_duration_remain_unknown(self):
        path = self.project / "state/runs" / (self.cycle + "-" + self.stage) / "journal.json"
        write(path, {"run_id": path.parent.name, "stage": self.stage, "started_at": "2026-11-06T00:00:00+00:00",
            "finished_at": "2026-11-06T00:00:12+00:00", "status": "needs_work"})
        decision = {"cycle_id": self.cycle, "decisions": []}
        item = {"attempt_id": "legacy-failure", "paper_id": "P01", "status": "failed", "outputs": []}
        write(self.project / "experiments/runs/legacy-failure/run.json", item)
        (self.project / "experiments/registry.jsonl").write_text(json.dumps(item) + "\n", encoding="utf-8")
        result = cloud_progress.decision_resources(self.project, decision, {},
            {"experiment_attempts": cloud_progress.experiment_attempts(self.project)})
        self.assertEqual(result["cli"]["duration_seconds"], 12)
        self.assertIsNone(result["cli"]["cost"])
        self.assertIsNone(result["cli"]["currency"])
        self.assertIsNone(result["models"]["known_duration_seconds"])
        self.assertTrue(result["unknown"])
        self.assertEqual(result["cli"]["source"]["sha256"], sha(path))
        self.assertEqual(result["experiments"]["new_this_cycle"]["duration_unknown_attempts"], 1)
        self.assertEqual(result["experiments"]["new_this_cycle"]["accounted_cost_unknown_attempts"], 1)
        self.assertEqual(result["experiments"]["new_this_cycle"]["actual_cost_unknown_attempts"], 1)
