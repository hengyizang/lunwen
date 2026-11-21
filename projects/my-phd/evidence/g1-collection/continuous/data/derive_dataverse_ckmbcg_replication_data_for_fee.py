#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-ckmbcg-replication-data-for-fee (10.7910/dvn/ckmbcg)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "image_lit.tab",
    "sha256": "f7f3adef2265c62c3784813adf7e85f886de20e559871b799c65a239b9c2071f"
  },
  {
    "file": "data.tab",
    "sha256": "30cc2dc578ffff586fdc1ad0b71e2ff93e337b7cfa6a43f9d5ae7e78b7e5f582"
  }
]
EXPECTED_OUTPUT_SHA256 = "22434ca4e5be02369786ff169a08d4db23e133c0141ef0ad040fe258f8ab773a"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
