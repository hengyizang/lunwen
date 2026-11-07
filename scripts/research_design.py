#!/usr/bin/env python3
"""Deterministic validators for doctoral novelty and paper-level study design.

These checks validate explicit evidence and design structure. They do not prove
novelty, doctoral merit, reliability, or journal acceptance. Independent scientific
audits assess meaning; G1/G2 topic decisions and external author obligations remain
human responsibilities. Other stage decisions use evidence-bound automated checks.
"""
from __future__ import annotations

import itertools
import math
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable


PAPER_RE = re.compile(r"^P[0-9]{2}$")
DATE_RE = re.compile(r"^20[0-9]{2}-[01][0-9]-[0-3][0-9]$")
VENUE_QUARTILES = {"Q1", "Q2"}
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


def _planning_quartile(value: Any, field: str, errors: list[str]) -> None:
    """Optional rank metadata never supplies a scientific quality threshold."""
    if value is not None and (not isinstance(value, str) or value not in {"Q1", "Q2", "Q3", "Q4", "unknown"}):
        errors.append(f"{field} must be Q1-Q4, unknown or null when supplied")


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


def validate_negative_result_plan(value: Any, field: str = "negative_result_plan") -> list[str]:
    """Require an information/precision boundary, never a promise of publication."""
    errors: list[str] = []
    plan = _object(value, field, errors)
    for key in ("informative_if_unsupported", "precision_limitations", "stop_rule", "claim_boundary"):
        _text(plan.get(key), f"{field}.{key}", errors)
    return errors


def validate_scientific_bindings(contract: dict[str, Any]) -> list[str]:
    """Bind G2 wording to explicit G3 comparisons without running experiments."""
    errors: list[str] = []
    value = _object(contract.get("scientific_bindings"), "scientific_bindings (migration required)", errors)
    if value.get("schema_version") != "1.0":
        errors.append("scientific_bindings.schema_version must be 1.0; migrate the scientific contract explicitly")
    original_hypotheses = contract.get("hypotheses")
    hypotheses = {h.get("id"): h for h in original_hypotheses if isinstance(h, dict) and isinstance(h.get("id"), str)} if isinstance(original_hypotheses, list) else {}
    empirical = contract.get("study_route", "empirical") == "empirical"
    bindings = _list(value.get("hypotheses"), "scientific_bindings.hypotheses", errors, minimum=int(empirical))
    conditions = _list(value.get("falsification_conditions"), "scientific_bindings.falsification_conditions", errors, minimum=int(empirical))
    by_id: dict[str, dict] = {}
    statements: list[str] = []
    for index, item in enumerate(conditions):
        prefix = f"scientific_bindings.falsification_conditions[{index}]"
        condition = _object(item, prefix, errors)
        key = _text(condition.get("condition_id"), prefix + ".condition_id", errors)
        if key in by_id:
            errors.append(prefix + ".condition_id is duplicated")
        if key:
            by_id[key] = condition
        statement = _text(condition.get("statement"), prefix + ".statement", errors)
        if statement:
            statements.append(statement)
        if not isinstance(condition.get("hypothesis_id"), str) or condition["hypothesis_id"] not in hypotheses:
            errors.append(prefix + ".hypothesis_id must name a contracted hypothesis")
        _text(condition.get("metric"), prefix + ".metric", errors)
        _text(condition.get("rationale"), prefix + ".rationale", errors)
        if condition.get("decision_rule") not in {"superiority", "equivalence"}:
            errors.append(prefix + ".decision_rule has no reviewed comparison adapter")
        threshold = condition.get("threshold")
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold < 0:
            errors.append(prefix + ".threshold must be a finite nonnegative effect threshold")
    original_conditions = contract.get("falsification_conditions")
    if empirical and (not isinstance(original_conditions, list) or any(not isinstance(s, str) for s in original_conditions)
                      or sorted(statements) != sorted(original_conditions)):
        errors.append("scientific_bindings conditions must preserve every exact contracted falsification statement")
    seen: set[str] = set()
    used: set[str] = set()
    for index, item in enumerate(bindings):
        prefix = f"scientific_bindings.hypotheses[{index}]"
        binding = _object(item, prefix, errors)
        key = binding.get("hypothesis_id")
        if not isinstance(key, str) or key not in hypotheses or key in seen:
            errors.append(prefix + ".hypothesis_id must uniquely name a contracted hypothesis")
        else:
            seen.add(key)
            if binding.get("primary_outcome_statement") != hypotheses[key].get("primary_outcome"):
                errors.append(prefix + ".primary_outcome_statement differs from the original primary outcome")
        for field in ("primary_metric", "aggregation", "rationale"):
            _text(binding.get(field), prefix + "." + field, errors)
        if binding.get("direction") not in {"higher", "lower"}:
            errors.append(prefix + ".direction must be higher or lower")
        if binding.get("decision_rule") not in {"superiority", "equivalence"}:
            errors.append(prefix + ".decision_rule has no reviewed comparison adapter")
        effect = binding.get("minimum_effect")
        if type(effect) not in (int, float) or not math.isfinite(effect) or effect < 0:
            errors.append(prefix + ".minimum_effect must be a finite nonnegative number")
        elif binding.get("decision_rule") == "equivalence" and effect <= 0:
            errors.append(prefix + ".minimum_effect needs a positive equivalence margin")
        selected = _string_list(binding.get("condition_ids"), prefix + ".condition_ids", errors)
        own = {cid for cid, condition in by_id.items() if condition.get("hypothesis_id") == key}
        if set(selected) != own:
            errors.append(prefix + ".condition_ids must cover every condition of this hypothesis exactly")
        used.update(selected)
        if not any(by_id[cid].get("metric") == binding.get("primary_metric")
                   and by_id[cid].get("decision_rule") == binding.get("decision_rule")
                   and by_id[cid].get("threshold") == effect for cid in selected if cid in by_id):
            errors.append(prefix + " needs a falsification condition for its exact primary comparison")
    if seen != set(hypotheses) or used != set(by_id):
        errors.append("scientific_bindings must cover all hypotheses and conditions without orphan records")
    return errors


def _paper_dependencies(papers: list[dict], expected: set[str], errors: list[str]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for row in papers:
        if not isinstance(row, dict) or not isinstance(row.get("paper_id"), str) or row["paper_id"] not in expected:
            continue
        pid = row["paper_id"]
        parents = _string_list(row.get("dependencies"), pid + ".dependencies", errors, minimum=0)
        graph[pid] = parents
        if pid in parents or set(parents) - expected:
            errors.append(pid + ".dependencies contain a self-reference or unknown paper")
    visiting, done = set(), set()
    def visit(pid):
        if pid in visiting:
            errors.append("paper dependencies must be acyclic: " + pid)
            return
        if pid in done:
            return
        visiting.add(pid)
        for parent in graph.get(pid, []):
            if parent in expected:
                visit(parent)
        visiting.remove(pid)
        done.add(pid)
    for pid in graph:
        visit(pid)
    return graph


def validate_venue_candidates(
    value: Any,
    field: str = "target_venues",
    target_quartile: str = "Q1",
) -> list[str]:
    errors: list[str] = []
    candidates = _list(value, field, errors, minimum=2)
    try:
        from scripts.venue_policy import meets_target, normalize_quartile
    except ImportError:
        from venue_policy import meets_target, normalize_quartile
    target = normalize_quartile(target_quartile)
    if target is None:
        errors.append(f"{field} target quartile must be Q1 or Q2")
        target = "Q1"
    for index, item in enumerate(candidates):
        prefix = f"{field}[{index}]"
        venue = _object(item, prefix, errors)
        if not venue:
            continue
        for key in ("name", "category", "scope_fit", "article_type"):
            _text(venue.get(key), f"{prefix}.{key}", errors)
        quartile = venue.get("quartile")
        if quartile not in VENUE_QUARTILES or not meets_target(quartile, target):
            errors.append(f"{prefix}.quartile must meet the current JCR {target} target")
        if venue.get("indexing") not in {"SCI", "SCIE"}:
            errors.append(f"{prefix}.indexing must be SCI or SCIE")
        year = venue.get("jcr_year")
        if not isinstance(year, int) or isinstance(year, bool) or year not in {date.today().year,date.today().year-1}:
            errors.append(f"{prefix}.jcr_year must identify the current or immediately previous JCR edition")
        _https(venue.get("source_url"), f"{prefix}.source_url", errors)
    return errors


def validate_thesis_theme(value: dict[str, Any], expected_theme_id: str) -> list[str]:
    """Validate the minimum falsifiable contract for thesis theme A or B."""

    errors: list[str] = []
    if value.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if value.get("theme_id") != expected_theme_id:
        errors.append(f"theme_id must be {expected_theme_id}")
    if value.get("status") not in {"ready_for_review", "approved"}:
        errors.append("status must be ready_for_review or approved")
    for key in ("title", "doctoral_question", "distinct_contribution"):
        _text(value.get(key), key, errors)
    errors.extend(validate_negative_result_plan(value.get("negative_result_plan")))
    _string_list(value.get("novelty_claim_ids"), "novelty_claim_ids", errors, minimum=2)
    paper_ids = _string_list(value.get("planned_paper_ids"), "planned_paper_ids", errors)
    for paper_id in paper_ids:
        if not PAPER_RE.fullmatch(paper_id):
            errors.append(f"planned_paper_ids contains an invalid paper ID: {paper_id}")
    _string_list(value.get("falsification_conditions"), "falsification_conditions", errors, minimum=2)
    if value.get("human_review_required") is not True:
        errors.append("human_review_required must be true")
    if expected_theme_id == "B":
        _text(value.get("mechanism_or_rationale"), "mechanism_or_rationale", errors)
        _string_list(
            value.get("independent_evidence_plan"),
            "independent_evidence_plan",
            errors,
            minimum=2,
        )
        _string_list(value.get("boundary_conditions"), "boundary_conditions", errors)
        _text(value.get("fallback_if_unsupported"), "fallback_if_unsupported", errors)
        relationship = _object(value.get("relationship_to_core"), "relationship_to_core", errors)
        _string_list(
            relationship.get("shared_foundation"),
            "relationship_to_core.shared_foundation",
            errors,
            minimum=0,
        )
        for key in (
            "independent_question",
            "independent_claims",
            "independent_primary_evidence",
            "survives_core_failure",
        ):
            if relationship.get(key) is not True:
                errors.append(f"relationship_to_core.{key} must be true")
        _text(
            relationship.get("non_dependency_rationale"),
            "relationship_to_core.non_dependency_rationale",
            errors,
        )
    return errors


def validate_theme_independence(
    core: dict[str, Any], extension: dict[str, Any]
) -> list[str]:
    """Make theme B independence a deterministic G1/G2 blocking condition."""

    errors = [f"core: {item}" for item in validate_thesis_theme(core, "A")]
    errors.extend(f"extension: {item}" for item in validate_thesis_theme(extension, "B"))
    core_claims = set(str(item) for item in core.get("novelty_claim_ids", [])) if isinstance(core.get("novelty_claim_ids"), list) else set()
    extension_claims = set(str(item) for item in extension.get("novelty_claim_ids", [])) if isinstance(extension.get("novelty_claim_ids"), list) else set()
    overlap = sorted(core_claims & extension_claims)
    if overlap:
        errors.append("theme A and B novelty claim IDs must be disjoint: " + ", ".join(overlap))
    core_papers = set(str(item) for item in core.get("planned_paper_ids", [])) if isinstance(core.get("planned_paper_ids"), list) else set()
    extension_papers = set(str(item) for item in extension.get("planned_paper_ids", [])) if isinstance(extension.get("planned_paper_ids"), list) else set()
    paper_overlap = sorted(core_papers & extension_papers)
    if paper_overlap:
        errors.append("theme A and B planned papers must be disjoint: " + ", ".join(paper_overlap))
    core_question = str(core.get("doctoral_question", "")).strip().casefold()
    extension_question = str(extension.get("doctoral_question", "")).strip().casefold()
    if core_question and core_question == extension_question:
        errors.append("theme B must have a doctoral question distinct from theme A")
    return errors


def validate_theme_mapping(
    paper_map: dict[str, Any], core: dict[str, Any], extension: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    papers = paper_map.get("papers") if isinstance(paper_map.get("papers"), list) else []
    by_theme: dict[str, dict[str, set[str]]] = {
        "A": {"papers": set(), "claims": set()},
        "B": {"papers": set(), "claims": set()},
    }
    for index, item in enumerate(papers):
        if not isinstance(item, dict):
            continue
        theme_id = item.get("theme_id")
        if theme_id not in by_theme:
            errors.append(f"papers[{index}].theme_id must be A or B")
            continue
        paper_id = item.get("paper_id")
        if isinstance(paper_id, str):
            by_theme[theme_id]["papers"].add(paper_id)
        claims = item.get("unique_claim_ids")
        if isinstance(claims, list):
            by_theme[theme_id]["claims"].update(str(claim) for claim in claims)
    for theme_id, contract in (("A", core), ("B", extension)):
        planned_values = contract.get("planned_paper_ids")
        planned = set(str(item) for item in planned_values) if isinstance(planned_values, list) else set()
        if by_theme[theme_id]["papers"] != planned:
            errors.append(f"theme {theme_id} paper-map assignments must exactly match planned_paper_ids")
        claim_values = contract.get("novelty_claim_ids")
        required_claims = set(str(item) for item in claim_values) if isinstance(claim_values, list) else set()
        missing = sorted(required_claims - by_theme[theme_id]["claims"])
        if missing:
            errors.append(f"theme {theme_id} paper-map claims omit: {', '.join(missing)}")
    return errors


def validate_selected_direction_cloud_feasibility(shortlist: dict[str, Any], project: Path | None = None) -> list[str]:
    """Block G1 until the selected direction has a cloud-only current-paper path."""

    errors: list[str] = []
    feasibility = _object(shortlist.get("selected_direction_cloud_feasibility"), "selected_direction_cloud_feasibility", errors)
    for key in ("current_papers_feasible", "no_future_lab_dependency"):
        if feasibility.get(key) is not True:
            errors.append(f"selected_direction_cloud_feasibility.{key} must be true")
    for key in ("authorized_data_plan", "cloud_experiment_plan", "current_paper_scope"):
        _text(feasibility.get(key), f"selected_direction_cloud_feasibility.{key}", errors)
    candidates = shortlist.get("candidates")
    ids = [row.get("candidate_id", row.get("id")) for row in candidates if isinstance(row, dict)] if isinstance(candidates, list) else []
    if len(ids) < 3 or any(not isinstance(key, str) or not key.strip() for key in ids) or len(set(ids)) != len(ids):
        errors.append("candidates need at least three distinct candidate_id values")
    decision = _object(shortlist.get("selection_decision"), "selection_decision (migration required)", errors)
    chosen, rival = decision.get("chosen_candidate_id"), decision.get("strongest_rival_candidate_id")
    if not isinstance(chosen, str) or chosen not in ids:
        errors.append("selection_decision.chosen_candidate_id must name a listed candidate")
    if not isinstance(rival, str) or rival not in ids or rival == chosen:
        errors.append("selection_decision.strongest_rival_candidate_id must name another listed candidate")
    for key in ("why_selected_over_rival", "change_of_mind_evidence"):
        _text(decision.get(key), "selection_decision." + key, errors)
    evidence = _object(feasibility.get("feasibility_evidence"), "feasibility_evidence (migration required)", errors)
    for kind in ("data_access", "research_rights", "compute_cost"):
        anchors = _list(evidence.get(kind), "feasibility_evidence." + kind, errors)
        for index, item in enumerate(anchors):
            prefix = f"feasibility_evidence.{kind}[{index}]"
            anchor = _object(item, prefix, errors)
            for key in ("path", "locator", "quote"):
                _text(anchor.get(key), prefix + "." + key, errors)
            if not re.fullmatch(r"[a-f0-9]{64}", str(anchor.get("sha256", ""))):
                errors.append(prefix + ".sha256 must bind saved source bytes")
            if project is not None:
                try:
                    from scripts.research_artifacts import bound_source, path_in
                    from scripts.output_provenance import current_origin
                    bound_source(project, anchor)
                    source = path_in(project, anchor["path"])
                    origin = current_origin(project, source)
                    if (origin.get("status") != "tracked" or origin.get("family") != "other"
                            or not (str(origin.get("provider", "")).startswith("deterministic-")
                                    or origin.get("provider") == "human-attestation")):
                        raise ValueError("feasibility evidence needs current acquired/local/supplied provenance, not model self-attestation")
                    content = source.read_text(encoding="utf-8")
                    if not isinstance(anchor.get("quote"), str) or not anchor["quote"].strip() or anchor["quote"] not in content:
                        raise ValueError("quoted feasibility evidence is not in the saved source")
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    errors.append(prefix + ": " + str(exc))
    pilot = _object(evidence.get("pilot"), "feasibility_evidence.pilot", errors)
    if pilot.get("status") in {"unknown", "not_run"}:
        _text(pilot.get("limitation"), "feasibility_evidence.pilot.limitation", errors)
    elif pilot.get("status") == "executed":
        attempt = _text(pilot.get("attempt_id"), "feasibility_evidence.pilot.attempt_id", errors)
        if project is None:
            errors.append("executed pilot needs project-bound executor verification")
        else:
            try:
                from scripts.research_artifacts import read, path_in, sha
                import json
                registry = path_in(project, "experiments/registry.jsonl")
                matches = [row for line in registry.read_text(encoding="utf-8").splitlines() if line.strip()
                           for row in [json.loads(line)] if row.get("attempt_id") == attempt]
                if not isinstance(attempt, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", attempt) or len(matches) != 1:
                    raise ValueError("executed pilot needs one real registered attempt")
                row = matches[0]
                if row.get("status") != "succeeded" or row.get("input_integrity", {}).get("passed") is not True:
                    raise ValueError("pilot has no successful integrity-checked execution")
                if read(path_in(project, f"experiments/runs/{attempt}/run.json")) != row or not row.get("outputs"):
                    raise ValueError("pilot receipt or outputs are missing")
                for output in row["outputs"]:
                    if sha(path_in(project, output["path"])) != output.get("sha256"):
                        raise ValueError("pilot output is missing or changed")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                errors.append("feasibility_evidence.pilot: " + str(exc))
    else:
        errors.append("feasibility_evidence.pilot.status must be unknown, not_run or executed")
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
        if record.get("schema_version") != "1.1":
            errors.append(f"{prefix}.schema_version must be 1.1")
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
        _text(record.get("evidence_receipt_id"), f"{prefix}.evidence_receipt_id", errors)
        for hash_field in ("response_sha256", "normalized_results_sha256"):
            value = record.get(hash_field)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                errors.append(f"{prefix}.{hash_field} must be a SHA-256 digest")
        _text(record.get("screened_by"), f"{prefix}.screened_by", errors)
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
        if paper.get("theme_id") not in {"A", "B"}:
            errors.append(f"{prefix}.theme_id must be A or B")
        _planning_quartile(paper.get("target_jcr_quartile"), f"{prefix}.target_jcr_quartile", errors)
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
    _paper_dependencies(papers, set(expected), errors)
    # Quartile targets describe the user's portfolio ambition. Evidence-led
    # scientific independence is not decided by a venue rank/count threshold.

    cumulative_mode = value.get("independence_basis") == "cumulative"
    if value.get("independence_basis", "legacy_pairwise") not in {"cumulative", "legacy_pairwise"}:
        errors.append("independence_basis must be cumulative or legacy_pairwise")
    required_pairs = {tuple(pair) for pair in itertools.combinations(expected, 2)}
    found_pairs: set[tuple[str, str]] = set()
    comparisons = _list(
        value.get("pairwise_distinctness", []),
        "pairwise_distinctness",
        errors,
        minimum=0 if cumulative_mode else len(required_pairs),
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
    if missing_pairs and not cumulative_mode:
        errors.append(
            "pairwise_distinctness is missing: "
            + ", ".join(f"{left}/{right}" for left, right in missing_pairs)
        )

    synthesis = _object(value.get("thesis_synthesis"), "thesis_synthesis", errors)
    if cumulative_mode:
        contributions = _list(synthesis.get("cumulative_contributions"), "thesis_synthesis.cumulative_contributions", errors, minimum=len(expected))
        by_paper = {row.get("paper_id"): row for row in papers if isinstance(row, dict)}
        contribution_papers = []
        for index, item in enumerate(contributions):
            prefix = f"thesis_synthesis.cumulative_contributions[{index}]"
            item = _object(item, prefix, errors)
            pid = item.get("paper_id")
            contribution_papers.append(pid)
            if not isinstance(pid, str) or pid not in by_paper:
                errors.append(prefix + ".paper_id must identify a declared paper")
                continue
            ids = _string_list(item.get("claim_ids"), prefix + ".claim_ids", errors)
            if set(ids) != set(by_paper[pid].get("unique_claim_ids", [])):
                errors.append(prefix + ".claim_ids must cover this paper's exact unique claims")
            for key in ("knowledge_increment", "standalone_value", "merge_trigger"):
                _text(item.get(key), prefix + "." + key, errors)
            _string_list(item.get("primary_evidence"), prefix + ".primary_evidence", errors)
        if sorted(str(p) for p in contribution_papers) != expected:
            errors.append("cumulative_contributions must cover every paper exactly once")
    for key in (
        "core_thesis",
        "extension_thesis",
        "cumulative_progression",
        "integrated_contribution",
        "dependency_logic",
    ):
        _text(synthesis.get(key), f"thesis_synthesis.{key}", errors)
    links = _list(synthesis.get("argument_links"), "thesis_synthesis.argument_links (migration required)", errors)
    covered: set[str] = set()
    steps: set[str] = set()
    for index, item in enumerate(links):
        prefix = f"thesis_synthesis.argument_links[{index}]"
        link = _object(item, prefix, errors)
        step = _text(link.get("step_id"), prefix + ".step_id", errors)
        if step in steps:
            errors.append(prefix + ".step_id is duplicated")
        if step:
            steps.add(step)
        for key in ("contribution", "what_changes_if_unsupported"):
            _text(link.get(key), prefix + "." + key, errors)
        claims = _string_list(link.get("claim_ids"), prefix + ".claim_ids", errors)
        if set(claims) - global_claim_ids:
            errors.append(prefix + ".claim_ids reference an unknown portfolio claim")
        covered.update(claims)
    for row in papers:
        if isinstance(row, dict):
            claims = row.get("unique_claim_ids")
            if not isinstance(claims, list) or not any(isinstance(claim, str) and claim in covered for claim in claims):
                errors.append(str(row.get("paper_id")) + " needs a claim in thesis_synthesis.argument_links")
    return errors


def validate_paper_contract(contract: dict[str, Any], expected_paper_id: str, *, study_route: str = "empirical") -> list[str]:
    errors: list[str] = []
    if study_route not in {"empirical", "meta_analysis", "theory"}:
        return ["unknown study route"]
    if contract.get("study_route", "empirical") != study_route:
        errors.append("paper contract study_route must match its actual research identity")
    if contract.get("schema_version") != "2.0":
        errors.append("schema_version must be 2.0")
    if contract.get("paper_id") != expected_paper_id:
        errors.append(f"paper_id must be {expected_paper_id}")
    if contract.get("writing_language") != "en":
        errors.append("writing_language must be en")
    _planning_quartile(contract.get("target_jcr_quartile"), "target_jcr_quartile", errors)
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

    feasibility = _object(contract.get("cloud_feasibility"), "cloud_feasibility", errors)
    for key in ("current_paper_cloud_executable", "no_future_lab_dependency"):
        if feasibility.get(key) is not True:
            errors.append(f"cloud_feasibility.{key} must be true")
    for key in ("data_access_plan", "cloud_execution_plan", "evidence_and_claim_scope"):
        _text(feasibility.get(key), f"cloud_feasibility.{key}", errors)

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

    hypotheses = _list(contract.get("hypotheses"), "hypotheses", errors, minimum=1 if study_route == "empirical" else 0)
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

    _string_list(contract.get("datasets"), "datasets", errors, minimum=1 if study_route == "empirical" else 0)
    planned = _object(contract.get("planned_experiments"), "planned_experiments", errors)
    _string_list(planned.get("design_ids"), "planned_experiments.design_ids", errors)
    classes = set(
        _string_list(
            planned.get("baseline_classes"),
            "planned_experiments.baseline_classes",
            errors,
            minimum=3 if study_route == "empirical" else 0,
        )
    )
    if study_route == "empirical" and classes and not BASELINE_CLASSES.issubset(classes):
        errors.append("planned_experiments.baseline_classes must include simple, domain_standard and strong_recent")
    _string_list(planned.get("ablations"), "planned_experiments.ablations", errors, minimum=1 if study_route == "empirical" else 0)
    for key in (
        "primary_evaluation",
        "statistical_plan",
        "external_validity_plan",
        "reproducibility_plan",
    ):
        _text(planned.get(key), f"planned_experiments.{key}", errors)

    _string_list(contract.get("falsification_conditions"), "falsification_conditions", errors)
    errors.extend(validate_negative_result_plan(contract.get("negative_result_plan")))
    errors.extend(validate_scientific_bindings({**contract, "study_route": study_route}))
    parents = _string_list(contract.get("dependencies"), "dependencies", errors, minimum=0)
    if expected_paper_id in parents or any(not PAPER_RE.fullmatch(pid) for pid in parents):
        errors.append("dependencies must name other exact paper IDs")
    bindings = _list(contract.get("dependency_bindings"), "dependency_bindings (migration required)", errors, minimum=0)
    seen_parents = set()
    for index, item in enumerate(bindings):
        prefix = f"dependency_bindings[{index}]"
        binding = _object(item, prefix, errors)
        parent = binding.get("paper_id")
        if not isinstance(parent, str) or parent not in parents or parent in seen_parents:
            errors.append(prefix + ".paper_id must uniquely bind one declared dependency")
        if isinstance(parent, str):
            seen_parents.add(parent)
        if binding.get("kind") not in {"scientific_premise", "shared_asset"}:
            errors.append(prefix + ".kind must identify a scientific premise or shared asset")
        _string_list(binding.get("claim_ids"), prefix + ".claim_ids", errors,
                     minimum=1 if binding.get("kind") == "scientific_premise" else 0)
        _string_list(binding.get("node_ids"), prefix + ".node_ids", errors)
        for key in ("graph_id", "rationale", "inherited_scope"):
            _text(binding.get(key), prefix + "." + key, errors)
    if seen_parents != set(parents):
        errors.append("dependency_bindings must explain every declared paper dependency")
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
    # Candidates can be incomplete while the scientific question is decided.
    # The explicit venue diagnostic remains available; submission fit uses actual
    # publisher evidence, never a model-filled count or JCR floor as merit.
    if not isinstance(contract.get("target_venues", []), list):
        errors.append("target_venues must be an array of provisional candidates")
    else:
        for index, item in enumerate(contract.get("target_venues", [])):
            field = f"target_venues[{index}]"
            venue = _object(item, field, errors)
            _text(venue.get("name"), field + ".name", errors)
            _planning_quartile(venue.get("quartile"), field + ".quartile", errors)
    return errors


def validate_portfolio_evidence(project: Path, paper_id: str | None = None, gate: str = "G5") -> list[str]:
    """Join the existing portfolio/claim/lineage records, without new result state.

    G2 checks declared relationships. G5 checks only the current paper's actual
    contribution and dependencies; an upstream paper need not be submission-ready.
    """
    from scripts.research_artifacts import read, path_in
    errors: list[str] = []
    try:
        state = read(path_in(project, "state/run.json"))
        expected = {f"P{n:02d}" for n in range(1, int(state["paper_count"]) + 1)}
        mapping = read(path_in(project, "program/paper-map.json"))
        errors.extend(validate_paper_map(mapping, expected))
        rows = {row["paper_id"]: row for row in mapping.get("papers", []) if isinstance(row, dict) and row.get("paper_id") in expected}
        contracts = {pid: read(path_in(project, f"papers/{pid}/paper-contract.json")) for pid in expected}
        for pid, contract in contracts.items():
            if set(contract.get("dependencies", [])) != set(rows.get(pid, {}).get("dependencies", [])):
                errors.append(pid + ": paper-map and contract dependencies disagree")
        if gate != "G5" or errors:
            return errors
        if paper_id not in expected:
            return ["portfolio evidence needs the current exact paper ID"]
        from scripts.results_validation import claim_outcomes
        actual = claim_outcomes(project, paper_id)
        owners = {claim: pid for pid, row in rows.items() for claim in row.get("unique_claim_ids", [])}
        synthesis = mapping["thesis_synthesis"]
        required = {claim for link in synthesis["argument_links"] for claim in link["claim_ids"]
                    if owners.get(claim) == paper_id}
        alignments = _list(synthesis.get("evidence_alignment"), "thesis_synthesis.evidence_alignment", errors)
        selected: dict[str, dict] = {}
        for index, value in enumerate(alignments):
            row = _object(value, f"thesis_synthesis.evidence_alignment[{index}]", errors)
            claim = row.get("claim_id")
            if not isinstance(claim, str) or claim not in owners:
                errors.append("thesis evidence alignment references an unknown claim")
            elif owners[claim] == paper_id:
                if claim in selected:
                    errors.append("duplicate current-paper thesis evidence alignment: " + claim)
                selected[claim] = row
        if not required <= set(selected):
            errors.append(paper_id + ": thesis synthesis lacks current actual claim outcomes")
        for claim, row in selected.items():
            outcome = actual["claims"].get(claim)
            if outcome is None:
                errors.append("thesis claim has no registered outcome: " + claim)
                continue
            if row.get("result_status") != outcome["result_status"] or sorted(row.get("comparison_ids", [])) != sorted(outcome["comparison_ids"]):
                errors.append("thesis synthesis contradicts actual claim outcome/comparisons: " + claim)
            if any(row.get(key) != actual[key] for key in ("claim_matrix_sha256", "evidence_plan_sha256")):
                errors.append("thesis evidence alignment has stale result bindings: " + claim)
            if row.get("disposition") not in {"retain", "narrow", "reframe", "unsupported"}:
                errors.append("thesis alignment needs an explicit evidence interpretation: " + claim)
            elif outcome["result_status"] in {"not_supported", "contradicted", "inconclusive"} and row["disposition"] == "retain":
                errors.append("adverse/uncertain evidence cannot retain the original thesis success narrative: " + claim)
            _text(row.get("claim_boundary"), "thesis alignment claim_boundary: " + claim, errors)

        contract = contracts[paper_id]
        parents = contract.get("dependencies", [])
        bindings = contract.get("dependency_bindings", [])
        if not isinstance(bindings, list) or {row.get("paper_id") for row in bindings if isinstance(row, dict)} != set(parents):
            errors.append(paper_id + ": every paper dependency needs its typed evidence binding")
            return errors
        if bindings:
            from scripts import research_increments as increments
            graphs = {row["id"]: row for row in increments.load(project)["dependencies"]}
            for binding in bindings:
                parent = binding["paper_id"]
                if parent not in expected or parent == paper_id:
                    errors.append(paper_id + ": invalid dependency parent")
                    continue
                graph = increments.dependencies(project, graphs[binding["graph_id"]])
                nodes = {row["id"]: row for row in graph["nodes"]}
                chosen = set(binding["node_ids"])
                if not chosen or not chosen <= set(nodes):
                    errors.append(paper_id + ": dependency needs exact existing graph nodes")
                    continue
                closure = set(chosen)
                pending = list(chosen)
                while pending:
                    for ancestor in nodes[pending.pop()].get("depends_on", []):
                        if ancestor not in closure:
                            closure.add(ancestor)
                            pending.append(ancestor)
                if any(key in graph["stale"] for key in chosen):
                    errors.append(paper_id + ": dependency evidence changed; review the affected inherited claim/asset")
                if not any(paper_id in nodes[key]["paper_ids"] for key in chosen) or not any(parent in nodes[key]["paper_ids"] for key in closure):
                    errors.append(paper_id + ": dependency graph does not bind consumer and source paper")
                if binding["kind"] == "scientific_premise":
                    parent_actual = claim_outcomes(project, parent)
                    claims = binding["claim_ids"]
                    if not claims or any(owners.get(cid) != parent or parent_actual["claims"].get(cid, {}).get("result_status") != "supported" for cid in claims):
                        errors.append(paper_id + ": inherited scientific premise is unsupported, changed or unknown; reassess its scope")
                elif binding["kind"] == "shared_asset":
                    if not any(nodes[key]["kind"] == "shared_asset" and parent in nodes[key]["paper_ids"] for key in closure):
                        errors.append(paper_id + ": shared-asset dependency needs an actual declared shared asset node")
                else:
                    errors.append(paper_id + ": unknown dependency kind")
        return errors
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        return [*errors, "portfolio evidence: " + str(exc)]


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
    selection = _object(data.get("model_selection"), "data_protocol.model_selection (migration required)", errors)
    _text(selection.get("rationale"), "data_protocol.model_selection.rationale", errors)
    status = selection.get("status")
    if status not in {"tuned", "not_tuned", "not_applicable"}:
        errors.append("data_protocol.model_selection.status must be tuned, not_tuned or not_applicable")
    if status == "tuned":
        if selection.get("selection_split") not in {"training", "validation", "nested_cross_validation"}:
            errors.append("model selection must use training/validation/nested cross-validation, never test/final/holdout data")
        _text(selection.get("selection_metric"), "data_protocol.model_selection.selection_metric", errors)
        space = _object(selection.get("search_space"), "data_protocol.model_selection.search_space", errors)
        if not space:
            errors.append("tuned model selection needs its declared parameter search space")
        for key, values in space.items():
            if (not isinstance(key, str) or not key.strip() or not isinstance(values, list) or not values
                    or any(type(v) not in (str, int, float, bool) or (type(v) is float and not math.isfinite(v)) for v in values)):
                errors.append("model_selection.search_space must map parameter names to explicit finite candidate values")
        tuning_runs = _string_list(selection.get("run_ids"), "data_protocol.model_selection.run_ids", errors)
        if not set(tuning_runs) <= set(run_ids):
            errors.append("model_selection.run_ids must belong to this declared paper design")
    elif selection.get("run_ids") or selection.get("search_space") or selection.get("selection_split") not in {None, "none"}:
        errors.append("untuned/not-applicable selection must not invent tuning runs, a search space or a selection split")

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
    reproduction = _object(design.get("reproduction_plan"), "reproduction_plan", errors)
    baseline_runs = _object(reproduction.get("baseline_runs"), "reproduction_plan.baseline_runs", errors)
    domain_runs = _string_list(
        baseline_runs.get("domain_standard"),
        "reproduction_plan.baseline_runs.domain_standard",
        errors,
    )
    recent_runs = _string_list(
        baseline_runs.get("strong_recent"),
        "reproduction_plan.baseline_runs.strong_recent",
        errors,
    )
    original_runs = _string_list(
        reproduction.get("original_run_ids"),
        "reproduction_plan.original_run_ids",
        errors,
    )
    clean_runs = _string_list(
        reproduction.get("clean_room_run_ids"),
        "reproduction_plan.clean_room_run_ids",
        errors,
    )
    declared = set(run_ids)
    referenced = set(domain_runs + recent_runs + original_runs + clean_runs)
    unknown_reproduction_runs = sorted(referenced - declared)
    if unknown_reproduction_runs:
        errors.append(
            "reproduction_plan references runs outside this design: "
            + ", ".join(unknown_reproduction_runs)
        )
    if set(original_runs) & set(clean_runs):
        errors.append("reproduction_plan original and clean-room run IDs must be disjoint")
    for run_id in clean_runs:
        run = plan_runs.get(run_id)
        isolation = run.get("isolation") if isinstance(run, dict) else None
        if not isinstance(isolation, dict) or isolation.get("kind") != "container":
            errors.append(
                f"clean-room run {run_id} must use digest-pinned container isolation"
            )
    for key in (
        "independent_operator_plan",
        "isolated_environment_plan",
        "environment_capture_plan",
    ):
        _text(reproduction.get(key), f"reproduction_plan.{key}", errors)
    tolerances = _list(
        reproduction.get("metric_tolerances"),
        "reproduction_plan.metric_tolerances",
        errors,
    )
    for index, item in enumerate(tolerances):
        prefix = f"reproduction_plan.metric_tolerances[{index}]"
        tolerance = _object(item, prefix, errors)
        _text(tolerance.get("metric"), f"{prefix}.metric", errors)
        _text(tolerance.get("rationale"), f"{prefix}.rationale", errors)
        value = tolerance.get("absolute_tolerance")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            errors.append(f"{prefix}.absolute_tolerance must be non-negative")
    return errors
