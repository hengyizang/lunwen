"""Source-bound synthetic Mermaid exports; no scientific figure approval."""
import copy
import unittest
from unittest.mock import patch

from scripts import diagram_mermaid, figure_story
from scripts.research_artifacts import read, sha, write
import tests.test_figure_story as fixtures


class DiagramMermaidTests(unittest.TestCase):
    track = fixtures.FigureStoryTests.track
    text = fixtures.FigureStoryTests.text
    save = fixtures.FigureStoryTests.save
    anchor = fixtures.FigureStoryTests.anchor
    request = fixtures.FigureStoryTests.request

    def setUp(self):
        fixtures.FigureStoryTests.setUp(self)

    def export_request(self):
        brief = figure_story.prepare(self.project, self.request())
        return {"schema_version": "1.0", "id": "main", "source": self.diagram,
            "story_ref": {"path": brief["path"], "sha256": brief["sha256"]}}

    def test_exports_only_actual_typed_nodes_and_arrows(self):
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid call")):
            report = diagram_mermaid.build(self.project, self.export_request())
        self.assertEqual(len(report["nodes"]), 3)
        self.assertEqual(len(report["edges"]), 2)
        self.assertIn('n0 -->|"planned: data"| n1', report["mermaid"])
        self.assertFalse(report["scientific_approval"])
        self.assertEqual(len(report["confirmation_required"]), 2)

    def test_source_brief_mapping_does_not_depend_on_connection_order(self):
        request = self.request()
        request["connections"].reverse()
        brief = figure_story.prepare(self.project, request)
        value = {"schema_version": "1.0", "id": "main", "source": self.diagram,
                 "story_ref": {"path": brief["path"], "sha256": brief["sha256"]}}
        report = diagram_mermaid.build(self.project, value)
        self.assertEqual(report["edges"][0]["source_mapping"]["from"], "input")

    def test_relationship_kinds_are_visible_and_reserved_input_ids_are_mapped(self):
        ir = copy.deepcopy(self.ir)
        ir["nodes"][0]["id"] = "end"
        ir["edges"][0]["from"] = "end"
        ir["edges"][0]["kind"] = "causal"
        ir["edges"][1]["kind"] = "association"
        value = diagram_mermaid.text(ir)
        self.assertIn('n0 ==>|"unreviewed: causal"| n1', value)
        self.assertIn('n1 -.-|"unreviewed: association"| n2', value)
        self.assertNotIn("  end[", value)

    def test_source_labels_cannot_inject_new_mermaid_statements(self):
        ir = copy.deepcopy(self.ir)
        ir["nodes"][0]["label"] = 'Input "] --> injected["extra'
        value = diagram_mermaid.text(ir)
        self.assertIn("&quot;", value)
        self.assertEqual(sum(line.startswith("  n") for line in value.splitlines()), 5)

    def test_export_requires_current_non_claude_ir_and_real_brief(self):
        request = self.export_request()
        self.track(self.project / self.diagram["path"], family="anthropic")
        with self.assertRaisesRegex(ValueError, "non-Claude"):
            diagram_mermaid.build(self.project, request)

    def test_changed_original_method_invalidates_attached_arrow_evidence(self):
        request = self.export_request()
        (self.project / self.protocol["path"]).write_text("Changed method", encoding="utf-8")
        with self.assertRaises(ValueError):
            diagram_mermaid.build(self.project, request)

    def test_missing_story_is_not_a_scientifically_bound_export(self):
        request = self.export_request()
        request["story_ref"] = None
        with self.assertRaisesRegex(ValueError, "figure brief"):
            diagram_mermaid.build(self.project, request)

    def test_planned_phase_remains_visible_when_only_original_caption_marks_it(self):
        self.ir["title"] = "Drift calibration framework"
        self.diagram = self.save(self.diagram["path"], self.ir)
        report = diagram_mermaid.build(self.project, self.export_request())
        self.assertIn('planned: process: Drift calibration', report["mermaid"])
        self.assertIn('planned: data', report["mermaid"])
        self.assertEqual(report["caption"], self.ir["caption"])

    def test_refresh_and_revalidate_detect_altered_code_and_manifest(self):
        write(self.project / "program/diagram-mermaid.json", self.export_request())
        result = diagram_mermaid.refresh(self.project)
        self.assertTrue(diagram_mermaid.validate_saved_report(self.project)["valid"])
        (self.project / result["mermaid"]).write_text("flowchart LR\n n0 --> fabricated\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "topology|output"):
            diagram_mermaid.validate_saved_report(self.project)
        with self.assertRaisesRegex(ValueError, "altered"):
            diagram_mermaid.refresh(self.project)
