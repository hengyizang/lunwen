#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-35055502-processed-data-supportin (10.6084/m9.figshare.35055502.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data.zip",
    "sha256": "d46a127a1fb707fcf554c1e98743826a4fc3e49a0a98f0d447cccd113802675e"
  }
]
EXPECTED_OUTPUT_SHA256 = "9f0d1b98f374ccd6988ae6ee29cb789aab7ce4ea450fabd43399f8e24d005806"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
