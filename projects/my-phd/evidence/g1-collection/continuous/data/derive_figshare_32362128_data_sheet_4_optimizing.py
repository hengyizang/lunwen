#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32362128-data-sheet-4-optimizing (10.3389/fmech.2026.1781598.s002)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data Sheet 4_Optimizing predictive maintenance with synthetic data_ a case study on ABB IRB 1100 industrial robot.csv",
    "sha256": "a8e35125db9c36d5376bf50bbc08ecd5cdbf24d1f81fa13d28e3e0a4a513c4eb"
  }
]
EXPECTED_OUTPUT_SHA256 = "6018f997112a86396729834dd4931ca55bab8fe23c1620569884c737447a6610"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
