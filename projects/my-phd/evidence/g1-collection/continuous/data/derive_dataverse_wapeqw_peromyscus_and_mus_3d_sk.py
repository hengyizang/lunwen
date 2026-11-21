#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-wapeqw-peromyscus-and-mus-3d-sk (10.7910/dvn/wapeqw)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "elisa_pre_post_tmt_raw.tab",
    "sha256": "ad43618f03c98fd6f041ff8bc3880aaff5b9dccb142da1ef7d804262967d40aa"
  },
  {
    "file": "TMT_test.txt",
    "sha256": "23896ef49bbbafe8cc68da77b6d4e6fdfca46350c9e458372c38c8471e83c6c5"
  },
  {
    "file": "elisa_pre_post_tmt_analysis.csv.txt",
    "sha256": "ee06d622dc8a1b3acf92c40df10f3aa7fce78123ec3345c8bca28d9ddce97efa"
  },
  {
    "file": "250810-tmt_no_recordings.hdf5.parts.json",
    "sha256": "ea46de1b31259dc6562053b1d862febc9edd6f8bd3be70a8223e655c93bc068e"
  }
]
EXPECTED_OUTPUT_SHA256 = "88786e7ec076f1ebc6fcb5e6fa4cb0650bf8182fc0650b858bada21f723bc0a1"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
