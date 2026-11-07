#!/usr/bin/env python3
"""Audit authentic academic style without scoring or evading AI detectors."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.research_artifacts import schema_errors, write
    from scripts.ref_verify_adapter import canonical_manuscript as select_manuscript
    from scripts.manuscript_language import extract_text
    from scripts.venue_compliance import manuscript_tree_sha256
except ImportError:  # Direct execution from scripts/.
    from research_artifacts import schema_errors, write
    from ref_verify_adapter import canonical_manuscript as select_manuscript
    from manuscript_language import extract_text  # type: ignore
    from venue_compliance import manuscript_tree_sha256  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
PAPER_RE = re.compile(r"^P[0-9]{2}$")
WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
PROSELINT_CONFIG = ROOT / "config" / "proselint-academic.json"
STYLE_RULES_CONFIG = ROOT / "config" / "academic-style-rules.json"
PROSELINT_MAX_DIAGNOSTICS = 100
PROSELINT_TIMEOUT_SECONDS = 30
HARPER_MAX_DIAGNOSTICS = 100
HARPER_TIMEOUT_SECONDS = 30


class AcademicStyleError(RuntimeError):
    pass


def find_proselint() -> str | None:
    for candidate in (
        ROOT / ".venv" / "bin" / "proselint",
        ROOT / ".venv" / "Scripts" / "proselint.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("proselint")


def find_harper() -> str | None:
    for candidate in (
        ROOT / ".venv" / "bin" / "harper-cli",
        ROOT / ".venv" / "Scripts" / "harper-cli.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("harper-cli")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_manuscript(paper: Path) -> Path:
    return select_manuscript(paper, error_type=AcademicStyleError)


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"[ \t]+", " ", text).strip()
    return [item.strip() for item in SENTENCE_RE.split(compact) if item.strip()]


def _paragraphs(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", item).strip()
        for item in re.split(r"\n\s*\n", text)
        if len(WORD_RE.findall(item)) >= 15
    ]


def _normalized_sentence(sentence: str) -> str:
    return " ".join(word.lower() for word in WORD_RE.findall(sentence))


def load_style_rules(path: Path | None = None) -> dict[str, Any]:
    source = path or STYLE_RULES_CONFIG
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcademicStyleError(f"cannot load academic style rules: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        raise AcademicStyleError("academic style rules must use schema_version 1.0")
    if not isinstance(payload.get("sources"), list) or not isinstance(payload.get("rules"), list):
        raise AcademicStyleError("academic style rules must contain source and rule arrays")
    source_ids = {
        item.get("id") for item in payload["sources"] if isinstance(item, dict)
    }
    for item in payload["rules"]:
        if not isinstance(item, dict):
            raise AcademicStyleError("each academic style rule must be an object")
        required = {
            "id", "category", "confidence", "pattern",
            "message", "guidance", "source_ids",
        }
        if not required.issubset(item):
            raise AcademicStyleError(f"academic style rule is incomplete: {item.get('id')}")
        if item["confidence"] not in {"high", "moderate"}:
            raise AcademicStyleError(f"invalid rule confidence: {item['id']}")
        if not isinstance(item["source_ids"], list) or any(
            source_id not in source_ids for source_id in item["source_ids"]
        ):
            raise AcademicStyleError(f"academic style rule has an unknown source: {item['id']}")
        try:
            re.compile(str(item["pattern"]), re.I | re.M)
        except re.error as exc:
            raise AcademicStyleError(f"invalid academic style regex {item['id']}: {exc}") from exc
    return payload


def _line_and_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset)
    return line, offset - line_start


def _excerpt(text: str, start: int, end: int, limit: int = 220) -> str:
    left = max(0, text.rfind("\n", 0, start) + 1)
    right_index = text.find("\n", end)
    right = len(text) if right_index < 0 else right_index
    raw = text[left:right]
    compact = re.sub(r"\s+", " ", raw).strip()
    if len(compact) <= limit:
        return compact
    match_start = max(0, start - left)
    window_start = max(0, match_start - limit // 3)
    return re.sub(r"\s+", " ", raw[window_start:window_start + limit]).strip()


def analyze_text(text: str, *, ruleset: dict[str, Any] | None = None) -> dict[str, Any]:
    """Locate optional observations; word/phrase ratios never decide readiness."""
    words, sentences, paragraphs = WORD_RE.findall(text), _sentences(text), _paragraphs(text)
    findings, warnings, errors = [], [], []
    for rule in (ruleset or load_style_rules())["rules"]:
        matches = list(re.finditer(str(rule["pattern"]), text, re.I | re.M))
        if matches:
            warnings.append(rule["message"])
            if rule["category"] == "research_integrity":
                errors.append(rule["id"] + ": " + rule["message"])
        for match in matches[:20]:
            line, column = _line_and_column(text, match.start())
            findings.append({"rule_id": rule["id"], "category": rule["category"], "confidence": rule["confidence"],
                "severity": "error" if rule["category"] == "research_integrity" else "review", "line": line, "column": column, "matched_text": match.group(0)[:160],
                "excerpt": _excerpt(text, match.start(), match.end()), "message": rule["message"],
                "guidance": rule["guidance"], "source_ids": rule["source_ids"]})
    duplicates = [{"sentence": sentence[:300], "count": count} for sentence, count in
        Counter(_normalized_sentence(item) for item in sentences if len(WORD_RE.findall(item)) >= 10).most_common() if count > 1]
    if duplicates:
        warnings.append("Repeated substantial sentences need contextual review; scientific qualifiers may legitimately recur.")
    return {"word_count": len(words), "sentence_count": len(sentences), "paragraph_count": len(paragraphs),
        "formulaic_pattern_findings": findings, "formulaic_pattern_finding_count": len(findings),
        "duplicate_sentences": duplicates[:20], "errors": errors, "warnings": warnings}


def _pair(value):
    return isinstance(value, list) and len(value) == 2 and all(type(item) is int for item in value)


def _diagnostic(item: dict, *, harper: bool) -> dict:
    position = [item.get("line"), item.get("column")] if harper else item.get("pos")
    span = item.get("span")
    if harper:
        span = [span.get("char_start"), span.get("char_end")] if isinstance(span, dict) else None
    replacements = item.get("suggestions" if harper else "replacements")
    result = {
        "check": str(item.get("rule" if harper else "check_path", "unknown"))[:160],
        "message": str(item.get("message", ""))[:500],
        "line": position[0] if _pair(position) else None,
        "column": position[1] if _pair(position) else None,
        "span": span if _pair(span) else None,
        "replacements": [str(value)[:200] for value in replacements[:10]] if isinstance(replacements, list) else None,
    }
    if harper:
        result.update(kind=str(item.get("kind", "unknown"))[:80], matched_text=str(item.get("matched_text", ""))[:200])
    return result


def _run_linter(text: str, *, name: str, executable, runner) -> dict:
    """One bounded local CLI lifecycle; adapters only translate tool formats."""
    harper = name == "harper"
    command = executable or (find_harper() if harper else find_proselint())
    base = {
        "name": name,
        "source": "https://github.com/" + ("Automattic/harper" if harper else "amperser/proselint"),
        "license": "Apache-2.0" if harper else "BSD-3-Clause",
        "required": False, "local_only": True, "detector": False,
        "diagnostic_count": 0, "diagnostics": [], "available": bool(command),
    }
    if not command:
        return {**base, "status": "unavailable", "note": "Optional local prose linter is not installed; contextual observations remain available."}
    if not harper and not PROSELINT_CONFIG.is_file():
        return {**base, "status": "error", "note": "Repository proselint academic configuration is missing."}
    timeout = HARPER_TIMEOUT_SECONDS if harper else PROSELINT_TIMEOUT_SECONDS
    args = (["--no-color", "lint", "--format", "json"] if harper else
            ["check", "--output-format", "json", "--config", str(PROSELINT_CONFIG)])
    try:
        with tempfile.TemporaryDirectory(prefix=f"research-os-{name}-") as directory:
            source = Path(directory) / "manuscript.txt"
            source.write_text(text, encoding="utf-8")
            completed = runner([command, *args, str(source)], cwd=ROOT, capture_output=True,
                               text=True, encoding="utf-8", timeout=timeout, check=False)
        if completed.returncode not in (0, 1):
            raise ValueError(f"CLI exited with code {completed.returncode}")
        payload = json.loads(completed.stdout)
        files = payload if harper else payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(files, list if harper else dict):
            raise ValueError("Harper JSON must be an array" if harper else "proselint JSON is missing result")
        diagnostics, tool_errors = [], []
        for file in files if harper else files.values():
            if not isinstance(file, dict):
                continue
            if file.get("error"):
                tool_errors.append(str(file["error"])[:300])
            items = file.get("lints" if harper else "diagnostics")
            if isinstance(items, list):
                diagnostics.extend(_diagnostic(item, harper=harper) for item in items if isinstance(item, dict))
        diagnostics = diagnostics[:HARPER_MAX_DIAGNOSTICS if harper else PROSELINT_MAX_DIAGNOSTICS]
        return {**base, "status": "error" if tool_errors else "advisory" if diagnostics else "pass",
                "diagnostic_count": len(diagnostics), "diagnostics": diagnostics,
                "note": f"{name} reported an input error: {tool_errors[0]}" if tool_errors else
                        "Advisory local prose findings; preserve discipline-specific terms and warranted uncertainty."}
    except subprocess.TimeoutExpired:
        return {**base, "status": "error", "note": f"{name} exceeded the {timeout}-second timeout."}
    except (OSError, UnicodeError, ValueError) as exc:
        return {**base, "status": "error", "note": f"{name} could not be evaluated: {str(exc)[:300]}"}


def run_proselint(text: str, *, executable: str | None = None, runner: Any = subprocess.run) -> dict[str, Any]:
    return _run_linter(text, name="proselint", executable=executable, runner=runner)


def run_harper(text: str, *, executable: str | None = None, runner: Any = subprocess.run) -> dict[str, Any]:
    return _run_linter(text, name="harper", executable=executable, runner=runner)


def editorial_reviews(manuscript: Path, text: str) -> dict[str, Any]:
    """Cover every pinned editorial pattern; semantic judgement stays explicit."""
    from scripts import humanizer_review, defensive_review, ccfa_humanization

    raw = None
    if manuscript.suffix.lower() == ".tex":
        from scripts.citation_audit import tex_source_paths
        raw = "\n\n".join(path.read_text(encoding="utf-8") for path in sorted(tex_source_paths(manuscript)))
    return {
        "humanizer_review": humanizer_review.audit_text(text, raw_text=raw),
        "anti_defensive_review": defensive_review.audit_text(text, raw_text=raw),
        "ccfa_humanization_review": ccfa_humanization.audit_text(text, raw_text=raw),
    }


def build_audit(paper: Path) -> dict[str, Any]:
    errors: list[str] = []
    manuscript: Path | None = None
    analysis: dict[str, Any] = {
        "word_count": 0,
        "sentence_count": 0,
        "paragraph_count": 0,
        "errors": [],
        "warnings": [],
    }
    external_linters: list[dict[str, Any]] = []
    reviewed_rule_sources: list[dict[str, Any]] = []
    try:
        manuscript = canonical_manuscript(paper)
        text = extract_text(manuscript)
        ruleset = load_style_rules()
        reviewed_rule_sources = ruleset["sources"]
        analysis = analyze_text(text, ruleset=ruleset)
        analysis.update(editorial_reviews(manuscript, text))
        errors.extend(str(item) for item in analysis.get("errors", []))
        for external in (run_proselint(text), run_harper(text)):
            external_linters.append(external)
            if external.get("status") == "advisory":
                analysis["warnings"].append(
                    f"{external['name']} reported {external['diagnostic_count']} "
                    "advisory finding(s)"
                )
            elif external.get("status") == "error":
                analysis["warnings"].append(
                    str(external.get("note", f"{external['name']} failed"))
                )
    except (AcademicStyleError, OSError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "1.2",
        "created_at": now(),
        "status": "pass" if not errors else "revise",
        "purpose": "authentic_academic_style_and_readability",
        "detector_score_used": False,
        "detector_evasion_prohibited": True,
        "disclosure_must_be_preserved": True,
        "human_review_required": False,
        "manuscript": {
            "path": manuscript.relative_to(paper).as_posix() if manuscript else None,
            "source_tree_sha256": manuscript_tree_sha256(manuscript) if manuscript else None,
        },
        "analysis": analysis,
        "reviewed_rule_sources": reviewed_rule_sources,
        "external_linters": external_linters,
        "errors": errors,
        "warnings": [str(item) for item in analysis.get("warnings", [])],
        "note": (
            "Heuristic writing-quality audit only. It does not estimate human authorship, "
            "predict an AI detector, justify nondisclosure, or guarantee journal acceptance."
        ),
    }


def report_path(paper: Path) -> Path:
    return paper / "style" / "academic-style-audit.json"


def write_audit(project: Path, paper_id: str) -> tuple[Path, dict[str, Any]]:
    if not PAPER_RE.fullmatch(paper_id):
        raise AcademicStyleError("paper id must look like P01")
    paper = project / "papers" / paper_id
    if not paper.is_dir():
        raise AcademicStyleError(f"paper does not exist: {paper_id}")
    report = build_audit(paper)
    output = report_path(paper)
    write(output, report)
    return output, report


def validate_saved_audit(paper: Path) -> list[str]:
    path = report_path(paper)
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"missing academic style audit: {path}"]
    except json.JSONDecodeError as exc:
        return [f"invalid academic style audit: {exc}"]
    errors = schema_errors(report, "academic-style-audit.schema.json")
    if errors:
        return errors
    analysis = report["analysis"]
    if analysis["formulaic_pattern_finding_count"] != len(analysis["formulaic_pattern_findings"]):
        errors.append("academic style audit line-level finding count is inconsistent")
    try:
        expected_sources = {item["id"]: item["commit"] for item in load_style_rules()["sources"]}
        actual_sources = {item["id"]: item["commit"] for item in report["reviewed_rule_sources"]}
        if actual_sources != expected_sources or len(actual_sources) != len(report["reviewed_rule_sources"]):
            errors.append("academic style audit reviewed rule sources do not match the lock")
    except (AcademicStyleError, KeyError, TypeError) as exc:
        errors.append(f"academic style rule source validation failed: {exc}")
    expected_linters = {"proselint": ("https://github.com/amperser/proselint", "BSD-3-Clause"),
                        "harper": ("https://github.com/Automattic/harper", "Apache-2.0")}
    linters = report["external_linters"]
    if len(linters) != 2 or {row["name"]: (row["source"], row["license"]) for row in linters} != expected_linters:
        errors.append("academic style audit must record proselint and Harper with their original source/license")
    for row in linters:
        if row["diagnostic_count"] != len(row["diagnostics"]):
            errors.append("academic style audit external diagnostic count is inconsistent")
    if report["status"] != "pass" or report["errors"]:
        errors.append("academic style audit contains unresolved style errors")
    try:
        manuscript = canonical_manuscript(paper)
        current_hash = manuscript_tree_sha256(manuscript)
    except (AcademicStyleError, OSError, ValueError) as exc:
        errors.append(str(exc))
        return errors
    manuscript_record = report.get("manuscript")
    if not isinstance(manuscript_record, dict):
        errors.append("academic style audit manuscript record is missing")
    elif manuscript_record.get("source_tree_sha256") != current_hash:
        errors.append("academic style audit is stale for the manuscript source tree")
    try:
        expected_reviews = editorial_reviews(manuscript, extract_text(manuscript))
        for name, expected in expected_reviews.items():
            if not isinstance(analysis, dict) or analysis.get(name) != expected:
                errors.append(f"academic style audit {name} is missing, incomplete or stale")
    except (OSError, ValueError, ImportError) as exc:
        errors.append(f"complete editorial coverage could not be verified: {exc}")
    return errors


def _project_path(slug: str) -> Path:
    if not SLUG_RE.fullmatch(slug):
        raise AcademicStyleError("project must be a safe project slug")
    project = PROJECTS_ROOT / slug
    if not project.is_dir():
        raise AcademicStyleError(f"project does not exist: {slug}")
    return project


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit natural academic style without AI-detector scoring"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "validate"):
        command = sub.add_parser(name)
        command.add_argument("--project", required=True)
        command.add_argument("--paper", required=True)
    args = parser.parse_args()
    try:
        project = _project_path(args.project)
        if not PAPER_RE.fullmatch(args.paper):
            raise AcademicStyleError("paper id must look like P01")
        paper = project / "papers" / args.paper
        if args.command == "audit":
            path, report = write_audit(project, args.paper)
            print(
                json.dumps(
                    {"path": path.relative_to(project).as_posix(), **report},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0 if report["status"] == "pass" else 2
        errors = validate_saved_audit(paper)
        print(
            json.dumps(
                {"status": "pass" if not errors else "fail", "errors": errors},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if not errors else 2
    except AcademicStyleError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
