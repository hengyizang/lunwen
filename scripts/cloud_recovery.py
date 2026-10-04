"""Owner-authorized cloud recovery: evidence, bounded retries and tested rollback.

No model calls, scientific decisions, experiment replays, or arbitrary patches.
Privileged code always comes from main. Failed-run artifacts are inert JSON.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts import cloud_job, cloud_continuation, cloud_progress, cloud_checkpoint, model_spend, researchctl
from scripts.cloud_retry import redact, transient

ROOT = Path(__file__).resolve().parents[1]
REPO = cloud_job.REPOSITORY
STATE = "state/cloud-recovery.json"
WORKFLOWS = {".github/workflows/cloud-research.yml", ".github/workflows/research-continuation.yml"}
VALIDATION = ".github/workflows/cloud-repair-validation.yml"
ALLOWED = {"scripts/cloud_runtime.py": "prepare", "scripts/manuscript_docx.py": "_python_docx"}
REQUIRED = {"Cloud executor and checkpoint", "Fresh runner restore and scientific exports",
    "Cloud human review controls", "Experiment design and statistical evidence",
    "Gateway startup and five-role cycle", "Automatic recovery safety and fault injection",
    "Deterministic checks (Python 3.10)", "Deterministic checks (Python 3.12)",
    "Deterministic checks (Python 3.13)", "Windows D-drive installer syntax"}
SHA = re.compile(r"[a-f0-9]{40}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def api(path: str, *, method="GET", body=None):
    with tempfile.TemporaryDirectory(prefix="recovery-api-") as directory:
        command = ["gh", "api", f"repos/{REPO}/{path}", "--method", method]
        if body is not None:
            payload = Path(directory) / "body.json"
            payload.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            command += ["--input", str(payload)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode:
        raise RuntimeError("GitHub recovery operation failed: " + redact(result.stderr)[-1200:])
    return json.loads(result.stdout) if result.stdout.strip() else None


def blob(path: str, ref: str) -> str:
    if path not in ALLOWED or not SHA.fullmatch(ref):
        raise ValueError("untrusted rollback source")
    value = api(f"contents/{path}?ref={ref}")
    if value.get("type") != "file" or value.get("size", 0) > 100_000:
        raise ValueError("rollback requires a bounded regular source file")
    return base64.b64decode(value["content"], validate=False).decode("utf-8")


def trusted_run(run: dict, paths=WORKFLOWS) -> None:
    if (run.get("path") not in paths or run.get("head_branch") != "main"
            or (run.get("head_repository") or {}).get("full_name") != REPO
            or (run.get("repository") or {}).get("full_name") != REPO
            or (run.get("actor") or {}).get("id") not in {cloud_job.OWNER_ID, 41898282}
            or not SHA.fullmatch(str(run.get("head_sha", "")))
            or run.get("event") not in {"issues", "schedule", "workflow_dispatch", "push"}):
        raise ValueError("untrusted recovery event; only canonical owner main runs are accepted")


def checks_pass(run: dict) -> bool:
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        return False
    jobs = api(f"actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
    names = {}
    for job in jobs:
        name = job["name"].split(" / ")[-1]
        if name in REQUIRED:
            if name in names:
                return False
            names[name] = job.get("conclusion")
    return set(names) == REQUIRED and all(value == "success" for value in names.values())


def rollback(current: str, previous: str, path: str) -> str:
    """Restore one helper body; imports, signatures, checks and all other code stay exact."""
    name = ALLOWED[path]
    trees = [ast.parse(text) for text in (current, previous)]
    functions = []
    for tree in trees:
        matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
        if len(matches) != 1:
            raise ValueError("rollback helper is missing or ambiguous")
        functions.append(matches[0])
    old, good = functions
    signature = lambda f: ast.dump(ast.FunctionDef(name=f.name, args=f.args, body=[],
                                                  decorator_list=f.decorator_list, returns=f.returns,
                                                  type_comment=f.type_comment), include_attributes=False)
    if signature(old) != signature(good):
        raise ValueError("automatic recovery cannot change a function contract")
    # Require the known-good revision to agree on every protected statement.
    for tree, function in zip(trees, functions):
        function.body = [ast.Pass()]
    if ast.dump(trees[0], include_attributes=False) != ast.dump(trees[1], include_attributes=False):
        raise ValueError("known-good source changes protected imports, controls or other functions")
    lines, prior = current.splitlines(keepends=True), previous.splitlines(keepends=True)
    proposed = "".join(lines[:old.lineno - 1] + prior[good.lineno - 1:good.end_lineno] + lines[old.end_lineno:])
    ast.parse(proposed)
    if proposed == current:
        raise ValueError("no verified rollback change available")
    return proposed


def authority(project: Path) -> str | None:
    """Recheck unchanged continuation authority and unresolved billing/evidence."""
    policy = read(project / cloud_continuation.POLICY, {})
    constraints_path = project / "intake/constraints.json"
    state = read(project / "state/run.json", {})
    approvals = state.get("approvals", [])
    g0 = next((x for x in reversed(approvals) if x.get("gate") == "G0"), {})
    constraints = read(constraints_path, {})
    if (policy.get("enabled") is not True or not constraints_path.is_file()
            or cloud_checkpoint.sha(constraints_path) != policy.get("constraints_sha256")
            or constraints.get("execution_mode") != "cloud_only"
            or "G0" not in state.get("approved_gates", [])
            or g0.get("actor") != policy.get("actor")
            or g0.get("artifact_sha256") != policy.get("g0_approval_artifact_sha256")):
        return "continuation_authority_changed"
    control = model_spend.read(project, required=True)
    if control["reservations"]:
        return "billing_reconciliation_pending"
    if control["spent_cny"] >= control["authorized_ceiling_cny"]:
        return "budget_boundary"
    if state.get("status") in {"awaiting_approval", "approved", "submission_ready"} or state.get("gate") is None:
        return "human_gate_pending"
    registry = project / "experiments/registry.jsonl"
    for line in registry.read_text(encoding="utf-8").splitlines() if registry.is_file() else []:
        if json.loads(line).get("status") in {"failed", "fail", "error", "timed_out", "cancelled"}:
            return "failed_experiment_requires_review"
    pause = cloud_progress.pause_reason(project.name)
    return pause["reason"] if pause else None


def safe_report(report: dict, run: dict, main: str) -> bool:
    return (report.get("schema_version") == "1.0" and report.get("status") == "failed"
            and report.get("run_id") == str(run["id"])
            and report.get("run_attempt") == str(run.get("run_attempt", 1))
            and report.get("source_sha") == main == run["head_sha"]
            and report.get("project") == "my-phd" and report.get("action") in {"cycle", "continuation"}
            and report.get("checkpoint_persisted") is True)


def classify(report: dict) -> str:
    diagnostic = str(report.get("diagnostic", ""))
    if (report.get("phase") == "environment" and report.get("execution_started") is False
            and transient(diagnostic)):
        return "environment_retry"
    if report.get("phase") in {"environment", "execution"}:
        for path, function in ALLOWED.items():
            if re.search(r'File "[^"\n]*' + re.escape(path) + r'", line \d+, in ' + re.escape(function) + r'\b', diagnostic):
                return "rollback:" + path
    return "inspection_required"


def bounded(state: dict, fingerprint: str, policy: dict) -> bool:
    events = state.get("events", [])
    operations = {"resume", "propose", "setup_retry"}
    incidents = sum(x.get("fingerprint") == fingerprint and x.get("operation") in operations for x in events)
    daily = sum(x.get("at", "").startswith(now()[:10]) and x.get("operation") in operations for x in events)
    return incidents < policy["max_incident_recoveries"] and daily < policy["max_daily_recoveries"]


def incident_fingerprint(report: dict) -> str:
    diagnostic = re.sub(r"\b\d{6,}\b|/home/runner/[^\s\"]+", "<volatile>", str(report.get("diagnostic", "")))
    return digest([report.get("source_sha"), report.get("phase"), classify(report), diagnostic])


def alert(state: dict, fingerprint: str, reason: str, run_id: int) -> None:
    if fingerprint in state.setdefault("alerts", {}):
        return
    issue = api("issues", method="POST", body={"title": "[cloud-recovery] 需要检查：" + reason[:80],
        "body": "自动恢复已停止：`" + reason + "`。失败证据与检查点保留。"
                "没有增加预算、重发模型请求、重跑正式实验或批准科学关卡。\n\n"
                f"[失败运行](https://github.com/{REPO}/actions/runs/{run_id})\n\n"
                "请修复或完成对账后，通过原有 owner resume 控制恢复。"})
    state["alerts"][fingerprint] = issue["number"]


def resume(project: Path, state: dict, report: dict, fingerprint: str, proof: dict) -> None:
    status_path = project / cloud_continuation.STATUS
    previous = read(status_path, {})
    if previous.get("source_run_id") != report["run_id"] or previous.get("last_cycle_exit_code", 0) == 0:
        raise ValueError("failed continuation state changed; no automatic reset")
    event = {"at": now(), "fingerprint": fingerprint, "operation": "resume", "source_run_id": report["run_id"],
             "previous_status": previous, "status_sha256": cloud_checkpoint.sha(status_path), "proof": proof,
             "previous_progress_sha256": cloud_checkpoint.sha(project / cloud_progress.FILE)
                if (project / cloud_progress.FILE).is_file() else None}
    state.setdefault("events", []).append(event)
    researchctl.write_json(status_path, {"schema_version": "1.0", "last_cycle_exit_code": 0,
        "reason": "bounded_verified_engineering_recovery", "source_run_id": os.environ["GITHUB_RUN_ID"]})
    # Keep all progress counters, approvals, adverse results and spending authority.
    researchctl.write_json(project / STATE, state)


def propose(state: dict, report: dict, fingerprint: str, path: str, main: str) -> None:
    current = blob(path, main)
    cursor = main
    for _ in range(12):
        parents = api(f"commits/{cursor}")["parents"]
        if not parents:
            break
        cursor = parents[0]["sha"]
        candidate = blob(path, cursor)
        try:
            proposed = rollback(current, candidate, path)
        except (ValueError, SyntaxError):
            continue
        runs = api(f"actions/runs?head_sha={cursor}&event=push&per_page=20")["workflow_runs"]
        if not any(r.get("path") == ".github/workflows/validate.yml" and checks_pass(r) for r in runs):
            continue
        branch = "cloud-repair/" + fingerprint[:16]
        api("git/refs", method="POST", body={"ref": "refs/heads/" + branch, "sha": main})
        base_tree = api(f"git/commits/{main}")["tree"]["sha"]
        tree = api("git/trees", method="POST", body={"base_tree": base_tree,
            "tree": [{"path": path, "mode": "100644", "type": "blob", "content": proposed}]})
        commit = api("git/commits", method="POST", body={"message": "Restore verified cloud helper after runtime regression",
                     "parents": [main], "tree": tree["sha"]})
        api("git/refs/heads/" + branch, method="PATCH", body={"sha": commit["sha"], "force": False})
        pr = api("pulls", method="POST", body={"head": branch, "base": "main",
            "title": "Recover cloud helper from verified revision",
            "body": f"Restore only `{path}` / `{ALLOWED[path]}` from CI-verified `{cursor}`. "
                    f"Triggered by [runtime failure](https://github.com/{REPO}/actions/runs/{report['run_id']}). "
                    "All protected statements, scientific evidence, approvals and budgets remain exact. "
                    "Automatic merge requires all ten cloud checks on this exact revision."})
        state["pending"] = {"pr": pr["number"], "branch": branch, "head": commit["sha"], "base": main,
            "baseline": cursor, "path": path, "content_sha256": hashlib.sha256(proposed.encode()).hexdigest(),
            "fingerprint": fingerprint, "report": report, "at": now()}
        state.setdefault("events", []).append({"at": now(), "operation": "propose", "fingerprint": fingerprint,
                                                "pr": pr["number"], "source_run_id": report["run_id"]})
        return
    raise ValueError("no protected-compatible helper with verified cloud CI found in the last 12 revisions")


def verify_pending(pending: dict, main: str) -> dict:
    if pending.get("base") != main or pending.get("path") not in ALLOWED:
        raise ValueError("main changed or repair scope is untrusted")
    pr = api(f"pulls/{pending['pr']}")
    if (pr.get("state") != "open" or pr.get("draft") or pr["base"]["ref"] != "main"
            or pr["head"]["sha"] != pending["head"] or pr["head"]["ref"] != pending["branch"]
            or pr["head"]["repo"]["full_name"] != REPO or pr["user"]["id"] != 41898282):
        raise ValueError("repair PR identity changed")
    files = api(f"pulls/{pending['pr']}/files?per_page=100")
    if len(files) != 1 or files[0].get("filename") != pending["path"] or files[0].get("status") != "modified":
        raise ValueError("repair changes files outside its recorded scope")
    candidate = rollback(blob(pending["path"], main), blob(pending["path"], pending["baseline"]), pending["path"])
    actual = blob(pending["path"], pending["head"])
    if candidate != actual or hashlib.sha256(actual.encode()).hexdigest() != pending["content_sha256"]:
        raise ValueError("repair content does not match the exact verified rollback")
    return pr


def failure_report(run: dict) -> dict:
    name = ("cloud-research-" if run["path"].endswith("/cloud-research.yml") else "continuous-research-") + str(run["id"])
    artifacts = api(f"actions/runs/{run['id']}/artifacts?per_page=100")["artifacts"]
    matches = [a for a in artifacts if a.get("name") == name and not a.get("expired")]
    if len(matches) != 1 or matches[0].get("size_in_bytes", 0) > 64_000_000:
        raise ValueError("trusted bounded failure artifact is unavailable")
    with tempfile.TemporaryDirectory(prefix="recovery-evidence-") as directory:
        result = subprocess.run(["gh", "run", "download", str(run["id"]), "--repo", REPO,
                                 "--name", name, "--dir", directory], capture_output=True, text=True,
                                timeout=180, check=False)
        path = Path(directory) / "failure.json"
        if result.returncode or not path.is_file() or path.is_symlink() or path.stat().st_size > 50_000:
            raise ValueError("trusted bounded failure receipt is unavailable; inspect runner logs")
        return read(path)


def setup_retry(run: dict, state: dict, policy: dict) -> bool:
    """An old job can be replayed only when its research step never started."""
    jobs = api(f"actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
    if len(jobs) != 1 or run.get("run_attempt", 1) > 2:
        return False
    steps = jobs[0].get("steps", [])
    execute = {"Run requested cloud job", "Re-check confirmation, configuration, human gates and remaining budget"}
    execution = [s for s in steps if s.get("name") in execute]
    failures = [s for s in steps if s.get("conclusion") in {"failure", "cancelled", "timed_out"}]
    if (len(execution) != 1 or execution[0].get("conclusion") != "skipped" or not failures
            or any(not re.fullmatch(r"Run actions/(?:checkout|setup-python)@v7", s.get("name", "")) for s in failures)):
        return False
    fingerprint = digest(["setup", run["head_sha"], [s["name"] for s in failures]])
    if not bounded(state, fingerprint, policy):
        return False
    # Save the intention before dispatch; never repeat after an ambiguous HTTP result.
    state.setdefault("events", []).append({"at": now(), "operation": "setup_retry",
        "fingerprint": fingerprint, "run_id": run["id"], "run_attempt": run.get("run_attempt", 1)})
    return True


def handle_failure(run: dict, project: Path, state: dict, policy: dict, main: str) -> bool:
    trusted_run(run)
    report = failure_report(run)
    fingerprint = incident_fingerprint(report)
    if state.get("pending"):
        return False
    reason = authority(project)
    if not safe_report(report, run, main):
        reason = reason or "missing_or_stale_safe_checkpoint"
    kind = classify(report)
    if not bounded(state, fingerprint, policy):
        reason = reason or "automatic_repair_attempt_limit"
    if reason or kind == "inspection_required":
        alert(state, fingerprint, reason or kind, run["id"])
        return False
    if kind == "environment_retry":
        resume(project, state, report, fingerprint, {"kind": kind, "model_calls": 0})
        return True
    propose(state, report, fingerprint, kind.split(":", 1)[1], main)
    return False


def validation_request(event: dict, output: Path) -> None:
    if ((event.get("repository") or {}).get("full_name") != REPO
            or (event.get("sender") or {}).get("id") not in {cloud_job.OWNER_ID, 41898282}):
        raise ValueError("only owner/bot validation requests are accepted")
    pending = api("contents/projects/my-phd/" + STATE + "?ref=cloud-state/my-phd")
    pending = json.loads(base64.b64decode(pending["content"]))["pending"]
    ref = (event.get("inputs") or {}).get("repair_ref", "")
    if not SHA.fullmatch(ref) or ref != pending["head"]:
        raise ValueError("validation requires the recorded exact repair revision")
    main = api("git/ref/heads/main")["object"]["sha"]
    verify_pending(pending, main)
    with output.open("a", encoding="utf-8") as stream:
        stream.write("repair_ref=" + ref + "\n")


def run(event: dict, *, inspect=False) -> None:
    if ((event.get("repository") or {}).get("full_name") != REPO
            or ((event.get("repository") or {}).get("owner") or {}).get("id") != cloud_job.OWNER_ID
            or os.environ.get("GITHUB_REF") != "refs/heads/main"):
        raise ValueError("recovery is owner main only")
    policy = read(ROOT / "config/cloud-recovery.json")
    if not policy or not policy.get("enabled"):
        return
    if (policy.get("project") != "my-phd" or policy.get("owner_id") != cloud_job.OWNER_ID
            or policy.get("model_calls_allowed") is not False or policy.get("external_paid_compute_usd") != 0
            or policy.get("max_incident_recoveries") != 2 or policy.get("max_daily_recoveries") != 4):
        raise ValueError("invalid bounded recovery policy")
    main = api("git/ref/heads/main")["object"]["sha"]
    if cloud_job.git("rev-parse", "HEAD").stdout.strip() != main:
        raise ValueError("checked-out recovery code is stale")
    trigger = event.get("workflow_run")
    runs = [api(f"actions/runs/{trigger['id']}")] if trigger else []
    if not runs:
        for workflow in ("cloud-research.yml", "research-continuation.yml"):
            runs += api(f"actions/workflows/{workflow}/runs?status=failure&branch=main&per_page=5")["workflow_runs"]
    if inspect:
        print(json.dumps({"model_calls": 0, "mutation": False, "failed_runs": [r["id"] for r in runs]}))
        return
    cloud_job.RUNTIME.mkdir(exist_ok=True)
    worktree, branch = cloud_job.restore_state("my-phd")
    project = cloud_job.ROOT / "projects/my-phd"
    state = read(project / STATE, {"schema_version": "1.0", "events": [], "alerts": {}, "seen": []})
    dispatch = False
    dispatch_validation = None
    replay_setup = None
    try:
        pending = state.get("pending")
        if pending:
            validate_runs = api("actions/workflows/cloud-repair-validation.yml/runs?event=workflow_dispatch&per_page=30")["workflow_runs"]
            matches = [r for r in validate_runs if r.get("display_title") == "Cloud repair " + pending["head"]
                       and r.get("created_at", "") >= pending["at"][:19] + "Z"]
            completed = next((r for r in matches if r.get("status") == "completed"), None)
            if completed:
                trusted_run(completed, {VALIDATION})
                reason = authority(project)
                if reason or not checks_pass(completed):
                    alert(state, pending["fingerprint"], reason or "repair_cloud_checks_failed", completed["id"])
                else:
                    verify_pending(pending, main)
                    result = api(f"pulls/{pending['pr']}/merge", method="PUT",
                                 body={"sha": pending["head"], "merge_method": "squash"})
                    if not result.get("merged"):
                        raise ValueError("GitHub did not merge the verified repair")
                    resume(project, state, pending["report"], pending["fingerprint"],
                           {"kind": "verified_rollback", "pr": pending["pr"], "validation_run": completed["id"],
                            "validated_head": pending["head"], "merged_sha": result["sha"]})
                    state.pop("pending")
                    dispatch = True
            elif not matches:
                dispatch_validation = pending["head"]
        else:
            for source in sorted(runs, key=lambda r: r["id"], reverse=True):
                key = f"{source['id']}:{source.get('run_attempt', 1)}"
                if key in state["seen"] or source.get("path") not in WORKFLOWS or source.get("conclusion") != "failure":
                    continue
                state["seen"].append(key)
                try:
                    trusted_run(source)
                    if source["head_sha"] == main and not authority(project) and setup_retry(source, state, policy):
                        replay_setup = source["id"]
                    else:
                        dispatch = handle_failure(source, project, state, policy, main)
                except (ValueError, RuntimeError, KeyError, OSError) as exc:
                    alert(state, digest(key), str(exc), source["id"])
                if state.get("pending"):
                    dispatch_validation = state["pending"]["head"]
                break
        researchctl.write_json(project / STATE, state)
        cloud_job.persist_state("my-phd", worktree, branch, os.environ["GITHUB_RUN_ID"])
        if replay_setup:
            api(f"actions/runs/{replay_setup}/rerun-failed-jobs", method="POST")
        if dispatch_validation:
            api("actions/workflows/cloud-repair-validation.yml/dispatches", method="POST",
                body={"ref": "main", "inputs": {"repair_ref": dispatch_validation}})
        if dispatch:
            api("actions/workflows/research-continuation.yml/dispatches", method="POST",
                body={"ref": "main", "inputs": {"mode": "start"}})
        print(json.dumps({"model_calls": 0, "pending_pr": state.get("pending", {}).get("pr"),
                          "continuation_dispatched": dispatch, "recorded_events": len(state["events"])}))
    finally:
        cloud_job.git("worktree", "remove", "--force", str(worktree), check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--validation-output", type=Path)
    args = parser.parse_args()
    try:
        event = read(args.event)
        if args.validation_output:
            validation_request(event, args.validation_output)
        else:
            run(event, inspect=args.inspect)
        return 0
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        print("Automatic recovery stopped safely: " + redact(str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
