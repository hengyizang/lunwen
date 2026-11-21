#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-8cse6u-drone-telemetry-record-d (10.7910/dvn/8cse6u)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Drone_Flights_data_dictionary.tab",
    "sha256": "2fc41b3c7af0a4d9c039844abf7dd8792e0d87797fce4561e9b0567ec7605454"
  },
  {
    "file": "5_RSMH.tab",
    "sha256": "3bc58064b3d97164d721e1aba4bde8f54b30f67c773e7dc2e38b7998ab8ca915"
  },
  {
    "file": "1_RSMH.tab",
    "sha256": "08f5fd4b69b2325e5b425113b8ed6b85d66dd049c29ba857efc562a0d0af5f67"
  },
  {
    "file": "2_RSMH.tab",
    "sha256": "17a61124aa84dedc590f51378ff2711c2b2fcf5a43bdf1beb04e151f11c456ed"
  }
]
EXPECTED_OUTPUT_SHA256 = "125b1acf0be832f08811770f39dada8874142a034bc0ef4cf769f121112bd6ad"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
