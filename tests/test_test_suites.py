"""The quick check must not silently omit tests or hide import failures."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.run_tests import ROOT, load_suite, test_files


class TestSuiteTests(unittest.TestCase):
    def test_direct_entry_uses_the_same_package_instances_as_module_execution(self):
        probe = (
            "import runpy,sys; from pathlib import Path; "
            "sys.path[0]=str(Path('scripts').resolve()); "
            "runpy.run_path('scripts/run_tests.py',run_name='bootstrap_probe'); "
            "from scripts import submission_package,researchctl; "
            "assert submission_package.load_state is researchctl.load_state"
        )
        result = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_partitions_cover_all_tests_without_overlap(self):
        fast, slow, all_tests = (set(test_files(name)) for name in ("fast", "slow", "all"))
        self.assertFalse(fast & slow)
        self.assertEqual(fast | slow, all_tests)
        self.assertEqual(all_tests, set((ROOT / "tests").glob("test*.py")))

    def test_new_tests_default_to_fast_and_stale_classifications_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            (root / "config").mkdir()
            for name in ("test_slow.py", "test_new.py"):
                (root / "tests" / name).touch()
            config = root / "config/test-suites.json"
            config.write_text(json.dumps({"test_slow.py": "measured expensive fixture"}))
            self.assertEqual([p.name for p in test_files("fast", root)], ["test_new.py"])
            (root / "tests/test_slow.py").unlink()
            with self.assertRaisesRegex(ValueError, "missing tests"):
                test_files("fast", root)

    def test_discovery_preserves_module_skips_and_import_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skipped, broken = root / "test_suite_optional_fixture.py", root / "test_suite_broken_fixture.py"
            skipped.write_text("import unittest\nraise unittest.SkipTest('optional fixture unavailable')\n")
            broken.write_text("raise RuntimeError('fixture import failed')\n")
            result = unittest.TextTestRunner(stream=io.StringIO()).run(load_suite([skipped, broken]))
            self.assertEqual(result.testsRun, 2)
            self.assertEqual(len(result.skipped), 1)
            self.assertEqual(len(result.errors), 1)
            self.assertIn("fixture import failed", result.errors[0][1])
