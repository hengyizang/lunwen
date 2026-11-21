#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-zyqvlr-replication-data-for-dif (10.7910/dvn/zyqvlr)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "data_hot_thermal_tolerance.tab",
    "sha256": "b90d59c6e0ac73507af49555cd74be08e529c89883199ff550d2952b6f5e4d2e"
  },
  {
    "file": "data_thermal_tolerance_time.tab",
    "sha256": "048828367bdcbdc9c000cd4702d811b237f05ae1173b7ef3d8751367d55afa1b"
  },
  {
    "file": "data_cold_thermal_tolerance.tab",
    "sha256": "a2ac10bdf9b7c1817d26fbbff35a75be893f2fe1a97ba6a9fb192a04a804481e"
  },
  {
    "file": "data_hot_thermal_tolerance_age.tab",
    "sha256": "7cf9c4ce537e761747b202aff847e99d8f3979d898f9d0f1e7f881e6161758b6"
  }
]
EXPECTED_OUTPUT_SHA256 = "1993c3eab7e8f56b9f4d009e4af3166ccd219962ad9861330310ba5f08b005ad"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
