#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-prdwpp-consumer-perception-of-u (10.7910/dvn/prdwpp)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Future of Health Delivery Drone Survey Community   Survey_RawData.csv",
    "sha256": "d0bf909055054e213b261600064ab6904c898bcc4adf4f5185e45241ad376e7c"
  },
  {
    "file": "Future of Health Delivery Drone Survey RSMH Team   Members_RawData.csv",
    "sha256": "2952aec100e5a899dd62ca2ff6eae011d47b002a80ed299c18bfa356f1140ac3"
  },
  {
    "file": "READ_ME.txt",
    "sha256": "bf1db8a399346ed1fe7ea4f72acb05421377a2f5ffbc1414b3ffe21662a1b4b2"
  }
]
EXPECTED_OUTPUT_SHA256 = "2c9a5db1b10b9404661ef5b4b3b1327d25bedf96d9d59f9ed61ae24c82e3fa18"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
