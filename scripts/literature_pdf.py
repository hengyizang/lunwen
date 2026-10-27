"""Source-bound cloud PDF views and annotated copies, preserving the original.

Raster/coordinate navigation and optional OCR are reading aids. OCR is never
silently substituted for the native original-text evidence authority.
"""
from __future__ import annotations

import csv
import html
import io
import math
import os
from pathlib import Path
import posixpath
import shutil
import subprocess
import tempfile
from urllib.parse import quote

from scripts import literature_reading as reading, literature_workbench as wb
from scripts.research_artifacts import path_in, read, record, sha, write

REQUEST = "program/literature-pdf.json"
OUTPUT = "reports/literature-pdf"
MODULE = "scripts/literature_pdf.py"


def _cloud():
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise ValueError("PDF viewing, annotation and OCR execute only on the authorized cloud runner")


def _request(project, request_path):
    if not isinstance(request_path, str) or not request_path.startswith("program/") or not request_path.endswith(".json"):
        raise ValueError("PDF request must be a JSON file under program/")
    target = path_in(project, request_path)
    if target.stat().st_size > 200_000:
        raise ValueError("PDF request exceeds 200 KB")
    return read(target)


def _prepare(project, spec):
    if (not isinstance(spec, dict) or spec.get("schema_version") != "1.0"
            or set(spec) - {"schema_version", "id", "paper_id", "pages", "sentence_ids", "annotate_pdf", "ocr"}):
        raise ValueError("unsupported source-bound PDF request")
    identifier = wb._id(spec.get("id"), "PDF view ID")
    paper, manifest = reading._paper(project, spec.get("paper_id"), None)
    if Path(paper["source"]["path"]).suffix.lower() != ".pdf":
        raise ValueError("PDF view needs a current registered original PDF")
    pages = spec.get("pages")
    if (not isinstance(pages, list) or not 1 <= len(pages) <= 20
            or any(type(p) is not int or not 1 <= p <= 100 for p in pages) or len(set(pages)) != len(pages)):
        raise ValueError("select 1..20 distinct physical PDF pages within 1..100")
    ids = spec.get("sentence_ids")
    if ids is not None and (not isinstance(ids, list) or len(ids) > 500 or any(not isinstance(i, str) for i in ids)
                            or len(set(ids)) != len(ids)):
        raise ValueError("sentence_ids must be at most 500 distinct current sentence IDs")
    annotate = spec.get("annotate_pdf", False)
    if type(annotate) is not bool:
        raise ValueError("annotate_pdf must be an explicit boolean")
    ocr = spec.get("ocr", {"enabled": False, "language": "eng"})
    if (not isinstance(ocr, dict) or set(ocr) - {"enabled", "language"} or type(ocr.get("enabled")) is not bool
            or ocr.get("language", "eng") not in {"eng", "chi_sim", "eng+chi_sim"}):
        raise ValueError("OCR needs an explicit enabled boolean and supported eng/chi_sim language")
    native = reading.build_index(project, paper["id"]) if paper.get("reader") else None
    sentences = [] if native is None else [s for s in native["sentences"] if s["pdf_page"] in pages]
    available = {s["sentence_id"] for s in sentences}
    if ids is not None:
        if set(ids) - available:
            raise ValueError("sentence ID is absent from current selected original pages")
        sentences = [s for s in sentences if s["sentence_id"] in ids]
    if len(sentences) > 500:
        raise ValueError("select at most 500 sentences for a PDF view")
    fingerprint = wb._digest({"spec": spec, "paper": paper["input_fingerprint"], "workbench": manifest,
                              "sentences": sentences, "implementation": sha(Path(__file__))})
    return {"id": identifier, "paper": paper, "pages": sorted(pages), "sentences": sentences,
            "ocr": {"enabled": ocr["enabled"], "language": ocr.get("language", "eng")},
            "annotate_pdf": annotate, "fingerprint": fingerprint}


def _run(arguments, *, timeout=90):
    return subprocess.run(arguments, check=True, capture_output=True, timeout=timeout)


def provision(project, ocr):
    """Install only missing declared tools for this explicit cloud operation."""
    _cloud()
    packages = []
    if any(shutil.which(name) is None for name in ("pdftotext", "pdftoppm")):
        packages.append("poppler-utils")
    if ocr["enabled"]:
        has_ocr = shutil.which("tesseract") is not None
        if not has_ocr:
            packages.append("tesseract-ocr")
        installed = set(_run(["tesseract", "--list-langs"]).stdout.decode("utf-8").splitlines()) if has_ocr else set()
        language_packages = {"eng": "tesseract-ocr-eng", "chi_sim": "tesseract-ocr-chi-sim"}
        packages += [language_packages[language] for language in ocr["language"].split("+") if language not in installed]
    if packages:
        _run(["sudo", "-n", "apt-get", "update", "-qq", "-o", "Acquire::Retries=1", "-o", "Acquire::https::Timeout=20"], timeout=180)
        _run(["sudo", "-n", "apt-get", "install", "-y", "--no-install-recommends", "-o", "Acquire::Retries=1",
              "-o", "Acquire::https::Timeout=20", *packages], timeout=240)
        receipt = path_in(project, "reports/literature-pdf/runtime-provision.json", exists=False)
        write(receipt, {"schema_version": "1.0", "packages": packages, "cloud_only": True, "paid_model_calls": 0})
        record(project, [receipt], MODULE)
    return packages


def _normalize(source, destination):
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(str(source), strict=False)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
        raise ValueError("PDF view needs an unencrypted original of 1..100 pages")
    writer = PdfWriter()
    rotations = []
    for original in reader.pages:
        page = writer.add_page(original)
        rotation = int(page.rotation) % 360
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("unsupported PDF page rotation")
        rotations.append(rotation)
        if rotation:
            page.transfer_rotation_to_content()
    with destination.open("wb") as handle:
        writer.write(handle)
    return rotations


def _ocr_rows(payload):
    if len(payload) > 5_000_000:
        raise ValueError("OCR TSV exceeds 5 MB")
    rows = []
    for row in csv.DictReader(io.StringIO(payload), delimiter="\t"):
        text = row.get("text", "").strip()
        if not text or row.get("level") != "5":
            continue
        confidence = float(row["conf"])
        values = [int(row[k]) for k in ("left", "top", "width", "height")]
        if not math.isfinite(confidence) or any(v < 0 for v in values):
            raise ValueError("invalid OCR confidence or pixel rectangle")
        rows.append({"text": text, "confidence": confidence,
                     "bbox_pixels": [values[0], values[1], values[0] + values[2], values[1] + values[3]],
                     "semantic_verification": False})
    return rows


def _native_annotations(normalized, destination, sentences):
    from pypdf import PdfReader, PdfWriter
    from pypdf.annotations import Highlight
    from pypdf.generic import ArrayObject, FloatObject, NameObject, TextStringObject
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(str(normalized)))
    expected = []
    for sentence in sentences:
        if sentence["position_status"] != "located_unique_normalized_word_sequence":
            continue
        page = writer.pages[sentence["pdf_page"] - 1]
        left, top = float(page.cropbox.left), float(page.cropbox.top)
        quads, boxes = [], []
        for x0, y0, x1, y1 in sentence["rects"]:
            rect = [left + x0, top - y1, left + x1, top - y0]
            boxes.append(rect)
            quads.extend([rect[0], rect[3], rect[2], rect[3], rect[0], rect[1], rect[2], rect[1]])
        if not boxes:
            continue
        rect = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
        annotation = Highlight(rect=rect, quad_points=ArrayObject([FloatObject(v) for v in quads]), highlight_color="ffd500")
        annotation[NameObject("/Contents")] = TextStringObject(sentence["quote"])
        annotation[NameObject("/NM")] = TextStringObject("lunwen-" + sentence["sentence_id"])
        writer.add_annotation(sentence["pdf_page"] - 1, annotation)
        expected.append({"sentence_id": sentence["sentence_id"], "pdf_page": sentence["pdf_page"],
                         "rect_pdf_points_bottom_left": rect, "quad_points": quads})
    with destination.open("wb") as handle:
        writer.write(handle)
    # Reopen the logical annotation tree; a rendered image alone is insufficient.
    actual = []
    reopened = PdfReader(str(destination))
    for number, page in enumerate(reopened.pages, 1):
        for ref in page.get("/Annots", []):
            item = ref.get_object()
            name = str(item.get("/NM", ""))
            if name.startswith("lunwen-sentence-"):
                if item.get("/Subtype") != "/Highlight" or len(item.get("/QuadPoints", [])) % 8:
                    raise ValueError("written PDF highlight structure is invalid")
                actual.append((number, name))
    if sorted(actual) != sorted((x["pdf_page"], "lunwen-" + x["sentence_id"]) for x in expected):
        raise ValueError("written PDF annotation inventory differs from selected source sentences")
    return expected


def _links(project, directory, paper, sentences):
    links = []
    for sentence in sentences:
        relative = reading.OUTPUT + "/" + paper["id"] + "/index.html"
        links.append({"kind": "sentence", "id": sentence["sentence_id"], "pdf_page": sentence["pdf_page"],
            "target": relative + "#" + sentence["sentence_id"], "quote": sentence["quote"]})
    matrix_path = path_in(project, "reports/literature-matrix/manifest.json", exists=False)
    matrix_binding = None
    if matrix_path.is_file():
        from scripts import literature_matrix
        matrix_manifest = read(matrix_path)
        literature_matrix.validate_saved_report(project, matrix_manifest["request"]["path"])
        matrix = read(project / literature_matrix.OUTPUT / "matrix.json")
        matrix_binding = {"path": literature_matrix.OUTPUT + "/manifest.json", "sha256": sha(matrix_path)}
        for cell in matrix["cells"]:
            visual = cell.get("source_context", {}).get("visual_asset")
            if cell["paper_id"] == paper["id"] and visual:
                cell_id = literature_matrix.cell_anchor(paper["id"], cell["field_id"])
                links.append({"kind": "table_cell", "id": cell_id,
                    "pdf_page": visual["pdf_page"], "target": literature_matrix.OUTPUT + "/index.html#" + cell_id,
                    "asset": visual, "quote": cell["text"]})
    return links, matrix_binding


def html_text(project, report):
    esc = lambda value: html.escape(str(value), quote=True)
    directory = OUTPUT + "/" + report["id"]
    href = lambda relative: quote(posixpath.relpath(relative.split("#")[0], directory), safe="/") + ("#" + relative.split("#", 1)[1] if "#" in relative else "")
    body = ['<!doctype html><html lang="en"><meta charset="utf-8">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\' data:; style-src \'unsafe-inline\'">',
        '<title>Source PDF evidence view</title><style>body{font:16px/1.5 system-ui;max-width:80rem;margin:2rem auto;padding:1rem}'
        '.page{position:relative;max-width:70rem}.page img{display:block;width:100%}.page svg{position:absolute;inset:0;width:100%;height:100%}'
        'rect{fill:#ffd500;fill-opacity:.12;stroke:#a56800;stroke-width:.7}a:focus rect,a:hover rect,:target rect{fill-opacity:.4;stroke-width:2}'
        'li:target{background:#fff2b0}pre{white-space:pre-wrap}small{overflow-wrap:anywhere}</style>',
        '<h1>Source PDF evidence view</h1><p>Original SHA-256: <code>' + esc(report["source"]["sha256"]) + '</code></p>',
        '<p>Source navigation and optional OCR assistance; semantic support remains unverified. Original bytes are preserved.</p>']
    if report.get("annotated_pdf"):
        body.append('<p><a href="annotated.pdf">Download annotated reading copy</a> (rotation-normalized; original remains authoritative)</p>')
    for page in report["pages"]:
        number = page["pdf_page"]
        width, height = page["page_size"]
        original = wb._href(Path(project), Path(project) / directory, report["source"]["path"], page=number,
                            source=report["source"], manifest=report.get("source_manifest"))
        body.append('<section id="page-' + str(number) + '"><h2>PDF page ' + str(number) + '</h2><p>' + esc(page["text_status"]) + '</p><p><a href="' + original + '">Open original physical page</a></p>')
        body.append('<div class="page"><img alt="Original PDF physical page ' + str(number) + '" src="' + esc(Path(page["image"]["path"]).name) + '">')
        body.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + str(width) + ' ' + str(height) + '" aria-label="Evidence rectangles">')
        for sentence in report["sentences"]:
            if sentence["pdf_page"] != number or sentence["position_status"] != "located_unique_normalized_word_sequence":
                continue
            body.append('<a href="#text-' + sentence["sentence_id"] + '" id="box-' + sentence["sentence_id"] + '"><title>' + esc(sentence["quote"]) + '</title>')
            for x0, y0, x1, y1 in sentence["rects"]:
                body.append('<rect x="' + str(x0) + '" y="' + str(y0) + '" width="' + str(x1-x0) + '" height="' + str(y1-y0) + '"/>')
            body.append('</a>')
        for link in report["links"]:
            if link["kind"] != "table_cell" or link["pdf_page"] != number:
                continue
            # Native asset manifests already use displayed CropBox points after
            # page rotation, matching this normalized view's top-left coordinates.
            x0, y0, x1, y1 = link["asset"]["bbox"]
            if not 0 <= x0 < x1 <= width + 0.1 or not 0 <= y0 < y1 <= height + 0.1:
                raise ValueError("table evidence rectangle exceeds the displayed PDF page")
            body.append('<a href="#' + esc(link["id"]) + '"><rect x="' + str(x0) + '" y="' + str(y0) + '" width="' + str(x1-x0) + '" height="' + str(y1-y0) + '"/></a>')
        body.append('</svg></div><ol>')
        for sentence in report["sentences"]:
            if sentence["pdf_page"] == number:
                body.append('<li id="text-' + sentence["sentence_id"] + '"><a href="#box-' + sentence["sentence_id"] + '">Locate on page</a> <pre>' + esc(sentence["quote"]) + '</pre><small>' + esc(sentence["position_status"]) + '</small></li>')
        body.append('</ol>')
        if page.get("ocr"):
            body.append('<h3>OCR assistance, unverified</h3><pre>' + esc(" ".join(r["text"] for r in page["ocr"]["words"])) + '</pre>')
        body.append('</section>')
    body.append('<h2>Original text and evidence-table links</h2><ul>')
    for link in report["links"]:
        body.append('<li id="' + esc(link["id"]) + '"><a href="' + esc(href(link["target"])) + '">' + esc(link["kind"]) + '</a> - <a href="#page-' + str(link["pdf_page"]) + '">PDF page ' + str(link["pdf_page"]) + '</a> ' + esc(link["quote"]) + '</li>')
    return "\n".join(body + ['</ul></html>']) + "\n"


def refresh(project: Path, request_path=REQUEST):
    _cloud()
    project = Path(project).resolve()
    spec = _request(project, request_path)
    prepared = _prepare(project, spec)
    directory = path_in(project, OUTPUT + "/" + prepared["id"], exists=False)
    manifest_path = directory / "manifest.json"
    if directory.exists() and any(directory.iterdir()):
        if not manifest_path.is_file():
            raise ValueError("refusing to replace an unowned PDF output directory")
        validate_saved_report(project, request_path)
        result = read(directory / "report.json")
        return {"report": (directory / "report.json").relative_to(project).as_posix(), "cache_hit": True, **result}
    required = ("pdftotext", "pdftoppm") + (("tesseract",) if prepared["ocr"]["enabled"] else ())
    provision(project, prepared["ocr"])
    if any(shutil.which(name) is None for name in required):
        raise RuntimeError("PDF view requires declared cloud tools: " + ", ".join(required))
    directory.mkdir(parents=True, exist_ok=True)
    source = path_in(project, prepared["paper"]["source"]["path"])
    outputs, pages, positioned = [], [], []
    links, matrix_binding = _links(project, directory, prepared["paper"], prepared["sentences"])
    with tempfile.TemporaryDirectory(prefix="literature-pdf-") as temporary:
        normalized = Path(temporary) / "normalized.pdf"
        rotations = _normalize(source, normalized)
        if max(prepared["pages"]) > len(rotations):
            raise ValueError("requested physical PDF page does not exist")
        bbox_path = Path(temporary) / "positions.xhtml"
        _run(["pdftotext", "-bbox-layout", "-cropbox", str(normalized), str(bbox_path)])
        actual_pages = reading._positioned_pages(bbox_path.read_bytes())
        for sentence in prepared["sentences"]:
            positioned.append(reading._locate_sentence(sentence, actual_pages[sentence["pdf_page"] - 1]))
        for number in prepared["pages"]:
            page = actual_pages[number - 1]
            stem = directory / ("page-" + str(number))
            _run(["pdftoppm", "-f", str(number), "-l", str(number), "-singlefile", "-cropbox", "-scale-to", "1800", "-png", str(normalized), str(stem)])
            image = stem.with_suffix(".png")
            if image.stat().st_size > 12_000_000:
                raise ValueError("rendered PDF page exceeds 12 MB")
            outputs.append(image)
            row = {"pdf_page": number, "page_size": [page["width"], page["height"]],
                "source_rotation": rotations[number - 1], "image": {"path": image.relative_to(project).as_posix(), "sha256": sha(image)},
                "text_status": "positioned_original_text_available" if page["words"] else "no_native_text_ocr_or_visual_review_required"}
            if prepared["ocr"]["enabled"]:
                result = _run(["tesseract", str(image), "stdout", "-l", prepared["ocr"]["language"], "tsv"])
                payload = result.stdout.decode("utf-8")
                words = _ocr_rows(payload)
                tsv = stem.with_suffix(".ocr.tsv")
                tsv.write_text(payload, encoding="utf-8")
                outputs.append(tsv)
                row["ocr"] = {"language": prepared["ocr"]["language"], "words": words,
                    "tsv": {"path": tsv.relative_to(project).as_posix(), "sha256": sha(tsv)},
                    "status": "assistance_pending_original_image_review" if words else "no_words_recognized_visual_review_required",
                    "authoritative_original_text": False, "human_review_required": True}
            pages.append(row)
        annotations = []
        annotated = None
        if prepared["annotate_pdf"]:
            annotated = directory / "annotated.pdf"
            annotations = _native_annotations(normalized, annotated, positioned)
            outputs.append(annotated)
        report = {"schema_version": "1.0", "id": prepared["id"], "paper_id": prepared["paper"]["id"],
            "source": prepared["paper"]["source"], "source_manifest": prepared["paper"].get("manifest"), "fingerprint": prepared["fingerprint"],
            "pages": pages, "sentences": positioned, "links": links, "matrix_manifest": matrix_binding,
            "annotated_pdf": None if annotated is None else {"path": annotated.relative_to(project).as_posix(), "sha256": sha(annotated)},
            "annotations": annotations, "original_bytes_preserved": sha(source) == prepared["paper"]["source"]["sha256"],
            "coordinate_system": "rotation_normalized_cropbox_points_top_left", "personal_use_only": True,
            "ocr_is_original_evidence": False, "semantic_support_verified": False, "paid_calls": 0}
        # Revalidate rights and every input after actual tools complete.
        if _prepare(project, spec)["fingerprint"] != prepared["fingerprint"] or not report["original_bytes_preserved"]:
            raise ValueError("source, rights, native text or PDF request changed during rendering")
    target, dashboard = directory / "report.json", directory / "index.html"
    write(target, report)
    dashboard.write_text(html_text(project, report), encoding="utf-8")
    outputs.extend([target, dashboard])
    write(manifest_path, {"schema_version": "1.0", "request": {"path": request_path, "sha256": sha(project / request_path)},
        "fingerprint": prepared["fingerprint"], "implementation_sha256": sha(Path(__file__)),
        "outputs": [{"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in outputs]})
    record(project, [*outputs, manifest_path], MODULE)
    return {"report": target.relative_to(project).as_posix(), "html": dashboard.relative_to(project).as_posix(), "cache_hit": False, **report}


def validate_saved_report(project: Path, request_path=REQUEST):
    from scripts.output_provenance import current_origin
    project = Path(project).resolve()
    prepared = _prepare(project, _request(project, request_path))
    directory = path_in(project, OUTPUT + "/" + prepared["id"], exists=False)
    manifest_path = path_in(project, OUTPUT + "/" + prepared["id"] + "/manifest.json")
    origin = current_origin(project, manifest_path)
    if origin.get("status") != "tracked" or origin.get("model") != MODULE or origin.get("family") != "other":
        raise ValueError("PDF view needs current deterministic output provenance")
    manifest = read(manifest_path)
    if (manifest.get("fingerprint") != prepared["fingerprint"] or manifest.get("implementation_sha256") != sha(Path(__file__))
            or manifest.get("request") != {"path": request_path, "sha256": sha(path_in(project, request_path))}):
        raise ValueError("PDF view source, rights, request or implementation changed")
    outputs = manifest.get("outputs", [])
    if not isinstance(outputs, list) or len({x.get("path") for x in outputs}) != len(outputs):
        raise ValueError("PDF view output inventory is invalid")
    expected = {p.relative_to(project).as_posix() for p in directory.iterdir() if p.is_file() and p != manifest_path}
    if {x.get("path") for x in outputs} != expected or not {OUTPUT + "/" + prepared["id"] + "/report.json", OUTPUT + "/" + prepared["id"] + "/index.html"} <= expected:
        raise ValueError("PDF view output inventory changed")
    for item in outputs:
        if not item["path"].startswith(OUTPUT + "/" + prepared["id"] + "/") or sha(path_in(project, item["path"])) != item.get("sha256"):
            raise ValueError("PDF view output changed")
    report = read(directory / "report.json")
    links, matrix_binding = _links(project, directory, prepared["paper"], prepared["sentences"])
    if (report.get("fingerprint") != prepared["fingerprint"] or report.get("source") != prepared["paper"]["source"]
            or report.get("source_manifest") != prepared["paper"].get("manifest")
            or report.get("matrix_manifest") != matrix_binding or report.get("links") != links
            or (directory / "index.html").read_text(encoding="utf-8") != html_text(project, report)):
        raise ValueError("PDF view no longer matches current source and evidence links")
    return {"valid": True, "fingerprint": prepared["fingerprint"], "semantic_support_verified": False}
