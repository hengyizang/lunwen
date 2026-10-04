"""Cloud-only synthetic fault injection; never a scientific-completion receipt."""
from __future__ import annotations
import argparse
import json
import unittest
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromNames(["tests.test_cloud_retry", "tests.test_cloud_recovery"])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {"schema_version": "1.0", "status": "pass" if result.wasSuccessful() else "fail",
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "model_calls": 0, "external_paid_compute_usd": 0, "production_state_mutated": False,
        "scope": "synthetic engineering fault injection and recovery controls",
        "scientific_completion_verified": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
