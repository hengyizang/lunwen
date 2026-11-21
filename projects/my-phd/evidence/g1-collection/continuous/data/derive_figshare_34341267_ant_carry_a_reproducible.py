#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34341267-ant-carry-a-reproducible (10.6084/m9.figshare.34341267.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "ANT_CARRY_ETRI_Complete_Dataset.zip",
    "sha256": "b12302f6ef9e93bca7a61e2184c1dbf1739ce5f98ea4b9cfc68b610d09987a5c"
  }
]
EXPECTED_OUTPUT_SHA256 = "0fc1608571acc9d78772558a81fcf1faee87039dd122ab2391f45eb93447efd2"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
