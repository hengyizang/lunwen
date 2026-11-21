#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-26318407-non-muscle-powered-actua (10.6084/m9.figshare.26318407.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "80%_8sv1.csv",
    "sha256": "e0f9dedbdb67882317c42d84d67da3dbde749552b285a853dfe9423ba075e601"
  },
  {
    "file": "Results from Overlay Dots 80%_8s_withoutcell in \u00b5m per sec.csv",
    "sha256": "eca9fc5ec4ef3068e2e47602e192bf2c58a1afe0e030f041388ae9c3399a8f25"
  },
  {
    "file": "weiyitu.txt",
    "sha256": "1861cde4c9d2fd1bfe6fd531fdd781ed951c6c7b17844b37892b545c267827d8"
  },
  {
    "file": "lobelimi.txt",
    "sha256": "d4cd73e2fb489a4b53dd34a9d3d8d3384cb2f3b1c2b5a537a94eb33a4e09dff9"
  }
]
EXPECTED_OUTPUT_SHA256 = "3ee073126d6125e19a7d6a6cebc20995d41d3adb3f3db076b0348d7f3d2646e6"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
