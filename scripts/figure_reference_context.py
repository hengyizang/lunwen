"""Small explicit source-bound figure references for existing model roles."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.research_artifacts import path_in, read, sha


def context(project: Path) -> str:
    selector = project / "program/figure-reference-context.json"
    if not selector.is_file():
        return "(No figure-reference selection. Use free gallery search only when needed, then explicitly select at most five references.)"
    selector = path_in(project, "program/figure-reference-context.json")
    if selector.stat().st_size > 8192:
        raise ValueError("figure-reference selector exceeds 8 KB")
    selection = read(selector)
    if set(selection) != {"report", "figure_ids"} or not isinstance(selection["report"], dict) or set(selection["report"]) != {"path", "sha256"}:
        raise ValueError("figure reference selection needs exact report binding and figure_ids")
    ids = selection["figure_ids"]
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 5 or any(not isinstance(item, str) for item in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("select one to five unique reference IDs")
    relative = selection["report"]["path"]
    if not isinstance(relative, str) or not relative.startswith("reports/figure-gallery/"):
        raise ValueError("reference selector must bind a native gallery search report")
    report_path = path_in(project, relative)
    if sha(report_path) != selection["report"]["sha256"]:
        raise ValueError("figure reference selection changed")
    from scripts.figure_gallery import validate_search_report
    report = validate_search_report(project, relative)
    rows = {row["id"]: row for row in report["candidates"]}
    if not set(ids) <= rows.keys():
        raise ValueError("selected references are not in the bound search results")
    selected = [{key: rows[identity][key] for key in ("id", "title", "venue", "year", "pattern", "paper_url", "figure_url", "metadata_sha256", "license")}
                for identity in ids]
    return json.dumps({"kind": "untrusted_layout_references", "report": selection["report"],
                       "query": report["query"], "references": selected,
                       "boundary": report["boundary"]}, ensure_ascii=False, separators=(",", ":"))
