"""Isolated cloud DOCX rendering with exact image, input and output receipts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from scripts.research_artifacts import path_in, sha, write
from scripts import output_provenance
from scripts.experiment_runner import container_user
from scripts.live_acceptance import DEFAULT_IMAGE

RECIPE = (f"FROM {DEFAULT_IMAGE}\n"
          "RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-writer fonts-dejavu fonts-liberation "
          "&& dpkg-query -W > /opt/package-versions.txt && rm -rf /var/lib/apt/lists/*\n"
          "ENV HOME=/tmp\n")


def cloud():
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise RuntimeError("Word rendering requires an authorized cloud executor")
    if not shutil.which("docker"):
        raise RuntimeError("cloud Docker runtime required")


def environment():
    return {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "TZ"}}


def prepare_image() -> str:
    cloud()
    configured = os.environ.get("DR_OS_WORD_IMAGE")
    if configured:
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", configured):
            raise ValueError("DR_OS_WORD_IMAGE must be an exact locally prepared image ID")
        return configured
    recipe_hash = hashlib.sha256(RECIPE.encode()).hexdigest()
    tag = "research-word:" + recipe_hash[:20]
    inspected = subprocess.run(["docker", "image", "inspect", "--format={{.Id}}", tag],
                               capture_output=True, text=True, timeout=30, env=environment())
    if inspected.returncode:
        # Build context contains only the fixed recipe, never project data or keys.
        with tempfile.TemporaryDirectory(prefix="word-image-") as folder:
            Path(folder, "Dockerfile").write_text(RECIPE, encoding="utf-8")
            built = subprocess.run(["docker", "build", "--tag", tag, folder], capture_output=True,
                                   text=True, timeout=900, env=environment())
            if built.returncode:
                raise RuntimeError("Word runtime installation failed: " + (built.stdout + built.stderr)[-4000:])
        inspected = subprocess.run(["docker", "image", "inspect", "--format={{.Id}}", tag],
                                   capture_output=True, text=True, timeout=30, check=True, env=environment())
    image = inspected.stdout.strip()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise RuntimeError("Docker did not return an immutable image ID")
    return image


def check_docx(source: Path):
    if source.stat().st_size > 50_000_000:
        raise ValueError("Word input exceeds 50 MB")
    with zipfile.ZipFile(source) as package:
        if sum(i.file_size for i in package.infolist()) > 200_000_000:
            raise ValueError("expanded Word package exceeds 200 MB")
        if "word/document.xml" not in package.namelist():
            raise ValueError("invalid DOCX package")
        if any("vbaproject" in name.lower() or "embeddings/" in name.lower() for name in package.namelist()):
            raise ValueError("active embedded objects and macros are unsupported")


def render(project: Path, paper_id: str, source_relative: str | None = None) -> dict:
    cloud()
    if not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("invalid paper ID")
    source_relative = source_relative or f"papers/{paper_id}/manuscript/main.docx"
    if not source_relative.startswith(f"papers/{paper_id}/") or Path(source_relative).suffix.lower() != ".docx":
        raise ValueError("render source must be this paper's DOCX")
    source = path_in(project, source_relative)
    check_docx(source)
    output_provenance.require_final_origins(project, [source])
    image = prepare_image()
    before = sha(source)
    run_id = "word-" + uuid.uuid4().hex
    relative = f"reports/word-render/{paper_id}/{run_id}"
    directory = path_in(project, relative + "/receipt.json", exists=False).parent
    directory.mkdir(parents=True, exist_ok=False)
    command = ["docker", "run", "--rm", "--user", container_user(), "--network=none", "--read-only",
               "--cap-drop=ALL", "--pids-limit=256", "--cpus=2", "--memory=2g", "--security-opt=no-new-privileges",
               "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m", "--mount", f"type=bind,src={source.resolve()},dst=/input/main.docx,readonly",
               "--mount", f"type=bind,src={directory.resolve()},dst=/out", image,
               "libreoffice", "-env:UserInstallation=file:///tmp/lo-profile", "--headless", "--convert-to", "pdf:writer_pdf_Export",
               "--outdir", "/out", "/input/main.docx"]
    report = {"schema_version": "1.0", "status": "fail", "source_sha256": before,
              "inputs": [{"path": source_relative, "sha256": before}], "outputs": [],
              "image": image, "recipe_sha256": hashlib.sha256(RECIPE.encode()).hexdigest(),
              "renderer": {"name": "word_render", "implementation_sha256": sha(Path(__file__))},
              "execution": {"mode": "cloud", "receipt_id": run_id}, "network_disabled": True,
              "human_visual_review_required": True, "microsoft_word_pagination_equivalence_verified": False}
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=300, env=environment())
        report["log_tail"] = (result.stdout + result.stderr)[-12000:]
        pdf = directory / "main.pdf"
        if result.returncode or not pdf.is_file() or sha(source) != before:
            raise RuntimeError("Word conversion failed or source changed")
        metadata = subprocess.run(["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL",
                                   "--security-opt=no-new-privileges", image, "cat", "/opt/package-versions.txt"],
                                  capture_output=True, text=True, timeout=30, check=True, env=environment())
        package_versions = directory / "package-versions.txt"
        package_versions.write_text(metadata.stdout, encoding="utf-8")
        import fitz
        outputs = [pdf, package_versions]
        with fitz.open(pdf) as document:
            if not 1 <= len(document) <= 200:
                raise ValueError("Word PDF empty or exceeds 200 pages")
            pages = []
            for index, page in enumerate(document, 1):
                preview = directory / f"page-{index:03d}.png"
                page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).save(preview)
                outputs.append(preview)
                pages.append({"page": index, "width_pt": page.rect.width, "height_pt": page.rect.height,
                              "preview": preview.relative_to(project).as_posix(), "extracted_text": page.get_text()})
            report["pages"] = pages
        report.update(status="pass", inputs_unchanged=True,
                      outputs=[{"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in outputs])
        output_provenance.record_model_writes(project, outputs, family="other", provider="cloud-word-renderer",
            model=image, role="rendered-manuscript", run_id=run_id)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report["error"] = str(exc)
    receipt = directory / "receipt.json"
    write(receipt, report)
    output_provenance.record_model_writes(project, [receipt], family="other", provider="cloud-word-renderer",
        model=image, role="render-receipt", run_id=run_id)
    if report["status"] != "pass":
        raise RuntimeError("Word rendering failed; preserved receipt: " + receipt.relative_to(project).as_posix())
    # Index only the actual canonical manuscript. Revision previews are not canonical pages.
    if source_relative == f"papers/{paper_id}/manuscript/main.docx":
        paper = project / "papers" / paper_id
        final = path_in(project, f"papers/{paper_id}/manuscript/main.pdf", exists=False)
        shutil.copyfile(directory / "main.pdf", final)
        report["outputs"].append({"path": final.relative_to(project).as_posix(), "sha256": sha(final)})
        canonical_receipt = path_in(project, f"papers/{paper_id}/reviews/cloud-word-build.json", exists=False)
        write(canonical_receipt, report)
        output_provenance.record_model_writes(project, [final], family="other", provider="cloud-word-renderer",
            model=image, role="compiled-manuscript", run_id=run_id)
        output_provenance.record_model_writes(project, [canonical_receipt], family="other", provider="cloud-word-renderer",
            model=image, role="render-receipt", run_id=run_id)
        from scripts.revision_render import build_render_manifest
        build_render_manifest(paper, final, "word_render", image, rendering_receipt=canonical_receipt)
    return {**report, "receipt": receipt.relative_to(project).as_posix()}
