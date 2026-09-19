#!/usr/bin/env python3
"""Build and validate a per-paper venue registry from a local JCR export.

The program does not automate Clarivate access.  A researcher exports an
authorized CSV/JSON file locally; this control binds every Q1/SCI(SCIE)
candidate to the exact export row and keeps policy URLs and ranking rationale
separate from the licensed source data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
PAPER_RE = re.compile(r"^P[0-9]{2}$")


class VenueCandidateError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def project_path(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", slug):
        raise VenueCandidateError("project must be a safe 2-63 character slug")
    project = PROJECTS_ROOT / slug
    if not project.is_dir():
        raise VenueCandidateError(f"project does not exist: {slug}")
    return project


def safe_file(project: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise VenueCandidateError("file must be project-relative and cannot contain ..")
    path = (project / value).resolve()
    if project.resolve() not in path.parents or not path.is_file() or path.is_symlink():
        raise VenueCandidateError(f"file is not a regular project file: {relative}")
    return path


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = handle.name
    os.replace(temporary, path)


def rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(item) for item in csv.DictReader(handle)]
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            value = value.get("records", value.get("results", value.get("items")))
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise VenueCandidateError("JCR JSON must be an array or contain records/results/items")
        return [dict(item) for item in value]
    raise VenueCandidateError("JCR export must be CSV or JSON")


def field(row: dict[str, Any], *aliases: str) -> Any:
    values = {str(key).strip().casefold(): value for key, value in row.items()}
    for alias in aliases:
        value = values.get(alias.casefold())
        if value is not None and str(value).strip():
            return value
    return None


def issn(value: Any) -> str:
    return re.sub(r"[^0-9xX]", "", str(value or "")).upper()


def slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return result[:80] or "venue"


def normalize_jcr(row: dict[str, Any]) -> dict[str, Any]:
    name = str(field(row, "journal name", "journal", "title", "name") or "").strip()
    raw_issn = field(row, "issn", "eissn", "e-issn")
    category = str(field(row, "category", "jcr category", "categories") or "").strip()
    quartile = str(field(row, "quartile", "jif quartile", "jcr quartile") or "").strip().upper()
    indexing = str(field(row, "indexing", "edition", "web of science index") or "").strip().upper()
    year_value = field(row, "jcr year", "year", "edition year")
    impact_value = field(row, "journal impact factor", "impact factor", "jif")
    try:
        year = int(str(year_value).strip())
        impact = float(str(impact_value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise VenueCandidateError(f"invalid JCR year or impact factor for {name or 'unnamed row'}") from exc
    if indexing not in {"SCI", "SCIE"}:
        if "SCIE" in indexing:
            indexing = "SCIE"
        elif re.search(r"\bSCI\b", indexing):
            indexing = "SCI"
    value = {
        "name": name,
        "issn": issn(raw_issn),
        "category": category,
        "quartile": quartile,
        "impact_factor": impact,
        "indexing": indexing,
        "jcr_year": year,
    }
    value["source_row_sha256"] = canonical_hash(value)
    return value


def normalized_export(path: Path) -> list[dict[str, Any]]:
    values = [normalize_jcr(row) for row in rows(path)]
    if not values:
        raise VenueCandidateError("JCR export contains no rows")
    return values


def match_row(spec: dict[str, Any], export: list[dict[str, Any]]) -> dict[str, Any]:
    wanted_issn = issn(spec.get("issn"))
    wanted_name = str(spec.get("name", "")).strip().casefold()
    matches = [
        row for row in export
        if (wanted_issn and row["issn"] == wanted_issn)
        or (wanted_name and row["name"].casefold() == wanted_name)
    ]
    if len(matches) != 1:
        raise VenueCandidateError(
            f"candidate {spec.get('name') or spec.get('issn')} must match exactly one JCR export row"
        )
    return matches[0]


def required_https(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.startswith("https://"):
        raise VenueCandidateError(f"{field_name} must be an HTTPS URL")
    return value


def build_registry(
    project: Path,
    spec_path: str,
    export_path: str,
    actor: str,
    source_url: str,
) -> dict[str, Any]:
    if not actor.strip():
        raise VenueCandidateError("actor is required")
    required_https(source_url, "source-url")
    spec_file = safe_file(project, spec_path)
    jcr_file = safe_file(project, export_path)
    try:
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VenueCandidateError(f"cannot read candidate specification: {exc}") from exc
    if not isinstance(spec, dict) or not isinstance(spec.get("papers"), list):
        raise VenueCandidateError("candidate specification must contain a papers array")
    export = normalized_export(jcr_file)
    current_years = {date.today().year, date.today().year - 1}
    paper_values: list[dict[str, Any]] = []
    seen_papers: set[str] = set()
    for paper_spec in spec["papers"]:
        if not isinstance(paper_spec, dict) or not PAPER_RE.fullmatch(str(paper_spec.get("paper_id", ""))):
            raise VenueCandidateError("each paper specification needs a paper_id such as P01")
        paper_id = str(paper_spec["paper_id"])
        if paper_id in seen_papers or not (project / "papers" / paper_id).is_dir():
            raise VenueCandidateError(f"paper is duplicate or absent from project: {paper_id}")
        seen_papers.add(paper_id)
        candidates = paper_spec.get("candidates")
        if not isinstance(candidates, list) or len(candidates) < 2:
            raise VenueCandidateError(f"{paper_id} requires at least two venue candidates")
        selected_count = sum(
            1 for item in candidates
            if isinstance(item, dict) and item.get("selection_status") == "selected"
        )
        if selected_count > 1:
            raise VenueCandidateError(f"{paper_id} may select at most one venue")
        normalized_candidates: list[dict[str, Any]] = []
        for item in candidates:
            if not isinstance(item, dict):
                raise VenueCandidateError(f"{paper_id} candidate must be an object")
            row = match_row(item, export)
            if row["quartile"] != "Q1" or row["impact_factor"] <= 1 or row["indexing"] not in {"SCI", "SCIE"}:
                raise VenueCandidateError(f"{row['name']} is not JCR Q1, IF > 1 and SCI/SCIE in the export")
            if row["jcr_year"] not in current_years:
                raise VenueCandidateError(f"{row['name']} JCR year is stale")
            status = item.get("selection_status", "candidate")
            if status not in {"candidate", "selected", "fallback"}:
                raise VenueCandidateError("selection_status must be candidate, selected or fallback")
            try:
                fit_score = float(item.get("fit_score"))
            except (TypeError, ValueError) as exc:
                raise VenueCandidateError("fit_score must be numeric") from exc
            if not 0 <= fit_score <= 100:
                raise VenueCandidateError("fit_score must be between 0 and 100")
            for key in ("article_type", "scope_fit"):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    raise VenueCandidateError(f"{key} is required")
            normalized_candidates.append(
                {
                    "rank": 0,
                    "venue_id": slug(str(item.get("venue_id") or row["name"])),
                    **{key: row[key] for key in ("name", "issn", "category", "quartile", "impact_factor", "indexing", "jcr_year")},
                    "jcr_source_url": source_url,
                    "official_guidelines_url": required_https(item.get("official_guidelines_url"), "official_guidelines_url"),
                    "policy_source_url": required_https(item.get("policy_source_url"), "policy_source_url"),
                    "article_type": item["article_type"].strip(),
                    "scope_fit": item["scope_fit"].strip(),
                    "fit_score": fit_score,
                    "selection_status": status,
                    "source_row_sha256": row["source_row_sha256"],
                }
            )
        normalized_candidates.sort(key=lambda item: (-item["fit_score"], item["name"].casefold()))
        for rank, candidate in enumerate(normalized_candidates, 1):
            candidate["rank"] = rank
        selected = next((item["venue_id"] for item in normalized_candidates if item["selection_status"] == "selected"), None)
        paper_values.append({"paper_id": paper_id, "selected_venue_id": selected, "candidates": normalized_candidates})
    expected = {path.name for path in (project / "papers").glob("P[0-9][0-9]") if path.is_dir()}
    if seen_papers != expected:
        raise VenueCandidateError("candidate specification must cover every project paper exactly once")
    return {
        "schema_version": "1.0",
        "generated_at": now(),
        "generated_by": "deterministic_local_control_plane",
        "jcr_export": {
            "path": jcr_file.relative_to(project).as_posix(),
            "sha256": sha256_file(jcr_file),
            "imported_by": actor.strip(),
            "imported_at": now(),
            "source_url": source_url,
            "row_count": len(export),
        },
        "papers": paper_values,
        "human_review_required": True,
    }


def validate_registry(project: Path, value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if value.get("schema_version") != "1.0" or value.get("generated_by") != "deterministic_local_control_plane":
        errors.append("venue registry must be schema 1.0 and generated by the local control plane")
    if value.get("human_review_required") is not True:
        errors.append("human_review_required must be true")
    export_record = value.get("jcr_export")
    export: list[dict[str, Any]] = []
    if not isinstance(export_record, dict):
        errors.append("jcr_export must be an object")
    else:
        try:
            path = safe_file(project, str(export_record.get("path")))
            if export_record.get("sha256") != sha256_file(path):
                errors.append("JCR export hash changed")
            export = normalized_export(path)
            if export_record.get("row_count") != len(export):
                errors.append("JCR export row_count changed")
        except VenueCandidateError as exc:
            errors.append(str(exc))
        if not str(export_record.get("source_url", "")).startswith("https://"):
            errors.append("jcr_export.source_url must use HTTPS")
        if not str(export_record.get("imported_by", "")).strip():
            errors.append("jcr_export.imported_by is required")
    rows_by_hash = {row["source_row_sha256"]: row for row in export}
    paper_values = value.get("papers")
    if not isinstance(paper_values, list):
        return errors + ["papers must be an array"]
    expected = {path.name for path in (project / "papers").glob("P[0-9][0-9]") if path.is_dir()}
    seen: set[str] = set()
    for paper in paper_values:
        if not isinstance(paper, dict):
            errors.append("paper entry must be an object")
            continue
        paper_id = str(paper.get("paper_id", ""))
        if not PAPER_RE.fullmatch(paper_id) or paper_id not in expected:
            errors.append(f"invalid or unknown paper_id: {paper_id}")
        if paper_id in seen:
            errors.append(f"duplicate paper entry: {paper_id}")
        seen.add(paper_id)
        candidates = paper.get("candidates")
        if not isinstance(candidates, list) or len(candidates) < 2:
            errors.append(f"{paper_id} requires at least two candidates")
            continue
        selected = [item for item in candidates if isinstance(item, dict) and item.get("selection_status") == "selected"]
        if len(selected) > 1:
            errors.append(f"{paper_id} has multiple selected venues")
        expected_selected = selected[0].get("venue_id") if selected else None
        if paper.get("selected_venue_id") != expected_selected:
            errors.append(f"{paper_id} selected_venue_id is inconsistent")
        seen_venues: set[str] = set()
        ranked_scores: list[float] = []
        for rank, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, dict):
                errors.append(f"{paper_id} candidate {rank} must be an object")
                continue
            if candidate.get("rank") != rank:
                errors.append(f"{paper_id} candidate ranks are not contiguous")
            venue_id = candidate.get("venue_id")
            if not isinstance(venue_id, str) or not re.fullmatch(r"[a-z0-9-]+", venue_id):
                errors.append(f"{paper_id} candidate {rank}.venue_id is invalid")
            elif venue_id in seen_venues:
                errors.append(f"{paper_id} repeats venue_id {venue_id}")
            else:
                seen_venues.add(venue_id)
            status = candidate.get("selection_status")
            if status not in {"candidate", "selected", "fallback"}:
                errors.append(f"{paper_id} candidate {rank}.selection_status is invalid")
            score = candidate.get("fit_score")
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 100:
                errors.append(f"{paper_id} candidate {rank}.fit_score must be between 0 and 100")
            else:
                ranked_scores.append(float(score))
            for key in ("article_type", "scope_fit"):
                if not isinstance(candidate.get(key), str) or not candidate[key].strip():
                    errors.append(f"{paper_id} candidate {rank}.{key} is required")
            row = rows_by_hash.get(candidate.get("source_row_sha256"))
            if row is None:
                errors.append(f"{paper_id} candidate {rank} is absent from the bound JCR export")
                continue
            for key in ("name", "issn", "category", "quartile", "impact_factor", "indexing", "jcr_year"):
                if candidate.get(key) != row.get(key):
                    errors.append(f"{paper_id} candidate {rank}.{key} differs from the JCR export")
            if row["quartile"] != "Q1" or row["impact_factor"] <= 1 or row["indexing"] not in {"SCI", "SCIE"}:
                errors.append(f"{paper_id} candidate {rank} fails the venue floor")
            if row["jcr_year"] not in {date.today().year, date.today().year - 1}:
                errors.append(f"{paper_id} candidate {rank} JCR year is stale")
            for key in ("jcr_source_url", "official_guidelines_url", "policy_source_url"):
                if not str(candidate.get(key, "")).startswith("https://"):
                    errors.append(f"{paper_id} candidate {rank}.{key} must use HTTPS")
        if ranked_scores != sorted(ranked_scores, reverse=True):
            errors.append(f"{paper_id} candidates are not ranked by descending fit_score")
    if seen != expected:
        errors.append("venue registry must cover every project paper exactly once")
    return errors


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--project", required=True)
    build.add_argument("--spec", required=True)
    build.add_argument("--jcr-export", required=True)
    build.add_argument("--actor", required=True)
    build.add_argument("--source-url", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--project", required=True)
    return root


def main(argv: Iterable[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        project = project_path(args.project)
        output = project / "program" / "venue-candidates.json"
        if args.command == "build":
            value = build_registry(project, args.spec, args.jcr_export, args.actor, args.source_url)
            atomic_json(output, value)
            print(output.relative_to(project).as_posix())
        else:
            value = json.loads(output.read_text(encoding="utf-8"))
            errors = validate_registry(project, value)
            print(json.dumps({"status": "pass" if not errors else "block", "errors": errors}, indent=2))
            if errors:
                raise VenueCandidateError(f"{len(errors)} venue candidate requirement(s) remain")
        return 0
    except (VenueCandidateError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
