#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32025606-snu-planetary-gearbox-da (10.6084/m9.figshare.32025606.v5)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "datasummary.csv",
    "sha256": "e4e0dcbb38b850bce883334a4e472a4d397cb17f69e5493d526f8e7a1a96d72d"
  }
]
EXPECTED_OUTPUT_SHA256 = "4984eb4da27a6e405ed418745b7a0b77f1cec916b83dea0d1f801644a5582f21"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
