"""Model substitutes exercise evidence binding, never publication quality."""
from __future__ import annotations

import hashlib
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import automated_visual_review as visual, output_provenance
from scripts.research_artifacts import read, record, sha, write


class AutomatedVisualReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name) / "study"
        self.paper = self.project / "papers/P01"
        self.target = self.paper / "figures/chart.png"
        self.target.parent.mkdir(parents=True)
        from PIL import Image
        Image.new("RGB", (80, 60), "white").save(self.target)
        write(self.project / "state/run.json", {"stage": "writing-and-review", "status": "awaiting_work", "active_paper": "P01"})
        self.rows = []
        self.outcome = "pass"
        self.calls = 0
        self.bad_response = False
        self.addCleanup(patch.stopall)
        patch.object(visual.model_routing, "select", return_value={"provider": "synthetic-visual"}).start()
        patch.object(visual.model_runtime, "ledger_entries", side_effect=lambda _: list(self.rows)).start()
        patch.object(visual.ai_providers, "require_complete").start()
        patch.object(visual.model_runtime, "call", side_effect=self.call).start()

    def call(self, project, **request):
        self.calls += 1
        packet = json.loads(request["prompt"].split("Packet:\n", 1)[1])
        pages = packet["page_count"]
        text = "invalid" if self.bad_response else json.dumps({"pages": [{"page": n,
            "checks": {key: self.outcome for key in packet["checks"]},
            "notes": "Synthetic visual output exercises page coverage only."} for n in range(1, pages + 1)]})
        attachment = request["attachments"][0]
        import base64
        self.rows.append({"run_id": request["run_id"], "role": "multimodal-inspection",
            "prompt_sha256": hashlib.sha256(request["prompt"].encode()).hexdigest(),
            "request_id": "fixture-" + str(self.calls), "model": "synthetic-model",
            "completion_status": "completed", "cost_status": "settled_usage_receipt",
            "attachments": [{"sha256": attachment["sha256"], "mime_type": attachment["mime_type"],
                             "size_bytes": len(base64.b64decode(attachment["data_base64"]))}]})
        return types.SimpleNamespace(text=text, provider="synthetic-visual", request_id="fixture-" + str(self.calls),
                                     reported_model="synthetic-model")

    def test_real_file_binding_model_identity_and_idempotency(self):
        target = self.target.relative_to(self.project).as_posix()
        result = visual.execute(self.project, "P01", target)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["human_review"])
        self.assertEqual(visual.verify(self.project, "P01", target), [])
        self.assertEqual(visual.execute(self.project, "P01", target), result)
        self.assertEqual(self.calls, 1)
        self.rows[0]["attachments"][0]["sha256"] = "0" * 64
        self.assertTrue(visual.verify(self.project, "P01", target))

    def test_unknown_or_malformed_reply_blocks_without_repeated_paid_calls(self):
        target = self.target.relative_to(self.project).as_posix()
        self.outcome = "unknown"
        self.assertEqual(visual.execute(self.project, "P01", target)["status"], "fail")
        self.assertTrue(visual.verify(self.project, "P01", target))
        self.assertEqual(visual.execute(self.project, "P01", target)["status"], "fail")
        self.assertEqual(self.calls, 1)
        from PIL import Image
        Image.new("RGB", (81, 60), "white").save(self.target)
        self.bad_response = True
        result = visual.execute(self.project, "P01", target)
        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(visual.execute(self.project, "P01", target)["status"], "invalid_response")
        self.assertEqual(self.calls, 2)

    def test_every_actual_pdf_page_is_required(self):
        packet = {"page_count": 2}
        with self.assertRaisesRegex(ValueError, "every page"):
            visual._response(json.dumps({"pages": [{"page": 1, "checks": {key: "pass" for key in visual.CHECKS}, "notes": "Fixture"}]}), packet)

    def test_docx_requires_current_real_render_receipt(self):
        source = self.paper / "manuscript/main.docx"
        source.parent.mkdir()
        source.write_bytes(b"synthetic bound DOCX input")
        target = source.relative_to(self.project).as_posix()
        with self.assertRaises(ValueError):
            visual.execute(self.project, "P01", target)
        self.assertEqual(self.calls, 0)
        import fitz
        pdf = source.with_suffix(".pdf")
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), "Synthetic render fixture")
            document.save(pdf)
        receipt = self.paper / "reviews/cloud-word-build.json"
        write(receipt, {"status": "pass", "inputs_unchanged": True, "source_sha256": sha(source),
                        "execution": {"mode": "cloud"},
                        "inputs": [{"path": target, "sha256": sha(source)}],
                        "outputs": [{"path": pdf.relative_to(self.project).as_posix(), "sha256": sha(pdf)}]})
        output_provenance.record_model_writes(self.project, [receipt], family="other", provider="cloud-word-renderer",
                                             model="synthetic-test", role="render-receipt", run_id="fixture")
        self.assertEqual(visual.execute(self.project, "P01", target)["status"], "pass")
        source.write_bytes(b"changed source")
        self.assertTrue(visual.verify(self.project, "P01", target))

    def test_tex_final_pdf_uses_exact_cloud_render_and_all_pages(self):
        source=self.paper/"manuscript/main.tex";source.parent.mkdir()
        source.write_text("% Synthetic TeX source for binding checks\n",encoding="utf-8")
        import fitz
        pdf=source.with_suffix(".pdf")
        with fitz.open() as document:
            for _ in range(2):document.new_page().insert_text((72,72),"Synthetic rendered page")
            document.save(pdf)
        receipt=self.paper/"reviews/cloud-tex-build.json"
        write(receipt,{"status":"pass","inputs_unchanged":True,"source_sha256":sha(source),"execution":{"mode":"cloud"},
                       "inputs":[{"path":source.relative_to(self.project).as_posix(),"sha256":sha(source)}],
                       "outputs":[{"path":pdf.relative_to(self.project).as_posix(),"sha256":sha(pdf)}]})
        output_provenance.record_model_writes(self.project,[receipt],family="other",provider="cloud-tex-renderer",model="synthetic-test",role="render-receipt",run_id="fixture")
        target=source.relative_to(self.project).as_posix()
        result=visual.execute(self.project,"P01",target)
        self.assertEqual(result["status"],"pass");self.assertEqual(len(result["pages"]),2)
        self.assertEqual(visual.verify(self.project,"P01",target),[])

    def test_svg_preview_is_derived_without_altering_original(self):
        source = self.target.with_suffix(".svg")
        source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="80"><text x="5" y="20">Fixture</text></svg>', encoding="utf-8")
        original = source.read_bytes()
        target = source.relative_to(self.project).as_posix()
        packet = visual.prepare(self.project, "P01", target, create=True)
        first = sha(self.project / packet["attachment"]["path"])
        self.assertEqual(visual.prepare(self.project, "P01", target, create=True), packet)
        self.assertEqual(sha(self.project / packet["attachment"]["path"]), first)
        self.assertEqual(source.read_bytes(), original)

    def test_run_uses_declared_final_assets_and_propagates_budget_failure(self):
        extra = self.target.with_name("unselected-preview.png")
        extra.write_bytes(self.target.read_bytes())
        registry = self.target.parent / "figure-provenance.json"
        write(registry, {"figures": [{"figure_path": self.target.relative_to(self.project).as_posix()}]})
        record(self.project, [registry], "scripts/figure_provenance.py")
        report = visual.run(self.project, "P01")
        self.assertEqual(report["checked"], [self.target.relative_to(self.project).as_posix()])
        self.assertEqual(self.calls, 1)
        from PIL import Image
        Image.new("RGB", (82, 60), "white").save(self.target)
        with patch.object(visual.model_runtime, "call", side_effect=visual.model_runtime.ModelBudgetError("unsettled charge")):
            with self.assertRaises(visual.model_runtime.ModelBudgetError):
                visual.run(self.project, "P01")

    def packet_fixture(self):
        from scripts import review_packets
        from PIL import Image
        source = self.target.with_name("recorded-source.py")
        source.write_text("# Synthetic chart source; no scientific result.\n", encoding="utf-8")
        preview = self.target.with_name("chart-gray.png")
        Image.new("RGB", (80, 60), "gray").save(preview)
        bind = lambda path: {"path": path.relative_to(self.project).as_posix(), "sha256": sha(path), "locator": "Synthetic full-file binding"}
        qa = self.paper / "reviews/chart-qa.json"
        write(qa, {"status": "review_required", "errors": [], "pending_human_checks": ["Inspect mathematical layout in actual preview."]})
        record(self.project, [qa], "synthetic-qa-fixture")
        receipt = self.paper / "reviews/chart-render.json"
        write(receipt, {"schema_version": "1.0", "status": "pass", "inputs": [bind(source)],
            "outputs": [bind(self.target), bind(preview)],
            "renderer": {"name": "cloud_runtime", "implementation_sha256": sha(review_packets.ROOT / "scripts/cloud_runtime.py")},
            "execution": {"mode": "cloud", "receipt_id": "synthetic-controlled-render"}})
        output_provenance.record_model_writes(self.project, [receipt], family="other", provider="cloud-tex-renderer",
            model="synthetic-test", role="render-receipt", run_id="fixture")
        checks = ["math_symbols", "final_size_readability", "color_vision", "statistical_labels"]
        packet = {"id": "visual-one", "kind": "visual", "rubric": {
            "dimensions": [{"id": "readable", "description": "Visual readability", "value_type": "integer", "min": 0, "max": 3}],
            "critical_errors": [{"id": "clipping", "criterion": "Content is clipped"}]},
            "artifacts": [{"id": "chart", "artifact": bind(self.target), "sources": [bind(source)],
                           "previews": [bind(preview)], "qa_report": bind(qa), "render_receipt": bind(receipt), "checklist": checks}]}
        write(self.project / review_packets.INPUT, {"schema_version": "1.0", "packets": [packet]})
        self.assertEqual(review_packets.refresh(self.project)["status"], "pass")
        return packet

    def test_declared_visual_packet_passes_from_actual_metered_views_without_human_vote(self):
        from scripts import review_packets
        packet = self.packet_fixture()
        target = visual.packet_target(packet["id"], "chart")
        self.assertTrue(review_packets.validate_gate_reviews(self.project, "P01"))
        report = visual.run(self.project, "P01")
        self.assertEqual(report["checked"], [target])
        self.assertEqual(self.calls, 1)
        prepared = visual.prepare(self.project, "P01", target)
        self.assertEqual(prepared["page_count"], 2)
        self.assertEqual(len(prepared["rendered_views"]), 2)
        self.assertTrue(set(packet["artifacts"][0]["checklist"]) <= set(prepared["checks"]))
        self.assertEqual(review_packets.validate_gate_reviews(self.project, "P01"), [])
        self.assertEqual(review_packets.audit(self.project)["packets"][0]["review_status"], "automated_visual_observations_recorded")
        self.assertFalse(review_packets.audit(self.project)["packets"][0]["human_observations_recorded"])
        self.assertFalse((self.project / "state/review-packet-confirmations").exists())
        self.assertFalse(visual.execute(self.project, "P01", target)["human_review"])
        self.assertEqual(self.calls, 1)
        source = self.project / packet["artifacts"][0]["sources"][0]["path"]
        source.write_text("# Changed source.\n", encoding="utf-8")
        self.assertTrue(review_packets.validate_gate_reviews(self.project, "P01"))

    def test_packet_unknown_checks_block_without_repeated_paid_votes(self):
        from scripts import review_packets
        packet = self.packet_fixture()
        target = visual.packet_target(packet["id"], "chart")
        self.outcome = "unknown"
        self.assertEqual(visual.execute(self.project, "P01", target)["status"], "fail")
        self.assertTrue(review_packets.validate_gate_reviews(self.project, "P01"))
        self.assertEqual(visual.execute(self.project, "P01", target)["status"], "fail")
        self.assertEqual(self.calls, 1)

    def test_adverse_human_observations_cannot_be_outvoted_on_unchanged_material(self):
        from scripts import review_packets
        packet = self.packet_fixture()
        target = visual.packet_target(packet["id"], "chart")
        # A prior unchanged adverse observation remains evidence even if a
        # subsequently recorded model inspection reports every check as passing.
        self.assertEqual(visual.execute(self.project, "P01", target)["status"], "pass")
        judgments = {"rater_id": "synthetic-rater", "independent": True, "independence_note": "Synthetic independent observation",
            "inspections": [{"artifact_id": "chart", "checks": {key: key != "math_symbols" for key in packet["artifacts"][0]["checklist"]},
                             "note": "Synthetic adverse symbol observation."}]}
        path, confirmation = review_packets.create_confirmation(self.project, packet["id"], "Synthetic owner", judgments)
        write(path, confirmation)
        self.assertTrue(any("adverse" in issue for issue in review_packets.validate_gate_reviews(self.project, "P01")))
        self.assertEqual(len(review_packets.audit(self.project)["packets"][0]["confirmations"]), 1)

    def test_other_paper_packet_is_not_a_current_paper_human_or_visual_gate(self):
        from scripts import review_packets
        packet = self.packet_fixture()
        original = read(self.project / review_packets.INPUT)
        import copy
        future = copy.deepcopy(packet)
        future["id"] = "future-paper"
        future["artifacts"][0]["artifact"]["path"] = "papers/P02/figures/future.png"
        original["packets"].append(future)
        write(self.project / review_packets.INPUT, original)
        # Refresh the selected packet while preserving the unavailable future
        # packet as an explicit blocker for its own later stage.
        self.assertEqual(review_packets.refresh(self.project)["status"], "fail")
        self.assertEqual(visual.run(self.project, "P01")["blockers"], [])
        self.assertEqual(review_packets.validate_gate_reviews(self.project, "P01"), [])
        self.assertTrue(review_packets.validate_gate_reviews(self.project, "P02"))


if __name__ == "__main__":
    unittest.main()
