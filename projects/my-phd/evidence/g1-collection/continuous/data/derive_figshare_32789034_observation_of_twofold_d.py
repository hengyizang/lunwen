#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32789034-observation-of-twofold-d (10.6084/m9.figshare.32789034.v2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Fig.S1.txt",
    "sha256": "838fcd254e0725d895efbba757230ebf3da7d49b6cfdb12c08e8e82ccf635d78"
  },
  {
    "file": "Fig.3c.txt",
    "sha256": "86efdebf67d95e8ffad579b04508534fe387ebaa30b9337638f4f517a06d9922"
  },
  {
    "file": "Fig.1c.txt",
    "sha256": "2e6b4046bb331124cb172e0144ffbb573332aa23299f6325ab28f79e907daf06"
  },
  {
    "file": "Fig.S3.txt",
    "sha256": "5be09f3660e80ecf56597d1f2b412c30f9376b1d5e4854b2308099dd34e644f6"
  }
]
EXPECTED_OUTPUT_SHA256 = "cd1fe38ea7e3cd6c5f401ab99d0f3834b12473eccd6d506c05666353c5bca9fe"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
