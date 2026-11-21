#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34910805-data-sheet-1-reliability (10.3389/fnbot.2026.1973789.s001)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Data Sheet 1_Reliability-aware multimodal sensor fusion for human motion monitoring with safety-constrained neurorobotic feedback in spo.zip",
    "sha256": "1ce3ce9678f1ceca8324dfae17d84e49757f3983d8ced79c930f7b22747a4704"
  }
]
EXPECTED_OUTPUT_SHA256 = "5e426aa5d56efe957d50d1f1e26a2a8ffa7424eef71e9801467930c98dd349af"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
