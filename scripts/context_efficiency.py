"""Lossless text preparation and explicit discovery navigation; no source edits."""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath


def discovery_navigation_index(relative: str, text: str, source_sha256: str) -> str | None:
    """Index every candidate in an automatic metadata receipt, without judging it.

    Large API discovery descriptions are not required full-text scientific
    evidence. Keep the original bytes/hash and give every candidate an exact
    pointer and line range for the existing explicit source-selection workflow.
    Never use this representation for a manuscript, contract or result source.
    """
    if not re.fullmatch(r"data/discovery-broad-auto-\d{8}T\d{12}Z\.json", relative):
        return None
    report = json.loads(text)
    if (not isinstance(report, dict) or report.get("schema_version") not in {"1.0", "1.1"}
            or not isinstance(report.get("automatic_screening_summary"), dict)
            or report["automatic_screening_summary"].get("method") != "deterministic_metadata_screening"):
        return None
    candidates = report.get("candidates")
    if not isinstance(candidates, list) or report.get("candidate_count") != len(candidates):
        raise ValueError("automatic discovery candidate count differs from its complete receipt")
    if not re.fullmatch(r"[a-f0-9]{64}", source_sha256):
        raise ValueError("discovery navigation requires the original source SHA-256")
    decoder = json.JSONDecoder()

    def whitespace(position):
        while position < len(text) and text[position].isspace():
            position += 1
        return position

    # Locate the actual root candidates array, ignoring similar words in data.
    cursor = whitespace(0) + 1
    while True:
        key, cursor = decoder.raw_decode(text, whitespace(cursor))
        cursor = whitespace(cursor)
        if text[cursor] != ":":
            raise ValueError("invalid discovery receipt key")
        cursor = whitespace(cursor + 1)
        if key == "candidates":
            break
        _, cursor = decoder.raw_decode(text, cursor)
        cursor = whitespace(cursor)
        if text[cursor] != ",":
            raise ValueError("discovery receipt lacks its candidate array")
        cursor += 1
    if text[cursor] != "[":
        raise ValueError("discovery candidates must be an array")
    cursor += 1
    values, lookup, rows, fields = [], {}, [], set()

    def intern(value):
        # IDs, URLs, statuses and unknowns are retained exactly, without previews.
        if value is not None and not isinstance(value, str):
            raise ValueError("discovery navigation identity/status must be text or unknown")
        if value not in lookup:
            lookup[value] = len(values)
            values.append(value)
        return lookup[value]

    for index, candidate in enumerate(candidates):
        start = whitespace(cursor)
        original, cursor = decoder.raw_decode(text, start)
        if not isinstance(candidate, dict) or original != candidate:
            raise ValueError("discovery candidate locator differs from the original receipt")
        screening = candidate.get("automatic_screening", {})
        if not isinstance(screening, dict):
            raise ValueError("discovery screening metadata must be an object")
        rows.append([index, text.count("\n", 0, start) + 1, text.count("\n", 0, cursor) + 1,
                     *[intern(v) for v in (candidate.get("provider"), candidate.get("provider_id"),
                         candidate.get("doi"), candidate.get("landing_url"), screening.get("status"),
                         candidate.get("license_status"), candidate.get("fitness_status"))]])
        fields.update(candidate)
        cursor = whitespace(cursor)
        if cursor < len(text) and text[cursor] == ",":
            cursor += 1
    payload = {
        "representation": "complete_dataset_discovery_navigation_index",
        "source": {"path": relative, "sha256": source_sha256},
        "notice": ("Metadata discovery leads only. Every candidate is indexed, including deprioritized and unknown entries. "
                   "Titles, descriptions and other candidate fields remain in the unchanged original receipt; "
                   "they have not been reviewed or judged irrelevant. Read the selected complete candidate through "
                   "program/context-plan.json source line ranges before a scientific, rights or dataset-use decision. "
                   "This index does not establish full-text reading, scientific fitness or permission."),
        "report_metadata": {key: value for key, value in report.items() if key != "candidates"},
        "candidate_count": len(rows), "omitted_candidate_count": 0,
        "pointer_template": "/candidates/{candidate_index}",
        "columns": ["candidate_index", "start_line", "end_line", "provider", "provider_id", "doi", "landing_url",
                    "screening_status", "license_status", "fitness_status"],
        "encoding": "The first three columns are literal integers; all remaining cells index value_table, including null unknowns.",
        "value_table": values, "candidate_rows": rows,
        "original_candidate_fields": sorted(fields), "scientific_completeness_verified": False,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


# Scientific sources, constraints, approvals and spending authority are retained.
# Invocation transcripts must not leak old plans/verdicts into independent review.
OPERATIONAL_PREFIXES = ("state/runs/", "state/citation-metadata/",
                        "state/review-receipts/", "state/scientific-scope/",
                        "reports/ccfa-tasks/", "reports/ccfa-science/history/", "reports/research-toolkit/",
                        "reports/research-iteration/", "reports/research-frontier/", "reports/research-search-tree/",
                        "reports/figure-panel-cache/",
                        "literature/figure-gallery/", "reports/figure-gallery/", "reports/figure-gallery-semantic/",
                        ".cache/figure-gallery-models/")
# Source-bound scientific reports may be useful to a writer, but historical
# internal judgments must never enter an independent critic's source packet.
REVIEW_PREFIXES = ("reports/ccfa-science/internal_review/",)
INSTRUCTION_FILES = {"program/cloud-operations.json", "program/ccfa-request.json", "program/scope-amendment.json"}
OPERATIONAL_FILES = {
    "reports/evidence-retrieval/latest.json",
    "state/autopilot.json", "state/model-usage.jsonl", "state/model-health.jsonl",
    "state/cloud-checkpoint.json", "state/continuation-progress.json",
    "state/continuation-status.json", "state/continuation-resumes.jsonl",
    "state/dataset-discovery-cache.json", "state/cloud-operations-cache.json",
    "state/literature-attempts.json", "state/cost-audit.json",
    "state/model-route-decisions.jsonl", "state/dynamic-routing-acceptances.json",
    "state/task-routing-profile.json",
}


def operational_path(relative: str, *, exclude_reviews: bool = False) -> bool:
    value = PurePosixPath(relative).as_posix().casefold()
    return (value in OPERATIONAL_FILES or value.startswith(OPERATIONAL_PREFIXES)
            or exclude_reviews and (value.startswith(REVIEW_PREFIXES) or value in INSTRUCTION_FILES
                                    or value == "state/research-steps.json"))


def instruction_paths(project: Path) -> set[str]:
    """Recognize actual request envelopes even when an owner uses a custom filename.

    Scientific plans/cards and source evidence are retained. Only the invocation
    envelope is removed; its referenced scientific sources remain independently
    eligible in the normal or explicitly scoped evidence packet.
    """
    found = set(INSTRUCTION_FILES)
    program = Path(project) / "program"
    if not program.is_dir():
        return found
    for path in program.rglob("*.json"):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4_000_000:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        operations = value.get("operations")
        queue = isinstance(operations, list) and any(isinstance(row, dict) and "action" in row for row in operations)
        if (queue or "desired_verdict" in value or "preferred_verdict" in value
                or value.get("kind") in {"research_iteration", "research_frontier", "research_search_tree"}
                or "action" in value and (value["action"] in {"research_toolkit", "research_iteration", "research_frontier", "research_search_tree"} or "request" in value or str(value["action"]).startswith(("ccfa_", "literature_", "figure_", "editable_figure_")))
                or "task" in value and "skill" in value
                or "task" in value and "tool_ids" in value and "input_bindings" in value
                or "operation" in value and "request" in value):
            found.add(path.relative_to(project).as_posix())
    return found


def _compact_json(text: str) -> str:
    try:
        json.loads(text)
    except (ValueError, TypeError):
        return text
    # Do not deserialize/reserialize numeric values: that can round a decimal,
    # change an exponent, or alter a protected scientific string/quotation.
    result: list[str] = []
    quoted = escaped = False
    for character in text:
        if quoted:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
            result.append(character)
        elif character not in " \t\r\n":
            result.append(character)
    return "".join(result)


def lossless_text(relative: str, text: str) -> tuple[str, str | None]:
    """Remove JSON formatting whitespace only; all other sources stay literal."""
    suffix = PurePosixPath(relative).suffix.casefold()
    if suffix == ".json":
        rendered = _compact_json(text)
    elif suffix == ".jsonl":
        # JSONL records use LF. splitlines() would also split a literal U+2028
        # inside a protected JSON string and change its content.
        rendered = "\n".join(_compact_json(line) for line in text.split("\n"))
    else:
        return text, None
    return rendered, "json-whitespace-compacted" if rendered != text else None
