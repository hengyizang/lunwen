#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-c4ydif-results-of-the-graph-and (10.7910/dvn/c4ydif)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "optimization_history-1.txt",
    "sha256": "3d87bd2f2e3f20ae9c81270b27d5404e66b65375b4f891fd43f5ed999544bcce"
  },
  {
    "file": "optimization_history.txt",
    "sha256": "b5b28ace2a57dc64e43883b00a90b01b6f56f94308bb29ed6ce90791d71f5185"
  }
]
EXPECTED_OUTPUT_SHA256 = "d908100130e66705917822ef4b4fbee6e9480d9389b98846d100222a8305d8d5"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
