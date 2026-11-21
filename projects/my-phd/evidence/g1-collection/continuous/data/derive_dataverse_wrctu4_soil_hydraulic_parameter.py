#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-wrctu4-soil-hydraulic-parameter (10.7910/dvn/wrctu4)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "all_fitted_hydraulic_parameters-final.tab",
    "sha256": "4310d567b54edcc92e45371f70da7faec470113e4752ed267aaa915a42c5d4c6"
  }
]
EXPECTED_OUTPUT_SHA256 = "4c588c01e973fb76a220b7df4f28d095670e33c131a8760304a013ef3de5dc2e"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
