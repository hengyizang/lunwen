#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-qblawv-the-scent-of-the-swarm-f (10.7910/dvn/qblawv)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "antswarm_tracking.tab",
    "sha256": "c03b06209bced89256541d58f0f58fb6c909ed88c887eda5b71e8330133e73f0"
  },
  {
    "file": "detections_olfaction.tab",
    "sha256": "717aa8266505ad5c53b5d88bae0fd6c326b20cc0befc24e512f4f8149e1f4147"
  }
]
EXPECTED_OUTPUT_SHA256 = "36a02e291586e8754b3ac9bbf9799c5b346e34c0e5af469c3df71b0b552fb1f6"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
