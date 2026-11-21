#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-lccllw-multisensegolf-a-multimo (10.7910/dvn/lccllw)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Documentation.zip",
    "sha256": "026fcf22978ff9c42e01a02d70778967fca47a40effa4fa4c1f1e18bfad92e7b"
  }
]
EXPECTED_OUTPUT_SHA256 = "b11bf998481a06f6a127cc3697ec23ef061512507a3c0dcc02dbfd96ff68edfc"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
