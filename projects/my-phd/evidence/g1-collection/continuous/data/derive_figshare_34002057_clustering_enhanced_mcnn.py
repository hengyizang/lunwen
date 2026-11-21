#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34002057-clustering-enhanced-mcnn (10.6084/m9.figshare.34002057.v2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Fig07_torque_no_load.csv",
    "sha256": "3ae2b31aaf2d9ec62a371161a55602735bbbc78e2d63ac82155a36d99df0030a"
  },
  {
    "file": "Fig09_torque_sudden_load_10Nm.csv",
    "sha256": "41f807b6870bdd08b1f1333ed4746c4e70dc3dbc4de9c3c9211b6be1ea148335"
  },
  {
    "file": "Fig11_torque_steady_load_10Nm.csv",
    "sha256": "caa6d651626de1ebe63669d7b721e78a0e70c05260318abe8ce3f067e6b6b51d"
  },
  {
    "file": "Fig10_speed_steady_load_10Nm.csv",
    "sha256": "eb5e7b08ef2820c41288c4d6db420955f98e9a55d0e746e4537b8ec9d671a818"
  }
]
EXPECTED_OUTPUT_SHA256 = "ca4106d9fa2cffdc33fc695eb15ba46b83604e6ab0bbe419fdebc8562bfbdd2c"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
