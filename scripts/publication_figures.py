#!/usr/bin/env python3
"""Render polished, deterministic, journal-ready figures from recorded data.

The renderer is specification driven: models may propose a JSON design, but
Python reads the real table and creates vector plus high-resolution outputs.
It intentionally rejects 3-D chart junk, missing axis semantics and unbound
data.  Visual polish never replaces uncertainty or provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import numbers
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
try:
    from scripts import figure_recipes
except ImportError:
    import figure_recipes  # type: ignore

KINDS = {"line", "scatter", "bar", "heatmap", "forest"} | figure_recipes.KINDS
FORMATS = {"png", "pdf", "svg"}
PALETTE = (
    "#005F73",
    "#EE9B00",
    "#0A9396",
    "#BB3E03",
    "#6D597A",
    "#3A86FF",
    "#8A5A44",
    "#2A9D8F",
)
MARKERS = ("o", "s", "^", "D", "P", "X", "v", "<")
LINESTYLES = ("-", "--", "-.", ":")
CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


class FigureSpecError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_file(project: Path, relative: Any, field: str) -> Path:
    value = Path(str(relative or ""))
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise FigureSpecError(f"{field} must be a safe project-relative path")
    result = (project / value).resolve()
    root = project.resolve()
    if result == root or root not in result.parents:
        raise FigureSpecError(f"{field} escapes the project")
    return result


def _english_text(value: Any, field: str, *, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise FigureSpecError(f"{field} must be a non-empty English string")
    result = value.strip()
    if CJK_RE.search(result):
        raise FigureSpecError(f"{field} must use English manuscript text")
    return result


def validate_spec(spec: dict[str, Any]) -> None:
    if spec.get("schema_version") != "1.0":
        raise FigureSpecError("schema_version must be 1.0")
    if spec.get("style") not in {"technical", "minimal", "high-impact"}:
        raise FigureSpecError("style must be technical, minimal or high-impact")
    formats = spec.get("formats")
    if not isinstance(formats, list) or not {"svg", "pdf"}.issubset(set(formats)):
        raise FigureSpecError("formats must include SVG and PDF vector outputs")
    if any(item not in FORMATS for item in formats):
        raise FigureSpecError("unsupported output format")
    dpi = spec.get("dpi")
    if not isinstance(dpi, int) or isinstance(dpi, bool) or dpi < 300:
        raise FigureSpecError("dpi must be an integer of at least 300")
    _english_text(spec.get("caption"), "caption")
    _english_text(spec.get("alt_text"), "alt_text")
    claims = spec.get("claim_ids")
    if not isinstance(claims, list) or not claims or any(not str(item).strip() for item in claims):
        raise FigureSpecError("claim_ids must contain at least one claim")
    panels = spec.get("panels")
    if not isinstance(panels, list) or not panels or len(panels) > 6:
        raise FigureSpecError("panels must contain one to six panels")
    for index, panel in enumerate(panels):
        prefix = f"panels[{index}]"
        if not isinstance(panel, dict) or panel.get("kind") not in KINDS:
            raise FigureSpecError(f"{prefix}.kind is unsupported")
        _english_text(panel.get("title", ""), f"{prefix}.title", required=False)
        for optional_label in ("legend_title", "colorbar_label"):
            if panel.get(optional_label) is not None:
                _english_text(panel.get(optional_label), f"{prefix}.{optional_label}")
        for field in ("x", "y", "xlabel", "ylabel"):
            if (panel.get("kind") == "forest" and field == "x") or (panel.get("kind") == "correlation" and field in {"x", "y"}):
                continue
            _english_text(panel.get(field), f"{prefix}.{field}")
        if panel.get("kind") in {"sankey", "confusion"}:
            _english_text(panel.get("value"), f"{prefix}.value")
        if panel.get("kind") == "dumbbell":
            _english_text(panel.get("end"), f"{prefix}.end")
        if panel.get("kind") == "forest":
            for field in ("label", "ci_low", "ci_high"):
                _english_text(panel.get(field), f"{prefix}.{field}")
        if panel.get("kind") == "heatmap":
            _english_text(panel.get("value"), f"{prefix}.value")
        uncertainty = panel.get("uncertainty")
        if uncertainty is not None:
            if panel.get("kind") in {"heatmap", "forest"}:
                raise FigureSpecError(
                    f"{prefix}.uncertainty is not supported for {panel.get('kind')} panels"
                )
            if not isinstance(uncertainty, dict):
                raise FigureSpecError(f"{prefix}.uncertainty must be an object")
            _english_text(uncertainty.get("lower"), f"{prefix}.uncertainty.lower")
            _english_text(uncertainty.get("upper"), f"{prefix}.uncertainty.upper")
        if panel.get("kind") == "errorbar" and uncertainty is None:
            raise FigureSpecError(f"{prefix}.uncertainty is required for errorbar")
    if not isinstance(spec.get("source_data_export", False), bool):
        raise FigureSpecError("source_data_export must be boolean")


def _imports() -> tuple[Any, Any, Any]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import pandas as pd
    except ImportError as exc:
        raise FigureSpecError(
            "publication figures require matplotlib, numpy and pandas; "
            "run bootstrap-wsl.sh --with-figures"
        ) from exc
    return plt, np, pd


def _read_table(path: Path, pd: Any) -> Any:
    if not path.is_file() or path.is_symlink():
        raise FigureSpecError(f"data file is missing: {path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix == ".tsv":
        frame = pd.read_csv(path, sep="\t")
    elif suffix == ".json":
        frame = pd.read_json(path)
    else:
        raise FigureSpecError("figure data must be CSV, TSV or JSON")
    if frame.empty:
        raise FigureSpecError("figure data table is empty")
    return frame


def _groups(frame: Any, hue: str | None) -> list[tuple[str, Any]]:
    if hue:
        if hue not in frame.columns:
            raise FigureSpecError(f"missing hue column: {hue}")
        if frame[hue].astype(str).map(lambda value: bool(CJK_RE.search(value))).any():
            raise FigureSpecError(f"hue values must use English manuscript text: {hue}")
        return [(str(name), group.copy()) for name, group in frame.groupby(hue, sort=True)]
    return [("", frame.copy())]


def _numeric(frame: Any, fields: list[str]) -> None:
    for field in fields:
        if field not in frame.columns:
            raise FigureSpecError(f"missing data column: {field}")
        if not frame[field].map(
            lambda value: isinstance(value, numbers.Real)
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        ).all():
            raise FigureSpecError(f"column must contain finite numeric values: {field}")


def _decorate(ax: Any, panel: dict[str, Any], label: str) -> None:
    ax.set_xlabel(panel["xlabel"], fontweight="medium")
    ax.set_ylabel(panel["ylabel"], fontweight="medium")
    if panel.get("title"):
        ax.set_title(panel["title"], loc="left", fontweight="semibold", pad=10)
    ax.text(
        -0.11,
        1.04,
        label,
        transform=ax.transAxes,
        fontsize=10,
        fontweight="bold",
        va="bottom",
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#D8DEE9", linewidth=0.6, alpha=0.65, zorder=0)
    ax.set_axisbelow(True)


def _draw_standard(ax: Any, panel: dict[str, Any], frame: Any, np: Any) -> None:
    kind = panel["kind"]
    x, y = panel["x"], panel["y"]
    hue = panel.get("hue")
    uncertainty = panel.get("uncertainty") or {}
    numeric = [y]
    if kind in {"line", "scatter"}:
        numeric.append(x)
    if uncertainty:
        numeric.extend([uncertainty["lower"], uncertainty["upper"]])
    _numeric(frame, numeric)
    groups = _groups(frame, hue)
    if len(groups) > len(PALETTE):
        raise FigureSpecError("a panel may contain at most eight visual groups")
    if kind == "bar":
        categories = sorted(frame[x].astype(str).unique())
        if any(CJK_RE.search(item) for item in categories):
            raise FigureSpecError(f"bar category values must use English manuscript text: {x}")
        width = 0.76 / max(1, len(groups))
        positions = np.arange(len(categories), dtype=float)
        for index, (name, group) in enumerate(groups):
            keyed = group.assign(_category=group[x].astype(str)).set_index("_category")
            if not keyed.index.is_unique:
                raise FigureSpecError(
                    "bar data must contain one pre-aggregated row per category and group"
                )
            values = [float(keyed.loc[item, y]) if item in keyed.index else math.nan for item in categories]
            error_bars = None
            if uncertainty:
                lows = [float(keyed.loc[item, uncertainty["lower"]]) if item in keyed.index else math.nan for item in categories]
                highs = [float(keyed.loc[item, uncertainty["upper"]]) if item in keyed.index else math.nan for item in categories]
                if any(low > center or high < center for low, center, high in zip(lows, values, highs) if not any(math.isnan(item) for item in (low, center, high))):
                    raise FigureSpecError("bar uncertainty interval must contain its estimate")
                error_bars = np.vstack(
                    ([center - low for low, center in zip(lows, values)], [high - center for high, center in zip(highs, values)])
                )
            offset = (index - (len(groups) - 1) / 2) * width
            ax.bar(
                positions + offset,
                values,
                width=width * 0.92,
                yerr=error_bars,
                capsize=2.5 if error_bars is not None else 0,
                error_kw={"elinewidth": 0.9, "capthick": 0.9, "ecolor": "#34495E"},
                label=name or None,
                color=PALETTE[index],
                edgecolor="white",
                linewidth=0.7,
                zorder=3,
            )
        ax.set_xticks(positions, categories, rotation=float(panel.get("x_tick_rotation", 0)))
    else:
        for index, (name, group) in enumerate(groups):
            group = group.sort_values(x)
            kwargs = {
                "color": PALETTE[index],
                "label": name or None,
                "marker": MARKERS[index],
                "markersize": 4.8,
                "markeredgecolor": "white",
                "markeredgewidth": 0.55,
                "zorder": 3,
            }
            if kind == "line":
                ax.plot(
                    group[x],
                    group[y],
                    linewidth=1.8,
                    linestyle=LINESTYLES[index % len(LINESTYLES)],
                    **kwargs,
                )
            else:
                ax.scatter(group[x], group[y], s=34, **{key: value for key, value in kwargs.items() if key not in {"markersize"}})
            if uncertainty:
                if (
                    (group[uncertainty["lower"]] > group[y]).any()
                    or (group[uncertainty["upper"]] < group[y]).any()
                ):
                    raise FigureSpecError(
                        "uncertainty interval must contain its estimate"
                    )
                ax.fill_between(
                    group[x].astype(float),
                    group[uncertainty["lower"]].astype(float),
                    group[uncertainty["upper"]].astype(float),
                    color=PALETTE[index],
                    alpha=0.13,
                    linewidth=0,
                    zorder=1,
                )
    if hue:
        ax.legend(frameon=False, ncol=min(3, len(groups)), loc="best", title=panel.get("legend_title") or hue)


def _draw_heatmap(ax: Any, panel: dict[str, Any], frame: Any, np: Any) -> None:
    x, y, value = panel["x"], panel["y"], panel["value"]
    _numeric(frame, [value])
    for field in (x, y):
        if field not in frame.columns:
            raise FigureSpecError(f"missing data column: {field}")
    if frame.duplicated(subset=[x, y]).any():
        raise FigureSpecError("heatmap data must contain one value per x/y cell")
    matrix = frame.pivot(index=y, columns=x, values=value)
    if any(CJK_RE.search(str(item)) for item in [*matrix.columns, *matrix.index]):
        raise FigureSpecError("heatmap category values must use English manuscript text")
    image = ax.imshow(matrix.to_numpy(dtype=float), cmap="viridis", aspect="auto")
    ax.set_xticks(np.arange(len(matrix.columns)), [str(item) for item in matrix.columns], rotation=45, ha="right")
    ax.set_yticks(np.arange(len(matrix.index)), [str(item) for item in matrix.index])
    if panel.get("annotate", True) and matrix.size <= 100:
        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                value_item = matrix.iloc[row, column]
                if not math.isnan(float(value_item)):
                    ax.text(column, row, f"{float(value_item):.2f}", ha="center", va="center", fontsize=7, color="white" if float(value_item) < float(matrix.stack().median()) else "black")
    colorbar = ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    colorbar.set_label(panel.get("colorbar_label") or value)


def _draw_forest(ax: Any, panel: dict[str, Any], frame: Any, np: Any) -> None:
    label, effect = panel["label"], panel["y"]
    low, high = panel["ci_low"], panel["ci_high"]
    _numeric(frame, [effect, low, high])
    if label not in frame.columns:
        raise FigureSpecError(f"missing data column: {label}")
    ordered = frame.reset_index(drop=True)
    if ordered[label].astype(str).map(lambda value: bool(CJK_RE.search(value))).any():
        raise FigureSpecError(f"forest labels must use English manuscript text: {label}")
    positions = np.arange(len(ordered))[::-1]
    center = ordered[effect].to_numpy(dtype=float)
    lower = ordered[low].to_numpy(dtype=float)
    upper = ordered[high].to_numpy(dtype=float)
    if np.any(lower > center) or np.any(upper < center):
        raise FigureSpecError("forest confidence interval must contain its effect")
    ax.errorbar(
        center,
        positions,
        xerr=np.vstack((center - lower, upper - center)),
        fmt="o",
        color=PALETTE[0],
        ecolor="#54738A",
        capsize=3,
        linewidth=1.4,
        markeredgecolor="white",
        markeredgewidth=0.6,
        zorder=3,
    )
    ax.axvline(float(panel.get("reference", 0.0)), color="#6B7280", linewidth=1, linestyle="--")
    ax.set_yticks(positions, ordered[label].astype(str))


def inspect_layout(fig: Any) -> list[str]:
    """Mechanical preflight; a human must still inspect all rendered formats."""
    from matplotlib.text import Text

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bounds = fig.bbox
    warnings: list[str] = []
    for ax_index, ax in enumerate(fig.axes, 1):
        for artist in ax.get_children():
            if not isinstance(artist, Text) or not artist.get_visible() or not artist.get_text().strip():
                continue
            box = artist.get_window_extent(renderer)
            if (box.x0 < bounds.x0-3 or box.y0 < bounds.y0-3 or
                    box.x1 > bounds.x1+3 or box.y1 > bounds.y1+3):
                warnings.append(f"axes {ax_index}: text extends outside canvas: {artist.get_text()[:50]}")
    return warnings


def render(project: Path, spec_path: Path) -> dict[str, Any]:
    project = project.resolve()
    spec_path = spec_path.resolve()
    if project not in spec_path.parents or not spec_path.is_file():
        raise FigureSpecError("spec must be an existing project file")
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FigureSpecError(f"cannot read figure spec: {exc}") from exc
    if not isinstance(spec, dict):
        raise FigureSpecError("figure spec must be an object")
    validate_spec(spec)
    plt, np, pd = _imports()
    style = spec["style"]
    axes_face = {"minimal": "white", "technical": "#F8FAFC", "high-impact": "#F4F8FB"}[style]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.labelsize": 9,
            "axes.titlesize": 9.5,
            "axes.linewidth": 0.8,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "legend.fontsize": 7.4,
            "figure.facecolor": "white",
            "axes.facecolor": axes_face,
            "savefig.facecolor": "white",
            "svg.hashsalt": "doctoral-research-os-v2",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    panels = spec["panels"]
    columns = min(int(spec.get("columns", 2 if len(panels) > 1 else 1)), 3)
    rows = math.ceil(len(panels) / columns)
    width = float(spec.get("width", 7.2 * columns / min(columns, 2)))
    height = float(spec.get("height", 3.8 * rows))
    if not (3 <= width <= 18 and 2.5 <= height <= 24):
        raise FigureSpecError("figure width/height is outside publication-safe bounds")
    fig, axes = plt.subplots(rows, columns, figsize=(width, height), squeeze=False, constrained_layout=True)
    data_records: dict[str, dict[str, Any]] = {}
    layout_warnings: list[str] = []
    try:
        for index, panel in enumerate(panels):
            ax = axes[index // columns][index % columns]
            data_relative = panel.get("data", spec.get("data"))
            data_path = safe_file(project, data_relative, f"panels[{index}].data")
            frame = _read_table(data_path, pd)
            relative = data_path.relative_to(project).as_posix()
            data_records[relative] = {"path": relative, "sha256": sha256_file(data_path), "rows": int(len(frame)), "columns": [str(item) for item in frame.columns]}
            if panel["kind"] == "heatmap":
                _draw_heatmap(ax, panel, frame, np)
            elif panel["kind"] == "forest":
                _draw_forest(ax, panel, frame, np)
            elif panel["kind"] in figure_recipes.KINDS:
                try:
                    figure_recipes.draw(ax, panel, frame, np, pd, PALETTE)
                except (ValueError, KeyError, TypeError, OverflowError) as exc:
                    raise FigureSpecError(f"panels[{index}]: {exc}") from exc
            else:
                _draw_standard(ax, panel, frame, np)
            _decorate(ax, panel, chr(ord("a") + index))
        for index in range(len(panels), rows * columns):
            axes[index // columns][index % columns].axis("off")
        layout_warnings = inspect_layout(fig)
        output_stem = safe_file(project, spec.get("output_stem"), "output_stem")
        expected_root = project / "papers"
        if expected_root.resolve() not in output_stem.parents or "figures" not in output_stem.parts:
            raise FigureSpecError("output_stem must be inside papers/Pxx/figures")
        output_stem.parent.mkdir(parents=True, exist_ok=True)
        source_records: list[dict[str, Any]] = []
        if spec.get("source_data_export", False):
            # Explicit opt-in: copying a raw table can disclose restricted data.
            for index, panel in enumerate(panels):
                source = safe_file(project, panel.get("data", spec["data"]), "source data")
                target = output_stem.with_name(f"{output_stem.name}-panel-{index+1}-source{source.suffix}")
                shutil.copyfile(source, target)
                source_records.append({"path": target.relative_to(project).as_posix(), "sha256": sha256_file(target)})
        outputs: list[dict[str, Any]] = []
        for suffix in spec["formats"]:
            path = output_stem.with_suffix(f".{suffix}")
            metadata: dict[str, Any]
            if suffix == "pdf":
                metadata = {"Creator": "Doctoral Research OS", "CreationDate": None, "ModDate": None}
            elif suffix == "svg":
                metadata = {"Creator": "Doctoral Research OS", "Date": None}
            else:
                metadata = {"Software": "Doctoral Research OS"}
            fig.savefig(
                path,
                dpi=int(spec["dpi"]) if suffix == "png" else None,
                bbox_inches="tight",
                metadata=metadata,
            )
            outputs.append({"path": path.relative_to(project).as_posix(), "format": suffix, "sha256": sha256_file(path), "size": path.stat().st_size})
    finally:
        plt.close(fig)
    renderer = output_stem.with_suffix(".renderer.py")
    renderer.write_text(
        "#!/usr/bin/env python3\n"
        "# Deterministic wrapper generated by Doctoral Research OS.\n"
        "from pathlib import Path\n"
        "import subprocess\n"
        "import sys\n\n"
        "repo = next(parent for parent in Path(__file__).resolve().parents "
        "if (parent / 'scripts' / 'publication_figures.py').is_file())\n"
        "subprocess.run([sys.executable, str(repo / 'scripts' / 'publication_figures.py'), "
        f"'render', '--project', {project.name!r}, '--spec', {spec_path.relative_to(project).as_posix()!r}], check=True)\n",
        encoding="utf-8",
    )
    try:
        from scripts import output_provenance
    except ImportError:
        import output_provenance  # type: ignore
    report = {
        "schema_version": "1.0",
        "renderer": "scripts/publication_figures.py",
        "renderer_sha256": sha256_file(Path(__file__)),
        "renderer_wrapper": {"path": renderer.relative_to(project).as_posix(), "sha256": sha256_file(renderer)},
        "spec": {"path": spec_path.relative_to(project).as_posix(), "sha256": sha256_file(spec_path)},
        "data": sorted(data_records.values(), key=lambda item: item["path"]),
        "source_data_exports": source_records,
        "outputs": outputs,
        "quality": {
            "vector_outputs": sorted(set(spec["formats"]) & {"svg", "pdf"}),
            "raster_dpi": int(spec["dpi"]),
            "colorblind_safe_palette": True,
            "redundant_group_encoding": "color+marker+line-style",
            "three_dimensional_chart": False,
            "caption": spec["caption"],
            "alt_text": spec["alt_text"],
            "claim_ids": spec["claim_ids"],
            "layout_review_required": True,
            "layout_warnings": layout_warnings,
            "distribution_estimates_not_inferred": True,
        },
    }
    report_path = output_stem.with_suffix(".figure-build.json")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=report_path.parent, delete=False) as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(report_path)
    output_provenance.record_model_writes(
        project,
        [renderer, report_path],
        family="other",
        provider="deterministic-local-renderer",
        model="scripts/publication_figures.py",
        role="figure-renderer-control",
        run_id=f"figure-{hashlib.sha256(spec_path.read_bytes()).hexdigest()[:16]}",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("render")
    command.add_argument("--project", required=True)
    command.add_argument("--spec", required=True)
    command.add_argument("--record", action="store_true")
    command.add_argument("--run", action="append", default=[])
    command.add_argument("--language-checked-by")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", args.project):
        raise SystemExit("error: invalid project slug")
    project = PROJECTS_ROOT / args.project
    try:
        spec_path = safe_file(project, args.spec, "spec")
        report = render(project, spec_path)
        if args.record:
            if not args.run or not args.language_checked_by:
                raise FigureSpecError("--record requires --run and --language-checked-by")
            try:
                from scripts.figure_provenance import record_figure
            except ImportError:
                from figure_provenance import record_figure
            paper_match = re.search(r"(?:^|/)papers/(P[0-9]{2})/figures/", report["outputs"][0]["path"])
            if not paper_match:
                raise FigureSpecError("cannot determine paper ID from output path")
            renderer = report["renderer_wrapper"]["path"]
            inputs = [item["path"] for item in report["data"]]
            for output in report["outputs"]:
                record_figure(
                    project,
                    paper_match.group(1),
                    output["path"],
                    "data_chart",
                    renderer,
                    inputs,
                    args.run,
                    args.spec,
                    args.language_checked_by,
                )
    except FigureSpecError as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
