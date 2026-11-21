#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-efnv5j-replication-data-for-hyd (10.7910/dvn/efnv5j)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "L4_IL_Header_Data.txt",
    "sha256": "81cdd210694d2b8bf85d95843e7bec788c43110fb373a702d13f2ae2d747de77"
  },
  {
    "file": "L4_NV_Header_Data.txt",
    "sha256": "020e390f418bbd95f8c2f650cbeb3746da5e69d22c4aabffbd53e6aef059c77b"
  },
  {
    "file": "L4_NE_Header_Data.txt",
    "sha256": "9b81de132d1b6d6a51f555e6cfa026d5abb09a4a67866989a4d73caea3013dcb"
  },
  {
    "file": "L4_MI_Header_Data.txt",
    "sha256": "4aeab3f1a8d761b437b1c31e9bb3038003c42d2b0d5b35f9027d8ddb33e186be"
  }
]
EXPECTED_OUTPUT_SHA256 = "ec48f1332a708878a5b0a7015a75c68e9b2c31f3a5a7183a03e313170983d7c5"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
