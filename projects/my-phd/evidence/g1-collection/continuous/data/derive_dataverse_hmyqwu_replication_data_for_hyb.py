#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-hmyqwu-replication-data-for-hyb (10.7910/dvn/hmyqwu)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "approximate_plane_set.tab",
    "sha256": "7cbd84bb3edf6fc543579fd2b21dd83e2322b266e3a4f308c3635388a2d36a85"
  }
]
EXPECTED_OUTPUT_SHA256 = "d4b8a44ded5ad4e8595da7b010212f7525910fd345c8d9a8fab0c68dc6a146d3"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
