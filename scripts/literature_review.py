"""Question-scoped retrieval over the current authorized literature workbench.

The writer supplies bounded query expansions in its existing cycle. This module
does no acquisition, embedding/model request, scope approval or scientific review.
"""
from __future__ import annotations

import html
from pathlib import Path

from scripts import evidence_retrieval, literature_workbench as workbench
from scripts.research_artifacts import path_in, record, sha, write

OUTPUT = "reports/literature-retrieval"


def prepare(project: Path, request: dict) -> dict:
    allowed = {"schema_version", "question", "paper_ids", "query_expansions", "limit", "dense_cache", "stances"}
    if not isinstance(request, dict) or set(request) - allowed or request.get("schema_version") != "1.0":
        raise ValueError("unsupported literature retrieval request")
    question = workbench._text(request.get("question"), "retrieval question", 1000)
    identifiers = request.get("paper_ids")
    if (not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 30
            or any(not isinstance(x, str) for x in identifiers) or len(set(identifiers)) != len(identifiers)):
        raise ValueError("select 1..30 distinct registered literature papers")
    library, _, manifest = workbench._snapshot(project)
    papers = {p["id"]: p for p in library["papers"] if p.get("status") == "current"}
    stances = request.get("stances", {})
    if (not isinstance(stances, dict) or set(stances) - set(identifiers)
            or any(v not in {"neutral", "contradicts", "mixed"} for v in stances.values())):
        raise ValueError("retrieval stances must refer to selected papers")
    from scripts.literaturectl import source_blocks
    sources, bindings, paper_sources = {}, {}, {}
    for identifier in identifiers:
        if identifier not in papers:
            raise ValueError("selected paper is absent or stale: " + identifier)
        blocks, dependencies = source_blocks(project, papers[identifier])
        paper_sources[identifier] = sorted({b["path"] for b in blocks})
        for binding in dependencies:
            bindings[binding["path"]] = binding
        for block in blocks:
            source = sources.setdefault(block["path"], {"path": block["path"], "sha256": block["sha256"],
                "ranges": [], "stance": "neutral"})
            span = {k: block[k] for k in ("start_line", "end_line")}
            if block.get("pdf_page") is not None:
                span["pdf_page"] = block["pdf_page"]
            if span not in source["ranges"]:
                source["ranges"].append(span)
            if stances.get(identifier) in {"contradicts", "mixed"}:
                source["stance"] = stances[identifier]
    for source in sources.values():
        source["ranges"].sort(key=lambda span: span["start_line"])
    spec = {"schema_version": "1.0", "query": question, "sources": list(sources.values()),
            "limit": request.get("limit", 8)}
    for key in ("query_expansions", "dense_cache"):
        if key in request:
            spec[key] = request[key]
    return {"spec": spec, "paper_sources": paper_sources,
            "paper_scopes": {p: papers[p].get("source_scope", "scope_not_declared") for p in identifiers},
            "dependencies": list(bindings.values()),
            "workbench_manifest_sha256": sha(project / manifest["output_dir"] / "manifest.json"),
            "doctoral_scope": library.get("scope"), "question": question}


def retrieve(project: Path, request: dict) -> dict:
    prepared = prepare(project, request)
    result = evidence_retrieval.retrieve(project, prepared["spec"])
    return {**result, "kind": "question_scoped_literature_retrieval", "question": prepared["question"],
            "paper_sources": prepared["paper_sources"], "dependencies": prepared["dependencies"],
            "paper_scopes": prepared["paper_scopes"],
            "workbench_manifest_sha256": prepared["workbench_manifest_sha256"],
            "doctoral_scope": prepared["doctoral_scope"], "original_text_only": True,
            "query_expansions_are_proposals": True, "semantic_support_verified": False,
            "novelty_verified": False, "paid_calls": 0}


def refresh(project: Path, request_file="program/literature-retrieval.json") -> dict:
    if not isinstance(request_file, str) or not request_file.startswith("program/"):
        raise ValueError("literature retrieval request belongs under program/")
    source = workbench._path(project, request_file)
    request = workbench._json(source.read_bytes())
    result = retrieve(project, request)
    result["request"] = {"path": request_file, "sha256": sha(source)}
    result["implementation_sha256"] = sha(Path(__file__))
    result["fingerprint"] = workbench._digest(result)
    directory = path_in(project, OUTPUT, exists=False)
    report, view = directory / "latest.json", directory / "index.html"
    write(report, result)
    rows = []
    for item in result["results"]:
        href = "../../" + item["path"] + "#L" + str(item["start_line"])
        rows.append('<li><a href="' + html.escape(href, quote=True) + '">' +
            html.escape(item["path"]) + " · lines " + str(item["start_line"]) + "–" + str(item["end_line"]) +
            "</a><pre>" + html.escape(item.get("quote") or "Excerpt omitted; inspect source.") + "</pre></li>")
    view.write_text('<!doctype html><meta charset="utf-8"><title>Literature evidence retrieval</title>' +
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">' +
        "<h1>Question-scoped original evidence</h1><p>" + html.escape(result["question"]) +
        "</p><p>Ranking is a reading aid. Source presence does not establish claim support.</p><ol>" +
        "".join(rows) + "</ol>", encoding="utf-8")
    record(project, [report, view], "scripts/literature_review.py")
    return {"report": OUTPUT + "/latest.json", "view": OUTPUT + "/index.html", **result}
