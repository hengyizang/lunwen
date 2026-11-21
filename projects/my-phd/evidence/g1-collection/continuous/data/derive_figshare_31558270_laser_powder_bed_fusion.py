#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-31558270-laser-powder-bed-fusion (10.6084/m9.figshare.31558270.v2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "friction coefficient-1.csv",
    "sha256": "c6feed0cde5b2a8f51f900119eb07c3f388c0e7508dca442c2b0698ed44ac1a6"
  },
  {
    "file": "friction coefficient-2.csv",
    "sha256": "dde9c8a9fc326b4341c2c1f8968042695ba8c593bbeb0a29daef0fb03dc61bd9"
  },
  {
    "file": "Raman spectroscopy-2.txt",
    "sha256": "9e7f2fd4be1e4a913b18199cd6b66273162d05eed80f4c1bf4f94f0ed6c4c75d"
  },
  {
    "file": "Raman spectroscopy-1.txt",
    "sha256": "f2c810d7a3a862dd81b3a8d572c78a4ba1ce99967b7783d165f7118219661987"
  }
]
EXPECTED_OUTPUT_SHA256 = "a6c35617c585444cc190a2c72aac4a66df0531298790c0110190057e0b603226"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
