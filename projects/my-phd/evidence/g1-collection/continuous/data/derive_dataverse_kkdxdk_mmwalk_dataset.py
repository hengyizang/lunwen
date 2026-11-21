#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-kkdxdk-mmwalk-dataset (10.7910/dvn/kkdxdk)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "QAPairs.zip",
    "sha256": "82d91d6cf85179c2eb91ec3adc016561b8610edc58ac235a0d1a3ba4c8f68f47"
  }
]
EXPECTED_OUTPUT_SHA256 = "c35819f756d285afc2d21d0f326ada1ef85c9aed3a89f2ed3fb689de8f969f6d"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
