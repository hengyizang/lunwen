#!/usr/bin/env python3
"""Audit authentic academic style without scoring or evading AI detectors."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import statistics
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.manuscript_language import extract_text
    from scripts.venue_compliance import manuscript_tree_sha256
except ImportError:  # Direct execution from scripts/.
    from manuscript_language import extract_text  # type: ignore
    from venue_compliance import manuscript_tree_sha256  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
PAPER_RE = re.compile(r"^P[0-9]{2}$")
WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
STOCK_PATTERNS = {
    "rapidly evolving framing": re.compile(
        r"\bin (?:today['’]s|the) rapidly evolving (?:world|landscape|field)\b",
        re.I,
    ),
    "importance announcement": re.compile(
        r"\bit (?:is|should be) (?:important|crucial) to note that\b", re.I
    ),
    "crucial-role formula": re.compile(r"\bplays? a (?:crucial|pivotal|vital) role\b", re.I),
    "delve formula": re.compile(r"\bdelv(?:e|es|ed|ing) into\b", re.I),
    "shed-light formula": re.compile(r"\bshed(?:s|ding)? light on\b", re.I),
    "pave-the-way formula": re.compile(r"\bpav(?:e|es|ed|ing) the way\b", re.I),
    "realm formula": re.compile(r"\bin the realm of\b", re.I),
    "testament formula": re.compile(r"\b(?:is|serves as) a testament to\b", re.I),
    "unlock-potential formula": re.compile(r"\bunlock(?:s|ed|ing)? the potential\b", re.I),
    "underscore-importance formula": re.compile(
        r"\bunderscor(?:e|es|ed|ing) the importance of\b", re.I
    ),
    "comprehensive-understanding formula": re.compile(
        r"\b(?:gain|provide|provides|offering) a comprehensive understanding of\b",
        re.I,
    ),
    "ever-evolving formula": re.compile(r"\bever-evolving\b", re.I),
}
TRANSITION_OPENERS = {
    "additionally",
    "consequently",
    "furthermore",
    "importantly",
    "moreover",
    "nevertheless",
    "notably",
    "overall",
    "therefore",
}
PROSELINT_CONFIG = ROOT / "config" / "proselint-academic.json"
PROSELINT_MAX_DIAGNOSTICS = 100
PROSELINT_TIMEOUT_SECONDS = 30


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


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_manuscript(paper: Path) -> Path:
    candidates = [
        path
        for path in (
            paper / "manuscript" / "main.tex",
            paper / "manuscript" / "main.docx",
        )
        if path.is_file() and not path.is_symlink()
    ]
    if len(candidates) != 1:
        raise AcademicStyleError(
            "exactly one canonical manuscript/main.tex or manuscript/main.docx is required"
        )
    return candidates[0]


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


def _coefficient_of_variation(values: list[int]) -> float | None:
    if len(values) < 2 or not statistics.mean(values):
        return None
    return statistics.pstdev(values) / statistics.mean(values)


def analyze_text(text: str) -> dict[str, Any]:
    words = WORD_RE.findall(text)
    sentences = _sentences(text)
    sentence_lengths = [len(WORD_RE.findall(item)) for item in sentences]
    paragraphs = _paragraphs(text)
    paragraph_lengths = [len(WORD_RE.findall(item)) for item in paragraphs]
    errors: list[str] = []
    warnings: list[str] = []

    stock_hits: list[dict[str, Any]] = []
    for label, pattern in STOCK_PATTERNS.items():
        matches = [match.group(0) for match in pattern.finditer(text)]
        if matches:
            stock_hits.append({"pattern": label, "count": len(matches), "examples": matches[:3]})
    stock_count = sum(int(item["count"]) for item in stock_hits)
    stock_limit = max(2, math.ceil(len(words) / 1000))
    if stock_count > stock_limit:
        errors.append(
            f"template phrase count {stock_count} exceeds the manuscript-size limit {stock_limit}"
        )
    elif stock_count:
        warnings.append(
            f"review {stock_count} stock academic phrase occurrence(s) in context"
        )

    normalized = [_normalized_sentence(item) for item in sentences]
    duplicate_sentences = [
        {"sentence": sentence[:300], "count": count}
        for sentence, count in Counter(
            item for item in normalized if len(item.split()) >= 10
        ).most_common()
        if count > 1
    ]
    if duplicate_sentences:
        errors.append("one or more substantial sentences are repeated verbatim")

    openings = Counter(
        " ".join(item.split()[:3])
        for item in normalized
        if len(item.split()) >= 8
    )
    repeated_openings = [
        {"opening": opening, "count": count}
        for opening, count in openings.most_common()
        if count >= 4 and count / max(1, len(sentences)) > 0.10
    ]
    if repeated_openings:
        errors.append("sentence openings are mechanically repeated")

    transition_counts: Counter[str] = Counter()
    for sentence in normalized:
        if not sentence:
            continue
        opener = sentence.split()[0]
        if opener in TRANSITION_OPENERS:
            transition_counts[opener] += 1
    transition_total = sum(transition_counts.values())
    transition_ratio = transition_total / max(1, len(sentences))
    if len(sentences) >= 10 and transition_ratio > 0.15:
        errors.append(
            f"sentence-initial transition ratio {transition_ratio:.3f} exceeds 0.150"
        )

    long_count = sum(length > 45 for length in sentence_lengths)
    short_count = sum(0 < length < 6 for length in sentence_lengths)
    long_ratio = long_count / max(1, len(sentence_lengths))
    short_ratio = short_count / max(1, len(sentence_lengths))
    if len(sentences) >= 10 and long_ratio > 0.15:
        errors.append(f"very-long-sentence ratio {long_ratio:.3f} exceeds 0.150")
    if len(sentences) >= 10 and short_ratio > 0.20:
        warnings.append(f"very-short-sentence ratio is {short_ratio:.3f}")

    sentence_cv = _coefficient_of_variation(sentence_lengths)
    paragraph_cv = _coefficient_of_variation(paragraph_lengths)
    if len(sentences) >= 20 and sentence_cv is not None and sentence_cv < 0.22:
        warnings.append("sentence lengths are unusually uniform; inspect cadence manually")
    if len(paragraphs) >= 6 and paragraph_cv is not None and paragraph_cv < 0.18:
        warnings.append("paragraph lengths are unusually uniform; inspect argument structure")
    if len(words) < 500:
        errors.append("fewer than 500 English words were available for a meaningful style audit")

    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "sentence_length": {
            "mean": round(statistics.mean(sentence_lengths), 3) if sentence_lengths else 0,
            "coefficient_of_variation": round(sentence_cv, 3) if sentence_cv is not None else None,
            "very_long_count": long_count,
            "very_long_ratio": round(long_ratio, 6),
            "very_short_count": short_count,
            "very_short_ratio": round(short_ratio, 6),
        },
        "paragraph_length_coefficient_of_variation": (
            round(paragraph_cv, 3) if paragraph_cv is not None else None
        ),
        "stock_phrase_hits": stock_hits,
        "stock_phrase_limit": stock_limit,
        "duplicate_sentences": duplicate_sentences[:20],
        "repeated_sentence_openings": repeated_openings[:20],
        "transition_openers": dict(sorted(transition_counts.items())),
        "transition_opener_ratio": round(transition_ratio, 6),
        "errors": errors,
        "warnings": warnings,
    }


def run_proselint(
    text: str,
    *,
    executable: str | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Run the optional local proselint CLI over extracted plain text.

    The linter is advisory: general-purpose prose rules can conflict with
    discipline-specific terminology and legitimate scientific uncertainty.
    """

    command = executable or find_proselint()
    base: dict[str, Any] = {
        "name": "proselint",
        "source": "https://github.com/amperser/proselint",
        "license": "BSD-3-Clause",
        "required": False,
        "local_only": True,
        "detector": False,
        "diagnostic_count": 0,
        "diagnostics": [],
    }
    if not command:
        return {
            **base,
            "available": False,
            "status": "unavailable",
            "note": (
                "Optional local prose linter not installed; the deterministic "
                "academic-style gate still ran."
            ),
        }
    if not PROSELINT_CONFIG.is_file():
        return {
            **base,
            "available": True,
            "status": "error",
            "note": "Repository proselint academic configuration is missing.",
        }

    try:
        with tempfile.TemporaryDirectory(prefix="research-os-proselint-") as directory:
            source = Path(directory) / "manuscript.txt"
            source.write_text(text, encoding="utf-8")
            completed = runner(
                [
                    command,
                    "check",
                    "--output-format",
                    "json",
                    "--config",
                    str(PROSELINT_CONFIG),
                    str(source),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=PROSELINT_TIMEOUT_SECONDS,
                check=False,
            )
        payload = json.loads(completed.stdout or "{}")
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ValueError("proselint JSON is missing result")
        diagnostics: list[dict[str, Any]] = []
        for file_result in result.values():
            if not isinstance(file_result, dict):
                continue
            raw_diagnostics = file_result.get("diagnostics")
            if not isinstance(raw_diagnostics, list):
                continue
            for item in raw_diagnostics:
                if not isinstance(item, dict):
                    continue
                position = item.get("pos")
                span = item.get("span")
                replacements = item.get("replacements")
                diagnostics.append(
                    {
                        "check": str(item.get("check_path", "unknown"))[:160],
                        "message": str(item.get("message", ""))[:500],
                        "line": (
                            position[0]
                            if isinstance(position, list)
                            and len(position) == 2
                            and isinstance(position[0], int)
                            else None
                        ),
                        "column": (
                            position[1]
                            if isinstance(position, list)
                            and len(position) == 2
                            and isinstance(position[1], int)
                            else None
                        ),
                        "span": (
                            span
                            if isinstance(span, list)
                            and len(span) == 2
                            and all(isinstance(value, int) for value in span)
                            else None
                        ),
                        "replacements": (
                            [str(value)[:200] for value in replacements[:10]]
                            if isinstance(replacements, list)
                            else None
                        ),
                    }
                )
        diagnostics = diagnostics[:PROSELINT_MAX_DIAGNOSTICS]
        return {
            **base,
            "available": True,
            "status": "advisory" if diagnostics else "pass",
            "diagnostic_count": len(diagnostics),
            "diagnostics": diagnostics,
            "note": (
                "Advisory local prose findings; review in scientific context and "
                "do not erase warranted uncertainty."
            ),
        }
    except subprocess.TimeoutExpired:
        return {
            **base,
            "available": True,
            "status": "error",
            "note": f"proselint exceeded the {PROSELINT_TIMEOUT_SECONDS}-second timeout.",
        }
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            **base,
            "available": True,
            "status": "error",
            "note": f"proselint could not be evaluated: {str(exc)[:300]}",
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
    try:
        manuscript = canonical_manuscript(paper)
        text = extract_text(manuscript)
        analysis = analyze_text(text)
        errors.extend(str(item) for item in analysis.get("errors", []))
        external = run_proselint(text)
        external_linters.append(external)
        if external.get("status") == "advisory":
            analysis["warnings"].append(
                f"proselint reported {external['diagnostic_count']} advisory finding(s)"
            )
        elif external.get("status") == "error":
            analysis["warnings"].append(str(external.get("note", "proselint failed")))
    except (AcademicStyleError, OSError, ValueError) as exc:
        errors.append(str(exc))
    return {
        "schema_version": "1.1",
        "created_at": now(),
        "status": "pass" if not errors else "revise",
        "purpose": "authentic_academic_style_and_readability",
        "detector_score_used": False,
        "detector_evasion_prohibited": True,
        "disclosure_must_be_preserved": True,
        "human_review_required": True,
        "manuscript": {
            "path": manuscript.relative_to(paper).as_posix() if manuscript else None,
            "source_tree_sha256": manuscript_tree_sha256(manuscript) if manuscript else None,
        },
        "analysis": analysis,
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
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output.parent, delete=False
    ) as handle:
        handle.write(payload)
        temporary = handle.name
    Path(temporary).replace(output)
    return output, report


def validate_saved_audit(paper: Path) -> list[str]:
    path = report_path(paper)
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"missing academic style audit: {path}"]
    except json.JSONDecodeError as exc:
        return [f"invalid academic style audit: {exc}"]
    if not isinstance(report, dict):
        return ["academic style audit must be a JSON object"]
    errors: list[str] = []
    if report.get("schema_version") != "1.1":
        errors.append("academic style audit schema_version must be 1.1")
    if report.get("purpose") != "authentic_academic_style_and_readability":
        errors.append("academic style audit has an invalid purpose")
    if report.get("detector_score_used") is not False:
        errors.append("academic style audit must not use an AI-detector score")
    if report.get("detector_evasion_prohibited") is not True:
        errors.append("academic style audit must prohibit detector evasion")
    if report.get("disclosure_must_be_preserved") is not True:
        errors.append("academic style audit must preserve AI-use disclosure")
    if report.get("human_review_required") is not True:
        errors.append("academic style audit must require human review")
    external_linters = report.get("external_linters")
    if not isinstance(external_linters, list):
        errors.append("academic style audit external_linters must be an array")
    else:
        for linter in external_linters:
            if not isinstance(linter, dict):
                errors.append("academic style audit has an invalid external linter record")
                continue
            if linter.get("detector") is not False or linter.get("local_only") is not True:
                errors.append("external writing checks must be local and must not be AI detectors")
    if report.get("status") != "pass":
        errors.append("academic style audit must pass")
    stored_errors = report.get("errors")
    if not isinstance(stored_errors, list) or stored_errors:
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
