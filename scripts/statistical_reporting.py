"""Bind manuscript statistics to the reproducible, preregistered evidence report."""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.research_artifacts import path_in, read, write, sha, record
from scripts.manuscript_language import extract_text

REQUIRED = ("method", "analysis_unit", "independent_units", "estimate", "ci_low", "ci_high",
            "ci_confidence", "p_value", "p_adjusted", "seeds", "aggregation", "family", "family_size",
            "direction", "assumptions", "sample_size_rationale", "decision", "analysis_phase")
NUMERIC = {"independent_units", "estimate", "ci_low", "ci_high", "ci_confidence", "p_value", "p_adjusted", "seeds", "family_size"}


def display_value(value, decimals: int = 6) -> str:
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        return f"{value:.{decimals}f}".rstrip("0").rstrip(".") if decimals else str(round(value))
    return str(value)


def check_mapping(project: Path, paper_id: str, evidence: dict, mapping: dict) -> dict:
    errors, bindings = [], []
    comparisons = {row["comparison_id"]: row for row in evidence.get("comparisons", [])}
    if not comparisons:
        errors.append("no registered comparisons are available for statistical reporting")
    rows = mapping.get("comparisons", [])
    if not isinstance(rows, list):
        raise ValueError("statistical map comparisons must be an array")
    ids = [row.get("comparison_id") for row in rows if isinstance(row, dict)]
    if len(ids) != len(set(ids)) or set(ids) != set(comparisons):
        errors.append("map must cover every registered comparison exactly once, including adverse/exploratory results")
    paper_prefix = f"papers/{paper_id}/"
    for item in rows:
        if not isinstance(item, dict) or item.get("comparison_id") not in comparisons:
            errors.append("unknown or malformed comparison mapping")
            continue
        identifier = item["comparison_id"]
        actual = comparisons[identifier]
        if actual.get("status") != "computed":
            errors.append(f"{identifier}: blocked evidence cannot support manuscript statistics")
            continue
        fields, sections = set(), set()
        for location in item.get("locations", []):
            try:
                field = location["field"]
                if field not in REQUIRED:
                    raise ValueError("unsupported statistical field")
                relative = location["path"]
                if not relative.startswith(paper_prefix) or not any(
                        relative.startswith(paper_prefix + part + "/") for part in ("manuscript", "figures", "tables", "supplement")):
                    raise ValueError("statistics must point to this paper's final materials")
                target = path_in(project, relative)
                text = extract_text(target)
                quote = location["quote"]
                if not isinstance(quote, str) or not quote or text.count(quote) != 1:
                    raise ValueError("location quote must identify exactly one actual text passage")
                decimals = location.get("decimals", 6)
                if not isinstance(decimals, int) or isinstance(decimals, bool) or not 0 <= decimals <= 12:
                    raise ValueError("decimals must be an integer between 0 and 12")
                if field in NUMERIC:
                    scale = location.get("display_scale", 1)
                    if scale != 1 and not (field == "ci_confidence" and scale == 100):
                        raise ValueError("only confidence probability to percentage conversion is supported")
                    if not re.search(r"(?<![\w.])" + re.escape(display_value(actual[field] * scale, decimals)) + r"(?![\w.])", quote):
                        raise ValueError("displayed number differs from the actual evidence at the declared precision")
                elif location.get("value") != actual[field]:
                    raise ValueError("method, unit, phase or decision differs from the evidence record")
                if field == "ci_confidence" and location.get("uncertainty") != "CI":
                    raise ValueError("confidence interval cannot be relabelled as SD or SE")
                section = location["section"]
                if section not in {"Methods", "Results", "Caption", "Table", "Supplement"}:
                    raise ValueError("unknown reporting section")
                fields.add(field)
                sections.add(section)
                bindings.append({**location, "comparison_id": identifier, "sha256": sha(target),
                                 "evidence_value": actual[field]})
            except (KeyError, TypeError, ValueError, OSError) as exc:
                errors.append(f"{identifier}: {exc}")
        if not set(REQUIRED).issubset(fields):
            errors.append(f"{identifier}: missing fields {sorted(set(REQUIRED) - fields)}")
        if not {"Methods", "Results"}.issubset(sections):
            errors.append(f"{identifier}: Methods and Results locations are required")
        if item.get("has_figure") is True and "Caption" not in sections:
            errors.append(f"{identifier}: statistical figure needs a caption mapping")
        if not str(item.get("reporting_notes", "")).strip():
            errors.append(f"{identifier}: document exclusions, missingness, assumptions and repetition levels")
    return {"schema_version": "1.0", "status": "pass" if not errors else "fail", "paper_id": paper_id,
            "bindings": bindings, "errors": errors, "semantic_support_verified": False,
            "human_scientific_review_required": True, "scientific_completion_verified": False}


def audit(project: Path, paper_id: str) -> dict:
    from scripts.experiment_evidence import build_report, validate_report
    errors = validate_report(project, paper_id)
    evidence = build_report(project, paper_id)
    paper = path_in(project, f"papers/{paper_id}/statistical-reporting-map.json")
    result = check_mapping(project, paper_id, evidence, read(paper))
    result["errors"] = errors + result["errors"]
    result["status"] = "pass" if not result["errors"] else "fail"
    result["mapping_sha256"] = sha(paper)
    result["evidence_sha256"] = sha(path_in(project, f"papers/{paper_id}/experiment-evidence.json"))
    return result


def refresh(project: Path, paper_id: str) -> dict:
    value = audit(project, paper_id)
    output = project / "papers" / paper_id / "reviews/statistical-reporting.json"
    write(output, value)
    record(project, [output], "scripts/statistical_reporting.py")
    return value


def validate_saved_report(project: Path, paper_id: str) -> list[str]:
    try:
        expected = audit(project, paper_id)
        saved = read(path_in(project, f"papers/{paper_id}/reviews/statistical-reporting.json"))
        return expected["errors"] + ([] if expected == saved else ["statistical reporting is stale or differs from a rerun"])
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        return [str(exc)]
