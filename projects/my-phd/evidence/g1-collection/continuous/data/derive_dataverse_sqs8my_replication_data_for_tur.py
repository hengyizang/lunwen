#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-sqs8my-replication-data-for-tur (10.7910/dvn/sqs8my)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "TurningToCourts_RemedyExhaustion.tab",
    "sha256": "200f9737871026168a295205ad9a9e88de058763ff293b3c60d78fccb6af17ff"
  },
  {
    "file": "TurningToCourts.tab",
    "sha256": "1482314298f46ffe91a9703e40ad0d62de39f743319d6a907a6d67eef24be47a"
  }
]
EXPECTED_OUTPUT_SHA256 = "77796ff23dc5edf85f6a7223ab3ff0eaa340a3ac1baa88b2f7156d49938cf06b"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
