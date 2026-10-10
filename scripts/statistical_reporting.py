"""Bind manuscript statistics to the reproducible, preregistered evidence report."""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.research_artifacts import path_in, read, write, sha, record, bound_source
from scripts.manuscript_language import extract_text
from scripts.scientific_editing import scientific_text

REQUIRED = ("method", "analysis_unit", "independent_units", "estimate", "ci_low", "ci_high",
            "ci_confidence", "p_value", "p_adjusted", "seeds", "aggregation", "family", "family_size",
            "direction", "assumptions", "sample_size_rationale", "decision", "analysis_phase")
NUMERIC = {"independent_units", "estimate", "ci_low", "ci_high", "ci_confidence", "p_value", "p_adjusted", "seeds", "family_size"}


def reporting_semantics(project: Path, paper_id: str, item: dict, actual: dict) -> dict:
    """Audit explicit reporting declarations, without claiming their truth."""
    value = item.get("reporting_semantics")
    if not isinstance(value, dict):
        raise ValueError("structured reporting_semantics is required")
    for key in ("estimand", "inclusion_rule", "exclusion_rule", "missingness_rule",
                "uncertainty_interpretation", "inference_boundary"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(f"reporting_semantics needs {key}")
    repetition = value.get("repetition")
    if not isinstance(repetition, dict) or any(repetition.get(key) != actual.get(key)
            for key in ("analysis_unit", "independent_units", "seeds", "aggregation")):
        raise ValueError("repetition levels must match actual independent units, seeds and aggregation")
    if repetition.get("seeds_are_independent_units") is not False:
        raise ValueError("seeds must not be counted as independent units")
    counts = value.get("sample_flow")
    if not isinstance(counts, dict) or any(type(counts.get(key)) is not int or counts[key] < 0
            for key in ("eligible_units", "excluded_units", "missing_units", "analyzed_units")):
        raise ValueError("sample_flow requires nonnegative integer counts")
    if (counts["analyzed_units"] != actual["independent_units"] or
            counts["eligible_units"] != counts["excluded_units"] + counts["missing_units"] + counts["analyzed_units"]):
        raise ValueError("sample_flow must reconcile disjoint eligible/excluded/missing/analyzed units to actual n")
    anchors = value.get("evidence", [])
    if not isinstance(anchors, list) or not 1 <= len(anchors) <= 20:
        raise ValueError("reporting semantics requires actual protocol/sample-flow evidence")
    bindings = []
    for anchor in anchors:
        source = bound_source(project, anchor)
        relative = source["path"]
        if relative.startswith((f"papers/{paper_id}/manuscript/", f"papers/{paper_id}/reviews/", "reports/")):
            raise ValueError("reporting semantics cannot cite its own manuscript or generated audit")
        text = path_in(project, relative).read_text(encoding="utf-8")
        quote = anchor.get("quote")
        if not isinstance(quote, str) or not quote.strip() or text.count(quote) != 1:
            raise ValueError("reporting semantics evidence requires a unique actual source quote")
        bindings.append({**source, "quote": quote})
    return {**value, "evidence": bindings, "declaration_truth_verified": False}


def display_value(value, decimals: int = 6) -> str:
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        return f"{value:.{decimals}f}".rstrip("0").rstrip(".") if decimals else str(round(value))
    return str(value)


def check_mapping(project: Path, paper_id: str, evidence: dict, mapping: dict, *, manuscript_sources: set[str] | None = None, figure_claims: set[str] | None = None) -> dict:
    errors, bindings, semantics = [], [], []
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
                text = (scientific_text(target).replace(r"\%", "%").replace(r"\_", "_").replace(r"\&", "&")
                        if target.suffix.lower() == ".tex" else extract_text(target))
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
                    if not re.search(r"(?<![\w.])" + re.escape(display_value(actual[field] * scale, decimals)) + r"(?!\w|\.\d)", quote):
                        raise ValueError("displayed number differs from the actual evidence at the declared precision")
                elif location.get("value") != actual[field]:
                    raise ValueError("method, unit, phase or decision differs from the evidence record")
                if field == "ci_confidence" and location.get("uncertainty") != "CI":
                    raise ValueError("confidence interval cannot be relabelled as SD or SE")
                section = location["section"]
                if section not in {"Methods", "Results", "Caption", "Table", "Supplement"}:
                    raise ValueError("unknown reporting section")
                if section in {"Methods", "Results"} and manuscript_sources is not None and relative not in manuscript_sources:
                    raise ValueError("Methods/Results must occur in the actual canonical manuscript source tree")
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
        needs_caption = item.get("has_figure") is True or bool(set(actual.get("claim_ids", [])) & (figure_claims or set()))
        if needs_caption and "Caption" not in sections:
            errors.append(f"{identifier}: statistical figure needs a caption mapping")
        if not str(item.get("reporting_notes", "")).strip():
            errors.append(f"{identifier}: document exclusions, missingness, assumptions and repetition levels")
        try:
            semantics.append({"comparison_id": identifier, **reporting_semantics(project, paper_id, item, actual)})
        except (ValueError, OSError, KeyError, TypeError) as exc:
            errors.append(f"{identifier}: {exc}")
    return {"schema_version": "1.0", "status": "pass" if not errors else "fail", "paper_id": paper_id,
            "bindings": bindings, "reporting_semantics": semantics, "errors": errors, "semantic_support_verified": False,
            "human_scientific_review_required": True, "scientific_completion_verified": False}


def audit(project: Path, paper_id: str) -> dict:
    from scripts.experiment_evidence import build_report, validate_report
    errors = validate_report(project, paper_id)
    evidence = build_report(project, paper_id)
    paper = path_in(project, f"papers/{paper_id}/statistical-reporting-map.json")
    from scripts.ref_verify_adapter import canonical_manuscript
    from scripts.citation_audit import tex_source_paths
    canonical = canonical_manuscript(project / "papers" / paper_id)
    sources = tex_source_paths(canonical) if canonical.suffix == ".tex" else [canonical]
    manuscript_sources = {p.relative_to(project).as_posix() for p in sources}
    figure_claims = set()
    figure_inputs = {}
    for build in sorted((project / "papers" / paper_id / "figures").rglob("*.figure-build.json")):
        figure_claims.update(read(build).get("quality", {}).get("claim_ids", []))
        figure_inputs[build.relative_to(project).as_posix()] = sha(build)
    result = check_mapping(project, paper_id, evidence, read(paper), manuscript_sources=manuscript_sources, figure_claims=figure_claims)
    result["errors"] = errors + result["errors"]
    result["status"] = "pass" if not result["errors"] else "fail"
    result["mapping_sha256"] = sha(paper)
    result["evidence_sha256"] = sha(path_in(project, f"papers/{paper_id}/experiment-evidence.json"))
    result["figure_inputs"] = figure_inputs
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
