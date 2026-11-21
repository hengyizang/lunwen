#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32308917-dataset-for-laser-weldin (10.6084/m9.figshare.32308917.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "laser_welding_data_scaled_train.txt",
    "sha256": "8202e327786d8de23190b4d0908b4e45c76a17a1ec70a3d24b837ce70f35614f"
  },
  {
    "file": "laser_welding_data_raw.txt",
    "sha256": "4615a3972488bcdade134768bf7c7728ddde7ddf29335c09ee44593a6a884354"
  },
  {
    "file": "laser_welding_data_test.txt",
    "sha256": "b954539e6417f5aa9d8e239495a970ad880450c280873dad0f3bf05f59cab798"
  }
]
EXPECTED_OUTPUT_SHA256 = "8272bce36317b7c544f6d393fda4b882dc5459c106b145e4d52033779da7387e"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
