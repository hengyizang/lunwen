#!/usr/bin/env python3
"""Reproducible deterministic cleaner for figshare-32221713-quip-experimental-design (10.6084/m9.figshare.32221713.v2)."""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

EXPECTED_FILES = [
  {
    "file": "README.txt",
    "sha256": "bf8eb4a184c2fedf2e24288b3b38f0a2d551aa254cd7d01671a38e8b4314b7b4"
  },
  {
    "file": "quipcode.zip",
    "sha256": "209eb14ab159ba66c1c1399164cedb7872ef3936fa0ed19766f23a2f4313f328"
  }
]
EXPECTED_OUTPUT_SHA256 = "19624d3efba3003abbb39cedbd41caf1e10482a9ebb963b54ac2bd8819615894"
MODE = "summary_table"
MAX_RAW_BYTES = 25000000


def _parse_tabular(name: str, data: bytes):
    ext = Path(name).suffix.lower()
    if ext in {".tsv", ".tab"}:
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(data), sep="\t", encoding=enc)
                if df.shape[1] >= 2 and df.shape[0] >= 2:
                    return df
            except Exception:
                continue
    elif ext in {".csv", ".txt"}:
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(data), sep=None, engine="python", encoding=enc)
                if df.shape[1] >= 2 and df.shape[0] >= 2:
                    return df
            except Exception:
                continue
    elif ext == ".json":
        obj = json.loads(data.decode("utf-8", errors="replace"))
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            return pd.json_normalize(obj)
        if isinstance(obj, dict):
            for val in obj.values():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    return pd.json_normalize(val)
            flat = pd.json_normalize([obj])
            if flat.shape[1] >= 2:
                return flat
    return None


def _clean_text(value, max_len: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[: max_len - 3].rstrip() + "..." if max_len and len(text) > max_len else text


def _summarize(df: pd.DataFrame, source_file: str) -> list[dict]:
    rows = []
    for col in df.columns:
        series = df[col]
        non_null = int(series.notna().sum())
        null_cnt = int(series.isna().sum())
        num = pd.to_numeric(series, errors="coerce")
        valid_num = num.dropna()
        if len(valid_num) > 0 and len(valid_num) >= 0.5 * max(1, non_null):
            rows.append({
                "source_file": source_file, "column": str(col), "inferred_kind": "numeric",
                "rows_total": int(len(df)), "non_null": non_null, "null_count": null_cnt,
                "unique_count": int(series.nunique(dropna=True)),
                "min": f"{float(valid_num.min()):.6g}", "p25": f"{float(valid_num.quantile(0.25)):.6g}",
                "median": f"{float(valid_num.median()):.6g}", "mean": f"{float(valid_num.mean()):.6g}",
                "p75": f"{float(valid_num.quantile(0.75)):.6g}", "max": f"{float(valid_num.max()):.6g}",
                "std": f"{float(valid_num.std(ddof=1)):.6g}" if len(valid_num) > 1 else "0",
            })
        else:
            top_vals = series.dropna().astype(str).value_counts().head(3).to_dict()
            rows.append({
                "source_file": source_file, "column": str(col), "inferred_kind": "categorical_or_text",
                "rows_total": int(len(df)), "non_null": non_null, "null_count": null_cnt,
                "unique_count": int(series.nunique(dropna=True)),
                "min": "", "p25": "", "median": "", "mean": "", "p75": "", "max": "",
                "std": _clean_text(json.dumps(top_vals, ensure_ascii=False), 160),
            })
    return rows


def reproduce(input_dir: Path, output_csv: Path | None = None) -> bytes:
    parsed_tables = []
    for item in EXPECTED_FILES:
        target = input_dir / item["file"]
        if not target.is_file():
            raise FileNotFoundError(f"Missing staged raw file: {target}")
        raw_bytes = target.read_bytes()
        actual = hashlib.sha256(raw_bytes).hexdigest()
        if actual != item["sha256"]:
            raise ValueError(f"SHA-256 mismatch for {item['file']}: {actual} != {item['sha256']}")
        if target.suffix.lower() == ".zip":
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                members = [
                    m for m in zf.infolist()
                    if not m.is_dir() and not m.filename.startswith("__MACOSX")
                    and Path(m.filename).suffix.lower() in {".csv", ".tsv", ".txt", ".json"}
                    and m.file_size <= MAX_RAW_BYTES
                ]
                for m in members[:5]:
                    df = _parse_tabular(m.filename, zf.read(m.filename))
                    if df is not None and df.shape[0] >= 2 and df.shape[1] >= 2:
                        parsed_tables.append((f"{target.name}::{Path(m.filename).name}", df))
        else:
            df = _parse_tabular(target.name, raw_bytes)
            if df is not None and df.shape[0] >= 2 and df.shape[1] >= 2:
                parsed_tables.append((target.name, df))

    cleaned_frames, summary_rows = [], []
    for src_name, df in parsed_tables:
        df_clean = df.copy()
        df_clean.columns = [re.sub(r"\s+", " ", str(c).strip()) for c in df_clean.columns]
        df_clean = df_clean.drop_duplicates().reset_index(drop=True)
        summary_rows.extend(_summarize(df_clean, src_name))
        df_w = df_clean.copy()
        df_w.insert(0, "source_file", src_name)
        cleaned_frames.append(df_w)

    if MODE == "cleaned_rows":
        out_bytes = pd.concat(cleaned_frames, ignore_index=True).to_csv(index=False, lineterminator="\n").encode("utf-8")
    else:
        out_bytes = pd.DataFrame(summary_rows).to_csv(index=False, lineterminator="\n").encode("utf-8")
    out_sha = hashlib.sha256(out_bytes).hexdigest()
    if out_sha != EXPECTED_OUTPUT_SHA256:
        raise ValueError(f"Reproduced output SHA-256 mismatch: {out_sha} != {EXPECTED_OUTPUT_SHA256}")
    if output_csv is not None:
        output_csv.write_bytes(out_bytes)
    return out_bytes


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python " + Path(__file__).name + " <raw_staging_dir> [output_csv]", file=sys.stderr)
        return 2
    out = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
    reproduce(Path(sys.argv[1]), out)
    print(f"Reproduced & verified {len(EXPECTED_FILES)} raw inputs -> output SHA-256 {EXPECTED_OUTPUT_SHA256[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
