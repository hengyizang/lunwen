#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-35049556-data-for-a-four-level-ex (10.6084/m9.figshare.35049556.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "data_package.zip",
    "sha256": "4899442117fdbeb9040296fb14b9c1d666c9d98deb5c634b34925cfed356d9c1"
  }
]
EXPECTED_OUTPUT_SHA256 = "4f30face2f3e87e5cc8573b387584ab50989a7a72b1026759a2a5c193ac286ff"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
