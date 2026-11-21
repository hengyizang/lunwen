#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-35038195-data-sheet-2-multimodal (10.3389/fmech.2026.2040645.s001)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data Sheet 2_Multimodal nondestructive evaluation for structural assessment of composite wind turbine blades.zip",
    "sha256": "8d960eeec025d2fbc28e17dd985a2915349ff90d2ae00ce8c4e3c150faabbbc1"
  }
]
EXPECTED_OUTPUT_SHA256 = "508b7fa65bcf4362b65e58acf840a4d21eea16bdf1791f4fff37e7f7b9f4639e"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
