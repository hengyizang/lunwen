"""Real receipt shapes, unknown fields, neutral criticism and unchanged authority."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import research_iteration as iteration
from scripts.research_artifacts import read, record, sha, write


class ResearchIterationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        self.root = Path(self.temporary.name) / "code"
        self.cloud = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"})
        self.cloud.start()
        self.addCleanup(self.cloud.stop)
        for module in (iteration.MODULE, "scripts/primary_recovery.py", "scripts/research_artifacts.py", "scripts/output_provenance.py"):
            path = self.root / module
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("bound module fixture\n", encoding="utf-8")
        self.code = self.project / "experiments/model.py"
        self.code.parent.mkdir(parents=True)
        self.code.write_text("print('recorded fixture only')\n", encoding="utf-8")
        self.data = self.project / "data/development.csv"
        self.data.parent.mkdir()
        self.data.write_text("id,value\n1,3\n", encoding="utf-8")
        inputs = [{"path": p.relative_to(self.project).as_posix(), "sha256": sha(p)} for p in (self.code, self.data)]
        self.plan = {"schema_version": "1.0", "status": "ready_for_review", "runs": []}
        for index, name in enumerate(("one", "two", "three"), 1):
            self.plan["runs"].append({"run_id": name, "paper_id": "P01", "cwd": ".",
                "argv": ["python", "experiments/model.py", "--data=data/development.csv", "--output=experiments/results/" + name + ".json", "--alpha", "0.1"],
                "seed": 1 if index < 3 else 2, "inputs": inputs,
                "expected_outputs": ["experiments/results/" + name + ".json"],
                "timeout_seconds": 60, "estimated_cost_usd": 0,
                "isolation": {"kind": "container", "engine": "docker", "image": "example/runtime@sha256:" + "a" * 64}})
        write(self.project / "experiments/plan.json", self.plan)
        self.protocol = {"schema_version": "1.0", "paper_id": "P01", "comparisons": [
            {"analysis_phase": "confirmatory", "pairs": [{"treatment": {"run_id": name, "output": "experiments/results/" + name + ".json"}}]}
            for name in ("one", "two", "three")]}
        write(self.project / "papers/P01/experiment-evidence-plan.json", self.protocol)
        write(self.project / "papers/P01/experiments/main.json", {"run_ids": ["one", "two", "three"],
            "hypothesis_ids": ["H1"], "reproduction_plan": {"original_run_ids": ["one"], "clean_room_run_ids": ["two"]}})
        write(self.project / "experiments/budget.json", {"hard_ceiling_usd": 10})
        write(self.project / "state/run.json", {"stage": "experiment-execution", "gate": "G4", "approved_gates": ["G0", "G1", "G2", "G3"]})
        self.freeze()
        write(self.project / "intake/constraints.json", {"execution_mode": "cloud_only"})
        write(self.project / "program/hypothesis-register.json", {"hypotheses": [{"hypothesis_id": "H1",
            "prediction": "Prespecified result requiring scientific review.", "source_anchors": [
                {"path": "data/development.csv", "sha256": sha(self.data), "locator": "L2"}]}]})
        self.relative = "program/research-iteration.json"
        self.request = {"kind": "research_iteration", "id": "iteration-fixture", "max_items": 4}
        write(self.project / self.relative, self.request)

    def freeze(self):
        files = ["papers/P01/experiment-evidence-plan.json", "papers/P01/experiments/main.json"]
        write(self.project / "papers/P01/preregistration.json", {"status": "frozen",
            "files": [{"path": name, "sha256": sha(self.project / name)} for name in files]})
        state = read(self.project / "state/run.json")
        state["approvals"] = [{"gate": "G3", "experiment_plan_sha256": sha(self.project / "experiments/plan.json"),
            "frozen_protocol_sha256": {"papers/P01/preregistration.json": sha(self.project / "papers/P01/preregistration.json")}}]
        write(self.project / "state/run.json", state)

    def attempt(self, run_id, *, status="succeeded", error=None, log="", exit_code=0, mutate=None):
        run = next(r for r in self.plan["runs"] if r["run_id"] == run_id)
        attempt_id = run_id + "-attempt-001"
        folder = self.project / "experiments/runs" / attempt_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "stdout.txt").write_text("metric=0.0001; negative result retained\n", encoding="utf-8")
        (folder / "stderr.txt").write_text(log, encoding="utf-8")
        output = self.project / run["expected_outputs"][0]
        write(output, {"metric": 0.0001, "scientific_decision": "below registered threshold"})
        hour = {"one": "01", "two": "02", "three": "03"}[run_id]
        item = {"schema_version": "1.0", "run_id": run_id, "attempt_id": attempt_id, "paper_id": "P01",
            "status": status, "started_at": "2026-10-28T" + hour + ":00:00Z", "finished_at": "2026-10-28T" + hour + ":01:00Z",
            "argv": run["argv"], "cwd": run["cwd"], "seed": run["seed"], "timeout_seconds": 60,
            "timed_out": status == "timed_out", "exit_code": exit_code,
            "estimated_cost_usd": 0, "reported_cost_usd": None, "git_commit": "b" * 40,
            "approved_plan_sha256": sha(self.project / "experiments/plan.json"),
            "inputs": [{**i, "bytes": (self.project / i["path"]).stat().st_size} for i in run["inputs"]],
            "input_integrity": {"verified_after_run": True, "passed": True, "mutated_or_missing": []},
            "executor_isolation": {"kind": "container", "instance_id": attempt_id,
                "image_digest": "a" * 64, "network_disabled": True, "isolated_executor": True},
            "runtime": {"python": "3.12", "platform": "fixture"},
            "outputs": [{"path": run["expected_outputs"][0], "sha256": sha(output), "bytes": output.stat().st_size}],
            "missing_outputs": [], "error": error,
            "logs": {"stdout": (folder / "stdout.txt").relative_to(self.project).as_posix(),
                "stderr": (folder / "stderr.txt").relative_to(self.project).as_posix(),
                "stdout_truncated": False, "stderr_truncated": False}}
        if mutate:
            mutate(item)
        write(folder / "run.json", item)
        registry = self.project / "experiments/registry.jsonl"
        with registry.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item) + "\n")
        return item

    def prepare(self):
        return iteration.refresh(self.project, self.relative, root=self.root)

    def context(self, result, role="critic"):
        return iteration.model_context(self.project, result["report_path"], role, root=self.root)

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}

    def test_configuration_compares_across_run_ids_output_names_and_preserves_replication(self):
        for name in ("one", "two", "three"):
            self.attempt(name)
        result = self.prepare()
        matches = result["equivalent_configurations"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["run_ids"], ["one", "two"])
        self.assertTrue(matches[0]["declared_replication"])
        self.assertIn("retain_all_attempts", matches[0]["action"])
        self.assertEqual(len(result["attempts"]), 3)
        self.assertNotEqual(result["attempts"][0]["configuration"]["fingerprint"], result["attempts"][2]["configuration"]["fingerprint"])
        self.assertTrue(all(not a["diagnostics"] for a in result["attempts"]))
        self.assertEqual(result["experiments_executed"], 0)

    def test_missing_configuration_cannot_be_deduplicated_from_shared_environment(self):
        self.attempt("one", mutate=lambda row: row.pop("seed"))
        self.attempt("two", mutate=lambda row: row.update({"inputs": []}))
        result = self.prepare()
        self.assertFalse(result["equivalent_configurations"])
        self.assertIn("seed", result["attempts"][0]["configuration"]["unknown_fields"])
        self.assertIn("code_hashes", result["attempts"][1]["configuration"]["unknown_fields"])
        self.assertIsNone(result["attempts"][0]["configuration"]["fingerprint"])

    def test_host_python_version_without_sealed_environment_remains_unknown(self):
        self.attempt("one", mutate=lambda row: row.update({"executor_isolation": {"kind": "host"}}))
        result = self.prepare()
        self.assertIn("environment", result["attempts"][0]["configuration"]["unknown_fields"])
        self.assertIsNone(result["attempts"][0]["configuration"]["fingerprint"])

    def test_receipt_input_hash_disagrees_with_sealed_plan_disables_equivalence(self):
        self.attempt("one")
        def change_input(row):
            row["inputs"][1]["sha256"] = "c" * 64
        self.attempt("two", mutate=change_input)
        result = self.prepare()
        second = result["attempts"][1]
        self.assertIn("receipt_plan_mismatch", {d["code"] for d in second["diagnostics"]})
        self.assertIn("receipt_plan_consistency", second["configuration"]["unknown_fields"])
        self.assertIsNone(second["configuration"]["fingerprint"])
        self.assertFalse(result["equivalent_configurations"])

    def test_parameters_and_phase_are_effective_configuration(self):
        self.plan["runs"][1]["argv"][-1] = "0.2"
        write(self.project / "experiments/plan.json", self.plan)
        self.protocol["comparisons"][1]["analysis_phase"] = "exploratory"
        write(self.project / "papers/P01/experiment-evidence-plan.json", self.protocol)
        self.freeze()
        self.attempt("one")
        self.attempt("two")
        result = self.prepare()
        self.assertFalse(result["equivalent_configurations"])
        self.assertEqual(result["attempts"][1]["analysis_phase"], ["exploratory"])
        self.assertIn("0.2", result["attempts"][1]["configuration"]["effective"]["argv_parameters"])

    def test_successful_poor_scientific_metric_is_never_a_bug(self):
        self.attempt("one", log="Scientific null result, metric below target. ModuleNotFoundError mentioned as prior literature.")
        result = self.prepare()
        self.assertFalse(result["attempts"][0]["diagnostics"])
        self.assertEqual(result["attempts"][0]["scientific_outcome"], "not_assessed_from_execution_status")
        self.assertFalse(any(w.get("kind") == "inspect_recorded_condition" for w in result["next_iteration_worklist"]))

    def test_nonzero_exit_with_metric_threshold_does_not_establish_an_engineering_bug(self):
        self.attempt("one", status="failed", exit_code=1, error="Metric did not exceed the prespecified threshold.")
        result = self.prepare()
        self.assertEqual(result["attempts"][0]["diagnostics"][0]["code"], "execution_failed")
        self.assertEqual(result["attempts"][0]["diagnostics"][0]["condition"], "incomplete_execution")
        self.assertFalse(any(d["condition"] == "engineering_failure" for d in result["attempts"][0]["diagnostics"]))

    def test_unsealed_phase_change_is_unknown_instead_of_relabeling_a_run(self):
        self.protocol["comparisons"][0]["analysis_phase"] = "exploratory"
        write(self.project / "papers/P01/experiment-evidence-plan.json", self.protocol)
        self.attempt("one")
        result = self.prepare()
        self.assertIsNone(result["attempts"][0]["analysis_phase"])
        self.assertIn("analysis_phase", result["attempts"][0]["configuration"]["unknown_fields"])
        self.assertIsNone(result["attempts"][0]["configuration"]["fingerprint"])

    def test_actual_failure_missing_output_and_past_condition_have_source_bound_proposals(self):
        self.attempt("one", status="failed", exit_code=1, log="Traceback\nModuleNotFoundError: No module named 'actual_dependency'\n")
        self.attempt("two", status="failed", exit_code=1, log="ModuleNotFoundError: No module named 'actual_dependency'\n",
                     mutate=lambda row: row.update({"missing_outputs": ["experiments/results/missing.json"]}))
        result = self.prepare()
        self.assertIn("logged_modulenotfounderror", {d["code"] for d in result["attempts"][0]["diagnostics"]})
        self.assertIn("expected_output_missing", {d["code"] for d in result["attempts"][1]["diagnostics"]})
        self.assertEqual(result["similar_past_lessons"][0]["earlier_attempt_id"], "one-attempt-001")
        self.assertIn("no successful repair", result["similar_past_lessons"][0]["scope"])
        self.assertLessEqual(len(result["next_iteration_worklist"]), 4)
        self.assertTrue(all(w["status"] == "proposal_only_not_executed" for w in result["next_iteration_worklist"]))

    def test_timeout_and_input_integrity_are_distinct_from_measurement(self):
        self.attempt("one", status="timed_out", exit_code=None,
            mutate=lambda row: row.update({"input_integrity": {"verified_after_run": True, "passed": False,
                "mutated_or_missing": [{"path": "data/development.csv", "reason": "hash_changed"}]}}))
        result = self.prepare()
        codes = {d["code"] for d in result["attempts"][0]["diagnostics"]}
        self.assertTrue({"execution_timed_out", "input_integrity_failed"} <= codes)
        self.assertIn("post_run_input_integrity", result["attempts"][0]["configuration"]["unknown_fields"])

    def test_noop_and_context_do_not_rewrite_report_provenance_or_authority(self):
        self.attempt("one")
        authority = {name: (self.project / name).read_bytes() for name in
            ("experiments/plan.json", "experiments/budget.json", "experiments/registry.jsonl", "state/run.json")}
        result = self.prepare()
        before = self.snapshot()
        with patch.object(iteration, "write", side_effect=AssertionError("no writes")), patch.object(iteration, "record", side_effect=AssertionError("no provenance writes")):
            self.assertEqual(self.prepare(), result)
            for role in ("planner", "writer", "critic", "remediator"):
                self.context(result, role)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(authority, {name: (self.project / name).read_bytes() for name in authority})
        self.assertEqual(result["paid_calls"], 0)

    def test_independent_critic_receives_facts_without_repairs_or_author_narrative(self):
        self.attempt("one", status="failed", exit_code=1, log="ModuleNotFoundError: actual_dependency\n")
        result = self.prepare()
        critic = json.loads(self.context(result))
        self.assertEqual(critic["attempt_facts"][0]["observed_conditions"], ["logged_modulenotfounderror"])
        self.assertNotIn("next_iteration_worklist", critic)
        self.assertNotIn("similar_past_lessons", critic)
        for forbidden in ("remedy_proposal", "minimal_check", "next test", "smallest source-backed correction"):
            self.assertNotIn(forbidden, self.context(result))
        self.assertIn("next_iteration_worklist", json.loads(self.context(result, "writer")))

    def test_changed_request_input_log_phase_authority_or_builder_invalidates_context(self):
        self.attempt("one")
        result = self.prepare()
        targets = [self.project / self.relative, self.data, self.project / "experiments/runs/one-attempt-001/stderr.txt",
            self.project / "papers/P01/experiment-evidence-plan.json", self.project / "state/run.json", self.root / iteration.MODULE]
        for target in targets:
            original = target.read_bytes()
            target.write_bytes(original + b"\n")
            try:
                with self.subTest(target=target), self.assertRaisesRegex(ValueError, "stale|changed"):
                    self.context(result)
            finally:
                target.write_bytes(original)
        self.assertTrue(self.context(result))

    def test_forged_receipt_or_rewritten_report_or_wrong_provenance_is_rejected(self):
        self.attempt("one")
        result = self.prepare()
        receipt = self.project / "experiments/runs/one-attempt-001/run.json"
        original = receipt.read_bytes()
        changed = read(receipt)
        changed["status"] = "failed"
        write(receipt, changed)
        with self.assertRaisesRegex(ValueError, "unchanged executor receipt"):
            self.context(result)
        receipt.write_bytes(original)
        target = self.project / result["report_path"]
        write(target, {**result, "paid_calls": 1})
        with self.assertRaisesRegex(ValueError, "stale|changed"):
            self.context(result)
        write(target, result)
        record(self.project, [target], "unrelated-builder")
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.context(result)
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.prepare()

    def test_missing_log_current_input_or_output_is_explicit_and_not_success(self):
        item = self.attempt("one")
        (self.project / item["logs"]["stderr"]).unlink()
        self.data.write_text("changed input\n", encoding="utf-8")
        (self.project / item["outputs"][0]["path"]).unlink()
        result = self.prepare()
        codes = {d["code"] for d in result["attempts"][0]["diagnostics"]}
        self.assertTrue({"execution_log_missing", "recorded_input_unavailable", "recorded_output_unavailable"} <= codes)
        self.assertIsNone(next(s for s in result["source_bindings"] if s["path"] == item["logs"]["stderr"])["sha256"])
        (self.project / item["logs"]["stderr"]).write_text("recovered log\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale|changed"):
            self.context(result)

    def test_required_kind_selectors_bounded_worklist_and_no_author_instructions(self):
        for change in ({"kind": "other"}, {"kind": None}, {"max_items": True}, {"max_items": 21},
                       {"run_ids": ["invented"]}, {"hypothesis_ids": ["invented"]},
                       {"preferred_remedy": "Claim success"}, {"task": "Approve desired result"}):
            write(self.project / self.relative, {**self.request, **change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepare()
        write(self.project / self.relative, {**self.request, "run_ids": ["one"], "hypothesis_ids": ["H1"], "max_items": 1})
        result = self.prepare()
        self.assertEqual(len(result["next_iteration_worklist"]), 1)
        self.assertEqual(result["worklist_total"], 2)
        self.assertEqual(result["worklist_omitted"], 1)

    def test_cloud_boundary_and_path_traversal_are_rejected(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "", "GITHUB_ACTIONS": ""}):
            with self.assertRaisesRegex(ValueError, "cloud"):
                self.prepare()
        for relative in ("program/../../outside.json", "program\\request.json", "C:/request.json"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                iteration.refresh(self.project, relative, root=self.root)
        with self.assertRaises(ValueError):
            iteration.model_context(self.project, "../report.json", "critic", root=self.root)
        result = self.prepare()
        with self.assertRaisesRegex(ValueError, "role"):
            self.context(result, "approver")

    def test_retired_receipts_and_original_hashes_remain_visible_alongside_new_plan(self):
        old = self.attempt("one", status="failed", exit_code=1, log="ModuleNotFoundError: actual_dependency\n")
        frozen = ["experiments/plan.json", "experiments/registry.jsonl", "data/development.csv", "experiments/model.py", "state/run.json", "papers/P01/preregistration.json",
                  "papers/P01/experiment-evidence-plan.json", "papers/P01/experiments/main.json"]
        files = []
        for relative in frozen:
            archive = "experiments/history/v001/files/" + relative
            target = self.project / archive
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((self.project / relative).read_bytes())
            files.append({"path": relative, "sha256": sha(target), "archive": archive})
        retained = []
        for output in old["outputs"]:
            path = "experiments/recovery-artifacts/one-attempt-001/" + output["sha256"] + ".json"
            target = self.project / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((self.project / output["path"]).read_bytes())
            retained.append({"path": path, "sha256": output["sha256"], "original_path": output["path"], "attempt_id": old["attempt_id"]})
        manifest = {"version": "v001", "files": files,
            "attempt_receipts": [{"path": "experiments/runs/one-attempt-001/run.json", "sha256": sha(self.project / "experiments/runs/one-attempt-001/run.json")}],
            "retained_outputs": retained}
        write(self.project / "experiments/history/v001/manifest.json", manifest)
        write(self.project / "state/primary-recovery/versions/v001.json", {"manifest_sha256": sha(self.project / "experiments/history/v001/manifest.json")})
        (self.project / "experiments/registry.jsonl").write_text("", encoding="utf-8")
        self.data.write_text("id,value\n1,4\n", encoding="utf-8")
        self.plan["runs"] = [r for r in self.plan["runs"] if r["run_id"] != "one"]
        for run in self.plan["runs"]:
            run["inputs"][1]["sha256"] = sha(self.data)
        write(self.project / "experiments/plan.json", self.plan)
        self.attempt("two", status="failed", exit_code=1, log="ModuleNotFoundError: actual_dependency\n")
        result = self.prepare()
        self.assertEqual({a["run_id"] for a in result["attempts"]}, {"one", "two"})
        archived = next(a for a in result["attempts"] if a["run_id"] == "one")
        self.assertEqual(archived["history_version"], "v001")
        self.assertTrue(all(i["status"] == "matches_recorded_hash" for i in archived["input_facts"]))
        self.assertTrue(all(i["status"] == "matches_recorded_hash" for i in archived["output_facts"]))
        self.assertFalse(result["equivalent_configurations"])
        self.assertEqual(archived["analysis_phase"], ["confirmatory"])
        lesson = next(row for row in result["similar_past_lessons"] if row["attempt_id"] == "two-attempt-001")
        self.assertEqual(lesson["earlier_attempt_id"], "one-attempt-001")


if __name__ == "__main__":
    unittest.main()
