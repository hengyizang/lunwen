#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-myrxr8-autonomous-integrated-sy (10.7910/dvn/myrxr8)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "AI in Archaeology Publications (Scopus) - Data Submission for Harvard Dataverse.csv",
    "sha256": "5749db2a529a36102eb6b57d13f24f3f828b418b0e281d3bc530f655fd503981"
  },
  {
    "file": "AI in Archaeology Publications (Dimensions.ai) - Data Submission for Harvard Dataverse.tab",
    "sha256": "986494582cea0e19b78f4e03f8214b9924a3093d6ee52c1139dc5efe2a93cf0e"
  },
  {
    "file": "UK Archaeology Injury Frequency Rates - Data Extraction for Harvard Dataverse.tab",
    "sha256": "a00dcb2eeda2563fa1f61620efd808ccb0020898109be14785048d779a412972"
  }
]
EXPECTED_OUTPUT_SHA256 = "fcf3def5f196fc5b0a872a167d0d0144c5d57b642e1a8d5c19f43ab9c807a85c"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
