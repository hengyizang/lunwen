"""Source-bound synthetic fixtures; no providers, downloads or experiments.

Run in the cloud validation workflow. These tests do not validate scientific
interpretations, human reading, research novelty, or general model ability.
"""
import copy
import hashlib
import html
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import literature_workbench as workbench, paper_reader
from scripts.research_artifacts import read, record, sha, write


class WorkbenchFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.config = {"schema_version": "1.0", "papers": []}

    def source(self, relative, text):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return {"path": relative, "sha256": sha(path)}

    def add_paper(self, identifier, text, *, topic="topic-a", paper_ids=None, title=None):
        source = self.source(f"evidence/sources/{identifier}.txt", text)
        paper = {"id": identifier, "title": title or identifier, "source": source,
                 "topic_id": topic, "paper_ids": ["P01"] if paper_ids is None else paper_ids}
        self.config["papers"].append(paper)
        return paper

    def anchor(self, paper, quote, first=1, last=1):
        return {**paper["source"], "start_line": first, "end_line": last, "quote": quote}

    def card(self, paper, *, field="findings", quote=None, kind="author_claim", boundary=None):
        text = (self.project / paper["source"]["path"]).read_text(encoding="utf-8").splitlines()[0]
        row = {"text": text, "kind": kind, "evidence": [self.anchor(paper, quote or text)]}
        if boundary is not None:
            row["inference_boundary"] = boundary
        card = {"schema_version": "1.0", "paper_id": paper["id"], "fields": {field: [row]}}
        path = f"evidence/reading-cards/{paper['id']}.json"
        write(self.project / path, card)
        paper["card"] = {"path": path, "sha256": sha(self.project / path)}
        return card

    def build(self):
        write(self.project / workbench.CONFIG, self.config)
        return workbench.build(self.project)

    def output(self, filename):
        return read(self.project / workbench.OUTPUT / filename)


class WorkbenchTests(WorkbenchFixture):
    def test_persistent_bm25_pending_cards_and_no_model_calls(self):
        a = self.add_paper("a", "Gain invariance survives scalar rescaling.\nNegative controls remain pending.")
        self.add_paper("b", "A different benchmark measures calibration.")
        with patch("scripts.model_runtime.call", side_effect=AssertionError("no provider allowed")):
            result = self.build()
            hits = workbench.search(self.project, "gain invariance")
            plan = workbench.itinerary(self.project, "gain invariance")
        self.assertFalse(result["model_call_made"])
        self.assertEqual(hits["results"][0]["paper_id"], "a")
        self.assertEqual(hits["results"][0]["sha256"], a["source"]["sha256"])
        self.assertEqual(hits["results"][0]["start_line"], 1)
        self.assertIn("bm25", hits["method"])
        card = self.output("cards/a.json")
        self.assertEqual(card["status"], "pending_analysis")
        self.assertEqual(set(card["unknown_fields"]), set(workbench.FIELDS))
        self.assertFalse(card["human_full_text_reading_verified"])
        self.assertFalse(plan["scientific_completion_verified"])
        self.assertTrue(self.output("search-index.json")["postings"])

    def test_read_once_reuse_and_changed_input_fail_closed(self):
        a = self.add_paper("a", "Gain invariance appears in the synthetic source.")
        self.add_paper("b", "A stable independent calibration note.")
        self.build()
        repeated = self.build()
        self.assertEqual(repeated["reused_papers"], ["a", "b"])
        (self.project / a["source"]["path"]).write_text("Changed gain evidence.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            workbench.search(self.project, "gain")
        stale = self.build()
        self.assertEqual(stale["status"], "blocked")
        self.assertEqual(stale["reused_papers"], ["b"])
        self.assertEqual(self.output("cards/a.json")["status"], "blocked")
        with self.assertRaisesRegex(ValueError, "stale or invalid"):
            workbench.comparison_packet(self.project, ["a"])

    def test_rebinding_changed_source_invalidates_only_its_cached_card(self):
        a = self.add_paper("a", "Original source observation.")
        self.add_paper("b", "Independent stable observation.")
        self.card(a)
        self.build()
        path = self.project / a["source"]["path"]
        path.write_text("Replacement source observation.", encoding="utf-8")
        a["source"]["sha256"] = sha(path)
        result = self.build()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reused_papers"], ["b"])
        self.assertTrue(any("stale input hash" in e["error"] for e in result["errors"]))

    def test_output_tampering_and_manifest_tampering_require_rebuild(self):
        self.add_paper("a", "Exact evidence with gain invariance.")
        self.build()
        path = self.project / workbench.OUTPUT / "search-index.json"
        path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "output changed"):
            workbench.search(self.project, "gain")
        self.assertEqual(self.build()["reused_papers"], [])
        manifest = self.project / workbench.OUTPUT / "manifest.json"
        value = read(manifest)
        value["inputs"] = []
        write(manifest, value)
        with self.assertRaisesRegex(ValueError, "provenance"):
            workbench.search(self.project, "gain")

    def test_exact_card_locations_and_claim_inference_separation(self):
        a = self.add_paper("a", "Author baseline is logistic regression.\nA later line names device splits.")
        card = self.card(a, field="baseline")
        validated = workbench.validate_card(self.project, a, card)
        self.assertFalse(validated["semantic_verification"])
        anchor = validated["fields"]["baseline"][0]["evidence"][0]
        self.assertEqual(anchor["locator"], "lines 1-1")
        self.assertEqual(anchor["sha256"], sha(self.project / a["source"]["path"]))
        wrong_line = copy.deepcopy(card)
        wrong_line["fields"]["baseline"][0]["evidence"][0].update(start_line=2, end_line=2)
        with self.assertRaisesRegex(ValueError, "absent"):
            workbench.validate_card(self.project, a, wrong_line)
        fabricated = copy.deepcopy(card)
        fabricated["fields"]["baseline"][0]["evidence"][0]["quote"] = "Invented favorable result."
        with self.assertRaisesRegex(ValueError, "absent"):
            workbench.validate_card(self.project, a, fabricated)
        inference = copy.deepcopy(card)
        inference["fields"]["baseline"][0]["kind"] = "model_inference"
        with self.assertRaisesRegex(ValueError, "boundary"):
            workbench.validate_card(self.project, a, inference)
        inference["fields"]["baseline"][0]["inference_boundary"] = "This interpretation is not established by the source."
        self.assertEqual(workbench.validate_card(self.project, a, inference)["fields"]["baseline"][0]["kind"], "model_inference")

    def test_author_claim_cannot_be_laundered_through_a_note(self):
        a = self.add_paper("a", "The actual source discusses gain.")
        note = self.source("literature/notes/a.md", "The note asserts a large effect.")
        a["notes"] = [note]
        card = {"schema_version": "1.0", "paper_id": "a", "fields": {"findings": [{
            "text": "Large effect", "kind": "author_claim", "evidence": [{**note,
            "start_line": 1, "end_line": 1, "quote": "The note asserts a large effect."}]}]}}
        with self.assertRaisesRegex(ValueError, "author claims"):
            workbench.validate_card(self.project, a, card)

    def test_typed_graph_needs_both_actual_evidence_endpoints(self):
        a = self.add_paper("a", "Synthetic study reports a positive association.")
        b = self.add_paper("b", "Synthetic study reports a negative association.")
        self.build()
        self.assertEqual(self.output("graph.json")["edges"], [])
        edge = {"id": "contrast", "from": "a", "to": "b", "type": "contradicts",
                "kind": "model_inference", "rationale": "The located statements differ in direction.",
                "inference_boundary": "Comparability is not established.", "evidence": [
                    {"paper_id": "a", **self.anchor(a, "positive association")},
                    {"paper_id": "b", **self.anchor(b, "negative association")} ]}
        self.config["relationships"] = [edge]
        self.build()
        graph = self.output("graph.json")
        self.assertEqual(graph["edges"][0]["type"], "contradicts")
        self.assertFalse(graph["edges"][0]["semantic_verification"])
        edge["evidence"].pop()
        self.assertEqual(self.build()["status"], "blocked")
        self.assertEqual(self.output("graph.json")["edges"], [])
        edge["evidence"].append({"paper_id": "b", **self.anchor(b, "a fabricated contrary quote")})
        self.assertEqual(self.build()["status"], "blocked")
        self.assertEqual(self.output("graph.json")["edges"], [])

    def test_topic_scoped_paper_mappings_and_comparison_packet(self):
        a = self.add_paper("a", "Baseline gain classifier.", topic="topic-a")
        self.add_paper("b", "Baseline gain classifier.", topic="topic-b")
        self.card(a, field="baseline")
        state = {"stage": "G1", "approved": False}
        write(self.project / "state/run.json", state)
        self.build()
        with self.assertRaisesRegex(ValueError, "topic scope"):
            workbench.search(self.project, "gain", paper_id="P01")
        hits = workbench.search(self.project, "gain", topic_id="topic-a", paper_id="P01")
        self.assertEqual({h["paper_id"] for h in hits["results"]}, {"a"})
        packet = workbench.comparison_packet(self.project, ["a", "b"], question="Which baseline is justified?")
        self.assertEqual(packet["rows"][0]["fields"]["baseline"][0]["kind"], "author_claim")
        self.assertEqual(packet["rows"][0]["experiment_planning_gaps"], ["splits", "metrics", "ablations"])
        self.assertEqual(set(packet["rows"][1]["unknown_fields"]), set(workbench.FIELDS))
        self.assertFalse(packet["comparability_verified"])
        self.assertFalse(packet["experiment_executed"])
        self.assertEqual(read(self.project / "state/run.json"), state)
        self.assertTrue(workbench.search(self.project, "gain")["results"])

    def test_html_escapes_titles_claims_quotes_and_relative_link_targets(self):
        dangerous = '<script>alert("unsafe")</script> & quoted evidence'
        a = self.add_paper("a", dangerous, title='<img src=x onerror="alert(1)">')
        source = self.source("evidence/sources/a note's & source.txt", dangerous)
        a["source"] = source
        a["url"] = "https://example.test/original?x=%22%3E"
        self.card(a)
        self.build()
        page = (self.project / workbench.OUTPUT / "index.html").read_text(encoding="utf-8")
        # The only executable script is the pinned, CSP-hashed search viewer;
        # source text must not create a second script or active image element.
        import re
        from scripts import literature_browser
        scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
        self.assertEqual(scripts, [literature_browser.SCRIPT])
        self.assertIn("script-src 'sha256-" + literature_browser.script_hash(), page)
        self.assertNotIn('<img src=x', page)
        self.assertIn(html.escape(dangerous, quote=True), page)
        self.assertIn("../../evidence/sources/a%20note%27s%20%26%20source.txt", page)
        self.assertIn("https://example.test/original?x=%22%3E", page)
        self.assertIn("Content-Security-Policy", page)
        a["url"] = "javascript:alert(1)"
        self.assertEqual(self.build()["status"], "blocked")
        page = (self.project / workbench.OUTPUT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('href="javascript:', page)

    def test_safe_project_boundaries_and_pending_discovery(self):
        for relative in ("../outside.txt", "C:/outside.txt", "evidence\\sources\\a.txt", "state/run.json", "evidence/private/a.txt"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                workbench._path(self.project, relative, exists=False, corpus=True)
        self.source("literature/notes/gain.md", "A personal gain reading note.")
        result = workbench.build(self.project)
        self.assertEqual(result["paper_count"], 1)
        paper = self.output("library.json")["papers"][0]
        self.assertEqual(paper["paper_ids"], [])
        self.assertIsNone(paper["topic_id"])
        self.assertEqual(paper["card"]["status"], "pending_analysis")
        self.assertTrue(paper["discovered_pending"])
        with self.assertRaises(ValueError):
            workbench.build(self.project, output_dir="state/workbench")

    def test_all_ten_fields_unknown_are_not_fabricated_or_verified(self):
        a = self.add_paper("a", "An authorized source with limited available detail.")
        card = {"schema_version": "1.0", "paper_id": "a", "full_text_review_scope": "provided_full_text",
                "fields": {name: [] for name in workbench.FIELDS}}
        checked = workbench.validate_card(self.project, a, card)
        self.assertEqual(len(checked["unknown_fields"]), len(workbench.FIELDS))
        self.assertEqual(checked["full_text_review_scope"], "provided_full_text")
        self.assertEqual(checked["status"], "pending_analysis")
        self.assertFalse(checked["human_full_text_reading_verified"])

    def test_multi_paper_itinerary_retains_counterevidence_and_unknowns(self):
        self.add_paper("positive", "Gain correction improves this synthetic benchmark.")
        adverse = self.add_paper("adverse", "Gain correction fails in this synthetic boundary case.")
        self.card(adverse, field="counterevidence")
        self.build()
        plan = workbench.itinerary(self.project, "When does gain correction fail?", topic_id="topic-a", paper_id="P01")
        self.assertEqual({step["paper_id"] for step in plan["steps"]}, {"positive", "adverse"})
        self.assertEqual(plan["steps"][0]["paper_id"], "adverse")
        self.assertTrue(plan["steps"][0]["start_here"][0]["locator"])
        self.assertIn("splits", plan["steps"][0]["unknown_fields"])
        self.assertFalse(plan["gate_approved"])


def _minimal_pdf(text):
    """Actual one-page PDF bytes for binding tests; no extraction is performed."""
    stream = f"BT /F1 10 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    data, offsets = b"%PDF-1.4\n", [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(data)
    data += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        data += f"{offset:010d} 00000 n \n".encode()
    return data + f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


class NativeReaderTests(WorkbenchFixture):
    def fixture(self):
        quote = "Synthetic source reports a scalar gain control."
        pdf = self.project / "evidence/sources/native.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(_minimal_pdf(quote))
        source = {"path": "evidence/sources/native.pdf", "sha256": sha(pdf)}
        reader = self.source("evidence/readers/native.md", "# Reader\n\n## PDF page 1\n\n### Original extracted text\n\n" + quote +
                             "\n\n### Chinese reading translation\n\n[Translation pending]\n")
        mapping_path = self.project / "evidence/readers/native.source-map.json"
        write(mapping_path, {"source_sha256": source["sha256"], "reader_sha256": reader["sha256"],
                             "source_blocks": [{"pdf_page": 1, "extracted_text_sha256": hashlib.sha256(quote.encode()).hexdigest()}]})
        receipt_path = self.project / "evidence/readers/native.reader.json"
        write(receipt_path, {"pdf_sha256": source["sha256"], "reader_sha256": reader["sha256"],
                             "reader_implementation_sha256": sha(Path(paper_reader.__file__)),
                             "page_count": 1, "selected_pages": [1], "page_images": [],
                             "source_map": {"path": "evidence/readers/native.source-map.json", "sha256": sha(mapping_path)}})
        record(self.project, [self.project / reader["path"], receipt_path, mapping_path], "synthetic-fixture")
        paper = {"id": "native", "title": "Synthetic native reader fixture", "source": source, "reader": reader}
        self.config["papers"] = [paper]
        return paper, quote, receipt_path, mapping_path

    def test_pdf_anchor_binds_original_page_not_translation(self):
        paper, quote, _, _ = self.fixture()
        anchor = {**paper["reader"], "start_line": 7, "end_line": 7, "quote": quote, "pdf_page": 1}
        validated = workbench.validate_anchor(self.project, paper, anchor)
        self.assertEqual(validated["locator"], "PDF page 1; reader lines 7-7")
        self.assertFalse(validated["semantic_verification"])
        with self.assertRaisesRegex(ValueError, "exact PDF page"):
            workbench.validate_anchor(self.project, paper, {**anchor, "pdf_page": 2})
        with self.assertRaisesRegex(ValueError, "original text"):
            workbench.validate_anchor(self.project, paper, {**anchor, "start_line": 11,
                                      "end_line": 11, "quote": "[Translation pending]"})
        self.build()
        page = (self.project / workbench.OUTPUT / "index.html").read_text(encoding="utf-8")
        self.assertIn("../../evidence/sources/native.pdf", page)

    def test_receipt_map_and_source_hash_changes_block_reader_reuse(self):
        paper, _, _, mapping = self.fixture()
        self.build()
        self.assertEqual(self.build()["reused_papers"], ["native"])
        value = read(mapping)
        value["source_sha256"] = "0" * 64
        write(mapping, value)
        self.assertEqual(self.build()["status"], "blocked")
        with self.assertRaisesRegex(ValueError, "stale input hash"):
            workbench.validate_card(self.project, paper, {"schema_version": "1.0", "paper_id": "native", "fields": {}})

    def test_untracked_native_receipt_is_not_accepted_as_controlled(self):
        self.fixture()
        registry = self.project / "state/output-provenance.json"
        value = read(registry)
        value["files"].pop("evidence/readers/native.reader.json")
        write(registry, value)
        result = self.build()
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("controlled" in error["error"] for error in result["errors"]))

    def raw_fixture(self):
        paper, text, _, _ = self.fixture()
        raw = self.project / "data/raw/literature/sources/native.pdf"
        raw.parent.mkdir(parents=True)
        raw.write_bytes((self.project / paper["source"]["path"]).read_bytes())
        paper["source"] = {"path": raw.relative_to(self.project).as_posix(), "sha256": sha(raw)}
        manifest = "data/manifests/native.json"
        write(self.project / manifest, {"license": {"redistribution_allowed": True},
                                      "download": {"sha256": sha(raw)}})
        write(self.project / "state/data-authorizations.json", {"manifests": {manifest: {
            "sha256": sha(self.project / manifest), "actor": "Synthetic fixture owner",
            "cloud_use_confirmed": True}}})
        paper["manifest"] = manifest
        return paper, raw, text

    def test_raw_original_requires_authority_and_never_becomes_text(self):
        paper, raw, text = self.raw_fixture()
        files = workbench._Files(self.project)
        bound = workbench.source_binding(self.project, paper["source"], manifest=paper["manifest"], files=files)
        self.assertEqual(bound["sha256"], sha(raw))
        with self.assertRaisesRegex(ValueError, "binary PDFs"):
            files.text(paper["source"]["path"])
        with self.assertRaises(ValueError):
            files.binding(paper["source"])
        self.build()
        index = self.output("search-index.json")
        self.assertTrue(any(text in d["text"] for d in index["documents"]))
        self.assertTrue(all(d["path"] == paper["reader"]["path"] for d in index["documents"]))
        self.assertNotIn("%PDF-", json.dumps(index))
        page = (self.project / workbench.OUTPUT / "index.html").read_text(encoding="utf-8")
        self.assertIn("../../data/raw/literature/sources/native.pdf", page)
        authority = self.project / "state/data-authorizations.json"
        grant = read(authority)
        grant["manifests"][paper["manifest"]]["cloud_use_confirmed"] = False
        write(authority, grant)
        with self.assertRaisesRegex(ValueError, "Owner-reviewed"):
            workbench.search(self.project, "scalar gain")
        self.assertEqual(self.build()["status"], "blocked")

    def test_absent_raw_restore_or_unreviewed_manifest_blocks(self):
        paper, raw, _ = self.raw_fixture()
        (self.project / "state/data-authorizations.json").unlink()
        with self.assertRaisesRegex(ValueError, "Owner-reviewed"):
            workbench.source_binding(self.project, paper["source"], manifest=paper["manifest"])
        raw.unlink()
        self.assertEqual(self.build()["status"], "blocked")

    def test_text_sources_cannot_be_replaced_by_an_unrelated_pdf_reader(self):
        native, _, _, _ = self.fixture()
        paper = self.add_paper("text", "Independent actual text source.")
        paper["reader"] = native["reader"]
        with self.assertRaisesRegex(ValueError, "original PDF"):
            workbench.validate_card(self.project, paper, {"schema_version": "1.0", "paper_id": "text", "fields": {}})


if __name__ == "__main__":
    unittest.main()
