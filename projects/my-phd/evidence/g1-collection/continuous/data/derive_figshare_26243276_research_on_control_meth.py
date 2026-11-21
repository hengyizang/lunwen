#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-26243276-research-on-control-meth (10.6084/m9.figshare.26243276.v3)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "ur_eMc.txt",
    "sha256": "29b1479a510cd9d99a1b5004a75e03d4d70228f1d1970b45c6276878ed98dd39"
  }
]
EXPECTED_OUTPUT_SHA256 = "a600133acb887b9df0192a571602382317aba95dda5f84a0977a9f877b1b2ebd"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
