#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-hfcsqz-cfd-tool-vspaero-actuato (10.7910/dvn/hfcsqz)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "W37.csv",
    "sha256": "643a2d22f71af551cdbef9d61e101ef17b8375bbb05616a3985b8d1e5f259af4"
  },
  {
    "file": "SW15025.csv",
    "sha256": "33a4220656b08892423dae70e2164e0c308410525e5d86e8cf72a269dbe915df"
  },
  {
    "file": "SW12525.csv",
    "sha256": "d2320f6d16a3a3943c3976f3bfdaf88a5b700e29ccda525c3b313750662723ab"
  },
  {
    "file": "CW2525.csv",
    "sha256": "fad9b85178982d0b31267f79d8d2d6ba20c8c145e50f4cd1120d33e6f5a63730"
  }
]
EXPECTED_OUTPUT_SHA256 = "6221adfbff073ef977192eea7f06736bab2f300b8955b472955e9ec8dc44762f"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
