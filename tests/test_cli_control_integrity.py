"""The shared API writer rejects forged records and symlinks before any write."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import api_orchestrator as api


class CliControlIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.project = self.base / "projects/demo"
        self.project.mkdir(parents=True)
        self.root = patch.object(api, "ROOT", self.base)
        self.root.start()
        self.addCleanup(self.root.stop)

    def bundle(self, relative):
        return {
            "stage": "writing-and-review",
            "artifacts": [
                {
                    "path": "papers/P01/manuscript/draft.txt",
                    "content": "Uncommitted proposal",
                },
                {"path": relative, "content": "Forged control or result"},
            ],
        }

    def symlink(self, link, target, *, directory=False):
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Actual symlinks unavailable: {exc}")

    def test_source_and_quality_record_inventory_is_protected_before_bundle_writes(
        self,
    ):
        records = (
            "evidence/journal-sources/index.json",
            "evidence/source-scopes/source.txt",
            "program/hypothesis-audit.json",
            "papers/P01/reviews/revision-base/main.tex",
            "reports/watermark-cleanup/original/receipt.json",
            "state/run.json",
            "papers/P01/style/academic-style-audit.json",
            "data/raw/original.csv",
        )
        for relative in records:
            with self.subTest(path=relative):
                target = self.project / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"Original scientific source or control.\n")
                with self.assertRaises(ValueError):
                    api.apply_bundle(
                        "demo", self.bundle(relative), "writing-and-review"
                    )
                self.assertEqual(
                    target.read_bytes(), b"Original scientific source or control.\n"
                )
                self.assertFalse(
                    (self.project / "papers/P01/manuscript/draft.txt").exists()
                )

    def test_regular_drafts_are_editable_without_touching_protected_records(self):
        bundle = {
            "stage": "writing-and-review",
            "artifacts": [
                {
                    "path": "papers/P01/manuscript/draft.txt",
                    "content": "Evidence-bound provisional result.",
                }
            ],
        }
        api.apply_bundle("demo", bundle, "writing-and-review")
        self.assertEqual(
            (self.project / bundle["artifacts"][0]["path"]).read_text(),
            bundle["artifacts"][0]["content"],
        )

    def test_file_symlinks_are_rejected_even_when_target_bytes_match(self):
        for content in (b"Forged control or result", b"External private content"):
            with self.subTest(content=content):
                outside = self.base / "outside.txt"
                outside.write_bytes(content)
                alias = self.project / "papers/P01/manuscript/alias.txt"
                alias.unlink(missing_ok=True)
                self.symlink(alias, outside)
                with self.assertRaises(ValueError):
                    api.apply_bundle(
                        "demo",
                        self.bundle(alias.relative_to(self.project).as_posix()),
                        "writing-and-review",
                    )
                self.assertEqual(outside.read_bytes(), content)
                self.assertFalse(
                    (self.project / "papers/P01/manuscript/draft.txt").exists()
                )

    def test_parent_directory_symlinks_cannot_redirect_bundle_writes(self):
        outside = self.base / "outside-directory"
        outside.mkdir()
        sentinel = outside / "source.txt"
        sentinel.write_bytes(b"External original evidence")
        self.symlink(self.project / "papers/P01/manuscript", outside, directory=True)
        with self.assertRaises(ValueError):
            api.apply_bundle(
                "demo",
                self.bundle("papers/P01/manuscript/source.txt"),
                "writing-and-review",
            )
        self.assertEqual(sentinel.read_bytes(), b"External original evidence")
        self.assertFalse((outside / "draft.txt").exists())

    def test_atomic_controller_write_does_not_follow_a_predictable_temporary_symlink(
        self,
    ):
        outside = self.base / "private-sentinel.txt"
        outside.write_bytes(b"Keep external content.\n")
        target = self.project / "state/controller-record.json"
        target.parent.mkdir(parents=True)
        self.symlink(target.with_name("." + target.name + ".tmp"), outside)
        api.write_json_atomic(target, {"record": "trusted"})
        self.assertEqual(outside.read_bytes(), b"Keep external content.\n")
        self.assertEqual(target.read_text(), '{\n  "record": "trusted"\n}\n')
