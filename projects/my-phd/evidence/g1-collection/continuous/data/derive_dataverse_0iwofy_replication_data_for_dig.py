#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-0iwofy-replication-data-for-dig (10.7910/dvn/0iwofy)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "academic_russia_confirmed.csv",
    "sha256": "82250b70387637706c89cddde5b075d29e0f78dcb3c40d26c4ee0c63a9145a79"
  },
  {
    "file": "forced_choice.csv",
    "sha256": "9b2d3dca2d297eab738248a26ccc50c8896ef92317d7de8ba41baaefa404f2ed"
  },
  {
    "file": "stage3_c4_consensus.tab",
    "sha256": "5dd28d4a795c453b74d348f8bef30b0bc65e46585b8ea35d5129041d59dc0bba"
  },
  {
    "file": "classifier_signals.tab",
    "sha256": "5107af37eaec3e28f14e906a0d0658518a9ffb54073fae992c1f1192efaedc1a"
  }
]
EXPECTED_OUTPUT_SHA256 = "7a9e2475915d34e2bbf0c2df82bf7175926cb1030268160ce4b8fdf3c938023d"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
