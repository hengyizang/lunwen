#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-24116583-dataset-robotic-sanding (10.6084/m9.figshare.24116583.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "processed_confocal_data_cR.csv",
    "sha256": "551d8bbee4bafb6a3ad1f832f53cb33ee04b6a027eda35cd264a37ef36dd7ad6"
  },
  {
    "file": "processed_stylus_data_R.csv",
    "sha256": "cfd5e65795da6a479d08cc79d1f36dddb1e44d3d850273e074b6ad7db25e3d36"
  },
  {
    "file": "samples_names.txt",
    "sha256": "777279801be0a06809af40992a2513e4e123c12d3b75c1afc17214b4ac166228"
  },
  {
    "file": "RAW_Images.zip",
    "sha256": "41ec175d2b2e7381fe7ea3e1c7565c1e5a06ee1023cdb681a04f8402bda53ca0"
  }
]
EXPECTED_OUTPUT_SHA256 = "8e3ee3c304eafa2c13ba4f9bd2a2579e73e1cc0ac2d217ebb88315d21a59d69c"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
