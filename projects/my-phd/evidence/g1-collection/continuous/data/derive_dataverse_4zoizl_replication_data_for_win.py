#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-4zoizl-replication-data-for-win (10.7910/dvn/4zoizl)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "SYM_trial45.tab",
    "sha256": "3ece0c7ef9f46f0e0bdfa3f1c034e5fafc60ef8e68d3e6043a9206c032273a4e"
  },
  {
    "file": "SYM_trial10.tab",
    "sha256": "63658796ee7ce2a6d0eb5544721e5d85d6c3df45afb50c2fcd34a6cc2f061ec2"
  },
  {
    "file": "SYM_trial12.tab",
    "sha256": "c9dc6d4bd4616bd36f748844d81e69752a1782565e0ddfca2253aff15e8a24f5"
  },
  {
    "file": "SYM_trial46.tab",
    "sha256": "aef16a3e28717673014a97f6c8b72c139130026dda55d4b84a3e035a12ad95e3"
  }
]
EXPECTED_OUTPUT_SHA256 = "8a9e73ff3a0f1972a0cbf87507aaf143c4fb2b58703f8ed93248fe01aa7164e9"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
