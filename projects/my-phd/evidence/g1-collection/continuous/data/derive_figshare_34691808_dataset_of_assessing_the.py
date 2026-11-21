#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34691808-dataset-of-assessing-the (10.6084/m9.figshare.34691808.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Dataset RPA LB_145_RPA_SCR_SGR.csv",
    "sha256": "398717537b871f0c47293a366312537ca1fab96c22f3b67bfb4c7bd033fd761c"
  }
]
EXPECTED_OUTPUT_SHA256 = "08642636918664c617e4f41314e2956e7736fb85131e6e87601701c147348bcc"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
