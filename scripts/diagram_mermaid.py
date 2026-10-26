"""Export the existing evidence-bound diagram topology as editable Mermaid.

No prose-to-causal inference, JavaScript renderer, model call or figure approval.
"""
from __future__ import annotations

import html
from pathlib import Path

from scripts import editable_figures, research_diagrams, literature_workbench as wb
from scripts.research_artifacts import path_in, read, record, sha, write

OUTPUT = "reports/diagram-mermaid"


def text(ir: dict, *, node_phases=None, edge_phases=None) -> str:
    research_diagrams.validate(ir)
    identifiers = {node["id"]: "n" + str(i) for i, node in enumerate(ir["nodes"])}
    def label(value):
        return html.escape(value, quote=True).replace("|", "&#124;").replace("\n", " ")
    rows = ["flowchart LR", "  %% " + label(ir["title"]), "  %% Relationship labels preserve the source IR kinds; no scientific approval."]
    for node in ir["nodes"]:
        phase = node_phases[node["id"]] if node_phases is not None else "unreviewed"
        value = label(phase + ": " + node.get("kind", "process") + ": " + node["label"])
        rows.append(f'  {identifiers[node["id"]]}["{value}"]')
    for edge in ir["edges"]:
        kind = edge.get("kind", "control")
        marker = "==>" if kind == "causal" else "-.-" if kind == "association" else "-->"
        phase = edge_phases[(edge["from"], edge["to"])] if edge_phases is not None else "unreviewed"
        value = label(phase + ": " + kind + (": " + edge["label"] if edge.get("label") else ""))
        rows.append(f'  {identifiers[edge["from"]]} {marker}|"{value}"| {identifiers[edge["to"]]}')
    return "\n".join(rows) + "\n"


def build(project: Path, request: dict) -> dict:
    if (not isinstance(request, dict) or set(request) != {"schema_version", "id", "source", "story_ref"}
            or request.get("schema_version") != "1.0"):
        raise ValueError("Mermaid export needs id, exact diagram source and existing story_ref")
    identifier = wb._id(request["id"], "Mermaid export ID")
    binding = request["source"]
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("diagram needs an exact source binding")
    source = editable_figures._bound_file(project, binding, "source")
    from scripts.output_provenance import current_origin
    origin = current_origin(project, source)
    if origin.get("status") != "tracked" or origin.get("family") == "anthropic":
        raise ValueError("diagram source needs current non-Claude author provenance")
    if not isinstance(request["story_ref"], dict):
        raise ValueError("Mermaid needs an existing source-bound figure brief")
    alignment = editable_figures._story_alignment(project, request["story_ref"], binding)
    ir = wb._json(source.read_bytes())
    story = read(path_in(project, request["story_ref"]["path"]))
    code = text(ir, node_phases={m["node_id"]: m["phase"] for m in story["request"]["modules"]},
        edge_phases={(e["from"], e["to"]): e["phase"] for e in story["request"]["connections"]})
    nodes = [{"id": n["id"], "kind": n.get("kind", "process"), "label": n["label"]} for n in ir["nodes"]]
    connections = {(e["from"], e["to"]): e for e in story["request"]["connections"]}
    edges = [{"from": e["from"], "to": e["to"], "kind": e.get("kind", "control"),
              "label": e.get("label"), "source_mapping": connections[(e["from"], e["to"])]}
             for e in ir["edges"]]
    return {"schema_version": "1.0", "id": identifier, "kind": "editable_mermaid_from_typed_ir",
        "request": request, "nodes": nodes, "edges": edges, "mermaid": code,
        "phase": story["phase"], "caption": ir["caption"], "story_alignment": alignment,
        "confirmation_required": [{"from": e["from"], "to": e["to"], "kind": e["kind"],
            "reason": "Confirm scientific meaning and applicability of the located relationship."} for e in edges],
        "topology_and_kinds_preserved": True, "scientific_approval": False,
        "mermaid_runtime_validation": "not_rendered", "human_visual_review_required": True,
        "model_call_made": False, "implementation_sha256": sha(Path(__file__))}


def refresh(project: Path, request_path="program/diagram-mermaid.json") -> dict:
    if not isinstance(request_path, str) or not request_path.startswith("program/"):
        raise ValueError("Mermaid request belongs under program/")
    source = path_in(project, request_path)
    if source.stat().st_size > 64000:
        raise ValueError("Mermaid request exceeds 64 KB")
    report = build(project, wb._json(source.read_bytes()))
    directory = path_in(project, OUTPUT + "/" + report["id"], exists=False)
    paths = [directory / "report.json", directory / "diagram.mmd", directory / "index.html"]
    for target in paths:
        if target.exists():
            from scripts.output_provenance import current_origin
            origin = current_origin(project, target)
            if origin.get("status") != "tracked" or origin.get("model") != "scripts/diagram_mermaid.py":
                raise ValueError("preserve altered Mermaid output before rebuilding")
    write(paths[0], report)
    paths[1].write_text(report["mermaid"], encoding="utf-8")
    paths[2].write_text('<!doctype html><meta charset="utf-8"><title>Editable Mermaid source</title>' +
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'">' +
        '<h1>Editable research diagram</h1><p>' + html.escape(report["caption"]) + '</p><p>Same source topology and relation kinds. Confirm scientific meaning and inspect the final rendered diagram.</p>' +
        '<a href="diagram.mmd">Download editable Mermaid</a><pre>' + html.escape(report["mermaid"]) + '</pre>', encoding="utf-8")
    manifest = {"schema_version": "1.0", "request": {"path": request_path, "sha256": sha(source)},
        "outputs": [{"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in paths],
        "implementation_sha256": sha(Path(__file__))}
    write(directory / "manifest.json", manifest)
    record(project, [*paths, directory / "manifest.json"], "scripts/diagram_mermaid.py")
    return {"report": paths[0].relative_to(project).as_posix(), "mermaid": paths[1].relative_to(project).as_posix(),
            "html": paths[2].relative_to(project).as_posix(), "scientific_approval": False, "paid_calls": 0}


def validate_saved_report(project: Path, request_path="program/diagram-mermaid.json") -> dict:
    request = wb._json(path_in(project, request_path).read_bytes())
    fresh = build(project, request)
    directory = path_in(project, OUTPUT + "/" + fresh["id"], exists=False)
    manifest_path = directory / "manifest.json"
    from scripts.output_provenance import current_origin
    origin = current_origin(project, manifest_path)
    if origin.get("status") != "tracked" or origin.get("model") != "scripts/diagram_mermaid.py":
        raise ValueError("Mermaid manifest has no current deterministic provenance")
    manifest = read(manifest_path)
    if manifest["request"] != {"path": request_path, "sha256": sha(path_in(project, request_path))}:
        raise ValueError("Mermaid request changed")
    if read(directory / "report.json") != fresh:
        raise ValueError("Mermaid source, evidence or report changed")
    expected = {(directory / name).relative_to(project).as_posix() for name in ("report.json", "diagram.mmd", "index.html")}
    if {item.get("path") for item in manifest["outputs"]} != expected or len(manifest["outputs"]) != 3:
        raise ValueError("Mermaid output inventory changed")
    if (directory / "diagram.mmd").read_text(encoding="utf-8") != fresh["mermaid"]:
        raise ValueError("Mermaid code no longer matches the source topology")
    for item in manifest["outputs"]:
        if sha(path_in(project, item["path"])) != item["sha256"]:
            raise ValueError("Mermaid output changed")
    return {"valid": True, "scientific_approval": False}
