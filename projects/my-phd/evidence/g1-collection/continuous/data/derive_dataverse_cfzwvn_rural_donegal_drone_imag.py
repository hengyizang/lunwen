#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-cfzwvn-rural-donegal-drone-imag (10.7910/dvn/cfzwvn)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "user2~DJI_0140700.json",
    "sha256": "fa833327bc6269da090eee165cb06c9753687e4e5747715a2fd56d224ea555e4"
  },
  {
    "file": "user2~DJI_01532300.json",
    "sha256": "f063437eb0ab027ae38eca659a01a033b9be06e31feb269277dd93ab945dc82f"
  },
  {
    "file": "user2~DJI_01530.json",
    "sha256": "ef07499990095d0383f6e19632614bcf9d8c5b37a28bc988f26f6f5f7031a4ba"
  },
  {
    "file": "user1~DJI_0107600.json",
    "sha256": "4ae4b3ebff63e1901061f4f32869c932f0deaa8e9757499fe6e83e26993e3632"
  }
]
EXPECTED_OUTPUT_SHA256 = "d5901c30d2a712c6e684c313414e00b5231eb0b0bc4c9131da4cec81df87216c"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
