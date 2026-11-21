#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-idxscu-replication-data-for-old (10.7910/dvn/idxscu)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Statistical_results.tab",
    "sha256": "c473e00f767255c076c5fb61fd5db7bf25c516f837d208309508abbd16bdc0c1"
  },
  {
    "file": "Questionnaire_responses.tab",
    "sha256": "fcf80bfe0498fe21799a09d28ada2b837127d7b5db02450bef27b136f53ca5c5"
  }
]
EXPECTED_OUTPUT_SHA256 = "1b86e225cf4649e3c1f428bfa75d4678bafa4aaa09598d77d9486bb05e406a48"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
