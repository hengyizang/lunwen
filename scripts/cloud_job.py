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
import zipfile
from pathlib import Path, PurePosixPath

try:
    from scripts import model_spend, researchctl
except ImportError:
    import researchctl  # type: ignore
    import model_spend  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
ARTIFACT = RUNTIME / "cloud-artifact"
OWNER_ID = 163310614
REPOSITORY = "hengyizang/lunwen"
MARKER = "<!-- doctoral-research-os-cloud-job -->"
BODY = re.compile(r"\s*" + re.escape(MARKER) + r"\s*```json\s*\n(\{.*\})\s*\n```\s*", re.S)
PAID = {"cycle", "paperqa", "tooluniverse"}
COMMON = {"schema_version", "action", "project", "actor", "allow_paid"}
EXTRA = {
    "preflight": set(), "acceptance": set(), "free_jev_probe": set(), "init": {"paper_count"},
    "status": set(), "authorize_budget": {"new_ceiling_cny"},
    "reconcile_budget": {"reservation_id", "actual_cost_cny", "evidence_note"},
    "cycle": {"context", "stage"},
    "paperqa": {"corpus", "question", "settings"}, "tooluniverse": {"request_file"},
}
SUFFIXES = {".json", ".jsonl", ".md", ".csv", ".txt", ".tex", ".bib", ".svg", ".png", ".pdf", ".docx"}
DIRECTORIES = {"state", "intake", "program", "evidence", "data", "experiments", "claims", "reports", "reviews", "papers", "literature"}
EXCLUDED = {"raw", "private", "cache", "runs", "checkpoints", "build", "api_runs", "venue-template", "secrets", ".cache", "model-usage.jsonl"}


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
    if action == "authorize_budget" and (type(value.get("new_ceiling_cny")) is not int or value["new_ceiling_cny"] <= 0 or value["new_ceiling_cny"] % model_spend.STEP_CNY):
        raise CloudJobError("new_ceiling_cny must be a positive CNY 300 tranche boundary")
    if action == "reconcile_budget":
        if (not isinstance(value.get("reservation_id"), str) or not re.fullmatch(r"[a-f0-9]{32}", value["reservation_id"])
                or not isinstance(value.get("evidence_note"), str) or not 0 < len(value["evidence_note"].strip()) <= 300):
            raise CloudJobError("reconciliation requires a reservation ID and a short billing evidence note")
        model_spend._amount(value.get("actual_cost_cny"), "actual_cost_cny")
    if action == "init" and (type(value.get("paper_count", 6)) is not int or not 1 <= value.get("paper_count", 6) <= 20):
        raise CloudJobError("paper_count must be 1–20")
    if action == "cycle":
        if not isinstance(value.get("context", ""), str) or len(value.get("context", "")) > 4000:
            raise CloudJobError("context exceeds 4000 characters")
        if "stage" in value and value["stage"] not in {s["name"] for s in researchctl.STAGES if s["gate"]}:
            raise CloudJobError("invalid stage")
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
    rel = path.relative_to(project)
    if not rel.parts or rel.parts[0] not in DIRECTORIES or path.suffix.lower() not in SUFFIXES:
        return False
    if any(part.startswith(".") or part.lower() in EXCLUDED or "secret" in part.lower() or "credential" in part.lower() for part in rel.parts):
        return False
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent == project or project in parent.parents):
        raise CloudJobError("project contains a symlink in a persistable path")
    if not path.is_file() or path.stat().st_size > 2_000_000:
        return False
    return True


def selected_files(project: Path) -> list[Path]:
    if not project.exists():
        return []
    if project.is_symlink() or not project.is_dir():
        raise CloudJobError("project root must be a regular directory")
    files = [p for p in project.rglob("*") if p.is_file() and safe_file(p, project)]
    if sum(p.stat().st_size for p in files) > 15_000_000:
        raise CloudJobError("tracked cloud result exceeds 15 MB")
    secrets = [v.encode() for k, v in os.environ.items() if k in {"UUAPI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENALEX_API_KEY", "SEMANTIC_SCHOLAR_API_KEY", "OPENCITATIONS_ACCESS_TOKEN"} and len(v) >= 8]
    for path in files:
        data = path.read_bytes()
        if any(secret in data for secret in secrets):
            raise CloudJobError("a persistable file contains a configured credential")
    return sorted(files)


def git(*argv: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
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
        for key in ("UUAPI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENALEX_API_KEY", "LITERATURE_CONTACT_EMAIL", "SEMANTIC_SCHOLAR_API_KEY", "OPENCITATIONS_ACCESS_TOKEN"):
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
    try:
        if action in {"init", "status", "authorize_budget", "reconcile_budget", *PAID}:
            worktree, branch = restore_state(slug)
        project_exists = (ROOT / "projects" / slug / "state" / "run.json").is_file()
        if action == "preflight":
            output = {"repository": REPOSITORY, "project": slug, "configured": {
                name: bool(os.environ.get(name)) for name in ("UUAPI_API_KEY", "UUAPI_BASE_URL", "UUAPI_ANTHROPIC_MODEL", "UUAPI_OPENAI_MODEL", "DR_OS_MODEL_PRICING_JSON", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "OPENALEX_API_KEY", "LITERATURE_CONTACT_EMAIL")},
                "python": sys.version.split()[0], "cloud_runtime": True}
            logs.append(json.dumps(output, ensure_ascii=False, indent=2))
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
            if action == "status":
                cmd = ["scripts/researchctl.py", "status", "--project", slug, "--json"]
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
            elif action == "cycle":
                control = model_spend.read(ROOT / "projects" / slug, required=True)
                if not control or control["authorized_ceiling_cny"] <= 0:
                    raise CloudJobError("an initial CNY 300 owner budget approval is needed before paid model calls")
                required = ("UUAPI_API_KEY", "UUAPI_BASE_URL", "UUAPI_ANTHROPIC_MODEL", "UUAPI_OPENAI_MODEL", "DR_OS_MODEL_PRICING_JSON")
                if any(not os.environ.get(name) for name in required):
                    raise CloudJobError("UUAPI gateway key, base URL, exact model IDs and CNY pricing must be configured")
                state = researchctl.load_state(slug)
                if state["status"] in {"awaiting_approval", "approved"} or state["gate"] is None:
                    raise CloudJobError("current gate requires human review or is already approved")
                if job.get("stage", state["stage"]) != state["stage"]:
                    raise CloudJobError("requested stage does not match persisted current stage")
                cmd = ["scripts/api_orchestrator.py", "cycle", slug, state["stage"],
                       "--planner-provider", "uuapi-anthropic", "--writer-provider", "uuapi-openai",
                       "--critic-provider", "uuapi-anthropic", "--context", job.get("context", "")]
                os.environ["DR_OS_REQUIRE_MODEL_AUTH"] = "1"
            elif action == "paperqa":
                raise CloudJobError("PaperQA2 can use unmetered external model calls; its paid cloud action is paused until its charges can count against the approved tranche")
            else:
                raise CloudJobError("ToolUniverse can use unmetered paid APIs; its paid cloud action is paused until its charges can count against the approved tranche")
            if cmd is not None:
                code, output = run_command(cmd)
                logs.append(output)
                if code:
                    status = "failed"
                elif action == "status":
                    state = researchctl.load_state(slug)
                    detail = (f"Stage: `{state['stage']}` · Gate: `{state['gate']}` · "
                              f"State: `{state['status']}` · Blockers: {len(researchctl.gate_errors(slug, state['gate']))}.\n\n")
    except (CloudJobError, model_spend.SpendControlError, researchctl.ResearchCtlError, OSError, ImportError) as exc:
        status = "failed"
        logs.append(str(exc))
    finally:
        if worktree is not None:
            try:
                changed = persist_state(slug, worktree, branch, run_id)
            except (CloudJobError, OSError) as exc:
                status = "failed"
                logs.append("State persistence failed: " + str(exc))
            git("worktree", "remove", "--force", str(worktree), check=False)
            shutil.rmtree(worktree, ignore_errors=True)
        try:
            safe_results = selected_files(ROOT / "projects" / slug)
            with zipfile.ZipFile(ARTIFACT / "tracked-results.zip", "w", zipfile.ZIP_DEFLATED) as archive:
                for path in safe_results:
                    archive.write(path, path.relative_to(ROOT))
        except (CloudJobError, OSError) as exc:
            status = "failed"
            logs.append("Result packaging failed: " + str(exc))
        (ARTIFACT / "redacted-log.txt").write_text("\n".join(logs)[-100000:], encoding="utf-8")
        summary = (f"Cloud job `{action}` for `{slug}`: **{status}**.\n\n"
                   f"{detail}"
                   f"[GitHub Actions run](https://github.com/{REPOSITORY}/actions/runs/{run_id}) · "
                   f"State branch (when used): `cloud-state/{slug}` · Changed files: {len(changed)}.\n\n"
                   "The run artifact contains redacted logs and tracked results. Human scientific gates remain pending.\n")
        (RUNTIME / "cloud-summary.md").write_text(summary, encoding="utf-8")
    return 0 if status == "completed" else 1


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
