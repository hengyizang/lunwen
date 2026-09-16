#!/usr/bin/env python3
"""Automatically derive dataset queries, search approved sources and shortlist metadata."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    from scripts import data_discovery
    from scripts.network_safety import fetch_json
except ModuleNotFoundError:  # Direct execution from scripts/.
    import data_discovery  # type: ignore[no-redef]
    from network_safety import fetch_json  # type: ignore[no-redef]


AUTO_STAGES = {"topic-intelligence", "experiment-design"}
MAX_QUERY_LENGTH = 240
STOP_WORDS = {
    "about", "after", "against", "also", "among", "and", "are", "based",
    "before", "between", "build", "candidate", "complete", "data", "dataset",
    "datasets", "doctoral", "each", "every", "for", "from", "have", "into",
    "must", "only", "paper", "papers", "project", "public", "research", "should",
    "study", "that", "the", "their", "these", "this", "through", "using", "with",
}
DATA_WORDS = {"benchmark", "corpus", "data", "dataset", "datasets", "repository"}


class AutomaticDataDiscoveryError(RuntimeError):
    pass


def _load_json(path: Path) -> Any | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _strings(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    return []


def _keyword_phrase(value: str, maximum_words: int = 10) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{1,}", value)
    selected: list[str] = []
    seen: set[str] = set()
    for word in words:
        lowered = word.lower()
        if lowered in STOP_WORDS or lowered in seen:
            continue
        seen.add(lowered)
        selected.append(word)
        if len(selected) >= maximum_words:
            break
    if selected:
        return " ".join(selected)
    compact = re.sub(r"\s+", " ", value).strip()
    return compact[:MAX_QUERY_LENGTH] if len(compact) >= 4 else ""


def _project_material(project_root: Path, stage: str) -> list[str]:
    material: list[str] = []
    paper_material: list[str] = []
    intake = _load_json(project_root / "intake" / "constraints.json")
    if isinstance(intake, dict):
        for field in ("research_goal", "preferred_domains", "data_constraint"):
            material.extend(_strings(intake.get(field)))

    for relative in (
        "program/core-thesis.json",
        "program/extension-thesis.json",
        "program/topic-shortlist.json",
    ):
        value = _load_json(project_root / relative)
        if value is not None:
            material.extend(_strings(value)[:12])

    if stage == "experiment-design":
        for path in sorted((project_root / "papers").glob("P[0-9][0-9]/paper-contract.json")):
            contract = _load_json(path)
            if not isinstance(contract, dict):
                continue
            combined: list[str] = []
            for field in ("working_title", "research_question", "hypotheses", "datasets"):
                combined.extend(_strings(contract.get(field)))
            if combined:
                paper_material.append(" ".join(combined[:4]))
    return [*paper_material, *material]


def derive_queries(
    project_root: Path,
    stage: str,
    context: str = "",
    explicit_query: str = "",
    *,
    max_queries: int = 8,
) -> list[str]:
    """Derive bounded, English-friendly query variants without another model call."""

    if stage not in AUTO_STAGES:
        return []
    if not 1 <= max_queries <= 12:
        raise AutomaticDataDiscoveryError("max_queries must be between 1 and 12")

    queries: list[str] = []

    def add(value: str, *, add_dataset_suffix: bool = True) -> None:
        value = re.sub(r"\s+", " ", value).strip(" ,;:|")[:MAX_QUERY_LENGTH]
        if not value:
            return
        words = {word.lower() for word in re.findall(r"[A-Za-z]+", value)}
        if add_dataset_suffix and not words.intersection(DATA_WORDS):
            value = f"{value} dataset"[:MAX_QUERY_LENGTH]
        key = value.casefold()
        if key not in {item.casefold() for item in queries} and len(queries) < max_queries:
            queries.append(value)

    for item in re.split(r"[\n;|]+", explicit_query):
        add(item, add_dataset_suffix=False)

    material = _project_material(project_root, stage)
    if context.strip():
        material.append(context)
    anchors: list[str] = []
    for item in material:
        phrase = _keyword_phrase(item)
        if phrase and phrase.casefold() not in {value.casefold() for value in anchors}:
            anchors.append(phrase)

    for anchor in anchors:
        add(anchor)
        if len(queries) >= max_queries:
            break

    base = next((query for query in queries if query), "")
    if base:
        base_without_suffix = re.sub(r"\s+(?:public\s+)?datasets?$", "", base, flags=re.I)
        add(f"{base_without_suffix} public dataset", add_dataset_suffix=False)
        add(f"{base_without_suffix} benchmark dataset", add_dataset_suffix=False)

    if not queries:
        fallback = (
            "industrial artificial intelligence robotics predictive maintenance public dataset"
            if stage == "topic-intelligence"
            else "industrial machine learning multivariate sensor benchmark dataset"
        )
        add(fallback, add_dataset_suffix=False)
    return queries


def _candidate_identifier(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("doi")
        or candidate.get("landing_url")
        or f"{candidate.get('provider')}:{candidate.get('provider_id')}"
    )


def apply_automatic_screening(
    report: dict[str, Any], *, minimum_metadata_score: int = 25, maximum_shortlist: int = 80
) -> dict[str, Any]:
    """Create a metadata-only shortlist while preserving every retrieved candidate."""

    candidates = report.get("candidates", [])
    shortlist: list[str] = []
    for rank, candidate in enumerate(candidates, start=1):
        score = int(candidate.get("metadata_relevance_score") or 0)
        shortlisted = score >= minimum_metadata_score and len(shortlist) < maximum_shortlist
        candidate["automatic_screening"] = {
            "rank": rank,
            "status": "metadata_shortlist" if shortlisted else "metadata_deprioritized",
            "metadata_score": score,
            "cross_source_count": len(candidate.get("also_found_by", [])),
            "persistent_identifier_present": bool(candidate.get("doi")),
            "license_metadata_present_unverified": bool(candidate.get("license_claim")),
            "version_metadata_present": bool(candidate.get("version")),
            "scientific_fitness_assessed": False,
        }
        if shortlisted:
            shortlist.append(_candidate_identifier(candidate))
    report["automatic_screening_summary"] = {
        "method": "deterministic_metadata_screening",
        "minimum_metadata_score": minimum_metadata_score,
        "maximum_shortlist": maximum_shortlist,
        "shortlist_count": len(shortlist),
        "deprioritized_count": max(0, len(candidates) - len(shortlist)),
        "shortlisted_candidate_ids": shortlist,
        "criteria": [
            "query and title/description overlap",
            "cross-source recurrence",
            "persistent identifier presence",
            "license metadata presence (unverified)",
            "version metadata presence",
        ],
        "not_automatically_decided": [
            "license permission",
            "privacy and ethics",
            "scientific fitness",
            "sample adequacy and bias",
            "leakage risk",
            "final dataset adoption",
        ],
        "human_review_required": True,
    }
    return report


def _append_search_log(project_root: Path, report: dict[str, Any], output: Path) -> None:
    path = project_root / "evidence" / "dataset-search-log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "searched_at": report["created_at"],
        "kind": "automatic_dataset_discovery",
        "query": report["query"],
        "queries": report["queries"],
        "providers": report["providers"],
        "candidate_count": report["candidate_count"],
        "shortlist_count": report["automatic_screening_summary"]["shortlist_count"],
        "report": output.relative_to(project_root).as_posix(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_automatic_discovery(
    project_root: Path,
    stage: str,
    context: str = "",
    explicit_query: str = "",
    *,
    providers: Iterable[str] = data_discovery.PROVIDERS,
    limit: int = 20,
    max_candidates: int = 500,
    fetcher: Callable[..., Any] = fetch_json,
) -> dict[str, Any]:
    queries = derive_queries(project_root, stage, context, explicit_query)
    report = data_discovery.discover_many(
        queries,
        providers,
        limit,
        max_candidates=max_candidates,
        fetcher=fetcher,
    )
    successful_calls = sum(1 for item in report["providers"] if item.get("status") == "ok")
    if successful_calls == 0:
        raise AutomaticDataDiscoveryError(
            "all approved dataset sources failed; the model cycle was stopped before paid calls"
        )
    apply_automatic_screening(report)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = project_root / "data" / f"discovery-broad-auto-{stamp}.json"
    data_discovery.save_report(report, output)
    _append_search_log(project_root, report, output)
    summary = report["automatic_screening_summary"]
    return {
        "report_path": output.relative_to(project_root).as_posix(),
        "queries": queries,
        "provider_calls": len(report["providers"]),
        "successful_provider_calls": successful_calls,
        "candidate_count": report["candidate_count"],
        "shortlist_count": summary["shortlist_count"],
        "human_review_required": True,
    }
