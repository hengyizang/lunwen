from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.sciencepro_import import import_export


class ScienceProImportTests(unittest.TestCase):
    def test_import_is_private_hash_bound_and_advisory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "demo"
            project.mkdir()
            source = root / "sciencepro-export.bib"
            source.write_text(
                "@article{x, doi={10.1234/EXAMPLE}, url={https://doi.org/10.1234/example}}",
                encoding="utf-8",
            )
            output, report = import_export(project, source, "Researcher")
            self.assertTrue(output.is_file())
            self.assertTrue((project / report["source"]["private_path"]).is_file())
            self.assertEqual(report["evidence_status"], "advisory_requires_independent_verification")
            self.assertEqual(report["extraction"]["doi_candidates"], ["10.1234/example"])


if __name__ == "__main__":
    unittest.main()
