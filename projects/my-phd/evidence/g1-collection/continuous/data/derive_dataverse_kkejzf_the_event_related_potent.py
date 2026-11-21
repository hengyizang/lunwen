#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-kkejzf-the-event-related-potent (10.7910/dvn/kkejzf)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "C30.txt",
    "sha256": "a587c1166093bed66bb6627fb925ebe2a0c392e8a67d26b22e185f31d39b32b2"
  },
  {
    "file": "EARLY6.txt",
    "sha256": "1200c0a316aad34bf6e1113704ea82d95b0d021f5d279eb74104609cc944d2d4"
  },
  {
    "file": "C33.txt",
    "sha256": "d8efbbddbfc88cd38198e3d47fe43bec493843edfac25cfc57bd903baa136f9f"
  },
  {
    "file": "LATE19.txt",
    "sha256": "27dc760f8459c9e63b0bc95fffad6dd47147aeca1954eccec0ddec9b65737e44"
  }
]
EXPECTED_OUTPUT_SHA256 = "2aba63a076c253b7dd56bdedafaf59714b446cca8713616995cf8dc477d9c618"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
