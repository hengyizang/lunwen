#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-dozy6n-eval-dataset (10.7910/dvn/dozy6n)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "slide_block_to_target_fed.json",
    "sha256": "a522bf125f660f48e4c5ad65414c8156ab2a5cdd34cbe2ae360e1efb9580d7e3"
  },
  {
    "file": "close_box_fed.json",
    "sha256": "dae9d1d35874751d66428426f009b371283badbde70ea45f52a4f87f74899308"
  },
  {
    "file": "insert_onto_square_peg_fed.json",
    "sha256": "bbac7adc0c178bdad3a80b0115fb74800bb56c83b445d483e276c033302487ff"
  },
  {
    "file": "scoop_with_spatula_fed.json",
    "sha256": "dee9d175d00ec6bf43c9c87867f1df44f6bcecac26449740bc5eb2a44f88f0bd"
  }
]
EXPECTED_OUTPUT_SHA256 = "b387968cc772c7ebb6cda49daa370df452e7ca66e5388fa283044249aa8c0964"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
