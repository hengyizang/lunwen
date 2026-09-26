#!/usr/bin/env python3
"""Additional deterministic scientific chart recipes; never infer statistics.

Inputs for ROC, PR, calibration, PCA and survival must already be calculated by
registered analyses. Plotting code does not estimate or fit a model.
"""
from __future__ import annotations

import math
from typing import Any


KINDS = {
    "box", "violin", "strip", "histogram", "density", "ecdf", "area",
    "stacked_bar", "dumbbell", "errorbar", "roc", "pr", "calibration",
    "confusion", "correlation", "volcano", "pca", "survival", "sankey",
    "raincloud", "hexbin", "qq", "funnel", "waterfall",
}
RAW_DISTRIBUTIONS = {"box", "violin", "strip", "histogram", "density", "ecdf", "raincloud", "hexbin"}


def required_fields(panel: dict[str, Any]) -> list[str]:
    kind = panel["kind"]
    if kind == "sankey":
        return ["x", "y", "value"]  # source, destination, nonnegative flow
    if kind == "correlation":
        return []  # all numeric columns, no silent imputation
    if kind == "confusion":
        return ["x", "y", "value"]  # true class, predicted class, count
    if kind == "volcano":
        return ["x", "y"]  # log2 fold change, adjusted p value
    if kind == "dumbbell":
        return ["x", "y", "end"]  # category, before, after
    return ["x", "y"]


def draw(ax: Any, panel: dict[str, Any], frame: Any, np: Any, pd: Any,
         palette: tuple[str, ...]) -> None:
    kind, x, y = panel["kind"], panel.get("x"), panel.get("y")
    for field in required_fields(panel):
        if panel.get(field) not in frame.columns:
            raise ValueError(f"{kind}: missing data column {panel.get(field)!r}")
    hue = panel.get("hue")
    if hue and hue not in frame.columns:
        raise ValueError(f"{kind}: missing grouping column {hue!r}")
    groups = list(frame.groupby(hue, sort=True)) if hue else [("", frame)]
    if len(groups) > len(palette):
        raise ValueError("a panel may contain at most eight visual groups")

    if kind in {"box", "violin", "strip", "raincloud"}:
        values = pd.to_numeric(frame[y], errors="raise")
        if not np.isfinite(values).all():
            raise ValueError("distribution values must be finite")
        categories = sorted(frame[x].astype(str).unique())
        series = [values[frame[x].astype(str) == item].to_numpy() for item in categories]
        if kind == "box":
            artist = ax.boxplot(series, patch_artist=True, showfliers=True)
            for box in artist["boxes"]:
                box.set(facecolor=palette[0], alpha=.5)
        elif kind in {"violin", "raincloud"}:
            if any(len(item) < 2 or np.unique(item).size < 2 for item in series):
                raise ValueError("violin requires at least two distinct observations per group")
            artist = ax.violinplot(series, showmedians=True)
            for body in artist["bodies"]:
                body.set_facecolor(palette[0]); body.set_alpha(.5)
            if kind == "raincloud":
                ax.boxplot(series, widths=.14, showfliers=False, patch_artist=False)
                for index, item in enumerate(series, 1):
                    offsets = np.linspace(.16, .27, len(item))
                    ax.scatter(index + offsets, item, color=palette[0], s=9, alpha=.35)
        else:
            for index, item in enumerate(series, 1):
                # Deterministic jitter, independent of global random state.
                offsets = np.linspace(-.16, .16, len(item)) if len(item) > 1 else [0]
                ax.scatter(index + np.asarray(offsets), item, color=palette[0], s=12, alpha=.6)
        ax.set_xticks(range(1, len(categories) + 1), categories)
    elif kind in {"histogram", "density", "ecdf"}:
        bins = int(panel.get("bins", 20))
        if not 5 <= bins <= 100:
            raise ValueError("bins must be between 5 and 100")
        for index, (name, group) in enumerate(groups):
            values = pd.to_numeric(group[x], errors="raise").to_numpy(dtype=float)
            if not np.isfinite(values).all():
                raise ValueError("distribution values must be finite")
            if kind == "histogram":
                ax.hist(values, bins=bins, color=palette[index], alpha=.48, label=str(name) or None)
            elif kind == "density":
                counts, edges = np.histogram(values, bins=bins, density=True)
                # A histogram density, not a fitted KDE; disclose bin count in caption.
                ax.plot((edges[:-1]+edges[1:])/2, counts, color=palette[index], label=str(name) or None)
            else:
                ordered = np.sort(values)
                ax.step(ordered, np.arange(1, len(ordered)+1)/len(ordered),
                        where="post", color=palette[index], label=str(name) or None)
    elif kind in {"area", "roc", "pr", "calibration", "survival", "pca", "errorbar", "qq", "funnel"}:
        for index, (name, group) in enumerate(groups):
            xx = pd.to_numeric(group[x], errors="raise").to_numpy(dtype=float)
            yy = pd.to_numeric(group[y], errors="raise").to_numpy(dtype=float)
            if not (np.isfinite(xx).all() and np.isfinite(yy).all()):
                raise ValueError("plot coordinates must be finite")
            if kind in {"roc", "pr", "calibration", "survival"}:
                if (np.any(xx < 0) or np.any(yy < 0) or np.any(yy > 1)
                        or kind != "survival" and np.any(xx > 1)):
                    raise ValueError(f"{kind}: probabilities must be in [0, 1]")
            order = np.argsort(xx, kind="stable"); xx, yy = xx[order], yy[order]
            label = str(name) or None
            if kind == "area":
                ax.fill_between(xx, yy, color=palette[index], alpha=.25, label=label)
                ax.plot(xx, yy, color=palette[index])
            elif kind in {"pca", "qq", "funnel"}:
                ax.scatter(xx, yy, color=palette[index], s=24, label=label, alpha=.8)
            elif kind == "errorbar":
                uncertainty = panel.get("uncertainty")
                if not uncertainty:
                    raise ValueError("errorbar requires declared lower and upper columns")
                low = pd.to_numeric(group[uncertainty["lower"]], errors="raise").to_numpy(dtype=float)[order]
                high = pd.to_numeric(group[uncertainty["upper"]], errors="raise").to_numpy(dtype=float)[order]
                if not (np.isfinite(low).all() and np.isfinite(high).all()) or np.any(low > yy) or np.any(high < yy):
                    raise ValueError("invalid errorbar interval")
                ax.errorbar(xx, yy, yerr=np.vstack([yy-low, high-yy]), fmt="o", capsize=3,
                            color=palette[index], label=label)
            else:
                if kind == "survival" and np.any(np.diff(yy) > 1e-8):
                    raise ValueError("survival probabilities may not increase")
                ax.step(xx, yy, where="post" if kind == "survival" else "mid",
                        color=palette[index], label=label, linewidth=1.7)
        if kind in {"roc", "calibration"}:
            ax.plot([0, 1], [0, 1], "--", color="#777777", linewidth=.8)
        if kind in {"roc", "pr", "calibration"}:
            ax.set(xlim=(0, 1), ylim=(0, 1))
        elif kind == "survival":
            ax.set_ylim(0, 1)
        elif kind == "qq":
            xx = pd.to_numeric(frame[x], errors="raise").to_numpy(dtype=float)
            yy = pd.to_numeric(frame[y], errors="raise").to_numpy(dtype=float)
            low, high = min(xx.min(), yy.min()), max(xx.max(), yy.max())
            ax.plot([low, high], [low, high], linestyle="--", color="#777", linewidth=.8)
        elif kind == "funnel":
            if (pd.to_numeric(frame[y], errors="raise") <= 0).any():
                raise ValueError("funnel uncertainty (standard error) must be positive")
            if "reference" in panel:
                reference = float(panel["reference"])
                if not np.isfinite(reference):raise ValueError("funnel reference must be finite")
                ax.axvline(reference, linestyle="--", color="#777", linewidth=.8)
            ax.invert_yaxis()  # precomputed standard error, smaller at top
    elif kind == "hexbin":
        xx = pd.to_numeric(frame[x], errors="raise").to_numpy(dtype=float)
        yy = pd.to_numeric(frame[y], errors="raise").to_numpy(dtype=float)
        if not (np.isfinite(xx).all() and np.isfinite(yy).all()):
            raise ValueError("hexbin observations must be finite")
        artist = ax.hexbin(xx, yy, gridsize=25, mincnt=1, cmap="Blues")
        ax.figure.colorbar(artist, ax=ax, fraction=.046, pad=.04, label="Observed count")
    elif kind == "waterfall":
        if hue:raise ValueError("waterfall does not support hue")
        if frame[x].astype(str).duplicated().any():raise ValueError("waterfall categories must be unique")
        vals = pd.to_numeric(frame[y], errors="raise").to_numpy(dtype=float)
        if not np.isfinite(vals).all():raise ValueError("waterfall contributions must be finite")
        starts = np.r_[0.0, np.cumsum(vals[:-1])]
        for category, value, start in zip(frame[x].astype(str), vals, starts):
            ax.bar(category, value, bottom=start, color=palette[0] if value>=0 else palette[1])
        ax.axhline(0, color="#777", linewidth=.8)
    elif kind in {"stacked_bar", "dumbbell"}:
        categories = sorted(frame[x].astype(str).unique())
        if kind == "stacked_bar":
            if not hue:
                raise ValueError("stacked_bar requires hue column")
            if frame.duplicated([x, hue]).any():
                raise ValueError("stacked_bar needs one row per category and group")
            baseline = np.zeros(len(categories))
            for index, (name, group) in enumerate(groups):
                vals = group.set_index(group[x].astype(str))[y].reindex(categories).fillna(0).to_numpy(dtype=float)
                if not np.isfinite(vals).all() or np.any(vals < 0):
                    raise ValueError("stacked values must be nonnegative and finite")
                ax.bar(categories, vals, bottom=baseline, color=palette[index], label=str(name)); baseline += vals
        else:
            if frame[x].astype(str).duplicated().any():
                raise ValueError("dumbbell category values must be unique")
            start = pd.to_numeric(frame[y], errors="raise").to_numpy(dtype=float)
            end = pd.to_numeric(frame[panel["end"]], errors="raise").to_numpy(dtype=float)
            if not (np.isfinite(start).all() and np.isfinite(end).all()):
                raise ValueError("dumbbell values must be finite")
            pos = np.arange(len(frame))
            for a, b, p in zip(start, end, pos):
                ax.plot([a, b], [p, p], color="#9AA8B2", linewidth=2)
            ax.scatter(start, pos, color=palette[0], label="Before", zorder=3)
            ax.scatter(end, pos, color=palette[1], label="After", zorder=3)
            ax.set_yticks(pos, frame[x].astype(str)); ax.invert_yaxis()
    elif kind in {"confusion", "correlation"}:
        if kind == "confusion":
            if frame.duplicated([x, y]).any():
                raise ValueError("confusion cells must be unique")
            matrix = frame.pivot(index=x, columns=y, values=panel["value"])
        else:
            matrix = frame.select_dtypes(include="number").corr()
            if matrix.shape[0] < 2:
                raise ValueError("correlation needs at least two numeric columns")
        values = matrix.to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("matrix has missing/nonfinite cells; no imputation is performed")
        if kind == "confusion" and np.any(values < 0):
            raise ValueError("confusion counts must be nonnegative")
        im = ax.imshow(values, cmap="Blues" if kind == "confusion" else "coolwarm",
                       vmin=-1 if kind == "correlation" else 0,
                       vmax=1 if kind == "correlation" else None, aspect="auto")
        ax.set_xticks(range(len(matrix.columns)), matrix.columns.astype(str), rotation=45, ha="right")
        ax.set_yticks(range(len(matrix.index)), matrix.index.astype(str))
        ax.figure.colorbar(im, ax=ax, fraction=.046, pad=.04)
    elif kind == "volcano":
        fold = pd.to_numeric(frame[x], errors="raise").to_numpy(dtype=float)
        p = pd.to_numeric(frame[y], errors="raise").to_numpy(dtype=float)
        if not np.isfinite(fold).all() or not np.isfinite(p).all() or np.any(p <= 0) or np.any(p > 1):
            raise ValueError("volcano requires finite log2 fold change and adjusted p in (0,1]")
        threshold = float(panel.get("threshold", .05)); effect = float(panel.get("effect_threshold", 1))
        if not 0 < threshold < 1 or effect < 0:
            raise ValueError("volcano thresholds are invalid")
        significant = (p <= threshold) & (np.abs(fold) >= effect)
        ax.scatter(fold[~significant], -np.log10(p[~significant]), s=12, color="#AAB5BF", alpha=.6)
        ax.scatter(fold[significant], -np.log10(p[significant]), s=12, color=palette[0], alpha=.8)
        ax.axhline(-math.log10(threshold), color="#777", linestyle="--", linewidth=.8)
        ax.axvline(effect, color="#777", linestyle="--", linewidth=.8)
        ax.axvline(-effect, color="#777", linestyle="--", linewidth=.8)
    elif kind == "sankey":
        from matplotlib.patches import PathPatch, Rectangle
        from matplotlib.path import Path
        amounts = pd.to_numeric(frame[panel["value"]], errors="raise").to_numpy(dtype=float)
        if not np.isfinite(amounts).all() or np.any(amounts <= 0):
            raise ValueError("sankey flow values must be positive and finite")
        sources = sorted(frame[x].astype(str).unique()); targets = sorted(frame[y].astype(str).unique())
        left = frame.assign(_label=frame[x].astype(str)).groupby("_label")[panel["value"]].sum().reindex(sources)
        right = frame.assign(_label=frame[y].astype(str)).groupby("_label")[panel["value"]].sum().reindex(targets)
        total = float(amounts.sum()); unit = .85 / total
        positions: dict[str, dict[str, float]] = {"left": {}, "right": {}}
        for side, labels, weights, key in ((.05, sources, left, "left"), (.8, targets, right, "right")):
            base = .05
            for idx, (label, weight) in enumerate(zip(labels, weights)):
                height = float(weight)*unit
                ax.add_patch(Rectangle((side, base), .12, height, color=palette[idx % len(palette)], alpha=.7))
                positions[key][label] = base
                ax.text(side + (.14 if side < .5 else -.02), base+height/2, label,
                        ha="left" if side < .5 else "right", va="center", fontsize=7)
                base += height
        for row in frame.sort_values([x, y]).itertuples(index=False, name=None):
            data = dict(zip(frame.columns, row))
            src, dst, height = str(data[x]), str(data[y]), float(data[panel["value"]])*unit
            y0, y1 = positions["left"][src], positions["right"][dst]
            positions["left"][src] += height; positions["right"][dst] += height
            path = Path([(.17, y0), (.46, y0), (.54, y1), (.8, y1),
                         (.8, y1+height), (.54, y1+height), (.46, y0+height), (.17, y0+height), (.17, y0)],
                        [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
                         Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.CLOSEPOLY])
            ax.add_patch(PathPatch(path, facecolor=palette[sources.index(src) % len(palette)],
                                   alpha=.24, edgecolor="none", zorder=0))
        ax.text(.5, .98, f"Total flow: {total:g}", ha="center", va="top", fontsize=8)
        ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
    else:
        raise ValueError(f"unsupported chart: {kind}")
    if hue or kind == "dumbbell":
        ax.legend(frameon=False, fontsize=7)
