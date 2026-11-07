#!/usr/bin/env python3
"""Check factual quality evidence and report score/venue observations separately.

Numerical self-scores cannot verify science. Selected-venue requirements are checked
once when preparing the submission package, not through early readiness scores.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

MIN_SCORE = 8.0
MIN_OVERALL = 8.5
MIN_EVIDENCE = {"G1": 5, "G2": 5, "G3": 3, "G4": 3, "G5": 3}
ACCEPTABLE_QUARTILES = {"Q1", "Q2"}
DIMENSIONS = {
    "G1": ("novelty", "originality_evidence", "doctoral_depth", "significance", "feasibility", "reliability_plan", "evidence_strength", "publication_potential"),
    "G2": ("novelty", "distinct_contribution", "portfolio_coherence", "doctoral_progression", "significance", "feasibility", "methodological_rigor", "venue_fit"),
    "G3": ("novelty", "feasibility", "methodological_rigor", "baseline_strength", "statistical_rigor", "power_or_precision", "data_quality", "leakage_control", "external_validity", "reproducibility", "venue_fit"),
    "G4": ("novelty_supported", "effect_robustness", "external_validity", "statistical_rigor", "reproducibility", "claim_evidence_strength", "venue_fit"),
    "G5": ("novelty", "scientific_contribution", "methodological_rigor", "evidence_strength", "venue_fit", "review_resilience", "english_academic_writing", "claim_calibration"),
}
OBSERVATIONAL_CRITERIA = {"venue_fit", "publication_potential", "english_academic_writing"}


def scientific_projection(report):
    """Retain factual assessments without scores or final-venue observations."""
    result = {key: value for key, value in report.items() if key not in {
        "scores", "venue_readiness", "created_at", "updated_at", "generated_at", "reviewed_at"}}
    if isinstance(result.get("assessments"), dict):
        result["assessments"] = {name: row for name, row in result["assessments"].items() if name not in OBSERVATIONAL_CRITERIA}
        if not result["assessments"]:
            result.pop("assessments")
    return result


class QualityGateError(RuntimeError):
    pass

def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())

def _score(value: Any, field: str, warnings: list[str]) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 10:
        warnings.append(f"{field} is not a numerical observation from 0 to 10")
        return None
    if value < MIN_SCORE:
        warnings.append(f"{field}={value:g} is below advisory reference {MIN_SCORE:g}; the score is not a scientific gate")
    return float(value)

def validate_report(report: dict[str, Any], gate: str, *, project: Path | None = None,
                    require_facts: bool = False, warnings: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    observations = warnings if warnings is not None else []
    version = report.get("schema_version")
    if version not in {"1.1", "1.2"}: errors.append("schema_version must be 1.1 or 1.2")
    if require_facts and version != "1.2": observations.append("quality report migration: legacy numerical self-scores do not establish factual scientific validation")
    if report.get("gate") != gate: errors.append(f"gate must be {gate}")
    if report.get("status") not in {"ready_for_review", "approved"}: errors.append("status must be ready_for_review or approved")
    if version == "1.2" or "assessments" in report:
        assessments = report.get("assessments")
        if not isinstance(assessments, dict):
            errors.append("assessments object is required"); assessments = {}
        from scripts.research_candidates import anchor_errors
        required_criteria = DIMENSIONS.get(gate, ()) if version == "1.2" else ()
        for criterion in dict.fromkeys((*required_criteria, *assessments)):
            findings = observations if criterion in OBSERVATIONAL_CRITERIA else errors
            row = assessments.get(criterion)
            if not isinstance(row, dict): findings.append(criterion + " needs an evidence assessment"); continue
            if row.get("status") != "satisfied": findings.append(criterion + " has unresolved or failed evidence")
            if not _nonempty_string(row.get("rationale")): findings.append(criterion + " needs its factual rationale")
            anchors = row.get("source_anchors")
            if not isinstance(anchors, list) or not anchors: findings.append(criterion + " needs located factual evidence")
            elif project is not None:
                for anchor in anchors: findings.extend(criterion + ": " + e for e in anchor_errors(project, anchor))
    if version != "1.2" or "scores" in report:
        dimensions = report.get("scores")
        if not isinstance(dimensions, dict): observations.append("numerical scores are absent or malformed; scores are optional observations"); dimensions = {}
        scores: list[float] = []
        for field in DIMENSIONS.get(gate, ()):
            value = _score(dimensions.get(field), f"scores.{field}", observations)
            if value is not None: scores.append(value)
        if scores and sum(scores) / len(scores) < MIN_OVERALL: observations.append(f"overall mean score is below advisory reference {MIN_OVERALL:g}; scores do not establish scientific validity")
    evidence = report.get("evidence")
    minimum_evidence = MIN_EVIDENCE.get(gate, 3)
    if not isinstance(evidence, list) or len(evidence) < minimum_evidence:
        errors.append(f"at least {minimum_evidence} evidence items are required")
    else:
        for index, item in enumerate(evidence, 1):
            if not isinstance(item, dict): errors.append(f"evidence[{index}] must be an object"); continue
            for field in ("id", "source", "claim_supported", "source_date"):
                if not _nonempty_string(item.get(field)): errors.append(f"evidence[{index}] needs {field}")
    for field in ("novelty_claim", "feasibility_claim", "scientific_contribution"):
        if not _nonempty_string(report.get(field)): errors.append(f"{field} is required")
    if report.get("novelty_basis") not in {"comparative_primary_literature", "comparative_literature_and_patents"}:
        errors.append("novelty_basis must be comparative_primary_literature or comparative_literature_and_patents")
    if report.get("novelty_is_absence_only") is not False: errors.append("novelty_is_absence_only must be false")
    originality = report.get("originality_assessment")
    if not isinstance(originality, dict): errors.append("originality_assessment object is required")
    else:
        for field, minimum in (("closest_prior_work_ids", 3), ("adjacent_fields_checked", 3), ("non_novel_elements", 1), ("differentiating_claims", 1)):
            value = originality.get(field)
            if not isinstance(value, list) or len(value) < minimum or any(not _nonempty_string(item) for item in value):
                errors.append(f"originality_assessment.{field} needs at least {minimum} non-empty item(s)")
        if originality.get("counterevidence_considered") is not True: errors.append("originality_assessment.counterevidence_considered must be true")
        if not _nonempty_string(originality.get("residual_risk")): errors.append("originality_assessment.residual_risk is required")
    doctoral = report.get("doctoral_readiness")
    if not isinstance(doctoral, dict): errors.append("doctoral_readiness object is required")
    else:
        for field in ("unifying_thesis", "original_knowledge_contribution", "synthesis_beyond_individual_papers", "methodological_progression", "scope_boundaries"):
            if not _nonempty_string(doctoral.get(field)): errors.append(f"doctoral_readiness.{field} is required")
        challenges = doctoral.get("examiner_challenges")
        if not isinstance(challenges, list) or len(challenges) < 3 or any(not _nonempty_string(item) for item in challenges):
            errors.append("doctoral_readiness.examiner_challenges needs at least 3 non-empty items")
    venue = report.get("venue_readiness")
    if not isinstance(venue, dict): observations.append("venue_readiness is not recorded; selected-venue checks apply at submission packaging")
    else:
        minimum_quartile = venue.get("minimum_jcr_quartile")
        if not isinstance(minimum_quartile, str) or minimum_quartile not in ACCEPTABLE_QUARTILES: observations.append("venue_readiness.minimum_jcr_quartile should record the intended Q1 or Q2 target")
        if venue.get("preferred_jcr_quartile") != "Q1": observations.append("venue_readiness.preferred_jcr_quartile differs from the Q1 preference")
        candidates = venue.get("candidate_venues")
        if not isinstance(candidates, list) or len(candidates) < 2: observations.append("fewer than two current JCR candidate venues are recorded; final selected-venue verification remains separate")
        if venue.get("current_verification_required") is not True: observations.append("venue_readiness.current_verification_required is not recorded as true")
        if venue.get("venue_specific_guidelines_required") is not True: observations.append("venue_readiness.venue_specific_guidelines_required is not recorded as true")
        try:
            from scripts.venue_policy import meets_target
        except ImportError:
            from venue_policy import meets_target
        for index, candidate in enumerate(candidates if isinstance(candidates, list) else [], 1):
            if not isinstance(candidate, dict): observations.append(f"venue_readiness.candidate_venues[{index}] must be an object"); continue
            quartile = candidate.get("quartile")
            if not isinstance(quartile, str) or quartile not in ACCEPTABLE_QUARTILES or not meets_target(quartile, minimum_quartile): observations.append(f"candidate venue {index} does not establish the current JCR {minimum_quartile or 'Q1/Q2'} target")
            if candidate.get("indexing") not in ("SCIE", "SCI"): observations.append(f"candidate venue {index} lacks SCI/SCIE indexing evidence")
            if not str(candidate.get("source_url", "")).startswith("https://"): observations.append(f"candidate venue {index} needs an HTTPS primary source")
            for field in ("name", "category", "scope_fit", "article_type"):
                if not _nonempty_string(candidate.get(field)): observations.append(f"candidate venue {index} needs {field}")
            year = candidate.get("jcr_year")
            if not isinstance(year, int) or isinstance(year, bool) or year not in {date.today().year,date.today().year-1}: observations.append(f"candidate venue {index} needs the current or immediately previous JCR year")
    blockers = report.get("blockers")
    if not isinstance(blockers, list): errors.append("blockers must be a list")
    elif blockers: errors.append("quality report has unresolved blockers")
    if gate in {"G1", "G2"} and report.get("human_review_required") is not True:
        errors.append("human_review_required must be true for topic decisions")
    elif type(report.get("human_review_required")) is not bool:
        errors.append("human_review_required must be a boolean; only G1/G2 require human stage decisions")
    return errors

def validate_file(path: Path, gate: str, *, project: Path | None = None, require_facts: bool = False,
                  warnings: list[str] | None = None) -> list[str]:
    try: report = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError: return [f"missing quality report: {path}"]
    except json.JSONDecodeError as exc: return [f"invalid JSON in quality report {path}: {exc}"]
    if not isinstance(report, dict): return [f"quality report must be an object: {path}"]
    return validate_report(report, gate, project=project, require_facts=require_facts, warnings=warnings)
