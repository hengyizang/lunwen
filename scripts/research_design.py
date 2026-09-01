#!/usr/bin/env python3
"""Deterministic validators for doctoral novelty and paper-level study design.

These checks validate explicit evidence and design structure. They do not prove
novelty, doctoral merit, reliability, or journal acceptance; those judgments
remain human responsibilities at G1--G5.
"""
from __future__ import annotations

import itertools
import re
from datetime import date
from typing import Any, Iterable


PAPER_RE = re.compile(r"^P[0-9]{2}$")
DATE_RE = re.compile(r"^20[0-9]{2}-[01][0-9]-[0-3][0-9]$")
VENUE_QUARTILES = {"Q1"}
BASELINE_CLASSES = {"simple", "domain_standard", "strong_recent"}
NOVELTY_TYPES = {
    "theoretical",
    "methodological",
    "empirical",
    "dataset",
    "benchmark",
    "system",
    "application",
}


def _text(value: Any, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string")
        return None
    return value.strip()


def _list(
    value: Any,
    field: str,
    errors: list[str],
    *,
    minimum: int = 1,
) -> list[Any]:
    if not isinstance(value, list) or len(value) < minimum:
        errors.append(f"{field} must contain at least {minimum} item(s)")
        return []
    return value


def _string_list(
    value: Any,
    field: str,
    errors: list[str],
    *,
    minimum: int = 1,
) -> list[str]:
    items = _list(value, field, errors, minimum=minimum)
    if items and any(not isinstance(item, str) or not item.strip() for item in items):
        errors.append(f"{field} must contain only non-empty strings")
        return []
    normalized = [item.strip() for item in items]
    if len(set(normalized)) != len(normalized):
        errors.append(f"{field} must not contain duplicates")
    return normalized


def _object(value: Any, field: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return {}
    return value


def _https(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.startswith("https://"):
        errors.append(f"{field} must be an HTTPS primary-source URL")


def validate_venue_candidates(value: Any, field: str = "target_venues") -> list[str]:
    errors: list[str] = []
    candidates = _list(value, field, errors, minimum=2)
    q1_seen = False
    for index, item in enumerate(candidates):
        prefix = f"{field}[{index}]"
        venue = _object(item, prefix, errors)
        if not venue:
            continue
        for key in ("name", "category", "scope_fit", "article_type"):
            _text(venue.get(key), f"{prefix}.{key}", errors)
        quartile = venue.get("quartile")
        if quartile not in VENUE_QUARTILES:
            errors.append(f"{prefix}.quartile must be current JCR Q1")
        q1_seen = q1_seen or quartile == "Q1"
        if venue.get("indexing") not in {"SCI", "SCIE"}:
            errors.append(f"{prefix}.indexing must be SCI or SCIE")
        year = venue.get("jcr_year")
        if not isinstance(year, int) or isinstance(year, bool) or year not in {date.today().year,date.today().year-1}:
            errors.append(f"{prefix}.jcr_year must identify the current or immediately previous JCR edition")
        _https(venue.get("source_url"), f"{prefix}.source_url", errors)
    if candidates and not q1_seen:
        errors.append(f"{field} must contain current JCR Q1 candidates")
    return errors


def validate_originality_audit(audit: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if audit.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if audit.get("status") not in {"ready_for_review", "approved"}:
        errors.append("status must be ready_for_review or approved")

    scope = _object(audit.get("search_scope"), "search_scope", errors)
    _string_list(scope.get("databases"), "search_scope.databases", errors, minimum=3)
    _string_list(scope.get("adjacent_fields"), "search_scope.adjacent_fields", errors, minimum=3)
    _string_list(scope.get("query_families"), "search_scope.query_families", errors, minimum=3)
    cutoff = scope.get("cutoff_date")
    if not isinstance(cutoff, str) or not DATE_RE.fullmatch(cutoff):
        errors.append("search_scope.cutoff_date must use YYYY-MM-DD")
    else:
        try:cutoff_date=date.fromisoformat(cutoff)
        except ValueError:errors.append("search_scope.cutoff_date is not a real calendar date")
        else:
            if cutoff_date>date.today() or (date.today()-cutoff_date).days>120:errors.append("search_scope.cutoff_date must be current (within 120 days and not in the future)")

    works = _list(audit.get("closest_prior_work"), "closest_prior_work", errors, minimum=5)
    work_ids: set[str] = set()
    for index, item in enumerate(works):
        prefix = f"closest_prior_work[{index}]"
        work = _object(item, prefix, errors)
        work_id = _text(work.get("id"), f"{prefix}.id", errors)
        if work_id:
            if work_id in work_ids:
                errors.append(f"{prefix}.id is duplicated")
            work_ids.add(work_id)
        for key in ("title", "overlap", "difference", "evidence_location"):
            _text(work.get(key), f"{prefix}.{key}", errors)
        year = work.get("publication_year")
        if not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year <= date.today().year:
            errors.append(f"{prefix}.publication_year is invalid")
        _https(work.get("primary_source_url"), f"{prefix}.primary_source_url", errors)

    recent_works=[item for item in works if isinstance(item,dict) and isinstance(item.get("publication_year"),int) and item["publication_year"]>=date.today().year-5]
    if len(recent_works)<2:errors.append("closest_prior_work must include at least two works from the current five-year window")

    claims = _list(audit.get("novelty_claims"), "novelty_claims", errors, minimum=1)
    claim_ids:set[str]=set()
    for index, item in enumerate(claims):
        prefix = f"novelty_claims[{index}]"
        claim = _object(item, prefix, errors)
        for key in ("claim_id", "claim", "counterevidence", "residual_risk"):
            _text(claim.get(key), f"{prefix}.{key}", errors)
        claim_id=claim.get("claim_id")
        if isinstance(claim_id,str) and claim_id:
            if claim_id in claim_ids:errors.append(f"{prefix}.claim_id is duplicated")
            claim_ids.add(claim_id)
        if claim.get("novelty_type") not in NOVELTY_TYPES:
            errors.append(f"{prefix}.novelty_type is not recognized")
        evidence_ids = _string_list(
            claim.get("evidence_ids"), f"{prefix}.evidence_ids", errors, minimum=2
        )
        missing = sorted(set(evidence_ids) - work_ids)
        if missing:
            errors.append(f"{prefix}.evidence_ids reference unknown work: {', '.join(missing)}")

    patent = _object(audit.get("patent_search"), "patent_search", errors)
    patent_status = patent.get("status")
    if patent_status == "completed":
        _string_list(patent.get("databases"), "patent_search.databases", errors)
        _string_list(patent.get("queries"), "patent_search.queries", errors)
    elif patent_status == "not_applicable":
        _text(patent.get("justification"), "patent_search.justification", errors)
    else:
        errors.append("patent_search.status must be completed or not_applicable")

    doctoral = _object(audit.get("doctoral_case"), "doctoral_case", errors)
    for key in (
        "unifying_thesis",
        "original_knowledge_contribution",
        "synthesis_beyond_individual_papers",
        "methodological_progression",
        "scope_boundaries",
    ):
        _text(doctoral.get(key), f"doctoral_case.{key}", errors)
    _string_list(doctoral.get("examiner_challenges"), "doctoral_case.examiner_challenges", errors, minimum=3)

    reliability = _object(audit.get("reliability_strategy"), "reliability_strategy", errors)
    for key in (
        "triangulation",
        "replication",
        "sensitivity_analysis",
        "negative_result_policy",
        "external_validity",
    ):
        _text(reliability.get(key), f"reliability_strategy.{key}", errors)
    if audit.get("human_review_required") is not True:
        errors.append("human_review_required must be true")
    return errors


def validate_search_log(
    records: list[dict[str, Any]], audit: dict[str, Any]
) -> list[str]:
    """Validate that the claimed originality search is traceable to query logs."""

    errors: list[str] = []
    if len(records) < 3:
        errors.append("search log must contain at least three recorded searches")
    logged_databases: set[str] = set()
    logged_families: set[str] = set()
    included_work_ids: set[str] = set()
    search_ids: set[str] = set()
    for index, record in enumerate(records):
        prefix = f"search-log[{index}]"
        if record.get("schema_version") != "1.0":
            errors.append(f"{prefix}.schema_version must be 1.0")
        search_id = _text(record.get("search_id"), f"{prefix}.search_id", errors)
        if search_id:
            if search_id in search_ids:
                errors.append(f"{prefix}.search_id is duplicated")
            search_ids.add(search_id)
        database = _text(record.get("database"), f"{prefix}.database", errors)
        family = _text(record.get("query_family"), f"{prefix}.query_family", errors)
        if database:
            logged_databases.add(database)
        if family:
            logged_families.add(family)
        for key in ("query", "date_range", "filters"):
            _text(record.get(key), f"{prefix}.{key}", errors)
        searched_at = record.get("searched_at")
        if not isinstance(searched_at, str) or not DATE_RE.fullmatch(searched_at[:10]):
            errors.append(f"{prefix}.searched_at must begin with YYYY-MM-DD")
        else:
            try:searched_date=date.fromisoformat(searched_at[:10])
            except ValueError:errors.append(f"{prefix}.searched_at is not a real calendar date")
            else:
                if searched_date>date.today() or (date.today()-searched_date).days>180:errors.append(f"{prefix}.searched_at must be current (within 180 days and not in the future)")
        result_count = record.get("result_count")
        if not isinstance(result_count, int) or isinstance(result_count, bool) or result_count < 0:
            errors.append(f"{prefix}.result_count must be a non-negative integer")
        _https(record.get("source_url"), f"{prefix}.source_url", errors)
        included = _string_list(
            record.get("included_work_ids"),
            f"{prefix}.included_work_ids",
            errors,
            minimum=0,
        )
        included_work_ids.update(included)
        _string_list(
            record.get("exclusion_reasons"),
            f"{prefix}.exclusion_reasons",
            errors,
            minimum=1,
        )

    scope = audit.get("search_scope") if isinstance(audit.get("search_scope"), dict) else {}
    claimed_database_values = scope.get("databases")
    claimed_family_values = scope.get("query_families")
    claimed_databases = {
        str(item) for item in claimed_database_values
    } if isinstance(claimed_database_values, list) else set()
    claimed_families = {
        str(item) for item in claimed_family_values
    } if isinstance(claimed_family_values, list) else set()
    missing_databases = sorted(claimed_databases - logged_databases)
    missing_families = sorted(claimed_families - logged_families)
    if missing_databases:
        errors.append("claimed databases absent from search log: " + ", ".join(missing_databases))
    if missing_families:
        errors.append("claimed query families absent from search log: " + ", ".join(missing_families))
    closest_values = audit.get("closest_prior_work")
    closest_items = closest_values if isinstance(closest_values, list) else []
    closest_ids = {
        str(item.get("id"))
        for item in closest_items
        if isinstance(item, dict) and item.get("id")
    }
    missing_works = sorted(closest_ids - included_work_ids)
    if missing_works:
        errors.append("closest prior works absent from search log inclusions: " + ", ".join(missing_works))
    return errors


def validate_paper_map(value: dict[str, Any], expected_paper_ids: Iterable[str]) -> list[str]:
    errors: list[str] = []
    expected = sorted(expected_paper_ids)
    if value.get("schema_version") != "2.0":
        errors.append("schema_version must be 2.0")
    if value.get("status") not in {"ready_for_review", "approved"}:
        errors.append("status must be ready_for_review or approved")
    papers = _list(value.get("papers"), "papers", errors, minimum=len(expected))
    seen: list[str] = []
    global_claim_ids: set[str] = set()
    for index, item in enumerate(papers):
        prefix = f"papers[{index}]"
        paper = _object(item, prefix, errors)
        paper_id = paper.get("paper_id")
        if not isinstance(paper_id, str) or not PAPER_RE.fullmatch(paper_id):
            errors.append(f"{prefix}.paper_id must look like P01")
        else:
            seen.append(paper_id)
        for key in ("portfolio_role", "distinct_contribution"):
            _text(paper.get(key), f"{prefix}.{key}", errors)
        claim_ids = _string_list(paper.get("unique_claim_ids"), f"{prefix}.unique_claim_ids", errors)
        duplicated_claims = sorted(set(claim_ids) & global_claim_ids)
        if duplicated_claims:
            errors.append(f"{prefix}.unique_claim_ids repeat another paper's claim: {', '.join(duplicated_claims)}")
        global_claim_ids.update(claim_ids)
        _string_list(paper.get("shared_assets"), f"{prefix}.shared_assets", errors, minimum=0)
        _string_list(paper.get("dependencies"), f"{prefix}.dependencies", errors, minimum=0)
    if sorted(seen) != expected:
        errors.append(f"papers must contain exactly: {', '.join(expected)}")

    required_pairs = {tuple(pair) for pair in itertools.combinations(expected, 2)}
    found_pairs: set[tuple[str, str]] = set()
    comparisons = _list(
        value.get("pairwise_distinctness"),
        "pairwise_distinctness",
        errors,
        minimum=len(required_pairs),
    )
    for index, item in enumerate(comparisons):
        prefix = f"pairwise_distinctness[{index}]"
        comparison = _object(item, prefix, errors)
        pair = tuple(sorted((str(comparison.get("paper_a", "")), str(comparison.get("paper_b", "")))))
        if pair not in required_pairs:
            errors.append(f"{prefix} does not identify a valid distinct paper pair")
        elif pair in found_pairs:
            errors.append(f"{prefix} duplicates pair {pair[0]}/{pair[1]}")
        else:
            found_pairs.add(pair)
        for key in (
            "distinct_research_questions",
            "distinct_primary_claims",
            "independent_primary_evidence",
            "standalone_scientific_value",
        ):
            if comparison.get(key) is not True:
                errors.append(f"{prefix}.{key} must be true")
        if not isinstance(comparison.get("shared_primary_outcome"), bool):
            errors.append(f"{prefix}.shared_primary_outcome must be boolean")
        if comparison.get("overlap_risk") not in {"low", "moderate"}:
            errors.append(f"{prefix}.overlap_risk must be low or moderate")
        for key in ("shared_outcome_justification", "why_separate", "merge_trigger"):
            _text(comparison.get(key), f"{prefix}.{key}", errors)
    missing_pairs = sorted(required_pairs - found_pairs)
    if missing_pairs:
        errors.append(
            "pairwise_distinctness is missing: "
            + ", ".join(f"{left}/{right}" for left, right in missing_pairs)
        )

    synthesis = _object(value.get("thesis_synthesis"), "thesis_synthesis", errors)
    for key in (
        "core_thesis",
        "extension_thesis",
        "cumulative_progression",
        "integrated_contribution",
        "dependency_logic",
    ):
        _text(synthesis.get(key), f"thesis_synthesis.{key}", errors)
    return errors


def validate_paper_contract(contract: dict[str, Any], expected_paper_id: str) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != "2.0":
        errors.append("schema_version must be 2.0")
    if contract.get("paper_id") != expected_paper_id:
        errors.append(f"paper_id must be {expected_paper_id}")
    if contract.get("writing_language") != "en":
        errors.append("writing_language must be en")
    if contract.get("status") not in {"ready_for_review", "approved"}:
        errors.append("status must be ready_for_review or approved")
    for key in (
        "working_title",
        "research_question",
        "distinct_contribution",
        "relationship_to_core",
        "relationship_to_extension",
    ):
        _text(contract.get(key), key, errors)

    boundary = _object(contract.get("originality_boundary"), "originality_boundary", errors)
    _string_list(boundary.get("novel_elements"), "originality_boundary.novel_elements", errors)
    _string_list(boundary.get("reused_elements"), "originality_boundary.reused_elements", errors)
    _string_list(
        boundary.get("closest_prior_work_ids"),
        "originality_boundary.closest_prior_work_ids",
        errors,
        minimum=3,
    )
    for key in ("differentiation", "claim_limitations"):
        _text(boundary.get(key), f"originality_boundary.{key}", errors)

    hypotheses = _list(contract.get("hypotheses"), "hypotheses", errors)
    hypothesis_ids: set[str] = set()
    for index, item in enumerate(hypotheses):
        prefix = f"hypotheses[{index}]"
        hypothesis = _object(item, prefix, errors)
        hypothesis_id = _text(hypothesis.get("id"), f"{prefix}.id", errors)
        if hypothesis_id:
            if hypothesis_id in hypothesis_ids:
                errors.append(f"{prefix}.id is duplicated")
            hypothesis_ids.add(hypothesis_id)
        for key in ("statement", "null_hypothesis", "primary_outcome"):
            _text(hypothesis.get(key), f"{prefix}.{key}", errors)
        if not isinstance(hypothesis.get("confirmatory"), bool):
            errors.append(f"{prefix}.confirmatory must be boolean")

    _string_list(contract.get("datasets"), "datasets", errors)
    planned = _object(contract.get("planned_experiments"), "planned_experiments", errors)
    _string_list(planned.get("design_ids"), "planned_experiments.design_ids", errors)
    classes = set(
        _string_list(
            planned.get("baseline_classes"),
            "planned_experiments.baseline_classes",
            errors,
            minimum=3,
        )
    )
    if classes and not BASELINE_CLASSES.issubset(classes):
        errors.append("planned_experiments.baseline_classes must include simple, domain_standard and strong_recent")
    _string_list(planned.get("ablations"), "planned_experiments.ablations", errors)
    for key in (
        "primary_evaluation",
        "statistical_plan",
        "external_validity_plan",
        "reproducibility_plan",
    ):
        _text(planned.get(key), f"planned_experiments.{key}", errors)

    _string_list(contract.get("falsification_conditions"), "falsification_conditions", errors)
    independence = _object(contract.get("independence"), "independence", errors)
    _string_list(independence.get("unique_claim_ids"), "independence.unique_claim_ids", errors)
    _string_list(independence.get("shared_assets"), "independence.shared_assets", errors, minimum=0)
    _string_list(
        independence.get("overlap_with_other_papers"),
        "independence.overlap_with_other_papers",
        errors,
        minimum=0,
    )
    _text(independence.get("why_not_merge"), "independence.why_not_merge", errors)
    errors.extend(validate_venue_candidates(contract.get("target_venues")))
    return errors


def validate_experiment_design(
    design: dict[str, Any],
    expected_paper_id: str,
    plan_runs: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if design.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if design.get("status") != "ready_for_review":
        errors.append("status must be ready_for_review")
    if design.get("paper_id") != expected_paper_id:
        errors.append(f"paper_id must be {expected_paper_id}")
    _text(design.get("design_id"), "design_id", errors)
    _string_list(design.get("hypothesis_ids"), "hypothesis_ids", errors)
    run_ids = _string_list(design.get("run_ids"), "run_ids", errors)
    selected_runs: list[dict[str, Any]] = []
    for run_id in run_ids:
        run = plan_runs.get(run_id)
        if not run:
            errors.append(f"run_ids references unknown run {run_id}")
        elif run.get("paper_id") != expected_paper_id:
            errors.append(f"run {run_id} belongs to {run.get('paper_id')}, not {expected_paper_id}")
        else:
            selected_runs.append(run)
    stochastic = design.get("stochastic")
    if not isinstance(stochastic, bool):
        errors.append("stochastic must be boolean")
    seeds = _list(design.get("seeds"), "seeds", errors, minimum=3 if stochastic else 1)
    if seeds and any(not isinstance(seed, int) or isinstance(seed, bool) for seed in seeds):
        errors.append("seeds must contain only integers")
    if len(set(seeds)) != len(seeds):
        errors.append("seeds must be unique")
    if stochastic is True:
        planned_seeds = {run.get("seed") for run in selected_runs if isinstance(run.get("seed"), int)}
        if len(planned_seeds) < 3:
            errors.append("stochastic designs require at least three distinct planned run seeds")
        if seeds and set(seeds) != planned_seeds:
            errors.append("declared seeds must exactly match the linked planned run seeds")

    baselines = _list(design.get("baselines"), "baselines", errors, minimum=3)
    classes: set[str] = set()
    baseline_ids: set[str] = set()
    for index, item in enumerate(baselines):
        prefix = f"baselines[{index}]"
        baseline = _object(item, prefix, errors)
        baseline_id = _text(baseline.get("id"), f"{prefix}.id", errors)
        if baseline_id:
            if baseline_id in baseline_ids:
                errors.append(f"{prefix}.id is duplicated")
            baseline_ids.add(baseline_id)
        for key in (
            "rationale",
            "implementation_source",
            "version_or_commit",
            "license_or_terms",
            "tuning_budget",
        ):
            _text(baseline.get(key), f"{prefix}.{key}", errors)
        _https(baseline.get("primary_source_url"), f"{prefix}.primary_source_url", errors)
        category = baseline.get("class")
        if category not in BASELINE_CLASSES:
            errors.append(f"{prefix}.class must be simple, domain_standard or strong_recent")
        else:
            classes.add(category)
        publication_year = baseline.get("publication_year")
        if (
            not isinstance(publication_year, int)
            or isinstance(publication_year, bool)
            or not 1900 <= publication_year <= date.today().year
        ):
            errors.append(f"{prefix}.publication_year is invalid")
        elif category == "strong_recent" and publication_year < date.today().year - 5:
            errors.append(f"{prefix} strong_recent baseline must be from the last five years")
    if baselines and not BASELINE_CLASSES.issubset(classes):
        errors.append("baselines must cover simple, domain_standard and strong_recent comparators")

    fairness = _object(design.get("baseline_fairness"), "baseline_fairness", errors)
    for key in (
        "common_evaluation_protocol",
        "comparable_tuning_budget",
        "leakage_isolation",
        "implementation_verification",
    ):
        _text(fairness.get(key), f"baseline_fairness.{key}", errors)

    _string_list(design.get("ablations"), "ablations", errors)
    data = _object(design.get("data_protocol"), "data_protocol", errors)
    _string_list(data.get("datasets"), "data_protocol.datasets", errors)
    for key in (
        "split_unit",
        "split_strategy",
        "preprocessing_fit_scope",
        "external_validation",
    ):
        _text(data.get(key), f"data_protocol.{key}", errors)
    _string_list(data.get("leakage_controls"), "data_protocol.leakage_controls", errors, minimum=2)

    metrics = _object(design.get("metrics"), "metrics", errors)
    primary_metrics = _list(metrics.get("primary"), "metrics.primary", errors)
    for index, item in enumerate(primary_metrics):
        prefix = f"metrics.primary[{index}]"
        metric = _object(item, prefix, errors)
        for key in ("name", "direction", "aggregation", "uncertainty", "rationale"):
            _text(metric.get(key), f"{prefix}.{key}", errors)
    if not isinstance(metrics.get("secondary"), list):
        errors.append("metrics.secondary must be an array")

    statistics = _object(design.get("statistics"), "statistics", errors)
    for key in (
        "estimand",
        "unit_of_analysis",
        "effect_size",
        "confidence_interval",
        "test_or_model",
        "practical_significance_threshold",
        "multiplicity_control",
        "power_or_precision",
        "missing_data",
        "seed_aggregation",
    ):
        _text(statistics.get(key), f"statistics.{key}", errors)
    _string_list(statistics.get("assumption_checks"), "statistics.assumption_checks", errors)

    _string_list(design.get("robustness_checks"), "robustness_checks", errors, minimum=2)
    _string_list(design.get("negative_controls"), "negative_controls", errors)
    _string_list(design.get("falsification_criteria"), "falsification_criteria", errors)
    _string_list(design.get("stopping_rules"), "stopping_rules", errors)
    _text(design.get("failure_analysis"), "failure_analysis", errors)
    _text(design.get("claim_limits"), "claim_limits", errors)

    reproducibility = _object(design.get("reproducibility"), "reproducibility", errors)
    for key in ("environment_lock", "code_commit", "config_capture", "output_hashes"):
        _text(reproducibility.get(key), f"reproducibility.{key}", errors)
    return errors
