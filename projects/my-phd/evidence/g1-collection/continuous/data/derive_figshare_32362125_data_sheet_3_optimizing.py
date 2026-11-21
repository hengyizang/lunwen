#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32362125-data-sheet-3-optimizing (10.3389/fmech.2026.1781598.s003)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data Sheet 3_Optimizing predictive maintenance with synthetic data_ a case study on ABB IRB 1100 industrial robot.csv",
    "sha256": "bcaa8ca936394f851b0e580974a5b1c61d1beb5939b01150ad00f61dfd141f60"
  }
]
EXPECTED_OUTPUT_SHA256 = "c038615ee01693386c56d78af7c412668596212a07217397d68af3ae1f678231"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
