from __future__ import annotations

import json
import io
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.venue_compliance import ComplianceError, ingest_archive, inspect_archive
from scripts import venue_compliance as venue


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
            with self.assertRaises(ComplianceError):
                inspect_archive(archive)

    def test_unexpected_executable_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("run.exe", "bad")
            with self.assertRaises(ComplianceError):
                inspect_archive(archive)

    def test_zip_security_limits_symlink_encryption_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "bad.zip"
            for name in ("/escape.tex", "C:/escape.tex", "..\\escape.tex"):
                with zipfile.ZipFile(archive, "w") as handle:handle.writestr(name, "bad")
                with self.assertRaisesRegex(ComplianceError, "Unsafe archive path"):
                    inspect_archive(archive)
            member = zipfile.ZipInfo("linked.tex");member.create_system = 3
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as handle:handle.writestr(member, "target.tex")
            with self.assertRaisesRegex(ComplianceError, "Symlink"):
                inspect_archive(archive)
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("sample.tex", "fixture");handle.writestr("style.cls", "fixture")
            with patch.object(venue, "MAX_MEMBERS", 1), self.assertRaisesRegex(ComplianceError, "too many"):
                inspect_archive(archive)
            with patch.object(venue, "MAX_UNCOMPRESSED_BYTES", 1), self.assertRaisesRegex(ComplianceError, "too large"):
                inspect_archive(archive)
            payload = bytearray(archive.read_bytes());payload[6] |= 1
            payload[payload.index(b"PK\x01\x02") + 8] |= 1;archive.write_bytes(payload)
            with self.assertRaisesRegex(ComplianceError, "Encrypted"):
                inspect_archive(archive)

    def test_existing_destination_is_preserved_and_failed_ingest_cleans_temporary_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);archive = root / "template.zip";destination = root / "template"
            with zipfile.ZipFile(archive, "w") as handle:handle.writestr("sample.tex", "fixture")
            destination.mkdir();sentinel = destination / "sample.tex";sentinel.write_text("original")
            with self.assertRaisesRegex(ComplianceError, "already exists"):
                ingest_archive(archive, destination)
            self.assertEqual(sentinel.read_text(), "original")
            target = root / "failed"
            with patch.object(zipfile.ZipFile, "open", side_effect=OSError("fixture failure")):
                with self.assertRaisesRegex(OSError, "fixture failure"):
                    ingest_archive(archive, target)
            self.assertFalse(target.exists());self.assertEqual(list(root.glob(".failed-*")), [])

    def test_inspect_ingest_cli_dispatch_and_bad_zip_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);archive = root / "template.zip"
            with zipfile.ZipFile(archive, "w") as handle:handle.writestr("sample.tex", "fixture")
            for command in (["inspect", str(archive)], ["ingest", str(archive), str(root / "template")]):
                with patch.object(sys, "argv", ["venue_compliance.py", *command]), patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(venue.main(), 0)
                    self.assertEqual(json.loads(output.getvalue())["member_count"], 1)
            archive.write_bytes(b"invalid ZIP")
            with patch.object(sys, "argv", ["venue_compliance.py", "inspect", str(archive)]), patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(venue.main(), 2)
