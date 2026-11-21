#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-30944375-the-datasets-of-the-2017 (10.6084/m9.figshare.30944375.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Supplementary Data3-Focal mechanism Catalog.txt",
    "sha256": "136c8c0214d42fb08cb2f06fe74fd87347bc94d2a9c8c1119b5ef59833c48f37"
  },
  {
    "file": "Supplementary Data2-Relocation Catalog.txt",
    "sha256": "a72de136009f23a2f371a0bd8af80ba2427abe5878b50bc1b7eec1cdff297913"
  },
  {
    "file": "Supplementary Data1-Detected Catalog.txt",
    "sha256": "a39c76db9776a18bca21f251e95801359a6ae3a2cd8fac71f3af632954bd3e20"
  }
]
EXPECTED_OUTPUT_SHA256 = "20188c90f6bd516571f463e7ad27e263c8d8083c421d498103077ee4cf1adf09"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
