#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-xtpysv-light-detection-and-rang (10.7910/dvn/xtpysv)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "ProcTrajectory_3.tab",
    "sha256": "0be07b5056c70937857c15e292402f341833a987379c919a0f9d9ec6f606e01a"
  },
  {
    "file": "ProcTrajectory_2.tab",
    "sha256": "d67bdea068a6ccf7ea2906e66e43bee20b273255f8185c393e928a94886b30bc"
  },
  {
    "file": "ProcTrajectory_1.tab",
    "sha256": "1c0aa62fce2448e45c65067f0149f2d84d858fba74cf92b0f121657fcd1f3d30"
  }
]
EXPECTED_OUTPUT_SHA256 = "8689a914574544dfd3b4f58a90c83c636dd4f03814fbab7aae06c6dd006d7498"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
