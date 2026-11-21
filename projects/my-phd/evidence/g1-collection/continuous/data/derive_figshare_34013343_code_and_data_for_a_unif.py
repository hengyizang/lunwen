#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34013343-code-and-data-for-a-unif (10.6084/m9.figshare.34013343.v2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "rh_multirobot_code_data.zip",
    "sha256": "b2dc655e5a348c01ef709f052bfff0cb7b5fd88119d19b2e76ea1c30c1a1a1cb"
  }
]
EXPECTED_OUTPUT_SHA256 = "f27ddee717b09c496d9ec97f171c8d7636c20792ac573108f46a126304f48311"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
