#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-brzhhg-comparison-of-urethral-s (10.7910/dvn/brzhhg)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "dataKMADP_19006.txt",
    "sha256": "70ce2b39da4986023e8602d46f935131d69bc0aec2fc1025715a85b251ae2533"
  }
]
EXPECTED_OUTPUT_SHA256 = "cd02df877925ba2f2664e5a2b3609b317b8f84e31cac0dfc2a855c77239a6daa"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
