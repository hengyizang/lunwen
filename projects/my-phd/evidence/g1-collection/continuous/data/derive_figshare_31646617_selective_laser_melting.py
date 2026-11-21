#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-31646617-selective-laser-melting (10.6084/m9.figshare.31646617.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "data.csv",
    "sha256": "bd1cf54731edffe1881ea8f9b2ea36eb9420c385bdf68c67187dcb5b3c2584ba"
  }
]
EXPECTED_OUTPUT_SHA256 = "4dc6dbba07080cdc45bd68e1e71ad5df5dc773d15b8b7f43e1a27f14bfb19fcb"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
