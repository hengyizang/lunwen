#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-xfuwjg-simjeb-simulated-jet-eng (10.7910/dvn/xfuwjg)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "all_bracket_metadata.tab",
    "sha256": "687a77d3e3657f38086b13a18c78696b9d8d8e911a6ac728c2cb39cb4a6923ae"
  }
]
EXPECTED_OUTPUT_SHA256 = "e74bf7add14b7b1405745a82ddb97fe387e00d7b7e2dc089cdebda4a605728bf"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
