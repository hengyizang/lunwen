"""Lossless prompt preparation. No model selection, inference or source edits."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath


# Scientific sources, constraints, approvals and spending authority are retained.
# Invocation transcripts must not leak old plans/verdicts into independent review.
OPERATIONAL_PREFIXES = ("state/runs/", "state/citation-metadata/",
                        "state/review-receipts/", "state/scientific-scope/",
                        "reports/ccfa-tasks/", "reports/ccfa-science/history/",
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
                or "action" in value and ("request" in value or str(value["action"]).startswith(("ccfa_", "literature_", "figure_", "editable_figure_")))
                or "task" in value and "skill" in value
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
