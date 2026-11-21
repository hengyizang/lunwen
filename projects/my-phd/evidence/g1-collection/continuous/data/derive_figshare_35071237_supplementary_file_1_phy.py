#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-35071237-supplementary-file-1-phy (10.3389/fphys.2026.1947699.s001)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Supplementary file 1_Physiological digital twins require cross-system observation contracts.zip",
    "sha256": "7560dcee2b2169bcc05c28a251c1e6cb8a5e7c54fb3c28a3ee8e5b1d559629b3"
  }
]
EXPECTED_OUTPUT_SHA256 = "66284cc82ae8eb36ed2f3d7ade8627a50dc4a1067e92e56d2a225fbc6b7fd75d"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
