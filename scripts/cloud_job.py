#!/usr/bin/env python3
"""Owner-only GitHub issue control plane for a single cloud research job."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path, PurePosixPath

try:
    from scripts import cloud_checkpoint, cloud_continuation, cloud_human_controls, model_runtime, model_spend, researchctl
except ImportError:
    import researchctl  # type: ignore
    import cloud_checkpoint  # type: ignore
    import model_spend  # type: ignore
    import cloud_continuation  # type: ignore
    import model_runtime  # type: ignore
    import cloud_human_controls  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
ARTIFACT = RUNTIME / "cloud-artifact"
OWNER_ID = 163310614
REPOSITORY = "hengyizang/lunwen"
MARKER = "<!-- doctoral-research-os-cloud-job -->"
BODY = re.compile(r"\s*" + re.escape(MARKER) + r"\s*```json\s*\n(\{.*\})\s*\n```\s*", re.S)
PAID = {"cycle", "continuation", "paperqa", "tooluniverse", "auxiliary"}
COMMON = {"schema_version", "action", "project", "actor", "allow_paid"}
EXTRA = {
    "review_dossier": {"operation", "gate", "paper_id", "dataset_id", "receipt_id", "source", "scope", "packet_id", "kind", "record_id", "decision"},
    **{action: fields | cloud_human_controls.DECISIONS.get(action, set()) | {"expected_sha256", "note"}
       for action, fields in cloud_human_controls.SELECTORS.items()},
    "preflight": set(), "acceptance": set(), "free_jev_probe": set(),
    "bocha_jev_probe": {"live", "free_policy_checked_on"}, "init": {"paper_count"},
    "status": set(), "authorize_budget": {"new_ceiling_cny"},
    "reconcile_budget": {"reservation_id", "actual_cost_cny", "evidence_note"},
    "authorize_data": {"manifest", "expected_sha256"},
    "resume": {"expected_sha256", "repair_note"},
    "cycle": {"context", "stage", "task_kind", "task_profile"},
    "continuation": set(),
    "routing_status": set(),
    "set_routing_profile": {"stage", "task_profile", "expected_profile_sha256"},
    "accept_route": {"candidate_id", "packet_id", "profile_file", "expected_profile_sha256", "stage", "role"},
    "paperqa": {"corpus", "question", "settings"}, "tooluniverse": {"request_file"},
    "auxiliary": {"manifest"},
}


class CloudJobError(RuntimeError):
    pass


def unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise CloudJobError(f"duplicate JSON property: {key}")
        value[key] = item
    return value


def project_relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise CloudJobError("project-relative path is required")
    path = PurePosixPath(value)
    if path.is_absolute() or ":" in value.split("/")[0] or any(part in {".", ".."} for part in value.split("/")):
        raise CloudJobError("absolute paths and dot segments are forbidden")
    return value


def validate_request(value: object) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != "1.0":
        raise CloudJobError("schema_version 1.0 object required")
    action = value.get("action")
    if not isinstance(action, str) or action not in EXTRA:
        raise CloudJobError("unsupported action")
    if set(value) - COMMON - EXTRA[action] or COMMON - set(value):
        raise CloudJobError("missing or unsupported job properties")
    if not isinstance(value["project"], str):
        raise CloudJobError("project must be a slug")
    researchctl.validate_slug(value["project"])
    if (not isinstance(value["actor"], str) or not 0 < len(value["actor"].strip()) <= 100
            or any(ord(ch) < 32 for ch in value["actor"])):
        raise CloudJobError("actor must name the human requester")
    if type(value["allow_paid"]) is not bool or value["allow_paid"] != (action in PAID):
        raise CloudJobError("billable actions require allow_paid=true; non-billable actions require false")
    if action == "review_dossier" or action in cloud_human_controls.ACTIONS:
        try:
            operation = cloud_human_controls.validate_fields(value)
            allowed = cloud_human_controls.SELECTORS[operation]
            if action != "review_dossier":
                allowed = allowed | {"expected_sha256", "note"} | cloud_human_controls.DECISIONS.get(operation, set())
            elif set(value) - COMMON - allowed - {"operation"}:
                raise CloudJobError("dossier selectors must match the requested human operation")
        except (cloud_human_controls.HumanControlError, cloud_checkpoint.CheckpointError) as exc:
            raise CloudJobError(str(exc)) from exc
    if action == "authorize_budget" and (type(value.get("new_ceiling_cny")) is not int or value["new_ceiling_cny"] <= 0 or value["new_ceiling_cny"] % model_spend.STEP_CNY):
        raise CloudJobError("new_ceiling_cny must be a positive CNY 300 tranche boundary")
    if action == "reconcile_budget":
        if (not isinstance(value.get("reservation_id"), str) or not re.fullmatch(r"[a-f0-9]{32}", value["reservation_id"])
                or not isinstance(value.get("evidence_note"), str) or not 0 < len(value["evidence_note"].strip()) <= 300):
            raise CloudJobError("reconciliation requires a reservation ID and a short billing evidence note")
        model_spend._amount(value.get("actual_cost_cny"), "actual_cost_cny")
    if action in {"authorize_data", "resume"}:
        if not isinstance(value.get("expected_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", value["expected_sha256"]):
            raise CloudJobError("the exact reviewed artifact SHA-256 is required")
        if action == "authorize_data":
            relative = project_relative(value.get("manifest"))
            if not relative.startswith("data/manifests/") or not relative.endswith(".json"):
                raise CloudJobError("authorize an exact data/manifests/*.json file")
        elif not isinstance(value.get("repair_note"), str) or not 10 <= len(value["repair_note"].strip()) <= 500:
            raise CloudJobError("resume needs a 10–500 character explanation of the inspected repair")
    if action == "init" and (type(value.get("paper_count", 6)) is not int or not 1 <= value.get("paper_count", 6) <= 20):
        raise CloudJobError("paper_count must be 1–20")
    if action == "bocha_jev_probe":
        if type(value.get("live", False)) is not bool:
            raise CloudJobError("live must be a boolean")
        if value.get("live", False):
            if not isinstance(value.get("free_policy_checked_on"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value["free_policy_checked_on"]):
                raise CloudJobError("live Bocha trial requires the date the no-charge policy was checked")
        elif "free_policy_checked_on" in value:
            raise CloudJobError("a policy-check date is only used for a live Bocha trial")
    if action in {"cycle", "set_routing_profile"}:
        if not isinstance(value.get("context", ""), str) or len(value.get("context", "")) > 4000:
            raise CloudJobError("context exceeds 4000 characters")
        if "stage" in value and (not isinstance(value["stage"], str)
                or value["stage"] not in {s["name"] for s in researchctl.STAGES if s["gate"]}):
            raise CloudJobError("invalid stage")
        if "task_kind" in value:
            from scripts import model_routing
            policy, _ = model_routing.load_policy()
            if value["task_kind"] not in policy["critical_tasks"]:
                raise CloudJobError("task_kind must name an approved critical scientific task")
        if "task_profile" in value:
            from scripts import dynamic_routing
            try:
                if not isinstance(value["task_profile"], dict):
                    raise ValueError("task profile must be a JSON object")
                dynamic_routing.validate_profile(value["task_profile"], stage=value.get("stage"),
                                                 role="persistent-writer")
            except (TypeError, ValueError) as exc:
                raise CloudJobError(f"invalid task_profile: {exc}") from exc
        if action == "set_routing_profile":
            if "stage" not in value or "task_profile" not in value:
                raise CloudJobError("set_routing_profile requires stage and task_profile")
            if "expected_profile_sha256" in value and (not isinstance(value["expected_profile_sha256"], str)
                    or not re.fullmatch(r"[a-f0-9]{64}", value["expected_profile_sha256"])):
                raise CloudJobError("the exact current routing profile SHA-256 is required")
    if action == "accept_route":
        from scripts import model_routing
        for key in ("candidate_id", "packet_id"):
            if not isinstance(value.get(key), str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}", value[key]):
                raise CloudJobError(f"{key} must be an existing routing or review-packet identifier")
        relative = project_relative(value.get("profile_file"))
        if (len(relative) > 250 or not relative.startswith("evidence/routing-profiles/")
                or not relative.endswith(".json")):
            raise CloudJobError("profile_file must name evidence/routing-profiles/*.json")
        if not isinstance(value.get("expected_profile_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", value["expected_profile_sha256"]):
            raise CloudJobError("the exact reviewed routing profile SHA-256 is required")
        policy, _ = model_routing.load_policy()
        if not isinstance(value.get("stage"), str) or value["stage"] not in {*policy["stage_routes"], "auxiliary"}:
            raise CloudJobError("unsupported routing acceptance stage")
        if not isinstance(value.get("role"), str) or value["role"] not in {*model_routing.CYCLE_ROLES, *policy["auxiliary_routes"], *policy["critical_tasks"]}:
            raise CloudJobError("unsupported routing acceptance role")
    if action == "paperqa":
        if not isinstance(value.get("question"), str) or not 0 < len(value["question"].strip()) <= 2000:
            raise CloudJobError("a question of at most 2000 characters is required")
        if not isinstance(value.get("corpus"), str) or len(value["corpus"]) > 250:
            raise CloudJobError("corpus path is too long")
        project_relative(value["corpus"])
        if value.get("settings", "fast") not in {"fast", "medium", "high"}:
            raise CloudJobError("unsupported PaperQA2 settings")
    if action == "tooluniverse":
        if not isinstance(value.get("request_file"), str) or len(value["request_file"]) > 250:
            raise CloudJobError("request_file path is too long")
        project_relative(value["request_file"])
    if action == "auxiliary":
        manifest = project_relative(value.get("manifest"))
        if len(manifest) > 250 or not manifest.startswith("evidence/auxiliary-jobs/") or not manifest.endswith(".json"):
            raise CloudJobError("auxiliary requires an evidence/auxiliary-jobs/*.json manifest")
    return value


def issue_request(event: dict) -> dict:
    issue = event.get("issue") or {}
    repo = event.get("repository") or {}
    if (event.get("action") != "opened" or repo.get("full_name") != REPOSITORY
            or (repo.get("owner") or {}).get("id") != OWNER_ID
            or (issue.get("user") or {}).get("id") != OWNER_ID
            or "pull_request" in issue
            or not str(issue.get("title", "")).startswith("[research-cloud]")):
        raise CloudJobError("only an owner-created research-cloud issue can start a job")
    body = issue.get("body")
    if not isinstance(body, str) or len(body) > 16000:
        raise CloudJobError("issue body missing or too long")
    match = BODY.fullmatch(body)
    if not match:
        raise CloudJobError("issue must contain the marker and exactly one fenced JSON object")
    try:
        return validate_request(json.loads(match.group(1), object_pairs_hook=unique_pairs))
    except json.JSONDecodeError as exc:
        raise CloudJobError("issue must contain exactly one valid JSON object") from exc


def safe_file(path: Path, project: Path) -> bool:
    return path in selected_files(project)


def selected_files(project: Path) -> list[Path]:
    try:
        return cloud_checkpoint.git_files(project)
    except cloud_checkpoint.CheckpointError as exc:
        raise CloudJobError(str(exc)) from exc


def git(*argv: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    if argv and argv[0] in {"ls-remote", "fetch", "push"}:
        from scripts.cloud_retry import run
        result = run(["git", *argv], cwd=cwd or ROOT, operation="git-" + argv[0],
                     receipt=ARTIFACT / "infrastructure-retries.jsonl")
    else:
        result = subprocess.run(["git", *argv], cwd=cwd or ROOT, text=True, capture_output=True)
    if check and result.returncode:
        raise CloudJobError(f"git {argv[0]} failed (exit {result.returncode})")
    return result


def restore_state(slug: str) -> tuple[Path, str]:
    branch = f"cloud-state/{slug}"
    remote = git("ls-remote", "--exit-code", "origin", f"refs/heads/{branch}", check=False)
    if remote.returncode not in {0, 2}:
        raise CloudJobError("could not inspect state branch")
    tmp = Path(tempfile.mkdtemp(prefix="cloud-state-", dir=RUNTIME))
    if remote.returncode == 0:
        git("fetch", "origin", f"refs/heads/{branch}")
        ref = "FETCH_HEAD"
    else:
        ref = "HEAD"
    git("worktree", "add", "--detach", str(tmp), ref)
    source = tmp / "projects" / slug
    target = ROOT / "projects" / slug
    if source.exists():
        if target.exists():
            raise CloudJobError("main already contains a project with this slug")
        for path in selected_files(source):
            dest = target / path.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        cloud_checkpoint.restore(target)
    return tmp, branch


def persist_state(slug: str, worktree: Path, branch: str, run_id: str) -> list[str]:
    source = ROOT / "projects" / slug
    dest = worktree / "projects" / slug
    files = selected_files(source)
    if not files:
        return []
    current = {p.relative_to(source) for p in files}
    for old in selected_files(dest):
        if old.relative_to(dest) not in current:
            old.unlink()  # Git history retains prior evidence; current state mirrors the run.
    for file in files:
        copy = dest / file.relative_to(source)
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, copy)
    relative = f"projects/{slug}"
    git("add", "--", relative, cwd=worktree)
    changed = git("diff", "--cached", "--name-only", "--", relative, cwd=worktree).stdout.splitlines()
    if changed:
        git("-c", "user.name=research-cloud", "-c", "user.email=research-cloud@users.noreply.github.com",
            "commit", "-m", f"Save cloud research job {run_id} for {slug}", cwd=worktree)
        git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=worktree)
    return changed


def run_command(argv: list[str], *, timeout: int = 3600) -> tuple[int, str]:
    if not argv or not argv[0].startswith("scripts/") or not argv[0].endswith(".py"):
        raise CloudJobError("only repository Python entry points may run")
    module = argv[0][:-3].replace("/", ".")
    try:
        result = subprocess.run([sys.executable, "-m", module, *argv[1:]], cwd=ROOT, capture_output=True,
                                text=True, errors="replace", timeout=timeout)
        raw = (result.stdout + "\n" + result.stderr)[-50000:]
        for key in cloud_checkpoint.SECRET_NAMES | {"LITERATURE_CONTACT_EMAIL"} | {name for name in os.environ if name.startswith("DR_OS_WATERMARK_KEY_")}:
            if len(os.environ.get(key, "")) >= 8:
                raw = raw.replace(os.environ[key], "[REDACTED]")
        return result.returncode, raw
    except subprocess.TimeoutExpired:
        return 124, "Command timed out. Partial project files will be preserved for inspection."


def run_job(job: dict, run_id: str) -> int:
    RUNTIME.mkdir(exist_ok=True)
    ARTIFACT.mkdir(exist_ok=True)
    slug, action = job["project"], job["action"]
    worktree = None
    branch = f"cloud-state/{slug}"
    logs = []
    status = "completed"
    changed = []
    detail = ""
    continuation_decision = None
    progress_before = None
    phase = "restore"
    execution_started = False
    persisted = False
    try:
        if action in {"preflight", "init", "status", "routing_status", "accept_route", "set_routing_profile", "authorize_budget", "reconcile_budget", "authorize_data", "resume", "review_dossier", *cloud_human_controls.ACTIONS, *PAID}:
            worktree, branch = restore_state(slug)
            os.environ["DR_OS_STATE_WORKTREE"] = str(worktree)
            os.environ["DR_OS_STATE_BRANCH"] = branch
            if action in {"status", "cycle", "continuation", "review_dossier", *cloud_human_controls.ACTIONS}:
                from scripts.cloud_research_steps import acquire_data
                acquire_data(ROOT / "projects" / slug)
        project_exists = (ROOT / "projects" / slug / "state" / "run.json").is_file()
        phase = "control"
        if action == "preflight":
            output = cloud_continuation.startup_report(slug)
            output.update(repository=REPOSITORY, python=sys.version.split()[0], cloud_runtime=True)
            (ARTIFACT / "gateway-startup.json").write_text(
                json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            logs.append(json.dumps(output, ensure_ascii=False, indent=2))
            detail = (f"Configuration ready: **{output['configuration_ready']}** · "
                      f"Ready to continue: **{output['ready_to_continue']}** · Model calls: **0**.\n\n"
                      + output["next_action"] + "\n\n")
            if output["configuration_errors"]:
                detail += "\n".join("- " + error for error in output["configuration_errors"]) + "\n\n"
        elif action == "acceptance":
            from packaging.version import Version
            versions = {name: importlib.metadata.version(name) for name in ("paper-qa", "tooluniverse", "ref-verify")}
            expected = {"paper-qa": "2026.08.12", "tooluniverse": "1.5.1", "ref-verify": "1.2.0"}
            if any(Version(versions[name]) != Version(version) for name, version in expected.items()) or not shutil.which("pqa") or not shutil.which("ref-verify"):
                raise CloudJobError("pinned adapter version or entry point is unavailable")
            logs.append("Adapter package identity: " + json.dumps(versions))
            providers = ["openalex", "crossref", "arxiv", "europe-pmc", "dblp", "hal"]
            args = ["scripts/live_acceptance.py", "literature", "--limit", "1", "--pace-seconds", "2", "--output", str(ARTIFACT / "literature.json")]
            for provider in providers:
                args += ["--provider", provider]
            for cmd in (args, ["scripts/live_acceptance.py", "container", "--engine", "docker", "--output", str(ARTIFACT / "container.json")]):
                code, output = run_command(cmd, timeout=900)
                logs.append(output)
                if code:
                    status = "failed"
        elif action == "free_jev_probe":
            if not os.environ.get("OPENROUTER_API_KEY"):
                raise CloudJobError("a dedicated zero-credit OpenRouter key is required in the OPENROUTER_API_KEY repository secret")
            code, output = run_command(["scripts/free_jev_probe.py", "--output", str(ARTIFACT / "free-jev-probe.json")], timeout=120)
            logs.append(output)
            if code:
                status = "failed"
        elif action == "bocha_jev_probe":
            cmd = ["scripts/bocha_jev_probe.py", "--output", str(ARTIFACT / "bocha-jev-probe.json")]
            if job.get("live", False):
                cmd += ["--live", "--free-policy-checked-on", job["free_policy_checked_on"]]
            code, output = run_command(cmd, timeout=120)
            logs.append(output)
            if code:
                status = "failed"
        elif action == "init":
            if project_exists:
                raise CloudJobError("project already exists; use status or cycle")
            code, output = run_command(["scripts/researchctl.py", "init", "--project", slug, "--paper-count", str(job.get("paper_count", 6))])
            logs.append(output)
            if code:
                status = "failed"
        else:
            if not project_exists:
                raise CloudJobError("project does not exist; create it with init first")
            if action == "review_dossier" or action in cloud_human_controls.ACTIONS:
                result = cloud_human_controls.execute(job, run_id)
                (ARTIFACT / "human-control-receipt.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                logs.append(json.dumps(result, ensure_ascii=False, indent=2))
                if action == "review_dossier":
                    detail = (f"Review SHA-256: `{result['review_sha256']}`. "
                              f"Blockers: {len(result['blockers'])}. No human decision was recorded.\n\n")
                else:
                    detail = f"Recorded explicit owner operation `{action}`; no paid model call was made.\n\n"
                cmd = None
            elif action == "status":
                cmd = ["scripts/researchctl.py", "status", "--project", slug, "--json"]
            elif action == "set_routing_profile":
                if os.environ.get("DR_OS_ROUTING_PROFILE") != "production":
                    raise CloudJobError("routing management requires the production routing profile")
                result = cloud_continuation.set_task_profile(ROOT / "projects" / slug, job["stage"],
                    job["task_profile"], actor=job["actor"], run_id=str(run_id),
                    expected_profile_sha256=job.get("expected_profile_sha256"))
                (ARTIFACT / "routing-profile-receipt.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                logs.append(json.dumps(result, ensure_ascii=False, indent=2))
                detail = "Recorded the current-stage management profile; no model call, budget grant or scientific approval was performed.\n\n"
                cmd = None
            elif action in {"routing_status", "accept_route"}:
                if os.environ.get("DR_OS_ROUTING_PROFILE") != "production":
                    raise CloudJobError("routing management requires the production routing profile")
                cmd = ["scripts/dynamic_routing.py", "status" if action == "routing_status" else "accept",
                       "--project", slug]
                if action == "accept_route":
                    cmd += ["--candidate-id", job["candidate_id"], "--packet-id", job["packet_id"],
                            "--profile-file", job["profile_file"], "--expected-profile-sha256", job["expected_profile_sha256"],
                            "--stage", job["stage"], "--role", job["role"], "--actor", job["actor"]]
                detail = "Routing management checks existing evidence; no model call, budget grant or scientific approval is performed.\n\n"
            elif action == "authorize_budget":
                state = model_spend.grant(ROOT / "projects" / slug, new_ceiling_cny=job["new_ceiling_cny"],
                                          actor=job["actor"], run_id=run_id)
                logs.append(f"Owner approved project model spending ceiling CNY {state['authorized_ceiling_cny']}; no model call was made.")
                detail = f"Approved cumulative model API ceiling: CNY {state['authorized_ceiling_cny']}.\n\n"
                cmd = None
            elif action == "reconcile_budget":
                state = model_spend.reconcile(ROOT / "projects" / slug, job["reservation_id"],
                                              actual_cost_cny=job["actual_cost_cny"], actor=job["actor"],
                                              run_id=run_id, evidence_note=job["evidence_note"])
                logs.append(f"Owner reconciled reservation {job['reservation_id']}; aggregate estimated spending is CNY {state['spent_cny']}.")
                detail = f"Reconciled cumulative estimated model API spend: CNY {state['spent_cny']}.\n\n"
                cmd = None
            elif action == "authorize_data":
                from scripts.cloud_research_steps import authorize_data
                authorize_data(ROOT / "projects" / slug, job["manifest"], job["expected_sha256"], job["actor"], run_id)
                detail = "Recorded owner review of the exact data manifest; scientific gates are unchanged.\n\n"
                cmd = None
            elif action == "resume":
                from scripts.cloud_progress import resume
                resume(slug, job["expected_sha256"], job["actor"], job["repair_note"], run_id)
                detail = "Recorded the inspected repair; the next job rechecks budget, configuration and all gates.\n\n"
                cmd = None
            elif action in {"cycle", "continuation"}:
                if action == "continuation":
                    continuation_decision = cloud_continuation.evaluate(slug)
                    cloud_continuation.checkpoint(slug, continuation_decision, run_id)
                    detail = f"Continuation: `{continuation_decision['reason']}`.\n\n"
                    logs.append(json.dumps(continuation_decision, ensure_ascii=False, indent=2))
                if action == "continuation" and not continuation_decision["should_run"]:
                    cmd = None
                else:
                    if action == "continuation" and job["actor"] != continuation_decision["actor"]:
                        raise CloudJobError("continuation actor must match the recorded owner confirmation")
                    cmd = cycle_command(job, slug)
                    from scripts.cloud_runtime import prepare as prepare_runtime
                    phase = "environment"
                    prepare_runtime(ROOT / "projects" / slug)
                    phase = "control"
                    from scripts.cloud_progress import snapshot
                    progress_before = snapshot(slug)
            elif action == "auxiliary":
                if os.environ.get("DR_OS_ROUTING_PROFILE") != "production":
                    raise CloudJobError("bounded auxiliary jobs require the production routing profile")
                project = ROOT / "projects" / slug
                control = model_spend.read(project, required=True)
                if control["authorized_ceiling_cny"] <= 0 or control["reservations"]:
                    raise CloudJobError("auxiliary work needs existing owner budget and no outstanding reservations")
                os.environ["DR_OS_REQUIRE_MODEL_AUTH"] = "1"
                os.environ["DR_OS_REQUIRE_REMOTE_RESERVATION"] = "1"
                cmd = ["scripts/auxiliary_job.py", "--project", slug, "--manifest", job["manifest"],
                       "--output", "evidence/auxiliary/" + run_id + ".json", "--execute"]
            elif action == "paperqa":
                if os.environ.get("DR_OS_ROUTING_PROFILE") != "production":
                    raise CloudJobError("PaperQA2 SDK is unmetered; select production for the native budgeted source-QA alternative")
                from scripts.paper_qa import _file
                project = ROOT / "projects" / slug
                corpus = project / project_relative(job["corpus"])
                if corpus.is_symlink() or not corpus.exists():
                    raise CloudJobError("source corpus must exist and cannot be a symlink")
                sources = [corpus] if corpus.is_file() else sorted(p for p in corpus.rglob("*")
                    if p.is_file() and p.suffix.lower() in {".txt", ".md", ".pdf"})
                if not 1 <= len(sources) <= 20:
                    raise CloudJobError("native source QA requires 1-20 explicit supported source files")
                for source in sources:
                    _file(project, source.relative_to(project).as_posix(), "corpus source")
                question = project / "evidence" / "qa" / (run_id + "-question.txt")
                question.parent.mkdir(parents=True, exist_ok=True)
                question.write_text(job["question"], encoding="utf-8")
                control = model_spend.read(project, required=True)
                if control["authorized_ceiling_cny"] <= 0 or control["reservations"]:
                    raise CloudJobError("source QA needs existing owner budget and no outstanding reservations")
                os.environ["DR_OS_REQUIRE_MODEL_AUTH"]="1"
                os.environ["DR_OS_REQUIRE_REMOTE_RESERVATION"]="1"
                cmd = ["scripts/paper_qa.py", "--project", slug, "--question-file", question.relative_to(project).as_posix(),
                       "--output", "evidence/qa/" + run_id + ".json", "--execute"]
                for source in sources:
                    cmd += ["--source", source.relative_to(project).as_posix()]
            else:
                raise CloudJobError("ToolUniverse can use unmetered paid APIs; its paid cloud action is paused until its charges can count against the approved tranche")
            if cmd is not None:
                phase = "execution"
                execution_started = True
                code, output = run_command(cmd)
                logs.append(output)
                if action in {"cycle", "continuation"} and progress_before is not None:
                    from scripts.cloud_progress import record
                    record(slug, progress_before, run_id, code)
                    if action == "cycle":
                        cloud_continuation.checkpoint(slug, {"project": slug, "should_run": False,
                            "reason": "manual_cycle_completed" if not code else "previous_cycle_failed_requires_inspection"},
                            run_id, cycle_exit_code=code)
                if action == "continuation":
                    cloud_continuation.checkpoint(slug, continuation_decision, run_id, cycle_exit_code=code)
                    continuation_decision = cloud_continuation.evaluate(slug)
                    cloud_continuation.checkpoint(slug, continuation_decision, run_id, cycle_exit_code=code)
                    detail = f"Continuation after cycle: `{continuation_decision['reason']}`.\n\n"
                if code:
                    status = "failed"
                elif action == "status":
                    state = researchctl.load_state(slug)
                    detail = (f"Stage: `{state['stage']}` · Gate: `{state['gate']}` · "
                              f"State: `{state['status']}` · Blockers: {len(researchctl.gate_errors(slug, state['gate']))}.\n\n")
    except Exception:
        status = "failed"
        logs.append(traceback.format_exc())
        if worktree is not None and action in {"cycle", "continuation"}:
            cloud_continuation.checkpoint(slug, {"project": slug, "should_run": False,
                "reason": "previous_cycle_failed_requires_inspection"}, run_id, cycle_exit_code=2)
    finally:
        if worktree is not None:
            try:
                cloud_checkpoint.prepare(ROOT / "projects" / slug, RUNTIME / "checkpoint", run_id)
                changed = persist_state(slug, worktree, branch, run_id)
                persisted = True
            except (CloudJobError, cloud_checkpoint.CheckpointError, OSError, ValueError) as exc:
                status = "failed"
                phase = "checkpoint"
                logs.append("State persistence failed: " + str(exc))
                # Preserve the failure and conservative billing state even when
                # an unsupported/oversized research file prevents packaging.
                project = ROOT / "projects" / slug
                cloud_continuation.checkpoint(slug, {"project": slug, "should_run": False,
                    "reason": "checkpoint_repair_required"}, run_id, cycle_exit_code=2)
                try:
                    for relative in ("state/model-spend-control.json", "state/continuation-status.json"):
                        source = project / relative
                        if source.is_file():
                            cloud_checkpoint.check_file(source, project)
                            target = worktree / "projects" / slug / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(source, target)
                            git("add", "--", str(target.relative_to(worktree)), cwd=worktree)
                    if git("diff", "--cached", "--name-only", cwd=worktree).stdout.strip():
                        git("-c", "user.name=research-cloud", "-c", "user.email=research-cloud@users.noreply.github.com",
                            "commit", "-m", "Pause research after checkpoint failure; preserve billing", cwd=worktree)
                        git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=worktree)
                except (RuntimeError, OSError):
                    logs.append("Control-only recovery push failed; inspect the last remote reservation before any retry.")
            git("worktree", "remove", "--force", str(worktree), check=False)
            shutil.rmtree(worktree, ignore_errors=True)
        try:
            safe_results = selected_files(ROOT / "projects" / slug)
            with zipfile.ZipFile(ARTIFACT / "tracked-results.zip", "w", zipfile.ZIP_DEFLATED) as archive:
                for path in safe_results:
                    archive.write(path, path.relative_to(ROOT))
        except (RuntimeError, OSError, ValueError) as exc:
            status = "failed"
            phase = "packaging"
            logs.append("Result packaging failed: " + str(exc))
        from scripts.cloud_retry import redact
        diagnostic = redact("\n".join(logs))[-100000:]
        (ARTIFACT / "redacted-log.txt").write_text(diagnostic, encoding="utf-8")
        try:
            source_output = git("rev-parse", "HEAD", check=False).stdout
        except (RuntimeError, OSError):
            source_output = ""
        source_sha = source_output.strip() if isinstance(source_output, str) else ""
        if not re.fullmatch(r"[a-f0-9]{40}", source_sha):
            source_sha = ""  # Preserve the outcome; unknown code cannot auto-recover.
        (ARTIFACT / "failure.json").write_text(json.dumps({"schema_version": "1.0",
            "run_id": str(run_id), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
            "source_sha": source_sha, "project": slug, "action": action,
            "status": status, "phase": phase, "execution_started": execution_started,
            "checkpoint_persisted": persisted, "diagnostic": diagnostic[-12000:]}, ensure_ascii=False,
            indent=2) + "\n", encoding="utf-8")
        summary = (f"Cloud job `{action}` for `{slug}`: **{status}**.\n\n"
                   f"{detail}"
                   f"[GitHub Actions run](https://github.com/{REPOSITORY}/actions/runs/{run_id}) · "
                   f"State branch (when used): `cloud-state/{slug}` · Changed files: {len(changed)}.\n\n"
                   "The run artifact contains redacted logs and tracked results. Only explicit human decisions grant gates; software receipts do not establish scientific completion.\n")
        (RUNTIME / "cloud-summary.md").write_text(summary, encoding="utf-8")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
                output.write(summary)
        if action == "continuation" and status == "completed" and continuation_decision is not None:
            (RUNTIME / "continuation-followup.json").write_text(json.dumps(continuation_decision), encoding="utf-8")
    return 0 if status == "completed" else 1


def cycle_command(job: dict, slug: str) -> list[str]:
    from scripts.cloud_progress import pause_reason
    pause = pause_reason(slug)
    if pause:
        raise CloudJobError("Continuation needs external input or an inspected repair: " + pause["reason"])
    control = model_spend.read(ROOT / "projects" / slug, required=True)
    if not control or control["authorized_ceiling_cny"] <= 0:
        raise CloudJobError("an initial CNY 300 owner budget approval is needed before paid model calls")
    errors = cloud_continuation.configuration_errors(os.environ)
    if errors:
        raise CloudJobError("Gateway configuration pending: " + "; ".join(errors))
    state = researchctl.load_state(slug)
    if state["status"] in {"awaiting_approval", "approved"} or state["gate"] is None:
        raise CloudJobError("current gate requires human review or is already approved")
    if job.get("stage", state["stage"]) != state["stage"]:
        raise CloudJobError("requested stage does not match persisted current stage")
    context = job.get("context", "")
    if job["action"] == "continuation":
        context = ("Continue the owner-confirmed current stage toward the six-paper requirements. "
                   "Read the frozen intake constraints and existing evidence, initial/final audits and decision log; "
                   "repair remaining evidence and quality gaps without repeating completed work. "
                   "Preserve negative results. Use only cloud-authorized data and the cumulative approved budget. "
                   "Do not approve or advance a human gate, change spending authority, or auto-submit. "
                   "Keep Claude read-only and OpenAI as the persistent author. The October 7 target does not lower any requirement.")
    os.environ["DR_OS_REQUIRE_MODEL_AUTH"] = "1"
    os.environ["DR_OS_REQUIRE_REMOTE_RESERVATION"] = "1"
    production = os.environ.get("DR_OS_ROUTING_PROFILE")=="production"
    command = ["scripts/api_orchestrator.py", "cycle", slug, state["stage"],
            "--planner-provider", "codekey-kiro-enterprise" if production else "uuapi-anthropic",
            "--writer-provider", "cheapai-gpt-pro" if production else "uuapi-openai",
            "--critic-provider", "codekey-kiro-enterprise" if production else "uuapi-anthropic", "--context", context]
    task_profile = job.get("task_profile")
    if job["action"] == "continuation" and production:
        task_profile = cloud_continuation.task_profile(ROOT / "projects" / slug, state["stage"])
    if task_profile is not None:
        from scripts import dynamic_routing
        try:
            task_profile = dynamic_routing.validate_profile(task_profile, stage=state["stage"],
                                                           role="persistent-writer")
        except (TypeError, ValueError) as exc:
            raise CloudJobError(f"invalid task_profile: {exc}") from exc
        command += ["--task-profile", json.dumps(task_profile, separators=(",", ":"))]
    if job.get("task_kind"):
        command += ["--task-kind", job["task_kind"]]
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-event")
    validate.add_argument("--event", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True)
    validate.add_argument("--github-output", type=Path)
    execute = sub.add_parser("execute")
    execute.add_argument("--config", type=Path, required=True)
    execute.add_argument("--run-id", required=True)
    comment = sub.add_parser("comment")
    comment.add_argument("--issue", type=int, required=True)
    comment.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate-event":
            job = issue_request(json.loads(args.event.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(job), encoding="utf-8")
            if args.github_output:
                with args.github_output.open("a", encoding="utf-8") as handle:
                    handle.write(f"action={job['action']}\n")
            return 0
        if args.command == "execute":
            return run_job(validate_request(json.loads(args.config.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)), args.run_id)
        if not args.summary.is_file():
            raise CloudJobError("no cloud summary to post")
        return subprocess.run(["gh", "api", "-X", "POST", f"repos/{REPOSITORY}/issues/{args.issue}/comments",
                               "-F", f"body=@{args.summary}"], cwd=ROOT, check=False).returncode
    except (CloudJobError, researchctl.ResearchCtlError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"cloud job: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
