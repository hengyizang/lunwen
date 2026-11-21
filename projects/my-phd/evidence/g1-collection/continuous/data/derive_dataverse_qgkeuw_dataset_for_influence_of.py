#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-qgkeuw-dataset-for-influence-of (10.7910/dvn/qgkeuw)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "0_presentations_analysis.tab",
    "sha256": "5a748c1b718ead1777ea54852cf024f378f427169a7dc001f10e705ca905ae23"
  },
  {
    "file": "0_thresholdForce_analysis.tab",
    "sha256": "c8d8a8fa0815ea3ccba282b7d33cc4ff12a0f38cbada272cec78da60609baf20"
  },
  {
    "file": "Visual-alone.tab",
    "sha256": "dccbad8d68d1226182f6e90ae37df05cc447b426bb39b6fb90d9b73314089ab9"
  },
  {
    "file": "Haptics-alone.tab",
    "sha256": "8937cbf055b6a95cb53733120fe130bb94a7144959d0eb557bf737377b1067bf"
  }
]
EXPECTED_OUTPUT_SHA256 = "1098c0a0b66932030c7bf453c0e2ef5b8d1bd41b6a2e78407d55529591e555e0"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
