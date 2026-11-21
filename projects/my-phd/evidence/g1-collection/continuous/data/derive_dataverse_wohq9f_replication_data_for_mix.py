#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-wohq9f-replication-data-for-mix (10.7910/dvn/wohq9f)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "13_TraitData.csv",
    "sha256": "5d1ccf03e6886e0e8d3561974085655a0274341dce13e7ef671dce635ca515eb"
  },
  {
    "file": "09_HuberValues.csv",
    "sha256": "06cbf9f5a17811021723cc7d8fc26d723b2116a6d5c44276f4b2764341fc998e"
  },
  {
    "file": "02_MurrayParkRainfall.csv",
    "sha256": "bea0aeac529d1a1383cd2b91796d10c91a6b873fca85561b1f5e35eca9db7be5"
  },
  {
    "file": "03_CHIRPS.csv",
    "sha256": "ec27b537b922fbe5d2db53a6f2b922842d3782828fd50b09a0599c3daeda9f84"
  }
]
EXPECTED_OUTPUT_SHA256 = "7e86aec8f4f0677ec7034c40ed01d90e9092532aa69d6d1a94db3af893aab7b9"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
