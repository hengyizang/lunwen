#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32065938-custom-machining-gantry (10.6084/m9.figshare.32065938.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "GRR_T5_LOOSE_TOOL.csv",
    "sha256": "f667d7ae26ae68494406d55b2ab6101517a413c50ef5b46dc2163bb2fa642c60"
  },
  {
    "file": "GRR_T6_PLUNGE.csv",
    "sha256": "78fda95db07a8a2d8c34055318bc7e24eab0b19245e867192ceacc7bbab48395"
  },
  {
    "file": "GRR_T2.csv",
    "sha256": "fcba29d0edb56468e17bc4c82a5cd9dc6e4c79d9285391956a3febba8f3f0687"
  },
  {
    "file": "GRR_T7.csv",
    "sha256": "4251a83c5c134d0233e1e9e491c37fb91ab5d181c728f89aa201ca8a445a1928"
  }
]
EXPECTED_OUTPUT_SHA256 = "686a91bec5f7cf1de4f220d223e5831a0057f6f1660d23ad2df809e6b475913e"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
