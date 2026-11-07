"""Tests for the cloud issue boundary and isolated project state."""
import json
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
    def test_published_schema_matches_actual_actions_and_accepts_current_owner_envelopes(self):
        from jsonschema import Draft202012Validator
        schema = json.loads((cloud_job.ROOT / "schemas/cloud-job.schema.json").read_text())
        self.assertEqual(schema, cloud_job.job_schema())
        self.assertEqual(set(schema["properties"]["action"]["enum"]), set(cloud_job.EXTRA))
        self.assertLessEqual(set.union(*cloud_job.EXTRA.values()), set(schema["properties"]))
        validator = Draft202012Validator(schema)
        for value in (
            request("literature", request_file="program/reading-operation.json"),
            request("auxiliary", manifest="evidence/auxiliary-jobs/check.json"),
            request("routing_status"),
            request("review_dossier", operation="confirm_review_packet", packet_id="review-one"),
            request("amend_operating_constraints", allow_paid=True, new_ceiling_cny=300,
                    target_submission_ready_date="2026-12-01", expected_sha256="a" * 64,
                    note="The owner reviewed this actual cumulative operating amendment.")):
            with self.subTest(action=value["action"]):
                self.assertEqual(cloud_job.validate_request(value), value)
                validator.validate(value)
        value = request("cycle")
        value.pop("allow_paid")
        self.assertEqual(cloud_job.validate_request(value), value)
        validator.validate(value)

    def test_schema_and_runtime_reject_wrong_action_fields_and_incomplete_human_decisions(self):
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator(cloud_job.job_schema())
        for value in (request("status", request_file="program/reading-operation.json"),
                      request("cycle", allow_paid="yes"), request("approve", gate="G1"),
                      request("review_dossier", operation="confirm_review_packet")):
            with self.subTest(value=value):
                self.assertFalse(validator.is_valid(value))
                with self.assertRaises(cloud_job.CloudJobError):
                    cloud_job.validate_request(value)

    def test_owner_single_object_and_optional_legacy_paid_flag(self):
        self.assertEqual(cloud_job.issue_request(issue(request()))["action"], "status")
        self.assertEqual(cloud_job.issue_request(issue(request("free_jev_probe")))["action"], "free_jev_probe")
        self.assertEqual(cloud_job.issue_request(issue(request("bocha_jev_probe")))["action"], "bocha_jev_probe")
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(issue(request(), owner=42))
        for action, legacy in (("cycle", False), ("status", True), ("free_jev_probe", True)):
            self.assertEqual(cloud_job.issue_request(issue(request(action, allow_paid=legacy)))["action"], action)
        without_flag = request("cycle")
        without_flag.pop("allow_paid")
        self.assertEqual(cloud_job.issue_request(issue(without_flag)), without_flag)
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.validate_request(request("cycle", allow_paid="true"))
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.validate_request(request("bocha_jev_probe", live=True))
        self.assertEqual(cloud_job.validate_request(request("bocha_jev_probe", live=True,
                         free_policy_checked_on="2026-09-29"))["action"], "bocha_jev_probe")
        self.assertEqual(cloud_job.issue_request(issue(request("authorize_budget", allow_paid=False, new_ceiling_cny=300)))["new_ceiling_cny"], 300)
        for ceiling in (0, -1, 350.0, True, 900.0):
            with self.subTest(ceiling=ceiling), self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request(request("authorize_budget", allow_paid=False, new_ceiling_cny=ceiling))
        self.assertEqual(cloud_job.validate_request(request("authorize_budget", allow_paid=False,
                         new_ceiling_cny=800))["new_ceiling_cny"], 800)
        self.assertEqual(cloud_job.validate_request(request("reconcile_budget", allow_paid=False,
                        reservation_id="a" * 32, actual_cost_cny=0.0, evidence_note="Gateway shows no charge."))["action"], "reconcile_budget")

    def test_reject_duplicate_properties_extra_fences_and_prs(self):
        event = issue(request())
        event["issue"]["body"] = event["issue"]["body"].replace('"action": "status"', '"action": "status", "action": "cycle"')
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(json.loads(json.dumps(event), object_pairs_hook=cloud_job.unique_pairs))
        event = issue(request())
        event["issue"]["body"] += "\n```json\n{}\n```"
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(event)

    def test_operating_amendment_has_exact_owner_only_nonbillable_scope(self):
        selectors = {"new_ceiling_cny": 500, "target_submission_ready_date": "2026-10-26"}
        review = request("review_dossier", operation="amend_operating_constraints", **selectors)
        self.assertEqual(cloud_job.issue_request(issue(review))["new_ceiling_cny"], 500)
        change = request("amend_operating_constraints", expected_sha256="a" * 64,
                         note="Owner explicitly changed cumulative budget and target date.", **selectors)
        self.assertEqual(cloud_job.issue_request(issue(change))["action"], "amend_operating_constraints")
        self.assertEqual(cloud_job.validate_request(dict(change, allow_paid=True))["action"], "amend_operating_constraints")
        for invalid in (dict(change, model="unapproved-model"),
                        dict(review, gate="G1"), dict(review, operation="approve")):
            with self.subTest(invalid=invalid), self.assertRaises(cloud_job.CloudJobError):
                cloud_job.validate_request(invalid)
        with self.assertRaises(cloud_job.CloudJobError):
            cloud_job.issue_request(issue(change, owner=42))
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
            for rel in ("state/run.json", "state/model-spend-control.json", "state/model-usage.jsonl", "data/raw/input.json", "papers/P01/build/out.pdf", "reviews/a.md"):
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("safe", encoding="utf-8")
            try:
                (root / "reviews" / "linked.md").symlink_to(root / "reviews" / "a.md")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"This runner cannot create the symlink required by this test: {exc}")
            with self.assertRaises(cloud_job.CloudJobError):
                cloud_job.selected_files(root)
            (root / "reviews" / "linked.md").unlink()
            self.assertEqual([p.relative_to(root).as_posix() for p in cloud_job.selected_files(root)],
                             ["reviews/a.md", "state/model-spend-control.json", "state/run.json"])

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
