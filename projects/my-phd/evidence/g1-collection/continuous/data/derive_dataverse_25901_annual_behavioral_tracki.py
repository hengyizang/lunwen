#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-25901-annual-behavioral-tracki (10.7910/dvn/25901)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "ABTS-II_ MSM data PathFinder 2011.tab",
    "sha256": "da8e9bebe52840ac4130e55371122827731a42c0391bfa2ca80a4d73291febe1"
  },
  {
    "file": "ABTS-II_FSW data PathFinder 2011.tab",
    "sha256": "882bf9ede1859680f87b7c72192b1e21377e0765e380d9e6cf12e236bf8f7c17"
  }
]
EXPECTED_OUTPUT_SHA256 = "9f09e31a57f4d99cc6d0d867c2ff9ae6cdec2f888a4eab552ce16da3ee35ac56"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
