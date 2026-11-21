#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-ifhd40-replication-data-for-qua (10.7910/dvn/ifhd40)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "figures_index.csv",
    "sha256": "127ac1e0266569ab88979300d871565b94169c570875199b4f0ef601a5fe46a4"
  },
  {
    "file": "key_values.csv",
    "sha256": "e5a63e5d10a74b61112f8879a27483d291ebcf6053689dec37b309f61a18810f"
  },
  {
    "file": "verification.csv",
    "sha256": "58da61c821fbe6d705e462758d9b0687cacfd59b757e395ceb3fd08e8c6901bf"
  },
  {
    "file": "anchors.json",
    "sha256": "34f29a7063583424ba7e34a556ab2d948e23d6ae8f411ca3870ff26879aeebca"
  }
]
EXPECTED_OUTPUT_SHA256 = "3b81261b6d00794d077c78d60cbc1491fc67ed67e5b3f93d67bc2fbe23c8b9f9"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
