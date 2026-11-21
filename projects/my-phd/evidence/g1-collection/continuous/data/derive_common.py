#!/usr/bin/env python3
"""Shared deterministic verification & tabular reproduction helper for cleaned continuous datasets."""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

README_PREFIXES = ("readme", "license", "licence", "notice", "citation", "changelog", "copying", "authors")


def is_prose_txt(name: str) -> bool:
    p = Path(name)
    if p.suffix.lower() != ".txt":
        return False
    stem = p.stem.lower()
    return any(stem == prefix or stem.startswith(prefix + "-") or stem.startswith(prefix + "_") for prefix in README_PREFIXES)


def parse_tabular(name: str, data: bytes):
    if is_prose_txt(name):
        return None
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


def summarize(df: pd.DataFrame, source_file: str) -> list[dict]:
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


def reproduce(input_dir: Path, expected_files: list[dict], expected_output_sha256: str, mode: str,
              max_raw_bytes: int = 25_000_000, output_csv: Path | None = None) -> bytes:
    parsed_tables = []
    for item in expected_files:
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
                    and Path(m.filename).suffix.lower() in {".csv", ".tsv", ".tab", ".txt", ".json"}
                    and m.file_size <= max_raw_bytes
                ]
                for m in members[:5]:
                    df = parse_tabular(m.filename, zf.read(m.filename))
                    if df is not None and df.shape[0] >= 2 and df.shape[1] >= 2:
                        parsed_tables.append((f"{target.name}::{Path(m.filename).name}", df))
        else:
            df = parse_tabular(target.name, raw_bytes)
            if df is not None and df.shape[0] >= 2 and df.shape[1] >= 2:
                parsed_tables.append((target.name, df))

    cleaned_frames, summary_rows = [], []
    for src_name, df in parsed_tables:
        df_clean = df.copy()
        df_clean.columns = [re.sub(r"\s+", " ", str(c).strip()) for c in df_clean.columns]
        df_clean = df_clean.drop_duplicates().reset_index(drop=True)
        summary_rows.extend(summarize(df_clean, src_name))
        df_w = df_clean.copy()
        df_w.insert(0, "source_file", src_name)
        cleaned_frames.append(df_w)

    if mode == "cleaned_rows":
        out_bytes = pd.concat(cleaned_frames, ignore_index=True).to_csv(index=False, lineterminator="\n").encode("utf-8")
    else:
        out_bytes = pd.DataFrame(summary_rows).to_csv(index=False, lineterminator="\n").encode("utf-8")
    out_sha = hashlib.sha256(out_bytes).hexdigest()
    if out_sha != expected_output_sha256:
        raise ValueError(f"Reproduced output SHA-256 mismatch: {out_sha} != {expected_output_sha256}")
    if output_csv is not None:
        output_csv.write_bytes(out_bytes)
    return out_bytes


def run_cli(expected_files: list[dict], expected_output_sha256: str, mode: str, script_name: str,
            max_raw_bytes: int = 25_000_000) -> int:
    if len(sys.argv) < 2:
        print(f"Usage: python {script_name} <raw_staging_dir> [output_csv]", file=sys.stderr)
        return 2
    out = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
    reproduce(Path(sys.argv[1]), expected_files, expected_output_sha256, mode, max_raw_bytes, out)
    print(f"Reproduced & verified {len(expected_files)} raw inputs -> output SHA-256 {expected_output_sha256[:12]}")
    return 0
