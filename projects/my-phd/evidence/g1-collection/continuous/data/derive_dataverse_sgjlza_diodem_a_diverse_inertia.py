#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-sgjlza-diodem-a-diverse-inertia (10.7910/dvn/sgjlza)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "exp01_motion08_imu_nonrigid.csv",
    "sha256": "55f52591a1d071e1978bd3535a19a4edd4d84ec81078b35dd053142803eed2cb"
  },
  {
    "file": "exp04_motion06_imu_nonrigid.csv",
    "sha256": "1784f4f7c0097c21ac47b6a7951410d45e86e79643366f5926f6f9a5bfc94ce1"
  },
  {
    "file": "exp03_motion03_imu_nonrigid.csv",
    "sha256": "55df593d960c7d2507f8e45d474d78c3d0d8446704fc924f94a517a0043f427c"
  },
  {
    "file": "exp04_motion02_imu_nonrigid.csv",
    "sha256": "d9c5e5becb57766ff1e93707f2336e0f8a3136589d36728428471094f13bb5ed"
  }
]
EXPECTED_OUTPUT_SHA256 = "f4210b80eedbcbcb8dc932df849f1715f329fdba26cb98f904f8d0cba0acf440"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
