#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-qhfhyc-a-multi-sensory-inertial (10.7910/dvn/qhfhyc)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "ultrasound_Readings.tab",
    "sha256": "42a77bddfa85a976e83617bdbb02f37a80e71d822e713f18b99e9050482acd4d"
  },
  {
    "file": "ward_Readings.tab",
    "sha256": "1e46b66615340de04693581a7d578840d301deb956573b847962d84716072b7d"
  },
  {
    "file": "W27_R2.tab",
    "sha256": "7aabfef0ffff7a47bcc48469ed9e977b886c948523f92412b7b8b9d7864844a5"
  },
  {
    "file": "W29_R2.tab",
    "sha256": "63f54a43e32ac8f79f10d79bf4c336c46cd1bbdc70f7268d0cfdfe0ed5451887"
  }
]
EXPECTED_OUTPUT_SHA256 = "0e90f4999e8a15067d6ddc9174cc3124eb00f223edc22bb5a205309bd41e3c53"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
