"""One receipt for existing software suites; real integration runners stay separate."""
from __future__ import annotations
import argparse
import json
import os
import unittest
from pathlib import Path
from scripts.research_artifacts import write

SUITES = {
    "recovery": (["tests.test_cloud_retry", "tests.test_cloud_recovery"],
                 "synthetic engineering fault injection and recovery controls"),
    "cost-quality": (["tests.test_cost_optimization.LosslessContextTests", "tests.test_cost_optimization.CostRuntimeTests"],
                     "synthetic lossless source context, exact-request reuse and fresh independent assessment controls"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=SUITES, default="recovery")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise RuntimeError("software acceptance requires the configured cloud executor")
    names, scope = SUITES[args.suite]
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.wasSuccessful() and not result.skipped
    receipt = {"schema_version": "1.0", "status": "pass" if passed else "fail", "suite": args.suite,
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped),
        "model_calls": 0, "external_paid_compute_usd": 0, "production_state_mutated": False,
        "scope": scope,
        "scientific_completion_verified": False}
    if args.suite == "cost-quality":
        receipt.update(fixture_only=True, real_paid_model_calls=0, network_requests=0,
                       scientific_quality_or_actual_cost_savings_verified=False,
                       real_model_families_or_routing_not_evaluated=True)
    write(args.output, receipt)
    print(json.dumps(receipt))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
