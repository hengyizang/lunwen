from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import automated_quality, output_provenance, research_quality
from tests import test_research_quality


class AutomatedQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = test_research_quality.ResearchQualityTests().make_project(Path(self.temp.name))
        (self.project / "state").mkdir()
        self.state = self.project / "state/run.json"
        self.state.write_text(json.dumps({"stage": "experiment-design", "gate": "G3", "status": "awaiting_work"}), encoding="utf-8")

    def test_missing_report_does_not_create_confirmation_or_preregistration(self):
        result = automated_quality.run(self.project)
        self.assertTrue(result["blockers"])
        self.assertEqual(result["created"], [])
        self.assertFalse((self.project / "data/quality/d1-confirmation.json").exists())
        self.assertFalse((self.project / "papers/P01/preregistration.json").exists())

    def test_actual_report_is_bound_and_repeated_execution_keeps_record(self):
        report = research_quality.create_data_quality_report(
            self.project, "d1", "data/raw/dataset.csv", actor="test",
            label_column="label", split_column="split", group_column="machine")
        (self.project / "data/quality/d1.json").write_text(json.dumps(report), encoding="utf-8")
        first = automated_quality.run(self.project)
        path = self.project / "data/quality/d1-confirmation.json"
        self.assertIn("data/quality/d1-confirmation.json", first["created"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["confirmation_kind"], "automated")
        self.assertEqual(payload["confirmed_by"], "deterministic_control_plane")
        self.assertEqual(output_provenance.current_origin(self.project, path)["provider"], automated_quality.PROVIDER)
        original = path.read_bytes()
        second = automated_quality.run(self.project)
        self.assertIn("data/quality/d1-confirmation.json", second["existing"])
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(second["blockers"])
        self.assertFalse((self.project / "papers/P01/preregistration.json").exists())
        path.write_text(json.dumps({**payload, "statement": "changed"}), encoding="utf-8")
        third = automated_quality.run(self.project)
        self.assertTrue(any("provenance" in issue for issue in third["blockers"]))

    def test_non_open_stage_is_rejected_without_files(self):
        self.state.write_text(json.dumps({"stage": "experiment-design", "gate": "G3", "status": "awaiting_approval"}), encoding="utf-8")
        with self.assertRaises(research_quality.ResearchQualityError):
            automated_quality.run(self.project)
        self.assertFalse((self.project / "data/quality/d1-confirmation.json").exists())

    def test_supplemental_controller_accepts_its_actual_p02_identity(self):
        (self.project/"papers/P01").rename(self.project/"papers/P02")
        self.state.write_text(json.dumps({"stage":"experiment-design","gate":"G3","status":"awaiting_work",
            "active_paper":"P02","paper_count":1,"supplemental_context":{"paper_id":"P02"}}),encoding="utf-8")
        result=automated_quality.run(self.project)
        self.assertNotIn("paper directories do not match the current project state",result["blockers"])

    def test_stale_machine_record_refreshes_before_freeze_and_preserves_history(self):
        report = research_quality.create_data_quality_report(self.project, "d1", "data/raw/dataset.csv", actor="test")
        report_path=self.project / "data/quality/d1.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        automated_quality.run(self.project)
        confirmation=self.project / "data/quality/d1-confirmation.json"
        old=confirmation.read_bytes()
        report["initiated_by"]="updated test operator"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        result=automated_quality.run(self.project)
        self.assertIn("data/quality/d1-confirmation.json", result["refreshed"])
        self.assertNotEqual(old,confirmation.read_bytes())
        self.assertEqual(len(list((self.project/"state/automated-quality-history").glob("*.json"))),1)
        report["initiated_by"]="changed after freeze"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        state=json.loads(self.state.read_text(encoding="utf-8"));state["approved_gates"]=["G3"]
        self.state.write_text(json.dumps(state), encoding="utf-8")
        self.assertTrue(any("frozen" in item for item in automated_quality.run(self.project)["blockers"]))

    def test_g4_missing_runs_and_reports_cannot_create_reproduction_confirmation(self):
        self.state.write_text(json.dumps({"stage": "experiment-execution", "gate": "G4", "status": "awaiting_work"}), encoding="utf-8")
        result = automated_quality.run(self.project)
        self.assertTrue(result["blockers"])
        self.assertFalse((self.project / "papers/P01/reproduction-confirmation.json").exists())

    def test_nonempirical_automatic_confirmation_is_bound_and_does_not_invent_human_review(self):
        from scripts import study_routes
        self.state.write_text(json.dumps({"stage": "experiment-execution", "gate": "G4", "status": "awaiting_work"}), encoding="utf-8")
        report = {"status": "complete", "errors": [], "synthetic_fixture_only": True}
        with patch.object(research_quality, "validate_g4_quality", return_value=[]), \
                patch.object(study_routes, "route", return_value="theory"), \
                patch.object(study_routes, "build_report", return_value=report):
            result = automated_quality.run(self.project)
            relative = "papers/P01/study-validation-confirmation.json"
            self.assertIn(relative, result["created"])
            value = json.loads((self.project / relative).read_text(encoding="utf-8"))
            self.assertFalse(value["human_confirmation"])
            self.assertEqual(value["confirmation_kind"], "automated")
            self.assertIn(relative, automated_quality.run(self.project)["existing"])
