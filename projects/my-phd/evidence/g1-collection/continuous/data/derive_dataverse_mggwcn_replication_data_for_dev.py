#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-mggwcn-replication-data-for-dev (10.7910/dvn/mggwcn)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "06_wb1_142MP.tab",
    "sha256": "247852f86c017bc03cac5b4094a23488636773a781ecdc7ad9b144c6d2f2ca8b"
  },
  {
    "file": "01_wb1_142MP.tab",
    "sha256": "01bbb6761b4304d6cdf2460d0078e0226ab5cfbbcde5c3632e10dc7a439d77df"
  },
  {
    "file": "01_eb2_139MP.tab",
    "sha256": "c4f69f00bf0048b348d77117ff1e663d8e7e1c48acda400e2739dc3b4d1255f1"
  },
  {
    "file": "01_wb2_142MP.tab",
    "sha256": "567d6aacb22c14320824008b3cc0b814bf3902accc824a24afcc3b6dcf88266f"
  }
]
EXPECTED_OUTPUT_SHA256 = "74379d2bf36a39ac78a0247657f85ed89ff4a9a751e32313d3cd9c472473feba"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
