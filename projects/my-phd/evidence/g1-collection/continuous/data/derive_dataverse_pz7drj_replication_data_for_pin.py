#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-pz7drj-replication-data-for-pin (10.7910/dvn/pz7drj)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "rnn_training_crack_length_7yr.csv",
    "sha256": "a61df619c7467318c6f45e8b8baf5a9d55d028317a4a251fc8671e222b7cfa0b"
  },
  {
    "file": "rnn_training_initial_crack_length.csv",
    "sha256": "31e1ea6a6025ef4bbab9fe0053e6d09c087643933a7a9810a8698adc28e4c242"
  },
  {
    "file": "rnn_predict_7yr_crack_length.csv",
    "sha256": "729d463aa69cef3c1b340f9035ddd53fbafa02118b7498056d4905f401d3da4e"
  },
  {
    "file": "rnn_predict_cracks_pure_fatigue.csv",
    "sha256": "37795f128392d31c103139535d9778fa543f172c4a37e03002fe5ee8a6e23d18"
  }
]
EXPECTED_OUTPUT_SHA256 = "28d34654beabd7de95503c9b78156a6b98091f5dbef58e4d6f30e99010b3d9eb"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
