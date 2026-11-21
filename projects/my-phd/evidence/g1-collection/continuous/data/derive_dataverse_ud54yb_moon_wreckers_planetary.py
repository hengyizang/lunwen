#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-ud54yb-moon-wreckers-planetary (10.7910/dvn/ud54yb)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "ak1_vive_driving_stuck_jiggling_highbay_20171206.ak1.odom.csv",
    "sha256": "a86c89f001742fa2d5b291cd82bf226693a90172fd4a15a4a77f4d9500c7ae25"
  },
  {
    "file": "ak2_stopped_compositelab_20171109.ak2.odom.csv",
    "sha256": "cfa4018a47596ba9e49856395d90031948aae8139a9bb721072c4dcf6504abe5"
  },
  {
    "file": "ak1_vive_stopped_highbay_20171130.ak1.odom.csv",
    "sha256": "3d90e048b4339a36e1b51a03561ce8977a4e37ae3bfe4236fc290870080213ca"
  },
  {
    "file": "ak1_vive_driving_normal_rocky_highbay_20171206.ak1.odom.csv",
    "sha256": "6b2175d3860b3212ba71e6c728022b66dea44bcf225f2e6ed6887bb93362c9b6"
  }
]
EXPECTED_OUTPUT_SHA256 = "abc1db9b6a091821329e6d8a46a9831f5ff60c00d9498b0abf66a77e3dcb2c29"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
