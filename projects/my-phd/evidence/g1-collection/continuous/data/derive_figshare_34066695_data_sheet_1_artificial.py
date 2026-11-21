#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34066695-data-sheet-1-artificial (10.3389/fenrg.2026.1956543.s001)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data Sheet 1_Artificial intelligence-assisted design and CFD re-optimization of graded hybrid metal foams for faster hydrogen desorption.zip",
    "sha256": "4f9ab8a6081de8ef5ad2b494e0b835021a3f1360150a04d8dd22925533a35ccf"
  }
]
EXPECTED_OUTPUT_SHA256 = "15330f6906cb763379d0cb50b964bfe1a8a15679fa8389de3dc99fcd3cb96444"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
