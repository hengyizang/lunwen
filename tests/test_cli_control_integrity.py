"""Real filesystem attacks must not launder or redirect controller records."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import autopilot


class CliControlIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.patch = patch.object(autopilot.researchctl, "PROJECTS_ROOT", self.base / "projects")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.project = self.base / "projects/demo"
        self.receipt = self.project / "reports/watermark-cleanup/original/receipt.json"
        self.candidate = self.receipt.with_name("candidate.txt")
        self.receipt.parent.mkdir(parents=True)
        self.receipt.write_bytes(b'{"source":"original scientific evidence"}\n')
        self.candidate.write_bytes(b"The registered result and its uncertainty.\n")
        self.receipt_bytes = self.receipt.read_bytes()
        self.candidate_bytes = self.candidate.read_bytes()

    def symlink(self, link: Path, target: Path, *, directory: bool = False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"This filesystem cannot create actual symlinks: {exc}")

    def restored(self):
        self.assertFalse(self.receipt.is_symlink())
        self.assertFalse(self.receipt.parent.is_symlink())
        self.assertEqual(self.receipt.read_bytes(), self.receipt_bytes)
        self.assertEqual(self.candidate.read_bytes(), self.candidate_bytes)
        self.assertTrue(self.receipt.parent.is_dir())

    def test_equal_bytes_file_symlink_is_rejected_and_replaced_with_real_record(self):
        before = autopilot.protected_control_snapshot("demo")
        outside = self.base / "outside-receipt.json"
        outside.write_bytes(self.receipt_bytes)
        self.receipt.unlink()
        self.symlink(self.receipt, outside)
        with self.assertRaises(autopilot.AutopilotError):
            autopilot.ensure_protected_control_unchanged("demo", before)
        self.restored()
        self.assertEqual(outside.read_bytes(), self.receipt_bytes)

    def test_different_bytes_file_symlink_does_not_receive_restoration_payload(self):
        before = autopilot.protected_control_snapshot("demo")
        outside = self.base / "outside-private.txt"
        outside.write_bytes(b"External target must never be overwritten.\n")
        self.receipt.unlink()
        self.symlink(self.receipt, outside)
        with self.assertRaises(autopilot.AutopilotError):
            autopilot.ensure_protected_control_unchanged("demo", before)
        self.restored()
        self.assertEqual(outside.read_bytes(), b"External target must never be overwritten.\n")

    def test_equal_bytes_directory_symlink_is_removed_without_touching_external_tree(self):
        before = autopilot.protected_control_snapshot("demo")
        outside = self.base / "outside-copy"
        shutil.copytree(self.receipt.parent, outside)
        sentinel = outside / "private.txt"
        sentinel.write_bytes(b"Keep this external file.\n")
        shutil.rmtree(self.receipt.parent)
        self.symlink(self.receipt.parent, outside, directory=True)
        with self.assertRaises(autopilot.AutopilotError):
            autopilot.ensure_protected_control_unchanged("demo", before)
        self.restored()
        self.assertEqual((outside / "receipt.json").read_bytes(), self.receipt_bytes)
        self.assertEqual((outside / "candidate.txt").read_bytes(), self.candidate_bytes)
        self.assertEqual(sentinel.read_bytes(), b"Keep this external file.\n")

    def test_ancestor_directory_replaced_by_regular_file_is_repaired(self):
        before = autopilot.protected_control_snapshot("demo")
        directory = self.project / "reports"
        shutil.rmtree(directory)
        directory.write_bytes(b"A file cannot serve as the records directory.\n")
        with self.assertRaises(autopilot.AutopilotError):
            autopilot.ensure_protected_control_unchanged("demo", before)
        self.restored()
        self.assertTrue(directory.is_dir())

    def test_regular_record_replaced_by_directory_is_repaired(self):
        before = autopilot.protected_control_snapshot("demo")
        self.receipt.unlink()
        self.receipt.mkdir()
        (self.receipt / "forgery.txt").write_bytes(b"fake")
        with self.assertRaises(autopilot.AutopilotError):
            autopilot.ensure_protected_control_unchanged("demo", before)
        self.restored()
        self.assertTrue(self.receipt.is_file())

    def test_content_tamper_and_new_forgery_restore_without_false_positives(self):
        before = autopilot.protected_control_snapshot("demo")
        autopilot.ensure_protected_control_unchanged("demo", before)
        self.receipt.write_bytes(b"forged")
        forged = self.project / "reports/watermark-cleanup/new/candidate.txt"
        forged.parent.mkdir()
        forged.write_bytes(b"invented scientific result")
        with self.assertRaises(autopilot.AutopilotError):
            autopilot.ensure_protected_control_unchanged("demo", before)
        self.restored()
        self.assertFalse(forged.exists())
        self.assertFalse(forged.parent.exists())
        autopilot.ensure_protected_control_unchanged("demo", before)

    def test_preexisting_control_symlink_cannot_become_snapshot_authority(self):
        outside = self.base / "existing-alias.json"
        outside.write_bytes(self.receipt_bytes)
        self.receipt.unlink()
        self.symlink(self.receipt, outside)
        with self.assertRaises(autopilot.AutopilotError):
            autopilot.protected_control_snapshot("demo")
        self.assertEqual(outside.read_bytes(), self.receipt_bytes)


if __name__ == "__main__":
    unittest.main()
