#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-cc355j-experiment-dataset-for-t (10.7910/dvn/cc355j)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "block_04_case_07.tab",
    "sha256": "416df3a23bd642c23cef57e45e39d5a087863afbb6f770af5630dccc0aa90ba6"
  },
  {
    "file": "block_03_case_08.tab",
    "sha256": "e696d2e5ca94d722ea8637fcc9be3d840f4a19596acc9be2a46ae9769bb04bd4"
  },
  {
    "file": "block_02_case_07.tab",
    "sha256": "2f7ff9df5eca2c64f427d1003217808aa854e455f9e90dfad599bd57256f6a65"
  },
  {
    "file": "block_04_case_09.tab",
    "sha256": "8eb489c5485c32493843a7216d2b9521dd960082182fdfa28bdadb62db9b76a6"
  }
]
EXPECTED_OUTPUT_SHA256 = "fbaacfe622355bcf93b6e8300fcf6bcc009eae9ca226b8ac77145b1218d9ebea"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
