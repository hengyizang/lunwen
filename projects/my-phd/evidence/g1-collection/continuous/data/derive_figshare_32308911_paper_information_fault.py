#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-32308911-paper-information-fault (10.6084/m9.figshare.32308911.v2)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "thesaurus_instituciones.txt",
    "sha256": "08e6e869500f987f69c16b76705d5d40edbca5b0de11d859444832f081e25ef2"
  },
  {
    "file": "thesaurus_autores.txt",
    "sha256": "44dfc77e274f1dbf21ee939e0d1e01097942c5a67383b1dcf9ed278cce41a97b"
  },
  {
    "file": "thesaurus_keywords.txt",
    "sha256": "1214e6eda8f98a56f43db98c9c1d55265700e0ff3873f2a3bce1a24bd46f3a26"
  }
]
EXPECTED_OUTPUT_SHA256 = "63c145614afb8a3f4ceee2aca279ef9a8207d361868081a2f6a87ad441665d9d"
MODE = "cleaned_rows"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
