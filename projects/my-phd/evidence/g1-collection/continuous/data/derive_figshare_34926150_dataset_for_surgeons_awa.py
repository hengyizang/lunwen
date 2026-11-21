#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34926150-dataset-for-surgeons-awa (10.6084/m9.figshare.34926150.v2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "RAS_Surgeons_Survey_Anonymised_Dataset.csv",
    "sha256": "3677633f0aa24674d60db447d1d1373c9a83c04147c75dd589cb6a22c32513ea"
  }
]
EXPECTED_OUTPUT_SHA256 = "e76b5bd00a84186fae2725839fec63b2b96d4c658f98d4f47bc9b4f0c2df3d54"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
