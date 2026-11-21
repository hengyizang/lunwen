#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-getyap-drone-medical-package-de (10.7910/dvn/getyap)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "Future of Health Delivery Drone Survey Community   Survey_RawData.csv",
    "sha256": "ebb7e13fb595327c162a1176a85b0f828296e7fcd3189070cb6466827ae09616"
  },
  {
    "file": "Future of Health Delivery Drone Survey RSMH Team   Members_RawData.csv",
    "sha256": "ced2dfbdf08af223b5fd6c68ed6e660e66be13503c8f1e3e8ae0c0183f9ea958"
  },
  {
    "file": "Household_Size_Estimate.csv",
    "sha256": "4eebd06057888455f157d37474fcc83c7f02f7572fe586b97b5e93200cec3673"
  },
  {
    "file": "Residential_Analysis.csv",
    "sha256": "706c6a499679e2dea2dc0735411304dc3dbf945531baa19bfbc9842493755ce8"
  }
]
EXPECTED_OUTPUT_SHA256 = "8ed451b159821334f84288ac3eef74c1a50c418ebc36f389490b327d9b80c8b4"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
