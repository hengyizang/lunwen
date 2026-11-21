#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-k7igab-replication-data-for-ear (10.7910/dvn/k7igab)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "S39_LB.txt",
    "sha256": "e3205034d9b376b20379309182e41ac94fefa5b2ce265895a3a4bd4f128ef93d"
  },
  {
    "file": "S2_control.txt",
    "sha256": "69dd588becb29f87029b147e67e490bd49c04e80d3d3e3fa96cc50b96ff90a9b"
  },
  {
    "file": "S21_EB.txt",
    "sha256": "c244d8822959d10a4fcc91ca60c94d9611cd4caec18c09331b18be3035b30ce6"
  },
  {
    "file": "S35_control.txt",
    "sha256": "a587c1166093bed66bb6627fb925ebe2a0c392e8a67d26b22e185f31d39b32b2"
  }
]
EXPECTED_OUTPUT_SHA256 = "eac789a30bcdd6cd2e71826498aafd15ce978a662402581ae38a7eb73ae802b3"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
