#!/usr/bin/env python3
"""Source-bound paper cards and competing hypotheses after direction screening."""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

try:
    from scripts.research_methods import safe_path, sha256
except ImportError:
    from research_methods import safe_path, sha256

ROOT = Path(__file__).resolve().parents[1]


def text_fields(row: dict, fields: tuple[str, ...], prefix: str, errors: list[str]) -> None:
    for field in fields:
        if not isinstance(row.get(field), str) or not row[field].strip():
            errors.append(f"{prefix}.{field} requires concrete text")


def text_list(value: Any, minimum: int, field: str, errors: list[str]) -> None:
    if (not isinstance(value, list) or len(value) < minimum or
            any(not isinstance(item, str) or not item.strip() for item in value)):
        errors.append(f"{field} requires at least {minimum} nonempty strings")


def anchor_errors(project: Path, anchor: Any) -> list[str]:
    """Verify location/provenance only; textual presence is not claim support."""
    errors: list[str] = []
    if not isinstance(anchor, dict):
        return ["source anchor must be an object"]
    text_fields(anchor, ("path", "sha256", "locator", "excerpt"), "anchor", errors)
    if errors:
        return errors
    if len(anchor["excerpt"].split()) > 25 or len(anchor["excerpt"]) > 1000:
        errors.append("source excerpt exceeds the bounded 25-word/1000-character limit")
    try:
        path = safe_path(project, anchor["path"])
        if not path.is_file():
            return errors + ["source_missing: " + anchor["path"]]
        if sha256(path) != anchor["sha256"]:
            errors.append("stale source hash: " + anchor["path"])
        if path.suffix.lower() == ".pdf":
            page = anchor.get("pdf_page")
            if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                return errors + ["PDF anchors need a positive PDF page index"]
            from pypdf import PdfReader
            reader = PdfReader(str(path), strict=False)
            if page > len(reader.pages):
                return errors + ["PDF anchor page is outside the source"]
            source = reader.pages[page - 1].extract_text() or ""
        elif path.suffix.lower() in {".md", ".txt", ".tex", ".csv", ".tsv", ".json", ".jsonl", ".bib"}:
            source = path.read_text(encoding="utf-8")
            match = re.fullmatch(r"(?:L|lines?\s+)([1-9][0-9]*)(?:\s*-\s*(?:L)?([1-9][0-9]*))?",
                                 anchor["locator"], re.IGNORECASE)
            if not match:
                return errors + ["text anchors need a verifiable line locator (L1 or L1-L3)"]
            first, last = int(match[1]), int(match[2] or match[1])
            lines = source.splitlines()
            if last < first or last > len(lines):
                return errors + ["text anchor line range is outside the source"]
            source = "\n".join(lines[first - 1:last])
        elif path.suffix.lower() == ".docx":
            from docx import Document
            match = re.fullmatch(r"paragraph\s+([1-9][0-9]*)", anchor["locator"], re.IGNORECASE)
            if not match:
                return errors + ["DOCX anchors need a verifiable paragraph index"]
            paragraphs = Document(path).paragraphs
            index = int(match[1])
            if index > len(paragraphs):
                return errors + ["DOCX paragraph is outside the source"]
            source = paragraphs[index - 1].text
        else:
            return errors + ["source is not text-auditable; use a located textual evidence record"]
        if anchor["excerpt"] not in source:
            errors.append("unconfirmed_anchor: source does not contain the exact excerpt")
    except Exception as exc:
        # Parser/provenance failures must produce an unavailable anchor, never PASS.
        errors.append(f"source verification unavailable: {exc}")
    return errors


def validate_idea(project: Path, idea: Any, prefix: str) -> list[str]:
    if not isinstance(idea, dict):
        return [prefix + " must be an object"]
    errors: list[str] = []
    text_fields(idea, ("hypothesis_id", "hypothesis", "source_observation",
                      "precise_difference", "prediction", "falsifying_result",
                      "null_result_value"), prefix, errors)
    anchors = idea.get("source_anchors")
    if not isinstance(anchors, list) or not anchors:
        errors.append(prefix + ".source_anchors requires located source evidence")
    else:
        for anchor in anchors:
            errors.extend(prefix + ": " + error for error in anchor_errors(project, anchor))
    rivals = idea.get("alternative_explanations")
    if not isinstance(rivals, list) or len(rivals) < 2:
        errors.append(prefix + " needs at least two competing explanations")
    else:
        for index, rival in enumerate(rivals):
            if not isinstance(rival, dict):
                errors.append(prefix + ".alternative_explanations must contain objects")
                continue
            text_fields(rival, ("explanation", "discriminating_test", "expected_if_true"),
                        f"{prefix}.rival[{index}]", errors)
        explanations = [row["explanation"].strip().casefold() for row in rivals
                        if isinstance(row, dict) and isinstance(row.get("explanation"), str)]
        if len(set(explanations)) != len(explanations):
            errors.append(prefix + " repeats the same competing explanation")
    text_list(idea.get("failure_modes"), 2, prefix + ".failure_modes", errors)
    plan = idea.get("test_plan")
    if not isinstance(plan, dict):
        errors.append(prefix + ".test_plan must be an object")
    else:
        text_fields(plan, ("comparator", "metric", "dataset", "cloud_execution", "deadline"),
                    prefix + ".test_plan", errors)
        text_list(plan.get("controls"), 1, prefix + ".test_plan.controls", errors)
        budget = plan.get("budget_cny")
        if (isinstance(budget, bool) or not isinstance(budget, (int, float)) or
                not math.isfinite(budget) or budget < 0):
            errors.append(prefix + ".test_plan.budget_cny needs a finite nonnegative estimate")
        try:
            date.fromisoformat(plan.get("deadline", ""))
        except (ValueError, TypeError):
            errors.append(prefix + ".test_plan.deadline needs an ISO date")
    if idea.get("novelty_status") != "prior_art_search_required":
        # This register never grants novelty. The existing originality matrix owns that judgement.
        errors.append(prefix + ".novelty_status must remain prior_art_search_required")
    if idea.get("evidence_status") != "hypothesis":
        errors.append(prefix + ".evidence_status must be hypothesis, never an observed result")
    return errors


def audit_register(project: Path, spec: Path) -> dict[str, Any]:
    value = json.loads(spec.read_text(encoding="utf-8"))
    errors: list[str] = []
    if not isinstance(value, dict):
        raise ValueError("hypothesis register must be an object")
    if value.get("schema_version") != "1.0":
        errors.append("unsupported hypothesis register schema")
    if value.get("scope") != "specific_topics_after_direction_screening":
        errors.append("hypothesis assessment belongs after direction screening")
    text_fields(value, ("direction_id",), "register", errors)
    if value.get("automatic_selection") is not False:
        errors.append("the hypothesis register must not automatically select a topic")
    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) < 3:
        errors.append("at least three concrete candidate hypotheses are required")
        hypotheses = hypotheses if isinstance(hypotheses, list) else []
    ids = [row["hypothesis_id"].strip() for row in hypotheses
           if isinstance(row, dict) and isinstance(row.get("hypothesis_id"), str)]
    if len(set(ids)) != len(ids):
        errors.append("duplicate hypothesis IDs")
    for index, hypothesis in enumerate(hypotheses):
        errors.extend(validate_idea(project, hypothesis, f"hypotheses[{index}]"))
    argument = value.get("argument_plan")
    if not isinstance(argument, dict):
        errors.append("a proposal-first argument_plan is required")
    else:
        text_fields(argument, ("research_question",), "argument_plan", errors)
        for field in ("allowed_claims", "forbidden_claims", "planned_evidence", "stopping_conditions"):
            text_list(argument.get(field), 1, "argument_plan." + field, errors)
        allowed, forbidden = argument.get("allowed_claims", []), argument.get("forbidden_claims", [])
        if (isinstance(allowed, list) and isinstance(forbidden, list) and
                {item.strip() for item in allowed if isinstance(item, str)} &
                {item.strip() for item in forbidden if isinstance(item, str)}):
            errors.append("an argument claim is simultaneously allowed and forbidden")
    return {"schema_version": "1.0", "spec_sha256": sha256(spec), "hypothesis_count": len(hypotheses),
            "errors": errors, "pass": not errors, "scientific_validation": False,
            "novelty_granted": False, "human_review_required": True}


def audit_card(project: Path, spec: Path) -> dict[str, Any]:
    value = json.loads(spec.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("paper card must be an object")
    errors: list[str] = []
    if value.get("schema_version") != "1.0":
        errors.append("unsupported paper card schema")
    if not isinstance(value.get("source_scope"), str) or value["source_scope"] not in {
            "full_text", "abstract", "excerpt", "metadata"}:
        errors.append("paper card requires an explicit source_scope")
    for field in ("methods_assessed", "experiments_assessed"):
        if not isinstance(value.get(field), bool):
            errors.append("card." + field + " must be an explicit boolean")
    text_fields(value, ("paper_id", "research_question", "claimed_contribution"), "card", errors)
    scope_confirmed = False
    if value.get("source_scope") == "full_text":
        try:
            from scripts.source_scope import verify
        except ImportError:
            from source_scope import verify
        scope_errors = verify(project, value.get("primary_source"), value.get("scope_record"), "full_text")
        errors.extend(scope_errors)
        scope_confirmed = not scope_errors
    observations = value.get("claim_evidence", [])
    if not isinstance(observations, list) or not observations:
        errors.append("paper card requires claim_evidence")
    else:
        for index, observation in enumerate(observations):
            if not isinstance(observation, dict):
                errors.append("claim_evidence must contain objects")
                continue
            text_fields(observation, ("claim", "boundary"), f"claim_evidence[{index}]", errors)
            if not isinstance(observation.get("attribution"), str) or observation["attribution"] not in {
                    "author_statement", "agent_analysis"}:
                errors.append("separate author_statement from agent_analysis")
            errors.extend(anchor_errors(project, observation.get("anchor")))
            if value.get("source_scope") == "full_text" and isinstance(value.get("primary_source"), dict):
                anchor = observation.get("anchor")
                if not isinstance(anchor, dict) or anchor.get("path") != value["primary_source"].get("path"):
                    errors.append("full-text observations must anchor the confirmed primary source")
    if value.get("source_scope") != "full_text":
        if value.get("methods_assessed") is not False or value.get("experiments_assessed") is not False:
            errors.append("partial sources cannot establish unseen methods or experiments")
    ideas = value.get("candidate_ideas", [])
    if not isinstance(ideas, list):
        errors.append("candidate_ideas must be an array")
    else:
        for index, idea in enumerate(ideas):
            errors.extend(validate_idea(project, idea, f"candidate_ideas[{index}]"))
    return {"schema_version": "1.0", "spec_sha256": sha256(spec), "source_scope": value.get("source_scope"),
            "errors": errors, "pass": not errors, "not_independent_evidence": True,
            "provided_scope_confirmed": scope_confirmed, "human_read_scope": "not_declared",
            "scientific_validation": False,
            "human_review_required": True}


def validate_saved_register(project: Path) -> list[str]:
    spec = project / "program/hypothesis-register.json"
    report = project / "program/hypothesis-audit.json"
    if not spec.is_file() or not report.is_file():
        return ["hypothesis register and deterministic hypothesis audit are required"]
    try:
        current = audit_register(project, spec)
        saved = json.loads(report.read_text())
        if saved != current:
            return current["errors"] + ["hypothesis audit is stale or modified"]
        return current["errors"]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [f"cannot validate hypothesis register: {exc}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["hypotheses", "paper-card"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    project = safe_path(ROOT / "projects", args.project)
    spec, output = safe_path(project, args.spec), safe_path(project, args.output)
    report = audit_register(project, spec) if args.kind == "hypotheses" else audit_card(project, spec)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
