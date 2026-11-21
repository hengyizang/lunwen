#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-4qhuwx-replication-data-for-hea (10.7910/dvn/4qhuwx)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "figures_index.csv",
    "sha256": "060dbe697f9ed3f602dbcc71e65111bc5e99e016647a95418aec4e6aab9b7a23"
  },
  {
    "file": "key_values.csv",
    "sha256": "e0fd8e60ad109654ef8b738674c1cfc4182ae02e4bc98cd5f0ef1360252b2376"
  },
  {
    "file": "verification.csv",
    "sha256": "9246196011249a8b90e00058c2b4c12e9f84ebae83219cacc70fb609630b790b"
  },
  {
    "file": "anchors.json",
    "sha256": "13aa7c1a61b5227922a4d78916f2fb5aec0da7714ae5f93194cc8f131105313d"
  }
]
EXPECTED_OUTPUT_SHA256 = "4c5871ba2f6e54a07552ffe1cbbc076bf8e48b72e00cfbcb4f5220d2bcbf5f51"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
