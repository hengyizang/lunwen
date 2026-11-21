#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-nssigl-date-stamping-us-housing (10.7910/dvn/nssigl)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "US.tab",
    "sha256": "0ba1e5896d6921f58262f9feb1f59f30e9a2204e2a651c4353a4f95212c41ac9"
  },
  {
    "file": "ShillervsWinans.tab",
    "sha256": "18e8d76e61a221929dff5da260b33a2fb51c210611c533182faffb26b211e690"
  },
  {
    "file": "Housing prices GSADF_mehmet.tab",
    "sha256": "339259adc2f760f9bbb4a8bc251f15e06e086af74eef2b08ad1fcecf3c29dd97"
  }
]
EXPECTED_OUTPUT_SHA256 = "ca41ad23d7e2eb925f5c98bdb8b9ebf1134d8354f71fc6977b165341643224ad"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
