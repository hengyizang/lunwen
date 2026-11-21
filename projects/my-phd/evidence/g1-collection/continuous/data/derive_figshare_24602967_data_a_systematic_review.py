#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-24602967-data-a-systematic-review (10.6084/m9.figshare.24602967.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "data_extraction.csv",
    "sha256": "533ad76fe1e6011f8428caeafce3e0a534986d3198f9b33c3143c49c88d08fd8"
  },
  {
    "file": "imported_articles.csv",
    "sha256": "a8c97a4ab9e6cfaaccde1c4c767cdecbedb668d0b15e4f4cdfbd011c2569f5ca"
  }
]
EXPECTED_OUTPUT_SHA256 = "0ebdec446aac4bd7db372eb3604c202c5c51e2b5796742128fb31835ad2c454d"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
