#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-wjgdur-fem-data-for-large-radiu (10.7910/dvn/wjgdur)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "FEM_Dataverse.tab",
    "sha256": "9c74ea6f9d84a0e79f4e14f1992d5862d35d78affa5111f1070b597412445c5d"
  }
]
EXPECTED_OUTPUT_SHA256 = "47a6cf3814fb3e03e250b7912ac1777ed21f7e9eb7c86a3a52b03d0f0be6899b"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
