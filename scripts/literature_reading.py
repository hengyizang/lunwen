"""Source-bound sentence navigation and question-scoped reading coverage.

These are deterministic reading aids, not human-reading certifications. Existing
workbench rights, source hashes and append-only progress remain the authorities.
No model, network request, embedding service or new approval system is used.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import tempfile
import unicodedata
from urllib.parse import quote as urlquote
import xml.etree.ElementTree as ET

from scripts import literature_reasoning as reasoning, literature_workbench as wb
from scripts.research_artifacts import path_in, read, record, sha, write


OUTPUT = "reports/literature-reading"
DIMENSIONS = ("metadata", "abstract", "methods", "results", "appendix", "figures")
SECTION_NAMES = {
    "abstract": ("abstract",),
    "methods": ("methods", "methodology", "materials and methods", "experimental setup"),
    "results": ("results", "results and discussion", "experiments", "evaluation"),
    "appendix": ("appendix", "appendices", "supplement", "supplementary"),
}
FIELD_DIMENSIONS = {"methods": ("methods", "protocols", "splits", "statistics"),
                    "results": ("findings",), "abstract": (), "appendix": ()}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def _paper(project, paper_id, output_dir):
    wb._id(paper_id, "library paper ID")
    library, _, manifest = wb._snapshot(project, output_dir)
    paper = next((p for p in library["papers"] if p["id"] == paper_id), None)
    if paper is None or paper.get("status") != "current":
        raise ValueError("sentence index needs a current registered library paper")
    return paper, manifest


def _original_ranges(project, paper):
    binding = paper.get("reader") or paper["source"]
    if paper.get("source_scope") == "metadata_only":
        return binding, [], []
    if Path(binding["path"]).suffix.lower() == ".pdf":
        raise ValueError("sentence index requires an authorized original-text PDF reader")
    lines = wb._Files(project).text(binding["path"]).splitlines()
    if paper.get("reader"):
        ranges = [(int(page), bounds[0], bounds[1])
                  for page, bounds in paper["reader"]["page_ranges"].items()]
    else:
        ranges = [(None, 1, len(lines))] if lines else []
    return binding, lines, sorted(ranges, key=lambda item: item[1])


def _sentence_rows(project, paper):
    binding, lines, ranges = _original_ranges(project, paper)
    sentences, omitted = [], 0
    for page, first, last in ranges:
        original = "\n".join(lines[first - 1:last])
        # Mechanical sentence candidates preserve exact bytes and line offsets.
        # Abbreviations/formula punctuation may split candidates; no linguistic
        # completeness or semantic entailment is inferred from segmentation.
        for match in re.finditer(r"\S[\s\S]*?(?:[.!?。！？](?=\s|$)|\Z)", original):
            quote = match.group().rstrip()
            if not quote:
                continue
            if len(quote) > 4000:
                omitted += 1
                continue
            start = first + original.count("\n", 0, match.start())
            end = start + quote.count("\n")
            identity = {"source_sha256": paper["source"]["sha256"], "pdf_page": page,
                        "original_offset": match.start(), "quote": quote}
            sentences.append({"sentence_id": "sentence-" + _digest(identity)[:24],
                "paper_id": paper["id"], "path": binding["path"], "sha256": binding["sha256"],
                "start_line": start, "end_line": end, "quote": quote, "pdf_page": page,
                "page_label": None, "page_label_source": None,
                "bbox": None, "rects": [], "position_status": "not_requested",
                "semantic_support_verified": False})
    if len(sentences) > 30000:
        raise ValueError("sentence index exceeds 30000 candidates; narrow the reader scope")
    return sentences, omitted


def _tokens(text):
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold(), re.UNICODE)


def _positioned_pages(payload):
    """Parse actual Poppler word boxes, retaining physical page order."""
    if len(payload) > 12_000_000 or b"<!ENTITY" in payload.upper():
        raise ValueError("positioned PDF text exceeds bounds or contains entities")
    root = ET.fromstring(payload)
    pages = []
    for page in (node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "page"):
        width, height = float(page.attrib["width"]), float(page.attrib["height"])
        if not all(math.isfinite(v) and v > 0 for v in (width, height)):
            raise ValueError("invalid positioned PDF page dimensions")
        words = []
        for node in page.iter():
            if node.tag.rsplit("}", 1)[-1] != "word":
                continue
            box = [float(node.attrib[k]) for k in ("xMin", "yMin", "xMax", "yMax")]
            if (not all(math.isfinite(v) for v in box) or not 0 <= box[0] <= box[2] <= width + 0.1
                    or not 0 <= box[1] <= box[3] <= height + 0.1):
                raise ValueError("invalid positioned PDF word box")
            for token in _tokens("".join(node.itertext())):
                words.append({"token": token, "bbox": box})
        pages.append({"width": width, "height": height, "words": words})
    if not 1 <= len(pages) <= 100:
        raise ValueError("PDF positioning is bounded to 1..100 physical pages")
    return pages


def _locate_sentence(sentence, page):
    wanted = _tokens(sentence["quote"])
    actual = [word["token"] for word in page["words"]]
    matches = [start for start in range(len(actual) - len(wanted) + 1)
               if wanted and actual[start:start + len(wanted)] == wanted]
    result = {**sentence, "position_status": "not_found" if not matches else "ambiguous",
              "page_size": [page["width"], page["height"]], "coordinate_system": "cropbox_points_top_left"}
    if len(matches) != 1:
        return result
    boxes = [word["bbox"] for word in page["words"][matches[0]:matches[0] + len(wanted)]]
    rects = []
    for box in boxes:
        if box not in rects:
            rects.append(box)
    result.update(position_status="located_unique_normalized_word_sequence", rects=rects,
                  bbox=[min(b[0] for b in rects), min(b[1] for b in rects),
                        max(b[2] for b in rects), max(b[3] for b in rects)])
    return result


def _pdf_positions(project, paper, sentences):
    if not paper.get("reader") or Path(paper["source"]["path"]).suffix.lower() != ".pdf":
        raise ValueError("PDF positioning requires a bound native PDF reader")
    if os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1" and os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("PDF positioning executes only on the authorized cloud runner")
    program = shutil.which("pdftotext")
    if program is None:
        raise RuntimeError("explicit PDF positioning requires the existing Poppler pdftotext tool")
    from pypdf import PdfReader
    pdf = path_in(project, paper["source"]["path"])
    reader = PdfReader(str(pdf), strict=False)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
        raise ValueError("PDF positioning requires an unencrypted PDF of at most 100 pages")
    with tempfile.TemporaryDirectory(prefix="literature-positions-") as temporary:
        target = Path(temporary) / "positions.xhtml"
        subprocess.run([program, "-bbox-layout", "-cropbox", str(pdf), str(target)],
                       check=True, capture_output=True, timeout=90)
        if target.stat().st_size > 12_000_000:
            raise ValueError("positioned PDF text exceeds 12 MB")
        pages = _positioned_pages(target.read_bytes())
    if len(pages) != len(reader.pages):
        raise ValueError("positioned PDF physical-page count differs from the bound original")
    labels = reader.page_labels if "/PageLabels" in reader.trailer["/Root"] else None
    located = []
    for sentence in sentences:
        page_no = sentence["pdf_page"]
        if type(page_no) is not int or not 1 <= page_no <= len(pages):
            raise ValueError("sentence physical PDF page does not exist")
        row = _locate_sentence(sentence, pages[page_no - 1])
        if labels:
            row.update(page_label=str(labels[page_no - 1]), page_label_source="PDF PageLabels metadata")
        located.append(row)
    return located


def _origin_current(project, path):
    from scripts.output_provenance import current_origin
    origin = current_origin(project, path)
    return (origin.get("status") == "tracked" and origin.get("family") == "other"
            and origin.get("model") == "scripts/literature_reading.py")


def _save(project, relative, value, page):
    target = path_in(project, relative, exists=False)
    page_path = target.with_suffix(".html")
    for existing in (target, page_path):
        if existing.exists() and not _origin_current(project, existing):
            raise ValueError("derived reading output changed outside its controlled builder")
    write(target, value)
    page_path.write_text(page, encoding="utf-8")
    record(project, [target, page_path], "scripts/literature_reading.py")
    return {"report_path": relative, "html_path": page_path.relative_to(project).as_posix()}


def _html_document(title, body):
    return ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>" + html.escape(title) + "</title><style>body{max-width:72rem;margin:2rem auto;"
            "font:16px/1.55 system-ui;padding:0 1rem}li{margin:1rem 0}pre{white-space:pre-wrap}"
            ":target{background:#fff3b0}small{overflow-wrap:anywhere}table{border-collapse:collapse}"
            "td,th{border:1px solid #ccc;padding:.5rem;text-align:left}</style><h1>" + html.escape(title) +
            "</h1><p>Source navigation and attributed reading records; semantic support and human full-text "
            "reading are not certified.</p>" + body + "</html>")


def _index_html(project, relative, report):
    directory = posixpath.dirname(relative)
    body = "<p>Source SHA-256: <code>" + report["source"]["sha256"] + "</code></p><ol>"
    for sentence in report["sentences"]:
        page = sentence["pdf_page"]
        href = urlquote(posixpath.relpath(report["source"]["path"], directory), safe="/")
        if page is not None:
            href += "#page=" + str(page)
        label = "PDF page " + str(page) if page is not None else "Original source"
        if sentence["page_label"] is not None:
            label += " (PDF page label " + sentence["page_label"] + ")"
        body += ('<li id="' + sentence["sentence_id"] + '"><a href="#' + sentence["sentence_id"] +
                 '">Sentence permalink</a> · <a href="' + html.escape(href, quote=True) + '">' +
                 html.escape(label) + "</a><pre>" + html.escape(sentence["quote"]) + "</pre><small>" +
                 html.escape(sentence["path"]) + " · lines " + str(sentence["start_line"]) + "–" +
                 str(sentence["end_line"]) + " · " + html.escape(sentence["position_status"]) + "</small>")
        if sentence["bbox"] is not None:
            body += "<p>PDF crop-box coordinates: " + html.escape(json.dumps(sentence["bbox"])) + "</p>"
        body += "</li>"
    if not report["sentences"]:
        body += "<li>No original-text sentences indexed. Obtain an authorized full-text reader.</li>"
    return _html_document("Sentence evidence: " + report["paper_id"], body + "</ol>")


def build_index(project: Path, paper_id: str, *, output_dir=None, locate_pdf=False) -> dict:
    """Build/reuse an original-text sentence index after current source validation.

    ``output_dir`` selects the existing workbench snapshot, not a new corpus.
    PDF box extraction is explicit and cloud-only; the free default uses the
    native original-text map and makes no PDF-coordinate claim.
    """
    project = Path(project).resolve()
    if type(locate_pdf) is not bool:
        raise ValueError("locate_pdf must be an explicit boolean")
    paper, _ = _paper(project, paper_id, output_dir)
    binding = paper.get("reader") or paper["source"]
    dependencies = [paper["source"], binding]
    if paper.get("reader"):
        dependencies += [paper["reader"]["receipt"], paper["reader"]["source_map"]]
    fingerprint = _digest({"paper_id": paper_id, "source_scope": paper.get("source_scope"),
        "inputs": dependencies, "locate_pdf": locate_pdf, "implementation_sha256": sha(Path(__file__))})
    relative = OUTPUT + "/" + paper_id + "/index.json"
    target = path_in(project, relative, exists=False)
    if target.exists() and _origin_current(project, target) and _origin_current(project, target.with_suffix(".html")):
        existing = read(target)
        if existing.get("fingerprint") == fingerprint:
            return {**existing, "cache_hit": True, "report_path": relative,
                    "html_path": target.with_suffix(".html").relative_to(project).as_posix()}
    sentences, omitted = _sentence_rows(project, paper)
    if locate_pdf:
        sentences = _pdf_positions(project, paper, sentences)
    report = {"schema_version": "1.0", "kind": "source_bound_sentence_index", "paper_id": paper_id,
        "source": paper["source"], "reader": binding, "source_scope": paper.get("source_scope"),
        "inputs": dependencies, "fingerprint": fingerprint, "sentences": sentences,
        "segmentation": "mechanical_punctuation_candidates_not_linguistic_verification",
        "overlong_segments_not_indexed": omitted, "locate_pdf": locate_pdf,
        "source_positions_verified": locate_pdf and all(s["bbox"] is not None for s in sentences) and bool(sentences),
        "human_full_text_reading_verified": False, "semantic_support_verified": False,
        "retrieval_completeness_verified": False, "model_call_made": False,
        "implementation_sha256": sha(Path(__file__))}
    paths = _save(project, relative, report, _index_html(project, relative, report))
    return {**report, **paths, "cache_hit": False}


def validate_sentence(project: Path, paper_id: str, anchor: dict, *, output_dir=None, locate_pdf=False) -> dict:
    """Resolve an exact current sentence; identity/quotation does not entail a claim."""
    if not isinstance(anchor, dict):
        raise ValueError("sentence anchor must be an object")
    required = {"sentence_id", "path", "sha256", "start_line", "end_line", "quote", "pdf_page"}
    if not required <= set(anchor):
        raise ValueError("sentence anchor requires its exact identity, source, lines, quote and physical page")
    index = build_index(project, paper_id, output_dir=output_dir, locate_pdf=locate_pdf)
    sentence = next((s for s in index["sentences"] if s["sentence_id"] == anchor["sentence_id"]), None)
    if sentence is None or any(anchor[k] != sentence[k] or type(anchor[k]) is not type(sentence[k]) for k in required):
        raise ValueError("sentence quote, hash, lines or physical PDF page differs from the current original")
    for key in ("bbox", "rects", "page_label"):
        if key in anchor and anchor[key] is not None:
            if not locate_pdf or anchor[key] != sentence[key]:
                raise ValueError("sentence PDF coordinates/page labels need actual current PDF positioning")
    return {**sentence, "index_path": index["report_path"], "html_path": index["html_path"],
            "href": index["html_path"] + "#" + sentence["sentence_id"]}


def _section_dimension(title):
    title = re.sub(r"^#{1,6}\s+", "", title.strip()).casefold()
    title = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", title).strip()
    for dimension, names in SECTION_NAMES.items():
        if any(title == name or (dimension == "appendix" and title.startswith(name + " ")) for name in names):
            return dimension
    return None


def _coverage_sections(project, paper):
    """Add explicit supported headings within original ranges only.

    Native PDF extractions commonly contain unnumbered plain-text headings; the
    reasoning reader's generic section recognizer intentionally has a smaller
    vocabulary. Boundary detection remains a structural hint, not interpretation.
    """
    existing = reasoning._section_rows(project, paper)
    if not paper.get("reader") and Path(paper["source"]["path"]).suffix.lower() == ".pdf":
        return existing
    binding, lines, ranges = _original_ranges(project, paper)
    result = []
    for page, first, last in ranges:
        titles = {s["start_line"]: s["title"] for s in existing if first <= s["start_line"] <= last}
        for number in range(first, last + 1):
            if _section_dimension(lines[number - 1]) is not None:
                titles[number] = lines[number - 1].strip()
        starts = sorted(titles)
        for index, start in enumerate(starts):
            result.append({"title": titles[start], "path": binding["path"], "sha256": binding["sha256"],
                "start_line": start, "end_line": starts[index + 1] - 1 if index + 1 < len(starts) else last,
                "pdf_page": page, "structure_detection": "original_heading_not_semantic_verification"})
    return result


def _caption_location(project, paper, occurrence):
    """Bind one unique whitespace-normalized caption to original reader lines."""
    caption = occurrence.get("caption")
    if not isinstance(caption, str) or not caption.strip():
        return {"caption_attribution": "not_attributable", "caption_match_status": "missing_caption"}
    if not paper.get("reader"):
        return {"caption_attribution": "not_attributable", "caption_match_status": "original_reader_unavailable"}
    binding, lines, ranges = _original_ranges(project, paper)
    scope = next((r for r in ranges if r[0] == occurrence["pdf_page"]), None)
    if scope is None:
        return {"caption_attribution": "not_attributable", "caption_match_status": "original_reader_page_unavailable"}
    page, first, last = scope
    original = "\n".join(lines[first - 1:last])
    normalized, offsets = [], []
    for token in re.finditer(r"\S+", original):
        if normalized:
            normalized.append(" ")
            offsets.append(token.start())
        normalized.extend(token.group())
        offsets.extend(range(token.start(), token.end()))
    wanted = " ".join(caption.split())
    matches = list(re.finditer(r"(?<!\S)" + re.escape(wanted) + r"(?!\S)", "".join(normalized)))
    if len(matches) != 1:
        return {"caption_attribution": "not_attributable", "caption_match_status": (
            "caption_not_found_in_original_reader" if not matches else "ambiguous_original_caption")}
    start, end = offsets[matches[0].start()], offsets[matches[0].end() - 1] + 1
    return {"path": binding["path"], "sha256": binding["sha256"], "pdf_page": page,
        "start_line": first + original.count("\n", 0, start),
        "end_line": first + original.count("\n", 0, end), "quote": original[start:end],
        "basis": "matched_original_figure_caption", "caption_attribution": "exact_original_reader_caption",
        "caption_match_status": "unique_whitespace_normalized_original_caption",
        "spatial_association_verified": False, "visual_understanding_verified": False}


def _dimension_locations(project, paper):
    binding = paper.get("reader") or paper["source"]
    locations = {d: [] for d in DIMENSIONS}
    locations["metadata"] = [{"path": paper["source"]["path"], "sha256": paper["source"]["sha256"],
                              "locator": "registered source identity", "basis": "metadata_identity"}]
    for section in _coverage_sections(project, paper):
        dimension = _section_dimension(section["title"])
        if dimension is not None:
            locations[dimension].append({**section, "basis": "original_source_heading"})
    for dimension, fields in FIELD_DIMENSIONS.items():
        for field in fields:
            for statement in paper.get("card", {}).get("fields", {}).get(field, []):
                for anchor in statement["evidence"]:
                    if anchor["path"] == binding["path"]:
                        locations[dimension].append({**anchor, "basis": "located_card_field", "field": field})
    for asset in (paper.get("figure_manifest") or {}).get("assets", []):
        for occurrence in asset.get("occurrences", []):
            locations["figures"].append({"path": paper["source"]["path"], "sha256": paper["source"]["sha256"],
                "pdf_page": occurrence["pdf_page"], "asset": {"path": asset["path"], "sha256": asset["sha256"]},
                "basis": "extracted_figure_region_not_visual_review", **_caption_location(project, paper, occurrence)})
    return locations


def _overlaps(anchor, location):
    if anchor["path"] != location["path"] or anchor["sha256"] != location["sha256"]:
        return False
    if "start_line" not in location:
        return False
    if (location.get("basis") == "matched_original_figure_caption"
            and " ".join(location["quote"].split()) not in " ".join(anchor.get("quote", "").split())):
        return False
    return (location["start_line"] <= anchor["end_line"] and
            anchor["start_line"] <= location["end_line"] and
            (location.get("pdf_page") is None or location["pdf_page"] == anchor.get("pdf_page")))


def _coverage_html(report):
    body = "<p>Question: " + html.escape(report["question"]) + "</p><table><tr><th>Source</th><th>Dimension</th><th>State</th><th>Next evidence</th></tr>"
    for paper in report["papers"]:
        for row in paper["dimensions"]:
            body += "<tr>" + "".join("<td>" + html.escape(value) + "</td>" for value in
                (paper["paper_id"], row["dimension"], row["status"], row["next_action"])) + "</tr>"
    return _html_document("Question-scoped reading coverage", body + "</table>")


def coverage(project: Path, request: dict, *, output_dir=None) -> dict:
    """Summarize existing source cards and controlled question-bound answers.

    No new reading event is created. An attributed answer remains pending semantic
    review; an extracted page, heading or figure never counts as human reading.
    """
    project = Path(project).resolve()
    if not isinstance(request, dict) or set(request) - {"question", "paper_ids", "dimensions", "topic_id", "paper_id", "limit"}:
        raise ValueError("unsupported reading coverage request fields")
    question = wb._text(request.get("question"), "coverage question", 4000)
    dimensions = request.get("dimensions", list(DIMENSIONS))
    if (not isinstance(dimensions, list) or not dimensions or any(d not in DIMENSIONS for d in dimensions)
            or len(set(dimensions)) != len(dimensions)):
        raise ValueError("coverage dimensions must be distinct supported reading dimensions")
    library, _, _ = wb._snapshot(project, output_dir)
    papers = {p["id"]: p for p in library["papers"] if p.get("status") == "current"}
    explicit = request.get("paper_ids")
    if explicit is not None and (not isinstance(explicit, list) or not 1 <= len(explicit) <= 30
            or any(not isinstance(i, str) for i in explicit) or len(set(explicit)) != len(explicit)
            or any(i not in papers for i in explicit)):
        raise ValueError("coverage papers must be distinct current sources within the scoped reading plan")
    plan = reasoning.itinerary(project, question, topic_id=request.get("topic_id"), paper_id=request.get("paper_id"),
                               limit=request.get("limit", 30), output_dir=output_dir)
    selected = request.get("paper_ids", plan["selected_paper_ids"])
    if (not isinstance(selected, list) or not 1 <= len(selected) <= 30 or any(not isinstance(i, str) for i in selected)
            or len(set(selected)) != len(selected) or any(i not in plan["selected_paper_ids"] for i in selected)):
        raise ValueError("coverage papers must be distinct current sources within the scoped reading plan")
    rows, reused, missing = [], [], []
    for paper_id in selected:
        paper = papers[paper_id]
        locations = _dimension_locations(project, paper)
        answers = [s["recorded_answer"] for s in plan["steps"] if s["paper_id"] == paper_id
                   and s["status"] == "answer_recorded_pending_semantic_review"]
        dimension_rows = []
        for dimension in dimensions:
            evidence, seen = [], set()
            for answer in answers:
                for anchor in answer["evidence"]:
                    if anchor["paper_id"] != paper_id or not any(_overlaps(anchor, loc) for loc in locations[dimension]):
                        continue
                    key = _digest({k: anchor.get(k) for k in ("paper_id", "path", "sha256", "start_line", "end_line", "quote", "pdf_page")})
                    if key in seen:
                        continue
                    seen.add(key)
                    evidence.append({"event_id": answer["event_id"], "kind": answer["kind"],
                        "recorded_by": answer["recorded_by"], "outcome": answer["outcome"], "anchor": anchor})
            status = ("attributed_answer_pending_semantic_review" if evidence else
                      "located_not_read" if locations[dimension] else "not_located")
            next_action = ("Reuse the exact located evidence; resolve the recorded uncertainty before another read."
                           if evidence else "Read the located original material and record a question-bound answer."
                           if locations[dimension] else "Locate authorized original " + dimension + " evidence; do not infer absence.")
            if dimension == "metadata":
                status, next_action = "metadata_available_not_full_text_read", "Use metadata for discovery; inspect original scientific evidence for this question."
            if dimension == "figures" and locations[dimension]:
                next_action = "Inspect the actual figure/table region and its caption; extraction is not visual understanding."
            dimension_rows.append({"dimension": dimension, "status": status, "locations": locations[dimension],
                "reusable_evidence": evidence, "next_action": next_action,
                "human_full_text_reading_verified": False, "semantic_support_verified": False})
            reused += [{"paper_id": paper_id, "dimension": dimension, **e} for e in evidence]
            if not evidence and dimension != "metadata":
                missing.append({"paper_id": paper_id, "dimension": dimension, "action": next_action})
        rows.append({"paper_id": paper_id, "title": paper["title"], "source": paper["source"],
                     "source_scope": paper.get("source_scope"), "dimensions": dimension_rows})
    question_hash = _digest(question)
    scope_hash = _digest({"paper_ids": selected, "dimensions": dimensions,
                          "topic_id": request.get("topic_id"), "paper_id": request.get("paper_id")})
    relative = OUTPUT + "/coverage-" + question_hash[:16] + "-" + scope_hash[:12] + ".json"
    report = {"schema_version": "1.0", "kind": "question_scoped_reading_coverage", "question": question,
        "question_sha256": question_hash, "coverage_scope_sha256": scope_hash,
        "topic_id": request.get("topic_id"), "paper_id": request.get("paper_id"),
        "papers": rows, "reusable_evidence": reused, "missing_evidence": missing,
        "progress_inputs": plan["inputs"], "read_counts_prove_coverage": False,
        "versions_not_substituted": True, "human_full_text_reading_verified": False,
        "semantic_support_verified": False, "scientific_completion_verified": False,
        "model_call_made": False, "implementation_sha256": sha(Path(__file__))}
    return {**report, **_save(project, relative, report, _coverage_html(report))}
