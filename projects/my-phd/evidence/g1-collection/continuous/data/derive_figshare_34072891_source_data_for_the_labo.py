#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34072891-source-data-for-the-labo (10.1371/journal.pone.0359936.s001)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "pone.0359936.s001.zip",
    "sha256": "6448aa3c3b472b992818a0df373957e277183d7d82d03df2251e253195ab5d98"
  }
]
EXPECTED_OUTPUT_SHA256 = "c2440887fd691d867df4a2ee65dee5eb01399a9e2ab887b0387e87f2a96ded5b"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
