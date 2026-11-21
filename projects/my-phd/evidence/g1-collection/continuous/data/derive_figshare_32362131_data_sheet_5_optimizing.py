#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32362131-data-sheet-5-optimizing (10.3389/fmech.2026.1781598.s001)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data Sheet 5_Optimizing predictive maintenance with synthetic data_ a case study on ABB IRB 1100 industrial robot.zip",
    "sha256": "21fe3aef7ab0a1cfed826cd94c24d647e939ff8c675ed8531e47452bcab88339"
  }
]
EXPECTED_OUTPUT_SHA256 = "f59dc16cd701bc7e7739bd862c54ec84b9bd7dcb1010c16c3fb2ba49411969b6"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
