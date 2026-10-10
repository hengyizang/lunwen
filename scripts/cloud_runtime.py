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
    from scripts.cloud_retry import run
    result = run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                  ".[figures,reader,research-quality,reference-tools]"], cwd=ROOT,
                 operation="pinned-runtime-install", receipt=project / "state/cloud-retry.jsonl", timeout=300)
    if result.returncode:
        from scripts.cloud_retry import redact
        raise RuntimeError("declared cloud dependencies could not be installed; inspect the pinned package environment\n"
                           + redact((result.stdout + result.stderr)[-3000:]))
    report = {"schema_version": "1.0", "python": platform.python_version(), "platform": platform.platform(),
              "versions": {package: importlib.metadata.version(package) for package in PACKAGES},
              "docker_available": bool(shutil.which("docker")), "disk_free_bytes": shutil.disk_usage(project).free,
              "cpu_count": os.cpu_count(), "experiment_limits": {"cpus": 2, "memory_gb": 4, "timeout_seconds_per_run": 1200},
              "model_credentials_in_experiment_environment": False}
    write(project / "state/cloud-runtime.json", report)
    return report


def compile_tex(project: Path, paper_id: str) -> dict:
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise RuntimeError("TeX rendering requires an authorized cloud executor")
    if not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("invalid paper ID")
    paper = path_in(project, f"papers/{paper_id}")
    source = paper / "manuscript/main.tex"
    if not source.is_file() or not shutil.which("docker"):
        raise RuntimeError("TeX source and the cloud Docker runtime are required")
    output_provenance.require_final_origins(project, [source])
    # Bind actual mounted research inputs, including includes and figures.
    inputs = [{"path": item.relative_to(project).as_posix(), "sha256": sha(item)}
              for directory in ("manuscript", "figures", "tables", "supplement")
              for item in sorted((paper / directory).rglob("*"))
              if item.is_file() and item != paper / "manuscript/main.pdf"]
    if any(path_in(project, item["path"]).is_symlink() for item in inputs):
        raise RuntimeError("render inputs cannot be symlinks")
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
    inputs_unchanged = all(path_in(project, item["path"]).is_file()
                           and sha(path_in(project, item["path"])) == item["sha256"] for item in inputs)
    report = {"schema_version": "1.0", "status": "pass" if result.returncode == 0 and pdf.is_file() and inputs_unchanged else "fail",
              "source_sha256": sha(source), "image": image, "network_disabled": True,
              "inputs": inputs, "inputs_unchanged": inputs_unchanged,
              "renderer": {"name": "cloud_runtime", "implementation_sha256": sha(Path(__file__))},
              "execution": {"mode": "cloud", "receipt_id": "tex-" + str(os.environ.get("GITHUB_RUN_ID") or os.environ.get("DR_OS_CLOUD_RUN_ID") or "authorized-cloud") + "-" + sha(source)[:16]},
              "log_tail": (result.stdout + result.stderr)[-20000:], "human_visual_review_required": True}
    if report["status"] == "pass":
        final = paper / "manuscript/main.pdf"
        shutil.copyfile(pdf, final)
        report.update(pdf=final.relative_to(project).as_posix(), pdf_sha256=sha(final))
        report["outputs"] = [{"path": report["pdf"], "sha256": report["pdf_sha256"]}]
        output_provenance.record_model_writes(project, [final], family="other", provider="cloud-tex-renderer",
            model=image, role="compiled-manuscript", run_id="tex-" + report["source_sha256"][:16])
    write(paper / "reviews/cloud-tex-build.json", report)
    if report["status"] != "pass":
        raise RuntimeError("TeX compilation failed; inspect the preserved cloud-tex-build.json")
    output_provenance.record_model_writes(project, [paper / "reviews/cloud-tex-build.json"],
        family="other", provider="cloud-tex-renderer", model=image, role="render-receipt",
        run_id=report["execution"]["receipt_id"])
    from scripts.revision_render import build_render_manifest
    build_render_manifest(paper, final, "cloud_runtime", image,
                          rendering_receipt=paper / "reviews/cloud-tex-build.json")
    return report
