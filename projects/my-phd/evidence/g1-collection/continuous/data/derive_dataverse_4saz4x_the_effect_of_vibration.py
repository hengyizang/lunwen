#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-4saz4x-the-effect-of-vibration (10.7910/dvn/4saz4x)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data Capture Template - 200322 - Repository.tab",
    "sha256": "ce5db73af5fad6efdcbcd4cd46ad2022f9b5de9a0e4660c81e3ce2f20f6be4cf"
  }
]
EXPECTED_OUTPUT_SHA256 = "6249b326292fe3a2e3cefd889686b3b5c307842502de8c6d9bde2898c1022a87"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
