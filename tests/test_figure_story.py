"""Cloud-run synthetic figure story checks; no scientific evidence or paid calls."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import figure_gallery as gallery, figure_story as story, output_provenance
from scripts.research_artifacts import read, sha, write
from tests.figure_lineage_fixtures import sealed_run


class FigureStoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.cloud = patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1", "GITHUB_ACTIONS": "true"})
        self.cloud.start()
        self.addCleanup(self.cloud.stop)
        self.contract = self.save("papers/P01/paper-contract.json", {"paper_id": "P01", "research_question": "How does calibration respond to drift?",
            "distinct_contribution": "A proposed drift-aware calibration mechanism", "independence": {"unique_claim_ids": ["C1"]}})
        self.claims = self.text("claims/claim-evidence.csv", "claim_id,paper_id,claim,evidence_ids,analysis_ids,support,uncertainty,status\nC1,P01,Drift-aware calibration,,,,Pending tests,draft\n")
        self.protocol = self.text("papers/P01/method.md", "Proposed drift calibration maps recorded input to calibrated output.\nThe planned configuration uses 3 repeats.\n")
        self.ir = {"schema_version": "1.0", "type": "dataflow", "title": "Proposed drift calibration", "caption": "Proposed input, calibration mechanism and output.",
                   "alt_text": "A proposed calibration process.", "claim_ids": ["C1"], "output_stem": "papers/P01/figures/main",
                   "nodes": [{"id": "input", "label": "Recorded input", "kind": "input"}, {"id": "calibration", "label": "Drift calibration", "kind": "process"}, {"id": "output", "label": "Calibrated output", "kind": "output"}],
                   "edges": [{"from": "input", "to": "calibration", "kind": "data"}, {"from": "calibration", "to": "output", "kind": "data"}]}
        self.diagram = self.save("papers/P01/figures/main.json", self.ir)
        rows = [{"id": "iclr2025-a", "title": "Time Series Calibration Architecture", "authors": ["Synthetic Author"], "venue": "iclr", "year": 2025,
                 "pattern": "architecture", "tier": "oral", "image": "images/iclr/final/a.jpg", "paper": "https://openreview.net/forum?id=synthetic-a", "pdf_source": "https://openreview.net/pdf?id=synthetic-a"},
                {"id": "icml2025-b", "title": "Time Series Architecture under Drift", "authors": ["Synthetic Author"], "venue": "icml", "year": 2025,
                 "pattern": "architecture", "tier": "spotlight", "image": "images/icml/final/b.jpg", "paper": "https://proceedings.mlr.press/v000/synthetic-b.html", "pdf_source": "https://proceedings.mlr.press/v000/synthetic-b.pdf"}]
        raw = json.dumps(rows).encode()
        lock = gallery._lock()
        lock["metadata"] = {"path": "data/figures.json", "git_blob_sha": "0"*40, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), "record_count": len(rows)}
        pinned = patch.object(gallery, "_lock", return_value=lock)
        pinned.start()
        self.addCleanup(pinned.stop)
        with patch.object(gallery, "_download", return_value=raw):
            gallery.sync(self.project)
        self.search = gallery.search(self.project, "time series architecture", top_k=2)

    def track(self, target, family="openai"):
        output_provenance.record_model_writes(self.project, [target], family=family, provider="synthetic-writer", model="fixture", role="writer", run_id="figure-story-fixture")
        return {"path": target.relative_to(self.project).as_posix(), "sha256": sha(target)}

    def text(self, relative, content):
        target = self.project/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return self.track(target)

    def save(self, relative, value):
        target = self.project/relative
        write(target, value)
        return self.track(target)

    def anchor(self, binding=None, line=1, kind="method"):
        binding = binding or self.protocol
        lines = (self.project/binding["path"]).read_text(encoding="utf-8").splitlines()
        return {**binding, "start_line": line, "end_line": line, "quote": lines[line-1], "kind": kind}

    def request(self):
        return {"schema_version": "1.0", "id": "main-brief", "paper_id": "P01", "phase": "planned",
            "paper_contract": self.contract, "claims": self.claims, "diagram": self.diagram, "sources": [self.protocol], "claim_ids": ["C1"],
            "gallery_report": self.search["report_binding"],
            "references": [{"figure_id": row["id"], "url": row["figure_url"], "metadata_sha256": row["metadata_sha256"],
                "borrow_layout": "Candidate aligned input and output lanes; inspect the source image before adoption.", "do_not_copy": "Do not copy labels, mechanisms, numbers or results."} for row in self.search["candidates"]],
            "problem": {"text": "How does calibration respond to drift?", "text_locator": self.anchor()},
            "contribution": {"text": "A proposed drift-aware calibration mechanism", "text_locator": self.anchor()},
            "flow": {"inputs": ["input"], "mechanisms": ["calibration"], "outputs": ["output"]},
            "panels": [{"id": "a", "purpose": "Explain the proposed mechanism using the actual module inventory.", "node_ids": ["input", "calibration", "output"], "claim_ids": ["C1"], "text_locator": self.anchor()}],
            "modules": [{"node_id": node["id"], "meaning": node["label"], "phase": "planned", "text_locator": self.anchor()} for node in self.ir["nodes"]],
            "connections": [{**edge, "meaning": "The declared data flow.", "phase": "planned", "text_locator": self.anchor()} for edge in self.ir["edges"]],
            "numeric_bindings": [], "result_sources": []}

    def manuscript(self, request):
        part = self.text("papers/P01/manuscript/method.tex", "Proposed drift calibration maps recorded input to calibrated output.\n")
        main = self.text("papers/P01/manuscript/main.tex", "\\documentclass{article}\n\\begin{document}\n\\input{method}\n\\end{document}\n")
        request["manuscript"] = main
        request["panels"][0]["text_locator"] = self.anchor(part, kind="manuscript")
        return part

    def observed(self):
        request = self.request()
        self.manuscript(request)
        sealed_run(self.project, output="results/metrics.csv", body="metric,value\naccuracy,0.8\n")
        result = {"path": "results/metrics.csv", "sha256": sha(self.project/"results/metrics.csv")}
        request["phase"] = "observed"
        request["claims"] = self.text("claims/claim-evidence.csv", "claim_id,paper_id,claim,evidence_ids,analysis_ids,support,uncertainty,status\nC1,P01,Drift-aware calibration,E1,r1,supported,Sampling variation,observed\n")
        request["result_sources"] = [{**result, "run_id": "r1"}]
        request["modules"][-1].update(phase="observed", text_locator=self.anchor(result, 2, "result"))
        return request, result

    def test_prepare_is_nonpaid_candidate_and_exact_replay_reuses_it(self):
        request = self.request()
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no paid calls")):
            first = story.prepare(self.project, request)
            repeated = story.prepare(self.project, request)
            validated = story.validate_saved_report(self.project, self.project/first["path"])
        self.assertTrue(repeated["reused"])
        self.assertEqual(first["sha256"], repeated["sha256"])
        self.assertEqual(validated["status"], "candidate")
        self.assertFalse(validated["limits"]["scientific_approval"])
        self.assertFalse(validated["limits"]["reference_images_inspected"])
        self.assertEqual(validated["manuscript_alignment"], "not_available")
        self.assertEqual(validated["visual_style"]["status"], "not_assessed")
        self.assertFalse((self.project/"state/run.json").exists())

    def test_saved_request_report_and_style_match_their_closed_schemas(self):
        from scripts.editable_figures import _schema
        request = self.request()
        report = story.prepare(self.project, request)["report"]
        _schema(request, "figure-story-request.schema.json")
        _schema(report, "figure-story-report.schema.json")
        _schema(story.default_style(), "figure-visual-style.schema.json")

    def test_cloud_required_and_unknown_approval_field_refused(self):
        with patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "0", "GITHUB_ACTIONS": "false"}):
            with self.assertRaisesRegex(ValueError, "cloud"):
                story.prepare(self.project, self.request())
        request = self.request()
        request["approve"] = True
        with self.assertRaises(ValueError):
            story.prepare(self.project, request)

    def test_actual_claim_module_and_arrow_inventory_cannot_drift(self):
        cases = []
        request = self.request(); request["claim_ids"] = ["C2"]; cases.append(request)
        request = self.request(); request["modules"] = request["modules"][:-1]; cases.append(request)
        request = self.request(); request["connections"][0]["kind"] = "causal"; cases.append(request)
        request = self.request(); request["panels"][0]["node_ids"] = ["input"]; cases.append(request)
        request = self.request(); request["flow"]["outputs"] = ["missing"]; cases.append(request)
        for request in cases:
            with self.subTest(request=request), self.assertRaises(ValueError):
                story.prepare(self.project, request)

    def test_source_locations_and_all_included_manuscript_files_are_bound(self):
        request = self.request()
        part = self.manuscript(request)
        report = story.prepare(self.project, request)
        self.assertEqual(report["report"]["manuscript_alignment"], "source_locations_checked")
        self.assertIn(part, report["report"]["inputs"])
        (self.project/part["path"]).write_text("Changed the underlying mechanism.\n", encoding="utf-8")
        with self.assertRaises((ValueError, output_provenance.ProvenanceError)):
            story.validate_saved_report(self.project, self.project/report["path"])
        changed = self.request()
        # Restore and bind the canonical include tree before isolating a bad
        # quotation; the earlier stale-source check must not mask this case.
        self.manuscript(changed)
        changed["panels"][0]["text_locator"]["quote"] = "This source quotation does not exist."
        with self.assertRaisesRegex(ValueError, "quote"):
            story.prepare(self.project, changed)

    def test_existing_manuscript_requires_panel_locations_inside_its_real_tree(self):
        request = self.request()
        self.manuscript(request)
        request["panels"][0]["text_locator"] = self.anchor()
        with self.assertRaisesRegex(ValueError, "manuscript"):
            story.prepare(self.project, request)

    def test_existing_manuscript_cannot_be_omitted_to_hide_alignment(self):
        request = self.request()
        self.manuscript(request)
        del request["manuscript"]
        with self.assertRaisesRegex(ValueError, "Existing canonical manuscript"):
            story.prepare(self.project, request)

    def test_manually_changed_brief_is_preserved_instead_of_overwritten(self):
        request = self.request()
        receipt = story.prepare(self.project, request)
        target = self.project/receipt["path"]
        old = target.read_text(encoding="utf-8")+"\n"
        target.write_text(old, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Preserve changed figure brief"):
            story.prepare(self.project, request)
        self.assertEqual(target.read_text(encoding="utf-8"), old)

    def test_numeric_values_need_exact_quoted_source_and_phase(self):
        ir = copy.deepcopy(self.ir); ir["nodes"][1]["label"] = "3 repeats"
        self.diagram = self.save(self.diagram["path"], ir)
        request = self.request()
        with self.assertRaisesRegex(ValueError, "numeric inventory"):
            story.prepare(self.project, request)
        request["numeric_bindings"] = [{"value": "3", "phase": "planned", "text_locator": self.anchor(line=2, kind="protocol")}]
        self.assertEqual(story.prepare(self.project, request)["report"]["phase"], "planned")
        request["numeric_bindings"][0]["phase"] = "observed"
        with self.assertRaisesRegex(ValueError, "Observed relationship"):
            story.prepare(self.project, request)
        request["numeric_bindings"][0]["phase"] = "planned"
        request["numeric_bindings"][0]["text_locator"] = self.anchor()
        with self.assertRaisesRegex(ValueError, "number"):
            story.prepare(self.project, request)

    def test_planned_drawing_cannot_present_itself_as_an_observed_result(self):
        request = self.request()
        request["modules"][-1]["phase"] = "observed"
        with self.assertRaisesRegex(ValueError, "Observed relationship"):
            story.prepare(self.project, request)
        ir = copy.deepcopy(self.ir); ir["title"] = "Drift calibration"; ir["caption"] = "Successful input and output."
        request = self.request(); request["diagram"] = self.save(self.diagram["path"], ir)
        with self.assertRaisesRegex(ValueError, "labeled"):
            story.prepare(self.project, request)

    def test_observed_figure_needs_current_executor_outputs_and_original_analysis_links(self):
        request, _ = self.observed()
        report = story.prepare(self.project, request)
        self.assertEqual(report["report"]["phase"], "observed")
        self.assertFalse(report["report"]["limits"]["scientific_approval"])
        output = self.project/"results/metrics.csv"
        output.write_text("metric,value\naccuracy,0.9\n", encoding="utf-8")
        request["result_sources"][0]["sha256"] = sha(output)
        with self.assertRaisesRegex(ValueError, "changed"):
            story.prepare(self.project, request)

    def test_observed_figure_cannot_use_an_unregistered_result_or_omit_manuscript(self):
        request, _ = self.observed()
        del request["manuscript"]
        with self.assertRaisesRegex(ValueError, "manuscript"):
            story.prepare(self.project, request)
        request, _ = self.observed()
        request["result_sources"][0]["run_id"] = "invented-run"
        with self.assertRaises(ValueError):
            story.prepare(self.project, request)

    def test_external_reference_identity_metadata_and_count_are_exact(self):
        for change in ("metadata_sha256", "url", "figure_id"):
            request = self.request(); request["references"][0][change] = "invented"
            with self.subTest(change=change), self.assertRaises(ValueError):
                story.prepare(self.project, request)
        request = self.request(); request["references"] = request["references"][:1]
        with self.assertRaisesRegex(ValueError, "two to ten"):
            story.prepare(self.project, request)
        request = self.request(); request["references"][1] = dict(request["references"][0])
        with self.assertRaisesRegex(ValueError, "unique"):
            story.prepare(self.project, request)

    def test_unknown_reference_rights_stay_unknown_and_forged_search_is_refused(self):
        request = self.request()
        report = story.prepare(self.project, request)["report"]
        self.assertFalse(report["limits"]["external_results_reusable_as_our_results"])
        self.assertFalse(self.search["candidates"][0]["license"]["reuse_authorized"])
        path = self.project/self.search["report_binding"]["path"]
        modified = read(path); modified["candidates"][0]["license"]["reuse_authorized"] = True
        write(path, modified)
        request["gallery_report"]["sha256"] = sha(path)
        with self.assertRaises(ValueError):
            story.prepare(self.project, request)

    def test_changed_or_claude_persistent_source_is_refused(self):
        target = self.project/self.diagram["path"]
        self.track(target, family="anthropic")
        with self.assertRaises(output_provenance.ProvenanceError):
            story.prepare(self.project, self.request())

    def test_common_style_is_real_bound_and_missing_style_never_claims_pass(self):
        style = story.default_style()
        binding = story.execute(self.project, "style_prepare", style)
        self.assertEqual(story.load_visual_style(self.project, {k: binding[k] for k in ("path", "sha256")}), style)
        ir = copy.deepcopy(self.ir); ir["style_ref"] = {k: binding[k] for k in ("path", "sha256")}
        self.diagram = self.save(self.diagram["path"], ir)
        report = story.prepare(self.project, self.request())
        self.assertEqual(report["report"]["visual_style"]["status"], "static_tokens_checked")
        style["font_size_pt"] = 9
        story.execute(self.project, "style_prepare", style)
        with self.assertRaisesRegex(ValueError, "Source changed"):
            story.validate_saved_report(self.project, self.project/report["path"])

    def test_style_enforces_six_papers_contrast_line_semantics_and_literal_font(self):
        cases = []
        value = story.default_style(); value["paper_ids"] = ["P01"]; cases.append(value)
        value = story.default_style(); value["node_fills"]["input"] = value["text_color"]; cases.append(value)
        value = story.default_style(); value["edge_styles"]["association"] = "solid"; cases.append(value)
        value = story.default_style(); value["font_family"] = "Arial;html=1"; cases.append(value)
        value = story.default_style(); value["font_size_pt"] = 3; cases.append(value)
        value = story.default_style(); value["legend_policy"]["non_color_encoding"] = False; cases.append(value)
        for style in cases:
            with self.subTest(style=style), self.assertRaises(ValueError):
                story.execute(self.project, "style_prepare", style)


if __name__ == "__main__":
    unittest.main()
