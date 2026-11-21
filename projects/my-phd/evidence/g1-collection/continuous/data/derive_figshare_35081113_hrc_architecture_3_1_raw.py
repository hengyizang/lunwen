#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-35081113-hrc-architecture-3-1-raw (10.6084/m9.figshare.35081113)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "INVENTORY.csv",
    "sha256": "4a56e090f3e534df7e315ab822fc7fc0eab0e329903b4b65292f8b9ab2006399"
  },
  {
    "file": "INDEX.csv",
    "sha256": "49e30282fb4b7c30b19a569f11493bf06f01700bc0607112a35a0e052caf1e1a"
  },
  {
    "file": "stop_check_compare.csv",
    "sha256": "2ea8655bd660b58f2d028462a3e549af4711168c486bdd6d37a360bf497a1ed8"
  },
  {
    "file": "stop_samples_compare.csv",
    "sha256": "a605a68d5124a7419ef9ecd377a640c74e2132753cbfc8e04bdbf481255ff4bf"
  }
]
EXPECTED_OUTPUT_SHA256 = "35d787f79359491f449f834d6c2389e931561498f959f0fdd2c19f5f7057b0e0"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
