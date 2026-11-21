#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-itfa7o-replication-data-for-ind (10.7910/dvn/itfa7o)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "FigS3data.tab",
    "sha256": "6160be0c6072f27eb26a72c0fde1dc6c6b4fca0691a2c44fe152c5f733c175fd"
  },
  {
    "file": "F&O_twodigits_Wide.tab",
    "sha256": "7d8f4f2373eb5e651b93a5d50be39c93d924fe9f991b5489b98ab12a838b6fad"
  },
  {
    "file": "FigS4data.tab",
    "sha256": "3e0342357aa5c9e8d6289ad7db2966995731457ca03b42eb548a10055d4af1b4"
  }
]
EXPECTED_OUTPUT_SHA256 = "2f8f086847dd2644545a1e192ce8de8ac3159dd9490b7d7c3ed556fb01eac288"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
