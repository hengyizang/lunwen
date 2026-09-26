#!/usr/bin/env python3
"""Profile real figure data and suggest chart families without inventing values."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def profile(path: Path) -> dict[str, Any]:
    try:
        from scripts.publication_figures import _imports, _read_table, sha256_file
    except ImportError:
        from publication_figures import _imports, _read_table, sha256_file  # type: ignore

    _, _, pd = _imports()
    frame = _read_table(path, pd)
    columns = []
    for name in frame.columns:
        series = frame[name]
        nonnull = series.dropna()
        numeric = pd.api.types.is_numeric_dtype(series)
        record: dict[str, Any] = {
            "name": str(name), "dtype": str(series.dtype), "missing": int(series.isna().sum()),
            "distinct": int(nonnull.nunique()), "numeric": bool(numeric),
        }
        if numeric and len(nonnull):
            values = nonnull.astype(float)
            q1, q3 = values.quantile([.25, .75])
            record.update({"minimum": float(values.min()), "median": float(values.median()),
                           "maximum": float(values.max()), "outliers_iqr": int(((values < q1-1.5*(q3-q1)) | (values > q3+1.5*(q3-q1))).sum())})
        columns.append(record)
    numeric_count = sum(item["numeric"] for item in columns)
    categorical_count = len(columns)-numeric_count
    suggestions = []
    if numeric_count >= 2:
        suggestions += ["scatter", "line", "correlation", "pca (precomputed coordinates only)"]
    if categorical_count and numeric_count:
        suggestions += ["box/violin/strip for raw observations", "bar with declared uncertainty for aggregate results"]
    if numeric_count >= 1:
        suggestions += ["histogram", "ecdf"]
    issues = []
    if len(frame) < 20:
        issues.append("Small sample: show observations; avoid an unqualified mean-only bar chart.")
    if any(item["missing"] for item in columns):
        issues.append("Missing observations must be handled in the registered analysis; plotter will not impute.")
    if any(item.get("outliers_iqr", 0) for item in columns):
        issues.append("Inspect outliers against data provenance; do not silently drop them.")
    return {"schema_version": "1.0", "source_sha256": sha256_file(path), "rows": len(frame),
            "columns": columns, "suggestions_not_decisions": suggestions, "issues": issues,
            "question_for_author": "Which specific registered claim should this figure communicate?"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    args = parser.parse_args()
    print(json.dumps(profile(args.data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
