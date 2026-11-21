#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-epu7uw-scoop-with-spatula (10.7910/dvn/epu7uw)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "scoop_with_spatula_fed.json",
    "sha256": "2a2b5622df5f5510cc8db30f8a4b3c5c852ecc9cf83bd2c6186af6e3e11f0f89"
  }
]
EXPECTED_OUTPUT_SHA256 = "0f39bb0243890dcc81944bb7ef97541c82d1eda076d10cb1d72906afbf0bd1bb"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
