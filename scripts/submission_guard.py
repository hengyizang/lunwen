#!/usr/bin/env python3
"""Final deterministic guard before creating a manual submission package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.submission_package import build_package
    from scripts.researchctl import ResearchCtlError, project_dir, load_state, validate_paper_id
except ImportError:
    from submission_package import build_package  # type: ignore
    from researchctl import ResearchCtlError, project_dir, load_state, validate_paper_id  # type: ignore


def verify_jcr(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchCtlError(f"Invalid JCR verification file: {path}: {exc}") from exc
    required = ["database", "verification_year", "impact_factor", "quartile", "category", "indexing", "source_url", "verified_by", "verified_at"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ResearchCtlError(f"JCR verification missing: {', '.join(missing)}")
    if data["database"] != "Clarivate Journal Citation Reports":
        raise ResearchCtlError("JCR verification must identify Clarivate Journal Citation Reports")
    if not isinstance(data["impact_factor"], (int, float)) or data["impact_factor"] <= 1.0:
        raise ResearchCtlError("Manual submission requires a human-verified JCR impact factor > 1.0")
    if data["quartile"] != "Q1":
        raise ResearchCtlError("Manual submission requires a current JCR Q1 venue")
    if data["indexing"] not in {"SCI", "SCIE"}:
        raise ResearchCtlError("Manual submission requires SCI/SCIE indexing")
    if not str(data["source_url"]).startswith("https://"):
        raise ResearchCtlError("JCR source URL must use HTTPS")
    return data


def build_guarded_package(project: str, paper: str, output: Path | None = None) -> Path:
    paper = validate_paper_id(paper)
    state = load_state(project)
    if state.get("paper_statuses", {}).get(paper) != "submission_ready":
        raise ResearchCtlError(f"{paper} has not passed its G5 human gate")
    paper_dir = project_dir(project) / "papers" / paper
    verify_jcr(paper_dir / "jcr-verification.json")
    return build_package(project, paper, output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--paper", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        destination = build_guarded_package(args.project, args.paper, args.output)
    except ResearchCtlError as exc:
        print(f"error: {exc}")
        return 2
    print(destination)
    print("JCR Q1/SCI threshold passed. Package is for manual upload only; nothing was submitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
