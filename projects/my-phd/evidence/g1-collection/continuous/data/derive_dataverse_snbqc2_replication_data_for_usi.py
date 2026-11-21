#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-snbqc2-replication-data-for-usi (10.7910/dvn/snbqc2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Fig2H_ATR+_calcs_all.tab",
    "sha256": "4c66f11347a1326b16ff6b3befc6a95fb1733558a8ac21143f772356a40d370c"
  },
  {
    "file": "Fig2D_Larval_free_motion.tab",
    "sha256": "f2b06c512b2c7b72a33b9d1e1df9e14557a329140f9715a2217d07ca32f7e64e"
  },
  {
    "file": "Fig1D_Adult_free_movement.tab",
    "sha256": "13a0e7a7eed4feb60c434ff466f95bf9b0fa238d6920390974db41557649e027"
  },
  {
    "file": "Fig1H_HC_Chrimson_PI_Comparison.tab",
    "sha256": "2371f1cb59c8e8bb996c5dc09656bda6754cbee03e36d02ae4954a26a4f5f33e"
  }
]
EXPECTED_OUTPUT_SHA256 = "6ecccc817d4d3330a6bdd77a004a52e2204f794764b83a0a8ca0b5ffbf8e292b"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
