"""Source-bound main-figure briefs and shared visual tokens; no model calls.

A brief is a candidate composition, never a scientific approval. External
gallery records are discovery metadata, not inspected images or our results.
The existing manuscript, claims, diagram IR and executor receipts stay canonical.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.research_artifacts import path_in, read, record, sha, write

ROOT = Path(__file__).resolve().parents[1]
MODULE = "scripts/figure_story.py"
STYLE_PATH = "program/figure-visual-style.json"
NODE_KINDS = {"input", "data", "process", "model", "decision", "output", "actor", "system", "construct"}
EDGE_KINDS = {"data", "control", "causal", "association", "feedback", "temporal"}
NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?%?(?![\w.])")
PHASES = {"method", "planned", "observed"}


def _need(value, message):
    if not value:
        raise ValueError(message)


def _cloud():
    _need(os.environ.get("DR_OS_CLOUD_EXECUTOR") == "1" or os.environ.get("GITHUB_ACTIONS") == "true",
          "Figure story preparation requires the declared cloud executor")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _implementation():
    names = (MODULE, "scripts/research_diagrams.py", "scripts/figure_gallery.py", "scripts/tex_sources.py",
             "schemas/figure-story-request.schema.json", "schemas/figure-story-report.schema.json", "schemas/figure-visual-style.schema.json")
    return [{"path": name, "sha256": sha(ROOT/name)} for name in names]


def _keys(value, required, optional=()):
    _need(isinstance(value, dict) and set(required) <= set(value) <= set(required) | set(optional),
          "Unexpected or missing fields: " + ", ".join(sorted(required)))


def _text(value, label):
    _need(isinstance(value, str) and value.strip() and len(value) <= 4000, label + " needs bounded text")
    _need(not re.search(r"[\u3400-\u9fff\uf900-\ufaff]", value), label + " must be English for manuscript-bound figure work")
    return value


def _binding(project, value, inputs):
    _keys(value, {"path", "sha256"})
    _need(isinstance(value["path"], str), "Source path must be text")
    target = path_in(project, value["path"])
    _need(target.stat().st_size <= 10_000_000, "Figure story source exceeds 10 MB")
    _need(re.fullmatch(r"[0-9a-f]{64}", str(value["sha256"])) and sha(target) == value["sha256"],
          "Source changed: " + value["path"])
    if value not in inputs:
        inputs.append(dict(value))
    return target


def _authored(project, target):
    from scripts.output_provenance import require_final_origins
    require_final_origins(project, [target])


def _anchor(project, value, inputs, allowed):
    _keys(value, {"path", "sha256", "start_line", "end_line", "quote", "kind"})
    _need(value["kind"] in {"manuscript", "protocol", "paper_contract", "method", "result"}, "Unknown text locator kind")
    binding = {key: value[key] for key in ("path", "sha256")}
    _need(binding in allowed, "Text locator must refer to a bound paper source")
    target = _binding(project, binding, inputs)
    _need(target.suffix.lower() in {".md", ".tex", ".json", ".jsonl", ".csv", ".txt"}, "Text locator requires an actual text source")
    lines = target.read_text(encoding="utf-8").splitlines()
    start, end = value["start_line"], value["end_line"]
    _need(type(start) is int and type(end) is int and 1 <= start <= end <= len(lines) and end-start <= 50,
          "Text locator line range is absent or unbounded")
    quote = _text(value["quote"], "Located source quotation")
    located = "\n".join(lines[start-1:end])
    _need(quote in located, "Text locator quote does not occur at its actual source lines")
    return located


def _contrast(foreground, background):
    def luminance(color):
        channels = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
        linear = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in channels]
        return sum(c*w for c, w in zip(linear, (.2126, .7152, .0722)))
    low, high = sorted((luminance(foreground), luminance(background)))
    return (high+.05)/(low+.05)


def validate_style(style):
    _keys(style, {"schema_version", "id", "paper_ids", "font_family", "font_size_pt", "title_size_pt",
                  "edge_label_size_pt", "text_color", "node_fills", "edge_colors", "edge_styles",
                  "palette_semantics", "legend_policy"})
    _need(style["schema_version"] == "1.0" and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", str(style["id"])), "Unsupported visual style identity")
    _need(style["paper_ids"] == [f"P{i:02}" for i in range(1, 7)], "Visual style must cover the common six-paper portfolio")
    _text(style["font_family"], "Font family")
    _need(len(style["font_family"]) <= 80 and not re.search(r"[<>;\r\n\x00-\x1f]", style["font_family"]), "Font family needs a literal name")
    for key, low, high in (("font_size_pt", 7, 18), ("title_size_pt", 8, 24), ("edge_label_size_pt", 6, 16)):
        _need(type(style[key]) in {int, float} and low <= style[key] <= high, "Invalid final-size visual token: " + key)
    _need(isinstance(style["node_fills"], dict) and set(style["node_fills"]) == NODE_KINDS, "Every node kind needs a stable fill")
    _need(isinstance(style["edge_colors"], dict) and set(style["edge_colors"]) == EDGE_KINDS, "Every edge kind needs a stable color")
    _need(isinstance(style["edge_styles"], dict) and set(style["edge_styles"]) == EDGE_KINDS, "Every edge kind needs a stable line style")
    for color in [style["text_color"], *style["node_fills"].values(), *style["edge_colors"].values()]:
        _need(isinstance(color, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", color), "Colors require literal six-digit hex")
    _need(all(value in {"solid", "dashed", "dotted"} for value in style["edge_styles"].values()), "Unsupported semantic line style")
    _need(style["edge_styles"]["association"] == "dashed" and style["edge_styles"]["feedback"] == "dotted", "Association and feedback require distinct non-color encodings")
    _need(isinstance(style["palette_semantics"], dict) and set(style["palette_semantics"]) == NODE_KINDS, "Palette semantic roles must cover every node kind")
    for meaning in style["palette_semantics"].values():
        _text(meaning, "Palette meaning")
    _keys(style["legend_policy"], {"show_edge_kinds", "non_color_encoding"})
    _need(style["legend_policy"] == {"show_edge_kinds": True, "non_color_encoding": True}, "Visual legend must preserve typed and non-color semantics")
    _need(all(_contrast(style["text_color"], fill) >= 4.5 for fill in style["node_fills"].values()), "Node text/fill contrast is below 4.5")
    return style


def default_style():
    """Deterministic starting tokens, not a journal rule or a scientific decision."""
    return {"schema_version": "1.0", "id": "doctoral-six-paper-v1", "paper_ids": [f"P{i:02}" for i in range(1, 7)],
            "font_family": "Times New Roman", "font_size_pt": 8, "title_size_pt": 11, "edge_label_size_pt": 7,
            "text_color": "#142C38", "node_fills": {"input": "#D9EDF1", "data": "#D9EDF1", "process": "#E8E5F1",
            "model": "#FAEAD8", "decision": "#FAEAD8", "output": "#DCEDE5", "actor": "#E7EAF0", "system": "#E7EAF0", "construct": "#E8E5F1"},
            "edge_colors": {kind: "#416779" for kind in sorted(EDGE_KINDS)},
            "edge_styles": {kind: {"association": "dashed", "feedback": "dotted"}.get(kind, "solid") for kind in sorted(EDGE_KINDS)},
            "palette_semantics": {"input": "Supplied input", "data": "Recorded or proposed data source", "process": "Defined operation",
                "model": "Model component", "decision": "Decision rule", "output": "Declared output", "actor": "Responsible actor",
                "system": "System boundary", "construct": "Scientific construct"},
            "legend_policy": {"show_edge_kinds": True, "non_color_encoding": True}}


def load_visual_style(project: Path, style_ref):
    """Return verified common tokens; None keeps legacy diagrams unchanged."""
    if style_ref is None:
        return None
    inputs = []
    target = _binding(project, style_ref, inputs)
    _need(style_ref["path"] == STYLE_PATH, "Style reference must identify the shared program style")
    from scripts.output_provenance import current_origin
    origin = current_origin(project, target)
    _need(origin.get("status") == "tracked" and origin.get("family") != "anthropic", "Visual style needs tracked non-Claude persistent provenance")
    return validate_style(read(target))


def visual_style(project, ir, require=False):
    style = load_visual_style(project, ir.get("style_ref"))
    if require:
        _need(style is not None, "Diagram has no bound shared visual style")
    if style is None:
        return None, {"status": "not_assessed", "reason": "Diagram has no shared style_ref; legacy appearance is unchanged"}
    paper = Path(ir["output_stem"]).parts[1]
    _need(paper in style["paper_ids"], "Diagram is outside the shared style portfolio")
    return style, {"status": "static_tokens_checked", "style_ref": ir["style_ref"], "style_id": style["id"],
                   "final_size_human_inspection_required": True}


def _manuscript_sources(project, request, inputs):
    binding = request.get("manuscript")
    if binding is None:
        _need(request["phase"] == "planned", "Observed figure needs its current canonical manuscript")
        paper = project/"papers"/request["paper_id"]/"manuscript"
        _need(not any((paper/name).is_file() for name in ("main.tex", "main.docx")),
              "Existing canonical manuscript must be bound rather than reported unavailable")
        return [], "not_available"
    target = _binding(project, binding, inputs)
    from scripts.ref_verify_adapter import canonical_manuscript
    _need(target == canonical_manuscript(project/"papers"/request["paper_id"]), "Figure must bind the canonical manuscript")
    _need(target.suffix == ".tex", "Use the canonical TeX source for exact figure/text locators; DOCX paragraph mapping is not implemented")
    from scripts.tex_sources import expand
    expanded = expand(target, root=target.parent)
    bindings = []
    for source in sorted(expanded.files):
        _authored(project, source)
        item = {"path": source.relative_to(project).as_posix(), "sha256": sha(source)}
        _binding(project, item, inputs)
        bindings.append(item)
    return bindings, "source_locations_checked"


def _results(project, request, inputs, claims):
    results = request["result_sources"]
    _need(isinstance(results, list) and len(results) <= 100, "Result sources need a bounded list")
    if request["phase"] == "planned":
        _need(not results, "Planned diagrams cannot import observed result authority")
        return []
    _need(results, "Observed diagram needs executor-sealed actual results")
    from scripts.figure_lineage import run_seal
    sealed = {}
    bindings = []
    for row in results:
        _keys(row, {"path", "sha256", "run_id"})
        binding = {key: row[key] for key in ("path", "sha256")}
        _binding(project, binding, inputs)
        if row["run_id"] not in sealed:
            sealed[row["run_id"]] = run_seal(project, request["paper_id"], row["run_id"])
        seal = sealed[row["run_id"]]
        _need(binding in seal["outputs"], "Result file is not an exact successful executor output")
        for item in [seal["executor_receipt"], *([seal["scope"]] if seal.get("scope") else [])]:
            _binding(project, item, inputs)
        bindings.append(binding)
    used_runs = {row["run_id"] for row in results}
    for claim in claims:
        linked = {v.strip() for v in re.split(r"[;,]", claim.get("analysis_ids", "")) if v.strip()}
        _need(linked and linked <= used_runs and claim.get("support") in {"supported", "partially_supported", "not_supported", "contradicted"},
              "Observed claim must retain its registered analysis links and actual support status")
    return bindings


def build_report(project: Path, request: dict):
    required = {"schema_version", "id", "paper_id", "phase", "paper_contract", "claims", "diagram", "sources", "claim_ids",
                "gallery_report", "references", "problem", "contribution", "flow", "panels", "modules", "connections", "numeric_bindings", "result_sources"}
    _keys(request, required, {"manuscript"})
    _need(request["schema_version"] == "1.0" and request["phase"] in {"planned", "observed"}, "Unsupported figure story version or phase")
    _need(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", str(request["id"])), "Unsafe figure brief ID")
    paper = request["paper_id"]
    _need(re.fullmatch(r"P\d{2}", str(paper)), "Invalid paper ID")
    inputs = []
    _need(request["paper_contract"].get("path") == f"papers/{paper}/paper-contract.json" and request["claims"].get("path") == "claims/claim-evidence.csv", "Figure brief must bind canonical contract and claim matrix")
    contract = read(_binding(project, request["paper_contract"], inputs))
    _authored(project, project/request["paper_contract"]["path"])
    _need(contract.get("paper_id") == paper, "Contract paper differs from figure paper")
    claim_path = _binding(project, request["claims"], inputs)
    _authored(project, claim_path)
    rows = list(csv.DictReader(io.StringIO(claim_path.read_text(encoding="utf-8"))))
    ids = request["claim_ids"]
    _need(isinstance(ids, list) and ids and len(ids) == len(set(ids)) and all(isinstance(i, str) and i for i in ids), "Figure claim IDs need unique nonempty values")
    contracted = set(contract.get("independence", {}).get("unique_claim_ids", []))
    _need(set(ids) <= contracted, "Figure claim is not part of this paper's contracted contribution")
    selected = [row for row in rows if row.get("claim_id") in ids]
    _need(len(selected) == len(ids) and {row["claim_id"] for row in selected} == set(ids) and all(row.get("paper_id") == paper for row in selected), "Claim matrix omits, duplicates or misassigns the selected claims")
    diagram_path = _binding(project, request["diagram"], inputs)
    _authored(project, diagram_path)
    _need(request["diagram"]["path"].startswith(f"papers/{paper}/"), "Diagram source belongs to another paper")
    ir = read(diagram_path)
    from scripts.research_diagrams import validate
    validate(ir)
    _need(Path(ir["output_stem"]).parts[1] == paper and set(ir["claim_ids"]) == set(ids), "Diagram claim/paper scope differs from the brief")
    _, style_report = visual_style(project, ir)
    if ir.get("style_ref"):
        _binding(project, ir["style_ref"], inputs)
    _need(isinstance(request["sources"], list) and len(request["sources"]) <= 100, "Sources need a bounded list")
    allowed = [request["paper_contract"], request["claims"]]
    for source in request["sources"]:
        _binding(project, source, inputs)
        allowed.append(source)
    manuscripts, manuscript_status = _manuscript_sources(project, request, inputs)
    allowed += manuscripts
    results = _results(project, request, inputs, selected)
    allowed += results
    for field in ("problem", "contribution"):
        _keys(request[field], {"text", "text_locator"})
        _text(request[field]["text"], field)
        _anchor(project, request[field]["text_locator"], inputs, allowed)
    if request["phase"] == "planned":
        _need(re.search(r"\b(planned|proposed|expected)\b", ir["title"]+" "+ir["caption"], re.I), "Planned diagram must be labeled proposed/planned/expected in its visible title or caption")
    nodes = {node["id"]: node for node in ir["nodes"]}
    edges = {(edge["from"], edge["to"]): edge for edge in ir["edges"]}
    _keys(request["flow"], {"inputs", "mechanisms", "outputs"})
    flow = request["flow"]
    for group in flow.values():
        _need(isinstance(group, list) and group and len(group) == len(set(group)) and set(group) <= nodes.keys(), "Input/mechanism/output flow must name actual unique diagram nodes")
    _need(not(set(flow["inputs"]) & set(flow["outputs"])), "Input and output roles must be distinct")
    modules, connections = request["modules"], request["connections"]
    _need(isinstance(modules, list) and len(modules) == len(nodes), "Every actual module needs one text/phase mapping")
    _need(isinstance(connections, list) and len(connections) == len(edges), "Every actual arrow needs one text/phase mapping")
    node_seen, edge_seen = set(), set()
    for module in modules:
        _keys(module, {"node_id", "meaning", "phase", "text_locator"})
        node_id = module["node_id"]
        _need(node_id in nodes and node_id not in node_seen, "Module mapping is duplicated or absent from IR")
        node_seen.add(node_id)
        _text(module["meaning"], "Module meaning")
        _anchor(project, module["text_locator"], inputs, allowed)
        _check_phase(request, module, results)
        if module["phase"] == "planned":
            _need(re.search(r"\b(planned|proposed|expected)\b", nodes[node_id]["label"]+" "+ir["caption"], re.I), "Planned module must be visibly marked")
    for connection in connections:
        _keys(connection, {"from", "to", "kind", "meaning", "phase", "text_locator"})
        pair = (connection["from"], connection["to"])
        _need(pair in edges and pair not in edge_seen and connection["kind"] == edges[pair].get("kind", "control"), "Arrow mapping changes the actual topology or relationship kind")
        edge_seen.add(pair)
        _text(connection["meaning"], "Arrow meaning")
        _anchor(project, connection["text_locator"], inputs, allowed)
        _check_phase(request, connection, results)
    panels = request["panels"]
    _need(isinstance(panels, list) and 1 <= len(panels) <= 8, "Main figure needs one to eight purposeful panels")
    panel_ids, covered, covered_claims = set(), set(), set()
    for panel in panels:
        _keys(panel, {"id", "purpose", "node_ids", "claim_ids", "text_locator"})
        _need(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", str(panel["id"])) and panel["id"] not in panel_ids, "Panel IDs must be unique")
        panel_ids.add(panel["id"])
        _text(panel["purpose"], "Panel purpose")
        _need(isinstance(panel["node_ids"], list) and panel["node_ids"] and set(panel["node_ids"]) <= nodes.keys(), "Panel must map actual nodes")
        _need(isinstance(panel["claim_ids"], list) and panel["claim_ids"] and set(panel["claim_ids"]) <= set(ids), "Panel must map the paper's actual claims")
        _anchor(project, panel["text_locator"], inputs, allowed)
        if manuscripts:
            _need({k: panel["text_locator"][k] for k in ("path", "sha256")} in manuscripts and panel["text_locator"]["kind"] == "manuscript", "Existing manuscript needs actual panel-to-manuscript source locations")
        covered.update(panel["node_ids"])
        covered_claims.update(panel["claim_ids"])
    _need(covered == nodes.keys() and covered_claims == set(ids), "Panels omit an actual module or supported claim")
    _numeric(project, request, ir, inputs, allowed, results)
    _references(project, request, inputs)
    return {"schema_version": "1.0", "operation": "figure_story", "id": request["id"], "paper_id": paper,
            "status": "candidate", "phase": request["phase"], "request": request, "request_sha256": _digest(request),
            "inputs": inputs, "implementation_sha256": sha(Path(__file__)), "implementation": _implementation(), "visual_style": style_report,
            "manuscript_alignment": manuscript_status, "checks": {"actual_module_and_arrow_inventory": True,
                "located_text_quotes": True, "numeric_source_bindings": True, "gallery_metadata_bindings": True},
            "limits": {"scientific_approval": False, "semantic_alignment_requires_human_review": True,
                "reference_images_inspected": False, "external_results_reusable_as_our_results": False,
                "final_render_inspection_required": True, "paid_model_calls": 0}}


def _check_phase(request, entry, results):
    _need(entry["phase"] in PHASES, "Module/arrow must declare planned, method or observed phase")
    binding = {key: entry["text_locator"][key] for key in ("path", "sha256")}
    if entry["phase"] == "observed":
        _need(request["phase"] == "observed" and binding in results and entry["text_locator"]["kind"] == "result", "Observed relationship needs its exact recorded result source")
    elif entry["text_locator"]["kind"] == "result":
        _need(request["phase"] == "observed", "Planned figure cannot relabel observed evidence")


def _numeric(project, request, ir, inputs, allowed, results):
    visible = [ir["title"], ir["caption"], ir["alt_text"], request["problem"]["text"], request["contribution"]["text"]]
    visible += [n["label"]+" "+n.get("note", "") for n in ir["nodes"]]
    visible += [e.get("label", "") for e in ir["edges"]]
    visible += [p["purpose"] for p in request["panels"]]
    required = set(NUMBER.findall("\n".join(visible)))
    bindings = request["numeric_bindings"]
    _need(isinstance(bindings, list) and len(bindings) <= 200, "Numeric bindings require a bounded list")
    found = set()
    for entry in bindings:
        _keys(entry, {"value", "phase", "text_locator"})
        value = entry["value"]
        _need(isinstance(value, str) and NUMBER.fullmatch(value) and value not in found, "Numeric binding must identify one unique literal number")
        located = _anchor(project, entry["text_locator"], inputs, allowed)
        _need(value in NUMBER.findall(located) and value in NUMBER.findall(entry["text_locator"]["quote"]), "Figure number does not occur in its located source quotation")
        _check_phase(request, entry, results)
        found.add(value)
    _need(required == found, "Figure numeric inventory differs from its exact source bindings: " + ", ".join(sorted(required ^ found)))


def _references(project, request, inputs):
    gallery_path = _binding(project, request["gallery_report"], inputs)
    _need(request["gallery_report"]["path"].startswith("reports/figure-gallery/"), "References need a native figure-gallery search report")
    from scripts.figure_gallery import validate_search_report
    gallery = validate_search_report(project, request["gallery_report"]["path"])
    if gallery is None:
        gallery = read(gallery_path)
    candidates = gallery.get("candidates", [])
    references = request["references"]
    _need(isinstance(references, list) and 2 <= len(references) <= 10, "Compare two to ten external reference candidates")
    seen = set()
    for entry in references:
        _keys(entry, {"figure_id", "url", "metadata_sha256", "borrow_layout", "do_not_copy"})
        identifier = entry["figure_id"]
        _need(isinstance(identifier, str) and identifier not in seen, "Reference IDs must be unique")
        seen.add(identifier)
        matched = [row for row in candidates if row.get("id") == identifier]
        _need(len(matched) == 1, "Reference is absent or duplicated in the executed gallery search")
        candidate = matched[0]
        _need(entry["url"] == candidate.get("figure_url") and entry["metadata_sha256"] == candidate.get("metadata_sha256"), "Reference URL/metadata binding differs from the search candidate")
        _text(entry["borrow_layout"], "Reference layout transfer")
        _text(entry["do_not_copy"], "Reference non-transfer boundary")


def prepare(project: Path, request: dict):
    _cloud()
    project = project.resolve()
    report = build_report(project, request)
    target = path_in(project, f"reports/figure-story/{request['id']}.json", exists=False)
    if target.is_file():
        from scripts.output_provenance import current_origin
        origin = current_origin(project, target)
        _need(origin.get("status") == "tracked" and origin.get("provider") == "deterministic-control-plane"
              and origin.get("model") == MODULE, "Preserve changed figure brief before rebuilding")
        if read(target) == report:
            return {"path": target.relative_to(project).as_posix(), "sha256": sha(target), "reused": True, "report": report}
    write(target, report)
    record(project, [target], MODULE)
    return {"path": target.relative_to(project).as_posix(), "sha256": sha(target), "reused": False, "report": report}


def validate_saved_report(project: Path, report_path: Path):
    project = project.resolve()
    _need(report_path.resolve().is_relative_to(project), "Figure brief report escapes its project")
    report = read(report_path)
    _need(report == build_report(project, report["request"]), "Figure story report is stale or altered; prepare it from current inputs")
    from scripts.output_provenance import current_origin
    origin = current_origin(project, report_path)
    _need(origin.get("status") == "tracked" and origin.get("provider") == "deterministic-control-plane" and origin.get("model") == MODULE,
          "Figure brief needs current native deterministic provenance")
    return report


def execute(project: Path, operation: str, request: dict):
    _cloud()
    if operation == "prepare":
        return prepare(project, request)
    if operation == "validate":
        target = _binding(project, request, [])
        return {"path": request["path"], "sha256": sha(target), "report": validate_saved_report(project, target)}
    if operation == "style_prepare":
        style = validate_style(request)
        target = path_in(project, STYLE_PATH, exists=False)
        if not target.is_file() or read(target) != style:
            write(target, style)
            record(project, [target], MODULE)
        return {"path": STYLE_PATH, "sha256": sha(target), "status": "candidate_tokens", "scientific_approval": False}
    if operation == "style_validate":
        return {"style": load_visual_style(project, request), "status": "static_tokens_checked", "final_size_human_inspection_required": True}
    raise ValueError("Unknown figure story operation")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--operation", choices=["prepare", "validate", "style_prepare", "style_validate"], required=True)
    parser.add_argument("--request-file", required=True)
    args = parser.parse_args()
    _need(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", args.project), "Unsafe project slug")
    project = ROOT/"projects"/args.project
    result = execute(project, args.operation, read(path_in(project, args.request_file)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
