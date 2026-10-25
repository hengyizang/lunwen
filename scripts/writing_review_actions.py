"""Make existing review issues actionable without another ledger or model call.

Located files establish supplied material, not scientific adequacy or resolution.
The existing independent audit and human gate retain that decision.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re

from scripts.research_artifacts import path_in, read, sha

CATEGORIES = {"empty_evaluation", "missing_evidence", "inference_gap", "unclear_contribution_comparison",
              "unclear_mechanism", "unsupported_generality", "experimental_description_gap",
              "unclear_exposition", "redundant_framing", "terminology_inconsistency"}
MATERIAL_KINDS = {"data", "literature", "analysis", "proof", "protocol", "manuscript_edit"}
MATERIAL_STATES = {"missing", "supplied_pending_review", "not_applicable"}
EDITORIAL_CATEGORIES = {"empty_evaluation", "unclear_exposition", "redundant_framing", "terminology_inconsistency"}


def _need(value, message):
    if not value:
        raise ValueError(message)


def _keys(value, required, optional=()):
    _need(isinstance(value, dict) and set(required) <= set(value) <= set(required) | set(optional), "Writing action has missing or unsupported fields")


def _text(value, label, maximum=4000):
    _need(isinstance(value, str) and value.strip() and len(value) <= maximum and "\x00" not in value
          and value.strip().casefold() not in {"todo", "tbd", "unknown", "n/a"}, "Concrete bounded " + label + " is required")
    return value.strip()


def _strings(value, label, minimum=1, maximum=50):
    _need(isinstance(value, list) and minimum <= len(value) <= maximum, "Writing action needs bounded " + label)
    result = [_text(item, label, 1000) for item in value]
    _need(len(result) == len(set(result)), "Writing action " + label + " must be unique")
    return result


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def assess(project: Path, action=None, *, previous=None, paper_ids=None, bind_source=None):
    """Return a task assessment for one already-identified review issue.

    ``bind_source`` optionally records each minimal {path,sha256} in the
    caller's existing source-provenance list. It makes no model/tool request.
    A previous normalized assessment preserves the same issue's material IDs
    and appends its former task definition to that issue's own history.
    """
    prior = previous if isinstance(previous, dict) and previous.get("status") != "not_assessed" else None
    if action is None:
        _need(prior is None, "Do not remove an inherited structured writing action")
        return {"status": "not_assessed", "reason": "No structured material/action request on this legacy issue.",
                "scientific_resolution_verified": False, "independent_review_required": True}
    _keys(action, {"categories", "scope", "locations", "required_materials", "action", "completion_conditions"}, {"revision_reason"})
    categories = _strings(action["categories"], "issue categories", maximum=10)
    _need(set(categories) <= CATEGORIES, "Unsupported writing issue category")
    scope = action["scope"]
    _keys(scope, {"paper_ids", "claim_ids", "sections", "boundary"})
    papers = _strings(scope["paper_ids"], "paper scope", maximum=6)
    _need(all(re.fullmatch(r"P0[1-6]", paper) for paper in papers), "Writing action paper scope is restricted to P01-P06")
    if paper_ids is not None:
        _need(set(papers) <= set(paper_ids), "Writing action changes its parent issue's paper scope")
    claims = _strings(scope["claim_ids"], "claim IDs", minimum=0)
    _need(claims or set(categories) <= EDITORIAL_CATEGORIES, "Scientific writing issue needs actual claim IDs")
    normalized_scope = {"paper_ids": papers, "claim_ids": claims,
                        "sections": _strings(scope["sections"], "section scope", maximum=30),
                        "boundary": _text(scope["boundary"], "applicability boundary")}
    inputs = []

    def binding(value):
        _keys(value, {"path", "sha256"})
        relative = value["path"]
        _need(isinstance(relative, str) and relative.startswith(("papers/", "claims/", "program/", "evidence/", "literature/", "analysis/", "results/", "experiments/", "reports/"))
              and not any(part.casefold() in {"state", "raw", "private", "secrets", "credentials", ".git", "submission"} or part.startswith(".") for part in Path(relative).parts),
              "Writing-action source is outside the bounded project evidence corpus")
        target = path_in(project, relative)
        _need(target.stat().st_size <= 4_000_000 and re.fullmatch(r"[a-f0-9]{64}", str(value["sha256"])) and sha(target) == value["sha256"], "Writing-action source hash is stale or oversized")
        if value not in inputs:
            inputs.append(dict(value))
            if bind_source:
                bind_source(dict(value))
        return target

    def anchors(value, *, locations=False, minimum=1):
        _need(isinstance(value, list) and minimum <= len(value) <= 30, "Writing action requires actual bounded source locations")
        checked = []
        from scripts.research_candidates import anchor_errors
        for row in value:
            _keys(row, {"path", "sha256", "locator", "excerpt"}, {"pdf_page"})
            binding({key: row[key] for key in ("path", "sha256")})
            if locations:
                _need(any(row["path"].startswith(f"papers/{paper}/") for paper in papers), "Issue location must be in an applicable paper")
            _text(row["locator"], "exact source locator", 1000)
            _text(row["excerpt"], "actual source quotation")
            errors = anchor_errors(project, row)
            _need(not errors, "Writing-action location is invalid: " + "; ".join(errors))
            checked.append(dict(row))
        return checked

    if claims:
        claim_path = path_in(project, "claims/claim-evidence.csv", exists=False)
        csv_rows, matrix_rows = [], None
        if claim_path.is_file():
            binding({"path": "claims/claim-evidence.csv", "sha256": sha(claim_path)})
            with claim_path.open(encoding="utf-8", newline="") as handle:
                csv_rows = list(csv.DictReader(handle))
        for claim_id in claims:
            matching = [row for row in csv_rows if row.get("claim_id") == claim_id]
            if matching:
                _need(len(matching) == 1 and matching[0].get("paper_id") in papers, "Writing-action claim is absent, duplicated or outside its paper scope")
                continue
            # The initialized empirical CSV can legitimately be header-only
            # while an early-stage novelty claim already has its canonical ID.
            # A conflicting existing CSV row is never overridden by that matrix.
            if matrix_rows is None:
                matrix_path = path_in(project, "program/novelty-claim-matrix.json")
                binding({"path": "program/novelty-claim-matrix.json", "sha256": sha(matrix_path)})
                matrix_rows = read(matrix_path).get("claims", [])
            matching = [row for row in matrix_rows if row.get("claim_id", row.get("id")) == claim_id]
            _need(len(matching) == 1 and set(matching[0].get("paper_ids", [])) & set(papers), "Writing-action claim is absent or outside its paper scope")
    locations = anchors(action["locations"], locations=True)
    materials = action["required_materials"]
    _need(isinstance(materials, list) and 1 <= len(materials) <= 50, "Writing action needs one to fifty explicit required materials")
    checked_materials, seen = [], set()
    old_materials = {row["id"]: row for row in prior.get("definition", {}).get("required_materials", [])} if prior else {}
    for row in materials:
        _keys(row, {"id", "kind", "description", "status", "reason", "sources"})
        identifier = row["id"]
        _need(isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", identifier) and identifier not in seen, "Required material IDs must be stable and unique")
        seen.add(identifier)
        _need(row["kind"] in MATERIAL_KINDS and row["status"] in MATERIAL_STATES, "Material kind/status cannot claim verified scientific completion")
        item = {"id": identifier, "kind": row["kind"], "description": _text(row["description"], "required material description"),
                "status": row["status"], "reason": _text(row["reason"], "material availability or applicability reason"),
                "sources": anchors(row["sources"], minimum=0 if row["status"] == "missing" else 1)}
        _need(row["status"] != "missing" or not item["sources"], "Missing material cannot carry an asserted supplied source")
        if identifier in old_materials:
            _need(all(item[key] == old_materials[identifier][key] for key in ("kind", "description")), "Do not repurpose an inherited material ID; preserve it and add a new requirement")
        checked_materials.append(item)
    _need(not set(old_materials)-seen, "Do not delete inherited required materials")
    definition = {"categories": categories, "scope": normalized_scope, "locations": locations,
                  "required_materials": checked_materials, "action": _text(action["action"], "specific remediation action"),
                  "completion_conditions": _strings(action["completion_conditions"], "completion conditions")}
    fingerprint = _digest(definition)
    history = list(prior.get("history", [])) if prior else []
    revision = prior.get("revision", 1) if prior else 1
    if prior:
        old = prior["definition"]
        _need(categories == old["categories"] and normalized_scope == old["scope"], "Keep an inherited writing issue's categories and scientific scope stable")
        if fingerprint != prior.get("definition_sha256"):
            reason = _text(action.get("revision_reason"), "reason for changing inherited action/material availability")
            history.append({"revision": revision, "definition_sha256": prior["definition_sha256"], "definition": old,
                            "status": prior["status"], "change_reason": reason})
            revision += 1
    elif action.get("revision_reason") is not None:
        _text(action["revision_reason"], "revision reason")
    missing = [row["id"] for row in checked_materials if row["status"] == "missing"]
    return {"status": "pending_materials" if missing else "answered_pending_review", "definition": definition,
            "definition_sha256": fingerprint, "revision": revision, "history": history, "inputs": inputs,
            "missing_material_ids": missing, "claim_scope": "scientific_claim" if claims else "editorial_only",
            "scientific_resolution_verified": False, "completion_conditions_verified": False,
            "independent_review_required": True, "paid_calls": 0, "implementation_sha256": sha(Path(__file__))}
