#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-25880-annual-behavioral-tracki (10.7910/dvn/25880)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "ABTS-I MSM Pathfinder MH 2008.tab",
    "sha256": "4e2b18c6ac7002feaa5b48951e6098b7dc6e5a8f94920906abdb2d192b73f7dc"
  },
  {
    "file": "ABTS-I FSW Pathfinder MH 2008.tab",
    "sha256": "58878f981a8c58beea1daffa617e7a517187b7ebb13d7e652701ebff2e30853d"
  }
]
EXPECTED_OUTPUT_SHA256 = "835437f2bf9930e22a7ba00059ccc017cefc03d281b793794bd315e9d416a557"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
