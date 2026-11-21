#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-yuiynm-replication-data-for-com (10.7910/dvn/yuiynm)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "crib-drone-survey-results.tab",
    "sha256": "d35d03d5c6fa812541732881d4d6de7bedc16f35c21961adc000b0ab46c2111b"
  }
]
EXPECTED_OUTPUT_SHA256 = "e08c31d64d8289c752f9fb775dcea0ee96dc5188367a28bb4673eaebe7c8bfeb"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
