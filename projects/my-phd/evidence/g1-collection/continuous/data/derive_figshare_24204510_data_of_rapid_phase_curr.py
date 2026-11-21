#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-24204510-data-of-rapid-phase-curr (10.6084/m9.figshare.24204510.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "cobot_data.zip",
    "sha256": "d9ca7c67f8633acd4a85b9d4d0ef509c841582f5fdf66da95ec30ad052d42c7a"
  }
]
EXPECTED_OUTPUT_SHA256 = "7e609482d2451a12e787312b3d640a0c1e85f55b52ae55d321a06562ac223ed2"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
