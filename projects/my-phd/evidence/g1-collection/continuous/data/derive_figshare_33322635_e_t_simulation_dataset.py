#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-33322635-e-t-simulation-dataset (10.6084/m9.figshare.33322635.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "ET_FS85_analytical.csv",
    "sha256": "a503fccc71a600f74d31bd076d5dc64e68498b32f28002905192c46b5e534de4"
  }
]
EXPECTED_OUTPUT_SHA256 = "e029190e7ce7f722920e62cd092387737c2d1bd16bba6662e0ce73f8613b76a2"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
