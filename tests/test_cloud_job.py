"""Tests for the cloud issue boundary and isolated project state."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_job


def request(action="status", **extra):
    return {"schema_version": "1.0", "action": action, "project": "my-phd",
            "actor": "Hengyi", "allow_paid": action in cloud_job.PAID, **extra}


def issue(value, *, owner=cloud_job.OWNER_ID):
    return {"action": "opened", "repository": {"full_name": cloud_job.REPOSITORY,
            "owner": {"id": cloud_job.OWNER_ID}},
            "issue": {"user": {"id": owner}, "title": "[research-cloud] status",
                      "body": cloud_job.MARKER + "\n\n```json\n" + json.dumps(value) + "\n```"}}


class CloudJobTests(unittest.TestCase):
    def test_owner_single_object_and_paid_authorization(self):
        self.assertEqual(cloud_job.issue_request(issue(request()))["action"], "status")
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(issue(request(), owner=42))
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(issue(request("cycle", allow_paid=False)))
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(issue(request("status", allow_paid=True)))

    def test_reject_duplicate_properties_extra_fences_and_prs(self):
        event = issue(request())
        event["issue"]["body"] = event["issue"]["body"].replace('"action": "status"', '"action": "status", "action": "cycle"')
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(json.loads(json.dumps(event), object_pairs_hook=cloud_job.unique_pairs))
        event = issue(request())
        event["issue"]["body"] += "\n```json\n{}\n```"
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(event)
        event = issue(request())
        event["issue"]["pull_request"] = {}
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(event)

    def test_reject_untrusted_properties_and_paths(self):
        for path in ("/etc/passwd", "C:/private", "../private", "a/../b", "a\\..\\b", "./x"):
            with self.subTest(path=path), self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request(request("tooluniverse", request_file=path))
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.validate_request(request("cycle", context="x", shell="whoami"))
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.validate_request(request("cycle", stage="submission-ready"))

    def test_repository_entry_points_run_as_modules(self):
        code, output = cloud_job.run_command(["scripts/researchctl.py", "stages"])
        self.assertEqual(code, 0, output)
        self.assertIn('"intake"', output)
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.run_command(["/bin/sh", "-c", "true"])

    def test_result_selection_excludes_sensitive_paths_and_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("state/run.json", "data/raw/input.json", "papers/P01/build/out.pdf", "reviews/a.md"):
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("safe", encoding="utf-8")
            (root / "reviews" / "linked.md").symlink_to(root / "reviews" / "a.md")
            with self.assertRaises(cloud_job.CloudJobError):
                cloud_job.selected_files(root)
            (root / "reviews" / "linked.md").unlink()
            self.assertEqual([p.relative_to(root).as_posix() for p in cloud_job.selected_files(root)],
                             ["reviews/a.md", "state/run.json"])

    def test_state_branch_round_trip_without_remote_force_push(self):
        with tempfile.TemporaryDirectory() as d:
            parent = Path(d)
            bare, repo = parent / "remote.git", parent / "repo"
            subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
            subprocess.run(["git", "clone", str(bare), str(repo)], check=True, capture_output=True)

            def git(*args):
                return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout

            (repo / "README.md").write_text("test", encoding="utf-8")
            git("add", "README.md")
            git("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-m", "init")
            git("push", "origin", "HEAD:main")
            (repo / ".runtime").mkdir()
            with patch.object(cloud_job, "ROOT", repo), patch.object(cloud_job, "RUNTIME", repo / ".runtime"):
                worktree, branch = cloud_job.restore_state("my-phd")
                project = repo / "projects" / "my-phd"
                (project / "state").mkdir(parents=True)
                (project / "state" / "run.json").write_text('{"stage":"intake"}', encoding="utf-8")
                self.assertEqual(cloud_job.persist_state("my-phd", worktree, branch, "1"),
                                 ["projects/my-phd/state/run.json"])
                cloud_job.git("worktree", "remove", "--force", str(worktree))
                shutil_project = repo / "projects"
                import shutil
                shutil.rmtree(shutil_project)
                worktree, branch = cloud_job.restore_state("my-phd")
                self.assertEqual((project / "state" / "run.json").read_text(), '{"stage":"intake"}')
                cloud_job.git("worktree", "remove", "--force", str(worktree))
                self.assertIn("refs/heads/cloud-state/my-phd", git("ls-remote", "origin", "refs/heads/cloud-state/my-phd"))


if __name__ == "__main__":
    unittest.main()
