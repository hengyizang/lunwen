#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-wcmvol-airfield-pavement-manage (10.7910/dvn/wcmvol)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Final database for airport pavement index project.tab",
    "sha256": "55997178e8f25f125e2b4ca96b03136132a4798bb8ab08bc0065cf5adbcbe20e"
  }
]
EXPECTED_OUTPUT_SHA256 = "4aa65633406fb9cc5a82f4b986f3f2021868722a4de7dbceb35b3f4adf7de95f"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
