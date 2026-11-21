"""Regression tests for the opt-in real-work-first profile.

The full protocol remains the default. These tests pin down that the minimal
profile (a) is off unless explicitly enabled, (b) blocks only the checks that
prevent a fabricated doctoral topic decision, (c) never fabricates scientific
content, and (d) never records a gate decision without a named human actor.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import real_work, researchctl


class RealWorkProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        project = self.root / "projects" / "p"
        (project / "state").mkdir(parents=True)
        (self.root / "config").mkdir()
        state = {
            "schema_version": "2.0", "project": "p", "stage_index": 1,
            "stage": "topic-intelligence", "gate": "G1", "status": "awaiting_work",
            "active_paper": "P01", "paper_count": 6,
            "approved_gates": ["G0"], "approvals": [], "history": [],
        }
        (project / "state" / "run.json").write_text(json.dumps(state), encoding="utf-8")
        self._patches = [
            patch.object(real_work, "ROOT", self.root),
            patch.object(real_work, "CONFIG_PATH", self.root / "config" / "real-work.json"),
            patch.object(real_work, "LOCAL_MODELS", self.root / "config" / "model-routing.local.json"),
            patch.object(researchctl, "ROOT", self.root),
        ]
        for item in self._patches:
            item.start()
            self.addCleanup(item.stop)
        (self.root / "config" / "real-work.json").write_text(
            json.dumps({"schema_version": "1.0", "enabled_gates": ["G1"]}), encoding="utf-8")

    def _write_full_g1_material(self) -> None:
        program = self.root / "projects" / "p" / "program"
        program.mkdir(parents=True, exist_ok=True)
        (program / "topic-shortlist.json").write_text(json.dumps({
            "candidates": [{"candidate_id": f"C{i}"} for i in range(1, 4)],
        }), encoding="utf-8")
        (program / "core-thesis.json").write_text(json.dumps({
            "doctoral_question": "Owner-written overarching doctoral question?",
        }), encoding="utf-8")
        (program / "topic-decision.md").write_text(
            "# Decision\n\nOwner chose C1 after reviewing all three candidates.\n", encoding="utf-8")

    def test_research_first_is_the_single_default_without_an_optin(self):
        with patch.dict(os.environ,{"DR_OS_WORK_PROFILE":""}):
            self.assertTrue(real_work.profile_enabled("G1"))
            self.assertTrue(real_work.profile_enabled("G5"))

    def test_legacy_diagnostics_cannot_be_bypassed_by_three_empty_candidates(self):
        self._write_full_g1_material()
        with patch.dict(os.environ,{"DR_OS_WORK_PROFILE":"minimal"}),patch.object(researchctl,"_full_gate_errors",return_value=["actual source issue"]) as check:
            self.assertEqual(researchctl.gate_errors("p","G1"),["actual source issue"])
        check.assert_called_once()

    def test_missing_topic_templates_do_not_create_a_minimal_gate(self):
        with patch.dict(os.environ,{"DR_OS_WORK_PROFILE":"minimal"}),patch.object(researchctl,"_full_gate_errors",return_value=["legacy diagnostic"]):
            self.assertEqual(researchctl.gate_errors("p","G1"),["legacy diagnostic"])

    def test_prepare_decision_does_not_reintroduce_fixed_human_forms(self):
        self._write_full_g1_material()
        real_work.cmd_prepare_decision(argparse.Namespace(project="p"))
        text=(self.root/"projects/p/reports/G1-DECISION-SHEET.md").read_text()
        self.assertNotIn("three fields only you",text)
        self.assertNotIn("quality-G1.json",text)
        self.assertIn("autopilot resume",text)

    def test_bootstrap_writes_no_candidate_quota_or_scientific_content(self):
        self.assertEqual(real_work.cmd_bootstrap_g1(argparse.Namespace(project="p",force=False)),0)
        program=self.root/"projects/p/program"
        self.assertEqual(json.loads((program/"topic-shortlist.json").read_text())["candidates"],[])
        self.assertEqual(json.loads((program/"core-thesis.json").read_text())["doctoral_question"],"")
        self.assertIn(real_work.PLACEHOLDER,(program/"topic-decision.md").read_text())

    def test_bootstrap_does_not_overwrite_existing_material(self) -> None:
        self._write_full_g1_material()
        before = (self.root / "projects" / "p" / "program" / "topic-decision.md").read_text(encoding="utf-8")
        real_work.cmd_bootstrap_g1(argparse.Namespace(project="p", force=False))
        self.assertEqual(
            (self.root / "projects" / "p" / "program" / "topic-decision.md").read_text(encoding="utf-8"), before)

    def test_decide_requires_named_human(self) -> None:
        for actor in ("", "   ", "deterministic-control-plane"):
            with self.subTest(actor=actor), self.assertRaises(SystemExit):
                real_work.cmd_decide(argparse.Namespace(project="p", actor=actor, note="x"))

    def test_split_screening_never_fills_owner_decisions(self) -> None:
        import csv
        reports = self.root / "projects" / "p" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        fields = ["key", "title", "human_decision", "human_reason", "screened_by", "screened_at"]
        with (reports / "sheet.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index in range(7):
                writer.writerow({"key": f"k{index}", "title": f"t{index}",
                                 "human_decision": "", "human_reason": "",
                                 "screened_by": "", "screened_at": ""})
        args = argparse.Namespace(project="p", sheet="sheet.csv", size=3)
        self.assertEqual(real_work.cmd_split_screening(args), 0)
        outdir = reports / "g1-screening-batches"
        batches = sorted(outdir.glob("batch-*.csv"))
        self.assertEqual(len(batches), 3)
        total = 0
        for path in batches:
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            total += len(rows)
            for row in rows:
                for column in ("human_decision", "human_reason", "screened_by", "screened_at"):
                    self.assertEqual(row[column], "")
        self.assertEqual(total, 7)
        self.assertIn("No row was included", (outdir / "INDEX.md").read_text(encoding="utf-8"))

    def test_configure_models_writes_only_owner_supplied_ids(self) -> None:
        names = ("sol", "astra", "luna", "sonnet", "opus", "deepseek", "argon")
        args = argparse.Namespace(**{name: None for name in names})
        args.sol = "my-real-gpt"
        args.opus = "my-real-claude"
        self.assertEqual(real_work.cmd_configure_models(args), 0)
        data = json.loads(real_work.LOCAL_MODELS.read_text(encoding="utf-8"))
        self.assertEqual(set(data["models"]), {"sol", "opus"})
        self.assertEqual(data["models"]["sol"]["model"], "my-real-gpt")
        self.assertEqual(data["models"]["opus"]["model"], "my-real-claude")


if __name__ == "__main__":
    unittest.main()
