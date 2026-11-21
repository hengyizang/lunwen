#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-31158421-data-set-for-fabrication (10.6084/m9.figshare.31158421.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "XRD A2.txt",
    "sha256": "ce1d3a0f8aacc2d2bfe68cd0c39b2a79683ebb688ce7522a955b74ac31ba5a96"
  },
  {
    "file": "XRD A3.txt",
    "sha256": "a222abe6bc59788b2314634cf2e2660fed9acd5963da52e25b769e62e37c3aa2"
  },
  {
    "file": "XRD A4.txt",
    "sha256": "6a89b83db1ad92bdb3ecc4b984c091a70b48c46a4699bbf9db078489babd68fd"
  }
]
EXPECTED_OUTPUT_SHA256 = "25b717574f3bcc0443ec8a0be6e45323f0a46d7e7d5b1ca0185d870cc183d280"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
