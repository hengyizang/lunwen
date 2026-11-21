#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-ckliy1-perception-and-acoustic (10.7910/dvn/ckliy1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "AcousticData.tab",
    "sha256": "4084821900503a9e9d08ab1d317b8e70abd90a59215d60ab673e914430ca941a"
  },
  {
    "file": "PerceptionData.tab",
    "sha256": "aa76ce948c53c82e734a35be4237daee33af6c7167211557b10ba016c9768d3b"
  }
]
EXPECTED_OUTPUT_SHA256 = "f187161a45dde6ac060e5a3349118b1a82000a5f5e63156f49d0a7051929ae9b"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
