#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-33578671-source-data-for-tecobot (10.6084/m9.figshare.33578671.v2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Fig_3b.csv",
    "sha256": "db4cd6087b1a71584235c5e0e04601c3749bbd453f30add0c0d0858539152c8d"
  },
  {
    "file": "Fig_3e.csv",
    "sha256": "a8d5bbbd4de0c6c36924d09c85e47444291496fbaf86c545482b3f63dca3c31d"
  },
  {
    "file": "Fig_3j_cable_displacement.csv",
    "sha256": "270a787ae04b9a76f1c9c1e1c037ff81934007888a8c6a0165a169e91dd384a0"
  },
  {
    "file": "Fig_1b_table_S1_S2.csv",
    "sha256": "0368999c8d2c1ae73f65332a4e301300ed258d477015cd91bb1cdbed3663e620"
  }
]
EXPECTED_OUTPUT_SHA256 = "3bb69b59914d3ffd1645fce19d5910c43008bbf4d2593bb343bf7f9f13ddb545"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
