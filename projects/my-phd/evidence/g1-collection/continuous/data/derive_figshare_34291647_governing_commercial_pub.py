#!/usr/bin/env python3
"""Reproducible deterministic cleaner wrapper for figshare-34291647-governing-commercial-pub (10.6084/m9.figshare.34291647.v1)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_common import run_cli

EXPECTED_FILES = [
  {
    "file": "functional_class_matrix.csv",
    "sha256": "7242f591b30379036e51d968c93a5aa6c1b0d770d227d08bc0d0e3c096c54b61"
  },
  {
    "file": "proposal_register.csv",
    "sha256": "d30e0cc13a9447a3a0ada08b7754caf4744f25d3ced30bfd1536bfc31a7afd72"
  },
  {
    "file": "india_institutional_interface_map.csv",
    "sha256": "4e76412d25481bb7e8b0a358f8a3bde29915b66ae25e3fb918e9307a814d49be"
  },
  {
    "file": "comparative_regulatory_matrix.csv",
    "sha256": "70ac03566c9e249a23fad93d9bb5521799c038dc6c7c99fe3e3c60b87d4e3b92"
  }
]
EXPECTED_OUTPUT_SHA256 = "f624fce0dccc377c1b709918884415b4a7b8c94536a26a094109fae5e4a7d07d"
MODE = "summary_table"

if __name__ == "__main__":
    raise SystemExit(run_cli(EXPECTED_FILES, EXPECTED_OUTPUT_SHA256, MODE, Path(__file__).name, 25000000))
