#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34950610-dataset-robotic-sanding (10.6084/m9.figshare.34950610.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "processed_stylus_data_R.csv",
    "sha256": "8ce7afdc0306f38341b284d1cb31b3f00bae41a4927a514df134aa904fc5c75f"
  },
  {
    "file": "samples_names.txt",
    "sha256": "0f76f6e877c0ae71b81de015642c6abb60cb5e08de8934efe6597d0b3f0a7c31"
  }
]
EXPECTED_OUTPUT_SHA256 = "37687652abdbd1ea31e986b285091f1af4e364e490758f3fe10f9ffac8010267"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
