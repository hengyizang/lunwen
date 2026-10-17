"""Provision reviewed CPU toolchains; no research inputs or provider credentials.

The base image is resolved before G3 approval. Every later runner uses that
digest and verifies the exact read-only toolchain file inventory. Downloading
dependencies is separate from the network-disabled scientific execution.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import urllib.request
from pathlib import Path

BASE_TAG = "python:3.10.21-bookworm"
LEAN_URL = "https://github.com/leanprover/lean4/releases/download/v4.35.0/lean-4.35.0-linux.tar.zst"
LEAN_SHA256 = "7289597a44543246c9227b8cae501767e095ce17f6d448b95fc4a8dc97268f6d"
PACKAGES = ["statsmodels==0.15.0", "numpy==2.2.6", "scipy==1.15.3", "pandas==2.2.3", "patsy==1.0.1",
            "packaging==25.0", "python-dateutil==2.9.0.post0", "pytz==2025.2", "tzdata==2025.2", "six==1.17.0"]
ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def definition(kind):
    if kind not in {"meta_analysis", "theory"}:
        raise ValueError("unsupported reviewed runtime")
    value = {"profile": kind, "base_tag": BASE_TAG, "packages": PACKAGES if kind == "meta_analysis" else [],
             "lean_url": LEAN_URL if kind == "theory" else None, "lean_sha256": LEAN_SHA256 if kind == "theory" else None}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def run(argv, timeout=900):
    from scripts.experiment_runner import safe_environment
    result = subprocess.run(argv, env=safe_environment("toolchain-setup", 0), check=False,
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("reviewed toolchain setup failed: " + (result.stdout + result.stderr)[-2000:])
    return result.stdout.strip()


def prepare(kind, binding=None):
    if os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1" and os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("study environment provisioning is cloud-only")
    expected_definition = definition(kind)
    if binding and (binding.get("profile") != kind or binding.get("definition_sha256") != expected_definition):
        raise ValueError("reviewed runtime definition changed after approval")
    image = binding["base_image"] if binding else BASE_TAG
    run(["docker", "pull", image], timeout=600)
    if not binding:
        images = json.loads(run(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image]))
        image = next((v for v in images if "@sha256:" in v), None)
        if not image:
            raise ValueError("runtime base image has no immutable publisher digest")
    cache_key = hashlib.sha256((expected_definition + image).encode()).hexdigest()
    directory = ROOT / ".cache" / "study-environments" / cache_key
    vendor, manifest_path = directory / "toolchain", directory / "manifest.json"
    vendor.mkdir(parents=True, exist_ok=True)
    if not manifest_path.is_file():
        if any(vendor.iterdir()):
            raise ValueError("partial toolchain setup needs inspection; never reuse an unverified installation")
        if kind == "meta_analysis":
            from scripts.experiment_runner import container_user
            run(["docker", "run", "--rm", "--user", container_user(), "--cap-drop=ALL",
                 "--security-opt", "no-new-privileges", "-e", "PYTHONDONTWRITEBYTECODE=1",
                 "-v", str(vendor.resolve()) + ":/vendor", image, "python3", "-m", "pip", "install",
                 "--disable-pip-version-check", "--no-input", "--no-compile", "--only-binary=:all:", "--no-deps", "--target", "/vendor", *PACKAGES])
        else:
            archive = directory / "lean.tar.zst"
            with urllib.request.urlopen(LEAN_URL, timeout=60) as response, archive.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if digest(archive) != LEAN_SHA256:
                raise ValueError("official Lean release checksum mismatch")
            run(["tar", "--zstd", "-xf", str(archive), "--strip-components=1", "-C", str(vendor)], timeout=180)
        files = {p.relative_to(vendor).as_posix(): digest(p) for p in sorted(vendor.rglob("*")) if p.is_file()}
        manifest = {"profile": kind, "definition_sha256": expected_definition, "base_image": image, "files": files}
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_files = {p.relative_to(vendor).as_posix(): digest(p) for p in sorted(vendor.rglob("*")) if p.is_file()}
    if manifest != {"profile": kind, "definition_sha256": expected_definition, "base_image": image, "files": actual_files}:
        raise ValueError("runtime toolchain files changed")
    result = {"profile": kind, "definition_sha256": expected_definition, "base_image": image,
              "environment_sha256": digest(manifest_path)}
    if binding and result != binding:
        raise ValueError("restored runtime differs from the exact G3-approved environment")
    return result, vendor
