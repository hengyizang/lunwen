#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-fs95y3-gomezmurillotarwater-ant (10.7910/dvn/fs95y3)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "GomezMurillo_2026_Antswarmmech.tab",
    "sha256": "3cc853cf2fb07e68c4c555e9027a82234e21bb9b4eebe76995e760088b387a47"
  }
]
EXPECTED_OUTPUT_SHA256 = "9d88f98a3bf907b0a1b8b075b815503bc999e1e4b02a0be7dd7a61a73571703d"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
