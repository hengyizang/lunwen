#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34808832-data-for-piam-a-physics (10.6084/m9.figshare.34808832.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "PiAMDATA.zip",
    "sha256": "a01434913d7af8dac57c26cdf9364ae4674b2141bf995e2e6cef6d834d4fabd4"
  }
]
EXPECTED_OUTPUT_SHA256 = "b5b1dd0265c2494bcee511202adc79533348a52feb4a4258529503ce08052e85"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
