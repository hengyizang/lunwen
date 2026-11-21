#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32095810-quantitative-prediction (10.6084/m9.figshare.32095810.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Quantitative prediction errors of the RBFNN model across different welding parameters.csv",
    "sha256": "130c154ee177ca1f25b0e9b23e1f39b8302d3bc6516e8ecb7a68af0704369c21"
  }
]
EXPECTED_OUTPUT_SHA256 = "cfcbb8ddc860ff8db5e51ae8261bbdf5e2ebbd43747dde90ac10cc1237b4db51"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
