#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-7iajwu-the-multi-sensor-based-m (10.7910/dvn/7iajwu)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "T5_Tool_wear_values_for_all_Experiments.tab",
    "sha256": "6e2423c31e6756f367ddb57f01c00742519950235e8616411ce304c2306e6430"
  },
  {
    "file": "T8_Tool_wear_values_for_all_Experiments.tab",
    "sha256": "afe418f53a3bac71e5212121c893b0f40c1300bd2c3623fdcf69493494250e8d"
  },
  {
    "file": "T7_Tool_wear_values_for_all_Experiments.tab",
    "sha256": "beeab1a100fb0f4bfd1801ff0398df4eaecbb4a5afafcd261add6bc495334763"
  },
  {
    "file": "T6_Tool_wear_values_for_all_Experiments.tab",
    "sha256": "736b4aff7ab10590fca76e8240a564bcf8de1359f7eb5eff6ea3fdc80ca40fdf"
  }
]
EXPECTED_OUTPUT_SHA256 = "9a7860df0926bf239b7cfc7abbb7f5aff9c80a706fa33d7ba950a9e74272af99"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
