#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-gddmsa-enlarging-error-detectio (10.7910/dvn/gddmsa)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "exp3_result.txt",
    "sha256": "5bcde499216d76770d773c216b0dab3b0b94369f10f4b4f6957dafda5b136b04"
  },
  {
    "file": "exp1_result.txt",
    "sha256": "e3e80018314a64982254cb7aa75d7c3b77a613f5cbef649fb0b504b962a55c22"
  },
  {
    "file": "exp4_result.txt",
    "sha256": "90de176cbd67ec8882fecde35547039d9dd2293fa63e01222836868c33b38f07"
  },
  {
    "file": "exp2_follow_haptic.txt",
    "sha256": "2baf7ee1804ae9e351385fa7c4b22f78b854324ac5c5b2a34c709cff9de9d9f8"
  }
]
EXPECTED_OUTPUT_SHA256 = "bce523e0d9fbd177cbb89fd852865c308530bdcb99a00164046da8d1c8f1764e"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
