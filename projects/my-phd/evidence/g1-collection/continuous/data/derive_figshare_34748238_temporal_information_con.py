#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34748238-temporal-information-con (10.6084/m9.figshare.34748238.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Telemetry_Platform_Testbed.zip",
    "sha256": "5a3d5977d938423772335ee6b3f19f6e9e0ade2efe535b1c1d6df0fb0be9d04d"
  }
]
EXPECTED_OUTPUT_SHA256 = "042e2c8f2699a128dc82632c84575f808925a659d4de9d392520c08e28a694e0"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
