"""Acceptance authority boundaries; the separate cloud job uses the real PDF."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import literature_real_acceptance as acceptance
from scripts.research_artifacts import read, sha, write


class RealPaperAcceptanceBoundaries(unittest.TestCase):
    def test_real_acceptance_refuses_local_execution_before_network_or_writes(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.dict(os.environ, {"GITHUB_ACTIONS": "", "DR_OS_CLOUD_EXECUTOR": ""}), \
                patch.object(acceptance, "fetch_bytes") as fetch:
            with self.assertRaisesRegex(ValueError, "cloud"):
                acceptance.demonstrate(Path(temporary) / "output")
            self.assertFalse((Path(temporary) / "output").exists())
            fetch.assert_not_called()

    def test_acceptance_fixture_never_authorizes_existing_research_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "production-project"
            project.mkdir()
            write(project / "ACCEPTANCE-FIXTURE-ONLY.json", {"engineering_fixture_only": True,
                "production_owner_approval": False})
            with self.assertRaisesRegex(ValueError, "production"):
                acceptance._fixture_authority(project, "source.pdf", {})
            self.assertFalse((project / "state/data-authorizations.json").exists())

    def test_fixture_authority_is_explicit_hash_bound_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "real-paper-acceptance-fixture"
            project.mkdir()
            write(project / "ACCEPTANCE-FIXTURE-ONLY.json", {"engineering_fixture_only": True,
                "production_owner_approval": False})
            (project / "source.pdf").write_bytes(b"%PDF-fixture")
            relative = acceptance._fixture_authority(project, "source.pdf", {"url": acceptance.PUBLISHER})
            manifest = read(project / relative)
            authority = read(project / "state/data-authorizations.json")
            self.assertFalse(manifest["production_owner_approval"])
            self.assertFalse(authority["production_owner_approval"])
            self.assertEqual(manifest["download"]["sha256"], sha(project / "source.pdf"))
            self.assertEqual(authority["manifests"][relative]["sha256"], sha(project / relative))
            self.assertIn("NOT-project-owner", authority["manifests"][relative]["actor"])
            with self.assertRaisesRegex(ValueError, "existing authority"):
                acceptance._fixture_authority(project, "source.pdf", {})

    def test_publisher_license_is_checked_before_paper_acquisition(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.dict(os.environ, {"DR_OS_CLOUD_EXECUTOR": "1"}), \
                patch.object(acceptance, "fetch_bytes", return_value=(b"<html>no rights stated</html>", acceptance.PUBLISHER, 200, "text/html")), \
                patch.object(acceptance.literature_assets, "resolve") as resolve:
            with self.assertRaisesRegex(ValueError, "license"):
                acceptance.demonstrate(Path(temporary))
            resolve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
