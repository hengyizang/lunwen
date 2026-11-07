#!/usr/bin/env python3
"""Run measured fast/slow unittest partitions; all retains the complete suite."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPATIBILITY = {"test_api_first.py", "test_cloud_job.py", "test_test_suites.py",
                 "test_paper_execution.py", "test_network_safety.py", "test_output_provenance.py"}
if __package__ in {None, ""}:
    sys.path[0] = str(ROOT)


def test_files(suite: str, root: Path = ROOT) -> list[Path]:
    """New tests enter fast automatically; missing slow entries fail visibly."""
    if suite not in {"fast", "slow", "all", "compat"}:
        raise ValueError("test suite must be fast, slow, compat or all")
    files = {path.name: path for path in (root / "tests").glob("test*.py")}
    slow = json.loads((root / "config/test-suites.json").read_text(encoding="utf-8"))
    if (not isinstance(slow, dict) or not slow
            or any(not isinstance(reason, str) or not reason.strip() for reason in slow.values())):
        raise ValueError("slow tests need explicit nonempty classification reasons")
    if not files or set(slow) - files.keys():
        raise ValueError("test partition references missing tests: " + ", ".join(sorted(set(slow) - files.keys())))
    if suite == "compat":
        if COMPATIBILITY - files.keys():
            raise ValueError("compatibility partition references missing tests")
        return [files[name] for name in sorted(COMPATIBILITY)]
    return [files[name] for name in sorted(files)
            if suite == "all" or (name in slow) == (suite == "slow")]


def load_suite(paths: list[Path]) -> unittest.TestSuite:
    # Discovery converts module-level SkipTest to a skipped test and import
    # failures to failing tests. Loading named modules does not preserve that.
    loader = unittest.TestLoader()
    return unittest.TestSuite(loader.discover(str(path.parent), pattern=path.name) for path in paths)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=("fast", "slow", "all", "compat"), nargs="?", default="fast")
    parser.add_argument("--list", action="store_true", help="list selected test files without importing them")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--failfast", action="store_true")
    args = parser.parse_args(argv)
    try:
        paths = test_files(args.suite)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.list:
        print("\n".join(path.name for path in paths))
        return 0
    result = unittest.TextTestRunner(verbosity=1 if args.quiet else 2, failfast=args.failfast).run(load_suite(paths))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
