#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32445474-supplementary-file-1-des (10.3389/frobt.2026.1839026.s002)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Supplementary file 1_Design and experimental validation of a soft pneumatic robotic device for preterm infant skin-to-skin tactile thera.zip",
    "sha256": "48dc9db6a96267c386588bd6c7c7f8156163687bfbe128280f6197f6b0719c58"
  }
]
EXPECTED_OUTPUT_SHA256 = "763256e8885afaf6e9ef48a572d91779783183462fe98a1f4238aaed0a3b1074"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
