#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32141986-brac-act-supporting-data (10.6084/m9.figshare.32141986.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "BRAC-ACT_supporting_data_editable.zip",
    "sha256": "acedb8161340ea9a3af9954350bedea9d2061be8b19fbe7a40df9aebcd479804"
  }
]
EXPECTED_OUTPUT_SHA256 = "b1507052a0fe3dfc987d9e68191ce26bf7d10872df930c0964af57cecd6c38a8"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
