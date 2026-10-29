"""Content-bound vector panel reuse for the opt-in publication renderer.

Cache entries are ordinary JSON/SVG/PDF files, never Python objects. Final
outputs are always composed and audited again; a hit skips the panel drawer.
"""
from __future__ import annotations

import copy
import functools
import hashlib
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


class PanelCacheError(RuntimeError):
    pass


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@functools.lru_cache(maxsize=1)
def _installed_packages():
    """Installed dependencies are immutable during one executor process.

    Hash their actual bytes once, not once per figure. A new cloud process
    recomputes this identity rather than trusting a saved package/version label.
    """
    from packaging.requirements import Requirement
    packages = {}
    pending = ["matplotlib", "numpy", "pandas", "PyMuPDF"]
    while pending:
        name = pending.pop(0)
        identity = re.sub(r"[-_.]+", "-", name).lower()
        if identity in packages:
            continue
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise PanelCacheError(f"missing installed renderer dependency: {name}") from exc
        entries = []
        for relative in sorted(dist.files or [], key=str):
            if str(relative).endswith((".pyc", ".pyo")):
                continue
            path = Path(dist.locate_file(relative))
            if path.is_file():
                entries.append([str(relative), _digest(path)])
        if not entries:
            raise PanelCacheError(f"cannot bind installed renderer dependency: {name}")
        packages[identity] = {"version": dist.version,
                              "files_sha256": hashlib.sha256(_canonical(entries)).hexdigest()}
        for declared in dist.requires or []:
            dependency = Requirement(declared)
            if dependency.marker is None or dependency.marker.evaluate({"extra": ""}):
                pending.append(dependency.name)
    return packages


def renderer_dependencies(renderer, plt):
    """Recheck source, fonts, defaults and style on every render invocation."""
    sources = [Path(renderer.__file__), Path(__file__),
               Path(renderer.figure_recipes.__file__)]
    root = Path(renderer.__file__).resolve().parents[1]
    sources += [root / name for name in (
        "scripts/figure_layout.py", "scripts/figure_output_qa.py",
        "third_party/nature-figure/scripts/audit_panel_alignment.py",
        "third_party/nature-figure/scripts/audit_figure_collisions.py")]
    from matplotlib import font_manager
    fonts = sorted({font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight=weight))
                    for weight in ("normal", "medium", "semibold", "bold")})
    return {"sources": {path.relative_to(root).as_posix(): _digest(path) for path in sources},
            "packages": _installed_packages(), "python": sys.version,
            "fonts": [{"name": Path(path).name, "sha256": _digest(Path(path))} for path in fonts],
            "rcparams": {key: str(value) for key, value in plt.rcParams.items()},
            "palette": list(renderer.PALETTE), "markers": list(renderer.MARKERS),
            "linestyles": list(renderer.LINESTYLES)}


def _safe_svg(path, prefix):
    tree = ET.fromstring(path.read_bytes())
    ids = {node.get("id"): prefix + node.get("id") for node in tree.iter() if node.get("id")}
    for node in tree.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag in {"script", "foreignObject", "iframe", "object"}:
            raise PanelCacheError("unsafe content in cached panel SVG")
        for key, value in list(node.attrib.items()):
            local = key.rsplit("}", 1)[-1]
            if local.lower().startswith("on"):
                raise PanelCacheError("event handler in cached panel SVG")
            if local == "href" and not (value.startswith("#") or
                                          (tag == "image" and value.startswith("data:image/png;base64,"))):
                raise PanelCacheError("external resource in cached panel SVG")
            if local == "id":
                value = ids[value]
            elif local == "href" and value.startswith("#"):
                value = "#" + ids[value[1:]]
            value = re.sub(r"url\(#([^)]*)\)", lambda match: "url(#" + ids[match[1]] + ")", value)
            if re.search(r"url\((?!#)", value, flags=re.I):
                raise PanelCacheError("external style resource in cached panel SVG")
            node.set(key, value)
    return tree


def _load(project, entry, key, binding):
    receipt = entry / "panel.json"
    if not entry.exists():
        return None
    # A partially written or altered entry fails explicitly, rather than
    # disguising a corrupt checkpoint as an ordinary cache miss.
    if entry.is_symlink() or not receipt.is_file() or receipt.is_symlink():
        raise PanelCacheError("panel cache entry is incomplete or unsafe")
    try:
        try:
            from scripts.output_provenance import current_origin
        except ImportError:
            from output_provenance import current_origin
        origin = current_origin(project, receipt)
        if (origin.get("status") != "tracked" or origin.get("family") != "other" or
                origin.get("provider") != "deterministic-figure-panel-cache"):
            raise PanelCacheError("panel cache receipt lacks current executor provenance")
        record = json.loads(receipt.read_text(encoding="utf-8"))
        if record["key"] != key or record["binding"] != binding:
            raise PanelCacheError("panel cache binding mismatch")
        for suffix in ("svg", "pdf"):
            path = entry / ("panel." + suffix)
            if not path.is_file() or path.is_symlink() or _digest(path) != record["files"][suffix]:
                raise PanelCacheError("panel cache bytes changed: " + suffix)
        _safe_svg(entry / "panel.svg", "check-")
        metadata_hash = hashlib.sha256(_canonical(record["metadata"])).hexdigest()
        if metadata_hash != record["metadata_sha256"]:
            raise PanelCacheError("panel cache metadata changed")
        return record
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        raise PanelCacheError(f"invalid panel cache receipt: {exc}") from exc


def _bound_file(renderer, project, panel, spec, index, pd):
    path = renderer.safe_file(project, panel.get("data", spec.get("data")), f"panels[{index}].data")
    digest = _digest(path)
    frame = renderer._read_table(path, pd)
    if _digest(path) != digest:
        raise PanelCacheError("figure data changed while being read")
    return frame, {"path": path.relative_to(project).as_posix(), "sha256": digest,
                   "rows": int(len(frame)), "columns": [str(item) for item in frame.columns]}


def render_panels(project, spec, plt, np, pd, *, columns, rows, width, height):
    """Return the normal build inputs after independent vector-panel composition."""
    try:
        from scripts import publication_figures as renderer, figure_layout
        from scripts.figure_output_qa import audit_outputs
        from scripts.research_methods import load_vendored_module
    except ImportError:
        import publication_figures as renderer
        import figure_layout
        from figure_output_qa import audit_outputs
        from research_methods import load_vendored_module
    import fitz

    cache = project / "reports" / "figure-panel-cache"
    if cache.is_symlink() or any(parent.is_symlink() for parent in cache.parents if parent != project.parent):
        raise PanelCacheError("panel cache must be an ordinary executor-owned directory")
    cache.mkdir(parents=True, exist_ok=True)
    stem = renderer.safe_file(project, spec.get("output_stem"), "output_stem")
    if not re.fullmatch(r"papers/P[0-9]{2}/figures/.+", stem.relative_to(project).as_posix()):
        raise PanelCacheError("output_stem must belong to a valid paper's figures directory")
    stem.parent.mkdir(parents=True, exist_ok=True)
    dependencies = renderer_dependencies(renderer, plt)
    panel_width, panel_height = width / columns, height / rows
    # Deliberately fixed physical gutters isolate panel drawing dependencies.
    # This opt-in layout differs from the ordinary constrained-layout renderer.
    axes_rect = [0.20, 0.22, 0.52, 0.62]
    data_records, entries, decisions, labels, warnings = {}, [], [], [], []
    source_records = []
    for index, panel in enumerate(spec["panels"]):
        frame, data = _bound_file(renderer, project, panel, spec, index, pd)
        data_records[data["path"]] = data
        binding = {"schema_version": "1.0", "data": data, "panel": panel,
                   "style": spec["style"], "dependencies": dependencies,
                   "layout": {"width_in": panel_width, "height_in": panel_height,
                              "axes_rect": axes_rect, "label": chr(ord("a") + index),
                              "dpi": spec["dpi"]}}
        key = hashlib.sha256(_canonical(binding)).hexdigest()
        entry = cache / key
        record = _load(project, entry, key, binding)
        hit = record is not None
        if record is None:
            entry.mkdir()
            fig = plt.figure(figsize=(panel_width, panel_height))
            try:
                ax = fig.add_axes(axes_rect)
                renderer._draw_panel(ax, panel, frame, np, pd, index)
                measured = figure_layout.inspect_panels(fig)["manifest"]
                metadata = {"expected_labels": renderer.actual_figure_labels(fig),
                            "layout_warnings": renderer.inspect_layout(fig),
                            "manifest": measured}
                for suffix in ("svg", "pdf"):
                    figure_metadata = {"Creator": "Doctoral Research OS"}
                    figure_metadata.update({"Date": None} if suffix == "svg" else
                                           {"CreationDate": None, "ModDate": None})
                    fig.savefig(entry / ("panel." + suffix), metadata=figure_metadata)
                record = {"schema_version": "1.0", "key": key, "binding": binding,
                          "metadata": metadata,
                          "metadata_sha256": hashlib.sha256(_canonical(metadata)).hexdigest(),
                          "files": {suffix: _digest(entry / ("panel." + suffix)) for suffix in ("svg", "pdf")}}
                (entry / "panel.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            finally:
                plt.close(fig)
            try:
                from scripts.output_provenance import record_model_writes
            except ImportError:
                from output_provenance import record_model_writes
            record_model_writes(project, [entry / "panel.json"], family="other",
                                provider="deterministic-figure-panel-cache",
                                model="scripts/figure_panel_cache.py", role="figure-panel-cache",
                                run_id="panel-" + key)
        entries.append((entry, record))
        decisions.append({"panel": index + 1, "key": key, "reused": hit,
                          "receipt": {"path": (entry / "panel.json").relative_to(project).as_posix(),
                                      "sha256": _digest(entry / "panel.json")},
                          "files": record["files"], "data": data})
        labels.extend(record["metadata"]["expected_labels"])
        warnings.extend(f"panel {index+1}: {item}" for item in record["metadata"]["layout_warnings"])
        if spec.get("source_data_export", False):
            import shutil
            source = project / data["path"]
            target = stem.with_name(f"{stem.name}-panel-{index+1}-source{source.suffix}")
            shutil.copyfile(source, target)
            source_records.append({"path": target.relative_to(project).as_posix(), "sha256": _digest(target)})

    svg_ns = "http://www.w3.org/2000/svg"
    ET.register_namespace("", svg_ns)
    svg = ET.Element("{" + svg_ns + "}svg", {"width": f"{width*72}pt", "height": f"{height*72}pt",
                     "viewBox": f"0 0 {width*72} {height*72}", "version": "1.1"})
    manifest = {"schema_version": 1, "backend": "python-matplotlib-vector-panel-composition",
                "figure": {"width_pt": width*72, "height_pt": height*72}, "panels": [], "exemptions": []}
    with fitz.open() as composed:
        page = composed.new_page(width=width*72, height=height*72)
        for index, (entry, record) in enumerate(entries):
            col, row = index % columns, index // columns
            x, y = col*panel_width*72, row*panel_height*72
            child = _safe_svg(entry / "panel.svg", f"panel-{index+1}-")
            child.set("x", str(x))
            child.set("y", str(y))
            # Nested SVG lengths must be in the parent's viewBox user units.
            # Retaining Matplotlib's "pt" suffix would apply CSS's 4/3 unit
            # conversion again, making SVG panels larger than their PDF cells.
            child.set("width", str(panel_width*72))
            child.set("height", str(panel_height*72))
            svg.append(child)
            with fitz.open(entry / "panel.pdf") as source:
                page.show_pdf_page(fitz.Rect(x, y, x+panel_width*72, y+panel_height*72), source, 0)
            bottom = (rows-row-1)*panel_height*72
            for item in record["metadata"]["manifest"]["panels"]:
                measured = copy.deepcopy(item)
                measured["id"] = f"panel-{index+1}-{item['id']}"
                measured["bbox_pt"] = [item["bbox_pt"][0]+x, item["bbox_pt"][1]+bottom,
                                       item["bbox_pt"][2]+x, item["bbox_pt"][3]+bottom]
                if "panel_label_anchor_pt" in item:
                    anchor = item["panel_label_anchor_pt"]
                    measured["panel_label_anchor_pt"] = [anchor[0]+x, anchor[1]+bottom]
                measured.update(grid_id="composed", row_start=row, row_stop=row+1, col_start=col, col_stop=col+1)
                manifest["panels"].append(measured)
        composed.set_metadata({"creator": "Doctoral Research OS"})
        composed.save(stem.with_suffix(".pdf"), garbage=4, deflate=True, no_new_id=True)
        if "png" in spec["formats"]:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(spec["dpi"]/72, spec["dpi"]/72), alpha=False)
            pixmap.set_dpi(spec["dpi"], spec["dpi"])
            pixmap.save(stem.with_suffix(".png"))
    ET.ElementTree(svg).write(stem.with_suffix(".svg"), encoding="utf-8", xml_declaration=True)
    outputs = [{"path": stem.with_suffix("."+suffix).relative_to(project).as_posix(), "format": suffix,
                "sha256": _digest(stem.with_suffix("."+suffix)), "size": stem.with_suffix("."+suffix).stat().st_size}
               for suffix in spec["formats"]]
    helper = load_vendored_module(figure_layout.ALIGNMENT)
    alignment_report = helper.audit_layout_manifest(manifest)
    alignment = {"manifest": manifest, "report": alignment_report, "pass": helper.exit_code(alignment_report) == 0}
    paper = project / "papers" / stem.relative_to(project).parts[1]
    audit_path = (paper / "reviews" / "figure-layout" / stem.relative_to(paper / "figures")).with_suffix(".json")
    layout_audit = figure_layout.save_audit(project, stem.with_suffix(".pdf"), audit_path, alignment)
    qa = audit_outputs(project, outputs, expected_text=labels, final_width_mm=spec.get("final_width_mm"))
    return {"output_stem": stem, "data_records": data_records, "source_records": source_records,
            "outputs": outputs, "expected_labels": labels, "layout_warnings": warnings,
            "layout_audit": layout_audit, "output_qa": qa,
            "panel_cache": {"enabled": True, "composition": "editable-svg-and-pdf", "panels": decisions,
                            "execution_scope": "downstream_rendering",
                            "experiment_reproduction_assessed": False,
                            "drawn": sum(not row["reused"] for row in decisions),
                            "reused": sum(row["reused"] for row in decisions)}}


def validate_build(project, build):
    """Read-only final validation of the exact reused panel sources and bytes."""
    cache = build.get("panel_cache", {})
    if not cache.get("enabled"):
        return []
    try:
        try:
            from scripts import publication_figures as renderer
        except ImportError:
            import publication_figures as renderer
        plt, _np, _pd = renderer._imports()
        current = renderer_dependencies(renderer, plt)
        for row in cache["panels"]:
            receipt = renderer.safe_file(project, row["receipt"]["path"], "panel receipt")
            expected = project / "reports" / "figure-panel-cache" / row["key"] / "panel.json"
            if receipt != expected or _digest(receipt) != row["receipt"]["sha256"]:
                raise PanelCacheError("cached panel receipt changed or escaped its key")
            record = json.loads(receipt.read_text(encoding="utf-8"))
            if hashlib.sha256(_canonical(record["binding"])).hexdigest() != row["key"]:
                raise PanelCacheError("cached panel key differs from its actual binding")
            _load(project, receipt.parent, row["key"], record["binding"])
            # rcParams are an invocation snapshot, not mutable G5 process globals.
            # Rendering compares the full snapshot; final validation verifies the
            # installed renderer/style sources and font/runtime identities.
            bound = record["binding"]["dependencies"]
            if any(bound.get(key) != value for key, value in current.items() if key != "rcparams"):
                raise PanelCacheError("panel renderer/style/runtime dependency changed; rebuild figure")
        return []
    except (OSError, ValueError, KeyError, TypeError, PanelCacheError) as exc:
        return [f"panel cache validation failed: {exc}"]
