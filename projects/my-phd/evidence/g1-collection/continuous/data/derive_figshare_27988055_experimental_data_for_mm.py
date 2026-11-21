#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-27988055-experimental-data-for-mm (10.6084/m9.figshare.27988055.v4)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Revised Data.zip",
    "sha256": "e3012d302b207dffd0877b091080746f82f6eb7aae27fed3e348af18ac9d0a46"
  },
  {
    "file": "Raw Data.zip",
    "sha256": "80918cb7dec597e24c5c971af250c02624e3a465c57430c561ff6954f8401c88"
  }
]
EXPECTED_OUTPUT_SHA256 = "7c11f608bbb7761fbc0876e33e6eeaa0be9410aa522890b4ba8b5ea1a2cc4aff"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
