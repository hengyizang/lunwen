import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_checkpoint as cp


class CloudCheckpointTests(unittest.TestCase):
    def test_fresh_runner_restores_code_source_responses_results_and_api_audits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first", root / "second"
            files = {
                "experiments/code/run.py": b"print('fixture')",
                "experiments/config.yaml": b"seed: 17",
                "evidence/literature/raw/source.xml": b"<feed/>",
                "data/processed/measurements.parquet": b"PAR1fixture",
                "papers/P01/figures/plot.renderer.py": b"print('render')",
                "experiments/runs/trial/run.json": b'{"status":"failed"}',
                "experiments/runs/trial/stderr.txt": b"preserve negative evidence",
                "api_runs/trial/claude-plan.json": b'{"internal_only":true}',
                ".cache/model-responses/exact.json": b'{"cache":"fixture"}',
                "state/model-usage.jsonl": b'{"cost_cny":0.1}\n',
            }
            for rel, data in files.items():
                path = first / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            manifest = cp.prepare(first, root / "artifact", "12345")
            for file in cp.git_files(first):
                dest = second / file.relative_to(first)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, dest)
            cp.restore(second, root / "artifact/checkpoint.zip")
            self.assertEqual({p: (second / p).read_bytes() for p in files}, files)
            self.assertEqual(manifest["retention_days"], 90)
            self.assertIn("data/processed/measurements.parquet", [p["path"] for p in manifest["files"]])

    def test_tampering_or_missing_archive_blocks_without_partial_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            data = project / "results/value.csv"
            data.parent.mkdir(parents=True)
            data.write_text("value\n-1\n")
            cp.prepare(project, root / "artifact", "12")
            data.unlink()
            archive = root / "artifact/checkpoint.zip"
            archive.write_bytes(archive.read_bytes() + b"tampered")
            with self.assertRaisesRegex(cp.CheckpointError, "archive hash"):
                cp.restore(project, archive)
            self.assertFalse(data.exists())
            with patch.object(cp, "download_archive", side_effect=cp.CheckpointError("expired")):
                with self.assertRaisesRegex(cp.CheckpointError, "expired"):
                    cp.restore(project)
            with self.assertRaisesRegex(cp.CheckpointError, "not fully restored"):
                cp.prepare(project, root / "new", "13")

    def test_sensitive_raw_and_build_files_never_upload_and_unknown_files_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            for rel in ("data/raw/private.csv", "data/private/id.csv", "papers/P01/build/tmp.pdf"):
                path = project / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            self.assertEqual(cp.inventory(project), [])
            unknown = project / "data/processed/file.unknown"
            unknown.parent.mkdir(parents=True)
            unknown.write_text("fixture")
            with self.assertRaisesRegex(cp.CheckpointError, "explicit storage plan"):
                cp.inventory(project)

    def test_archive_cannot_restore_a_parent_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "state").mkdir()
            archive = project / "bad.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../escape.json", b"{}")
            (project / cp.MANIFEST).write_text(json.dumps({"schema_version": "1.0",
                "archive_sha256": cp.sha(archive), "files": [{"path": "../escape.json", "bytes": 2,
                "sha256": "a" * 64}]}))
            with self.assertRaises(cp.CheckpointError):
                cp.restore(project, archive)

    def test_archive_cannot_replace_control_state_even_with_a_matching_hash(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            project=Path(directory);(project/'state').mkdir();archive=project/'bad.zip';payload=b'{"approved":true}'
            with zipfile.ZipFile(archive,'w') as bundle:bundle.writestr('state/run.json',payload)
            (project/cp.MANIFEST).write_text(json.dumps({'schema_version':'1.0','archive_sha256':cp.sha(archive),
                'files':[{'path':'state/run.json','bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}]}))
            with self.assertRaisesRegex(cp.CheckpointError,'forbidden'):
                cp.restore(project,archive)
            self.assertFalse((project/'state/run.json').exists())

    def test_unchanged_idle_checkpoint_does_not_write_a_new_manifest_or_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project=root/'project';data=project/'results/negative.txt'
            data.parent.mkdir(parents=True);data.write_text('negative result')
            first=cp.prepare(project,root/'first','123')
            second=cp.prepare(project,root/'second','124')
            self.assertEqual(first,second);self.assertFalse((root/'second/checkpoint.zip').exists())
