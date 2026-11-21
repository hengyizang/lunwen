#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-lpnslg-tensile-test-and-finite (10.7910/dvn/lpnslg)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Connector load-strain curves.txt",
    "sha256": "af22dc85042b2425e84d67ad00a235176e611729575d3089e956cd3956661520"
  },
  {
    "file": "Connector load-displacement curves.txt",
    "sha256": "daa0c74584cf78cf6d34eb7c50a48f42e274e0df1be54ba15058aa39f3564ce7"
  }
]
EXPECTED_OUTPUT_SHA256 = "0d8df315f2ccbed07e9358d28ec67aa79bfa8806b2fadb83e8c1029278d12e16"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
