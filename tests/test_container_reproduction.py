"""Real Docker software acceptance; synthetic observations, no model or research claims.

The ordinary suite skips this integration. CI explicitly enables it, making a
missing daemon/image or an unsuccessful container a failure rather than a skip.
"""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from scripts import experiment_evidence as evidence
from scripts import experiment_evidence_acceptance as acceptance
from scripts import experiment_runner as runner
from scripts import research_case as case
from scripts.live_acceptance import DEFAULT_IMAGE
from scripts.research_artifacts import read, write, sha, record


TABLE = "results/replayed-table.csv"
CODE_PATH = "experiments/code/replay-table.py"
DATA_PATH = "experiments/code/table-input.json"
LOCK_PATH = "papers/P01/environment.lock"
RESOURCES = {"cpu": 1, "memory_gb": 0.5, "gpu": 0}
SEED = 173
TABLE_CODE = '''import csv, json, os, pathlib, platform
assert platform.python_version() == '3.10.21'
assert os.environ['RESEARCH_OS_RUN_ID'] == 'table-replay'
assert os.environ['RESEARCH_OS_SEED'] == os.environ['PYTHONHASHSEED'] == '173'
assert not any(os.environ.get(k) for k in ('GH_TOKEN', 'UUAPI_API_KEY', 'UUAPI_OPENAI_API_KEY', 'UUAPI_ANTHROPIC_API_KEY'))
assert {p.name for p in pathlib.Path('/sys/class/net').iterdir()} == {'lo'}, 'network must be disabled'
assert os.statvfs('/').f_flag & os.ST_RDONLY, 'root must be read-only'
status = dict(line.split(':', 1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
assert int(status['CapEff'].strip(), 16) == 0
assert status['NoNewPrivs'].strip() == '1'
for name in ('experiments/code/replay-table.py', 'experiments/code/table-input.json', 'papers/P01/environment.lock', 'results/undeclared.txt'):
    try:
        with open(name, 'ab') as handle: handle.write(b'forbidden')
    except OSError:
        pass
    else:
        raise AssertionError('write escaped the named output: ' + name)
cgroup = pathlib.Path('/sys/fs/cgroup')
if (cgroup / 'cpu.max').is_file():
    quota, period = (cgroup / 'cpu.max').read_text().split()
    memory = int((cgroup / 'memory.max').read_text())
else:
    cpu = next(p for p in (cgroup / 'cpu', cgroup / 'cpu,cpuacct') if p.exists())
    quota = (cpu / 'cpu.cfs_quota_us').read_text()
    period = (cpu / 'cpu.cfs_period_us').read_text()
    memory = int((cgroup / 'memory/memory.limit_in_bytes').read_text())
assert int(quota) / int(period) == 1, 'CPU quota changed'
assert memory == 536870912, 'memory limit changed'
rows = json.loads(pathlib.Path('experiments/code/table-input.json').read_text())
with open('results/replayed-table.csv', 'w', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=['comparison_id', 'estimate', 'ci_low', 'ci_high', 'decision'], extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps({'isolation_checks': 'passed', 'seed': 173, 'rows': len(rows)}))
'''


def binding(project: Path, relative: str) -> dict:
    return {"path": relative, "sha256": sha(project / relative)}


def authored(project: Path, relative: str, contents: str) -> dict:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    record(project, [path], "synthetic-container-reproduction-fixture")
    return binding(project, relative)


@unittest.skipUnless(os.environ.get("DR_OS_TEST_REAL_DOCKER") == "1",
                     "real Docker reproduction requires DR_OS_TEST_REAL_DOCKER=1 (mandatory in its CI step)")
class ContainerReproductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "posix" or shutil.which("docker") is None:
            raise AssertionError("The enabled real Docker acceptance needs a POSIX Docker runner.")
        # Inspect the managed/local socket explicitly. Preserve registry config
        # and proxy settings without allowing inherited endpoint redirection.
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS",
                                      "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"}}
        command = ["docker", "--host=unix:///var/run/docker.sock"]
        info = subprocess.run([*command, "info", "--format", "{{json .}}"],
                              env=environment, check=True, capture_output=True, text=True, timeout=30)
        capabilities = json.loads(info.stdout)
        if any(capabilities.get(key) is not True for key in ("MemoryLimit", "CpuCfsQuota", "CpuCfsPeriod")):
            raise AssertionError("The enabled real Docker acceptance requires enforced CPU/memory cgroups; "
                                 "this daemon reports unsupported resource controls.")
        present = subprocess.run([*command, "image", "inspect", DEFAULT_IMAGE],
                                 env=environment, capture_output=True, timeout=30)
        if present.returncode:
            subprocess.run([*command, "pull", DEFAULT_IMAGE], env=environment,
                           check=True, capture_output=True, text=True, timeout=300)

    def run_fixture(self, project: Path) -> dict:
        attempts = runner.execute(project.name, project_root=project)
        for attempt in attempts:
            self.assertEqual(attempt["status"], "succeeded",
                             (attempt, (project / attempt["logs"]["stderr"]).read_text()))
            self.assertEqual(attempt["executor_isolation"]["image"], DEFAULT_IMAGE)
            self.assertTrue(attempt["executor_isolation"]["network_disabled"])
            self.assertTrue(attempt["input_integrity"]["passed"])
        report = evidence.build_report(project, "P01")
        self.assertEqual(report["status"], "complete", report.get("errors"))
        return report

    def test_native_docker_export_replays_outside_deleted_project_with_all_results(self):
        with tempfile.TemporaryDirectory(prefix="real-container-reproduction-") as directory:
            root = Path(directory)
            reference = root / "reference"
            acceptance.fixture(reference, container=True, current_protocol=True)
            original = self.run_fixture(reference)

            # A fresh frozen fixture records the complete result-table input.
            # Its released results are independently checked against its own
            # actual Docker attempts, including the adverse recent baseline.
            project = root / "project"
            acceptance.fixture(project, container=True, current_protocol=True)
            lock = authored(project, LOCK_PATH,
                            "# Standard-library-only replay; the frozen image digest identifies its environment.\n")
            source = authored(project, DATA_PATH, json.dumps(original["comparisons"]))
            code = authored(project, CODE_PATH, TABLE_CODE)
            plan_path = project / "experiments/plan.json"
            plan = read(plan_path)
            run = {"run_id": "table-replay", "paper_id": "P01", "cwd": ".", "seed": SEED,
                   "argv": ["python3", CODE_PATH], "timeout_seconds": 60, "estimated_cost_usd": 0,
                   "isolation": {"kind": "container", "engine": "docker", "image": DEFAULT_IMAGE},
                   "resources": RESOURCES, "inputs": [source, code, lock], "expected_outputs": [TABLE],
                   "depends_on": [item["run_id"] for item in plan["runs"]]}
            plan["runs"].append(run)
            write(plan_path, plan)
            acceptance.freeze_fixture(project)
            report = self.run_fixture(project)
            matrix = acceptance.claim_matrix(project, report)
            (project / "claims").mkdir(exist_ok=True)
            shutil.copyfile(matrix, project / "claims/claim-evidence.csv")

            license_source = authored(project, "papers/P01/release-license.txt",
                                      "CC0 synthetic software fixture; redistribution permitted.\n")
            rights = {**license_source, "locator": "L1",
                      "excerpt": "CC0 synthetic software fixture; redistribution permitted."}
            spec = {"schema_version": "1.0", "paper_id": "P01", "reproduction": {
                "replay_run_id": run["run_id"], "result_table": TABLE,
                "license": license_source, "environment": lock,
                "files": [{**binding(project, name), "license": "CC0", "rights_source": rights}
                          for name in (CODE_PATH, DATA_PATH, LOCK_PATH)]}}
            authored(project, "papers/P01/research-case.json", json.dumps(spec))
            release = case.export(project, "P01", "reproduction")
            portable = root / "portable"
            shutil.copytree(project / release["path"], portable)
            attempts = [json.loads(line) for line in (project / "experiments/registry.jsonl").read_text().splitlines()]
            actual = next(row for row in attempts if row["run_id"] == run["run_id"])
            self.assertEqual(actual["resource_allocation"]["requested"], RESOURCES)
            self.assertEqual(actual["seed"], SEED)
            self.assertEqual(read(portable / "replay-run.json")["resources"], RESOURCES)
            runtime = read(portable / "recorded-runtime.json")
            self.assertEqual(runtime["environment_authority"], "recorded_digest_pinned_image")
            self.assertEqual(runtime["runtime"]["image"], DEFAULT_IMAGE)
            self.assertNotIn("python", runtime["runtime"])
            self.assertFalse(runtime["dependency_installation_verified"])
            expected_hash = sha(project / TABLE)
            expected_bytes = (project / TABLE).read_bytes()
            original_input_hashes = {item["path"]: item["sha256"] for item in run["inputs"]}
            shutil.rmtree(project)
            shutil.rmtree(reference)
            self.assertFalse(project.exists())
            output = portable / "sources" / TABLE
            output.unlink()
            replay = subprocess.run([sys.executable, str(portable / "reproduce.py")],
                                    cwd=portable, capture_output=True, text=True, timeout=120)
            self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
            self.assertIn('"isolation_checks": "passed"', replay.stdout)
            self.assertEqual(sha(output), expected_hash)
            self.assertEqual(output.read_bytes(), expected_bytes)
            for relative, digest in original_input_hashes.items():
                self.assertEqual(sha(portable / "sources" / relative), digest)
            self.assertFalse((portable / "sources/results/undeclared.txt").exists())
            rows = {row["comparison_id"]: row for row in csv.DictReader(io.StringIO(output.read_text()))}
            self.assertEqual(set(rows), {row["comparison_id"] for row in report["comparisons"]})
            self.assertEqual(len(rows), len(acceptance.CONDITIONS))
            for identifier in ("recent", "noise"):
                self.assertEqual(rows[identifier]["decision"], "does_not_establish_claim")
            self.assertLess(float(rows["recent"]["ci_high"]), 0)
            self.assertEqual(len(list(csv.DictReader(io.StringIO((portable / "results.csv").read_text())))), len(rows))
            self.assertFalse(release["scientific_validity_verified"])
            self.assertFalse(release["external_publication"])

            artifact = os.environ.get("DR_OS_CONTAINER_REPRO_ARTIFACTS")
            if artifact:
                destination = Path(artifact)
                destination.mkdir(parents=True, exist_ok=True)
                shutil.copytree(portable, destination / "portable", dirs_exist_ok=True)
                write(destination / "native-attempts.json", attempts)
                write(destination / "frozen-plan.json", plan)
                write(destination / "acceptance.json", {
                    "schema_version": "1.0", "status": "passed", "image": DEFAULT_IMAGE,
                    "actual_container_execution": True, "project_removed_before_replay": True,
                    "replayed_result_sha256": expected_hash, "comparison_count": len(rows),
                    "adverse_results_retained": ["recent", "noise"], "seed": SEED,
                    "resources": RESOURCES, "real_paid_model_calls": 0,
                    "scientific_validity_verified": False})
                (destination / "replay-stdout.txt").write_text(replay.stdout, encoding="utf-8")
