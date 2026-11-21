#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-29045729-data-analysis (10.6084/m9.figshare.29045729.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data_Analysis_Normalized.csv",
    "sha256": "0324671b766cd7f8982b3e3e1640a393a4e719afd07f60a3fc4f64cd375df45e"
  },
  {
    "file": "Data_Analysis_Raw.csv",
    "sha256": "b5cce0a9f0d24933ec086a55bdd0ce6a2aec5e2263654d8b12848a4fa09c2f30"
  }
]
EXPECTED_OUTPUT_SHA256 = "556cc7408ff6f249b5aa8707a6fce3f3e914bf075122ca742eb6ef8bcfb45a0b"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
