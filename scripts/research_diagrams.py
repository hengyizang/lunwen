#!/usr/bin/env python3
"""Compile a typed research-diagram IR into editable JSON/HTML and SVG/PDF/PNG.

The IR is an author-checked description; this renderer does not infer a study
design or manufacture a mechanistic relationship from prose.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from scripts import output_provenance
    from scripts.publication_figures import PROJECTS_ROOT, FigureSpecError, _english_text, safe_file, sha256_file
except ImportError:
    import output_provenance  # type: ignore
    from publication_figures import PROJECTS_ROOT, FigureSpecError, _english_text, safe_file, sha256_file  # type: ignore


TYPES = {"architecture", "workflow", "sequence", "dataflow", "lifecycle", "mechanism"}
PALETTE = ("#D9EDF1", "#E8E5F1", "#FAEAD8", "#DCEDE5", "#E7EAF0")


def validate(ir: dict[str, Any]) -> None:
    if ir.get("schema_version") != "1.0" or ir.get("type") not in TYPES:
        raise FigureSpecError("diagram requires schema_version 1.0 and a supported type")
    for field in ("title", "caption", "alt_text"):
        _english_text(ir.get(field), field)
    if not isinstance(ir.get("claim_ids"), list) or not ir["claim_ids"]:
        raise FigureSpecError("diagram requires claim_ids")
    nodes, edges = ir.get("nodes"), ir.get("edges")
    if not isinstance(nodes, list) or not 2 <= len(nodes) <= 32:
        raise FigureSpecError("diagram requires 2–32 nodes")
    if not isinstance(edges, list) or len(edges) > 64:
        raise FigureSpecError("diagram supports at most 64 edges")
    ids = set()
    positioned = ["layer" in node for node in nodes if isinstance(node,dict)]
    if any(positioned) and not all(positioned):
        raise FigureSpecError("explicit diagram layout needs a layer for every node")
    placements = set()
    for node in nodes:
        if not isinstance(node, dict) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", str(node.get("id", ""))):
            raise FigureSpecError("node id must be an alphanumeric identifier")
        if node["id"] in ids:
            raise FigureSpecError("duplicate node id")
        ids.add(node["id"])
        label = _english_text(node.get("label"), "node label")
        if len(label) > 80:
            raise FigureSpecError("node labels must be at most 80 characters; use a note")
        if node.get("note"):
            _english_text(node["note"], "note")
        if "layer" in node:
            layer, rank = node["layer"], node.get("rank", 0)
            if (not isinstance(layer,int) or isinstance(layer,bool) or not 0<=layer<=7 or
                    not isinstance(rank,int) or isinstance(rank,bool) or not 0<=rank<=7):
                raise FigureSpecError("layer and rank must be 0..7 integers")
            if (layer,rank) in placements:
                raise FigureSpecError("diagram nodes cannot occupy the same layer/rank")
            placements.add((layer,rank))
    seen = set()
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("from") not in ids or edge.get("to") not in ids or edge["from"] == edge["to"]:
            raise FigureSpecError("edge endpoints must be distinct existing nodes")
        pair = (edge["from"], edge["to"])
        if pair in seen:
            raise FigureSpecError("duplicate directed edge")
        seen.add(pair)
        if edge.get("label"):
            _english_text(edge["label"], "edge label")
    if not re.fullmatch(r"papers/P[0-9]{2}/figures/[A-Za-z0-9_-]+", str(ir.get("output_stem", ""))):
        raise FigureSpecError("output_stem must be papers/Pxx/figures/<name>")


def layout(ir: dict[str, Any]) -> dict[str, tuple[float, float]]:
    nodes = ir["nodes"]
    if all("layer" in node for node in nodes):
        return {node["id"]: (float(node["layer"]),-float(node.get("rank",0))) for node in nodes}
    # Explicit order remains deterministic and editable; no more than 4 nodes per row.
    columns = min(4, max(2, int(math.ceil(math.sqrt(len(nodes))))))
    return {node["id"]: (index % columns, -(index // columns))
            for index, node in enumerate(nodes)}


def render(project: Path, ir_path: Path) -> dict[str, Any]:
    project = project.resolve(); ir_path = ir_path.resolve()
    if project not in ir_path.parents or not ir_path.is_file():
        raise FigureSpecError("IR must be an existing project-local JSON file")
    ir = json.loads(ir_path.read_text(encoding="utf-8")); validate(ir)
    try:
        from scripts.publication_figures import _imports, inspect_layout
    except ImportError:
        from publication_figures import _imports, inspect_layout  # type: ignore
    plt, _, _ = _imports()
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    positions = layout(ir)
    columns = max(int(point[0]) for point in positions.values()) + 1
    rows = -min(int(point[1]) for point in positions.values()) + 1
    fig, ax = plt.subplots(figsize=(max(6, columns*2.2), max(3, rows*1.75+1)), constrained_layout=True)
    ax.set(xlim=(-.85, columns-.15), ylim=(-rows+.35, .9)); ax.axis("off")
    for index, node in enumerate(ir["nodes"]):
        x, y = positions[node["id"]]
        ax.add_patch(FancyBboxPatch((x-.36, y-.22), .72, .44, boxstyle="round,pad=0.06",
                                    facecolor=PALETTE[index % len(PALETTE)], edgecolor="#376175", linewidth=1.1, zorder=2))
        label = node["label"]
        if len(label) > 19 and " " in label:
            words, lines, current = label.split(), [], ""
            for word in words:
                if current and len(current)+1+len(word) > 18:
                    lines.append(current); current = word
                else:
                    current = f"{current} {word}".strip()
            lines.append(current)
            label = "\n".join(lines)
            if len(lines) > 3:
                raise FigureSpecError(f"node {node['id']} label is too long for the box")
        ax.text(x, y, label, ha="center", va="center", fontsize=8, color="#142C38", zorder=3)
    for edge in ir["edges"]:
        x0, y0 = positions[edge["from"]]; x1, y1 = positions[edge["to"]]
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>",
                                     mutation_scale=11, linewidth=1.2, color="#416779",
                                     shrinkA=31, shrinkB=31, connectionstyle="arc3,rad=.13", zorder=1))
        if edge.get("label"):
            ax.text((x0+x1)/2, (y0+y1)/2+.08, edge["label"], ha="center", fontsize=6.5,
                    bbox={"facecolor":"white","edgecolor":"none","alpha":.85}, zorder=4)
    ax.set_title(ir["title"], loc="left", fontsize=11, pad=10)
    output = safe_file(project, ir["output_stem"], "output_stem")
    output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        layout_warnings = inspect_layout(fig)
        for fmt in ("svg", "pdf", "png"):
            path = output.with_suffix("." + fmt)
            fig.savefig(path, dpi=350 if fmt == "png" else None, bbox_inches="tight",
                        metadata={"Creator":"Doctoral Research OS"} if fmt == "pdf" else None)
            results.append({"path": path.relative_to(project).as_posix(), "sha256": sha256_file(path)})
    finally:
        plt.close(fig)
    svg = output.with_suffix(".svg").read_text(encoding="utf-8")
    # Static HTML wrapper is local-only and imports no JavaScript or remote fonts.
    html = output.with_suffix(".html")
    html.write_text("<!doctype html><meta charset=\"utf-8\"><title>Research diagram</title>\n" + re.sub(r"^<\?xml[^>]*>\s*", "", svg),
                    encoding="utf-8")
    canonical_ir = output.with_suffix(".layout.json")
    canonical_ir.write_text(json.dumps({"schema_version":"1.0","source_sha256":sha256_file(ir_path),
                                        "node_positions":positions}, indent=2)+"\n", encoding="utf-8")
    wrapper = output.with_suffix(".renderer.py")
    wrapper.write_text(
        "#!/usr/bin/env python3\nfrom pathlib import Path\nimport subprocess\nimport sys\n"
        "repo = next(p for p in Path(__file__).resolve().parents if (p/'scripts'/'research_diagrams.py').is_file())\n"
        f"subprocess.run([sys.executable, str(repo/'scripts'/'research_diagrams.py'), '--project', {project.name!r}, "
        f"'--spec', {ir_path.relative_to(project).as_posix()!r}], check=True)\n", encoding="utf-8")
    output_provenance.record_model_writes(project,[html, canonical_ir, wrapper],family="other",
        provider="deterministic-local-renderer",model="scripts/research_diagrams.py",role="diagram-control",
        run_id="diagram-"+hashlib.sha256(ir_path.read_bytes()).hexdigest()[:16])
    return {"type": ir["type"], "outputs": results, "html": html.relative_to(project).as_posix(),
            "layout": canonical_ir.relative_to(project).as_posix(), "wrapper": wrapper.relative_to(project).as_posix(),
            "caption": ir["caption"], "alt_text": ir["alt_text"], "claim_ids": ir["claim_ids"],
            "human_layout_check_required": True, "layout_warnings": layout_warnings}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", required=True); p.add_argument("--spec", required=True)
    p.add_argument("--record", action="store_true"); p.add_argument("--language-checked-by")
    args = p.parse_args(); project = PROJECTS_ROOT/args.project
    try:
        report = render(project, safe_file(project, args.spec, "spec"))
        if args.record:
            if not args.language_checked_by:
                raise FigureSpecError("--record needs --language-checked-by")
            try:
                from scripts.figure_provenance import record_figure
            except ImportError:
                from figure_provenance import record_figure  # type: ignore
            paper = Path(report["outputs"][0]["path"]).parts[1]
            for output in report["outputs"]:
                record_figure(project,paper,output["path"],"conceptual_diagram",report["wrapper"],[],[],args.spec,args.language_checked_by)
    except (FigureSpecError, ValueError, OSError) as exc:
        p.error(str(exc))
    print(json.dumps(report,indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
