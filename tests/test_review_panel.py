"""Actual controller paths with mocked transports; no scientific acceptance or spend."""
from contextlib import ExitStack
from functools import lru_cache
import csv
import io
import json
import os
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ai_providers, review_panel, model_runtime, research_cycle
from scripts.research_artifacts import read, write, sha, record


@lru_cache(maxsize=1)
def panel_protocol_fixture():
    from scripts.experiment_evidence_acceptance import fixture
    with tempfile.TemporaryDirectory() as directory:
        return fixture(Path(directory) / "synthetic-protocol")


def panel_inputs(project):
    manuscript = project / "papers/P01/manuscript"
    manuscript.mkdir(parents=True, exist_ok=True)
    main = manuscript / "main.tex"
    title = "\\usepackage{graphicx,pgfplotstable}\n\\title{SYNTHETIC title source, no actual experiment.}\n"
    abstract = ("\\maketitle\n\\begin{abstract}\nSYNTHETIC abstract source, no actual experiment.\n"
        "\\detokenize{SYNTHETIC headline_claim source, no actual experiment.}\n\\end{abstract}\n")
    sections = ("\\section{Methods}\nSYNTHETIC methods source, no actual experiment.\n"
        "\\section{Results}\nSYNTHETIC results source, no actual experiment.\n"
        "\\begin{table}\n\\begin{tabular}{lr}\n\\detokenize{SYNTHETIC numeric_table source, no actual experiment.} & 0 \\\\\n"
        "\\end{tabular}\n\\end{table}\n\\begin{figure}\n"
        "\\pgfplotstabletypeset[col sep=comma,string type]{../tables/figure-values.csv}\n"
        "\\caption{\\detokenize{SYNTHETIC figure_one source, no actual experiment.}}\n\\end{figure}\n"
        "\\section{Discussion}\nNo scientific inference can be made from this software fixture.\n"
        "\\section{Conclusion}\nNo research has been performed.\n")
    if main.exists():
        main.write_text(main.read_text().replace(r"\begin{document}", title + "\\begin{document}\n" + abstract, 1)
                        .replace(r"\end{document}", sections + r"\end{document}"), encoding="utf-8")
    else:
        main.write_text("\\documentclass{article}\n" + title + "\\begin{document}\n" + abstract + "\\section{Introduction}\n"
                        "A synthetic source-isolation software test.\n" + sections + "\\end{document}\n", encoding="utf-8")
    values = project / "papers/P01/tables/figure-values.csv"
    values.parent.mkdir(parents=True, exist_ok=True)
    values.write_text("label,value\nSYNTHETIC figure-values source no actual experiment,0\n", encoding="utf-8")
    plan = project / "papers/P01/experiment-evidence-plan.json"
    write(plan, panel_protocol_fixture())
    protocol = project / "papers/P01/preregistration.json"
    write(protocol, {"schema_version":"1.0", "paper_id":"P01", "status":"frozen", "frozen_at":"2026-01-01T00:00:00Z",
        "frozen_by":"Synthetic fixture", "generated_by":"deterministic_local_control_plane", "confirmatory_lock":True,
        "files":[{"path":plan.relative_to(project).as_posix(), "sha256":sha(plan)}],
        "deviation_policy":"Synthetic protocol fixture only; no actual experiment.", "human_confirmation":True})
    rows = {}
    for seat, kinds in review_panel.VIEWS.items():
        rows[seat] = []
        for kind in sorted(kinds):
            target = project / f"papers/P01/manuscript/{kind}.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"SYNTHETIC {kind} source, no actual experiment.\n", encoding="utf-8")
            if kind == "numeric_table":
                target.write_text("\\detokenize{SYNTHETIC numeric_table source, no actual experiment.} & 0 \\\\\n", encoding="utf-8")
            elif kind == "protocol": target = protocol
            elif kind == "figure_values": target = values
            rows[seat].append({"kind": kind, "path": target.relative_to(project).as_posix(),
                "sha256": sha(target), "start_line": 1, "end_line": len(target.read_text().splitlines())})
    rows["statistics"].append({"kind":"protocol", "path":plan.relative_to(project).as_posix(), "sha256":sha(plan),
                                "start_line":1,"end_line":len(plan.read_text().splitlines())})
    write(project / review_panel.request_path("P01"), {"paper_id": "P01", "views": rows})


class ReviewPanelTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.project = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        write(self.project / "state/run.json", {"stage":"writing-and-review", "gate":"G5", "active_paper":"P01",
            "writing_phases":{"P01":"submission"}})
        panel_inputs(self.project)
        self.stack.enter_context(patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR":"1"}))
        self.stack.enter_context(patch.object(model_runtime, "preflight_route", return_value={}))

    def response(self, project, **kwargs):
        seat = kwargs["role"].removeprefix("independent-critic-panel-")
        body = {"view": seat, "findings": [], "uncertainty": ["Synthetic software fixture; no scientific conclusion."]}
        if seat == "domain":
            path = f"papers/P01/manuscript/methods.txt:L1-L1"
            body["findings"] = [{"id":"rival-1", "claim_pointer":path, "evidence_pointer":path,
                "gap":"Rival explanation remains", "minimum_test":"Compare an independent outcome",
                "severity":"major", "rationale":"Supplied fixture contains no experiment."}]
        return ai_providers.ModelResult(kwargs["provider"], kwargs["model"], json.dumps(body), {"input_tokens":2},
            request_id="synthetic-" + seat, reported_model=kwargs["model"], completion_status="completed", cache_hit=False)

    def run_panel(self, run="first"):
        with patch.object(model_runtime, "call", side_effect=self.response) as calls:
            result = review_panel.run(self.project, "P01", run)
        return result, calls

    def study_inputs(self, kind, *, figure=False):
        """Native study validation/freeze, without claiming a real executed study."""
        from scripts import study_route_acceptance as study, research_quality
        for name in ("preregistration.json", "experiment-evidence-plan.json"):
            (self.project / "papers/P01" / name).unlink()
        protocol = study.make_study(self.project, kind)
        study.freeze(self.project)
        registration = self.project / "papers/P01/preregistration.json"
        self.assertEqual(research_quality.validate_preregistration(read(registration), "P01", self.project), [])
        state = read(self.project / "state/run.json")
        state.update(stage_index=5, stage="writing-and-review", gate="G5", writing_phases={"P01":"submission"})
        write(self.project / "state/run.json", state)
        spec = read(self.project / review_panel.request_path("P01"))
        spec["views"]["statistics"] = [row for row in spec["views"]["statistics"] if row["kind"] != "protocol"]
        for path in (registration, self.project / "papers/P01/study-protocol.json"):
            spec["views"]["statistics"].append({"kind":"protocol", "path":path.relative_to(self.project).as_posix(),
                "sha256":sha(path), "start_line":1, "end_line":len(path.read_text().splitlines())})
        if kind == "theory":
            spec["views"]["domain"] = [row for row in spec["views"]["domain"] if row["kind"] != "numeric_table"]
            spec["views"]["statistics"] = [row for row in spec["views"]["statistics"] if row["kind"] == "protocol"]
            for name in sorted({row["source"] for row in protocol["theorems"]}):
                path = self.project / name
                spec["views"]["statistics"].append({"kind":"formal_proof", "path":name, "sha256":sha(path),
                    "start_line":1, "end_line":len(path.read_text().splitlines())})
            main = self.project / "papers/P01/manuscript/main.tex"
            main.write_text(re.sub(r"\\begin\{(table" + ("" if figure else "|figure") + r")\}.*?\\end\{\1\}", "", main.read_text(), flags=re.S))
            if figure:
                main.write_text(main.read_text().replace(
                    r"\pgfplotstabletypeset[col sep=comma,string type]{../tables/figure-values.csv}",
                    r"\fbox{Synthetic formal implication diagram; no measured data.}"))
            if not figure:
                spec["views"]["editorial"] = [row for row in spec["views"]["editorial"] if row["kind"] != "figure_one"]
        write(self.project / review_panel.request_path("P01"), spec)
        return protocol

    def test_meta_panel_uses_native_frozen_study_protocol_without_empirical_plan(self):
        self.study_inputs("meta_analysis")
        self.assertFalse((self.project / "papers/P01/experiment-evidence-plan.json").exists())
        packet = review_panel.prepare(self.project, "P01")
        self.assertIn('"outcomes"', packet["views"]["statistics"]["text"])
        result, calls = self.run_panel()
        self.assertEqual(calls.call_count, 3)
        self.assertEqual(result["paid_calls"], 3)
        self.assertFalse(result["scientific_completion_verified"])
        state = read(self.project / "state/run.json")
        state["approvals"][-1]["frozen_protocol_sha256"]["papers/P01/preregistration.json"] = "0" * 64
        write(self.project / "state/run.json", state)
        with patch.object(model_runtime, "call") as calls, self.assertRaisesRegex(ValueError, "G3 protocol decision"):
            review_panel.run(self.project, "P01", "replaced-study-freeze")
        calls.assert_not_called()

    def test_theory_panel_reads_complete_proofs_without_inventing_numeric_data_or_figure(self):
        self.study_inputs("theory")
        packet = review_panel.prepare(self.project, "P01")
        self.assertEqual({row["kind"] for row in packet["views"]["statistics"]["sources"]}, {"protocol", "formal_proof"})
        self.assertIn("add_zero_main", packet["views"]["statistics"]["text"])
        self.assertIn('"assumptions"', packet["views"]["statistics"]["text"])
        self.assertNotIn("figure_one", {row["kind"] for row in packet["views"]["editorial"]["sources"]})
        result, calls = self.run_panel()
        self.assertEqual(calls.call_count, 3)
        prompt = next(call.kwargs["prompt"] for call in calls.call_args_list if call.kwargs["role"].endswith("statistics"))
        self.assertIn("logical validity", prompt)
        self.assertNotIn("SYNTHETIC methods source", prompt)
        self.assertFalse(result["scientific_completion_verified"])

    def test_theory_retains_actual_first_figure_and_rejects_partial_or_changed_proof(self):
        self.study_inputs("theory", figure=True)
        request = self.project / review_panel.request_path("P01")
        spec = read(request)
        self.assertIn("figure_one", {row["kind"] for row in review_panel.prepare(self.project, "P01")["views"]["editorial"]["sources"]})
        next(row for row in spec["views"]["statistics"] if row["kind"] == "formal_proof")["end_line"] = 1
        write(request, spec)
        with patch.object(model_runtime, "call") as calls, self.assertRaisesRegex(ValueError, "complete source"):
            review_panel.run(self.project, "P01", "partial-proof")
        calls.assert_not_called()
        source = self.project / "analysis/proof.lean"
        source.write_text(source.read_text() + "\n-- Changed after freeze.\n")
        with patch.object(model_runtime, "call") as calls, self.assertRaises(ValueError):
            review_panel.run(self.project, "P01", "changed-proof")
        calls.assert_not_called()

    def test_empirical_request_cannot_declare_theory_to_waive_required_scientific_material(self):
        request = self.project / review_panel.request_path("P01")
        spec = read(request)
        spec["study_route"] = "theory"
        spec["views"]["domain"] = [row for row in spec["views"]["domain"] if row["kind"] != "numeric_table"]
        write(request, spec)
        with patch.object(model_runtime, "call") as calls, self.assertRaisesRegex(ValueError, "missing view-specific"):
            review_panel.run(self.project, "P01", "false-theory-waiver")
        calls.assert_not_called()

    def test_three_blind_distinct_families_freeze_before_synthesis_and_reuse_unchanged(self):
        result, calls = self.run_panel()
        self.assertEqual(calls.call_count, 3)
        self.assertEqual(result["paid_calls"], 3)
        records = review_panel.responses(self.project, "P01")
        self.assertEqual({r["receipt"]["identity"]["family"] for r in records}, {"anthropic", "google", "deepseek"})
        for call in calls.call_args_list:
            self.assertFalse(call.kwargs["use_cache"])
            self.assertEqual(call.kwargs["task_profile"]["science_risk"], "critical")
            seat = call.kwargs["role"].removeprefix("independent-critic-panel-")
            for other in set(review_panel.VIEWS) - {seat}:
                unique = review_panel.VIEWS[other] - review_panel.VIEWS[seat]
                self.assertFalse(any("SYNTHETIC " + k + " source" in call.kwargs["prompt"] for k in unique))
            self.assertNotIn("Rival explanation remains", call.kwargs["prompt"])
        self.assertFalse(result["scientific_completion_verified"])
        self.assertFalse(result["gate_authority"])
        self.assertEqual(result["findings"][0]["severity"], "major")
        reused, calls = self.run_panel("different-run")
        self.assertEqual(reused["paid_calls"], 0)
        self.assertEqual(calls.call_count, 0)
        self.assertEqual(reused["findings"], result["findings"])
        self.assertTrue(result["record_errors"])
        self.assertIn("Rival explanation remains", review_panel.author_context(self.project, "P01"))

    def test_private_other_paper_control_and_prior_review_paths_never_reach_transport(self):
        for relative in ("data/private/raw.csv", "papers/P02/manuscript/main.tex", "reviews/prior.json",
                         "papers/P01/manuscript/private/labels.txt", "program/answer-key.json", ".env"):
            with self.subTest(relative=relative):
                target = self.project / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("secret answer or unrelated paper", encoding="utf-8")
                spec = read(self.project / review_panel.request_path("P01"))
                spec["views"]["domain"][0].update(path=relative, sha256=sha(target))
                write(self.project / review_panel.request_path("P01"), spec)
                with patch.object(model_runtime, "call") as call, self.assertRaises(ValueError):
                    review_panel.run(self.project, "P01", "unsafe")
                call.assert_not_called()

    def test_copied_full_material_cannot_impersonate_distinct_views(self):
        spec = read(self.project / review_panel.request_path("P01"))
        for index, (seat, rows) in enumerate(spec["views"].items()):
            for row in rows:
                source = self.project / f"papers/P01/manuscript/{seat}-{row['kind']}.txt"
                source.write_text("Same full manuscript.\n" if index == 0 else "  Same   full\nmanuscript. \n", encoding="utf-8")
                row["path"] = source.relative_to(self.project).as_posix()
                row["sha256"] = sha(source)
        write(self.project / review_panel.request_path("P01"), spec)
        with patch.object(model_runtime, "call") as call, self.assertRaisesRegex(ValueError, "outside its actual canonical"):
            review_panel.run(self.project, "P01", "copied-views")
        call.assert_not_called()

    def test_distinct_views_may_share_the_actual_numeric_table(self):
        packet = review_panel.prepare(self.project, "P01")
        domain = next(row for row in packet["views"]["domain"]["sources"] if row.get("kind") == "numeric_table")
        statistics = next(row for row in packet["views"]["statistics"]["sources"] if row.get("kind") == "numeric_table")
        self.assertEqual(domain, statistics)
        self.assertNotEqual(packet["views"]["domain"]["sha256"], packet["views"]["statistics"]["sha256"])

    def test_full_manuscript_appended_to_otherwise_distinct_views_stops_before_transport(self):
        main = self.project / "papers/P01/manuscript/main.tex"
        text = main.read_text()
        for section in ("Introduction", "Methods", "Results", "Discussion", "Conclusion"):
            self.assertIn("\\section{" + section + "}", text)
        original = read(self.project / review_panel.request_path("P01"))
        kinds = {"domain":"methods", "editorial":"abstract", "statistics":"protocol"}
        for seats in (("domain",),("editorial",),("statistics",),tuple(review_panel.VIEWS)):
            spec = json.loads(json.dumps(original))
            for seat in seats:
                spec["views"][seat].append({"kind":kinds[seat], "path":main.relative_to(self.project).as_posix(),
                    "sha256":sha(main), "start_line":1, "end_line":len(text.splitlines())})
            write(self.project / review_panel.request_path("P01"), spec)
            with self.subTest(seats=seats), patch.object(model_runtime, "call") as call, \
                    self.assertRaisesRegex(ValueError, "actual canonical|canonical registered JSON"):
                review_panel.run(self.project, "P01", "full-manuscript-in-each-view")
            call.assert_not_called()

    def test_real_wrong_kind_and_cross_section_ranges_cannot_be_relabeled(self):
        main = self.project / "papers/P01/manuscript/main.tex"
        lines = main.read_text().splitlines()
        methods = next(i for i, line in enumerate(lines, 1) if line.startswith("SYNTHETIC methods"))
        results = next(i for i, line in enumerate(lines, 1) if line.startswith("SYNTHETIC results"))
        original = read(self.project / review_panel.request_path("P01"))
        for kind, first, last in (("abstract", methods, methods), ("methods", methods, results)):
            with self.subTest(kind=kind, first=first, last=last):
                spec = json.loads(json.dumps(original))
                seat = "editorial" if kind == "abstract" else "domain"
                row = next(row for row in spec["views"][seat] if row["kind"] == kind)
                row.update(path=main.relative_to(self.project).as_posix(), sha256=sha(main), start_line=first, end_line=last)
                write(self.project / review_panel.request_path("P01"), spec)
                with patch.object(model_runtime, "call") as call, self.assertRaisesRegex(ValueError, "actual canonical"):
                    review_panel.run(self.project, "P01", "wrong-kind")
                call.assert_not_called()

    def test_abstract_wrapper_and_nested_heading_markup_cannot_hide_whole_sections(self):
        main = self.project / "papers/P01/manuscript/main.tex"
        original = main.read_text()
        main.write_text(original.replace(r"\begin{abstract}", "").replace(r"\end{abstract}", "")
                        .replace(r"\begin{document}", "\\begin{document}\n\\begin{abstract}")
                        .replace(r"\end{document}", "\\end{abstract}\n\\end{document}"))
        with patch.object(model_runtime,"call") as calls, self.assertRaisesRegex(ValueError,"abstract crosses"):
            review_panel.run(self.project,"P01","wrapped-body")
        calls.assert_not_called()
        main.write_text(original.replace(r"\section{Results}", r"\section{\textbf{Results}}"))
        spec = read(self.project / review_panel.request_path("P01"))
        row = next(row for row in spec["views"]["domain"] if row["kind"] == "methods")
        lines = main.read_text().splitlines()
        start = next(i for i,line in enumerate(lines,1) if line.startswith("SYNTHETIC methods"))
        end = next(i for i,line in enumerate(lines,1) if line.startswith("SYNTHETIC results"))
        row.update(path=main.relative_to(self.project).as_posix(),sha256=sha(main),start_line=start,end_line=end)
        write(self.project / review_panel.request_path("P01"),spec)
        with patch.object(model_runtime,"call") as calls, self.assertRaisesRegex(ValueError,"actual canonical"):
            review_panel.run(self.project,"P01","nested-heading")
        calls.assert_not_called()

    def test_included_methods_keep_original_locations_and_source_changes_invalidate_panel(self):
        self.run_panel()
        main = self.project / "papers/P01/manuscript/main.tex"
        main.write_text(main.read_text().replace("A synthetic source-isolation software test.", "Changed introduction only."))
        with self.assertRaisesRegex(ValueError, "old judgments are historical"):
            review_panel.responses(self.project, "P01")
        included = main.with_name("design.tex")
        included.write_text("SYNTHETIC methods source, no actual experiment.\n")
        main.write_text(main.read_text().replace(included.read_text().strip(), r"\input{design}"))
        spec = read(self.project / review_panel.request_path("P01"))
        row = next(row for row in spec["views"]["domain"] if row["kind"] == "methods")
        row.update(path=included.relative_to(self.project).as_posix(), sha256=sha(included))
        write(self.project / review_panel.request_path("P01"), spec)
        packet = review_panel.prepare(self.project, "P01")
        binding = next(row for row in packet["views"]["domain"]["sources"] if row["kind"] == "methods")
        self.assertEqual(binding["path"], included.relative_to(self.project).as_posix())
        self.assertIn({"path":main.relative_to(self.project).as_posix(),"sha256":sha(main)}, binding["canonical_sources"])
        self.assertTrue(review_panel._pointer_in_view(binding["path"] + ":L1-L1", packet["views"]["domain"]["sources"]))

    def test_arbitrary_json_cannot_impersonate_protocol_or_figure_values(self):
        spec = read(self.project / review_panel.request_path("P01"))
        source = self.project / "papers/P01/tables/manuscript.json"
        write(source, {"title":"Whole manuscript", "methods":"Unscoped content", "results":"Unscoped results"})
        for kind in ("protocol", "figure_values"):
            with self.subTest(kind=kind):
                trial = json.loads(json.dumps(spec))
                row = next(row for row in trial["views"]["statistics"] if row["kind"] == kind)
                row.update(path=source.relative_to(self.project).as_posix(), sha256=sha(source), start_line=1,
                           end_line=len(source.read_text().splitlines()))
                write(self.project / review_panel.request_path("P01"), trial)
                with patch.object(model_runtime, "call") as call, self.assertRaises(ValueError):
                    review_panel.run(self.project, "P01", "arbitrary-json")
                call.assert_not_called()

    def test_protocol_cannot_hide_registered_comparisons_behind_a_partial_freeze_receipt(self):
        original = read(self.project / review_panel.request_path("P01"))
        trial = json.loads(json.dumps(original))
        next(row for row in trial["views"]["statistics"] if row["path"].endswith("preregistration.json"))["end_line"] = 1
        write(self.project / review_panel.request_path("P01"),trial)
        with patch.object(model_runtime,"call") as calls, self.assertRaisesRegex(ValueError,"complete canonical"):
            review_panel.run(self.project,"P01","empty-protocol")
        calls.assert_not_called()
        trial["views"]["statistics"] = [row for row in original["views"]["statistics"] if not row["path"].endswith("experiment-evidence-plan.json")]
        write(self.project / review_panel.request_path("P01"),trial)
        with patch.object(model_runtime,"call") as calls, self.assertRaisesRegex(ValueError,"both the complete frozen"):
            review_panel.run(self.project,"P01","freeze-receipt-only")
        calls.assert_not_called()
        write(self.project / review_panel.request_path("P01"),original)
        packet = review_panel.prepare(self.project,"P01")
        self.assertIn('"comparisons"', packet["views"]["statistics"]["text"])
        self.assertIn('"stop_if"', packet["views"]["statistics"]["text"])

    def test_first_figure_attachment_is_bound_to_actual_canonical_reference(self):
        from PIL import Image
        first = self.project / "papers/P01/figures/first.png"
        first.parent.mkdir(parents=True)
        Image.new("RGB", (2, 2), "white").save(first)
        second = first.with_name("second.png")
        Image.new("RGB", (2, 2), "black").save(second)
        main = self.project / "papers/P01/manuscript/main.tex"
        main.write_text(main.read_text().replace(r"\begin{figure}", "\\begin{figure}\n\\includegraphics{../figures/first.png}", 1)
            .replace(r"\end{document}", "\\begin{figure}\n\\includegraphics{../figures/second.png}\n\\caption{Second figure}\n\\end{figure}\n\\end{document}"))
        spec = read(self.project / review_panel.request_path("P01"))
        row = next(row for row in spec["views"]["editorial"] if row["kind"] == "figure_one")
        row.clear(); row.update(kind="figure_one", path=first.relative_to(self.project).as_posix(), sha256=sha(first))
        write(self.project / review_panel.request_path("P01"), spec)
        self.assertEqual(len(review_panel.prepare(self.project, "P01")["views"]["editorial"]["attachments"]), 1)
        row.update(path=second.relative_to(self.project).as_posix(), sha256=sha(second))
        write(self.project / review_panel.request_path("P01"), spec)
        with patch.object(model_runtime, "call") as call, self.assertRaisesRegex(ValueError, "canonical first figure"):
            review_panel.run(self.project, "P01", "wrong-figure")
        call.assert_not_called()

    def word_inputs(self):
        from docx import Document
        from PIL import Image
        main = self.project / "papers/P01/manuscript/main.tex"
        main.unlink()
        document = Document()
        document.add_paragraph("SYNTHETIC title source, no actual experiment.", style="Title")
        document.add_heading("Abstract", level=1)
        document.add_paragraph("SYNTHETIC abstract source, no actual experiment.")
        document.add_paragraph("SYNTHETIC headline_claim source, no actual experiment.")
        document.add_heading("Introduction", level=1)
        document.add_paragraph("A software fixture, not a scientific manuscript.")
        document.add_heading("Methods", level=1)
        document.add_paragraph("SYNTHETIC methods source, no actual experiment.")
        document.add_heading("Results", level=1)
        document.add_paragraph("SYNTHETIC results source, no actual experiment.")
        table = document.add_table(rows=2, cols=2)
        table.cell(0,0).text = "label"; table.cell(0,1).text = "value"
        table.cell(1,0).text = "SYNTHETIC numeric_table source, no actual experiment."; table.cell(1,1).text = "0"
        figure = self.project / "papers/P01/figures/first.png"
        figure.parent.mkdir(parents=True)
        Image.new("RGB", (2,2), "white").save(figure)
        document.add_picture(str(figure))
        document.add_paragraph("Figure 1. SYNTHETIC figure_one source, no actual experiment.", style="Caption")
        document.add_heading("Discussion", level=1); document.add_paragraph("No scientific conclusion.")
        canonical = main.with_suffix(".docx"); document.save(canonical)
        output = io.StringIO(); csv.writer(output, lineterminator="\n").writerows([
            ["label","value"],["SYNTHETIC numeric_table source, no actual experiment.","0"]])
        numeric = self.project / "papers/P01/tables/word-table.csv"; numeric.write_text(output.getvalue())
        values = self.project / "papers/P01/tables/figure-values.csv"
        write(figure.parent / "figure-provenance.json", {"schema_version":"1.0", "figures":[{
            "figure_path":figure.relative_to(self.project).as_posix(),"figure_type":"data_chart", "output_sha256":sha(figure),
            "inputs":[{"path":values.relative_to(self.project).as_posix(), "sha256":sha(values)}],
            "source_run_ids":["explicit-software-fixture"],"source_lineage":{"fixture_only":True}}]})
        spec = read(self.project / review_panel.request_path("P01"))
        for rows in spec["views"].values():
            for row in rows:
                if row["kind"] == "numeric_table":
                    row.update(path=numeric.relative_to(self.project).as_posix(), sha256=sha(numeric), end_line=2)
        row = next(row for row in spec["views"]["domain"] if row["kind"] == "methods")
        row.clear(); row.update(kind="methods", path=canonical.relative_to(self.project).as_posix(), sha256=sha(canonical),
                                start_paragraph=8, end_paragraph=8)
        write(self.project / review_panel.request_path("P01"), spec)
        return canonical, spec

    def test_word_headings_tables_and_first_figure_preserve_legitimate_panel_route(self):
        canonical, spec = self.word_inputs()
        with patch("scripts.figure_provenance.lineage", return_value={"fixture_only":True}):
            packet = review_panel.prepare(self.project, "P01")
            source = next(row for row in packet["views"]["domain"]["sources"] if row["kind"] == "methods")
            self.assertTrue(review_panel._pointer_in_view(source["path"] + ":P8-P8", [source]))
            self.assertFalse(review_panel._pointer_in_view(source["path"] + ":L8-L8", [source]))
            def response(project, **kwargs):
                result = self.response(project, **kwargs)
                result.text = result.text.replace("papers/P01/manuscript/methods.txt:L1-L1", source["path"] + ":P8-P8")
                return result
            with patch.object(model_runtime, "call", side_effect=response) as calls:
                result = review_panel.run(self.project, "P01", "word-scoped-fixture")
            self.assertEqual(result["paid_calls"], 3); self.assertEqual(calls.call_count, 3)
            row = next(row for row in spec["views"]["editorial"] if row["kind"] == "abstract")
            row.clear(); row.update(kind="abstract", path=source["path"], sha256=sha(canonical), start_paragraph=1, end_paragraph=18)
            write(self.project / review_panel.request_path("P01"), spec)
            with patch.object(model_runtime, "call") as calls, self.assertRaisesRegex(ValueError, "actual canonical"):
                review_panel.run(self.project, "P01", "whole-word-file")
            calls.assert_not_called()

    def test_word_formula_structure_is_preserved_and_opaque_objects_are_explicit(self):
        from docx import Document
        from docx.oxml import OxmlElement
        canonical, spec = self.word_inputs()
        document = Document(canonical)
        paragraph = next(p for p in document.paragraphs if p.text.startswith("SYNTHETIC methods"))
        formula = OxmlElement("m:oMath"); fraction = OxmlElement("m:f")
        for tag, value in (("m:num", "1"), ("m:den", "2")):
            part = OxmlElement(tag); run = OxmlElement("m:r"); number = OxmlElement("m:t")
            number.text = value; run.append(number); part.append(run); fraction.append(part)
        formula.append(fraction); paragraph._p.append(formula); document.save(canonical)
        row = next(row for row in spec["views"]["domain"] if row["kind"] == "methods")
        row["sha256"] = sha(canonical); write(self.project / review_panel.request_path("P01"),spec)
        with patch("scripts.figure_provenance.lineage", return_value={"fixture_only":True}):
            text = review_panel.prepare(self.project,"P01")["views"]["domain"]["text"]
            self.assertIn("OMML formula:", text); self.assertIn(":num>", text); self.assertIn(":den>", text)
            paragraph._p.append(OxmlElement("w:object")); document.save(canonical)
            row["sha256"] = sha(canonical); write(self.project / review_panel.request_path("P01"),spec)
            with patch.object(model_runtime,"call") as calls, self.assertRaisesRegex(ValueError,"unrendered embedded object"):
                review_panel.run(self.project,"P01","opaque-word-object")
            calls.assert_not_called()

    def test_word_layout_table_cannot_smuggle_document_sections_as_numeric_table(self):
        from docx import Document
        from scripts.revision_integrity import WordSource, W
        canonical, spec = self.word_inputs()
        document = Document(canonical)
        layout = document.add_table(rows=2, cols=2)
        layout.cell(0,0).text = "Title and abstract"; layout.cell(0,1).text = "0"
        layout.cell(1,0).text = "0"; layout.cell(1,1).text = "0"
        for node in list(document.element.body):
            if node.tag.endswith("}p"):
                layout.cell(0,0)._tc.append(node)
        document.save(canonical)
        paragraphs = ["".join(node.text or "" for node in p.iter() if node.tag.endswith("}t"))
                      for p in WordSource(canonical).root.iter(W + "p")]
        methods = next(i for i,value in enumerate(paragraphs,1) if value.startswith("SYNTHETIC methods"))
        # A valid table remains elsewhere; the layout table must not acquire
        # numeric authority merely because its cells surround the manuscript.
        spec["views"]["domain"] = [row for row in spec["views"]["domain"] if row["kind"] != "numeric_table"]
        spec["views"]["domain"].append({"kind":"numeric_table", "path":canonical.relative_to(self.project).as_posix(),
            "sha256":sha(canonical),"start_paragraph":5,"end_paragraph":len(paragraphs)})
        for rows in spec["views"].values():
            for row in rows:
                if row["path"] == canonical.relative_to(self.project).as_posix(): row["sha256"] = sha(canonical)
                if row["kind"] == "methods": row.update(start_paragraph=methods,end_paragraph=methods)
        write(self.project / review_panel.request_path("P01"), spec)
        with patch("scripts.figure_provenance.lineage", return_value={"fixture_only":True}), \
                patch.object(model_runtime, "call") as calls, self.assertRaisesRegex(ValueError,"numeric_table selection is outside"):
            review_panel.run(self.project, "P01", "word-layout-as-data")
        calls.assert_not_called()

    def test_side_task_payloads_cannot_restore_full_manuscript_after_source_validation(self):
        from scripts import literature_source_tasks as tasks
        main = self.project / "papers/P01/manuscript/main.tex"
        full = main.read_text()
        source = {"path":main.relative_to(self.project).as_posix(), "sha256":sha(main), "locator":"complete canonical paper"}
        write(self.project / "program/citation-task.json", {"schema_version":"1.0", "id":"full-source", "paper_id":"P01", "source":source})
        write(self.project / "program/claim-task.json", {"paper_id":"P01", "claim":full, "context":full,
              "prior_verdict":"PRIVATE_PRIOR_CLAIM_OPINION"})
        write(self.project / tasks.CONTROL, {"scientific_judgments":[
            {"operation":operation,"request_file":request,"paper_id":"P01","stages":["writing-and-review"],"panel_views":list(review_panel.VIEWS)}
            for operation,request in (("citation_crosscheck","program/citation-task.json"),("claim_evidence","program/claim-task.json"))]})
        # This really is a source-capable task, not a mocked payload. Ordinary
        # configuration remains usable; the final panel never prepares it.
        prepared = tasks.prepare_panel_task(self.project,"citation_crosscheck","program/citation-task.json",paper_id="P01")
        self.assertEqual(prepared["packet"]["source_text"], full)
        with patch.object(tasks,"selected_context",side_effect=AssertionError("final panel must not prepare ordinary tasks")), \
                patch.object(model_runtime,"call",side_effect=self.response) as calls:
            result = review_panel.run(self.project,"P01","side-tasks-stay-ordinary")
            reused = review_panel.run(self.project,"P01","ordinary-config-kept")
        self.assertEqual(calls.call_count,3); self.assertEqual(reused["paid_calls"],0)
        self.assertEqual(result["source_task_execution"],"not_performed_by_final_panel")
        for call in calls.call_args_list:
            self.assertNotIn(full,call.kwargs["prompt"])
            self.assertNotIn("PRIVATE_PRIOR_CLAIM_OPINION",call.kwargs["prompt"])
            self.assertNotIn("SELECTED TASKS",call.kwargs["prompt"])
        for field in ("claim_evidence","citation_extraction","anchor_labels"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,"its own view"):
                review_panel._response({"view":"domain","findings":[],"uncertainty":[],field:[]},"domain")

    def test_legacy_task_fields_remain_archived_but_do_not_become_current_panel_judgments(self):
        result, _ = self.run_panel("legacy")
        manifest_path = self.project / result["manifest"]["path"]
        manifest = read(manifest_path); manifest.pop("source_task_execution")
        for binding in manifest["receipts"].values():
            receipt_path = self.project / binding["path"]; receipt = read(receipt_path)
            response_path = self.project / receipt["response"]["path"]
            response = read(response_path)
            response["claim_evidence"] = [{"id":"HISTORICAL_TASK_ONLY"}]
            write(response_path,response); record(self.project,[response_path],review_panel.MODULE)
            receipt["response"]["sha256"] = sha(response_path)
            write(receipt_path,receipt); record(self.project,[receipt_path],review_panel.MODULE)
            binding["sha256"] = sha(receipt_path)
        write(manifest_path,manifest); record(self.project,[manifest_path],review_panel.MODULE)
        latest = self.project / review_panel.PREFIX / "P01/latest.json"
        write(latest,{"path":manifest_path.relative_to(self.project).as_posix(),"sha256":sha(manifest_path)})
        record(self.project,[latest],review_panel.MODULE)
        for observation in review_panel.responses(self.project,"P01"):
            self.assertNotIn("claim_evidence",observation["response"])
            raw = self.project / observation["receipt"]["response"]["path"]
            self.assertIn("HISTORICAL_TASK_ONLY",raw.read_text())
        reused, calls = self.run_panel("after-migration")
        self.assertEqual(calls.call_count,0)
        self.assertEqual(reused["findings"],result["findings"])

    def test_partial_failure_retained_and_same_id_never_repaid(self):
        count = 0
        def fail(project, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise ValueError("synthetic transport failure")
            return self.response(project, **kwargs)
        with patch.object(model_runtime, "call", side_effect=fail), self.assertRaisesRegex(ValueError, "transport failure"):
            review_panel.run(self.project, "P01", "partial")
        directory = self.project / review_panel.PREFIX / "P01/partial"
        self.assertTrue((directory / "domain.json").is_file())
        self.assertTrue((directory / "failure.json").is_file())
        self.assertFalse((directory.parent / "latest.json").exists())
        with patch.object(model_runtime, "call") as call, self.assertRaisesRegex(ValueError, "already attempted"):
            review_panel.run(self.project, "P01", "partial")
        call.assert_not_called()

    def test_identity_mismatch_retains_actual_failed_response(self):
        def mismatch(project, **kwargs):
            result = self.response(project, **kwargs)
            result.reported_model = "unexpected"
            return result
        with patch.object(model_runtime, "call", side_effect=mismatch), self.assertRaisesRegex(ValueError, "mismatch"):
            review_panel.run(self.project, "P01", "identity")
        self.assertTrue((self.project / review_panel.PREFIX / "P01/identity/domain-actual-response.json").is_file())
        self.assertTrue(review_panel.submission_errors(self.project, "P01"))

    def test_stale_sources_require_new_call_and_retained_disagreement(self):
        self.run_panel()
        path = self.project / "papers/P01/manuscript/methods.txt"
        path.write_text(path.read_text() + "A second synthetic source line.\n")
        self.assertTrue(review_panel.submission_errors(self.project, "P01"))
        spec = read(self.project / review_panel.request_path("P01"))
        for row in spec["views"]["domain"]:
            if row["kind"] == "methods": row["sha256"] = sha(path)
        spec["dispositions"] = [{"finding_id":"first:domain:rival-1", "status":"maintained", "rationale":"No discriminating experiment exists", "evidence":[]}]
        write(self.project / review_panel.request_path("P01"), spec)
        result, calls = self.run_panel("second")
        manifest = read(self.project / result["manifest"]["path"])
        self.assertEqual(calls.call_count, 3)
        self.assertEqual(len(manifest["prior_findings"]), 1)
        self.assertNotEqual(manifest["prior_findings"][0]["finding_id"], manifest["findings"][0]["finding_id"])
        self.assertEqual(manifest["prior_findings"][0]["local_finding_id"], manifest["findings"][0]["local_finding_id"])
        self.assertEqual(manifest["author_dispositions"], spec["dispositions"])
        self.assertIsNone(manifest["acceptance_probability"])

    def test_tampered_frozen_report_never_becomes_cache_miss_or_new_paid_call(self):
        result, _ = self.run_panel()
        target = self.project / result["manifest"]["path"]
        target.write_text(target.read_text() + "\n")
        with patch.object(model_runtime, "call") as call, self.assertRaises(ValueError):
            review_panel.run(self.project, "P01", "changed")
        call.assert_not_called()

    def test_shared_submission_adapter_does_not_create_ordinary_critic(self):
        with patch.object(research_cycle, "research_decision", return_value={"status":"recorded", "scientific_completion_verified":False}), \
                patch.object(model_runtime, "call", side_effect=self.response) as calls:
            result = research_cycle.submission_cycle(self.project, "adapter", writer_family="openai",
                refresh=lambda phase: ({"controlled_steps":{}, "academic_style_audit":{}}, {}))
        self.assertEqual(calls.call_count, 3)
        self.assertEqual(result["audits"], {})
        self.assertFalse(result["research_decision"]["scientific_completion_verified"])
        self.assertFalse((self.project / "state/review-receipts/G5-P01").exists())

    def test_model_cannot_overwrite_controller_finding_identity(self):
        result = self.response(self.project, role="independent-critic-panel-domain", provider="codekey-kiro-enterprise", model="claude-opus-5-5")
        response = json.loads(result.text)
        for field in ("finding_id", "source_run_id", "view", "local_finding_id"):
            forged = {**response, "findings":[{**response["findings"][0], field:"forged"}]}
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "read-only schema"):
                review_panel._response(forged, "domain")

    def test_pointer_must_be_inside_supplied_range(self):
        for pointer in ("papers/P01/manuscript/methods.txt:L999999", "papers/P01/manuscript/methods.txt:Lgarbage",
                        "papers/P01/manuscript/methods.txt:L1-L2", "papers/P01/manuscript/methods.txt"):
            with self.subTest(pointer=pointer):
                self.assertFalse(review_panel._pointer_in_view(pointer, review_panel.prepare(self.project, "P01")["views"]["domain"]["sources"]))
        self.assertTrue(review_panel._pointer_in_view("papers/P01/manuscript/methods.txt:L1-L1",
            review_panel.prepare(self.project, "P01")["views"]["domain"]["sources"]))

    def test_author_disposition_alone_does_not_repeat_paid_panel(self):
        result, _ = self.run_panel()
        spec = read(self.project / review_panel.request_path("P01"))
        spec["dispositions"] = [{"finding_id":result["findings"][0]["finding_id"], "status":"maintained",
            "rationale":"No discriminating evidence has arrived", "evidence":[{"path":"papers/P01/manuscript/methods.txt", "sha256":sha(self.project / "papers/P01/manuscript/methods.txt")}]}]
        write(self.project / review_panel.request_path("P01"), spec)
        reused, calls = self.run_panel("author-response")
        self.assertEqual(calls.call_count, 0)
        self.assertEqual(reused["author_dispositions"], spec["dispositions"])
        self.assertEqual(review_panel.submission_errors(self.project, "P01"), [])
        self.assertFalse(reused["scientific_completion_verified"])
        self.assertEqual(reused["findings"][0]["severity"], "major")

    def test_context_plan_cannot_reintroduce_hidden_answers(self):
        from scripts import evidence_context
        target = self.project / "evidence/answer.txt"
        target.parent.mkdir()
        target.write_text("Hidden expected judgment")
        write(self.project / "program/context-plan.json", {"schema_version":"1.0", "stages":{
            "writing-and-review":{"question":"Inspect evidence", "items":[{"path":"evidence/answer.txt", "reason":"try", "stance":"neutral"}]}}})
        with self.assertRaisesRegex(ValueError, "hidden judgment"):
            evidence_context.build(self.project, "writing-and-review", excluded_paths={"evidence/answer.txt"})
