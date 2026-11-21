#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-z1ohnl-replication-data-for-rol (10.7910/dvn/z1ohnl)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "splitC4-C6_5mms_100g_run1.tab",
    "sha256": "ff5918e2ede4b30581b3816acce5084b14899f0c36aca931a6e7d3e16c7125f5"
  },
  {
    "file": "splitC4-C6_25mms_25g_run3.tab",
    "sha256": "87fa3b75c3fb5bf5d0e6e319a1483b0ad343b5246b400111b59aaf34d470357d"
  },
  {
    "file": "splitC6-C4_45mms_0g_run3.tab",
    "sha256": "a5984b9c70e44e1637bef45e7cd4d4572890f987e786586606ddc5a3ead095cd"
  },
  {
    "file": "splitC4-C6_25mms_75g_run1.tab",
    "sha256": "2da66aaa037c9a56f66859d8054bfea742d4633936df150f605b8894d33bc1a2"
  }
]
EXPECTED_OUTPUT_SHA256 = "78602ab094d6a2631d80c31b6412fa589ba13de68d9ce900c81c98ec1c74010f"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
