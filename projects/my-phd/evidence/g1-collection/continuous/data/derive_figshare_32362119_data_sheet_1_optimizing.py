#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32362119-data-sheet-1-optimizing (10.3389/fmech.2026.1781598.s005)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data Sheet 1_Optimizing predictive maintenance with synthetic data_ a case study on ABB IRB 1100 industrial robot.csv",
    "sha256": "4c4a5f96d2e19882efed951d704fc2ab22d0c109554d17f058c68777b44ec746"
  }
]
EXPECTED_OUTPUT_SHA256 = "edd45da145cd193dbcaec73105912d45851a00b9baf1dfee4e2eb540521192ab"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
