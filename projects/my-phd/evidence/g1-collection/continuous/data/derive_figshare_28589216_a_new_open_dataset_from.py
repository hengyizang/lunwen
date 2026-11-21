#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-28589216-a-new-open-dataset-from (10.6084/m9.figshare.28589216.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "FeatureAndMetadata_Milling.csv",
    "sha256": "e125471f983e98ae326e2c47e15f633bb30738e285b9ad6e54b5e364d4d66dbc"
  }
]
EXPECTED_OUTPUT_SHA256 = "11c14f2212e2491aef21f42ae7ba1b92923f008cab32977a60dda5f4c6138280"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
