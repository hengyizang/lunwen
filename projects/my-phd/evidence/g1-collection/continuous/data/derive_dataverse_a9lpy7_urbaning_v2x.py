#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for dataverse-a9lpy7-urbaning-v2x (10.7910/dvn/a9lpy7)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "av_vehicle_data.json",
    "sha256": "a659594d5e30d32174c66a20a867cf510ca7d918a10344c9e23b0c691184be93"
  },
  {
    "file": "labels_av_track_ids.json",
    "sha256": "98c4b2111849e2b16e227662d521e7a8895fabfd13f2306420932cf241a9e474"
  },
  {
    "file": "20241126_0008_crossing1_01.json",
    "sha256": "f4f8733aa2117c8d4784c6aaac8b17d5e7c231d41b5038239136d179f77abddc"
  },
  {
    "file": "20241127_0024_crossing3_08.json",
    "sha256": "b6b6a58536663e4640f422ef97cbf7b227714e3032677d66f8ebf8f7b7ea4f2f"
  }
]
EXPECTED_OUTPUT_SHA256 = "d41ba4e912caec98e37d5d1c5e53bd8cdb26005f61288486bc7e4ee2abd39fed"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
