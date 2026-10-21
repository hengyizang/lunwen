"""Cloud-only synthetic checks for evidence reasoning, not scientific validity."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import literature_reasoning as reasoning, literature_workbench as workbench
from scripts.research_artifacts import read, sha, write


class LiteratureReasoningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.config = {"schema_version": "1.0", "doctoral_question": "When does calibration transfer across devices?", "papers": []}

    def add(self, identifier="a", *, text=None, fields=None, targets=None):
        text = text or "# Methods\nCalibration uses a held-out device.\n# Limitations\nTransfer fails under sensor drift.\n"
        path = self.project / f"evidence/sources/{identifier}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paper = {"id": identifier, "title": identifier, "source": {"path": path.relative_to(self.project).as_posix(), "sha256": sha(path)},
                 "topic_id": "calibration", "paper_ids": ["P01"] if targets is None else targets}
        self.config["papers"].append(paper)
        if fields:
            card = {"schema_version": "1.0", "paper_id": identifier, "fields": {}}
            for field, line in fields.items():
                quote = text.splitlines()[line - 1]
                card["fields"][field] = [{"text": quote, "kind": "author_claim", "evidence": [self.anchor(paper, line)]}]
            target = self.project / f"literature/cards/{identifier}.json"
            write(target, card)
            paper["card"] = {"path": target.relative_to(self.project).as_posix(), "sha256": sha(target)}
        return paper

    def anchor(self, paper, line=2):
        text = (self.project / paper["source"]["path"]).read_text(encoding="utf-8").splitlines()
        return {**paper["source"], "start_line": line, "end_line": line, "quote": text[line - 1]}

    def cite(self, paper, line=2):
        return {"paper_id": paper["id"], **self.anchor(paper, line)}

    def statement(self, paper, text, line=2):
        return {"text": text, "kind": "model_inference", "inference_boundary": "A proposed test, not a verified source conclusion.",
                "evidence": [self.cite(paper, line)]}

    def build(self):
        write(self.project / workbench.CONFIG, self.config)
        return workbench.build(self.project)

    def semantic_config(self, paper, *, candidates=None):
        value = {"schema_version": "1.0", "doctoral_question": self.config["doctoral_question"],
            "reading_objectives": [{"id": "identify-unit", "paper_id": paper["id"], "field": "splits",
                "question": "Is the held-out unit a whole device, rather than a row from the same device?",
                "purpose": "Distinguish device-level transfer from sample-level interpolation.", "evidence": [self.cite(paper)]}],
            "experiment_candidates": candidates or []}
        write(self.project / reasoning.CONFIG, value)
        return value

    def request(self, paper, plan, *, outcome="insufficient"):
        step = plan["steps"][0]
        return {"step_id": step["id"], "expected_step_sha256": step["step_sha256"],
            "answer": "Device identity is held out, but its tuning protocol needs the supplement.", "outcome": outcome,
            "evidence": [self.cite(paper)], "kind": "human_interpretation", "recorded_by": "fixture reviewer",
            "recorded_at": "2026-10-21T12:00:00+00:00", "inference_boundary": "Located text alone does not settle leakage."}

    def test_semantic_objective_survives_no_keyword_match_and_locates_sections(self):
        a = self.add(fields={"methods": 2, "limitations": 4})
        self.build()
        self.semantic_config(a)
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid call allowed")):
            plan = reasoning.itinerary(self.project, "Unrelated vocabulary used by an explicit reading objective")
        self.assertEqual(plan["selected_paper_ids"], ["a"])
        self.assertEqual(len(plan["steps"]), 6)
        step = next(s for s in plan["steps"] if s["phase"] == "semantic_objective")
        self.assertIn("whole device", step["question"])
        self.assertEqual(step["start_here"][0]["section"]["title"], "Methods")
        self.assertEqual(step["start_here"][0]["start_line"], 2)
        self.assertFalse(plan["semantic_verification"])

    def test_plan_contains_mechanism_protocol_challenge_and_falsification_dependencies(self):
        a = self.add(fields={"methods": 2, "counterevidence": 4})
        self.build()
        plan = reasoning.itinerary(self.project, "calibration transfer")
        self.assertEqual(plan["steps"][0]["phase"], "challenge")
        self.assertEqual({s["phase"] for s in plan["steps"]}, {p[0] for p in reasoning.PHASES})
        for previous, step in zip(plan["steps"], plan["steps"][1:]):
            self.assertEqual(step["dependencies"], [previous["id"]])
        self.assertIn("splits", plan["steps"][0]["unknown_fields"])
        test = next(s for s in plan["steps"] if s["phase"] == "test")
        self.assertEqual(test["status"], "needs_source_reading")
        self.assertIn("refute", test["question"])

    def test_scoped_plan_preserves_six_paper_mapping(self):
        self.add("a", targets=["P01"])
        self.add("b", targets=["P02"])
        self.build()
        plan = reasoning.itinerary(self.project, "calibration", topic_id="calibration", paper_id="P02")
        self.assertEqual(plan["selected_paper_ids"], ["b"])
        with self.assertRaisesRegex(ValueError, "requires its topic scope"):
            reasoning.itinerary(self.project, "calibration", paper_id="P02")

    def test_progress_append_adaptation_repeat_and_no_approval(self):
        a = self.add(fields={"methods": 2})
        self.build()
        plan = reasoning.itinerary(self.project, "calibration transfer")
        request = self.request(a, plan)
        result = reasoning.record_progress(self.project, request)
        self.assertEqual(result["itinerary"]["progress"]["answered_steps"], 1)
        answered = result["itinerary"]["steps"][0]
        self.assertIn("supplement", answered["recorded_answer"]["answer"])
        self.assertIn("full-text", answered["next_missing_evidence"])
        self.assertFalse(result["gate_approved"])
        repeated = reasoning.record_progress(self.project, request)
        self.assertEqual(repeated["status"], "already_recorded")
        self.assertEqual(len(read(self.project / reasoning.PROGRESS)["events"]), 1)
        revised = {**request, "outcome": "contradicts", "recorded_at": "2026-10-21T12:01:00+00:00"}
        result = reasoning.record_progress(self.project, revised)
        self.assertIn("independent contrary source", result["itinerary"]["steps"][0]["next_missing_evidence"])
        self.assertEqual(len(read(self.project / reasoning.PROGRESS)["events"]), 2)

    def test_progress_refuses_fabricated_quotes_wrong_hash_and_unattributed_answers(self):
        a = self.add(fields={"methods": 2})
        self.build()
        plan = reasoning.itinerary(self.project, "calibration")
        request = self.request(a, plan)
        bad = {**request, "expected_step_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "current step hash"):
            reasoning.record_progress(self.project, bad)
        bad = copy.deepcopy(request)
        bad["evidence"][0]["quote"] = "Invented useful evidence."
        with self.assertRaisesRegex(ValueError, "absent"):
            reasoning.record_progress(self.project, bad)
        with self.assertRaisesRegex(ValueError, "recorder"):
            reasoning.record_progress(self.project, {**request, "recorded_by": ""})
        with self.assertRaisesRegex(ValueError, "timezone"):
            reasoning.record_progress(self.project, {**request, "recorded_at": "2026-10-21T12:01:00"})
        self.assertFalse((self.project / reasoning.PROGRESS).exists())

    def test_mutated_progress_cannot_rewrite_an_attributed_reading_history(self):
        a = self.add(fields={"methods": 2})
        self.build()
        plan = reasoning.itinerary(self.project, "calibration")
        reasoning.record_progress(self.project, self.request(a, plan))
        value = read(self.project / reasoning.PROGRESS)
        value["events"][0]["answer"] = "A silently substituted interpretation."
        write(self.project / reasoning.PROGRESS, value)
        with self.assertRaisesRegex(ValueError, "append-only provenance"):
            reasoning.itinerary(self.project, "calibration")

    def test_native_reader_sections_exclude_translation_and_generated_headings(self):
        paper = self.add(text="## PDF page 1\nCalibration uses a held-out device.\n### English translation\n# Invented explanatory chapter\n")
        paper["reader"] = {**paper["source"], "page_ranges": {"1": [2, 2]}}
        sections = reasoning._section_rows(self.project, paper)
        self.assertEqual(len(sections), 1)
        self.assertEqual((sections[0]["start_line"], sections[0]["end_line"], sections[0]["pdf_page"]), (2, 2, 1))
        self.assertNotIn("Invented", sections[0]["title"])

    def test_changed_objectives_block_old_answer_and_changed_source_blocks_reading(self):
        a = self.add(fields={"methods": 2})
        self.build()
        value = self.semantic_config(a)
        plan = reasoning.itinerary(self.project, "calibration")
        request = self.request(a, plan)
        value["reading_objectives"][0]["purpose"] = "A changed objective needs renewed reading."
        write(self.project / reasoning.CONFIG, value)
        with self.assertRaisesRegex(ValueError, "objectives changed"):
            reasoning.record_progress(self.project, request)
        path = self.project / a["source"]["path"]
        path.write_text("Changed source.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            reasoning.itinerary(self.project, "calibration")

    def test_reasoning_rejects_fabricated_semantics_scope_changes_and_unsupported_keys(self):
        a = self.add(fields={"methods": 2})
        self.build()
        value = self.semantic_config(a)
        value["reading_objectives"][0]["evidence"][0]["quote"] = "No such passage."
        write(self.project / reasoning.CONFIG, value)
        with self.assertRaisesRegex(ValueError, "absent"):
            reasoning.itinerary(self.project, "calibration")
        value = self.semantic_config(a)
        value["doctoral_question"] = "A different unrelated thesis."
        write(self.project / reasoning.CONFIG, value)
        with self.assertRaisesRegex(ValueError, "doctoral question"):
            reasoning.itinerary(self.project, "calibration")
        value = self.semantic_config(a)
        value["approve_G1"] = True
        write(self.project / reasoning.CONFIG, value)
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            reasoning.itinerary(self.project, "calibration")

    def test_experiment_packet_recovers_all_axes_and_pairwise_unknowns(self):
        self.add("a", fields={"methods": 2, "limitations": 4, "baseline": 2, "metrics": 2})
        self.add("b", fields={"methods": 2, "counterevidence": 4, "metrics": 2})
        self.build()
        packet = reasoning.comparison_packet(self.project, ["a", "b"], question="Does calibration transfer?")
        self.assertEqual({a["field"] for a in packet["experiment_design_axes"]}, set(reasoning.EXPERIMENT_AXES))
        self.assertEqual(len(packet["pairwise_comparability"]), 1)
        conditions = packet["pairwise_comparability"][0]["conditions"]
        self.assertEqual(next(c for c in conditions if c["axis"] == "metrics")["status"], "needs_semantic_comparability_audit")
        self.assertEqual(next(c for c in conditions if c["axis"] == "datasets")["status"], "missing_evidence")
        self.assertEqual(len(packet["gap_hypotheses"]), 2)
        self.assertIn("not_established_research_gap", packet["gap_hypotheses"][0]["status"])
        self.assertFalse(packet["novelty_verified"])
        self.assertFalse(packet["experiment_executed"])

    def test_full_source_bound_candidate_and_nearest_work_matrix(self):
        a = self.add("a", fields={"methods": 2, "limitations": 4})
        b = self.add("b", fields={"methods": 2})
        self.build()
        candidate = {"id": "device-transfer", "question": "Does device-held-out tuning separate drift from calibration?",
            "source_paper_ids": ["a", "b"], "nearest_work_ids": ["a", "b"], "paper_ids": ["P01", "P02"],
            "fields": {axis: [self.statement(a, "Proposed " + axis)] for axis in reasoning.EXPERIMENT_AXES}}
        self.semantic_config(a, candidates=[candidate])
        packet = reasoning.comparison_packet(self.project, ["a", "b"])
        self.assertEqual(packet["reasoning_path"], reasoning.CONFIG)
        entry = packet["experiment_candidates"][0]
        self.assertEqual(entry["missing_design_fields"], [])
        self.assertEqual(len(entry["nearest_work_matrix"]), 2)
        self.assertEqual(entry["doctoral_question"], self.config["doctoral_question"])
        self.assertFalse(entry["needs_target_paper_mapping"])
        self.assertFalse(entry["novelty_verified"])
        self.assertFalse(packet["gate_approved"])

    def test_candidate_refuses_unrelated_source_and_invalid_target_mapping(self):
        a = self.add("a", fields={"methods": 2})
        b = self.add("b", fields={"methods": 2})
        self.build()
        candidate = {"id": "candidate", "question": "Can calibration transfer?", "source_paper_ids": ["a"],
            "nearest_work_ids": ["a"], "paper_ids": ["P01"],
            "fields": {"hypotheses": [self.statement(b, "A proposed mechanism.")]}}
        self.semantic_config(a, candidates=[candidate])
        with self.assertRaisesRegex(ValueError, "out-of-scope"):
            reasoning.comparison_packet(self.project, ["a", "b"])
        candidate["fields"] = {}
        candidate["paper_ids"] = ["P07"]
        self.semantic_config(a, candidates=[candidate])
        with self.assertRaisesRegex(ValueError, "P01-P06"):
            reasoning.comparison_packet(self.project, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
