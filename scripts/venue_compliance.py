#!/usr/bin/env python3
"""Verify template integrity, manuscript basics and a safe local LaTeX build."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

try:
    from scripts import output_provenance
except ImportError:
    import output_provenance  # type: ignore


MAX_LOG_CHARS = 200_000
PLACEHOLDER_RE = re.compile(
    r"(?i)(?:\bTODO\b|\bFIXME\b|\bTBD\b|\[CITATION(?: NEEDED)?\]|\?\?+|XX_PLACEHOLDER_XX)"
)


class ComplianceError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ComplianceError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ComplianceError(f"Expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manuscript_tree_sha256(manuscript: Path) -> str:
    digest=hashlib.sha256();root=manuscript.parent
    files=sorted(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())
    for path in files:
        relative=path.relative_to(root).as_posix();digest.update(relative.encode());digest.update(b"\0");digest.update(path.read_bytes());digest.update(b"\0")
    return digest.hexdigest()


def audit_template(template_dir: Path) -> dict[str, Any]:
    inventory_path = template_dir / "template-inventory.json"
    inventory = read_json(inventory_path)
    expected = inventory.get("extracted_file_sha256")
    if not isinstance(expected, dict) or not expected:
        raise ComplianceError("Template inventory contains no extracted file hashes")
    changed: list[str] = []
    missing: list[str] = []
    for relative, checksum in expected.items():
        if not isinstance(relative, str) or not isinstance(checksum, str):
            raise ComplianceError("Template inventory paths and hashes must be strings")
        root = template_dir.resolve()
        path = (template_dir / relative).resolve()
        if path == root or root not in path.parents:
            raise ComplianceError(f"Template inventory path escapes its directory: {relative}")
        if not path.is_file():
            missing.append(relative)
        elif sha256_file(path) != checksum:
            changed.append(relative)
    extra = sorted(
        path.relative_to(template_dir).as_posix()
        for path in template_dir.rglob("*")
        if path.is_file()
        and path.name != "template-inventory.json"
        and path.relative_to(template_dir).as_posix() not in expected
    )
    return {
        "status": "pass" if not missing and not changed else "fail",
        "inventory": str(inventory_path),
        "archive_sha256": inventory.get("archive_sha256"),
        "verified_files": len(expected) - len(missing) - len(changed),
        "missing": missing,
        "changed": changed,
        "extra_untracked": extra,
    }


def latex_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)(?<!\\)%.*$", " ", text)
    text = re.sub(r"\\(?:cite|ref|label|includegraphics)\*?(?:\[[^]]*\])?\{[^}]*\}", " ", text)
    text = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^]]*\])?", " ", text)
    return re.sub(r"[{}~]", " ", text)


def docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise ComplianceError(f"Cannot read DOCX manuscript: {exc}") from exc
    root = ElementTree.fromstring(xml)
    return " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))


def inspect_manuscript(paper_dir: Path, venue: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    tex = paper_dir / "manuscript" / "main.tex"
    docx = paper_dir / "manuscript" / "main.docx"
    if tex.is_file() and docx.is_file():
        raise ComplianceError("Both main.tex and main.docx exist; choose one canonical source")
    if tex.is_file():
        manuscript = tex
        text = latex_text(tex)
        format_name = "latex"
    elif docx.is_file():
        manuscript = docx
        text = docx_text(docx)
        format_name = "docx"
    else:
        raise ComplianceError("Manuscript main.tex or main.docx is required")
    normalized = " ".join(text.split())
    lower = normalized.lower()
    required_sections = ["abstract", "introduction"]
    missing_sections = [section for section in required_sections if section not in lower]
    placeholders = sorted(set(match.group(0) for match in PLACEHOLDER_RE.finditer(normalized)))
    words = re.findall(r"\b[\w'-]+\b", normalized, flags=re.UNICODE)
    maximum = venue.get("requirements", {}).get("original_article_max_word_equivalents")
    over_limit = isinstance(maximum, int) and len(words) > maximum
    return (
        {
            "status": "pass" if not missing_sections and not placeholders and not over_limit else "fail",
            "path": str(manuscript),
            "sha256": sha256_file(manuscript),
            "source_tree_sha256": manuscript_tree_sha256(manuscript),
            "format": format_name,
            "word_equivalent_estimate": len(words),
            "configured_maximum": maximum,
            "over_configured_maximum": over_limit,
            "required_sections": required_sections,
            "missing_sections": missing_sections,
            "unresolved_placeholders": placeholders,
            "note": "Word-equivalent count is an automated estimate; the publisher definition controls.",
        },
        manuscript,
    )


def compile_latex(manuscript: Path, timeout: int, no_compile: bool) -> dict[str, Any]:
    if manuscript.suffix.lower() != ".tex":
        return {"status": "not_applicable", "reason": "canonical source is DOCX"}
    latexmk = shutil.which("latexmk")
    if no_compile:
        return {"status": "not_requested", "reason": "--no-compile was supplied"}
    if not latexmk:
        return {
            "status": "skipped_tool_missing",
            "reason": "latexmk is not installed; human PDF inspection remains required",
        }
    build = manuscript.parent.parent / "build"
    build.mkdir(parents=True, exist_ok=True)
    command = [
        latexmk,
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        f"-outdir={build}",
        "-pdflatex=pdflatex -no-shell-escape %O %S",
        manuscript.name,
    ]
    try:
        allowed_environment = {
            key: value
            for key, value in os.environ.items()
            if key
            in {
                "PATH",
                "LANG",
                "LC_ALL",
                "TZ",
                "TMPDIR",
                "HOME",
                "TEXMFHOME",
                "TEXMFVAR",
                "TEXMFCONFIG",
            }
        }
        result = subprocess.run(
            command,
            cwd=manuscript.parent,
            env=allowed_environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        output = (result.stdout + "\n" + result.stderr)[-MAX_LOG_CHARS:]
        pdf = build / f"{manuscript.stem}.pdf"
        status = "pass" if result.returncode == 0 and pdf.is_file() else "fail"
        return {
            "status": status,
            "exit_code": result.returncode,
            "command": command,
            "pdf": str(pdf) if pdf.is_file() else None,
            "pdf_sha256": sha256_file(pdf) if pdf.is_file() else None,
            "log_tail": output,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "fail", "error": str(exc), "command": command}


def compliance_report(paper_dir: Path, timeout: int = 180, no_compile: bool = False) -> dict[str, Any]:
    venue = read_json(paper_dir / "venue.json")
    template = audit_template(paper_dir / "venue-template")
    manuscript, manuscript_path = inspect_manuscript(paper_dir, venue)
    compile_result = compile_latex(manuscript_path, timeout, no_compile)
    allowed_compile = {"pass", "not_applicable", "skipped_tool_missing"}
    status = (
        "pass"
        if template["status"] == manuscript["status"] == "pass"
        and compile_result["status"] in allowed_compile
        else "fail"
    )
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "paper_id": paper_dir.name,
        "venue_id": venue.get("venue_id"),
        "venue_sha256": sha256_file(paper_dir / "venue.json"),
        "status": status,
        "template": template,
        "manuscript": manuscript,
        "compile": compile_result,
        "human_checks_remaining": [
            "Inspect the final PDF or DOCX visually.",
            "Re-check current official venue policies and portal fields.",
            "Confirm authorship, ethics, conflicts, funding and AI-use disclosures."
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paper_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--no-compile", action="store_true")
    args = parser.parse_args()
    try:
        if args.timeout <= 0:
            raise ComplianceError("--timeout must be positive")
        report = compliance_report(args.paper_dir, args.timeout, args.no_compile)
        output = args.output or args.paper_dir / "reviews" / "venue-compliance.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        compile_info=report.get("compile") if isinstance(report.get("compile"),dict) else {}
        pdf_value=compile_info.get("pdf")
        if compile_info.get("status")=="pass" and isinstance(pdf_value,str):
            pdf=Path(pdf_value)
            if not pdf.is_absolute():pdf=args.paper_dir/pdf
            project=args.paper_dir.parent.parent
            output_provenance.record_model_writes(project,[pdf],family="other",provider="latexmk-local",model="latexmk",role="compiled-manuscript",run_id="venue-"+now().replace(":","-"))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1
    except (ComplianceError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
