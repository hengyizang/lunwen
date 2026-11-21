#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-ekpfj2-replication-data-for-art (10.7910/dvn/ekpfj2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "FoamBlockData.tab",
    "sha256": "24d19e8030829576d7fda8a4e0fa38474b677c11308ff41f233c2e2abc199d6a"
  }
]
EXPECTED_OUTPUT_SHA256 = "45dfab3a6b421c213c15f33286c71bb794c107b3165ea0c1da545b36de725ccb"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
