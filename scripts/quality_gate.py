#!/usr/bin/env python3
"""Deterministic quality gates for novelty, feasibility and Q1-level readiness.

AI may propose scores and evidence, but this module only accepts structured evidence
that satisfies hard thresholds. It cannot prove publication or acceptance; it enforces
a Q1-targeting floor before a human can approve a gate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MIN_SCORE = 8.0
MIN_OVERALL = 8.5
MIN_EVIDENCE = 3
Q1_LABELS = {"Q1", "JCR_Q1"}
DIMENSIONS = {
    "G1": ("novelty", "doctoral_depth", "significance", "feasibility", "evidence_strength", "publication_potential"),
    "G2": ("novelty", "distinct_contribution", "significance", "feasibility", "methodological_rigor", "q1_fit"),
    "G3": ("novelty", "feasibility", "methodological_rigor", "statistical_rigor", "data_quality", "reproducibility", "q1_fit"),
    "G4": ("novelty_supported", "effect_robustness", "statistical_rigor", "reproducibility", "claim_evidence_strength", "q1_fit"),
    "G5": ("novelty", "scientific_contribution", "methodological_rigor", "evidence_strength", "q1_fit", "review_resilience", "writing_quality"),
}

class QualityGateError(RuntimeError):
    pass

def _score(value: Any, field: str, errors: list[str]) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 10:
        errors.append(f"{field} must be a number from 0 to 10")
        return None
    if value < MIN_SCORE:
        errors.append(f"{field}={value:g} is below hard floor {MIN_SCORE:g}")
    return float(value)

def validate_report(report: dict[str, Any], gate: str) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != "1.0": errors.append("schema_version must be 1.0")
    if report.get("gate") != gate: errors.append(f"gate must be {gate}")
    if report.get("status") not in {"ready_for_review", "approved"}: errors.append("status must be ready_for_review or approved")
    dimensions = report.get("scores")
    if not isinstance(dimensions, dict): errors.append("scores object is required"); dimensions = {}
    scores: list[float] = []
    for field in DIMENSIONS.get(gate, ()):
        value = _score(dimensions.get(field), f"scores.{field}", errors)
        if value is not None: scores.append(value)
    if scores and sum(scores) / len(scores) < MIN_OVERALL: errors.append(f"overall mean score must be >= {MIN_OVERALL:g}")
    evidence = report.get("evidence")
    if not isinstance(evidence, list) or len(evidence) < MIN_EVIDENCE:
        errors.append(f"at least {MIN_EVIDENCE} evidence items are required")
    else:
        for index, item in enumerate(evidence, 1):
            if not isinstance(item, dict): errors.append(f"evidence[{index}] must be an object"); continue
            for field in ("id", "source", "claim_supported", "source_date"):
                if not str(item.get(field, "")).strip(): errors.append(f"evidence[{index}] needs {field}")
    for field in ("novelty_claim", "feasibility_claim", "scientific_contribution"):
        if not str(report.get(field, "")).strip(): errors.append(f"{field} is required")
    if report.get("novelty_basis") not in {"comparative_primary_literature", "comparative_literature_and_patents"}:
        errors.append("novelty_basis must be comparative_primary_literature or comparative_literature_and_patents")
    if report.get("novelty_is_absence_only") is not False: errors.append("novelty_is_absence_only must be false")
    q1 = report.get("q1_target")
    if not isinstance(q1, dict): errors.append("q1_target object is required")
    else:
        candidates = q1.get("candidate_venues")
        if not isinstance(candidates, list) or len(candidates) < 2: errors.append("at least two Q1 candidate venues are required")
        if q1.get("current_verification_required") is not True: errors.append("current_verification_required must be true")
        for index, candidate in enumerate(candidates or [], 1):
            if not isinstance(candidate, dict): errors.append(f"q1_target.candidate_venues[{index}] must be an object"); continue
            if candidate.get("quartile") not in Q1_LABELS: errors.append(f"q1 candidate {index} must be explicitly Q1")
            if candidate.get("indexing") not in {"SCIE", "SCI"}: errors.append(f"q1 candidate {index} must be SCI/SCIE")
            if not str(candidate.get("source_url", "")).startswith("https://"): errors.append(f"q1 candidate {index} needs an HTTPS primary source")
    blockers = report.get("blockers")
    if not isinstance(blockers, list): errors.append("blockers must be a list")
    elif blockers: errors.append("quality report has unresolved blockers")
    if report.get("human_review_required") is not True: errors.append("human_review_required must be true")
    return errors

def validate_file(path: Path, gate: str) -> list[str]:
    try: report = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError: return [f"missing quality report: {path}"]
    except json.JSONDecodeError as exc: return [f"invalid JSON in quality report {path}: {exc}"]
    if not isinstance(report, dict): return [f"quality report must be an object: {path}"]
    return validate_report(report, gate)
