"""Source-bound literature extraction tables; no inference, approval or API calls.

The existing workbench remains the library and source authority. This module
organizes writer-authored cells and existing reading cards, preserves unknowns,
and performs only declared Decimal unit conversions. A located value is never
automatically eligible for Meta analysis or a verified scientific conclusion.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation, localcontext
import html
import io
import json
import math
from pathlib import Path
import re

from scripts import literature_workbench as workbench
from scripts.research_artifacts import path_in, record, sha, write

REQUEST = "program/literature-extraction.json"
OUTPUT = "reports/literature-matrix"
DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
# These are exact dimensional conversions, never estimated effect transforms.
CONVERSIONS = {
    ("%", "proportion"): ("0.01", "0"),
    ("proportion", "%"): ("100", "0"),
    ("ms", "s"): ("0.001", "0"), ("s", "ms"): ("1000", "0"),
    ("min", "s"): ("60", "0"),
    ("mg", "g"): ("0.001", "0"), ("g", "mg"): ("1000", "0"),
    ("g", "kg"): ("0.001", "0"), ("kg", "g"): ("1000", "0"),
    ("C", "K"): ("1", "273.15"), ("K", "C"): ("1", "-273.15"),
}
UNITLESS = {"1", "unitless", "dimensionless"}


def _keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + " has unsupported fields")


def _text(value, label, maximum=6000):
    return workbench._text(value, label, maximum)


def _decimal(value, label):
    if not isinstance(value, str) or len(value) > 64 or not DECIMAL.fullmatch(value):
        raise ValueError(label + " requires an original finite decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(label + " requires a finite decimal") from exc
    if not parsed.is_finite() or abs(parsed.adjusted()) > 1000:
        raise ValueError(label + " is outside the bounded decimal range")
    return parsed


def _token(value, quotes, label, *, reject_separated_sign=False, interval_bound=False):
    # Do not accept 20 as evidence for 120 or .05 as a substring of .0501.
    matches = list(re.finditer(r"(?<![\w.+\-\u2212])" + re.escape(value) + r"(?!\w|\.[0-9])", quotes))
    if not matches:
        raise ValueError(label + " is not a verbatim bounded token in the original evidence")
    if (reject_separated_sign or interval_bound) and value[:1] not in {"+", "-"}:
        kept = []
        for match in matches:
            prefix = quotes[:match.start()]
            sign = re.search(r"([+\-\u2212])\s+\Z", prefix)
            # A hyphen directly between numeric bounds can delimit a range
            # (1 - 2). After a comma/bracket/to, or for a Unicode minus/plus,
            # dropping the separated sign would alter the reported bound.
            range_separator = (interval_bound and sign is not None and sign.group(1) == "-"
                and re.search(r"(?<![\w.])[+\-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+\-]?[0-9]+)?\Z",
                              prefix[:sign.start()].rstrip(" \t")))
            if sign is None or range_separator:
                kept.append(match)
        matches = kept
        if not matches:
            raise ValueError(label + " has a separated source sign; inspect the original PDF instead of dropping the sign")
    return matches


def _unit_token(value, quotes):
    left = r"(?<!\w)" if re.match(r"\w", value[0]) else ""
    right = r"(?!\w)" if re.match(r"\w", value[-1]) else ""
    if not re.search(left + re.escape(value) + right, quotes):
        raise ValueError("raw unit is not a complete token in the original evidence")


def _fields(items):
    if not isinstance(items, list) or not 1 <= len(items) <= 40:
        raise ValueError("fields requires 1..40 explicit extraction fields")
    result, seen = [], set()
    for field in items:
        _keys(field, {"id", "label", "type", "card_field", "quantity", "unit", "measure"}, "field")
        identifier = workbench._id(field.get("id"), "field ID")
        if identifier in seen:
            raise ValueError("duplicate extraction field")
        seen.add(identifier)
        kind = field.get("type", "text")
        if kind not in {"text", "number"}:
            raise ValueError("field type must be text or number")
        card_field = field.get("card_field")
        if card_field is not None and card_field not in workbench.FIELDS:
            raise ValueError("card_field must name an existing reading-card field")
        row = {"id": identifier, "label": _text(field.get("label", identifier), "field label", 200),
               "type": kind, "card_field": card_field}
        if kind == "number":
            row.update(quantity=_text(field.get("quantity"), "numeric quantity", 200),
                       unit=_text(field.get("unit"), "target unit", 80),
                       measure=field.get("measure", "value"))
            if row["measure"] not in {"value", "p_value", "ratio", "difference"}:
                raise ValueError("unsupported numeric measure")
            if row["measure"] == "p_value" and row["unit"] not in UNITLESS:
                raise ValueError("p values must be dimensionless")
        elif set(field) & {"quantity", "unit", "measure"}:
            raise ValueError("text fields cannot declare numerical units or measures")
        result.append(row)
    return result


def _context(value, anchors, paper):
    _keys(value, {"kind", "population", "conditions", "table_label", "row_header", "column_header",
                  "footnotes", "visual_asset"}, "source_context")
    kind = value.get("kind")
    if kind not in {"prose", "table"}:
        raise ValueError("source_context kind must be prose or table")
    quotes = "\n".join(a["quote"] for a in anchors)
    result = {"kind": kind}
    for name in ("population", "conditions"):
        item = _text(value.get(name), "source_context " + name, 1000)
        if item not in quotes:
            raise ValueError("source_context " + name + " must be located verbatim")
        result[name] = item
    if kind == "prose":
        if set(value) & {"table_label", "row_header", "column_header", "footnotes", "visual_asset"}:
            raise ValueError("prose contexts cannot declare table-only coordinates")
        result["visual_status"] = "not_a_table"
        return result
    for name in ("table_label", "row_header", "column_header"):
        item = _text(value.get(name), name, 500)
        if item not in quotes:
            raise ValueError(name + " must be located in the exact source evidence")
        result[name] = item
    footnotes = value.get("footnotes")
    if not isinstance(footnotes, list) or len(footnotes) > 20:
        raise ValueError("table footnotes require an explicit bounded list, including [] when unknown")
    result["footnotes"] = []
    for item in footnotes:
        _text(item, "table footnote", 1000)
        if item not in quotes:
            raise ValueError("table footnotes must be located verbatim")
        result["footnotes"].append(item)
    result["footnote_completeness_verified"] = False
    result["visual_status"] = "visual_pending"
    visual = value.get("visual_asset")
    if visual is not None:
        _keys(visual, {"path", "sha256", "pdf_page", "bbox"}, "visual_asset")
        bounds = visual.get("bbox")
        if (not isinstance(bounds, list) or len(bounds) != 4
                or any(type(v) not in {int, float} or not math.isfinite(v) for v in bounds)):
            raise ValueError("visual_asset requires an actual finite PDF rectangle")
        matches = [a for a in (paper.get("figure_manifest") or {}).get("assets", [])
                   if a["path"] == visual.get("path") and a["sha256"] == visual.get("sha256")]
        if len(matches) != 1:
            raise ValueError("visual_asset is not a current source-bound original PDF asset")
        occurrences = [o for o in matches[0]["occurrences"]
                       if o.get("pdf_page") == visual.get("pdf_page") and o.get("bbox") is not None
                       and o["bbox"] == visual.get("bbox")]
        page = visual.get("pdf_page")
        if (not occurrences or type(page) is not int
                or not any(a.get("pdf_page") == page for a in anchors)):
            raise ValueError("visual_asset requires actual coordinates and a same-page original-text anchor")
        result["visual_asset"] = dict(visual)
        result["visual_status"] = "original_region_located_cell_alignment_pending_review"
    return result


def _numeric(value, field, anchors, context):
    _keys(value, {"raw_value", "raw_unit", "quantity", "comparator", "uncertainty"}, "numeric")
    raw = _decimal(value.get("raw_value"), "raw_value")
    raw_unit = _text(value.get("raw_unit"), "raw_unit", 80)
    if value.get("quantity") != field["quantity"]:
        raise ValueError("numeric quantity differs from the declared field")
    quotes = "\n".join(a["quote"] for a in anchors)
    matches = _token(value["raw_value"], quotes, "raw_value", reject_separated_sign=True)
    if raw_unit not in UNITLESS:
        _unit_token(raw_unit, quotes)
    comparator = value.get("comparator", "=")
    if comparator not in {"=", "<", "<=", ">", ">="}:
        raise ValueError("unsupported reported comparator")
    operators = set()
    for match in matches:
        preceding = re.search(r"(<=|>=|<|>|\u2264|\u2265)\s*$", quotes[:match.start()])
        operators.add({"\u2264": "<=", "\u2265": ">="}.get(preceding.group(1), preceding.group(1)) if preceding else "=")
    if comparator not in operators:
        raise ValueError("reported inequality must preserve the operator beside the original value")
    if field["measure"] == "p_value" and (raw_unit not in UNITLESS or not 0 <= raw <= 1):
        raise ValueError("reported p value must be dimensionless and within 0..1")
    target = field["unit"]
    if target == raw_unit or target in UNITLESS and raw_unit in UNITLESS:
        scale, offset = Decimal(1), Decimal(0)
    elif (raw_unit, target) in CONVERSIONS:
        factor, addition = CONVERSIONS[(raw_unit, target)]
        scale, offset = Decimal(factor), Decimal(addition)
    else:
        raise ValueError("unsupported unit conversion; retain original units or add a reviewed exact conversion")
    with localcontext() as precision:
        precision.prec = max(100, abs(raw.adjusted()) + abs(raw.as_tuple().exponent) + 100)
        normalized = raw * scale + offset
        result = {"quantity": field["quantity"], "measure": field["measure"],
                  "raw_value": value["raw_value"], "raw_unit": raw_unit, "comparator": comparator,
                  "original_value": value["raw_value"], "original_unit": raw_unit,
                  "value": str(normalized), "unit": target,
                  "conversion": {"scale": str(scale), "offset": str(offset),
                                 "formula": "target = original * scale + offset", "exact_decimal_arithmetic": True},
                  "reported_zero_p_value_requires_precision_review": field["measure"] == "p_value" and raw == 0,
                  "numeric_token_verified": True, "quantity_semantics_verified": False,
                  "table_cell_alignment_verified": False if context["kind"] == "table" else None,
                  "eligible_for_quantitative_synthesis": False}
        uncertainty = value.get("uncertainty")
        if uncertainty is not None:
            _keys(uncertainty, {"lower", "upper", "label"}, "uncertainty")
            if comparator != "=":
                raise ValueError("a censored value cannot silently become an exact interval estimate")
            lower, upper = _decimal(uncertainty.get("lower"), "interval lower"), _decimal(uncertainty.get("upper"), "interval upper")
            precision.prec = max(precision.prec, abs(lower.adjusted()) + abs(lower.as_tuple().exponent) + 100,
                                 abs(upper.adjusted()) + abs(upper.as_tuple().exponent) + 100)
            if lower > upper:
                raise ValueError("interval lower exceeds upper")
            _token(uncertainty["lower"], quotes, "interval lower", interval_bound=True)
            _token(uncertainty["upper"], quotes, "interval upper", interval_bound=True)
            label = _text(uncertainty.get("label"), "uncertainty label", 100)
            if label not in quotes:
                raise ValueError("interval label must preserve its original source wording")
            result["uncertainty"] = {"raw_lower": uncertainty["lower"], "raw_upper": uncertainty["upper"],
                                     "label": label, "lower": str(lower * scale + offset),
                                     "upper": str(upper * scale + offset), "unit": target,
                                     "contains_reported_estimate": lower <= raw <= upper}
    return result


def _cell(project, row, field, paper):
    _keys(row, {"paper_id", "field_id", "text", "kind", "evidence", "inference_boundary", "numeric", "source_context"}, "cell")
    kind = row.get("kind")
    if kind not in workbench.KINDS:
        raise ValueError("cells must distinguish source claims and interpretations")
    text = _text(row.get("text"), "cell text")
    evidence = row.get("evidence")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 20:
        raise ValueError("a reported cell requires 1..20 exact evidence anchors")
    anchors = [workbench.validate_anchor(project, paper, a) for a in evidence]
    original_paths = {paper["source"]["path"], (paper.get("reader") or {}).get("path")}
    if any(a["path"] not in original_paths for a in anchors):
        raise ValueError("extraction cells must cite original source text, not generated notes")
    if paper.get("source_scope") == "metadata_only" and field["type"] == "number":
        raise ValueError("numeric extraction requires original text beyond metadata-only discovery")
    boundary = row.get("inference_boundary")
    if kind != "author_claim":
        boundary = _text(boundary, "interpretation inference boundary")
    result = {"paper_id": paper["id"], "field_id": field["id"], "status": "located_pending_semantic_review",
              "text": text, "kind": kind, "evidence": anchors, "inference_boundary": boundary,
              "from_reading_card": False, "semantic_verification": False,
              "eligible_for_quantitative_synthesis": False}
    if field["type"] == "number":
        if kind != "author_claim":
            raise ValueError("original numerical measurements cannot be inferred by a model or reader")
        context = _context(row.get("source_context"), anchors, paper)
        result.update(source_context=context, numeric=_numeric(row.get("numeric"), field, anchors, context))
        if context["kind"] == "table":
            result["status"] = "visual_pending" if context["visual_status"] == "visual_pending" else "located_pending_visual_and_semantic_review"
    elif "numeric" in row or "source_context" in row:
        raise ValueError("text cells cannot declare numerical extraction metadata")
    return result


def build(project: Path, spec: dict, *, workbench_dir=None) -> dict:
    """Build all selected papers x fields, retaining every unknown cell."""
    project = Path(project).resolve()
    _keys(spec, {"schema_version", "question", "paper_ids", "fields", "cells"}, "extraction request")
    if spec.get("schema_version") != "1.0":
        raise ValueError("unsupported literature extraction schema")
    question = _text(spec.get("question"), "extraction question", 4000)
    ids = spec.get("paper_ids")
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 100
            or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids)):
        raise ValueError("paper_ids requires 1..100 distinct current source IDs")
    fields = _fields(spec.get("fields"))
    incoming = spec.get("cells", [])
    if not isinstance(incoming, list) or len(incoming) > len(ids) * len(fields):
        raise ValueError("cells must be a bounded subset of the selected papers x fields")
    library, _, manifest = workbench._snapshot(project, workbench_dir)
    papers = {p["id"]: p for p in library["papers"]}
    for identifier in ids:
        if identifier not in papers or papers[identifier].get("status") != "current":
            raise ValueError("selected paper is missing, stale or invalid: " + identifier)
    selected, field_ids = {}, {f["id"] for f in fields}
    for cell in incoming:
        if not isinstance(cell, dict):
            raise ValueError("cell must be an object")
        key = (workbench._id(cell.get("paper_id"), "cell paper ID"),
               workbench._id(cell.get("field_id"), "cell field ID"))
        if key[0] not in ids or key[1] not in field_ids or key in selected:
            raise ValueError("duplicate or out-of-scope extraction cell")
        selected[key] = cell
    cells = []
    for identifier in ids:
        paper = papers[identifier]
        for field in fields:
            key = identifier, field["id"]
            if key in selected:
                cell = _cell(project, selected[key], field, paper)
            else:
                rows = paper.get("card", {}).get("fields", {}).get(field["card_field"], []) if field["card_field"] else []
                cell = {"paper_id": identifier, "field_id": field["id"], "status": "unknown",
                        "text": None, "kind": None, "evidence": [], "from_reading_card": False,
                        "semantic_verification": False, "eligible_for_quantitative_synthesis": False,
                        "required_resolution": "Locate the original field, context and applicable table/figure evidence; do not infer absence from an empty card."}
                if rows and field["type"] == "text":
                    # The existing card remains the fact authority. Preserve all
                    # entries and disagreements rather than select one answer.
                    cell.update(status="reading_card_entries_pending_review", from_reading_card=True,
                                text="\n".join(r["text"] for r in rows), entries=rows,
                                evidence=[a for r in rows for a in r["evidence"]])
            cells.append(cell)
    bindings = [{"paper_id": i, "source": papers[i]["source"],
                 "manifest": papers[i].get("manifest"),
                 "input_fingerprint": papers[i]["input_fingerprint"], "title": papers[i]["title"],
                 "source_scope": papers[i].get("source_scope"), "read_scope": papers[i].get("read_scope")} for i in ids]
    fingerprint = workbench._digest({"spec": spec, "bindings": bindings, "workbench_manifest": manifest,
                                     "implementation_sha256": sha(Path(__file__))})
    return {"schema_version": "1.0", "question": question, "fields": fields, "papers": bindings,
            "cells": cells, "unknown_cell_count": sum(c["status"] == "unknown" for c in cells),
            "fingerprint": fingerprint, "workbench_output": manifest["output_dir"],
            "model_call_made": False, "paid_calls": 0, "semantic_verification": False,
            "comparability_verified": False, "human_full_text_reading_verified": False,
            "eligible_for_quantitative_synthesis": False, "scientific_completion_verified": False}


def _csv_text(value):
    value = "" if value is None else str(value)
    return "'" + value if value[:1] in {"=", "+", "-", "@"} else value


def csv_text(report):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["paper_id", "field_id", "status", "text", "raw_value", "raw_unit", "comparator",
                     "normalized_value", "normalized_unit", "source_anchors", "eligible_for_quantitative_synthesis"])
    for cell in report["cells"]:
        number = cell.get("numeric", {})
        writer.writerow([cell["paper_id"], cell["field_id"], cell["status"], _csv_text(cell["text"]),
                         number.get("raw_value", ""), _csv_text(number.get("raw_unit")), number.get("comparator", ""),
                         number.get("value", ""), _csv_text(number.get("unit")),
                         json.dumps(cell["evidence"], ensure_ascii=False, sort_keys=True), "false"])
    return output.getvalue()


def markdown_text(report):
    """Portable evidence table; escaping preserves literal source wording."""
    esc = lambda value: html.escape("" if value is None else str(value)).replace("|", "&#124;").replace("\n", "<br>")
    lines = ["# Literature evidence matrix", "", esc(report["question"]), "",
             "Located evidence remains pending semantic and comparability review. Unknown values stay unknown.", "",
             "| Paper | Field | Status | Text | Original number / unit | Evidence |",
             "| --- | --- | --- | --- | --- | --- |"]
    for cell in report["cells"]:
        numeric = cell.get("numeric", {})
        original = " ".join(str(v) for v in (numeric.get("comparator"), numeric.get("original_value"), numeric.get("original_unit")) if v is not None)
        evidence = "<br>".join(esc(a["path"]) + " - " + esc(a["locator"]) + " - SHA256 " +
            esc(a.get("sha256", "unknown")) + ": " + esc(a["quote"]) for a in cell["evidence"])
        lines.append("| " + " | ".join(esc(v) for v in (cell["paper_id"], cell["field_id"], cell["status"], cell["text"], original)) + " | " + evidence + " |")
    lines += ["", "## Complete cell records", "",
              "Original and normalized values, uncertainty, source versions, conditions, table headers, footnotes and review boundaries are preserved below when present. Missing fields are not inferred."]
    papers = {row["paper_id"]: row for row in report.get("papers", [])}
    for cell in report["cells"]:
        payload = {"cell": cell, "paper_source": papers.get(cell["paper_id"])}
        lines += ["", "<details>", "<summary>" + html.escape(cell["paper_id"] + " / " + cell["field_id"]) + "</summary>", "",
                  "<pre>" + html.escape(json.dumps(payload, ensure_ascii=False, indent=2)) + "</pre>", "</details>"]
    return "\n".join(lines) + "\n"


def cell_anchor(paper_id, field_id):
    return "cell-" + workbench._digest([paper_id, field_id])[:24]


def html_text(project, report):
    esc = lambda value: html.escape(str(value), quote=True)
    directory = Path(project) / OUTPUT
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; base-uri \'none\'; form-action \'none\'">',
             '<title>Source-bound literature matrix</title></head><body>',
             '<h1>Source-bound literature matrix</h1><p>' + esc(report["question"]) + '</p>',
             '<p>Located quotations and parsed numbers require semantic and visual review. No cell is approved for quantitative synthesis.</p>',
             '<table><thead><tr><th>Paper</th><th>Field</th><th>Status</th><th>Value and evidence</th></tr></thead><tbody>']
    papers = {p["paper_id"]: p for p in report["papers"]}
    for cell in report["cells"]:
        parts.append('<tr id="' + cell_anchor(cell["paper_id"], cell["field_id"]) + '"><td>' + esc(cell["paper_id"]) + '</td><td>' + esc(cell["field_id"]) + '</td><td>' + esc(cell["status"]) + '</td><td>')
        parts.append('<p>' + esc(cell["text"] if cell["text"] is not None else "Unknown; source review required") + '</p>')
        if cell.get("numeric"):
            parts.append('<pre>' + esc(json.dumps(cell["numeric"], ensure_ascii=False, indent=2)) + '</pre>')
        paper = papers[cell["paper_id"]]
        for anchor in cell["evidence"]:
            # Anchor links always point to controlled original text; page links
            # point to the owning PDF separately instead of adding PDF fragments
            # to a markdown reader.
            link = workbench._href(Path(project), directory, anchor["path"], source=paper["source"])
            parts.append('<p><a href="' + link + '">' + esc(anchor["locator"]) + '</a> · ' + esc(anchor["sha256"]) + '</p><blockquote>' + esc(anchor["quote"]) + '</blockquote>')
            if anchor.get("pdf_page") is not None and Path(paper["source"]["path"]).suffix.lower() == ".pdf":
                pdf = workbench._href(Path(project), directory, paper["source"]["path"],
                                      page=anchor["pdf_page"], source=paper["source"], manifest=paper["manifest"])
                parts.append('<p><a href="' + pdf + '">Original PDF page ' + str(anchor["pdf_page"]) + '</a></p>')
        parts.append('</td></tr>')
    parts.append('</tbody></table></body></html>')
    return "\n".join(parts) + "\n"


def _request(project, request_path):
    if not isinstance(request_path, str) or not request_path.startswith("program/") or Path(request_path).suffix != ".json":
        raise ValueError("literature extraction request must be a JSON file under program/")
    target = path_in(project, request_path)
    if target.stat().st_size > 2_000_000:
        raise ValueError("literature extraction request exceeds 2 MB")
    return workbench._json(target.read_bytes())


def refresh(project: Path, request_path=REQUEST, *, workbench_dir=None) -> dict:
    project = Path(project).resolve()
    report = build(project, _request(project, request_path), workbench_dir=workbench_dir)
    directory = path_in(project, OUTPUT, exists=False)
    if directory.exists() and any(directory.iterdir()) and not (directory / "manifest.json").is_file():
        raise ValueError("refusing to overwrite a directory owned by another tool")
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / "matrix.json", directory / "matrix.csv", directory / "index.html", directory / "matrix.md"]
    write(paths[0], report)
    paths[1].write_text(csv_text(report), encoding="utf-8")
    paths[2].write_text(html_text(project, report), encoding="utf-8")
    paths[3].write_text(markdown_text(report), encoding="utf-8")
    manifest = {"schema_version": "1.0", "request": {"path": request_path, "sha256": sha(project / request_path)},
                "workbench_dir": report["workbench_output"], "fingerprint": report["fingerprint"],
                "implementation_sha256": sha(Path(__file__)),
                "outputs": [{"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in paths],
                "semantic_verification": False, "eligible_for_quantitative_synthesis": False}
    write(directory / "manifest.json", manifest)
    record(project, [*paths, directory / "manifest.json"], "scripts/literature_matrix.py")
    return {"report": OUTPUT + "/matrix.json", "csv": OUTPUT + "/matrix.csv", "html": OUTPUT + "/index.html", "markdown": OUTPUT + "/matrix.md",
            "cell_count": len(report["cells"]), "unknown_cell_count": report["unknown_cell_count"],
            "fingerprint": report["fingerprint"], "model_call_made": False}


def validate_saved_report(project: Path, request_path=REQUEST) -> dict:
    from scripts.output_provenance import current_origin
    project = Path(project).resolve()
    manifest_path = path_in(project, OUTPUT + "/manifest.json")
    origin = current_origin(project, manifest_path)
    if origin.get("status") != "tracked" or origin.get("family") != "other" or origin.get("model") != "scripts/literature_matrix.py":
        raise ValueError("literature matrix requires current deterministic output provenance")
    manifest = workbench._json(manifest_path.read_bytes())
    if manifest.get("request") != {"path": request_path, "sha256": sha(path_in(project, request_path))}:
        raise ValueError("literature extraction request changed")
    fresh = build(project, _request(project, request_path), workbench_dir=manifest.get("workbench_dir"))
    if manifest.get("fingerprint") != fresh["fingerprint"] or manifest.get("implementation_sha256") != sha(Path(__file__)):
        raise ValueError("literature matrix inputs or implementation changed")
    expected = {OUTPUT + "/matrix.json", OUTPUT + "/matrix.csv", OUTPUT + "/index.html", OUTPUT + "/matrix.md"}
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or {o.get("path") for o in outputs} != expected or len(outputs) != len(expected):
        raise ValueError("literature matrix output inventory differs")
    for item in outputs:
        if sha(path_in(project, item["path"])) != item.get("sha256"):
            raise ValueError("literature matrix output changed")
    saved = workbench._json(path_in(project, OUTPUT + "/matrix.json").read_bytes())
    if saved != fresh or path_in(project, OUTPUT + "/matrix.csv").read_text(encoding="utf-8") != csv_text(fresh) or path_in(project, OUTPUT + "/index.html").read_text(encoding="utf-8") != html_text(project, fresh):
        raise ValueError("literature matrix no longer reproduces its source-bound extraction")
    if path_in(project, OUTPUT + "/matrix.md").read_text(encoding="utf-8") != markdown_text(fresh):
        raise ValueError("literature matrix Markdown no longer reproduces its source-bound extraction")
    return {"valid": True, "fingerprint": fresh["fingerprint"], "semantic_verification": False,
            "eligible_for_quantitative_synthesis": False}
