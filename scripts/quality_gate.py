#!/usr/bin/env python3
"""Deterministic gates for doctoral rigor and JCR Q1 readiness.

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
MIN_EVIDENCE = {"G1": 5, "G2": 5, "G3": 3, "G4": 3, "G5": 3}
ACCEPTABLE_QUARTILES = {"Q1"}
DIMENSIONS = {
    "G1": ("novelty", "originality_evidence", "doctoral_depth", "significance", "feasibility", "reliability_plan", "evidence_strength", "publication_potential"),
    "G2": ("novelty", "distinct_contribution", "portfolio_coherence", "doctoral_progression", "significance", "feasibility", "methodological_rigor", "venue_fit"),
    "G3": ("novelty", "feasibility", "methodological_rigor", "baseline_strength", "statistical_rigor", "power_or_precision", "data_quality", "leakage_control", "external_validity", "reproducibility", "venue_fit"),
    "G4": ("novelty_supported", "effect_robustness", "external_validity", "statistical_rigor", "reproducibility", "claim_evidence_strength", "venue_fit"),
    "G5": ("novelty", "scientific_contribution", "methodological_rigor", "evidence_strength", "venue_fit", "review_resilience", "english_academic_writing", "claim_calibration"),
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
    if report.get("schema_version") != "1.1": errors.append("schema_version must be 1.1")
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
    minimum_evidence = MIN_EVIDENCE.get(gate, 3)
    if not isinstance(evidence, list) or len(evidence) < minimum_evidence:
        errors.append(f"at least {minimum_evidence} evidence items are required")
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
    originality = report.get("originality_assessment")
    if not isinstance(originality, dict): errors.append("originality_assessment object is required")
    else:
        for field, minimum in (("closest_prior_work_ids", 3), ("adjacent_fields_checked", 3), ("non_novel_elements", 1), ("differentiating_claims", 1)):
            value = originality.get(field)
            if not isinstance(value, list) or len(value) < minimum or any(not str(item).strip() for item in value):
                errors.append(f"originality_assessment.{field} needs at least {minimum} non-empty item(s)")
        if originality.get("counterevidence_considered") is not True: errors.append("originality_assessment.counterevidence_considered must be true")
        if not str(originality.get("residual_risk", "")).strip(): errors.append("originality_assessment.residual_risk is required")
    doctoral = report.get("doctoral_readiness")
    if not isinstance(doctoral, dict): errors.append("doctoral_readiness object is required")
    else:
        for field in ("unifying_thesis", "original_knowledge_contribution", "synthesis_beyond_individual_papers", "methodological_progression", "scope_boundaries"):
            if not str(doctoral.get(field, "")).strip(): errors.append(f"doctoral_readiness.{field} is required")
        challenges = doctoral.get("examiner_challenges")
        if not isinstance(challenges, list) or len(challenges) < 3 or any(not str(item).strip() for item in challenges):
            errors.append("doctoral_readiness.examiner_challenges needs at least 3 non-empty items")
    venue = report.get("venue_readiness")
    if not isinstance(venue, dict): errors.append("venue_readiness object is required")
    else:
        if venue.get("minimum_jcr_quartile") != "Q1": errors.append("venue_readiness.minimum_jcr_quartile must be Q1")
        if venue.get("preferred_jcr_quartile") != "Q1": errors.append("venue_readiness.preferred_jcr_quartile must be Q1")
        candidates = venue.get("candidate_venues")
        if not isinstance(candidates, list) or len(candidates) < 2: errors.append("at least two current JCR Q1 candidate venues are required")
        if venue.get("current_verification_required") is not True: errors.append("venue_readiness.current_verification_required must be true")
        if venue.get("venue_specific_guidelines_required") is not True: errors.append("venue_readiness.venue_specific_guidelines_required must be true")
        q1_seen = False
        for index, candidate in enumerate(candidates or [], 1):
            if not isinstance(candidate, dict): errors.append(f"venue_readiness.candidate_venues[{index}] must be an object"); continue
            quartile = candidate.get("quartile")
            if quartile not in ACCEPTABLE_QUARTILES: errors.append(f"candidate venue {index} must be current JCR Q1")
            q1_seen = q1_seen or quartile == "Q1"
            if candidate.get("indexing") not in {"SCIE", "SCI"}: errors.append(f"candidate venue {index} must be SCI/SCIE")
            if not str(candidate.get("source_url", "")).startswith("https://"): errors.append(f"candidate venue {index} needs an HTTPS primary source")
            for field in ("name", "category", "scope_fit", "article_type"):
                if not str(candidate.get(field, "")).strip(): errors.append(f"candidate venue {index} needs {field}")
            year = candidate.get("jcr_year")
            if not isinstance(year, int) or isinstance(year, bool) or year < 2000: errors.append(f"candidate venue {index} needs jcr_year")
        if candidates and not q1_seen: errors.append("at least one aspirational JCR Q1 candidate venue is required")
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
