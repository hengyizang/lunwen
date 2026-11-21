#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-j6ktrs-the-role-of-awareness-on (10.7910/dvn/j6ktrs)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Bubna_Frontiers_2021_Temporal Recalibration_Data.tab",
    "sha256": "f6308de1e39de66cca242b39ad37667b457f2b966a3e6070b108f31ab560c036"
  }
]
EXPECTED_OUTPUT_SHA256 = "cd4f8077772e886d9e249372043b802a629c09ca159aef400d7177082751e260"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
