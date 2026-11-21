#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-cytve5-replication-data-for-fin (10.7910/dvn/cytve5)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "AllSpecies.FinPhasing.tab",
    "sha256": "921a4b6940c9b66069a97bd0a8fc83b50320027a4f677946d6f29a6108040831"
  },
  {
    "file": "DataForStatsAnalysis.tab",
    "sha256": "ec93f305ee9337ad9bc8ba56c2625b9b1490ab00d37c360eefc4b21cd96b0f5a"
  }
]
EXPECTED_OUTPUT_SHA256 = "7170f92b42f651a482786b619ac114d62d3d75774a50a4c64fbc2d3d78ff908f"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
