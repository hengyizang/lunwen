#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-mygsyo-replication-data-for-foo (10.7910/dvn/mygsyo)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "CLoon4_02-body_xyzres.csv",
    "sha256": "b5455e1580d18effb736586dff4849ba908e7ffccc73676b8693d8bbf8f9edaf"
  },
  {
    "file": "CLoon4_04-eye_xyzres.csv",
    "sha256": "bf6324d3e2c2fd23d9c344401338ac61d339e2e118758f5d37016dfdc471995a"
  },
  {
    "file": "CLoon4_04-body_xyzres.csv",
    "sha256": "46aa9d08f4ceb89d2215230a1f6276b60513b770ac6b918887bc0668739dac99"
  },
  {
    "file": "CLoon2_05-Rfoot_xyzpts.csv",
    "sha256": "d2b318d8300e7160c92a36bfd6959fd4fb4742f403312244d2165751030a7d53"
  }
]
EXPECTED_OUTPUT_SHA256 = "ee96a49a3b10dd8f4a601770a262e5efa31498cbbf8945238e8e08d762e9981a"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
