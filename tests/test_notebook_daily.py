import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts import research_notebook
from scripts.research_artifacts import sha, write


class DailyNotebookTests(unittest.TestCase):
    def fixture(self, project):
        source = project / "evidence/source.txt"
        source.parent.mkdir()
        source.write_text("A negative result.", encoding="utf-8")
        question = {"id": "Q1", "question": "When does the effect fail?", "evidence": [
            {"id": "E1", "stance": "contradicts", "read_scope": "abstract", "observation": "A negative result",
             "source": {"path": "evidence/source.txt", "sha256": sha(source), "locator": "abstract"}}],
            "missing_evidence": ["Independent replication"]}
        write(project / "program/research-notebook.json", {"questions": [question]})
        return question, source

    def test_same_day_changes_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            question, _ = self.fixture(project)
            first_time = datetime(2026, 10, 9, 1, tzinfo=timezone.utc)
            first = research_notebook.refresh(project, at=first_time)
            repeat = research_notebook.refresh(project, at=first_time)
            self.assertFalse(repeat["changed"])
            self.assertFalse(repeat["daily_brief"]["changed"])
            question["question"] = "How sensitive is the effect?"
            question["missing_evidence"] = []
            write(project / "program/research-notebook.json", {"questions": [question]})
            second = research_notebook.refresh(project, at=datetime(2026, 10, 9, 2, tzinfo=timezone.utc))
            brief = second["daily_brief"]
            self.assertEqual(brief["event_count"], 2)
            self.assertEqual(brief["changes"]["questions_changed"], ["Q1"])
            self.assertEqual(brief["changes"]["missing_removed"][0]["status"], "resolution_requires_review")
            self.assertFalse(brief["resolution_verified"])
            self.assertEqual(first["daily_brief"]["changes"]["conflicts_new"], ["Q1"])

    def test_timezone_boundary_and_legacy_history(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            self.fixture(project)
            history = project / "reports/research-notebook-history.jsonl"
            history.parent.mkdir()
            history.write_text(json.dumps({"schema_version": "1.0", "questions": []}) + "\n")
            research_notebook.refresh(project, at=datetime(2026, 10, 9, 15, 59, tzinfo=timezone.utc))
            following = research_notebook.refresh(project, at=datetime(2026, 10, 9, 16, 1, tzinfo=timezone.utc))
            self.assertEqual(following["daily_brief"]["day"], "2026-10-10")
            self.assertEqual(following["daily_brief"]["event_count"], 0)
            self.assertEqual(following["daily_brief"]["undated_legacy_snapshots"], 1)

    def test_blocked_source_change_is_not_silently_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            _, source = self.fixture(project)
            at = datetime(2026, 10, 9, 3, tzinfo=timezone.utc)
            research_notebook.refresh(project, at=at)
            source.write_text("Changed source", encoding="utf-8")
            result = research_notebook.refresh(project, at=at)
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(result["daily_brief"]["failed_refreshes"])
            self.assertFalse(result["daily_brief"]["resolution_verified"])

    def test_malformed_history_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            history = project / "reports/research-notebook-history.jsonl"
            history.parent.mkdir()
            history.write_text('{"recorded_at": "2026-10-09T12:00:00"}\n')
            with self.assertRaises(ValueError):
                research_notebook.daily_brief(project)
