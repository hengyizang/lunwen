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
            "id", "category", "confidence", "block_on_any", "pattern",
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


def _review_formulaic_patterns(
    text: str, word_count: int, ruleset: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    high_confidence_count = 0
    for rule in ruleset["rules"]:
        pattern = re.compile(str(rule["pattern"]), re.I | re.M)
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        if rule["confidence"] == "high":
            high_confidence_count += len(matches)
        for match in matches[:20]:
            line, column = _line_and_column(text, match.start())
            findings.append(
                {
                    "rule_id": rule["id"],
                    "category": rule["category"],
                    "confidence": rule["confidence"],
                    "severity": "error" if rule["block_on_any"] else "review",
                    "line": line,
                    "column": column,
                    "matched_text": match.group(0)[:160],
                    "excerpt": _excerpt(text, match.start(), match.end()),
                    "message": rule["message"],
                    "guidance": rule["guidance"],
                    "source_ids": rule["source_ids"],
                }
            )
        if rule["block_on_any"]:
            errors.append(
                f"rule {rule['id']} found {len(matches)} journal-inappropriate occurrence(s)"
            )

    density = max(
        int(ruleset.get("high_confidence_minimum_before_block", 3)),
        math.ceil(word_count / 1000)
        * int(ruleset.get("high_confidence_density_per_1000_words", 2)),
    )
    if high_confidence_count >= density:
        errors.append(
            f"high-confidence formulaic pattern count {high_confidence_count} "
            f"meets or exceeds the manuscript-size limit {density}"
        )
    elif findings:
        warnings.append(
            f"review {len(findings)} line-level formulaic or claim-calibration finding(s)"
        )
    return findings[:200], errors, warnings


def analyze_text(text: str, *, ruleset: dict[str, Any] | None = None) -> dict[str, Any]:
    words = WORD_RE.findall(text)
    sentences = _sentences(text)
    sentence_lengths = [len(WORD_RE.findall(item)) for item in sentences]
    paragraphs = _paragraphs(text)
    paragraph_lengths = [len(WORD_RE.findall(item)) for item in paragraphs]
    errors: list[str] = []
    warnings: list[str] = []

    configured_rules = ruleset or load_style_rules()
    pattern_findings, pattern_errors, pattern_warnings = _review_formulaic_patterns(
        text, len(words), configured_rules
    )
    errors.extend(pattern_errors)
    warnings.extend(pattern_warnings)

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
        "formulaic_pattern_findings": pattern_findings,
        "formulaic_pattern_finding_count": len(pattern_findings),
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


def run_harper(
    text: str,
    *,
    executable: str | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Run the optional privacy-first Harper grammar CLI over temporary text."""

    command = executable or find_harper()
    base: dict[str, Any] = {
        "name": "harper",
        "source": "https://github.com/Automattic/harper",
        "license": "Apache-2.0",
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
                "Optional local Harper grammar CLI not installed; the deterministic "
                "academic-style gate still ran."
            ),
        }
    try:
        with tempfile.TemporaryDirectory(prefix="research-os-harper-") as directory:
            source = Path(directory) / "manuscript.txt"
            source.write_text(text, encoding="utf-8")
            completed = runner(
                [
                    command,
                    "--no-color",
                    "lint",
                    "--format",
                    "json",
                    str(source),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=HARPER_TIMEOUT_SECONDS,
                check=False,
            )
        payload = json.loads(completed.stdout or "[]")
        if not isinstance(payload, list):
            raise ValueError("Harper JSON must be an array")
        diagnostics: list[dict[str, Any]] = []
        tool_errors: list[str] = []
        for file_result in payload:
            if not isinstance(file_result, dict):
                continue
            if file_result.get("error"):
                tool_errors.append(str(file_result["error"])[:300])
            raw_lints = file_result.get("lints")
            if not isinstance(raw_lints, list):
                continue
            for item in raw_lints:
                if not isinstance(item, dict):
                    continue
                span = item.get("span")
                diagnostics.append(
                    {
                        "check": str(item.get("rule", "unknown"))[:160],
                        "kind": str(item.get("kind", "unknown"))[:80],
                        "message": str(item.get("message", ""))[:500],
                        "line": item.get("line") if isinstance(item.get("line"), int) else None,
                        "column": (
                            item.get("column")
                            if isinstance(item.get("column"), int)
                            else None
                        ),
                        "span": (
                            [span.get("char_start"), span.get("char_end")]
                            if isinstance(span, dict)
                            and isinstance(span.get("char_start"), int)
                            and isinstance(span.get("char_end"), int)
                            else None
                        ),
                        "matched_text": str(item.get("matched_text", ""))[:200],
                        "replacements": (
                            [str(value)[:200] for value in item.get("suggestions", [])[:10]]
                            if isinstance(item.get("suggestions"), list)
                            else None
                        ),
                    }
                )
        diagnostics = diagnostics[:HARPER_MAX_DIAGNOSTICS]
        if tool_errors:
            return {
                **base,
                "available": True,
                "status": "error",
                "diagnostic_count": len(diagnostics),
                "diagnostics": diagnostics,
                "note": f"Harper reported an input error: {tool_errors[0]}",
            }
        return {
            **base,
            "available": True,
            "status": "advisory" if diagnostics else "pass",
            "diagnostic_count": len(diagnostics),
            "diagnostics": diagnostics,
            "note": (
                "Advisory local grammar findings; discipline-specific terms and "
                "scientifically necessary wording require human review."
            ),
        }
    except subprocess.TimeoutExpired:
        return {
            **base,
            "available": True,
            "status": "error",
            "note": f"Harper exceeded the {HARPER_TIMEOUT_SECONDS}-second timeout.",
        }
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            **base,
            "available": True,
            "status": "error",
            "note": f"Harper could not be evaluated: {str(exc)[:300]}",
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
        "human_review_required": True,
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
    if report.get("schema_version") != "1.2":
        errors.append("academic style audit schema_version must be 1.2")
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
    analysis = report.get("analysis")
    if not isinstance(analysis, dict):
        errors.append("academic style audit analysis is missing")
    else:
        findings = analysis.get("formulaic_pattern_findings")
        finding_count = analysis.get("formulaic_pattern_finding_count")
        if not isinstance(findings, list) or not isinstance(finding_count, int):
            errors.append("academic style audit line-level findings are missing")
        elif finding_count != len(findings):
            errors.append("academic style audit line-level finding count is inconsistent")
    reviewed_sources = report.get("reviewed_rule_sources")
    if not isinstance(reviewed_sources, list) or len(reviewed_sources) < 3:
        errors.append("academic style audit reviewed rule sources are missing")
    else:
        try:
            expected_sources = {
                item["id"]: item["commit"] for item in load_style_rules()["sources"]
            }
        except (AcademicStyleError, KeyError, TypeError) as exc:
            errors.append(f"academic style rule source validation failed: {exc}")
        else:
            actual_sources = {
                item.get("id"): item.get("commit")
                for item in reviewed_sources
                if isinstance(item, dict)
            }
            if actual_sources != expected_sources:
                errors.append("academic style audit reviewed rule sources do not match the lock")
    external_linters = report.get("external_linters")
    if not isinstance(external_linters, list):
        errors.append("academic style audit external_linters must be an array")
    else:
        expected_linters = {
            "proselint": ("https://github.com/amperser/proselint", "BSD-3-Clause"),
            "harper": ("https://github.com/Automattic/harper", "Apache-2.0"),
        }
        seen_linters: set[str] = set()
        for linter in external_linters:
            if not isinstance(linter, dict):
                errors.append("academic style audit has an invalid external linter record")
                continue
            if linter.get("detector") is not False or linter.get("local_only") is not True:
                errors.append("external writing checks must be local and must not be AI detectors")
            name = linter.get("name")
            if name in seen_linters or name not in expected_linters:
                errors.append("academic style audit has an unknown or duplicate external linter")
                continue
            seen_linters.add(str(name))
            source, license_name = expected_linters[str(name)]
            if linter.get("source") != source or linter.get("license") != license_name:
                errors.append(f"academic style audit {name} source or license is invalid")
        if seen_linters != set(expected_linters):
            errors.append("academic style audit must record proselint and Harper status")
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
