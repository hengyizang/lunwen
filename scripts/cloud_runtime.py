"""Provision the declared cloud toolchain and compile TeX without host secrets."""
from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.cloud_research_steps import path_in, write
from scripts import output_provenance
from scripts.cloud_checkpoint import sha
from scripts.experiment_runner import container_user

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("matplotlib", "numpy", "pandas", "PyMuPDF", "pypdf", "python-docx", "python-pptx", "statsmodels", "ref-verify")
# Publisher's linux/amd64 digest, inspected 2026-10-01:
# https://github.com/xu-cheng/latex-docker/pkgs/container/texlive-small
DEFAULT_TEX_IMAGE = "ghcr.io/xu-cheng/texlive-small@sha256:f6a08603f17dcc949352829fee6109c7e319429718b5e630a0fa32ee9006f98a"


def prepare(project: Path) -> dict:
    result = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                             ".[figures,reader,research-quality,reference-tools]"], cwd=ROOT,
                            capture_output=True, text=True, timeout=900, check=False)
    if result.returncode:
        raise RuntimeError("declared cloud dependencies could not be installed; inspect the pinned package environment")
    report = {"schema_version": "1.0", "python": platform.python_version(), "platform": platform.platform(),
              "versions": {package: importlib.metadata.version(package) for package in PACKAGES},
              "docker_available": bool(shutil.which("docker")), "disk_free_bytes": shutil.disk_usage(project).free,
              "cpu_count": os.cpu_count(), "experiment_limits": {"cpus": 2, "memory_gb": 4, "timeout_seconds_per_run": 1200},
              "model_credentials_in_experiment_environment": False}
    write(project / "state/cloud-runtime.json", report)
    return report


def compile_tex(project: Path, paper_id: str) -> dict:
    if not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("invalid paper ID")
    paper = path_in(project, f"papers/{paper_id}")
    source = paper / "manuscript/main.tex"
    if not source.is_file() or not shutil.which("docker"):
        raise RuntimeError("TeX source and the cloud Docker runtime are required")
    output_provenance.require_final_origins(project, [source])
    # This variable is a reviewed digest, never a model-proposed shell command.
    image = os.environ.get("DR_OS_TEX_IMAGE") or DEFAULT_TEX_IMAGE
    if not re.fullmatch(r"ghcr\.io/xu-cheng/texlive-(?:small|full)@sha256:[a-f0-9]{64}", image):
        raise RuntimeError("configure DR_OS_TEX_IMAGE with a verified xu-cheng TeX Live image digest, or use the native DOCX path")
    build = paper / "build"
    build.mkdir(exist_ok=True)
    command = ["docker", "run", "--rm", "--user", container_user(), "--network=none", "--read-only", "--cap-drop=ALL", "--pids-limit=256",
               "--cpus=2", "--memory=4g", "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
               "--mount", f"type=bind,src={paper.resolve()},dst=/paper,readonly",
               "--mount", f"type=bind,src={build.resolve()},dst=/out", "-w", "/paper/manuscript",
               "-e", "TEXMFVAR=/tmp/texmf-var", "-e", "TEXMFCONFIG=/tmp/texmf-config", image,
               "latexmk", "-norc", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-outdir=/out",
               "-pdflatex=pdflatex -no-shell-escape %O %S", "main.tex"]
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "TZ"}}
    result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False, env=env)
    pdf = build / "main.pdf"
    report = {"schema_version": "1.0", "status": "pass" if result.returncode == 0 and pdf.is_file() else "fail",
              "source_sha256": sha(source), "image": image, "network_disabled": True,
              "log_tail": (result.stdout + result.stderr)[-20000:], "human_visual_review_required": True}
    if report["status"] == "pass":
        final = paper / "manuscript/main.pdf"
        shutil.copyfile(pdf, final)
        report.update(pdf=final.relative_to(project).as_posix(), pdf_sha256=sha(final))
        output_provenance.record_model_writes(project, [final], family="other", provider="cloud-tex-renderer",
            model=image, role="compiled-manuscript", run_id="tex-" + report["source_sha256"][:16])
    write(paper / "reviews/cloud-tex-build.json", report)
    if report["status"] != "pass":
        raise RuntimeError("TeX compilation failed; inspect the preserved cloud-tex-build.json")
    return report
