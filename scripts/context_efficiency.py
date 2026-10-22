"""Lossless prompt preparation. No model selection, inference or source edits."""
from __future__ import annotations

import json
from pathlib import PurePosixPath


# Scientific sources, constraints, approvals and spending authority are retained.
# Invocation transcripts must not leak old plans/verdicts into independent review.
OPERATIONAL_PREFIXES = ("state/runs/", "state/citation-metadata/",
                        "reports/ccfa-tasks/", "reports/ccfa-science/history/")
# Source-bound scientific reports may be useful to a writer, but historical
# internal judgments must never enter an independent critic's source packet.
REVIEW_PREFIXES = ("reports/ccfa-science/internal_review/",)
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
            or exclude_reviews and value.startswith(REVIEW_PREFIXES))


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
