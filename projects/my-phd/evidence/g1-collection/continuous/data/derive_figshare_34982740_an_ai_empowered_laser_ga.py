#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34982740-an-ai-empowered-laser-ga (10.6084/m9.figshare.34982740.v2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "requirements.txt",
    "sha256": "52c1d4956973c2acdfb22aa04c5447d9ef8415330d467eb44ac5afe6ce6631bd"
  },
  {
    "file": "config.json",
    "sha256": "debd6743f618ed68fbb602d7c5892cfbf7a7ae4eab5016c9a1e275792620af68"
  }
]
EXPECTED_OUTPUT_SHA256 = "6766671484e6346ec374e30229113e52bad387a89fb7e3f40ab8e1e713566bf8"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
