#!/usr/bin/env python3
"""Create a decomposed, risk-aware journal shortlist from the JCR-bound registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
WEIGHTS = {
    "scope_fit": 30,
    "article_type_fit": 15,
    "audience_fit": 10,
    "impact_and_tier": 20,
    "practicality": 15,
    "access_and_cost": 5,
    "reputation_and_risk": 5,
}
STRATEGIES = {"challenge", "target", "safety"}
HARD_RISKS = {"scope_mismatch", "indexing_uncertain", "inactive_submission", "integrity_concern"}
SOFT_RISKS = {"fees_unknown", "timeline_unknown", "special_issue_dependency", "policy_ambiguity"}
EVIDENCE_CATEGORIES = {"scope", "article_type", "audience", "practicality", "access", "reputation"}


class JournalScreeningError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def safe_file(project: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise JournalScreeningError("input path must be project-relative")
    path = (project / value).resolve()
    if project.resolve() not in path.parents or not path.is_file() or path.is_symlink():
        raise JournalScreeningError(f"not a regular project file: {relative}")
    return path


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JournalScreeningError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise JournalScreeningError(f"{label} must be a JSON object")
    return value


def build(project: Path, input_path: Path, registry_path: Path) -> dict[str, Any]:
    spec = load_object(input_path, "screening input")
    registry = load_object(registry_path, "venue registry")
    reviewed_by = str(spec.get("reviewed_by", "")).strip()
    reviewed_at = str(spec.get("reviewed_at", "")).strip()
    if not reviewed_by or not reviewed_at:
        raise JournalScreeningError("screening input needs reviewed_by and reviewed_at")
    try:
        review_time = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JournalScreeningError("reviewed_at must be an ISO-8601 timestamp") from exc
    if review_time.tzinfo is None:
        raise JournalScreeningError("reviewed_at must include a timezone")
    spec_papers = spec.get("papers")
    registry_papers = registry.get("papers")
    if not isinstance(spec_papers, list) or not isinstance(registry_papers, list):
        raise JournalScreeningError("input and registry must contain papers arrays")
    registry_map = {
        str(item.get("paper_id")): item for item in registry_papers if isinstance(item, dict)
    }
    if {str(item.get("paper_id")) for item in spec_papers if isinstance(item, dict)} != set(registry_map):
        raise JournalScreeningError("screening input must cover every registry paper exactly once")
    papers: list[dict[str, Any]] = []
    for paper_spec in spec_papers:
        if not isinstance(paper_spec, dict):
            raise JournalScreeningError("each paper screening must be an object")
        paper_id = str(paper_spec.get("paper_id", ""))
        if not re.fullmatch(r"P[0-9]{2}", paper_id):
            raise JournalScreeningError("paper_id must look like P01")
        registry_paper = registry_map[paper_id]
        registry_candidates = {
            str(item.get("venue_id")): item
            for item in registry_paper.get("candidates", [])
            if isinstance(item, dict)
        }
        candidate_specs = paper_spec.get("candidates")
        if not isinstance(candidate_specs, list) or len(candidate_specs) < 3:
            raise JournalScreeningError(f"{paper_id} needs at least three screened venues")
        roles: list[str] = []
        seen: set[str] = set()
        output_candidates: list[dict[str, Any]] = []
        for item in candidate_specs:
            if not isinstance(item, dict):
                raise JournalScreeningError(f"{paper_id} candidate must be an object")
            venue_id = str(item.get("venue_id", ""))
            if venue_id not in registry_candidates or venue_id in seen:
                raise JournalScreeningError(f"{paper_id} has unknown or duplicate venue_id {venue_id}")
            seen.add(venue_id)
            strategy = str(item.get("strategy", ""))
            if strategy not in STRATEGIES:
                raise JournalScreeningError(f"{paper_id}/{venue_id} has invalid strategy")
            roles.append(strategy)
            scores = item.get("scores")
            if not isinstance(scores, dict) or set(scores) != set(WEIGHTS):
                raise JournalScreeningError(f"{paper_id}/{venue_id} needs all seven score dimensions")
            normalized_scores: dict[str, float] = {}
            for dimension in WEIGHTS:
                try:
                    score = float(scores[dimension])
                except (TypeError, ValueError) as exc:
                    raise JournalScreeningError(f"{paper_id}/{venue_id}/{dimension} must be numeric") from exc
                if not 0 <= score <= 5:
                    raise JournalScreeningError(f"{paper_id}/{venue_id}/{dimension} must be 0-5")
                normalized_scores[dimension] = score
            evidence = item.get("evidence")
            if not isinstance(evidence, list):
                raise JournalScreeningError(f"{paper_id}/{venue_id} evidence must be an array")
            categories: set[str] = set()
            normalized_evidence: list[dict[str, str]] = []
            for source in evidence:
                if not isinstance(source, dict):
                    raise JournalScreeningError("evidence rows must be objects")
                category = str(source.get("category", ""))
                url = str(source.get("url", ""))
                accessed_at = str(source.get("accessed_at", ""))
                note = str(source.get("note", "")).strip()
                if category not in EVIDENCE_CATEGORIES or not url.startswith("https://") or not accessed_at or not note:
                    raise JournalScreeningError(
                        f"{paper_id}/{venue_id} evidence needs category, HTTPS URL, accessed_at and note"
                    )
                categories.add(category)
                normalized_evidence.append(
                    {"category": category, "url": url, "accessed_at": accessed_at, "note": note}
                )
            if categories != EVIDENCE_CATEGORIES:
                missing = ", ".join(sorted(EVIDENCE_CATEGORIES - categories))
                raise JournalScreeningError(f"{paper_id}/{venue_id} evidence misses: {missing}")
            risk_flags = sorted(set(str(value) for value in item.get("risk_flags", [])))
            unknown = set(risk_flags) - HARD_RISKS - SOFT_RISKS
            if unknown:
                raise JournalScreeningError(f"{paper_id}/{venue_id} unknown risks: {', '.join(sorted(unknown))}")
            hard_excluded = bool(set(risk_flags) & HARD_RISKS)
            weighted_score = round(
                sum(normalized_scores[key] / 5 * weight for key, weight in WEIGHTS.items()), 2
            )
            output_candidates.append(
                {
                    "venue_id": venue_id,
                    "name": registry_candidates[venue_id].get("name"),
                    "strategy": strategy,
                    "scores": normalized_scores,
                    "weighted_score": weighted_score,
                    "risk_flags": risk_flags,
                    "hard_excluded": hard_excluded,
                    "recommended": not hard_excluded,
                    "evidence": normalized_evidence,
                }
            )
        if set(roles) != STRATEGIES:
            raise JournalScreeningError(
                f"{paper_id} shortlist must contain challenge, target and safety strategies"
            )
        selected = registry_paper.get("selected_venue_id")
        selected_row = next((item for item in output_candidates if item["venue_id"] == selected), None)
        if selected is not None and (selected_row is None or selected_row["hard_excluded"]):
            raise JournalScreeningError(f"{paper_id} selected venue is absent or hard-excluded")
        output_candidates.sort(key=lambda value: (-value["weighted_score"], value["name"] or ""))
        papers.append(
            {
                "paper_id": paper_id,
                "target_jcr_quartile": registry_paper.get("target_jcr_quartile"),
                "selected_venue_id": selected,
                "candidates": output_candidates,
            }
        )
    return {
        "schema_version": "1.0",
        "created_at": now(),
        "method": {"score_scale": "0-5", "weights": WEIGHTS, "strategies": sorted(STRATEGIES)},
        "input": {"path": input_path.relative_to(project).as_posix(), "sha256": sha256_file(input_path)},
        "registry": {"path": registry_path.relative_to(project).as_posix(), "sha256": sha256_file(registry_path)},
        "human_review": {"reviewed_by": reviewed_by, "reviewed_at": reviewed_at},
        "papers": papers,
        "human_review_required": True,
    }


def validate_saved_report(project: Path) -> list[str]:
    path = project / "program" / "journal-screening.json"
    if not path.is_file():
        return ["program/journal-screening.json is required"]
    try:
        saved = load_object(path, "journal screening")
        input_record = saved.get("input") if isinstance(saved.get("input"), dict) else {}
        registry_record = saved.get("registry") if isinstance(saved.get("registry"), dict) else {}
        input_path = safe_file(project, str(input_record.get("path", "")))
        registry_path = safe_file(project, str(registry_record.get("path", "")))
        current = build(project, input_path, registry_path)
    except JournalScreeningError as exc:
        return [str(exc)]
    errors: list[str] = []
    if saved.get("schema_version") != "1.0" or saved.get("human_review_required") is not True:
        errors.append("journal screening must be schema_version 1.0 and require human review")
    for key in ("input", "registry", "human_review", "method", "papers"):
        if saved.get(key) != current.get(key):
            errors.append(f"journal screening is stale or altered for {key}")
    return errors


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--input", default="program/journal-screening-input.json")
    parser.add_argument("--registry", default="program/venue-candidates.json")
    args = parser.parse_args()
    project = PROJECTS_ROOT / args.project
    try:
        if not project.is_dir():
            raise JournalScreeningError("project does not exist")
        input_path = safe_file(project, args.input)
        registry_path = safe_file(project, args.registry)
        report = build(project, input_path, registry_path)
        atomic_json(project / "program" / "journal-screening.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except JournalScreeningError as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
