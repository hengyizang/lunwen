#!/usr/bin/env python3
"""Criterion-bound, evidence-anchored submission review; never an acceptance score."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.research_candidates import anchor_errors, text_fields
    from scripts.research_methods import safe_path, sha256
    from scripts.reporting_checklist import canonical_manuscript
    from scripts.citation_audit import manuscript_digest, tex_source_paths
except ImportError:
    from research_candidates import anchor_errors, text_fields
    from research_methods import safe_path, sha256
    from reporting_checklist import canonical_manuscript
    from citation_audit import manuscript_digest, tex_source_paths

ROOT = Path(__file__).resolve().parents[1]
CRITERIA_PATH = ROOT / "config/pre-submission-criteria.json"
JUDGEMENTS = {"EXCEEDS", "MEETS", "PARTLY_MEETS", "DOES_NOT_MEET", "NOT_ASSESSED", "NOT_APPLICABLE"}


def criteria_for(article_type: str) -> list[dict[str, Any]]:
    criteria = json.loads(CRITERIA_PATH.read_text())
    if not isinstance(article_type, str) or article_type not in criteria["article_types"]:
        raise ValueError("unsupported review article_type")
    return criteria["universal"] + criteria["article_types"][article_type]


def audit(paper: Path) -> dict[str, Any]:
    project = paper.parent.parent
    spec = paper / "reviews/pre-submission-checklist.json"
    manuscript = canonical_manuscript(paper)
    manuscript_sources = (tex_source_paths(manuscript) if manuscript.suffix == ".tex"
                          else {manuscript.resolve()})
    value = json.loads(spec.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("pre-submission checklist must be an object")
    required = {row["id"]: row for row in criteria_for(value.get("article_type", ""))}
    universal = {row["id"] for row in json.loads(CRITERIA_PATH.read_text())["universal"]}
    errors: list[str] = []
    if value.get("schema_version") != "1.0":
        errors.append("unsupported pre-submission checklist schema")
    if value.get("calibration_status") != "NOT_CALIBRATED":
        errors.append("review criteria are NOT_CALIBRATED; do not claim measured acceptance odds")
    if any(key in value for key in ("score", "overall_score", "acceptance_probability", "ranking")):
        errors.append("criterion judgements must not be converted to a total or acceptance probability")
    checks = value.get("checks")
    if not isinstance(checks, list):
        raise ValueError("checks must be an array")
    seen: set[str] = set()
    unresolved: list[str] = []
    dependencies: dict[str, str] = {}
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            errors.append(f"checks[{index}] must be an object")
            continue
        criterion = check.get("criterion_id")
        if not isinstance(criterion, str) or criterion not in required:
            errors.append(f"unknown criterion: {criterion}")
            continue
        if criterion in seen:
            errors.append("duplicate criterion: " + criterion)
        seen.add(criterion)
        text_fields(check, ("criterion_source", "rationale", "uncertainty", "resolution_test"),
                    criterion, errors)
        judgement = check.get("judgement")
        if not isinstance(judgement, str) or judgement not in JUDGEMENTS:
            errors.append(criterion + ": invalid categorical judgement")
            judgement = "NOT_ASSESSED"
        if not isinstance(check.get("decision_bearing"), bool):
            errors.append(criterion + ": decision_bearing must be explicit")
        if any(key in check for key in ("score", "points", "weight")):
            errors.append(criterion + ": numeric scoring is not a criterion judgement")
        if judgement == "NOT_APPLICABLE":
            if criterion in universal:
                errors.append(criterion + ": universal criteria cannot be skipped")
            text_fields(check, ("non_applicability_reason",), criterion, errors)
            continue
        if judgement not in {"MEETS", "EXCEEDS"}:
            unresolved.append(criterion)
            errors.append(criterion + ": unresolved " + str(judgement))
        manuscript_anchors = check.get("manuscript_anchors")
        evidence_anchors = check.get("evidence_anchors")
        for field, anchors in (("manuscript_anchors", manuscript_anchors),
                               ("evidence_anchors", evidence_anchors)):
            if not isinstance(anchors, list) or not anchors:
                errors.append(criterion + "." + field + " requires verifiable locations")
                continue
            for anchor in anchors:
                errors.extend(criterion + ": " + error for error in anchor_errors(project, anchor))
                if isinstance(anchor, dict) and isinstance(anchor.get("path"), str):
                    if field == "manuscript_anchors" and not anchor["path"].startswith(
                            f"papers/{paper.name}/manuscript/"):
                        errors.append(criterion + ": manuscript anchor is outside this manuscript")
                    try:
                        path = safe_path(project, anchor["path"])
                        if field == "manuscript_anchors" and path.resolve() not in manuscript_sources:
                            errors.append(criterion + ": anchor is not in the canonical manuscript source tree")
                        if path.is_file():
                            dependencies[anchor["path"]] = sha256(path)
                    except ValueError:
                        pass
    missing = sorted(set(required) - seen)
    if missing:
        errors.append("unassessed required criteria: " + ", ".join(missing))
    return {"schema_version": "1.0", "paper_id": paper.name,
            "spec_sha256": sha256(spec), "criteria_sha256": sha256(CRITERIA_PATH),
            "manuscript_sha256": manuscript_digest(manuscript),
            "dependencies": dict(sorted(dependencies.items())), "criteria_count": len(required),
            "unresolved_criteria": unresolved, "errors": errors, "pass": not errors,
            "calibration_status": "NOT_CALIBRATED", "scientific_validation": False,
            "human_review_required": True}


def validate_saved_report(paper: Path) -> list[str]:
    path = paper / "reviews/pre-submission-review.json"
    if not path.is_file():
        return ["deterministic pre-submission review is missing"]
    try:
        current = audit(paper)
        saved = json.loads(path.read_text())
        errors = list(current["errors"])
        if current != saved:
            errors.append("pre-submission review is stale or modified")
        return errors
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return [f"cannot validate pre-submission checklist: {exc}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--paper", required=True)
    args = parser.parse_args()
    project = safe_path(ROOT / "projects", args.project)
    paper = safe_path(project / "papers", args.paper)
    report = audit(paper)
    output = paper / "reviews/pre-submission-review.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
