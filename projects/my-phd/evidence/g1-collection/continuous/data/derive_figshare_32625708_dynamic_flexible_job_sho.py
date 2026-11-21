#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32625708-dynamic-flexible-job-sho (10.6084/m9.figshare.32625708.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Instances.zip",
    "sha256": "c69c4879f96b7376041776797a1b2d9478ab499ce8bccc870479ce9ab66c94e3"
  }
]
EXPECTED_OUTPUT_SHA256 = "8dbda376cee0c3a3d8f9b024df20bd43a96f48b8822ea7c4da316eda23dac3f8"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
