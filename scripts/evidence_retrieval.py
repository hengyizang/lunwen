"""Cloud CPU lexical/BM25 leads over explicit hash-bound sources; no AI calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from scripts.evidence_context import safe_text
from scripts.research_artifacts import path_in, read, write

PLAN = "program/retrieval-plan.json"
REPORT = "reports/evidence-retrieval/latest.json"


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text.casefold())
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        words.extend(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return words


def retrieve(project: Path, spec: dict, *, redact=lambda value: value) -> dict:
    sources, query, limit = spec.get("sources"), spec.get("query"), spec.get("limit", 8)
    if (spec.get("schema_version") != "1.0" or not isinstance(sources, list) or not 1 <= len(sources) <= 50
            or not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000
            or type(limit) is not int or not 1 <= limit <= 20):
        raise ValueError("retrieval needs 1-50 explicit sources, a query and limit 1-20")
    terms = set(tokens(query))
    if not terms:
        raise ValueError("query has no searchable terms")
    chunks, searched, total = [], [], 0
    for source in sources:
        relative = source["path"]
        if relative in {item["path"] for item in searched}:
            raise ValueError("duplicate retrieval source")
        text, digest = safe_text(project, relative, redact)
        if source.get("sha256") != digest:
            raise ValueError("retrieval source changed: " + relative)
        total += len(text.encode())
        if total > 20_000_000:
            raise ValueError("retrieval exceeds 20 MB; declare a smaller explicit corpus")
        searched.append({"path": relative, "sha256": digest})
        lines = text.splitlines(keepends=True)
        for start in range(0, len(lines), 20):
            quote = "".join(lines[start:start + 20])
            counts = Counter(tokens(quote))
            chunks.append({"path": relative, "sha256": digest, "start_line": start + 1,
                           "end_line": min(start + 20, len(lines)), "quote": quote,
                           "counts": counts, "length": sum(counts.values())})
    if not chunks:
        raise ValueError("explicit retrieval corpus contains no text")
    average = sum(row["length"] for row in chunks) / len(chunks) or 1
    frequencies = {term: sum(term in row["counts"] for row in chunks) for term in terms}
    for row in chunks:
        score = 0.0
        for term in terms:
            frequency = row["counts"][term]
            if frequency:
                inverse = math.log(1 + (len(chunks) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
                score += inverse * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * row["length"] / average))
        row["score"] = score
    ranked = sorted((row for row in chunks if row["score"] > 0), key=lambda row: (-row["score"], row["path"], row["start_line"]))
    results = []
    for row in ranked[:limit]:
        quote = row["quote"]
        results.append({k: v for k, v in row.items() if k not in {"counts", "length", "quote"}})
        results[-1].update(quote=quote if len(quote.encode()) <= 8000 else None,
                           excerpt_sha256=hashlib.sha256(quote.encode()).hexdigest(),
                           quote_omitted_due_to_size=len(quote.encode()) > 8000)
    return {"schema_version": "1.0", "algorithm": "BM25 k1=1.2 b=0.75; English terms and Chinese bigrams",
            "query": query, "searched_sources": searched, "chunk_count": len(chunks),
            "matching_chunks": len(ranked), "results": results, "not_returned_chunk_count": len(chunks) - len(results),
            "advisory_only": True, "automatic_source_exclusion": False,
            "scientific_completeness_verified": False, "paid_calls": 0,
            "next": "Read the original hash-bound ranges. An explicit context plan must retain constraints and full counterevidence; lexical nonmatches are not irrelevant evidence."}


def refresh(project: Path) -> dict:
    from scripts.api_orchestrator import redact
    result = retrieve(project, read(path_in(project, PLAN)), redact=redact)
    write(project / REPORT, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    from scripts.api_orchestrator import project_root
    print(json.dumps(refresh(project_root(args.project)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
