"""Review-ready contributions within the existing paper-facts authority.

Checks current located facts and actual executor outputs, not scientific merit.
No prose generation, model call, experiment, independent ledger or approval.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.research_artifacts import path_in, read, sha

ROLES = {"empirical": {"finding", "magnitude", "uncertainty", "comparison"},
         "meta-analysis": {"finding", "magnitude", "uncertainty", "comparison", "heterogeneity", "bias"},
         "theoretical": {"proposition", "assumptions", "proof"},
         "qualitative": {"finding", "scope"}}
TEXTS = {"subject", "finding", "conditions", "scientific_answer"}
RESULTS = {"supported", "partially_supported", "not_supported", "contradicted", "inconclusive"}


def need(value, message):
    if not value:
        raise ValueError(message)


def text(value, name):
    need(isinstance(value, str) and 1 <= len(value.strip()) <= 5000, name + " requires concrete bounded text")
    return value.strip()


def _binding(project, value):
    need(isinstance(value, dict) and set(value) == {"path", "sha256"}, "exact source path/hash required")
    target = path_in(project, value["path"])
    need(sha(target) == value["sha256"], "contribution source changed: " + value["path"])
    return target


def _fact(project, fact):
    target = _binding(project, {"path": fact["source_path"], "sha256": fact["source_sha256"]})
    need(not fact["source_path"].startswith(("state/", "reviews/", "reports/"))
         and "/reviews/" not in fact["source_path"], "contribution facts cannot cite their own audit or approval")
    need(target.stat().st_size <= 4_000_000, "use a bounded, authorized fact source extract")
    excerpt = text(fact["verbatim_evidence"], "fact verbatim_evidence")
    need(excerpt in target.read_text(encoding="utf-8"), "contribution excerpt is absent from the bound result/source")
    text(fact["location"], "fact location")
    return {"path": fact["source_path"], "sha256": sha(target)}


def contribution(project, paper_id, link, facts, comparisons):
    detail = link.get("contribution_detail")
    if detail is None:
        return {"claim_id": link["claim_id"], "status": "not_assessed",
                "missing": ["contribution_detail"], "semantic_support_verified": False}
    required = {"kind", *TEXTS, "fact_roles", "execution", "expectation_review"}
    need(isinstance(detail, dict) and set(detail) == required, "contribution_detail has missing or unknown fields")
    kind = detail["kind"]
    need(kind in ROLES, "unsupported contribution reporting kind")
    identity = read(path_in(project, f"papers/{paper_id}/research-identity.json"))
    expected_kind = {"empirical": {"empirical"}, "computational": {"empirical"},
        "theoretical": {"theoretical"}, "meta-analysis": {"meta-analysis"},
        "quantitative-reanalysis": {"empirical"}, "bibliometric-hypothesis-test": {"empirical"},
        "case-study": {"empirical", "qualitative"}, "policy": {"empirical", "qualitative"},
        "software": {"empirical", "qualitative"}}
    from scripts.research_identity import PRIMARY, SECONDARY
    family = identity.get("design_family")
    need(family in PRIMARY | SECONDARY and identity.get("research_kind") ==
         ("primary" if family in PRIMARY else "secondary_quantitative"), "paper research identity has inconsistent kind/family")
    need(kind in expected_kind.get(family, set()),
         "reporting kind differs from the actual paper research identity")
    for field in TEXTS:
        text(detail[field], "contribution " + field)
    roles = detail["fact_roles"]
    need(isinstance(roles, list) and len(roles) == len(ROLES[kind]), "contribution needs exact design-specific fact roles")
    by_role, sources = {}, []
    for role in roles:
        need(isinstance(role, dict) and set(role) == {"role", "fact_id", "value"}, "fact role requires role/fact_id/value")
        name, identity = role["role"], role["fact_id"]
        need(name in ROLES[kind] and name not in by_role, "duplicate or irrelevant contribution fact role")
        need(identity in facts and identity in link["evidence_ids"], "contribution role is outside current claim evidence")
        fact = facts[identity]
        value = text(role["value"], "reported fact value")
        need(value in fact["verbatim_evidence"], "reported contribution value is absent from its exact source excerpt")
        sources.append(_fact(project, fact))
        by_role[name] = {"fact_id": identity, "value": value, "source": sources[-1]}
    executions = detail["execution"]
    need(isinstance(executions, list) and 1 <= len(executions) <= 50, "contribution needs actual executed result bindings")
    from scripts.figure_lineage import run_seal
    seals, outputs, seen = [], set(), set()
    for execution in executions:
        need(isinstance(execution, dict) and set(execution) == {"run_id", "path", "sha256"}, "execution needs exact run/output binding")
        identity = (execution["run_id"], execution["path"])
        need(identity not in seen, "duplicate contribution execution binding")
        seen.add(identity)
        seal = run_seal(project, paper_id, execution["run_id"])
        bound = {"path": execution["path"], "sha256": execution["sha256"]}
        need(bound in seal["outputs"], "contribution evidence is not the exact successful executor output")
        outputs.add((bound["path"], bound["sha256"]))
        seals.append(seal)
    measured = ROLES[kind] - {"assumptions", "scope", "proposition"}
    need(all((by_role[role]["source"]["path"], by_role[role]["source"]["sha256"]) in outputs for role in measured),
         "findings, magnitudes, intervals and proofs must come from declared sealed outputs")
    review = detail["expectation_review"]
    need(isinstance(review, dict) and set(review) == {"planned_source", "planned_quote", "observed_status", "decision", "reason", "scope"},
         "expectation_review requires frozen planned source, actual outcome and interpretation")
    planned = _binding(project, review["planned_source"])
    frozen = read(path_in(project, f"papers/{paper_id}/preregistration.json"))
    need(review["planned_source"] in frozen.get("files", []), "expectation must bind a frozen preregistered source")
    if kind == "theoretical":
        need(all(by_role[role]["source"] in frozen.get("files", []) for role in ("proposition", "assumptions")),
             "theoretical propositions and assumptions must bind the frozen proof inputs")
    need(text(review["planned_quote"], "planned prediction") in planned.read_text(encoding="utf-8"), "planned prediction is absent from frozen source")
    need(review["observed_status"] in RESULTS and review["observed_status"] == link["result_status"], "expectation review contradicts the current claim outcome")
    need(review["decision"] in {"retain", "narrow", "reframe", "unsupported"}, "explicit evidence-led interpretation decision required")
    if link["result_status"] in {"not_supported", "contradicted", "inconclusive"}:
        need(review["decision"] != "retain", "unsupported or inconclusive evidence cannot retain the original success narrative")
    text(review["reason"], "interpretation reason")
    text(review["scope"], "preserved claim scope")
    # The existing originality matrix remains the authority for closest-work IDs.
    matrix_path = path_in(project, "program/novelty-claim-matrix.json")
    matrix = read(matrix_path)
    candidates = [row for row in matrix.get("claims", []) if row.get("claim_id") == link["claim_id"] and paper_id in row.get("paper_ids", [])]
    need(len(candidates) == 1, "contribution must link the actual paper-scoped novelty claim")
    expected = set(candidates[0].get("closest_work_ids", []))
    need(expected, "contribution has no declared closest work")
    actual = set()
    for row in comparisons:
        closest = row.get("closest_work", {})
        if closest.get("paper_id") != paper_id or closest.get("claim_id") != link["claim_id"]:
            continue
        axes = closest.get("axes", {})
        # An honestly uninspected paper remains a useful research lead, but
        # cannot silently complete the final core-contribution comparison.
        located = all(side.get("status") in {"reported", "not_reported"} and side.get("evidence")
                      for axis in axes.values() for side in (axis.get("ours", {}), axis.get("prior", {})))
        if closest.get("record_complete") is True and len(axes) == 3 and located:
            actual.add(closest.get("work_id"))
    missing = sorted(expected - actual)
    need(not missing, "source-located object/method/result comparison is missing for: " + ", ".join(missing))
    return {"claim_id": link["claim_id"], "kind": kind, "status": "ready_for_scientific_review",
            **{key: detail[key] for key in TEXTS}, "fact_roles": by_role, "execution": seals,
            "expectation_review": review, "closest_work_ids": sorted(expected),
            "novelty_matrix": {"path": "program/novelty-claim-matrix.json", "sha256": sha(matrix_path)},
            "semantic_support_verified": False, "scientific_contribution_verified": False}


def audit(project: Path, paper_id: str, config: dict):
    """Append to manuscript-audit; no new result authority or review ledger."""
    facts = {row["id"]: row for row in config.get("facts", []) if isinstance(row, dict) and isinstance(row.get("id"), str)}
    comparisons, comparison_errors = [], []
    extension = project / "program/research-extensions.json"
    if extension.is_file():
        from scripts.research_extensions import comparison
        for row in read(extension).get("comparisons", []):
            closest = row.get("closest_work", {}) if isinstance(row, dict) else {}
            if not isinstance(closest, dict):
                comparison_errors.append("closest_work must be a structured comparison object")
                continue
            if isinstance(row, dict) and closest.get("paper_id") == paper_id:
                try:
                    comparisons.append(comparison(project, row))
                except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
                    comparison_errors.append(str(exc))
    rows, errors = [], comparison_errors
    for link in config.get("claim_alignment", []):
        if not isinstance(link, dict) or not isinstance(link.get("claim_id"), str):
            errors.append("contribution requires a current claim alignment")
            continue
        try:
            checked = contribution(project, paper_id, link, facts, comparisons)
            rows.append(checked)
            if checked["status"] == "not_assessed":
                errors.append(link["claim_id"] + ": contribution evidence and expectation review are not assessed")
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            errors.append(link["claim_id"] + ": " + str(exc))
    if not rows:
        errors.append("no current contribution reporting records")
    return {"status": "needs_preparation" if errors else "ready_for_scientific_review",
            "claims": rows, "errors": errors, "semantic_support_verified": False,
            "scientific_completion_verified": False,
            "implementation_sha256": sha(Path(__file__)), "paid_model_calls": 0}


def feedback(project: Path, paper_id: str):
    relative = f"papers/{paper_id}/reviews/paper-facts.json"
    source = path_in(project, relative, exists=False)
    if not source.is_file():
        return {"status": "input_missing", "required": relative, "semantic_support_verified": False}
    try:
        result = audit(project, paper_id, read(source))
        return {"status": result["status"], "input": {"path": relative, "sha256": sha(source)},
                "errors": result["errors"][:40], "omitted_error_count": max(0, len(result["errors"])-40),
                "claims": [{"claim_id": row["claim_id"], "status": row["status"]} for row in result["claims"]],
                "semantic_support_verified": False, "paid_model_calls": 0,
                "instruction": "Mechanical preparation only. Independently inspect claim support and inference in the actual manuscript/results; this is not a preferred review verdict."}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return {"status": "blocked", "error": str(exc), "semantic_support_verified": False}
