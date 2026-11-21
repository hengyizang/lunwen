#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-r0ozel-when-travel-meets-robots (10.7910/dvn/r0ozel)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "402.tab",
    "sha256": "5dfc576eab09b8b3ce8f3767f61aeb6a1199f471f3b45f87895672d0d9fd4e62"
  }
]
EXPECTED_OUTPUT_SHA256 = "7c82e414dd762660d57b6b4ac33de9cf87e39e4f697fd0f242ca9eb507510161"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
