#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-m6jxed-open-ended-creative-and (10.7910/dvn/m6jxed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "OLA_07_creative_play_2026-06_codebook.tab",
    "sha256": "a01a6467f93ce2a525ae6ecd003a2a87430f108a7494822c16b3ca6ade675b5b"
  },
  {
    "file": "OLA_07_creative_play_2026-06.tab",
    "sha256": "ab951508fd39501c5be5ff0a6040be973f117c7506fc463fd54e864a20fc9821"
  },
  {
    "file": "OLA_07_creative_play_2026-06_README.txt",
    "sha256": "8e00b728913d123d2c4e707fe56033ffbfaaaa82f447ecdf20d82b9d40c4c490"
  }
]
EXPECTED_OUTPUT_SHA256 = "16a4a419dd9d588ed74830158b7eb5cd54ad3031fd9da6848e2872288af04e4d"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
