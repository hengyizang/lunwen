#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-jzgtxj-peafowl-locomotion (10.7910/dvn/jzgtxj)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "PeafowlLocomotion_Data.tab",
    "sha256": "a7c4d8841feac9e39ba94c5d400907b06e359132474a6a14803efb50b0717f40"
  }
]
EXPECTED_OUTPUT_SHA256 = "35b8e1e109576998c50714ea0e06aaa63a3de3a18c0d5b377fc65751a2e0de15"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
