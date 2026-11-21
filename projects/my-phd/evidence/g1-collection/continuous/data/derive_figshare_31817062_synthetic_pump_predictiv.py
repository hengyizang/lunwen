#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-31817062-synthetic-pump-predictiv (10.6084/m9.figshare.31817062)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "pump_predictive_maintenance_dataset1.csv",
    "sha256": "fc69c38645f1b58da10a625020ba38338a3083808a9078628d8d53ca63418995"
  }
]
EXPECTED_OUTPUT_SHA256 = "e236b49a36c97771d5469f7da53ef28951d4f79423fabe27317860ab5f303c43"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
