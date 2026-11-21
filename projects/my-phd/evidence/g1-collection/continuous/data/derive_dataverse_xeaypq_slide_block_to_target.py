#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-xeaypq-slide-block-to-target (10.7910/dvn/xeaypq)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "slide_block_to_target_fed.json",
    "sha256": "7d93310b0f77fabea4ce9fc9a4d33fc7cd679e0054a8b10834f44fa29f4d7c22"
  }
]
EXPECTED_OUTPUT_SHA256 = "ff9c9405cc1c072e1408b100fcd80d08ff080f37ee366f2da9df30a8504c3b4c"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
