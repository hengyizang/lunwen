#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34163973-combined-effects-of-fibe (10.6084/m9.figshare.34163973.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "!10-50CF-CF30.txt",
    "sha256": "bafee8d3ce900025fbe5722c0e8d10eaeda0351d0e7358608889aa3364fc451f"
  },
  {
    "file": "!09-40CF-CF30.txt",
    "sha256": "bafb0b0b494099dd77e0c3ef1cc982e6ef72cef965050f4079cdfe11416b89a3"
  },
  {
    "file": "!11-30CF-CF200-H.txt",
    "sha256": "891d19b899673c1b420f7cc7cd4dc00684ff5641d4d05283851ab90c9e8cae8e"
  },
  {
    "file": "!12-40CF-CF200-H.txt",
    "sha256": "d3e02f62a2054cd5d6484ef7948c2e1b815e535cea1e40478170939440a30f99"
  }
]
EXPECTED_OUTPUT_SHA256 = "80793ae843dbcc703dd0d72544691d4e08ba27aab3f1dc571a51becaed258956"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
