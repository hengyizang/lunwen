#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-ombstn-a-sound-dataset-of-vario (10.7910/dvn/ombstn)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "HF01_20230411_label.tab",
    "sha256": "f7a279a1337befb56bbe2a36cb7209ab8356d19895398bb6ad6ea8647a422072"
  },
  {
    "file": "PB01_20210426_label.tab",
    "sha256": "05c72bb73144ca32a92aa8c7c4720a86704ec9b684a146ba70095e519fe5494d"
  },
  {
    "file": "HF01_20221215_label.tab",
    "sha256": "e399a7dea6c5a41933661fcb81eada03087237ca6d98f697d8eb056b8805dbd0"
  },
  {
    "file": "HF01_20230314_label.tab",
    "sha256": "4a0ed8159b3b72e647080b928beb89176390a26e87c92a166e5a960fdbf58f66"
  }
]
EXPECTED_OUTPUT_SHA256 = "b53efd63af017a06d4553d4e221eab57bff728cf234790ef7d3bda73935e957f"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
