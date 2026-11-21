#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-d0zgsm-acoustic-mems-sensor-arr (10.7910/dvn/d0zgsm)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "20ja042_fig5_data.tab",
    "sha256": "ee045c0e8a7dc648deb42d6fb28aa8c98587b92aa682a576c8a45944ac98b459"
  }
]
EXPECTED_OUTPUT_SHA256 = "78a6bb91b46efd8b9f7637402e79faf7d5e154bfa9d53b5cc15ae872012681df"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
