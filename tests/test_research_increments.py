"""Engineering acceptance only; fixtures never demonstrate scientific completion."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import incremental_evidence as evidence, incremental_writing as writing
from scripts import incremental_rules as rules, research_increments as increments
from scripts import evidence_context, output_provenance, model_spend
from scripts.research_artifacts import read, sha, write


class IncrementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.paper = self.project / "papers/P01"
        self.paper.mkdir(parents=True)
        self.put("papers/P01/manuscript/main.tex", "First bounded observation.\n\nSecond scoped argument.\n")
        self.put("evidence/source.md", "Source observation has a stated limitation.\nA different source line.\n")
        write(self.paper / "reviews/paper-facts.json", {"facts": [{"id": "F1", "statement": "bounded"}]})
        write(self.project / "state/run.json", {"stage": "writing-and-review", "gate": "G5",
                                               "status": "awaiting_work", "active_paper": "P01",
                                               "approved_gates": ["G0"]})
        write(self.project / "state/model-spend-control.json", model_spend.initial())
        self.spec = increments.initialize(self.project)

    def put(self, relative, content):
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": relative, "sha256": sha(target)}

    def save(self):
        write(self.project / increments.PLAN, self.spec)

    def anchor(self):
        return {"path": "evidence/source.md", "sha256": sha(self.project / "evidence/source.md"),
                "kind": "source_lines", "start_line": 1, "end_line": 1,
                "quote": "Source observation has a stated limitation."}

    def argument(self):
        units = writing.inventory(self.project, "P01")["units"]
        row = {"id": "A1", "paper_id": "P01", "precedence": [{"before": "P1", "after": "P2"}],
               "paragraphs": [{"paragraph_id": "P" + str(index), "section": "Introduction",
                               "function": "context", "purpose": "Provide bounded context",
                               "claim_ids": ["F1"], "inference_boundary": "source scope only",
                               "transition": "next premise", "units": [
                                   {"unit_id": unit["unit_id"], "sha256": unit["sha256"]}]}
                              for index, unit in enumerate(units, 1)]}
        writing.freeze_plan(self.project, row, phase="before_writer")
        return row

    def lineage(self):
        return {"id": "L1", "paper_id": "P01", "nodes": [
            {"id": "N1", "kind": "primary_finding", "research_state": "unknown",
             "read_scope": "abstract", "statement": "bounded published observation",
             "boundary": "abstract only", "parents": [], "evidence": [self.anchor()]}],
            "fact_links": [{"fact_id": "F1", "node_id": "N1"}]}

    def lesson(self):
        cases = []
        for split in ("development", "validation", "holdout"):
            for flag in (True, False):
                key = split + ("_positive" if flag else "_negative")
                source = self.put("evidence/cases/" + key + ".txt",
                                  split + (" unsupported observation" if flag else " calibrated finding"))
                cases.append({"id": key, "group_id": key, "split": split, "source": source,
                              "expected_flag": flag, "rationale": "Declared synthetic checker fixture"})
        write(self.project / "evidence/benchmark.json", {"cases": cases})
        return {"id": "RULE1", "lesson": self.anchor(), "failure": "Unsupported wording",
                "root_cause": "Missing source-bound check", "proposed_check": "Flag literal unsupported",
                "limitations": "Literal synthetic fixtures only", "rollback_reason": "Any regression",
                "benchmark": {"path": "evidence/benchmark.json", "sha256": sha(self.project / "evidence/benchmark.json")},
                "baseline": {"op": "contains_any", "terms": ["never_present"]},
                "rule": {"op": "contains_any", "terms": ["unsupported"]}}

    def authorize(self, kind, row, decision):
        self.spec["voices" if kind == "voice" else "lessons"] = [row]
        self.save()
        outputs = increments.prepare_confirmation(self.project, kind, row["id"], decision, "fixture-owner")
        for target, value in outputs:
            value.update(source_run_id="123", cloud_review_sha256="a" * 64)
            write(target, value)
        output_provenance.record_model_writes(
            self.project, [target for target, value in outputs], family="other",
            provider="deterministic-cloud-human-control", model="fixture-owner-control",
            role="human-reviewed-control", run_id="123")

    def test_argument_complete_reverse_outline_and_current_gate(self):
        self.spec["arguments"] = [self.argument()]
        self.spec["lineage"] = [self.lineage()]
        self.save()
        report = increments.refresh(self.project)
        self.assertEqual(report["status"], "mechanically_checked")
        self.assertEqual(len(report["groups"]["arguments"][0]["reverse_outline"]), 2)
        self.assertFalse(report["scientific_completion_verified"])
        self.assertEqual(increments.gate_errors(self.project, "G5", "P01"), [])

    def test_argument_missing_duplicate_changed_and_order(self):
        original = self.argument()
        for mutate in ("missing", "duplicate", "changed", "order"):
            row = copy.deepcopy(original)
            if mutate == "missing":
                row["paragraphs"].pop()
            elif mutate == "duplicate":
                row["paragraphs"][1]["units"] = row["paragraphs"][0]["units"]
            elif mutate == "changed":
                row["paragraphs"][0]["units"][0]["sha256"] = "0" * 64
            else:
                row["precedence"] = [{"before": "P2", "after": "P1"}]
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                writing.arguments(self.project, row)

    def test_manual_checkpoint_cannot_claim_prewrite(self):
        row = self.argument()
        target = self.project / increments.ROOT / "argument-plans/A1.json"
        target.unlink()
        writing.freeze_plan(self.project, row)
        with self.assertRaisesRegex(ValueError, "pre-write"):
            writing.arguments(self.project, row)

    def test_tex_traversal_repeated_include_and_cycle(self):
        self.put("papers/P01/manuscript/main.tex", "Start.\n\n\\input{body}\n\nBetween.\n\n\\input{body}\n")
        self.put("papers/P01/manuscript/body.tex", "Included paragraph.\n")
        actual = writing.inventory(self.project, "P01")["units"]
        self.assertEqual([row["text"] for row in actual], ["Start.", "Included paragraph.", "Between.", "Included paragraph."])
        self.assertEqual(len({row["unit_id"] for row in actual}), 4)
        self.put("papers/P01/manuscript/body.tex", "\\input{main}\n")
        with self.assertRaisesRegex(ValueError, "cyclic"):
            writing.inventory(self.project, "P01")

    def test_lineage_secondary_attribution_and_cycle(self):
        row = self.lineage()
        row["nodes"][0].update(kind="review_report", attribution_wording="The review reports",
                               primary_access="not_obtained")
        result = evidence.lineage(self.project, row)
        self.assertFalse(result["semantic_support_verified"])
        row["nodes"][0]["primary_access"] = "obtained"
        with self.assertRaises(ValueError):
            evidence.lineage(self.project, row)
        row["nodes"][0]["parents"] = ["N1"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            evidence.lineage(self.project, row)

    def test_lineage_rejects_false_observation_unseen_method_and_missing_fact(self):
        for change in ("observation", "full_text", "metadata", "missing_fact"):
            row = self.lineage()
            if change == "observation":
                row["nodes"][0]["kind"] = "project_observation"
                row["nodes"][0]["attempt_id"] = "invented"
            elif change == "full_text":
                row["nodes"][0]["claim_type"] = "procedure"
            elif change == "metadata":
                row["nodes"][0]["read_scope"] = "metadata"
            else:
                row["fact_links"][0]["fact_id"] = "invented"
            with self.subTest(change=change), self.assertRaises(ValueError):
                evidence.lineage(self.project, row)

    def test_anchor_exact_slice_hash_and_ambiguity(self):
        value = self.anchor()
        self.assertFalse(evidence.anchor(self.project, value)["semantic_support_verified"])
        value["start_line"] = value["end_line"] = 2
        with self.assertRaises(ValueError):
            evidence.anchor(self.project, value)
        self.put("evidence/source.md", "Source changed.\n")
        with self.assertRaises(ValueError):
            evidence.anchor(self.project, self.anchor() | {"sha256": "a" * 64})

    def test_gap_links_and_finite_scope(self):
        write(self.project / "program/hypothesis-register.json", {"hypotheses": [{"hypothesis_id": "H1"}]})
        write(self.project / "program/novelty-claim-matrix.json", {"claims": [{"claim_id": "C1", "closest_work_ids": ["W1"]}]})
        write(self.project / "program/originality-audit.json", {"closest_prior_work": [{"id": "W1"}]})
        row = {"id": "G1", "hypothesis_id": "H1", "novelty_claim_id": "C1", "closest_work_ids": ["W1"],
               "types": ["empirical", "temporal"], "status": "candidate", "scope": "supplied_materials",
               "attribution": "reader_inferred", "evidence": [self.anchor()], "counterevidence": [],
               "counter_search_ids": [], **{key: "Bounded fixture scope" for key in (
                   "question", "importance", "precise_difference", "falsification_test", "feasibility",
                   "failure_condition", "missing_evidence")}}
        self.assertFalse(evidence.gaps(self.project, row)["novelty_granted"])
        row["scope"] = "executed_queries"
        with self.assertRaises(ValueError):
            evidence.gaps(self.project, row)
        row["scope"] = "supplied_materials"
        row["closest_work_ids"] = ["W"]  # Substrings are not an identity match.
        with self.assertRaises(ValueError):
            evidence.gaps(self.project, row)

    def test_metadata_receipts_duplicate_without_claiming_fulltext(self):
        row = {"id": "I1", "work_id": "W1", "identifiers": {"doi": "10.1234/test"},
               "title": "A declared fixture", "version": "publisher-v1", "source_url": "https://example.org/paper"}
        self.spec["ingestion"] = [row, {**row, "id": "I2", "work_id": "W2",
                                      "identifiers": {"doi": "10.1234/test", "arxiv": "2601.12345"}}]
        self.save()
        results = increments.build(self.project)["groups"]["ingestion"]
        self.assertEqual(results[1]["duplicate_of"], "I1")
        self.assertEqual(results[0]["attachment_status"], "metadata_only")
        self.assertEqual(results[0]["human_full_text_read"], "not_declared")

    def test_actual_pdf_identity_parseability_and_rights(self):
        import fitz
        target = self.project / "evidence/actual.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "A declared fixture DOI 10.1234/test")
        doc.save(target)
        doc.close()
        row = {"id": "I1", "work_id": "W1", "identifiers": {"doi": "10.1234/test"},
               "title": "A declared fixture", "version": "v1", "source_url": "https://example.org/paper",
               "attachment": {"path": "evidence/actual.pdf", "sha256": sha(target)}}
        write(self.project / "data/manifests/source.json",
              {"download": {"sha256": sha(target), "expected_bytes": target.stat().st_size}})
        row["rights_manifest"] = {"path": "data/manifests/source.json",
                                  "sha256": sha(self.project / "data/manifests/source.json")}
        with self.assertRaises(ValueError):
            evidence.ingest(self.project, row)
        write(self.project / "state/data-authorizations.json",
              {"manifests": {row["rights_manifest"]["path"]: {
                  "sha256": row["rights_manifest"]["sha256"], "cloud_use_confirmed": True}}})
        result = evidence.ingest(self.project, row)
        self.assertEqual(result["identity_status"], "identity_match_candidate")
        self.assertEqual(result["attachment_status"], "parseable_text")
        row["title"] = "Wrong title"
        self.assertEqual(evidence.ingest(self.project, row)["identity_status"], "pending_identity_check")

    def test_frozen_paired_rule_adoption_and_rollback(self):
        row = self.lesson()
        with self.assertRaises(ValueError):
            rules.evaluate(self.project, row)
        rules.freeze(self.project, row)
        audit = rules.evaluate(self.project, row)
        self.assertEqual(audit["status"], "eligible_for_owner_review")
        self.assertFalse(audit["adopted"])
        self.authorize("lesson", row, "adopt_rule")
        self.assertEqual(len(rules.active_checks(self.project, increments.confirmation)), 1)
        self.authorize("lesson", row, "rollback_rule")
        self.assertEqual(rules.active_checks(self.project, increments.confirmation), [])

    def test_rule_regression_rejected_and_frozen_candidate_immutable(self):
        row = self.lesson()
        row["rule"]["terms"] = ["finding", "unsupported"]
        rules.freeze(self.project, row)
        audit = rules.evaluate(self.project, row)
        self.assertEqual(audit["status"], "rejected")
        self.assertTrue(audit["regression_case_ids"])
        with self.assertRaises(ValueError):
            self.authorize("lesson", row, "adopt_rule")
        row["rule"]["terms"] = ["unsupported"]
        with self.assertRaisesRegex(ValueError, "overwritten"):
            rules.freeze(self.project, row)

    def test_rule_split_leakage_by_content_and_group(self):
        row = self.lesson()
        path = self.project / row["benchmark"]["path"]
        value = read(path)
        value["cases"][2]["source"] = value["cases"][0]["source"]
        write(path, value)
        row["benchmark"]["sha256"] = sha(path)
        with self.assertRaisesRegex(ValueError, "share content"):
            rules.freeze(self.project, row)

    def test_rules_do_not_execute_regex_or_shell(self):
        for rule in ({"op": "shell", "terms": ["anything"]},
                     {"op": "contains_any", "terms": ["x"], "command": "echo unsafe"}):
            with self.assertRaises(ValueError):
                rules.checker(rule)

    def test_dependency_staleness_propagates_and_shared_assets_disclosed(self):
        bound = self.put("evidence/asset.txt", "Shared methodological asset")
        row = {"id": "D1", "nodes": [
            {"id": "N1", "kind": "shared_asset", "meaning": "reused asset", "paper_ids": ["P01"],
             "source": bound, "depends_on": []},
            {"id": "N2", "kind": "text", "meaning": "dependent prose", "paper_ids": ["P01"],
             "source": {"path": "papers/P01/manuscript/main.tex", "sha256": sha(self.paper / "manuscript/main.tex")},
             "depends_on": ["N1"]}]}
        self.assertEqual(increments.dependencies(self.project, row)["status"], "current")
        self.put("evidence/asset.txt", "Changed asset")
        self.assertEqual(set(increments.dependencies(self.project, row)["stale"]), {"N1", "N2"})
        row["nodes"][0]["depends_on"] = ["N2"]
        with self.assertRaisesRegex(ValueError, "cyclic"):
            increments.dependencies(self.project, row)

    def test_voice_requires_owner_scope_and_current_bytes(self):
        sample = self.put("evidence/author.txt", "A concise, grounded sentence with a concrete observation. " * 5)
        row = {"id": "V1", "sample": sample, "language": "en", "genre": "academic",
               "owner": "fixture-owner", "authorized_use": "style_reference_only"}
        with self.assertRaises(ValueError):
            writing.voice(self.project, row, increments.confirmation)
        self.authorize("voice", row, "authorize_sample")
        self.assertEqual(writing.voice(self.project, row, increments.confirmation)["use"], "style_reference_only")
        row["language"] = "zh"
        with self.assertRaises(ValueError):
            writing.voice(self.project, row, increments.confirmation)

    def test_minimal_edit_stop_does_not_skip_scientific_correction(self):
        row = {"id": "E1", "paper_id": "P01", "purpose": "clarity", "language": "en",
               "genre": "academic", "issue_ids": ["H01"], "evidence": []}
        self.spec["editing"] = [row]
        self.save()
        self.assertEqual(writing.editing(self.project, row, [])["edit_strength"], "minimal")
        increments.record_editing_attempt(self.project)
        self.assertTrue(writing.editing(self.project, row, [])["stop_repeated_editorial_rework"])
        row["purpose"] = "scientific_correction"
        with self.assertRaises(ValueError):
            writing.editing(self.project, row, [])
        row["evidence"] = [{"path": "evidence/source.md", "sha256": sha(self.project / "evidence/source.md")}]
        self.assertFalse(writing.editing(self.project, row, [])["stop_repeated_editorial_rework"])

    def test_task_context_reuse_hash_invalidation_and_counterevidence(self):
        plan = {"schema_version": "1.0", "stages": {"writing-and-review": {
            "question": "stage question", "items": [], "active_task": "results", "tasks": {
                "results": {"question": "bounded chapter question", "target": "P01/results",
                            "items": [{"path": "evidence/source.md", "stance": "contradicts", "reason": "mandatory contrary evidence"}],
                            "dependencies": [{"path": "papers/P01/manuscript/main.tex"}]}}}}}
        write(self.project / "program/context-plan.json", plan)
        first = evidence_context.refresh(self.project, "writing-and-review")
        self.assertFalse(first["reusable"])
        self.assertTrue(evidence_context.refresh(self.project, "writing-and-review")["reusable"])
        asset = self.put("evidence/unselected.txt", "Declared source outside the selected chapter slice")
        self.spec["dependencies"] = [{"id": "DEPENDENCY", "nodes": [
            {"id": "ASSET", "kind": "shared_asset", "meaning": "Declared dependency", "paper_ids": ["P01"],
             "source": asset, "depends_on": []}]}]
        self.save()
        evidence_context.refresh(self.project, "writing-and-review")
        self.assertTrue(evidence_context.refresh(self.project, "writing-and-review")["reusable"])
        self.put("evidence/unselected.txt", "Upstream source changed outside the selected chapter")
        changed = evidence_context.refresh(self.project, "writing-and-review")
        self.assertFalse(changed["reusable"])
        self.assertIn("evidence/unselected.txt", changed["dependency_changes"])
        self.put("papers/P01/manuscript/main.tex", "Changed chapter.")
        self.assertFalse(evidence_context.refresh(self.project, "writing-and-review")["reusable"])
        self.assertEqual(first["target"], "P01/results")
        write(self.project / "program/research-notebook.json", {"questions": [{"evidence": [
            {"id": "CONTRA", "stance": "contradicts", "source": {
                "path": "evidence/source.md", "sha256": sha(self.project / "evidence/source.md")}}]}]})
        plan["stages"]["writing-and-review"]["tasks"]["results"]["items"][0]["stance"] = "supports"
        write(self.project / "program/context-plan.json", plan)
        with self.assertRaisesRegex(ValueError, "counterevidence"):
            evidence_context.build(self.project, "writing-and-review")

    def test_handoff_reports_unknown_cost_and_negative_budget_without_science_claim(self):
        spend = model_spend.initial()
        spend["spent_cny"] = 12
        spend["reservations"] = {"r1": {"paper_id": "P01", "max_cost_cny": 3}}
        write(self.project / "state/model-spend-control.json", spend)
        brief = increments.handoff(self.project, increments.build(self.project))
        self.assertEqual(brief["cost"]["remaining_after_reservations"], -15)
        self.assertFalse(brief["cost"]["billing_reconciled"])
        self.assertFalse(brief["scientific_completion_verified"])
        self.assertNotIn("percent_complete", brief)
        (self.project / "state/model-spend-control.json").unlink()
        self.assertEqual(increments.handoff(self.project, {})["cost"]["status"], "authorization_state_missing")

    def test_writer_cannot_forge_increment_report_or_owner_control(self):
        from scripts import api_orchestrator
        for relative in ("reports/research-increments/audit.json",
                         "state/research-increment-confirmations/voice-V1.json"):
            bundle = {"schema_version": "1.0", "stage": "writing-and-review",
                      "artifacts": [{"path": relative, "content": "{}"}], "notes": []}
            with patch.object(api_orchestrator, "project_root", return_value=self.project):
                with self.assertRaises(ValueError):
                    api_orchestrator.apply_bundle("fixture-project", bundle, "writing-and-review")

    def test_forged_saved_report_and_missing_active_paper_are_blocked(self):
        self.spec["arguments"] = [self.argument()]
        self.spec["lineage"] = [self.lineage()]
        self.save()
        increments.refresh(self.project)
        self.assertTrue(increments.gate_errors(self.project, "G5", "P02"))
        write(self.project / increments.REPORT, {"status": "mechanically_checked"})
        self.assertIn("stale", " ".join(increments.gate_errors(self.project, "G5", "P01")))

    def test_word_inventory_covers_nonempty_table_paragraphs_without_pdf_page_claims(self):
        import zipfile
        (self.paper / "manuscript/main.tex").unlink()
        target = self.paper / "manuscript/main.docx"
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:p><w:r><w:t>Body argument.</w:t></w:r></w:p>'
               '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table argument.</w:t></w:r></w:p>'
               '</w:tc></w:tr></w:tbl></w:body></w:document>')
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("word/document.xml", xml)
        inventory = writing.inventory(self.project, "P01")
        self.assertEqual([row["text"] for row in inventory["units"]], ["Body argument.", "Table argument."])
        self.assertFalse(inventory["rendered_pagination_verified"])

    def test_paper_approval_binds_its_shared_inputs_without_invalidating_unrelated_paper(self):
        from scripts import researchctl
        self.spec["arguments"] = [self.argument()]
        self.spec["lineage"] = [self.lineage()]
        self.save()
        with patch.object(researchctl, "project_dir", return_value=self.project):
            initial = researchctl.paper_artifact_hash("fixture-project", "P01")
            self.spec["editing"] = [{"id": "OTHER", "paper_id": "P02", "purpose": "clarity",
                                     "language": "en", "genre": "academic", "issue_ids": [], "evidence": []}]
            self.save()
            self.assertEqual(researchctl.paper_artifact_hash("fixture-project", "P01"), initial)
            self.spec["lineage"][0]["nodes"][0]["boundary"] = "Changed interpretation scope"
            self.save()
            self.assertNotEqual(researchctl.paper_artifact_hash("fixture-project", "P01"), initial)
            current = researchctl.paper_artifact_hash("fixture-project", "P01")
            self.put("evidence/source.md", "Changed upstream scientific source.")
            self.assertNotEqual(researchctl.paper_artifact_hash("fixture-project", "P01"), current)

    def test_actual_cloud_owner_dossier_authorizes_voice_and_rejects_stale_review(self):
        from scripts import cloud_human_controls as controls, cloud_job, researchctl
        sample = self.put("evidence/author.txt", "A grounded sample with an explicit observation. " * 5)
        row = {"id": "V1", "sample": sample, "language": "en", "genre": "academic",
               "owner": "fixture-owner", "authorized_use": "style_reference_only"}
        self.spec["voices"] = [row]
        self.save()
        common = {"schema_version": "1.0", "project": "fixture-project", "actor": "fixture-owner", "allow_paid": False}
        selectors = {"kind": "voice", "record_id": "V1", "decision": "authorize_sample"}
        preview = {**common, **selectors, "action": "review_dossier", "operation": "confirm_research_increment"}
        cloud_job.validate_request(preview)
        with patch.object(researchctl, "project_dir", return_value=self.project), patch.object(
            researchctl, "load_state", side_effect=lambda *args: read(self.project / "state/run.json")
        ), patch.object(researchctl, "artifact_hash", return_value="a" * 64):
            reviewed = controls.execute(preview, "123")
            self.assertFalse((self.project / increments.CONFIRMATIONS).exists())
            self.assertEqual(reviewed["blockers"], [])
            decision = {**common, **selectors, "action": "confirm_research_increment",
                        "expected_sha256": reviewed["review_sha256"], "note": "Reviewed this exact scoped author sample."}
            cloud_job.validate_request(decision)
            self.put("evidence/unrelated.txt", "Changed checkpoint after review")
            with self.assertRaisesRegex(controls.HumanControlError, "changed"):
                controls.execute(decision, "124")
            decision["expected_sha256"] = controls.execute(preview, "125")["review_sha256"]
            receipt = controls.execute(decision, "126")
            self.assertEqual(receipt["paid_calls"], 0)
            self.assertTrue(increments.confirmation(self.project, "voice", "V1", row, "authorize_sample"))
            self.assertEqual(read(self.project / "state/run.json")["approved_gates"], ["G0"])

    def test_failed_observation_remains_failed_with_actual_executor_receipt(self):
        row = self.lineage()
        attempt = {"attempt_id": "ATTEMPT1", "run_id": "RUN1", "paper_id": "P01", "status": "failed",
                   "input_integrity": {"passed": False}, "outputs": [], "error": "Synthetic invalid input"}
        write(self.project / "experiments/runs/ATTEMPT1/run.json", attempt)
        self.put("experiments/registry.jsonl", json.dumps(attempt) + "\n")
        write(self.project / "experiments/plan.json", {"runs": [{"run_id": "RUN1", "paper_id": "P01"}]})
        receipt = self.project / "experiments/runs/ATTEMPT1/run.json"
        lines = receipt.read_text(encoding="utf-8").splitlines()
        line = next(i for i, value in enumerate(lines, 1) if '"error"' in value)
        row["nodes"][0].update(kind="project_observation", research_state="failed", attempt_id="ATTEMPT1",
                               evidence=[{"path": receipt.relative_to(self.project).as_posix(), "sha256": sha(receipt),
                                          "kind": "source_lines", "start_line": line, "end_line": line,
                                          "quote": "Synthetic invalid input"}])
        self.assertEqual(evidence.lineage(self.project, row)["nodes"][0]["research_state"], "failed")
        row["nodes"][0]["research_state"] = "confirmatory"
        with self.assertRaises(ValueError):
            evidence.lineage(self.project, row)


if __name__ == "__main__":
    unittest.main()
