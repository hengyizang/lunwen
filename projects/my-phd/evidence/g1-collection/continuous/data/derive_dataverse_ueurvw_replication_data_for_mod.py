#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-ueurvw-replication-data-for-mod (10.7910/dvn/ueurvw)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data experiment 1.tab",
    "sha256": "8c989a7068b7b86487f37fc9bf8ade9e7f36066dc2f5c03fc9ad02267ed83f75"
  },
  {
    "file": "Data experiment 2.tab",
    "sha256": "e942de120bc3700a592b2368d4612ad5279859c783af5bf4f269981132449872"
  },
  {
    "file": "Data experiment 1-1.tab",
    "sha256": "8d1f6bed71bbfda6c586cda008c07b2d813159a0021be8cc3c685bebdc2334b3"
  },
  {
    "file": "Data experiment 2-1.tab",
    "sha256": "3ba31ca9eda8dcb3246fecefb48a054e95fb5399ee1c99e32e82c38448b7ca8b"
  }
]
EXPECTED_OUTPUT_SHA256 = "e913edaea0c8b4c54bca7864897bf9084746527b8a9297712df419d06b566774"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
