"""Organize writer-authored synthesis against the existing complete evidence matrix.

No vote counting, scientific-strength score, paper generation or new model pass.
"""
from __future__ import annotations

import html
from pathlib import Path

from scripts import literature_matrix, literature_workbench as wb
from scripts.research_artifacts import path_in, read, record, sha, write

OUTPUT = "reports/literature-synthesis"
AXES = {"construct", "population", "data", "method", "identification", "measurement", "statistics", "protocol", "scope"}
ASSESSMENTS = {"design", "bias", "comparability", "uncertainty"}


def _cell_references(value, cells, label):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError(label + " needs bounded matrix cell references")
    selected, seen = [], set()
    for ref in value:
        if not isinstance(ref, dict) or set(ref) != {"paper_id", "field_id"}:
            raise ValueError(label + " needs exact paper_id and field_id")
        key = (ref["paper_id"], ref["field_id"])
        if key in seen or key not in cells or cells[key]["status"] == "unknown" or not cells[key]["evidence"]:
            raise ValueError(label + " cites duplicate, absent or unknown evidence")
        seen.add(key)
        selected.append({**ref, "evidence": cells[key]["evidence"], "source_status": cells[key]["status"]})
    return selected


def _outline(items, ids, depth=1):
    if not isinstance(items, list) or not 1 <= len(items) <= 8:
        raise ValueError("each outline level needs 1..8 sections")
    result, covered = [], set()
    for item in items:
        keys = {"title", "purpose", "judgment_ids"} | ({"sections"} if depth < 3 else set())
        if not isinstance(item, dict) or set(item) != keys:
            raise ValueError("outline must have exactly three explicit levels")
        title = wb._text(item["title"], "outline title", 300)
        purpose = wb._text(item["purpose"], "outline purpose", 1500)
        references = item["judgment_ids"]
        if (not isinstance(references, list) or len(references) > 50 or any(not isinstance(i, str) for i in references)
                or len(set(references)) != len(references) or not set(references) <= ids):
            raise ValueError("outline references unknown or repeated synthesis judgments")
        row = {"title": title, "purpose": purpose, "judgment_ids": references}
        covered.update(references)
        if depth < 3:
            row["sections"], child_ids = _outline(item["sections"], ids, depth + 1)
            covered.update(child_ids)
        elif not references:
            raise ValueError("each leaf outline section needs a located synthesis judgment")
        result.append(row)
    return result, covered


def build(project: Path, spec: dict) -> dict:
    if (not isinstance(spec, dict) or set(spec) != {"schema_version", "question", "matrix", "judgments", "outline"}
            or spec.get("schema_version") != "1.0"):
        raise ValueError("synthesis needs current matrix, judgments and three-level outline")
    binding = spec["matrix"]
    if (not isinstance(binding, dict) or set(binding) != {"path", "sha256"}
            or binding.get("path") != "reports/literature-matrix/matrix.json"):
        raise ValueError("synthesis uses the existing canonical matrix")
    manifest = read(path_in(project, "reports/literature-matrix/manifest.json"))
    literature_matrix.validate_saved_report(project, manifest["request"]["path"])
    target = path_in(project, binding["path"])
    if sha(target) != binding["sha256"]:
        raise ValueError("synthesis matrix changed")
    matrix = wb._json(target.read_bytes())
    question = wb._text(spec["question"], "synthesis question", 4000)
    if question != matrix["question"]:
        raise ValueError("synthesis question must match the selected matrix scope")
    incoming = spec["judgments"]
    if not isinstance(incoming, list) or not 1 <= len(incoming) <= 50:
        raise ValueError("synthesis requires 1..50 explicit judgments")
    cells = {(c["paper_id"], c["field_id"]): c for c in matrix["cells"]}
    judgments, identifiers, used = [], set(), set()
    for item in incoming:
        keys = {"id", "statement", "relation", "axes", "supports", "contradicts", "assessment", "inference_boundary", "missing_evidence"}
        if not isinstance(item, dict) or set(item) != keys or wb._id(item.get("id")) in identifiers:
            raise ValueError("synthesis judgment has invalid fields or duplicate ID")
        identifiers.add(item["id"])
        statement = wb._text(item["statement"], "synthesis statement", 4000)
        boundary = wb._text(item["inference_boundary"], "synthesis inference boundary", 2000)
        if item["relation"] not in {"agreement", "conflict", "conditional", "insufficient"}:
            raise ValueError("unsupported synthesis relationship")
        axes = item["axes"]
        if not isinstance(axes, list) or not axes or any(a not in AXES for a in axes) or len(set(axes)) != len(axes):
            raise ValueError("explain the actual conditions behind agreement or disagreement")
        supports = _cell_references(item["supports"], cells, "supporting evidence")
        contradicts = _cell_references(item["contradicts"], cells, "contrary evidence")
        if not supports and not contradicts:
            raise ValueError("synthesis judgment needs actual located evidence")
        sources = {r["paper_id"] for r in supports + contradicts}
        if item["relation"] in {"agreement", "conflict"} and len(sources) < 2:
            raise ValueError("cross-paper agreement/conflict needs at least two source identities")
        if item["relation"] == "conflict" and (not supports or not contradicts):
            raise ValueError("a conflict needs both competing evidence sides")
        if item["relation"] == "agreement" and contradicts:
            raise ValueError("preserve contrary evidence as conflict or conditional synthesis")
        assessment = item["assessment"]
        if not isinstance(assessment, dict) or set(assessment) != ASSESSMENTS:
            raise ValueError("assess design, bias, comparability and uncertainty separately")
        assessed = {}
        for dimension in sorted(ASSESSMENTS):
            value = assessment[dimension]
            if not isinstance(value, dict) or set(value) != {"status", "text", "cells"} or value["status"] not in {"unknown", "interpretation"}:
                raise ValueError("evidence strength is an attributed assessment, never an automated verified score")
            assessed[dimension] = {"status": value["status"], "text": wb._text(value["text"], "assessment rationale", 2000),
                "cells": _cell_references(value["cells"], cells, "assessment evidence")}
            if value["status"] == "interpretation" and not assessed[dimension]["cells"]:
                raise ValueError("an interpreted strength assessment needs located evidence")
        missing = item["missing_evidence"]
        if not isinstance(missing, list) or len(missing) > 30 or any(not isinstance(v, str) or not v.strip() or len(v) > 1500 for v in missing):
            raise ValueError("missing evidence must be explicit bounded follow-up tasks")
        if item["relation"] == "insufficient" and not missing:
            raise ValueError("insufficient evidence needs a concrete next task")
        used.update((r["paper_id"], r["field_id"]) for r in supports + contradicts)
        judgments.append({"id": item["id"], "statement": statement, "relation": item["relation"],
            "axes": axes, "supports": supports, "contradicts": contradicts, "assessment": assessed,
            "inference_boundary": boundary, "missing_evidence": missing,
            "semantic_support_verified": False, "independent_studies_verified": False})
    outline, covered = _outline(spec["outline"], identifiers)
    if covered != identifiers:
        raise ValueError("outline omits a registered synthesis judgment")
    return {"schema_version": "1.0", "kind": "source_bound_literature_synthesis_plan", "question": question,
        "matrix": binding, "judgments": judgments, "outline": outline,
        "unaddressed_cells": [{"paper_id": p, "field_id": f, "status": cells[p, f]["status"]}
            for p, f in cells if (p, f) not in used],
        "unknown_cells": [{"paper_id": c["paper_id"], "field_id": c["field_id"]} for c in matrix["cells"] if c["status"] == "unknown"],
        "all_matrix_cells_retained": matrix["cells"], "vote_counting_used": False,
        "semantic_support_verified": False, "research_gap_proven": False,
        "narrative_review_fulfills_paper_portfolio": False, "model_call_made": False,
        "implementation_sha256": sha(Path(__file__))}


def _html(report):
    def outline_html(rows):
        return "<ol>" + "".join("<li>" + html.escape(r["title"]) + ": " + html.escape(r["purpose"]) +
            (outline_html(r["sections"]) if "sections" in r else "") + "</li>" for r in rows) + "</ol>"
    judgments = []
    for judgment in report["judgments"]:
        part = "<h2>" + html.escape(judgment["id"]) + "</h2><p>" + html.escape(judgment["statement"]) + "</p>"
        for side in ("supports", "contradicts"):
            part += "<h3>" + side + "</h3><ul>"
            for ref in judgment[side]:
                part += "<li>" + html.escape(ref["paper_id"] + " / " + ref["field_id"])
                for anchor in ref["evidence"]:
                    href = "../../" + anchor["path"] + "#L" + str(anchor["start_line"])
                    part += '<p><a href="' + html.escape(href, quote=True) + '">' + html.escape(anchor.get("locator", "Original source")) + '</a></p><blockquote>' + html.escape(anchor["quote"]) + '</blockquote>'
                part += "</li>"
            part += "</ul>"
        part += "<p>Boundary: " + html.escape(judgment["inference_boundary"]) + "</p><ul>" + "".join(
            "<li>Missing evidence: " + html.escape(task) + "</li>" for task in judgment["missing_evidence"]) + "</ul>"
        judgments.append(part)
    return ('<!doctype html><meta charset="utf-8"><title>Evidence synthesis plan</title>' +
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'">' +
        "<h1>Evidence synthesis plan</h1><p>" + html.escape(report["question"]) + "</p>" +
        "<p>Source-backed interpretations require scientific review. Evidence strength is not a paper-count vote.</p>" +
        '<p><a href="../literature-matrix/index.html">Complete matrix, including unknowns and unaddressed cells</a></p>' +
        outline_html(report["outline"]) + "".join(judgments))


def refresh(project: Path, request_path="program/literature-synthesis.json") -> dict:
    if not isinstance(request_path, str) or not request_path.startswith("program/"):
        raise ValueError("synthesis request belongs under program/")
    source = path_in(project, request_path)
    if source.stat().st_size > 1_000_000:
        raise ValueError("synthesis request exceeds 1 MB")
    report = build(project, wb._json(source.read_bytes()))
    report["request"] = {"path": request_path, "sha256": sha(source)}
    directory = path_in(project, OUTPUT, exists=False)
    target = directory / "latest.json"
    from scripts.output_provenance import current_origin
    page = directory / "index.html"
    for output in (target, page):
        if output.exists() and (current_origin(project, output).get("status") != "tracked"
                or current_origin(project, output).get("model") != "scripts/literature_synthesis.py"):
            raise ValueError("preserve altered synthesis output before rebuilding")
    write(target, report)
    page.write_text(_html(report), encoding="utf-8")
    record(project, [target, page], "scripts/literature_synthesis.py")
    return {"report": OUTPUT + "/latest.json", "html": OUTPUT + "/index.html", "model_call_made": False}


def validate_saved_report(project: Path, request_path="program/literature-synthesis.json") -> dict:
    source = path_in(project, request_path)
    fresh = build(project, wb._json(source.read_bytes()))
    fresh["request"] = {"path": request_path, "sha256": sha(source)}
    target = path_in(project, OUTPUT + "/latest.json")
    from scripts.output_provenance import current_origin
    page = path_in(project, OUTPUT + "/index.html")
    if (current_origin(project, target).get("status") != "tracked" or read(target) != fresh
            or current_origin(project, page).get("status") != "tracked" or page.read_text(encoding="utf-8") != _html(fresh)):
        raise ValueError("synthesis inputs or output changed")
    return {"valid": True, "semantic_support_verified": False}
