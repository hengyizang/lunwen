#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-25024495-optimization-of-a-hydrog (10.1021/acs.analchem.3c04186.s006)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "ac3c04186_si_006.txt",
    "sha256": "9d05e14cdbecb059a07f79b3ad989892d2e273ecae929242e564a373bb2379e5"
  }
]
EXPECTED_OUTPUT_SHA256 = "01dfe51fa6f633c8090cc24056461a2c3a00411c702139dec3691a21aaf24b17"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
