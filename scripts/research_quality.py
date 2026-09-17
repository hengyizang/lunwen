#!/usr/bin/env python3
"""Evidence-bound novelty, data-quality, power and reproducibility controls.

The mandatory validators are dependency-free.  Optional, reviewed upstream
packages can create richer reports, but a model-authored assertion never
substitutes for a local file hash or a successful experiment-registry entry.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
PAPER_RE = re.compile(r"^P[0-9]{2}$")
DATASET_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
TABULAR_SUFFIXES = {".csv", ".tsv", ".jsonl"}
REVIEWED_STATSMODELS_VERSION = "0.15.0"


class ResearchQualityError(RuntimeError):
    """Raised for unsafe paths, invalid evidence or unavailable calculations."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(payload)
        temporary = handle.name
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchQualityError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchQualityError(f"expected a JSON object: {path}")
    return value


def _project(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", slug):
        raise ResearchQualityError("project must be a safe 2-63 character slug")
    project = PROJECTS_ROOT / slug
    if not project.is_dir():
        raise ResearchQualityError(f"project does not exist: {slug}")
    return project


def _safe_path(project: Path, value: str, *, must_exist: bool = True) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ResearchQualityError("paths must be project-relative and cannot contain ..")
    target = (project / relative).resolve()
    root = project.resolve()
    if target == root or root not in target.parents:
        raise ResearchQualityError("path escapes the project directory")
    if must_exist and not target.exists():
        raise ResearchQualityError(f"path does not exist: {value}")
    return target


def _text(value: Any, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string")
        return None
    return value.strip()


def _string_list(
    value: Any, field: str, errors: list[str], minimum: int = 1
) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        errors.append(f"{field} must contain at least {minimum} item(s)")
        return []
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{field} must contain only non-empty strings")
        return []
    result = [item.strip() for item in value]
    if len(set(result)) != len(result):
        errors.append(f"{field} must not contain duplicates")
    return result


def _paper_ids(project: Path) -> list[str]:
    return [path.name for path in sorted((project / "papers").glob("P[0-9][0-9]"))]


def _manifest_map(project: Path) -> dict[str, dict[str, Any]]:
    path = project / "data" / "datasets.jsonl"
    manifests: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return manifests
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ResearchQualityError(f"invalid datasets.jsonl line {number}: {exc}") from exc
        if isinstance(item, dict) and item.get("dataset_id"):
            dataset_id = str(item["dataset_id"])
            if dataset_id in manifests:
                raise ResearchQualityError(
                    f"duplicate dataset_id in datasets.jsonl: {dataset_id}"
                )
            manifests[dataset_id] = item
    return manifests


def _registry(project: Path) -> list[dict[str, Any]]:
    path = project / "experiments" / "registry.jsonl"
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ResearchQualityError(
                f"invalid experiments/registry.jsonl line {number}: {exc}"
            ) from exc
        if isinstance(value, dict):
            records.append(value)
        else:
            raise ResearchQualityError(
                f"experiments/registry.jsonl line {number} must be a JSON object"
            )
    return records


def validate_novelty_claim_matrix(
    matrix: dict[str, Any], originality: dict[str, Any], searches: list[dict[str, Any]] | None = None
) -> list[str]:
    """Require claim-level closest-work differences and search saturation."""

    errors: list[str] = []
    if matrix.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if matrix.get("status") != "ready_for_review":
        errors.append("status must be ready_for_review")
    works_value = originality.get("closest_prior_work")
    works = works_value if isinstance(works_value, list) else []
    known_works = {
        str(item.get("id"))
        for item in works if isinstance(item, dict) and item.get("id")
    }
    source_claim_values = originality.get("novelty_claims")
    source_claims = source_claim_values if isinstance(source_claim_values, list) else []
    expected_claims = {
        str(item.get("claim_id"))
        for item in source_claims
        if isinstance(item, dict) and item.get("claim_id")
    }
    claims = matrix.get("claims")
    if not isinstance(claims, list) or not claims:
        errors.append("claims must be a non-empty array")
        claims = []
    seen: set[str] = set()
    for index, item in enumerate(claims):
        prefix = f"claims[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        claim_id = _text(item.get("claim_id"), f"{prefix}.claim_id", errors)
        if claim_id:
            if claim_id in seen:
                errors.append(f"{prefix}.claim_id is duplicated")
            seen.add(claim_id)
        for key in (
            "claim",
            "already_known",
            "precise_difference",
            "mechanism_or_rationale",
            "falsification_test",
            "expected_if_false",
            "boundary_conditions",
            "residual_risk",
        ):
            _text(item.get(key), f"{prefix}.{key}", errors)
        evidence = _string_list(
            item.get("closest_work_ids"), f"{prefix}.closest_work_ids", errors, 3
        )
        unknown = sorted(set(evidence) - known_works)
        if unknown:
            errors.append(f"{prefix}.closest_work_ids reference unknown work: {', '.join(unknown)}")
        papers = _string_list(item.get("paper_ids"), f"{prefix}.paper_ids", errors, 1)
        invalid_papers = [paper for paper in papers if not PAPER_RE.fullmatch(paper)]
        if invalid_papers:
            errors.append(f"{prefix}.paper_ids contain invalid IDs: {', '.join(invalid_papers)}")
    if expected_claims and seen != expected_claims:
        missing = sorted(expected_claims - seen)
        extra = sorted(seen - expected_claims)
        if missing:
            errors.append("matrix is missing originality claims: " + ", ".join(missing))
        if extra:
            errors.append("matrix contains claims absent from originality audit: " + ", ".join(extra))

    saturation = matrix.get("search_saturation")
    if not isinstance(saturation, dict):
        errors.append("search_saturation must be an object")
    else:
        for field in ("exact_query_rounds", "adjacent_field_rounds"):
            value = saturation.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 2:
                errors.append(f"search_saturation.{field} must be an integer >= 2")
        if saturation.get("backward_chaining_complete") is not True:
            errors.append("search_saturation.backward_chaining_complete must be true")
        if saturation.get("forward_chaining_complete") is not True:
            errors.append("search_saturation.forward_chaining_complete must be true")
        supporting = _string_list(
            saturation.get("supporting_search_ids"),
            "search_saturation.supporting_search_ids",
            errors,
            4,
        )
        backward = _string_list(
            saturation.get("backward_chaining_search_ids"),
            "search_saturation.backward_chaining_search_ids",
            errors,
        )
        forward = _string_list(
            saturation.get("forward_chaining_search_ids"),
            "search_saturation.forward_chaining_search_ids",
            errors,
        )
        if not set(backward + forward).issubset(set(supporting)):
            errors.append("citation-chaining search IDs must be included in supporting_search_ids")
        if searches is not None:
            known_searches = {
                str(item.get("search_id"))
                for item in searches
                if isinstance(item, dict) and item.get("search_id")
            }
            unknown_searches = sorted(set(supporting) - known_searches)
            if unknown_searches:
                errors.append(
                    "search_saturation references unknown search-log IDs: "
                    + ", ".join(unknown_searches)
                )
        rounds = saturation.get("consecutive_no_material_new_work_rounds")
        if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds < 2:
            errors.append(
                "search_saturation.consecutive_no_material_new_work_rounds must be >= 2"
            )
        no_new_rounds = saturation.get("no_material_new_work_rounds")
        if not isinstance(no_new_rounds, list) or len(no_new_rounds) < 2:
            errors.append("search_saturation.no_material_new_work_rounds must contain at least two rounds")
            no_new_rounds = []
        round_ids: set[str] = set()
        for index, item in enumerate(no_new_rounds):
            prefix = f"search_saturation.no_material_new_work_rounds[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} must be an object")
                continue
            round_id = _text(item.get("round_id"), f"{prefix}.round_id", errors)
            if round_id:
                if round_id in round_ids:
                    errors.append(f"{prefix}.round_id is duplicated")
                round_ids.add(round_id)
            round_searches = _string_list(item.get("search_ids"), f"{prefix}.search_ids", errors)
            if not set(round_searches).issubset(set(supporting)):
                errors.append(f"{prefix}.search_ids must be included in supporting_search_ids")
            if item.get("material_new_closest_work_count") != 0:
                errors.append(f"{prefix}.material_new_closest_work_count must be zero")
            _text(item.get("stopping_reason"), f"{prefix}.stopping_reason", errors)
        if isinstance(rounds, int) and not isinstance(rounds, bool) and rounds != len(no_new_rounds):
            errors.append("consecutive_no_material_new_work_rounds must equal the recorded round count")
        if saturation.get("unresolved_search_gaps") != []:
            errors.append("search_saturation.unresolved_search_gaps must be an empty array")
        _text(saturation.get("saturation_rationale"), "search_saturation.saturation_rationale", errors)
    if matrix.get("human_review_required") is not True:
        errors.append("human_review_required must be true")
    return errors


def _iter_rows(path: Path, maximum: int) -> tuple[list[str], list[dict[str, str]], bool]:
    suffix = path.suffix.lower()
    rows: list[dict[str, str]] = []
    complete = True
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            fields = [str(item) for item in (reader.fieldnames or [])]
            for index, row in enumerate(reader):
                if index >= maximum:
                    complete = False
                    break
                rows.append({str(key): "" if value is None else str(value) for key, value in row.items()})
        return fields, rows, complete
    if suffix == ".jsonl":
        fields: list[str] = []
        seen_fields: set[str] = set()
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index >= maximum:
                    complete = False
                    break
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ResearchQualityError("JSONL rows must be objects")
                row = {str(key): "" if item is None else str(item) for key, item in value.items()}
                for key in row:
                    if key not in seen_fields:
                        fields.append(key)
                        seen_fields.add(key)
                rows.append(row)
        return fields, rows, complete
    raise ResearchQualityError("automatic row audit supports CSV, TSV and JSONL")


def _row_key(row: dict[str, str], fields: Iterable[str]) -> str:
    payload = json.dumps([row.get(field, "") for field in fields], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_data_quality_report(
    project: Path,
    dataset_id: str,
    relative_path: str,
    *,
    actor: str,
    label_column: str | None = None,
    split_column: str | None = None,
    group_column: str | None = None,
    derived: bool = False,
    maximum_rows: int = 1_000_000,
) -> dict[str, Any]:
    manifests = _manifest_map(project)
    if dataset_id not in manifests:
        raise ResearchQualityError(f"dataset_id is absent from data/datasets.jsonl: {dataset_id}")
    if not actor.strip():
        raise ResearchQualityError("actor is required to record who initiated the local audit")
    source = _safe_path(project, relative_path)
    if source.is_symlink():
        raise ResearchQualityError("dataset audit does not accept symlinks")
    files = [source] if source.is_file() else sorted(
        path for path in source.rglob("*") if path.is_file() and not path.is_symlink()
    )
    if not files:
        raise ResearchQualityError("dataset path contains no regular files")
    inventory = [
        {
            "path": path.relative_to(project).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in files
    ]
    blockers: list[str] = []
    warnings: list[str] = []
    tabular = [path for path in files if path.suffix.lower() in TABULAR_SUFFIXES]
    table: dict[str, Any] | None = None
    if len(files) == 1 and len(tabular) == 1:
        try:
            fields, rows, complete = _iter_rows(source, maximum_rows)
        except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
            raise ResearchQualityError(f"cannot parse dataset: {exc}") from exc
        if not fields:
            blockers.append("tabular data has no header fields")
        if not rows:
            blockers.append("tabular data has no rows")
        if not complete:
            blockers.append("row limit reached; a complete scan is required")
        row_keys = [_row_key(row, fields) for row in rows]
        duplicates = len(row_keys) - len(set(row_keys))
        missing = {
            field: sum(1 for row in rows if not row.get(field, "").strip())
            for field in fields
        }
        constant = [
            field for field in fields
            if rows and len({row.get(field, "") for row in rows}) <= 1
        ]
        if rows and duplicates / len(rows) > 0.20:
            warnings.append("more than 20% of rows are exact duplicates")
        if constant:
            warnings.append("constant columns require review: " + ", ".join(constant))
        labels: dict[str, int] | None = None
        if label_column:
            if label_column not in fields:
                blockers.append(f"label column is absent: {label_column}")
            else:
                labels = dict(Counter(row.get(label_column, "") for row in rows))
                nonempty = [count for value, count in labels.items() if value]
                if nonempty and max(nonempty) / sum(nonempty) > 0.95:
                    warnings.append("largest non-empty label class exceeds 95% of labeled rows")
        split_overlap: dict[str, Any] | None = None
        if split_column:
            if split_column not in fields:
                blockers.append(f"split column is absent: {split_column}")
            else:
                identity_fields = [field for field in fields if field != split_column]
                by_split: dict[str, set[str]] = {}
                for row in rows:
                    by_split.setdefault(row.get(split_column, ""), set()).add(
                        _row_key(row, identity_fields)
                    )
                overlap: set[str] = set()
                names = sorted(by_split)
                for left_index, left in enumerate(names):
                    for right in names[left_index + 1:]:
                        overlap.update(by_split[left] & by_split[right])
                split_overlap = {"split_values": names, "exact_row_overlap_count": len(overlap)}
                if overlap:
                    blockers.append("identical observations occur in multiple splits")
        group_overlap: dict[str, Any] | None = None
        if group_column and split_column:
            if group_column not in fields:
                blockers.append(f"group column is absent: {group_column}")
            elif split_column in fields:
                group_splits: dict[str, set[str]] = {}
                for row in rows:
                    group_splits.setdefault(row.get(group_column, ""), set()).add(
                        row.get(split_column, "")
                    )
                leaking = sorted(group for group, splits in group_splits.items() if len(splits) > 1)
                group_overlap = {
                    "group_column": group_column,
                    "groups_crossing_splits": len(leaking),
                    "examples": leaking[:20],
                }
                if leaking:
                    blockers.append("group identifiers occur in multiple splits")
        table = {
            "format": source.suffix.lower().lstrip("."),
            "complete_scan": complete,
            "row_count": len(rows),
            "column_count": len(fields),
            "columns": fields,
            "missing_count_by_column": missing,
            "exact_duplicate_rows": duplicates,
            "constant_columns": constant,
            "label_column": label_column,
            "label_distribution": labels,
            "split_column": split_column,
            "split_overlap": split_overlap,
            "group_overlap": group_overlap,
        }
    else:
        warnings.append(
            "automatic cell-level checks were unavailable for a multi-file or non-tabular dataset"
        )

    manifest = manifests[dataset_id]
    download = manifest.get("download") if isinstance(manifest.get("download"), dict) else {}
    expected_hash = str(download.get("sha256", "")).lower()
    canonical_match = len(inventory) == 1 and inventory[0]["sha256"] == expected_hash
    if expected_hash == "pending":
        blockers.append("dataset manifest checksum is still pending")
    elif not derived and not canonical_match:
        blockers.append("audited file hash does not match the canonical manifest checksum")
    elif derived:
        provenance = manifest.get("provenance") if isinstance(manifest.get("provenance"), dict) else {}
        transformations = provenance.get("transformations")
        if not isinstance(transformations, list) or not transformations:
            blockers.append("derived data requires recorded manifest transformations")

    report = {
        "schema_version": "1.0",
        "dataset_id": dataset_id,
        "created_at": utc_now(),
        "generated_by": "deterministic_local_control_plane",
        "source_path": source.relative_to(project).as_posix(),
        "derived_data": derived,
        "manifest_download_sha256": expected_hash,
        "canonical_hash_match": canonical_match,
        "inventory": inventory,
        "tabular_profile": table,
        "optional_upstreams": optional_tool_status(),
        "blockers": blockers,
        "warnings": warnings,
        "initiated_by": actor.strip(),
        "human_review_required": True,
        "status": "pass" if not blockers else "block",
    }
    return report


def validate_data_quality_report(
    report: dict[str, Any], dataset_id: str, project: Path
) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if report.get("dataset_id") != dataset_id:
        errors.append(f"dataset_id must be {dataset_id}")
    if report.get("generated_by") != "deterministic_local_control_plane":
        errors.append("report must be generated by the deterministic local control plane")
    if report.get("status") != "pass" or report.get("blockers") != []:
        errors.append("data-quality report must pass with no blockers")
    try:
        manifest = _manifest_map(project).get(dataset_id)
    except ResearchQualityError as exc:
        errors.append(str(exc))
        manifest = None
    if manifest is None:
        errors.append("dataset is absent from the current data/datasets.jsonl")
    else:
        download = manifest.get("download") if isinstance(manifest.get("download"), dict) else {}
        current_manifest_hash = str(download.get("sha256", "")).lower()
        if report.get("manifest_download_sha256") != current_manifest_hash:
            errors.append("manifest_download_sha256 differs from the current dataset manifest")
    _text(report.get("initiated_by"), "initiated_by", errors)
    if report.get("human_review_required") is not True:
        errors.append("human_review_required must be true")
    inventory = report.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        errors.append("inventory must be non-empty")
        return errors
    for index, item in enumerate(inventory):
        if not isinstance(item, dict):
            errors.append(f"inventory[{index}] must be an object")
            continue
        try:
            path = _safe_path(project, str(item.get("path")))
        except ResearchQualityError as exc:
            errors.append(f"inventory[{index}]: {exc}")
            continue
        if not path.is_file():
            errors.append(f"inventory[{index}] is not a regular file")
        elif item.get("sha256") != sha256_file(path):
            errors.append(f"inventory[{index}] hash changed")
        elif item.get("bytes") != path.stat().st_size:
            errors.append(f"inventory[{index}] size changed")
    return errors


def create_data_quality_confirmation(
    project: Path, dataset_id: str, actor: str
) -> dict[str, Any]:
    if not actor.strip():
        raise ResearchQualityError("actor is required")
    report_path = project / "data" / "quality" / f"{dataset_id}.json"
    report = _load_json(report_path)
    errors = validate_data_quality_report(report, dataset_id, project)
    if errors:
        raise ResearchQualityError(
            "cannot confirm an invalid data-quality report: " + "; ".join(errors)
        )
    warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
    return {
        "schema_version": "1.0",
        "dataset_id": dataset_id,
        "generated_by": "deterministic_local_control_plane",
        "confirmed_by": actor.strip(),
        "confirmed_at": utc_now(),
        "data_quality_report_sha256": sha256_file(report_path),
        "reviewed_warning_count": len(warnings),
        "statement": (
            "I reviewed the local data-quality report, its warnings, source provenance, "
            "label validity and the scientific suitability limits that deterministic scanning cannot establish."
        ),
    }


def validate_data_quality_confirmation(
    confirmation: dict[str, Any], dataset_id: str, project: Path
) -> list[str]:
    errors: list[str] = []
    if confirmation.get("schema_version") != "1.0" or confirmation.get("dataset_id") != dataset_id:
        errors.append("data-quality confirmation schema/dataset does not match")
    if confirmation.get("generated_by") != "deterministic_local_control_plane":
        errors.append("data-quality confirmation must be generated locally")
    _text(confirmation.get("confirmed_by"), "confirmed_by", errors)
    _text(confirmation.get("confirmed_at"), "confirmed_at", errors)
    _text(confirmation.get("statement"), "statement", errors)
    warning_count = confirmation.get("reviewed_warning_count")
    if not isinstance(warning_count, int) or isinstance(warning_count, bool) or warning_count < 0:
        errors.append("reviewed_warning_count must be a non-negative integer")
    report_path = project / "data" / "quality" / f"{dataset_id}.json"
    if not report_path.is_file() or confirmation.get("data_quality_report_sha256") != sha256_file(report_path):
        errors.append("data_quality_report_sha256 is missing or stale")
    else:
        try:
            report = _load_json(report_path)
        except ResearchQualityError as exc:
            errors.append(str(exc))
        else:
            warnings = report.get("warnings") if isinstance(report.get("warnings"), list) else []
            if warning_count != len(warnings):
                errors.append("reviewed_warning_count does not match the current report")
    return errors


def optional_tool_status() -> dict[str, dict[str, Any]]:
    packages = {
        "statsmodels": "statsmodels",
        "fg-data-profiling": "fg-data-profiling",
        "pandera": "pandera",
        "evidently": "evidently",
        "dvc": "dvc",
    }
    result: dict[str, dict[str, Any]] = {}
    for label, package in packages.items():
        try:
            version = metadata.version(package)
        except metadata.PackageNotFoundError:
            result[label] = {"available": False, "version": None}
        else:
            result[label] = {"available": True, "version": version}
    return result


def _design_paths(project: Path, paper_id: str) -> list[Path]:
    return sorted((project / "papers" / paper_id / "experiments").glob("*.json"))


def create_power_report(
    project: Path,
    paper_id: str,
    method: str,
    effect_size: float,
    alpha: float,
    target_power: float,
    ratio: float,
    effect_size_basis: str,
    groups: int = 2,
) -> dict[str, Any]:
    if not PAPER_RE.fullmatch(paper_id) or not (project / "papers" / paper_id).is_dir():
        raise ResearchQualityError("paper must be an existing ID such as P01")
    if not 0 < effect_size:
        raise ResearchQualityError("effect size must be positive")
    if not 0 < alpha < 1 or not 0 < target_power < 1 or ratio <= 0:
        raise ResearchQualityError("alpha, target power and ratio are outside valid ranges")
    if not effect_size_basis.strip():
        raise ResearchQualityError("effect-size-basis is required")
    if groups < 2:
        raise ResearchQualityError("groups must be at least two")
    try:
        import statsmodels  # type: ignore
        from statsmodels.stats.power import FTestAnovaPower, NormalIndPower, TTestIndPower, TTestPower  # type: ignore
    except ImportError as exc:
        raise ResearchQualityError(
            "statsmodels is required; run bash scripts/bootstrap-wsl.sh --with-research-quality-tools"
        ) from exc
    if statsmodels.__version__ != REVIEWED_STATSMODELS_VERSION:
        raise ResearchQualityError(
            "statsmodels version is not the reviewed target; run "
            "bash scripts/bootstrap-wsl.sh --with-research-quality-tools"
        )
    if method == "ttest_ind":
        per_group = float(TTestIndPower().solve_power(
            effect_size=effect_size, alpha=alpha, power=target_power, ratio=ratio
        ))
        sample = {"group_1": math.ceil(per_group), "group_2": math.ceil(per_group * ratio)}
    elif method in {"ttest_paired", "ttest_one_sample"}:
        nobs = float(TTestPower().solve_power(
            effect_size=effect_size, alpha=alpha, power=target_power
        ))
        sample = {"pairs" if method == "ttest_paired" else "observations": math.ceil(nobs)}
    elif method == "anova":
        nobs = float(FTestAnovaPower().solve_power(
            effect_size=effect_size, alpha=alpha, power=target_power, k_groups=groups
        ))
        sample = {"total_observations": math.ceil(nobs)}
    elif method == "proportion_ind":
        per_group = float(NormalIndPower().solve_power(
            effect_size=effect_size, alpha=alpha, power=target_power, ratio=ratio
        ))
        sample = {"group_1": math.ceil(per_group), "group_2": math.ceil(per_group * ratio)}
    else:
        raise ResearchQualityError(
            "method must be ttest_ind, ttest_paired, ttest_one_sample, anova or proportion_ind"
        )
    contract = project / "papers" / paper_id / "paper-contract.json"
    designs = _design_paths(project, paper_id)
    if not contract.is_file() or not designs:
        raise ResearchQualityError("paper contract and at least one experiment design are required")
    bindings = [contract, *designs]
    return {
        "schema_version": "1.0",
        "paper_id": paper_id,
        "created_at": utc_now(),
        "generated_by": "statsmodels",
        "engine_version": statsmodels.__version__,
        "method": method,
        "effect_size": effect_size,
        "effect_size_basis": effect_size_basis.strip(),
        "alpha": alpha,
        "target_power": target_power,
        "allocation_ratio": ratio,
        "group_count": groups if method == "anova" else None,
        "required_sample_size": sample,
        "assumptions": [
            "The standardized effect size is defined before confirmatory execution.",
            "Independence and distributional assumptions must be checked against the study design.",
            "Attrition, grouping and multiplicity require separate inflation where applicable.",
        ],
        "bound_files": [
            {"path": path.relative_to(project).as_posix(), "sha256": sha256_file(path)}
            for path in bindings
        ],
        "status": "ready_for_review",
        "human_review_required": True,
    }


def create_simulation_power_report(
    project: Path,
    paper_id: str,
    effect_size: float,
    alpha: float,
    target_power: float,
    simulation_count: int,
    achieved_power: float,
    script_path: str,
    evidence_path: str,
    method_note: str,
    effect_size_basis: str,
) -> dict[str, Any]:
    if not PAPER_RE.fullmatch(paper_id) or not (project / "papers" / paper_id).is_dir():
        raise ResearchQualityError("paper must be an existing ID such as P01")
    if simulation_count < 1000:
        raise ResearchQualityError("simulation-count must be at least 1000")
    if not 0 < effect_size or not 0 < alpha < 1 or not 0 < target_power < 1:
        raise ResearchQualityError("effect size, alpha and target power are outside valid ranges")
    if not 0 <= achieved_power <= 1 or achieved_power < target_power:
        raise ResearchQualityError("achieved power must be in [0,1] and meet target power")
    if not method_note.strip():
        raise ResearchQualityError("method-note is required")
    if not effect_size_basis.strip():
        raise ResearchQualityError("effect-size-basis is required")
    script = _safe_path(project, script_path)
    evidence = _safe_path(project, evidence_path)
    if not script.is_file() or not evidence.is_file():
        raise ResearchQualityError("simulation script and evidence must be regular files")
    evidence_value = _load_json(evidence)
    evidence_errors: list[str] = []
    if evidence_value.get("schema_version") != "1.0":
        evidence_errors.append("schema_version must be 1.0")
    if evidence_value.get("simulation_count") != simulation_count:
        evidence_errors.append("simulation_count differs from the command")
    rejection_count = evidence_value.get("rejection_count")
    if (
        not isinstance(rejection_count, int)
        or isinstance(rejection_count, bool)
        or not 0 <= rejection_count <= simulation_count
    ):
        evidence_errors.append("rejection_count must be an integer within simulation_count")
    evidence_power = evidence_value.get("achieved_power")
    if (
        not isinstance(evidence_power, (int, float))
        or isinstance(evidence_power, bool)
        or not math.isclose(float(evidence_power), achieved_power, rel_tol=0.0, abs_tol=1e-12)
    ):
        evidence_errors.append("achieved_power differs from the command")
    if isinstance(rejection_count, int) and not isinstance(rejection_count, bool):
        computed_power = rejection_count / simulation_count
        if not math.isclose(computed_power, achieved_power, rel_tol=0.0, abs_tol=1e-12):
            evidence_errors.append("achieved_power must equal rejection_count / simulation_count")
    evidence_effect = evidence_value.get("effect_size")
    if (
        not isinstance(evidence_effect, (int, float))
        or isinstance(evidence_effect, bool)
        or not math.isclose(float(evidence_effect), effect_size, rel_tol=0.0, abs_tol=1e-12)
    ):
        evidence_errors.append("effect_size differs from the command")
    evidence_alpha = evidence_value.get("alpha")
    if (
        not isinstance(evidence_alpha, (int, float))
        or isinstance(evidence_alpha, bool)
        or not math.isclose(float(evidence_alpha), alpha, rel_tol=0.0, abs_tol=1e-12)
    ):
        evidence_errors.append("alpha differs from the command")
    seeds = evidence_value.get("random_seeds")
    if (
        not isinstance(seeds, list)
        or not seeds
        or any(not isinstance(seed, int) or isinstance(seed, bool) for seed in seeds)
    ):
        evidence_errors.append("random_seeds must be a non-empty integer array")
    for field in ("decision_rule", "data_generating_process"):
        _text(evidence_value.get(field), field, evidence_errors)
    script_digest = sha256_file(script)
    if evidence_value.get("generated_by_script_sha256") != script_digest:
        evidence_errors.append("generated_by_script_sha256 does not match the simulation script")
    if evidence_errors:
        raise ResearchQualityError(
            "simulation evidence is invalid: " + "; ".join(evidence_errors)
        )
    contract = project / "papers" / paper_id / "paper-contract.json"
    designs = _design_paths(project, paper_id)
    if not contract.is_file() or not designs:
        raise ResearchQualityError("paper contract and at least one experiment design are required")
    bindings = [contract, *designs, script, evidence]
    return {
        "schema_version": "1.0",
        "paper_id": paper_id,
        "created_at": utc_now(),
        "generated_by": "simulation",
        "method": "monte_carlo_simulation",
        "effect_size": effect_size,
        "effect_size_basis": effect_size_basis.strip(),
        "alpha": alpha,
        "target_power": target_power,
        "simulation_count": simulation_count,
        "rejection_count": rejection_count,
        "achieved_power": achieved_power,
        "simulation_method": method_note.strip(),
        "random_seeds": seeds,
        "bound_files": [
            {"path": path.relative_to(project).as_posix(), "sha256": sha256_file(path)}
            for path in bindings
        ],
        "status": "ready_for_review",
        "human_review_required": True,
    }


def validate_power_report(report: dict[str, Any], paper_id: str, project: Path) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if report.get("paper_id") != paper_id:
        errors.append(f"paper_id must be {paper_id}")
    if report.get("status") != "ready_for_review":
        errors.append("status must be ready_for_review")
    if report.get("human_review_required") is not True:
        errors.append("human_review_required must be true")
    _text(report.get("effect_size_basis"), "effect_size_basis", errors)
    engine = report.get("generated_by")
    if engine == "statsmodels":
        if report.get("engine_version") != REVIEWED_STATSMODELS_VERSION:
            errors.append(
                f"engine_version must be the reviewed {REVIEWED_STATSMODELS_VERSION}"
            )
        if report.get("method") not in {
            "ttest_ind", "ttest_paired", "ttest_one_sample", "anova", "proportion_ind"
        }:
            errors.append("method is not a supported statsmodels calculation")
        if not isinstance(report.get("required_sample_size"), dict) or not report["required_sample_size"]:
            errors.append("required_sample_size must be a non-empty object")
    elif engine == "simulation":
        simulations = report.get("simulation_count")
        if not isinstance(simulations, int) or isinstance(simulations, bool) or simulations < 1000:
            errors.append("simulation_count must be at least 1000")
        achieved = report.get("achieved_power")
        target = report.get("target_power")
        if not isinstance(achieved, (int, float)) or not isinstance(target, (int, float)) or achieved < target:
            errors.append("achieved_power must meet target_power")
        rejections = report.get("rejection_count")
        if (
            not isinstance(rejections, int)
            or isinstance(rejections, bool)
            or not isinstance(simulations, int)
            or not 0 <= rejections <= simulations
        ):
            errors.append("rejection_count must be an integer within simulation_count")
        elif isinstance(achieved, (int, float)) and not math.isclose(
            rejections / simulations, float(achieved), rel_tol=0.0, abs_tol=1e-12
        ):
            errors.append("achieved_power must equal rejection_count / simulation_count")
        seeds = report.get("random_seeds")
        if (
            not isinstance(seeds, list)
            or not seeds
            or any(not isinstance(seed, int) or isinstance(seed, bool) for seed in seeds)
        ):
            errors.append("random_seeds must be a non-empty integer array")
        _text(report.get("simulation_method"), "simulation_method", errors)
    else:
        errors.append("generated_by must be statsmodels or simulation")
    effect = report.get("effect_size")
    alpha = report.get("alpha")
    target_power = report.get("target_power")
    if not isinstance(effect, (int, float)) or isinstance(effect, bool) or effect <= 0:
        errors.append("effect_size must be a positive number")
    if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not 0 < alpha < 1:
        errors.append("alpha must be between zero and one")
    if not isinstance(target_power, (int, float)) or isinstance(target_power, bool) or not 0 < target_power < 1:
        errors.append("target_power must be between zero and one")
    if engine == "statsmodels" and isinstance(report.get("required_sample_size"), dict):
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1
            for value in report["required_sample_size"].values()
        ):
            errors.append("required_sample_size values must be positive integers")
    bindings = report.get("bound_files")
    if not isinstance(bindings, list) or not bindings:
        errors.append("bound_files must be non-empty")
    else:
        for index, item in enumerate(bindings):
            if not isinstance(item, dict):
                errors.append(f"bound_files[{index}] must be an object")
                continue
            try:
                path = _safe_path(project, str(item.get("path")))
            except ResearchQualityError as exc:
                errors.append(f"bound_files[{index}]: {exc}")
                continue
            if not path.is_file() or item.get("sha256") != sha256_file(path):
                errors.append(f"bound_files[{index}] is missing or changed")
    return errors


def _preregistration_inputs(project: Path, paper_id: str) -> list[Path]:
    contract = project / "papers" / paper_id / "paper-contract.json"
    power = project / "papers" / paper_id / "power-analysis.json"
    common = [
        project / "data" / "datasets.jsonl",
        project / "experiments" / "plan.json",
        project / "experiments" / "budget.json",
        contract,
        power,
    ]
    try:
        contract_value = _load_json(contract)
    except ResearchQualityError:
        contract_value = {}
    dataset_ids = contract_value.get("datasets") if isinstance(contract_value.get("datasets"), list) else []
    data_reports = [project / "data" / "quality" / f"{dataset_id}.json" for dataset_id in dataset_ids]
    data_confirmations = [
        project / "data" / "quality" / f"{dataset_id}-confirmation.json"
        for dataset_id in dataset_ids
    ]
    return [*common, *_design_paths(project, paper_id), *data_reports, *data_confirmations]


def create_preregistration(project: Path, paper_id: str, actor: str) -> dict[str, Any]:
    if not actor.strip():
        raise ResearchQualityError("actor is required")
    registry = project / "experiments" / "registry.jsonl"
    if registry.is_file() and registry.read_text(encoding="utf-8").strip():
        raise ResearchQualityError("cannot freeze a preregistration after experiment attempts exist")
    inputs = _preregistration_inputs(project, paper_id)
    missing = [path.relative_to(project).as_posix() for path in inputs if not path.is_file()]
    if missing:
        raise ResearchQualityError("cannot freeze; missing inputs: " + ", ".join(missing))
    power_errors = validate_power_report(_load_json(project / "papers" / paper_id / "power-analysis.json"), paper_id, project)
    if power_errors:
        raise ResearchQualityError("power analysis is invalid: " + "; ".join(power_errors))
    manifests = _manifest_map(project)
    contract = _load_json(project / "papers" / paper_id / "paper-contract.json")
    for dataset_id in contract.get("datasets", []) if isinstance(contract.get("datasets"), list) else []:
        report = _load_json(project / "data" / "quality" / f"{dataset_id}.json")
        issues = validate_data_quality_report(report, str(dataset_id), project)
        confirmation_path = project / "data" / "quality" / f"{dataset_id}-confirmation.json"
        if confirmation_path.is_file():
            issues.extend(
                validate_data_quality_confirmation(
                    _load_json(confirmation_path), str(dataset_id), project
                )
            )
        else:
            issues.append("named human data-quality confirmation is missing")
        if str(dataset_id) not in manifests:
            issues.append("dataset is absent from data/datasets.jsonl")
        if issues:
            raise ResearchQualityError(f"data quality for {dataset_id} is invalid: " + "; ".join(issues))
    return {
        "schema_version": "1.0",
        "paper_id": paper_id,
        "status": "frozen",
        "frozen_at": utc_now(),
        "frozen_by": actor.strip(),
        "generated_by": "deterministic_local_control_plane",
        "confirmatory_lock": True,
        "files": [
            {"path": path.relative_to(project).as_posix(), "sha256": sha256_file(path)}
            for path in sorted(set(inputs))
        ],
        "deviation_policy": (
            "Any post-freeze change must be logged before inspecting the affected outcome, "
            "justified, and labeled protocol deviation or exploratory analysis."
        ),
        "human_confirmation": True,
    }


def validate_preregistration(report: dict[str, Any], paper_id: str, project: Path) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != "1.0" or report.get("status") != "frozen":
        errors.append("preregistration must be schema 1.0 with status frozen")
    if report.get("paper_id") != paper_id:
        errors.append(f"paper_id must be {paper_id}")
    if report.get("generated_by") != "deterministic_local_control_plane":
        errors.append("preregistration must be generated locally")
    if report.get("confirmatory_lock") is not True or report.get("human_confirmation") is not True:
        errors.append("confirmatory lock and human confirmation must be true")
    _text(report.get("frozen_by"), "frozen_by", errors)
    _text(report.get("deviation_policy"), "deviation_policy", errors)
    files = report.get("files")
    recorded: dict[str, str] = {}
    if not isinstance(files, list) or not files:
        errors.append("files must be a non-empty array")
        files = []
    for index, item in enumerate(files):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append(f"files[{index}] is invalid")
            continue
        recorded[item["path"]] = str(item.get("sha256", ""))
        try:
            path = _safe_path(project, item["path"])
        except ResearchQualityError as exc:
            errors.append(f"files[{index}]: {exc}")
            continue
        if not path.is_file() or item.get("sha256") != sha256_file(path):
            errors.append(f"files[{index}] is missing or changed after preregistration")
    expected = {path.relative_to(project).as_posix() for path in _preregistration_inputs(project, paper_id)}
    missing = sorted(expected - set(recorded))
    if missing:
        errors.append("preregistration omits required files: " + ", ".join(missing))
    return errors


def _successful_runs(registry: list[dict[str, Any]], paper_id: str) -> set[str]:
    return {
        str(item.get("run_id"))
        for item in registry
        if item.get("status") == "succeeded" and item.get("paper_id") == paper_id
    }


def _planned_reproduction(
    project: Path, paper_id: str
) -> tuple[dict[str, set[str]], dict[str, float], dict[str, dict[str, str]], list[str]]:
    """Read the G3-frozen reproduction roles, tolerances and baseline sources."""

    roles = {
        "domain_standard": set(),
        "strong_recent": set(),
        "original": set(),
        "clean_room": set(),
    }
    tolerances: dict[str, float] = {}
    baselines: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    paths = _design_paths(project, paper_id)
    if not paths:
        return roles, tolerances, baselines, ["no G3 experiment design is available"]
    for path in paths:
        relative = path.relative_to(project).as_posix()
        try:
            design = _load_json(path)
        except ResearchQualityError as exc:
            errors.append(str(exc))
            continue
        for item in design.get("baselines", []) if isinstance(design.get("baselines"), list) else []:
            if not isinstance(item, dict):
                continue
            baseline_id = item.get("id")
            category = item.get("class")
            source = item.get("primary_source_url")
            if (
                isinstance(baseline_id, str)
                and baseline_id.strip()
                and category in {"domain_standard", "strong_recent"}
                and isinstance(source, str)
            ):
                existing = baselines.get(baseline_id)
                value = {"class": str(category), "primary_source_url": source}
                if existing is not None and existing != value:
                    errors.append(f"{relative} conflicts on baseline ID {baseline_id}")
                baselines[baseline_id] = value
        reproduction = design.get("reproduction_plan")
        if not isinstance(reproduction, dict):
            errors.append(f"{relative} has no reproduction_plan")
            continue
        baseline_runs = reproduction.get("baseline_runs")
        if not isinstance(baseline_runs, dict):
            errors.append(f"{relative} has no reproduction_plan.baseline_runs")
            baseline_runs = {}
        mappings = (
            ("domain_standard", baseline_runs.get("domain_standard")),
            ("strong_recent", baseline_runs.get("strong_recent")),
            ("original", reproduction.get("original_run_ids")),
            ("clean_room", reproduction.get("clean_room_run_ids")),
        )
        for role, values in mappings:
            if not isinstance(values, list) or not values or any(
                not isinstance(item, str) or not item.strip() for item in values
            ):
                errors.append(f"{relative} has invalid planned {role} run IDs")
                continue
            roles[role].update(item.strip() for item in values)
        values = reproduction.get("metric_tolerances")
        if not isinstance(values, list) or not values:
            errors.append(f"{relative} has no predeclared metric tolerances")
            continue
        for index, item in enumerate(values):
            if not isinstance(item, dict):
                errors.append(f"{relative} metric_tolerances[{index}] is invalid")
                continue
            metric = item.get("metric")
            tolerance = item.get("absolute_tolerance")
            if (
                not isinstance(metric, str)
                or not metric.strip()
                or not isinstance(tolerance, (int, float))
                or isinstance(tolerance, bool)
                or tolerance < 0
            ):
                errors.append(f"{relative} metric_tolerances[{index}] is invalid")
                continue
            metric = metric.strip()
            numeric = float(tolerance)
            if metric in tolerances and not math.isclose(
                tolerances[metric], numeric, rel_tol=0.0, abs_tol=1e-12
            ):
                errors.append(f"{relative} conflicts on the predeclared tolerance for {metric}")
            tolerances[metric] = numeric
    for role, run_ids in roles.items():
        if not run_ids:
            errors.append(f"G3 reproduction plan has no {role} run IDs")
    return roles, tolerances, baselines, errors


def _selected_attempts(
    registry: list[dict[str, Any]],
    paper_id: str,
    run_ids: set[str],
    attempt_values: Any,
    field: str,
    errors: list[str],
) -> list[dict[str, Any]]:
    attempt_ids = _string_list(attempt_values, field, errors)
    by_attempt = {
        str(item.get("attempt_id")): item
        for item in registry
        if item.get("attempt_id")
    }
    selected: list[dict[str, Any]] = []
    for attempt_id in attempt_ids:
        entry = by_attempt.get(attempt_id)
        if entry is None:
            errors.append(f"{field} references an unknown attempt: {attempt_id}")
            continue
        if entry.get("status") != "succeeded" or entry.get("paper_id") != paper_id:
            errors.append(f"{field} attempt did not succeed for {paper_id}: {attempt_id}")
            continue
        if str(entry.get("run_id")) not in run_ids:
            errors.append(f"{field} attempt is not one of the declared run IDs: {attempt_id}")
            continue
        selected.append(entry)
    represented = {str(item.get("run_id")) for item in selected}
    if represented != run_ids:
        missing = sorted(run_ids - represented)
        extra = sorted(represented - run_ids)
        if missing:
            errors.append(f"{field} omits successful attempts for run IDs: {', '.join(missing)}")
        if extra:
            errors.append(f"{field} includes attempts for undeclared run IDs: {', '.join(extra)}")
    return selected


def _attempt_output_pairs(
    project: Path, entries: list[dict[str, Any]], field: str, errors: list[str]
) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for entry in entries:
        attempt_id = str(entry.get("attempt_id"))
        outputs = entry.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            errors.append(f"{field} attempt has no outputs: {attempt_id}")
            continue
        for output in outputs:
            if not isinstance(output, dict) or not isinstance(output.get("path"), str):
                errors.append(f"{field} attempt has malformed output evidence: {attempt_id}")
                continue
            try:
                path = _safe_path(project, output["path"])
            except ResearchQualityError as exc:
                errors.append(f"{field} attempt {attempt_id}: {exc}")
                continue
            digest = output.get("sha256")
            if not path.is_file() or digest != sha256_file(path):
                errors.append(f"{field} attempt output is missing or stale: {attempt_id}/{output['path']}")
                continue
            pairs.add((output["path"], str(digest)))
    return pairs


def _validate_evidence_files(
    project: Path,
    values: Any,
    field: str,
    errors: list[str],
    *,
    expected_pairs: set[tuple[str, str]] | None = None,
) -> set[tuple[str, str]]:
    recorded: set[tuple[str, str]] = set()
    if not isinstance(values, list) or not values:
        errors.append(f"{field} must be a non-empty array")
        return recorded
    for index, item in enumerate(values):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append(f"{field}[{index}] must contain path and sha256")
            continue
        try:
            path = _safe_path(project, item["path"])
        except ResearchQualityError as exc:
            errors.append(f"{field}[{index}]: {exc}")
            continue
        if not path.is_file() or item.get("sha256") != sha256_file(path):
            errors.append(f"{field}[{index}] is missing or hash-mismatched")
        else:
            recorded.add((item["path"], str(item.get("sha256"))))
    if expected_pairs is not None and recorded != expected_pairs:
        missing = sorted(path for path, _digest in expected_pairs - recorded)
        extra = sorted(path for path, _digest in recorded - expected_pairs)
        if missing:
            errors.append(f"{field} omits selected-attempt outputs: {', '.join(missing)}")
        if extra:
            errors.append(f"{field} includes files not produced by selected attempts: {', '.join(extra)}")
    return recorded


def validate_baseline_reproduction(
    report: dict[str, Any], paper_id: str, project: Path, registry: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != "1.0" or report.get("paper_id") != paper_id:
        errors.append("baseline report schema/paper does not match")
    if report.get("status") != "pass" or report.get("human_review_required") is not True:
        errors.append("baseline report must pass and require human review")
    successful = _successful_runs(registry, paper_id)
    planned, tolerances, baseline_specs, plan_errors = _planned_reproduction(project, paper_id)
    errors.extend(plan_errors)
    entries = report.get("baselines")
    if not isinstance(entries, list) or len(entries) < 2:
        errors.append("baselines must contain domain_standard and strong_recent entries")
        entries = []
    classes: set[str] = set()
    reported_runs = {"domain_standard": set(), "strong_recent": set()}
    for index, entry in enumerate(entries):
        prefix = f"baselines[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        category = entry.get("class")
        if category in {"domain_standard", "strong_recent"}:
            classes.add(str(category))
        else:
            errors.append(f"{prefix}.class must be domain_standard or strong_recent")
        for key in ("baseline_id", "metric", "reference_source_url", "comparison_notes"):
            _text(entry.get(key), f"{prefix}.{key}", errors)
        baseline_id = entry.get("baseline_id")
        if isinstance(baseline_id, str):
            expected_spec = baseline_specs.get(baseline_id)
            if expected_spec is None:
                errors.append(f"{prefix}.baseline_id was not declared at G3")
            else:
                if expected_spec["class"] != category:
                    errors.append(f"{prefix}.class differs from the G3 baseline declaration")
                if expected_spec["primary_source_url"] != entry.get("reference_source_url"):
                    errors.append(f"{prefix}.reference_source_url differs from the G3 source")
        if not str(entry.get("reference_source_url", "")).startswith("https://"):
            errors.append(f"{prefix}.reference_source_url must use HTTPS")
        for key in ("reference_value", "observed_value", "absolute_tolerance"):
            value = entry.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{prefix}.{key} must be numeric")
        if entry.get("comparable_protocol") is not True or entry.get("within_tolerance") is not True:
            errors.append(f"{prefix} must use a comparable protocol and reproduce within tolerance")
        reference = entry.get("reference_value")
        observed = entry.get("observed_value")
        tolerance = entry.get("absolute_tolerance")
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (reference, observed, tolerance)):
            if tolerance < 0 or abs(float(reference) - float(observed)) > float(tolerance):
                errors.append(f"{prefix} numeric values exceed the declared absolute tolerance")
        metric = entry.get("metric")
        if isinstance(metric, str) and metric in tolerances and isinstance(tolerance, (int, float)):
            if not math.isclose(float(tolerance), tolerances[metric], rel_tol=0.0, abs_tol=1e-12):
                errors.append(f"{prefix}.absolute_tolerance differs from the G3 preregistration")
        elif isinstance(metric, str):
            errors.append(f"{prefix}.metric has no G3-predeclared tolerance")
        run_ids = _string_list(entry.get("run_ids"), f"{prefix}.run_ids", errors)
        missing = sorted(set(run_ids) - successful)
        if missing:
            errors.append(f"{prefix} references runs that did not succeed for {paper_id}: {', '.join(missing)}")
        if category in reported_runs:
            reported_runs[str(category)].update(run_ids)
        selected = _selected_attempts(
            registry,
            paper_id,
            set(run_ids),
            entry.get("attempt_ids"),
            f"{prefix}.attempt_ids",
            errors,
        )
        expected_evidence = _attempt_output_pairs(
            project, selected, f"{prefix}.attempt_ids", errors
        )
        _validate_evidence_files(
            project,
            entry.get("evidence_files"),
            f"{prefix}.evidence_files",
            errors,
            expected_pairs=expected_evidence,
        )
    if not {"domain_standard", "strong_recent"}.issubset(classes):
        errors.append("baseline reproduction must cover domain_standard and strong_recent")
    for category in ("domain_standard", "strong_recent"):
        if reported_runs[category] != planned[category]:
            errors.append(f"reported {category} run IDs differ from the G3 reproduction plan")
    return errors


def validate_clean_room_reproduction(
    report: dict[str, Any], paper_id: str, project: Path, registry: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != "1.0" or report.get("paper_id") != paper_id:
        errors.append("clean-room report schema/paper does not match")
    if report.get("status") != "pass" or report.get("human_review_required") is not True:
        errors.append("clean-room report must pass and require human review")
    _text(report.get("independent_operator"), "independent_operator", errors)
    successful = _successful_runs(registry, paper_id)
    planned, tolerances, _baseline_specs, plan_errors = _planned_reproduction(project, paper_id)
    errors.extend(plan_errors)
    original = set(_string_list(report.get("original_run_ids"), "original_run_ids", errors))
    reproduction = set(_string_list(report.get("reproduction_run_ids"), "reproduction_run_ids", errors))
    if original & reproduction:
        errors.append("original and reproduction run IDs must be disjoint")
    missing = sorted((original | reproduction) - successful)
    if missing:
        errors.append("clean-room report references unsuccessful/unknown runs: " + ", ".join(missing))
    if original != planned["original"]:
        errors.append("original_run_ids differ from the G3 reproduction plan")
    if reproduction != planned["clean_room"]:
        errors.append("reproduction_run_ids differ from the G3 reproduction plan")
    original_entries = _selected_attempts(
        registry,
        paper_id,
        original,
        report.get("original_attempt_ids"),
        "original_attempt_ids",
        errors,
    )
    reproduction_entries = _selected_attempts(
        registry,
        paper_id,
        reproduction,
        report.get("reproduction_attempt_ids"),
        "reproduction_attempt_ids",
        errors,
    )
    original_cwds = {str(item.get("cwd")) for item in original_entries}
    reproduction_cwds = {str(item.get("cwd")) for item in reproduction_entries}
    if original_cwds & reproduction_cwds:
        errors.append("original and reproduction attempts must use different recorded cwd/checkouts")
    isolation = report.get("isolation")
    if not isinstance(isolation, dict):
        errors.append("isolation must be an object")
    else:
        if isolation.get("separate_checkout") is not True:
            errors.append("isolation.separate_checkout must be true")
        original_digest = _text(isolation.get("original_environment_digest"), "isolation.original_environment_digest", errors)
        reproduction_digest = _text(isolation.get("reproduction_environment_digest"), "isolation.reproduction_environment_digest", errors)
        if original_digest and original_digest == reproduction_digest:
            errors.append("clean-room environments must have distinct recorded digests")
        original_attempts = {str(item.get("attempt_id")) for item in original_entries}
        reproduction_attempts = {str(item.get("attempt_id")) for item in reproduction_entries}
        if original_attempts:
            expected_original = registry_environment_digest(registry, original_attempts)
            if original_digest != expected_original:
                errors.append("original_environment_digest does not match the registry")
        if reproduction_attempts:
            expected_reproduction = registry_environment_digest(registry, reproduction_attempts)
            if reproduction_digest != expected_reproduction:
                errors.append("reproduction_environment_digest does not match the registry")
        source_commit = _text(isolation.get("source_commit"), "isolation.source_commit", errors)
        selected_commits = {
            str(item.get("git_commit"))
            for item in registry
            if str(item.get("attempt_id")) in original_attempts | reproduction_attempts
        }
        if source_commit and selected_commits != {source_commit}:
            errors.append("isolation.source_commit must match every selected registry run")
    comparisons = report.get("metric_comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        errors.append("metric_comparisons must be non-empty")
        comparisons = []
    for index, item in enumerate(comparisons):
        prefix = f"metric_comparisons[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _text(item.get("metric"), f"{prefix}.metric", errors)
        for key in ("original_value", "reproduction_value", "absolute_tolerance"):
            value = item.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{prefix}.{key} must be numeric")
        if item.get("within_tolerance") is not True:
            errors.append(f"{prefix}.within_tolerance must be true")
        original_value = item.get("original_value")
        reproduction_value = item.get("reproduction_value")
        tolerance = item.get("absolute_tolerance")
        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (original_value, reproduction_value, tolerance)):
            if tolerance < 0 or abs(float(original_value) - float(reproduction_value)) > float(tolerance):
                errors.append(f"{prefix} numeric values exceed the declared absolute tolerance")
        metric = item.get("metric")
        if isinstance(metric, str) and metric in tolerances and isinstance(tolerance, (int, float)):
            if not math.isclose(float(tolerance), tolerances[metric], rel_tol=0.0, abs_tol=1e-12):
                errors.append(f"{prefix}.absolute_tolerance differs from the G3 preregistration")
        elif isinstance(metric, str):
            errors.append(f"{prefix}.metric has no G3-predeclared tolerance")
    comparison_metrics = {
        str(item.get("metric")) for item in comparisons if isinstance(item, dict) and item.get("metric")
    }
    if comparison_metrics != set(tolerances):
        errors.append("metric_comparisons must cover exactly the G3-predeclared tolerances")
    expected_evidence = _attempt_output_pairs(
        project,
        [*original_entries, *reproduction_entries],
        "clean-room attempts",
        errors,
    )
    _validate_evidence_files(
        project,
        report.get("evidence_files"),
        "evidence_files",
        errors,
        expected_pairs=expected_evidence,
    )
    return errors


def create_reproduction_confirmation(project: Path, paper_id: str, actor: str) -> dict[str, Any]:
    if not actor.strip():
        raise ResearchQualityError("actor is required")
    registry = _registry(project)
    baseline_path = project / "papers" / paper_id / "baseline-reproduction.json"
    clean_path = project / "papers" / paper_id / "clean-room-reproduction.json"
    baseline = _load_json(baseline_path)
    clean = _load_json(clean_path)
    preregistration = _load_json(project / "papers" / paper_id / "preregistration.json")
    errors = validate_preregistration(preregistration, paper_id, project)
    errors.extend(validate_baseline_reproduction(baseline, paper_id, project, registry))
    errors.extend(validate_clean_room_reproduction(clean, paper_id, project, registry))
    if errors:
        raise ResearchQualityError("cannot confirm invalid reproduction evidence: " + "; ".join(errors))
    return {
        "schema_version": "1.0",
        "paper_id": paper_id,
        "generated_by": "deterministic_local_control_plane",
        "confirmed_by": actor.strip(),
        "confirmed_at": utc_now(),
        "baseline_report_sha256": sha256_file(baseline_path),
        "clean_room_report_sha256": sha256_file(clean_path),
        "statement": (
            "I reviewed the named runs, numeric tolerances, current evidence files, "
            "separate-checkout record and independent-operator identity."
        ),
    }


def validate_reproduction_confirmation(
    confirmation: dict[str, Any], paper_id: str, project: Path
) -> list[str]:
    errors: list[str] = []
    if confirmation.get("schema_version") != "1.0" or confirmation.get("paper_id") != paper_id:
        errors.append("reproduction confirmation schema/paper does not match")
    if confirmation.get("generated_by") != "deterministic_local_control_plane":
        errors.append("reproduction confirmation must be generated locally")
    _text(confirmation.get("confirmed_by"), "confirmed_by", errors)
    _text(confirmation.get("confirmed_at"), "confirmed_at", errors)
    _text(confirmation.get("statement"), "statement", errors)
    expected = {
        "baseline_report_sha256": project / "papers" / paper_id / "baseline-reproduction.json",
        "clean_room_report_sha256": project / "papers" / paper_id / "clean-room-reproduction.json",
    }
    for field, path in expected.items():
        if not path.is_file() or confirmation.get(field) != sha256_file(path):
            errors.append(f"{field} is missing or stale")
    return errors


def registry_environment_digest(
    registry: list[dict[str, Any]], attempt_ids: Iterable[str]
) -> str:
    """Hash unique environments for exact successful attempt IDs.

    Run and attempt identifiers are deliberately excluded from the payload:
    differently named attempts in the same checkout/runtime must have the same
    digest, rather than masquerading as isolated reproductions.
    """

    selected = set(attempt_ids)
    unique: dict[str, dict[str, Any]] = {}
    for item in registry:
        if item.get("status") != "succeeded" or str(item.get("attempt_id")) not in selected:
            continue
        record = {
            "git_commit": item.get("git_commit"),
            "cwd": item.get("cwd"),
            "runtime": item.get("runtime"),
        }
        key = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        unique[key] = record
    records = [unique[key] for key in sorted(unique)]
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def refresh_runtime_evidence_catalog(project: Path) -> Path:
    """Materialize verified G4 run facts so writers need not invent hashes."""

    registry = _registry(project)
    runs: list[dict[str, Any]] = []
    for item in registry:
        if item.get("status") != "succeeded" or not item.get("run_id"):
            continue
        outputs: list[dict[str, Any]] = []
        for output in item.get("outputs", []) if isinstance(item.get("outputs"), list) else []:
            if not isinstance(output, dict) or not isinstance(output.get("path"), str):
                continue
            try:
                path = _safe_path(project, output["path"])
            except ResearchQualityError:
                current = False
            else:
                current = path.is_file() and output.get("sha256") == sha256_file(path)
            outputs.append({
                "path": output["path"],
                "sha256": output.get("sha256"),
                "current_hash_match": current,
            })
        run_id = str(item["run_id"])
        runs.append({
            "run_id": run_id,
            "attempt_id": item.get("attempt_id"),
            "paper_id": item.get("paper_id"),
            "git_commit": item.get("git_commit"),
            "cwd": item.get("cwd"),
            "runtime": item.get("runtime"),
            "single_attempt_environment_digest": registry_environment_digest(
                registry, [str(item.get("attempt_id"))]
            ),
            "outputs": outputs,
        })
    catalog = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "generated_by": "deterministic_local_control_plane",
        "note": "Use exact successful attempt_id values and only current_hash_match=true outputs. Multi-attempt environment digests must be computed with the local environment-digest command.",
        "runs": runs,
    }
    path = project / "reports" / "runtime-evidence-catalog.json"
    _atomic_json(path, catalog)
    return path


def validate_g3_quality(project: Path) -> list[str]:
    errors: list[str] = []
    manifests = _manifest_map(project)
    for dataset_id in sorted(manifests):
        path = project / "data" / "quality" / f"{dataset_id}.json"
        if not path.is_file():
            errors.append(f"missing data-quality report: data/quality/{dataset_id}.json")
            continue
        try:
            report = _load_json(path)
        except ResearchQualityError as exc:
            errors.append(str(exc))
            continue
        errors.extend(
            f"data/quality/{dataset_id}.json: {issue}"
            for issue in validate_data_quality_report(report, dataset_id, project)
        )
        confirmation_path = project / "data" / "quality" / f"{dataset_id}-confirmation.json"
        if not confirmation_path.is_file():
            errors.append(f"missing named confirmation: data/quality/{dataset_id}-confirmation.json")
        else:
            try:
                confirmation = _load_json(confirmation_path)
            except ResearchQualityError as exc:
                errors.append(str(exc))
            else:
                errors.extend(
                    f"data/quality/{dataset_id}-confirmation.json: {issue}"
                    for issue in validate_data_quality_confirmation(
                        confirmation, dataset_id, project
                    )
                )
    for paper_id in _paper_ids(project):
        power_path = project / "papers" / paper_id / "power-analysis.json"
        prereg_path = project / "papers" / paper_id / "preregistration.json"
        if not power_path.is_file():
            errors.append(f"{paper_id} is missing power-analysis.json")
        else:
            try:
                report = _load_json(power_path)
                errors.extend(
                    f"{paper_id}/power-analysis.json: {issue}"
                    for issue in validate_power_report(report, paper_id, project)
                )
            except ResearchQualityError as exc:
                errors.append(str(exc))
        if not prereg_path.is_file():
            errors.append(f"{paper_id} is missing preregistration.json")
        else:
            try:
                report = _load_json(prereg_path)
                errors.extend(
                    f"{paper_id}/preregistration.json: {issue}"
                    for issue in validate_preregistration(report, paper_id, project)
                )
            except ResearchQualityError as exc:
                errors.append(str(exc))
    return errors


def validate_g4_quality(project: Path) -> list[str]:
    errors: list[str] = []
    registry = _registry(project)
    for paper_id in _paper_ids(project):
        prereg_path = project / "papers" / paper_id / "preregistration.json"
        if prereg_path.is_file():
            try:
                errors.extend(
                    f"{paper_id}/preregistration.json: {issue}"
                    for issue in validate_preregistration(_load_json(prereg_path), paper_id, project)
                )
            except ResearchQualityError as exc:
                errors.append(str(exc))
        else:
            errors.append(f"{paper_id} is missing preregistration.json")
        baseline_path = project / "papers" / paper_id / "baseline-reproduction.json"
        clean_path = project / "papers" / paper_id / "clean-room-reproduction.json"
        if not baseline_path.is_file():
            errors.append(f"{paper_id} is missing baseline-reproduction.json")
        else:
            try:
                errors.extend(
                    f"{paper_id}/baseline-reproduction.json: {issue}"
                    for issue in validate_baseline_reproduction(
                        _load_json(baseline_path), paper_id, project, registry
                    )
                )
            except ResearchQualityError as exc:
                errors.append(str(exc))
        if not clean_path.is_file():
            errors.append(f"{paper_id} is missing clean-room-reproduction.json")
        else:
            try:
                errors.extend(
                    f"{paper_id}/clean-room-reproduction.json: {issue}"
                    for issue in validate_clean_room_reproduction(
                        _load_json(clean_path), paper_id, project, registry
                    )
                )
            except ResearchQualityError as exc:
                errors.append(str(exc))
        confirmation_path = project / "papers" / paper_id / "reproduction-confirmation.json"
        if not confirmation_path.is_file():
            errors.append(f"{paper_id} is missing reproduction-confirmation.json")
        else:
            try:
                errors.extend(
                    f"{paper_id}/reproduction-confirmation.json: {issue}"
                    for issue in validate_reproduction_confirmation(
                        _load_json(confirmation_path), paper_id, project
                    )
                )
            except ResearchQualityError as exc:
                errors.append(str(exc))
    return errors


def quality_summary(project: Path) -> dict[str, Any]:
    manifests = _manifest_map(project)
    papers = _paper_ids(project)
    count = lambda paths: sum(1 for path in paths if path.is_file())
    novelty = project / "program" / "novelty-claim-matrix.json"
    return {
        "novelty_claim_matrix": novelty.is_file(),
        "data_quality_reports": count(project / "data" / "quality" / f"{item}.json" for item in manifests),
        "data_quality_confirmations": count(
            project / "data" / "quality" / f"{item}-confirmation.json" for item in manifests
        ),
        "dataset_count": len(manifests),
        "power_reports": count(project / "papers" / paper / "power-analysis.json" for paper in papers),
        "preregistrations": count(project / "papers" / paper / "preregistration.json" for paper in papers),
        "baseline_reproductions": count(project / "papers" / paper / "baseline-reproduction.json" for paper in papers),
        "clean_room_reproductions": count(project / "papers" / paper / "clean-room-reproduction.json" for paper in papers),
        "reproduction_confirmations": count(project / "papers" / paper / "reproduction-confirmation.json" for paper in papers),
        "paper_count": len(papers),
        "optional_tools": optional_tool_status(),
    }


def _cmd_data_audit(args: argparse.Namespace) -> None:
    project = _project(args.project)
    if not DATASET_RE.fullmatch(args.dataset_id):
        raise ResearchQualityError("dataset-id contains unsafe characters")
    report = create_data_quality_report(
        project,
        args.dataset_id,
        args.path,
        actor=args.actor,
        label_column=args.label_column,
        split_column=args.split_column,
        group_column=args.group_column,
        derived=args.derived,
        maximum_rows=args.max_rows,
    )
    output = project / "data" / "quality" / f"{args.dataset_id}.json"
    _atomic_json(output, report)
    print(json.dumps({"report": output.relative_to(project).as_posix(), "status": report["status"], "blockers": report["blockers"], "warnings": report["warnings"]}, ensure_ascii=False, indent=2))
    if report["status"] != "pass":
        raise ResearchQualityError("data-quality audit recorded blockers")


def _cmd_confirm_data_quality(args: argparse.Namespace) -> None:
    project = _project(args.project)
    if not DATASET_RE.fullmatch(args.dataset_id):
        raise ResearchQualityError("dataset-id contains unsafe characters")
    confirmation = create_data_quality_confirmation(
        project, args.dataset_id, args.actor
    )
    output = project / "data" / "quality" / f"{args.dataset_id}-confirmation.json"
    _atomic_json(output, confirmation)
    print(output.relative_to(project).as_posix())


def _cmd_power(args: argparse.Namespace) -> None:
    project = _project(args.project)
    report = create_power_report(
        project, args.paper, args.method, args.effect_size, args.alpha, args.power,
        args.ratio, args.effect_size_basis, args.groups
    )
    output = project / "papers" / args.paper / "power-analysis.json"
    _atomic_json(output, report)
    print(json.dumps({"report": output.relative_to(project).as_posix(), "required_sample_size": report["required_sample_size"]}, indent=2))


def _cmd_simulation_power(args: argparse.Namespace) -> None:
    project = _project(args.project)
    report = create_simulation_power_report(
        project,
        args.paper,
        args.effect_size,
        args.alpha,
        args.power,
        args.simulation_count,
        args.achieved_power,
        args.script,
        args.evidence,
        args.method_note,
        args.effect_size_basis,
    )
    output = project / "papers" / args.paper / "power-analysis.json"
    _atomic_json(output, report)
    print(json.dumps({"report": output.relative_to(project).as_posix(), "simulation_count": report["simulation_count"], "achieved_power": report["achieved_power"]}, indent=2))


def _cmd_freeze(args: argparse.Namespace) -> None:
    project = _project(args.project)
    papers = _paper_ids(project) if args.all else [args.paper]
    if not papers or any(not paper or not PAPER_RE.fullmatch(paper) for paper in papers):
        raise ResearchQualityError("select --all or an existing --paper such as P01")
    prepared: list[tuple[Path, dict[str, Any]]] = []
    for paper in papers:
        if not (project / "papers" / paper).is_dir():
            raise ResearchQualityError(f"paper does not exist: {paper}")
        prepared.append((
            project / "papers" / paper / "preregistration.json",
            create_preregistration(project, paper, args.actor),
        ))
    for path, report in prepared:
        _atomic_json(path, report)
        print(f"frozen {path.relative_to(project)}")


def _cmd_validate(args: argparse.Namespace) -> None:
    project = _project(args.project)
    stage = args.stage
    if stage == "auto":
        try:
            state = _load_json(project / "state" / "run.json")
            gate = state.get("gate")
        except ResearchQualityError:
            gate = None
        stage = "g4" if gate in {"G4", "G5", None} else "g3"
    errors = validate_g4_quality(project) if stage == "g4" else validate_g3_quality(project)
    print(json.dumps({"stage": stage, "status": "pass" if not errors else "block", "errors": errors, "summary": quality_summary(project)}, ensure_ascii=False, indent=2))
    if errors:
        raise ResearchQualityError(f"{len(errors)} research-quality requirement(s) remain")


def _cmd_environment_digest(args: argparse.Namespace) -> None:
    project = _project(args.project)
    registry = _registry(project)
    successful = {str(item.get("attempt_id")) for item in registry if item.get("status") == "succeeded"}
    unknown = sorted(set(args.attempt) - successful)
    if unknown:
        raise ResearchQualityError("attempts are not successful registry entries: " + ", ".join(unknown))
    print(registry_environment_digest(registry, args.attempt))


def _cmd_runtime_catalog(args: argparse.Namespace) -> None:
    project = _project(args.project)
    path = refresh_runtime_evidence_catalog(project)
    print(path.relative_to(project).as_posix())


def _cmd_confirm_reproduction(args: argparse.Namespace) -> None:
    project = _project(args.project)
    if not PAPER_RE.fullmatch(args.paper) or not (project / "papers" / args.paper).is_dir():
        raise ResearchQualityError("paper must be an existing ID such as P01")
    report = create_reproduction_confirmation(project, args.paper, args.actor)
    path = project / "papers" / args.paper / "reproduction-confirmation.json"
    _atomic_json(path, report)
    print(path.relative_to(project).as_posix())


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("data-audit", help="Create a local hash-bound data-quality report")
    audit.add_argument("--project", required=True)
    audit.add_argument("--dataset-id", required=True)
    audit.add_argument("--path", required=True)
    audit.add_argument("--actor", required=True)
    audit.add_argument("--label-column")
    audit.add_argument("--split-column")
    audit.add_argument("--group-column")
    audit.add_argument("--derived", action="store_true")
    audit.add_argument("--max-rows", type=int, default=1_000_000)
    audit.set_defaults(func=_cmd_data_audit)

    confirm_data = sub.add_parser(
        "confirm-data-quality",
        help="Create a named hash-bound confirmation after reviewing a local data audit",
    )
    confirm_data.add_argument("--project", required=True)
    confirm_data.add_argument("--dataset-id", required=True)
    confirm_data.add_argument("--actor", required=True)
    confirm_data.set_defaults(func=_cmd_confirm_data_quality)

    power = sub.add_parser("power", help="Calculate and bind a statsmodels power report")
    power.add_argument("--project", required=True)
    power.add_argument("--paper", required=True)
    power.add_argument("--method", required=True, choices=["ttest_ind", "ttest_paired", "ttest_one_sample", "anova", "proportion_ind"])
    power.add_argument("--effect-size", type=float, required=True)
    power.add_argument("--alpha", type=float, default=0.05)
    power.add_argument("--power", type=float, default=0.8)
    power.add_argument("--ratio", type=float, default=1.0)
    power.add_argument("--groups", type=int, default=2)
    power.add_argument("--effect-size-basis", required=True)
    power.set_defaults(func=_cmd_power)

    simulation = sub.add_parser("simulation-power", help="Bind a Monte Carlo power analysis to real local evidence")
    simulation.add_argument("--project", required=True)
    simulation.add_argument("--paper", required=True)
    simulation.add_argument("--effect-size", type=float, required=True)
    simulation.add_argument("--alpha", type=float, default=0.05)
    simulation.add_argument("--power", type=float, default=0.8)
    simulation.add_argument("--simulation-count", type=int, required=True)
    simulation.add_argument("--achieved-power", type=float, required=True)
    simulation.add_argument("--script", required=True)
    simulation.add_argument("--evidence", required=True)
    simulation.add_argument("--method-note", required=True)
    simulation.add_argument("--effect-size-basis", required=True)
    simulation.set_defaults(func=_cmd_simulation_power)

    freeze = sub.add_parser("freeze", help="Freeze hash-bound G3 preregistrations")
    freeze.add_argument("--project", required=True)
    choice = freeze.add_mutually_exclusive_group(required=True)
    choice.add_argument("--paper")
    choice.add_argument("--all", action="store_true")
    freeze.add_argument("--actor", required=True)
    freeze.set_defaults(func=_cmd_freeze)

    validate = sub.add_parser("validate", help="Validate evidence-bound quality reports")
    validate.add_argument("--project", required=True)
    validate.add_argument("--stage", choices=["auto", "g3", "g4"], default="auto")
    validate.set_defaults(func=_cmd_validate)
    digest = sub.add_parser("environment-digest", help="Hash executor-recorded environments for exact successful attempts")
    digest.add_argument("--project", required=True)
    digest.add_argument("--attempt", action="append", required=True)
    digest.set_defaults(func=_cmd_environment_digest)
    catalog = sub.add_parser("runtime-catalog", help="Refresh verified G4 registry evidence")
    catalog.add_argument("--project", required=True)
    catalog.set_defaults(func=_cmd_runtime_catalog)
    confirm = sub.add_parser("confirm-reproduction", help="Bind named human review to G4 reproduction reports")
    confirm.add_argument("--project", required=True)
    confirm.add_argument("--paper", required=True)
    confirm.add_argument("--actor", required=True)
    confirm.set_defaults(func=_cmd_confirm_reproduction)
    return root


def main(argv: Iterable[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        if getattr(args, "max_rows", 1) <= 0:
            raise ResearchQualityError("--max-rows must be positive")
        args.func(args)
        return 0
    except (ResearchQualityError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
