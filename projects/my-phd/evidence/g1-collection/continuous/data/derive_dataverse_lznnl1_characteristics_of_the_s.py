#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-lznnl1-characteristics-of-the-s (10.7910/dvn/lznnl1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "TSFC_over_T.tab",
    "sha256": "a6a3c87d20b1066f3e7e854e0cea561c1600ee2dafa6486bf482735b88511df5"
  }
]
EXPECTED_OUTPUT_SHA256 = "a74cee4e7edc45d354550652b76d4f0658fb63b69d7d18c72c8cf0d947673be5"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
