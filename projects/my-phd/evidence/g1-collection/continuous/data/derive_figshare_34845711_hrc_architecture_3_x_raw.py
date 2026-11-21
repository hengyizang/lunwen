#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34845711-hrc-architecture-3-x-raw (10.6084/m9.figshare.34845711.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "INVENTORY.csv",
    "sha256": "e20d46fa75ac98eb135276cf5b26aa428307fcea4ec5453b4963652a24fca999"
  },
  {
    "file": "INDEX.csv",
    "sha256": "6f70f6421b73ba49f61d5db6bc2c6d0cff26eb38de80098f91fbbff7ddb38d31"
  },
  {
    "file": "git_tags.txt",
    "sha256": "fa0d18ef0b2831c8b57f4d767127386d00b4e628b0806596fc401953141775a5"
  },
  {
    "file": "git_log.txt",
    "sha256": "d1441059f925425d8c4a8f6f0b376ad139264038ccdb72954e74b6e08f40d958"
  }
]
EXPECTED_OUTPUT_SHA256 = "7c1e17a1903d82a2d6af1665b3802f9fd74f8a1a7e8e376ac76dd44ce3ef28f2"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
