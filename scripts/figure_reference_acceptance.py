"""Cloud integration replay using public references and an explicit software fixture.

Downloads the pinned metadata/CPU embedding assets, executes real ONNX text
inference, then renders a synthetic proposed diagram. No paid model calls,
actual research results, human approvals or scientific completion are supplied.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import editable_figures, figure_gallery as gallery, figure_gallery_semantic as semantic
from scripts import figure_story as story, output_provenance
from scripts.research_artifacts import sha, write

ROOT = Path(__file__).resolve().parents[1]


def _need(value, message):
    if not value:
        raise ValueError(message)


def _fixture_file(project, relative, value):
    target = project/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, dict):
        write(target, value)
    else:
        target.write_text(value, encoding="utf-8")
    output_provenance.record_model_writes(project, [target], family="other", provider="deterministic-control-plane",
        model="scripts/figure_reference_acceptance.py", role="synthetic-software-fixture", run_id="figure-reference-acceptance")
    return {"path": relative, "sha256": sha(target)}


def _anchor(project, binding, kind):
    return {**binding, "start_line": 1, "end_line": 1,
            "quote": (project/binding["path"]).read_text(encoding="utf-8").splitlines()[0], "kind": kind}


def _fixture(project, reference_report):
    # These are explicitly synthetic test records, never my-phd or research data.
    contract = _fixture_file(project, "papers/P01/paper-contract.json", {"paper_id": "P01",
        "research_question": "Synthetic software fixture: how is an input transformed into an output?",
        "distinct_contribution": "Synthetic proposed processing mechanism, not a research finding",
        "independence": {"unique_claim_ids": ["FIXTURE-C1"]}})
    claims = _fixture_file(project, "claims/claim-evidence.csv", "claim_id,paper_id,claim,evidence_ids,analysis_ids,support,uncertainty,status\nFIXTURE-C1,P01,Synthetic proposed mechanism,,,,Not scientific evidence,fixture\n")
    method = _fixture_file(project, "papers/P01/method.md", "Synthetic proposed method: supplied input passes through a declared process to produce an output.\n")
    manuscript = _fixture_file(project, "papers/P01/manuscript/main.tex", "Synthetic proposed method: supplied input passes through a declared process to produce an output.\n")
    style = story.execute(project, "style_prepare", story.default_style())
    style_ref = {key: style[key] for key in ("path", "sha256")}
    ir = {"schema_version": "1.0", "type": "dataflow", "title": "Synthetic proposed mechanism", "caption": "Synthetic proposed input, process and output; software check, not a scientific result.",
        "alt_text": "A synthetic proposed method represented by editable objects.", "claim_ids": ["FIXTURE-C1"],
        "output_stem": "papers/P01/figures/synthetic-main", "style_ref": style_ref,
        "nodes": [{"id": "input", "label": "Supplied input", "kind": "input", "layer": 0}, {"id": "process", "label": "Defined process", "kind": "process", "layer": 1}, {"id": "output", "label": "Declared output", "kind": "output", "layer": 2}],
        "edges": [{"from": "input", "to": "process", "kind": "data", "label": "input"}, {"from": "process", "to": "output", "kind": "data", "label": "output"}]}
    diagram = _fixture_file(project, "papers/P01/figures/synthetic-main.json", ir)
    references = [{"figure_id": row["id"], "url": row["figure_url"], "metadata_sha256": row["metadata_sha256"],
        "borrow_layout": "Candidate reference for module and reading-path arrangement; original image inspection remains pending.",
        "do_not_copy": "Do not copy external method modules, scientific claims, numerical values or original artwork."}
        for row in reference_report["candidates"][:2]]
    request = {"schema_version": "1.0", "id": "synthetic-main", "paper_id": "P01", "phase": "planned",
        "paper_contract": contract, "claims": claims, "diagram": diagram, "manuscript": manuscript, "sources": [method],
        "claim_ids": ["FIXTURE-C1"], "gallery_report": reference_report["report_binding"], "references": references,
        "problem": {"text": "How does the synthetic input pass through the declared mechanism?", "text_locator": _anchor(project, method, "method")},
        "contribution": {"text": "A synthetic proposed processing mechanism", "text_locator": _anchor(project, method, "method")},
        "flow": {"inputs": ["input"], "mechanisms": ["process"], "outputs": ["output"]},
        "panels": [{"id": "a", "purpose": "Show the synthetic proposed module inventory and reading direction.", "node_ids": ["input", "process", "output"], "claim_ids": ["FIXTURE-C1"], "text_locator": _anchor(project, manuscript, "manuscript")}],
        "modules": [{"node_id": node["id"], "meaning": node["label"], "phase": "planned", "text_locator": _anchor(project, method, "method")} for node in ir["nodes"]],
        "connections": [{**{key: edge[key] for key in ("from", "to", "kind")}, "meaning": "The declared synthetic data path.", "phase": "planned", "text_locator": _anchor(project, method, "method")} for edge in ir["edges"]],
        "numeric_bindings": [], "result_sources": []}
    brief = story.prepare(project, request)
    story.validate_saved_report(project, project/brief["path"])
    export_request = {"schema_version": "1.0", "diagram_spec": diagram["path"], "expected_source_sha256": diagram["sha256"],
        "story_ref": {key: brief[key] for key in ("path", "sha256")},
        "formats": ["svg", "pptx", "drawio"], "evidence": [{**method, "locator": "L1, explicit synthetic fixture"}],
        "reference_notes": [{"source_url": entry["url"], "purpose": "layout_reference", "rights_status": "unverified", "note": entry["do_not_copy"]} for entry in references]}
    export_binding = _fixture_file(project, "program/synthetic-editable-export.json", export_request)
    export = editable_figures.export(project, project/export_binding["path"])
    receipt_path = project/"papers/P01/figures/synthetic-main.editable-export.json"
    editable_figures.verify_export(project, receipt_path)
    _need(export["story_alignment"]["manuscript_alignment"] == "source_locations_checked", "Export must retain the current source-bound manuscript alignment")
    _need({row["format"] for row in export["outputs"]} == {"svg", "pptx", "drawio"}, "Missing requested native format")
    _need(all(row["editability"] == "native" and row["raster_elements"] == 0 for row in export["outputs"]), "Synthetic exports must use native editable objects")
    svg = project/next(row["path"] for row in export["outputs"] if row["format"] == "svg")
    root = ET.parse(svg).getroot()
    _need(not root.findall(".//{http://www.w3.org/2000/svg}image"), "SVG cannot be a flattened raster")
    pptx = project/next(row["path"] for row in export["outputs"] if row["format"] == "pptx")
    with ZipFile(pptx) as archive:
        slide = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
        ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main", "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        _need(len(slide.findall(".//p:cxnSp", ns)) >= 2 and len(slide.findall(".//a:t", ns)) >= 4, "PPTX needs attached editable connectors and live text")
        _need(not any(name.startswith("ppt/media/") for name in archive.namelist()), "PPTX fixture must not hide flattened images")
    return {"brief": brief, "export": export, "receipt": receipt_path, "diagram": project/diagram["path"],
            "style": project/style_ref["path"], "manuscript": project/manuscript["path"],
            "claims": project/claims["path"], "pptx": pptx}


def _render_pptx(pptx, output):
    output.mkdir(parents=True, exist_ok=True)
    lo = shutil.which("libreoffice") or shutil.which("soffice")
    ppm, text = shutil.which("pdftoppm"), shutil.which("pdftotext")
    _need(lo and ppm and text, "Cloud acceptance needs LibreOffice and Poppler; the workflow installs them")
    with tempfile.TemporaryDirectory(prefix="figure-reference-lo-") as profile:
        result = subprocess.run([lo, "-env:UserInstallation="+Path(profile).as_uri(), "--headless", "--convert-to", "pdf", "--outdir", str(output), str(pptx)],
                                capture_output=True, text=True, timeout=120, check=False)
    (output/"libreoffice.log").write_text(result.stdout+result.stderr, encoding="utf-8")
    _need(result.returncode == 0, "LibreOffice could not render the native PPTX")
    pdf = output/(pptx.stem+".pdf")
    _need(pdf.is_file() and pdf.stat().st_size > 1000, "Native PPTX render produced no usable PDF")
    extracted = subprocess.run([text, str(pdf), "-"], capture_output=True, text=True, timeout=30, check=True).stdout
    _need(all(label in extracted for label in ("Supplied input", "Defined process", "Declared output")), "PPTX render lost an actual module label")
    (output/"rendered-text.txt").write_text(extracted, encoding="utf-8")
    subprocess.run([ppm, "-f", "1", "-singlefile", "-png", "-r", "120", str(pdf), str(output/"native-pptx")],
                   capture_output=True, text=True, timeout=60, check=True)
    png = output/"native-pptx.png"
    _need(png.is_file() and png.stat().st_size > 1000, "PPTX render preview is missing")
    return [{"path": str(path.relative_to(ROOT)), "sha256": sha(path)} for path in (pdf, png)]


def _staleness(project, artifacts):
    blocked = {}
    for label in ("diagram", "style", "manuscript", "claims"):
        target = artifacts[label]
        original = target.read_bytes()
        target.write_bytes(original+b"\n")
        try:
            try:
                editable_figures.verify_export(project, artifacts["receipt"])
            except (ValueError, RuntimeError, OSError):
                blocked[label] = True
            else:
                raise ValueError("Changed "+label+" did not invalidate the export")
        finally:
            target.write_bytes(original)
    editable_figures.verify_export(project, artifacts["receipt"])
    return blocked


def run(directory):
    gallery._cloud()
    directory = directory.resolve()
    _need(directory.is_relative_to(ROOT) and directory != ROOT, "Acceptance directory must remain inside the repository")
    project = directory/"synthetic-project"
    _need(not project.exists(), "Preserve existing acceptance artifacts; use a fresh cloud output directory")
    project.mkdir(parents=True)
    receipt = gallery.sync(project)
    expected_count = gallery._lock()["metadata"]["record_count"]
    _need(receipt["record_count"] == expected_count and expected_count > 3000, "Pinned real gallery corpus count differs")
    zh = gallery.search(project, "时间序列预测的架构图", top_k=6)
    en = gallery.search(project, "time series prediction architecture", top_k=6)
    _need(len(zh["candidates"]) >= 2 and len(en["candidates"]) >= 2, "Real bilingual reference searches did not find enough candidates")
    sample = en["candidates"][0]
    filtered = gallery.search(project, "time series architecture", venues=[sample["venue"]], years=[sample["year"]], patterns=[sample["pattern"]], tiers=[sample["tier"]], top_k=4)
    _need(filtered["candidates"] and all(row["venue"] == sample["venue"] and row["year"] == sample["year"] and row["pattern"] == sample["pattern"] and row["tier"] == sample["tier"] for row in filtered["candidates"]), "Real structured filters were not applied")
    for report in (zh, en, filtered):
        gallery.validate_search_report(project, report["report_binding"]["path"])
    semantic.provision(project)
    semantic_report = semantic.search(project, "time series prediction architecture", top_k=6)
    gallery.validate_search_report(project, semantic_report["report_binding"]["path"])
    _need(semantic_report["retrieval"]["semantic_image_search"] is True, "Acceptance requires real CPU semantic execution")
    artifacts = _fixture(project, semantic_report)
    rendered = _render_pptx(artifacts["pptx"], directory/"preview")
    stale = _staleness(project, artifacts)
    summary = {"schema_version": "1.0", "status": "software_checks_passed", "real_gallery_record_count": expected_count,
        "real_bilingual_metadata_search": True, "real_structured_filters": True, "real_cpu_semantic_search": True,
        "semantic_evidence": semantic_report["retrieval"]["semantic_evidence"], "synthetic_source_bound_brief": artifacts["brief"]["path"],
        "native_formats": [row["format"] for row in artifacts["export"]["outputs"]], "actual_native_pptx_render": rendered,
        "changed_inputs_rejected": stale, "paid_model_calls": 0, "scientific_completion": False,
        "limits": ["All local paper, claim, method and diagram contents in this replay are explicit synthetic software fixtures.",
            "Retrieved references are real public metadata and upstream embeddings; retrieval is not a scientific or rights approval.",
            "Rendered previews require final-size visual inspection; software checks cannot establish research quality or publication acceptance."]}
    write(directory/"summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/figure-reference"))
    args = parser.parse_args()
    run(args.directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
