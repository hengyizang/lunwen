#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-zbhakc-an-acoustic-quench-detec (10.7910/dvn/zbhakc)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "19ja063_fig4_data.tab",
    "sha256": "f3812cabf442936bfc8f50d7dac66daf24898c52d9576801f4f53182a9e98afa"
  }
]
EXPECTED_OUTPUT_SHA256 = "460fad029c513f5aa9417a4d27247cbb365f87b967b657d02ccf9c7164f7b9eb"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
