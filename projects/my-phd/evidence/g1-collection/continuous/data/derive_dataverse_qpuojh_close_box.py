#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-qpuojh-close-box (10.7910/dvn/qpuojh)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "close_box_fed.json",
    "sha256": "552f163cf7c176a56c60f24dfc58f169d1a5b2c69a9b861d58dbfd1e3ac7b836"
  }
]
EXPECTED_OUTPUT_SHA256 = "793ff2b757162aa829bc4736444c53e535c964aad87f575f6852f69b5d6c9608"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
