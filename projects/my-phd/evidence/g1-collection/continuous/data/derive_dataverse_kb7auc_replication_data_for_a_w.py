#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-kb7auc-replication-data-for-a-w (10.7910/dvn/kb7auc)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Pushup.tab",
    "sha256": "f6438da5d84b5fc58dbdf4a202d36626886b6de7c7d202f9b721342fa3e212e1"
  },
  {
    "file": "Run.tab",
    "sha256": "5e11954e4f7e8c8983d36d4a1cd3287593d0e52e83c17746911135c54fe25c5f"
  },
  {
    "file": "Squat.tab",
    "sha256": "c089e5b5e78eed82108d99aa74f863e7a57e1366042af3f96311001312c2eef8"
  },
  {
    "file": "Walk.tab",
    "sha256": "90be2ad812e81fb6bf230090bf9b51edf666ed378f285e2b464974e5e1f513e7"
  }
]
EXPECTED_OUTPUT_SHA256 = "214ac834a9c8e29f8cb37a83f21072202af2f38763a131d0b4c3b31802a9edf5"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
