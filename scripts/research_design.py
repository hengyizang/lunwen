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

from scripts.research_artifacts import schema_errors


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
    """One schema is authoritative for each falsifiable theme contract."""
    if expected_theme_id not in {"A", "B"}:
        return ["theme_id must be A or B"]
    name = "core-thesis" if expected_theme_id == "A" else "extension-thesis"
    return schema_errors(value, name + ".schema.json")


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
    for kind in ("data_access", "compute_cost"):
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


def _record_date(value, field: str, *, timestamp=False) -> list[str]:
    text = value[:10] if timestamp and isinstance(value, str) else value
    if not isinstance(text, str) or not DATE_RE.fullmatch(text):
        return [field + " must use YYYY-MM-DD" + (" or begin with that date" if timestamp else "")]
    try:
        actual = date.fromisoformat(text)
    except ValueError:
        return [field + " is not a real calendar date"]
    return [field + " must not be in the future"] if actual > date.today() else []


def validate_originality_audit(audit: dict[str, Any]) -> list[str]:
    errors = schema_errors(audit, "originality-audit.schema.json")
    if errors:
        return errors
    errors.extend(_record_date(audit["search_scope"]["cutoff_date"], "search_scope.cutoff_date"))
    work_ids, claim_ids = set(), set()
    works = audit["closest_prior_work"]
    for index, work in enumerate(works):
        identifier = work["id"].strip()
        if identifier in work_ids:
            errors.append(f"closest_prior_work[{index}].id is duplicated")
        work_ids.add(identifier)
        if work["publication_year"] > date.today().year:
            errors.append(f"closest_prior_work[{index}].publication_year is invalid")
    if sum(work["publication_year"] >= date.today().year - 5 for work in works) < 2:
        errors.append("closest_prior_work must include at least two works from the current five-year window")
    for index, claim in enumerate(audit["novelty_claims"]):
        identifier = claim["claim_id"].strip()
        if identifier in claim_ids:
            errors.append(f"novelty_claims[{index}].claim_id is duplicated")
        claim_ids.add(identifier)
        missing = sorted({item.strip() for item in claim["evidence_ids"]} - work_ids)
        if missing:
            errors.append(f"novelty_claims[{index}].evidence_ids reference unknown work: {', '.join(missing)}")
    patent = audit["patent_search"]
    if patent["status"] == "completed":
        for key in ("databases", "queries"):
            _string_list(patent.get(key), "patent_search." + key, errors)
    else:
        _text(patent.get("justification"), "patent_search.justification", errors)
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
        structural = schema_errors(record, "search-record.schema.json")
        errors.extend(prefix + "." + error for error in structural)
        if structural:
            continue
        search_id = record["search_id"].strip()
        if search_id in search_ids:
            errors.append(prefix + ".search_id is duplicated")
        search_ids.add(search_id)
        logged_databases.add(record["database"].strip())
        logged_families.add(record["query_family"].strip())
        included_work_ids.update(item.strip() for item in record["included_work_ids"])
        errors.extend(_record_date(record["searched_at"], prefix + ".searched_at", timestamp=True))

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
    errors = schema_errors(value, "paper-map.schema.json")
    if errors:
        return errors
    expected = sorted(expected_paper_ids)
    papers = value["papers"]
    if sorted(row["paper_id"] for row in papers) != expected:
        errors.append(f"papers must contain exactly: {', '.join(expected)}")
    global_claim_ids: set[str] = set()
    for index, paper in enumerate(papers):
        claims = {item.strip() for item in paper["unique_claim_ids"]}
        duplicated = sorted(claims & global_claim_ids)
        if duplicated:
            errors.append(f"papers[{index}].unique_claim_ids repeat another paper's claim: {', '.join(duplicated)}")
        global_claim_ids.update(claims)
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
        if sorted(str(p) for p in contribution_papers) != expected:
            errors.append("cumulative_contributions must cover every paper exactly once")
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
    if study_route not in {"empirical", "meta_analysis", "theory"}:
        return ["unknown study route"]
    if not isinstance(contract, dict):
        return ["paper contract must be an object"]
    errors = schema_errors({**contract, "study_route": study_route}, "paper-contract.schema.json")
    if contract.get("study_route", "empirical") != study_route:
        errors.append("paper contract study_route must match its actual research identity")
    if contract.get("paper_id") != expected_paper_id:
        errors.append(f"paper_id must be {expected_paper_id}")
    _planning_quartile(contract.get("target_jcr_quartile"), "target_jcr_quartile", errors)
    venues = contract.get("target_venues")
    for index, venue in enumerate(venues if isinstance(venues, list) else []):
        if isinstance(venue, dict):
            _planning_quartile(venue.get("quartile"), f"target_venues[{index}].quartile", errors)
    if errors:
        return errors
    planned = contract["planned_experiments"]
    if study_route == "empirical" and not BASELINE_CLASSES <= set(planned["baseline_classes"]):
        errors.append("planned_experiments.baseline_classes must include simple, domain_standard and strong_recent")
    hypotheses = [row["id"].strip() for row in contract["hypotheses"]]
    if len(set(hypotheses)) != len(hypotheses):
        errors.append("hypotheses.id is duplicated")
    errors.extend(validate_scientific_bindings({**contract, "study_route": study_route}))
    parents = set(contract["dependencies"])
    if expected_paper_id in parents:
        errors.append("dependencies must name other exact paper IDs")
    seen = set()
    for row in contract["dependency_bindings"]:
        parent = row["paper_id"]
        if parent not in parents or parent in seen:
            errors.append("dependency_bindings.paper_id must uniquely bind one declared dependency")
        seen.add(parent)
        if row["kind"] == "scientific_premise" and not row["claim_ids"]:
            errors.append("dependency_bindings.claim_ids must name the inherited scientific premise")
    if seen != parents:
        errors.append("dependency_bindings must explain every declared paper dependency")
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
    design: dict[str, Any], expected_paper_id: str, plan_runs: dict[str, dict[str, Any]],
) -> list[str]:
    errors = schema_errors(design, "paper-experiment-design.schema.json")
    data = design.get("data_protocol") if isinstance(design, dict) else None
    selection = data.get("model_selection") if isinstance(data, dict) else None
    if isinstance(selection, dict):
        if selection.get("status") == "tuned" and selection.get("selection_split") not in ("training", "validation", "nested_cross_validation"):
            errors.append("model selection must use training/validation/nested cross-validation, never test/final/holdout data")
        elif selection.get("status") in ("not_tuned", "not_applicable") and (selection.get("run_ids") or selection.get("search_space") or selection.get("selection_split") not in (None, "none")):
            errors.append("untuned/not-applicable selection must not invent tuning runs, a search space or a selection split")
    baselines = design.get("baselines", []) if isinstance(design, dict) else []
    for index, baseline in enumerate(baselines if isinstance(baselines, list) else []):
        if not isinstance(baseline, dict) or type(baseline.get("publication_year")) is not int:
            continue
        year = baseline["publication_year"]
        if year > date.today().year:
            errors.append(f"baselines[{index}].publication_year is invalid")
        elif baseline.get("class") == "strong_recent" and year < date.today().year - 5:
            errors.append(f"baselines[{index}] strong_recent baseline must be from the last five years")
    if errors:
        return errors
    if design["paper_id"] != expected_paper_id:
        errors.append(f"paper_id must be {expected_paper_id}")
    run_ids, seeds = design["run_ids"], design["seeds"]
    selected_runs = []
    for run_id in run_ids:
        run = plan_runs.get(run_id)
        if not run:
            errors.append(f"run_ids references unknown run {run_id}")
        elif run.get("paper_id") != expected_paper_id:
            errors.append(f"run {run_id} belongs to {run.get('paper_id')}, not {expected_paper_id}")
        else:
            selected_runs.append(run)
    if design["stochastic"]:
        planned_seeds = {run.get("seed") for run in selected_runs if type(run.get("seed")) is int}
        if len(seeds) < 3 or len(planned_seeds) < 3:
            errors.append("stochastic designs require at least three distinct planned run seeds")
        if set(seeds) != planned_seeds:
            errors.append("declared seeds must exactly match the linked planned run seeds")
    baselines = design["baselines"]
    if not BASELINE_CLASSES <= {row["class"] for row in baselines}:
        errors.append("baselines must cover simple, domain_standard and strong_recent comparators")
    identifiers = [row["id"].strip() for row in baselines]
    if len(set(identifiers)) != len(identifiers):
        errors.append("baselines.id is duplicated")
    selection = design["data_protocol"]["model_selection"]
    if selection["status"] == "tuned":
        if not selection.get("search_space"):
            errors.append("tuned model selection needs its declared parameter search space")
        for key, values in selection.get("search_space", {}).items():
            if (not key.strip() or not isinstance(values, list) or not values or
                    any(type(v) not in (str, int, float, bool) or (type(v) is float and not math.isfinite(v)) for v in values)):
                errors.append("model_selection.search_space must map parameter names to explicit finite candidate values")
        if not set(selection.get("run_ids", [])) <= set(run_ids):
            errors.append("model_selection.run_ids must belong to this declared paper design")
    reproduction = design["reproduction_plan"]
    baseline_runs = reproduction["baseline_runs"]
    original_runs, clean_runs = reproduction["original_run_ids"], reproduction["clean_room_run_ids"]
    referenced = set(baseline_runs["domain_standard"] + baseline_runs["strong_recent"] + original_runs + clean_runs)
    unknown = sorted(referenced - set(run_ids))
    if unknown:
        errors.append("reproduction_plan references runs outside this design: " + ", ".join(unknown))
    if set(original_runs) & set(clean_runs):
        errors.append("reproduction_plan original and clean-room run IDs must be disjoint")
    for run_id in clean_runs:
        run = plan_runs.get(run_id)
        if not isinstance(run, dict) or not isinstance(run.get("isolation"), dict) or run["isolation"].get("kind") != "container":
            errors.append(f"clean-room run {run_id} must use digest-pinned container isolation")
    return errors
