#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-0wb6z1-the-replication-material (10.7910/dvn/0wb6z1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Robot.tab",
    "sha256": "24a008db25af3d8a4a07fd674da73481ba8d1bb6387a9c24bed16581cb3cc7bb"
  }
]
EXPECTED_OUTPUT_SHA256 = "68a96bc25f15de6419f7da2857c97518ee1b985f6218c9274564815c38a2d043"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
