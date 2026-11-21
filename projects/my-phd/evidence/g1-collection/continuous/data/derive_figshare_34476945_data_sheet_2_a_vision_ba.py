#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34476945-data-sheet-2-a-vision-ba (10.3389/frobt.2026.1948863.s002)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data Sheet 2_A vision-based closed-loop framework for adaptive ergonomic human-robot collaboration.csv",
    "sha256": "8afa86e63d0a78ee9e59895695095e56de2335dd48ac991a4046296f7d4af7ee"
  }
]
EXPECTED_OUTPUT_SHA256 = "5097f8ca007f663ead33eef5ef12378caf031f9eb4ba80c9d8ae2fd78682ad5f"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
