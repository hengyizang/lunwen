from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.venue_adapter import TemplateError, ingest_archive, inspect_archive


class VenueAdapterTests(unittest.TestCase):
    def test_safe_template_is_inspected_and_ingested(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "ijssd-2e.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("ijssd/ws-ijssd.cls", "class fixture")
                handle.writestr("ijssd/ws-ijssd.tex", "sample fixture")
                handle.writestr("ijssd/figure.eps", "eps fixture")

            report = inspect_archive(archive)
            self.assertEqual(report["member_count"], 3)
            self.assertEqual(report["detected"]["classes"], ["ijssd/ws-ijssd.cls"])

            destination = root / "venue-template"
            ingest_archive(archive, destination)
            self.assertTrue((destination / "ijssd" / "ws-ijssd.cls").is_file())
            inventory = json.loads(
                (destination / "template-inventory.json").read_text()
            )
            self.assertEqual(len(inventory["archive_sha256"]), 64)
            self.assertIn(
                "ijssd/ws-ijssd.tex", inventory["extracted_file_sha256"]
            )

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("../escape.tex", "bad")
            with self.assertRaises(TemplateError):
                inspect_archive(archive)

    def test_unexpected_executable_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("run.exe", "bad")
            with self.assertRaises(TemplateError):
                inspect_archive(archive)


if __name__ == "__main__":
    unittest.main()
