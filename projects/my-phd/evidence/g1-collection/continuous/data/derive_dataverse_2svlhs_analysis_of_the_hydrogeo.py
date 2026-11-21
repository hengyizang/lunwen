#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-2svlhs-analysis-of-the-hydrogeo (10.7910/dvn/2svlhs)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Seismic Sequences' Data (Bao and Eaton, 2016).tab",
    "sha256": "7cbd9189013d9a52aba8d227a19e2af6a4b4cc5a884462d5284ab8a80f23c9ed"
  }
]
EXPECTED_OUTPUT_SHA256 = "bdd061e01bae6fc56d75710a7473b944e7db8cfdab6493f6ac57c1a85b8dddfb"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
