#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34476927-data-sheet-1-a-vision-ba (10.3389/frobt.2026.1948863.s003)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data Sheet 1_A vision-based closed-loop framework for adaptive ergonomic human-robot collaboration.csv",
    "sha256": "45ac02efcb333f1773ffd720cc2b047a2f001f6d50e7cb1f92336cc9179f7f4f"
  }
]
EXPECTED_OUTPUT_SHA256 = "a7b57928aaad44a83a862563c66e61f16ef2b9790796f7e73f211f5769025e37"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
