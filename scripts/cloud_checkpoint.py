"""Hash-verified cloud checkpoints: small sources in Git, other results in Actions.

Raw datasets are rehydrated from authorized acquisition receipts, never uploaded.
Secrets/private paths are never archived. Missing/expired artifacts fail closed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

MANIFEST = "state/cloud-checkpoint.json"
DIRECTORIES = {"state", "intake", "program", "evidence", "data", "experiments", "claims",
               "reports", "reviews", "papers", "literature", "results", "api_runs", ".cache"}
GIT_SUFFIXES = {".json", ".jsonl", ".md", ".csv", ".tsv", ".txt", ".tex", ".bib", ".svg",
                ".png", ".pdf", ".docx", ".py", ".r", ".jl", ".yaml", ".yml", ".toml",
                ".xml", ".html", ".css", ".sty", ".cls", ".bst", ".lock"}
DATA_SUFFIXES = {".parquet", ".feather", ".npy", ".npz", ".h5", ".hdf5", ".pkl", ".pickle",
                 ".pt", ".pth", ".onnx", ".zip", ".gz", ".tar", ".zst", ".jpg", ".jpeg"}
GIT_FILE_LIMIT = 2_000_000
GIT_TOTAL_LIMIT = 14_000_000  # Leave space for the control manifest.
ARCHIVE_LIMIT = 512_000_000
SECRET_NAMES = {"UUAPI_API_KEY", "UUAPI_OPENAI_API_KEY", "UUAPI_ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
                "BOCHA_JEV_API_KEY", "OPENALEX_API_KEY", "SEMANTIC_SCHOLAR_API_KEY",
                "OPENCITATIONS_ACCESS_TOKEN", "TAVILY_API_KEY", "GH_TOKEN", "GITHUB_TOKEN"}


class CheckpointError(RuntimeError):
    pass


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(value: str) -> str:
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or any(ord(c) < 32 for c in value) or value.startswith("/")
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise CheckpointError("unsafe checkpoint path")
    return PurePosixPath(value).as_posix()


def excluded(value: str) -> bool:
    parts = PurePosixPath(value).parts
    if not parts or parts[0] not in DIRECTORIES:
        return True
    for index, part in enumerate(parts):
        lower = part.casefold()
        if lower in {"private", "secrets", "credentials", ".git", ".env"} or "secret" in lower or "credential" in lower:
            return True
        if part.startswith(".") and not (index == 0 and value.startswith(".cache/model-responses/")):
            return True
    # These source responses are public bibliographic receipts, not raw datasets.
    if "raw" in parts and not value.startswith("evidence/literature/raw/"):
        return True
    return any(p in {"build", "__pycache__"} for p in parts)


def check_file(path: Path, project: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents) if p == project or project in p.parents):
        raise CheckpointError("checkpoint paths must not be symlinks")
    secrets = [os.environ[k].encode() for k in SECRET_NAMES if len(os.environ.get(k, "")) >= 8]
    overlap = max((len(s) for s in secrets), default=1) - 1
    tail = b""
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            data = tail + chunk
            if any(s in data for s in secrets):
                raise CheckpointError("a checkpoint file contains a configured credential")
            tail = data[-overlap:] if overlap else b""


def inventory(project: Path) -> list[dict]:
    if not project.exists():
        return []
    if project.is_symlink() or not project.is_dir():
        raise CheckpointError("project must be a regular directory")
    entries, used_git, used_archive = [], 0, 0
    paths = sorted(project.rglob("*"), key=lambda p: (p.relative_to(project).parts[0] != "state", str(p)))
    for path in paths:
        rel = path.relative_to(project).as_posix()
        if excluded(rel) or not path.is_file():
            continue
        relative(rel)
        check_file(path, project)
        if path.suffix.lower() not in GIT_SUFFIXES | DATA_SUFFIXES:
            raise CheckpointError(f"unsupported checkpoint file requires an explicit storage plan: {rel}")
        size = path.stat().st_size
        internal = rel.startswith(("api_runs/", ".cache/", "experiments/runs/", "results/")) or rel == "state/model-usage.jsonl"
        in_git = (not internal and path.suffix.lower() in GIT_SUFFIXES and size <= GIT_FILE_LIMIT
                  and (rel == MANIFEST or used_git + size <= GIT_TOTAL_LIMIT))
        if rel.startswith("state/") and rel != "state/model-usage.jsonl" and not in_git:
            raise CheckpointError("control state exceeds the Git checkpoint limit; archive cannot replace authority")
        if in_git:
            used_git += size
        else:
            used_archive += size
        entries.append({"path": rel, "bytes": size, "sha256": sha(path), "storage": "git" if in_git else "artifact"})
    if used_archive > ARCHIVE_LIMIT:
        raise CheckpointError("checkpoint exceeds 512 MB; configure a reviewed external storage/rehydration plan")
    return entries


def git_files(project: Path) -> list[Path]:
    return sorted(project / item["path"] for item in inventory(project) if item["storage"] == "git")


def prepare(project: Path, destination: Path, run_id: str) -> dict | None:
    if not project.exists():
        return None
    if not re.fullmatch(r"[0-9]+", str(run_id)):
        raise CheckpointError("checkpoint needs a numeric GitHub run ID")
    files = [e for e in inventory(project) if e["storage"] == "artifact"]
    # Missing prior archive material must never be replaced by a smaller checkpoint.
    old_path = project / MANIFEST
    old = {}
    if old_path.is_file():
        old = json.loads(old_path.read_text())
        for entry in old.get("files", []):
            if not (project / relative(entry["path"])).is_file():
                raise CheckpointError("previous checkpoint was not fully restored")
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "checkpoint.zip"
    # Keep idle jobs stable, but refresh the archive before its 90-day expiry.
    if old.get("files") == files:
        try:
            recent = datetime.now(timezone.utc) - datetime.fromisoformat(old["created_at"]) < timedelta(days=60)
        except (KeyError, ValueError, TypeError):
            recent = not files
        if recent:
            archive.unlink(missing_ok=True)
            return old
    if files:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for entry in files:
                output.write(project / entry["path"], entry["path"])
    else:
        archive.unlink(missing_ok=True)
    value = {"schema_version": "1.0", "run_id": str(run_id),
             "created_at": datetime.now(timezone.utc).isoformat(),
             "artifact_name": f"research-checkpoint-{run_id}",
             "archive_sha256": sha(archive) if files else None,
             "retention_days": 90, "files": files,
             "raw_data_policy": "rehydrate_from_authorized_acquisition_receipts"}
    old_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value


def sync_billing(project: Path) -> None:
    """Push the reservation before network generation, surviving runner loss.

    The authenticated owner job sets these paths; authoring bundles cannot edit
    state or environment. A failed push blocks the transport, never permits it.
    """
    if os.environ.get("DR_OS_REQUIRE_REMOTE_RESERVATION") != "1":
        return
    worktree = os.environ.get("DR_OS_STATE_WORKTREE")
    branch = os.environ.get("DR_OS_STATE_BRANCH")
    if os.environ.get("GITHUB_ACTIONS") != "true" or not worktree or branch != f"cloud-state/{project.name}":
        raise CheckpointError("cloud billing checkpoint is not configured")
    checkout = Path(worktree)
    rel = f"projects/{project.name}/state/model-spend-control.json"
    target = checkout / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(project / "state/model-spend-control.json", target)
    def git(*args: str) -> subprocess.CompletedProcess:
        result = subprocess.run(["git", *args], cwd=checkout, capture_output=True, check=False)
        if result.returncode:
            raise CheckpointError("could not persist the billing reservation; provider request blocked")
        return result
    git("add", "--", rel)
    if git("diff", "--cached", "--name-only", "--", rel).stdout.strip():
        git("-c", "user.name=research-cloud", "-c", "user.email=research-cloud@users.noreply.github.com",
            "commit", "-m", "Reserve approved research API cost before transport", "--", rel)
        git("push", "origin", f"HEAD:refs/heads/{branch}")


def download_archive(manifest: dict, directory: Path) -> Path:
    run_id = str(manifest.get("run_id", ""))
    if not re.fullmatch(r"[0-9]+", run_id) or manifest.get("artifact_name") != f"research-checkpoint-{run_id}":
        raise CheckpointError("invalid checkpoint artifact identity")
    result = subprocess.run(["gh", "run", "download", run_id, "--repo", "hengyizang/lunwen",
                             "--name", manifest["artifact_name"], "--dir", str(directory)],
                            capture_output=True, timeout=180, check=False)
    path = directory / "checkpoint.zip"
    if result.returncode or not path.is_file():
        raise CheckpointError("checkpoint artifact is missing, expired, or unreadable; restore it before resuming")
    return path


def restore(project: Path, archive: Path | None = None) -> None:
    manifest_path = project / MANIFEST
    if not manifest_path.is_file():
        return  # Pre-checkpoint projects can migrate without inventing missing evidence.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files")
    if manifest.get("schema_version") != "1.0" or not isinstance(files, list):
        raise CheckpointError("invalid cloud checkpoint manifest")
    if not files:
        return
    with tempfile.TemporaryDirectory(prefix="research-checkpoint-") as directory:
        scratch = Path(directory)
        source = archive or download_archive(manifest, scratch / "download")
        if sha(source) != manifest.get("archive_sha256"):
            raise CheckpointError("checkpoint archive hash changed")
        expected = {relative(item["path"]): item for item in files}
        if (len(expected) != len(files) or any(excluded(p) for p in expected)
                or any(p.startswith("state/") and p != "state/model-usage.jsonl" for p in expected)):
            raise CheckpointError("duplicate or forbidden checkpoint entries")
        prepared = []
        total = 0
        with zipfile.ZipFile(source) as bundle:
            if len(bundle.infolist()) != len(expected) or {i.filename for i in bundle.infolist()} != set(expected):
                raise CheckpointError("archive entries do not match the checkpoint manifest")
            for info in bundle.infolist():
                rel = relative(info.filename)
                if stat.S_ISLNK(info.external_attr >> 16) or info.is_dir():
                    raise CheckpointError("archive must contain regular files")
                entry = expected[rel]
                total += info.file_size
                if total > ARCHIVE_LIMIT or info.file_size != entry.get("bytes"):
                    raise CheckpointError("checkpoint size mismatch or limit exceeded")
                target = project / rel
                if any(p.is_symlink() for p in (target, *target.parents) if p == project or project in p.parents):
                    raise CheckpointError("checkpoint destination contains a symlink")
                tmp = scratch / "verified" / rel
                tmp.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as src, tmp.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                if sha(tmp) != entry.get("sha256"):
                    raise CheckpointError("checkpoint file hash changed")
                check_file(tmp, scratch / "verified")
                prepared.append((tmp, target))
        # Validate the entire archive before exposing any restored output.
        for tmp, target in prepared:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tmp, target)
