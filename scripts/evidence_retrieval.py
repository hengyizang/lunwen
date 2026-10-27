"""Bounded BM25/query-fusion and optional cached-vector leads; no AI calls.

Query expansions are explicit writer inputs, not autonomous search decisions.
Cached vectors must bind the exact query and every current source block. This
module never downloads models, requests embeddings or infers scientific support.
"""
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


def _query(value, field: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 1000 or not tokens(value):
        raise ValueError(field + " needs 1-1000 characters and searchable terms")
    return value


def _vector(value, dimension: int, field: str) -> list[float]:
    if (not isinstance(value, list) or len(value) != dimension
            or any(type(number) not in (int, float) for number in value)):
        raise ValueError(field + " needs a finite vector with the declared dimension")
    try:
        value = [float(number) for number in value]
    except OverflowError as exc:
        raise ValueError(field + " has an unrepresentable number") from exc
    if not all(math.isfinite(number) for number in value):
        raise ValueError(field + " needs finite numbers")
    norm = math.hypot(*value)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError(field + " must have a finite nonzero norm")
    return [number / norm for number in value]


def _dense_scores(project: Path, binding: dict, query: str, chunks: list[dict], searched: list[dict], redact) -> tuple[list[float], dict]:
    if (not isinstance(binding, dict) or set(binding) != {"path", "sha256"}
            or not isinstance(binding.get("path"), str)):
        raise ValueError("dense_cache needs an exact path and sha256")
    content, digest = safe_text(project, binding["path"], redact)
    if binding["sha256"] != digest:
        raise ValueError("dense cache changed")
    cache = json.loads(content)
    if not isinstance(cache, dict) or set(cache) != {"schema_version", "model", "dimension", "query", "sources", "blocks"} or cache.get("schema_version") != "1.0":
        raise ValueError("invalid dense cache schema")
    model = cache["model"]
    if (not isinstance(model, dict) or set(model) != {"id", "revision"}
            or any(not isinstance(v, str) or not 1 <= len(v.strip()) <= 200 for v in model.values())):
        raise ValueError("dense cache needs an explicit model identity and revision")
    dimension = cache["dimension"]
    if type(dimension) is not int or not 2 <= dimension <= 4096:
        raise ValueError("dense dimension must be 2-4096")
    query_record = cache["query"]
    query_hash = hashlib.sha256(query.encode()).hexdigest()
    if (not isinstance(query_record, dict) or set(query_record) != {"text", "sha256", "vector"}
            or query_record["text"] != query or query_record["sha256"] != query_hash):
        raise ValueError("dense query binding changed")
    query_vector = _vector(query_record["vector"], dimension, "dense query")
    expected_sources = [{key: row[key] for key in ("path", "sha256", "ranges") if key in row} for row in searched]
    if cache["sources"] != expected_sources:
        raise ValueError("dense source manifest changed")
    expected = {(row["path"], row["sha256"], row["start_line"], row["end_line"],
                 hashlib.sha256(row["quote"].encode()).hexdigest()): index for index, row in enumerate(chunks)}
    entries = cache["blocks"]
    if not isinstance(entries, list) or len(entries) != len(chunks):
        raise ValueError("dense cache must cover every current block exactly once")
    scores, seen = [0.0] * len(chunks), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "start_line", "end_line", "excerpt_sha256", "vector"}:
            raise ValueError("invalid dense block schema")
        if type(entry["start_line"]) is not int or type(entry["end_line"]) is not int:
            raise ValueError("dense block line numbers must be integers")
        if any(not isinstance(entry[key], str) for key in ("path", "sha256", "excerpt_sha256")):
            raise ValueError("dense block identity must contain strings")
        key = (entry["path"], entry["sha256"], entry["start_line"], entry["end_line"], entry["excerpt_sha256"])
        if key not in expected or key in seen:
            raise ValueError("dense block binding changed or is duplicated")
        seen.add(key)
        vector = _vector(entry["vector"], dimension, "dense block")
        scores[expected[key]] = max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(query_vector, vector))))
    return scores, {"path": binding["path"], "sha256": digest, "model": model,
                    "dimension": dimension, "model_identity_independently_verified": False,
                    "embedding_calls_made": 0, "coverage": "all_current_blocks"}


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text.casefold())
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        words.extend(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return words


def corpus(project: Path, sources: list[dict], *, redact=lambda value: value) -> tuple[list[dict], list[dict]]:
    chunks, searched, total = [], [], 0
    for source in sources:
        if (not isinstance(source, dict) or not isinstance(source.get("path"), str)
                or not isinstance(source.get("sha256"), str)
                or not isinstance(source.get("stance", "neutral"), str)
                or source.get("stance", "neutral") not in {"supports", "contradicts", "mixed", "neutral"}):
            raise ValueError("retrieval source needs path, sha256 and an optional declared stance")
        relative = source["path"]
        if relative in {item["path"] for item in searched}:
            raise ValueError("duplicate retrieval source")
        text, digest = safe_text(project, relative, redact)
        if source.get("sha256") != digest:
            raise ValueError("retrieval source changed: " + relative)
        total += len(text.encode())
        if total > 20_000_000:
            raise ValueError("retrieval exceeds 20 MB; declare a smaller explicit corpus")
        searched.append({"path": relative, "sha256": digest, "stance": source.get("stance", "neutral")})
        lines = text.splitlines(keepends=True)
        ranges = source.get("ranges")
        if "ranges" in source:
            if not isinstance(ranges, list) or not 1 <= len(ranges) <= 200:
                raise ValueError("source ranges need 1-200 explicit original-text ranges")
            previous_end = 0
            for selected_range in ranges:
                if (not isinstance(selected_range, dict)
                        or set(selected_range) - {"start_line", "end_line", "pdf_page"}
                        or type(selected_range.get("start_line")) is not int
                        or type(selected_range.get("end_line")) is not int
                        or not previous_end < selected_range["start_line"] <= selected_range["end_line"] <= len(lines)
                        or ("pdf_page" in selected_range and (type(selected_range["pdf_page"]) is not int or selected_range["pdf_page"] < 1))):
                    raise ValueError("source ranges must be ordered, nonoverlapping 1-based line ranges")
                previous_end = selected_range["end_line"]
            searched[-1]["ranges"] = ranges
        else:
            ranges = [{"start_line": 1, "end_line": len(lines)}] if lines else []
        searched[-1]["indexed_line_count"] = sum(row["end_line"] - row["start_line"] + 1 for row in ranges)
        searched[-1]["text_line_count"] = len(lines)
        for selected_range in ranges:
            for start in range(selected_range["start_line"] - 1, selected_range["end_line"], 20):
                end = min(start + 20, selected_range["end_line"])
                quote = "".join(lines[start:end])
                counts = Counter(tokens(quote))
                chunks.append({"path": relative, "sha256": digest, "start_line": start + 1,
                               "end_line": end, "quote": quote,
                               **({"pdf_page": selected_range["pdf_page"]} if "pdf_page" in selected_range else {}),
                               "counts": counts, "length": sum(counts.values())})
    if not chunks:
        raise ValueError("explicit retrieval corpus contains no text")
    return chunks, searched


def retrieve(project: Path, spec: dict, *, redact=lambda value: value) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("retrieval plan must be an object")
    sources, query, limit = spec.get("sources"), spec.get("query"), spec.get("limit", 8)
    if (spec.get("schema_version") != "1.0" or not isinstance(sources, list) or not 1 <= len(sources) <= 50
            or type(limit) is not int or not 1 <= limit <= 20):
        raise ValueError("retrieval needs 1-50 explicit sources, a query and limit 1-20")
    query = _query(query, "query")
    expansions = spec.get("query_expansions", [])
    if not isinstance(expansions, list) or len(expansions) > 5:
        raise ValueError("at most five explicit query expansions are allowed")
    queries = [{"id": "original", "query": query, "reason": "original research question"}]
    seen_queries = {query.casefold().strip()}
    for number, expansion in enumerate(expansions, 1):
        if (not isinstance(expansion, dict) or set(expansion) != {"query", "reason"}
                or not isinstance(expansion["reason"], str) or not 1 <= len(expansion["reason"].strip()) <= 1000):
            raise ValueError("query expansions need query and a concrete bounded reason")
        value = _query(expansion["query"], "expanded query")
        if value.casefold().strip() in seen_queries:
            raise ValueError("duplicate query expansion")
        seen_queries.add(value.casefold().strip())
        queries.append({"id": f"expansion-{number}", **expansion})
    chunks, searched = corpus(project, sources, redact=redact)
    average = sum(row["length"] for row in chunks) / len(chunks) or 1
    routes, scores_by_route = [], []
    for route in queries:
        terms = set(tokens(route["query"]))
        frequencies = {term: sum(term in row["counts"] for row in chunks) for term in terms}
        scores = []
        for row in chunks:
            score = 0.0
            for term in terms:
                frequency = row["counts"][term]
                if frequency:
                    inverse = math.log(1 + (len(chunks) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
                    score += inverse * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * row["length"] / average))
            scores.append(score)
        routes.append({**route, "method": "BM25", "semantic_expansion_verified": False})
        scores_by_route.append(scores)
    dense = None
    if "dense_cache" in spec:
        scores, dense = _dense_scores(project, spec["dense_cache"], query, chunks, searched, redact)
        scores_by_route.append(scores)
        routes.append({"id": "cached-dense", "method": "cosine_similarity", "query": query,
                       "reason": "explicitly supplied source-bound cached vectors"})
    fused = len(routes) > 1
    for row in chunks:
        row.update(score=0.0, lexical_score=0.0, retrieval_routes={})
    for route, scores in zip(routes, scores_by_route):
        ranked_indices = sorted((i for i, score in enumerate(scores) if score > 0),
                                key=lambda i: (-scores[i], chunks[i]["path"], chunks[i]["start_line"]))
        route["matching_chunks"] = len(ranked_indices)
        route["no_match"] = not ranked_indices
        for rank, index in enumerate(ranked_indices, 1):
            row = chunks[index]
            row["retrieval_routes"][route["id"]] = {"rank": rank, "score": scores[index]}
            row["score"] += 1.0 / (60 + rank) if fused else scores[index]
            if route["id"] == "original":
                row["lexical_score"] = scores[index]
    ranked = sorted((row for row in chunks if row["score"] > 0), key=lambda row: (-row["score"], row["path"], row["start_line"]))
    counter_sources = [row["path"] for row in searched if row["stance"] in {"contradicts", "mixed"}]
    if len(counter_sources) > limit:
        raise ValueError("result limit cannot retain every declared counterevidence source")
    selected = []
    for relative in counter_sources:
        candidates = [row for row in chunks if row["path"] == relative]
        if not candidates:
            raise ValueError("declared counterevidence source has no readable block")
        row = sorted(candidates, key=lambda item: (-item["score"], item["start_line"]))[0]
        row["selection_reason"] = "declared_counterevidence_requires_full_source_review"
        selected.append(row)
    for row in ranked:
        if len(selected) == limit:
            break
        if row not in selected:
            row["selection_reason"] = "ranked_retrieval_lead"
            selected.append(row)
    selected.sort(key=lambda row: (-row["score"], row["path"], row["start_line"]))
    rerank_evidence = None
    if "rerank_cache" in spec:
        from scripts.literature_semantic import apply_rerank_cache
        rerank_evidence = apply_rerank_cache(project, spec, selected)
    results = []
    for row in selected:
        quote = row["quote"]
        results.append({k: v for k, v in row.items() if k not in {"counts", "length", "quote"}})
        results[-1].update(quote=quote if len(quote.encode()) <= 8000 else None,
                           excerpt_sha256=hashlib.sha256(quote.encode()).hexdigest(),
                           quote_omitted_due_to_size=len(quote.encode()) > 8000)
    selected_keys = {(row["path"], row["start_line"]) for row in selected}
    for route in routes:
        route["returned_chunks"] = sum(route["id"] in row["retrieval_routes"] for row in selected)
        route["not_returned_matching_chunks"] = route["matching_chunks"] - route["returned_chunks"]
    for source in searched:
        if hashlib.sha256(path_in(project, source["path"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("retrieval source changed during processing: " + source["path"])
        source["matching_chunks"] = sum(row["path"] == source["path"] for row in ranked)
        source["returned_chunks"] = sum(path == source["path"] for path, _ in selected_keys)
        source["source_integrity"] = "current_hash_checked"
    fingerprint = hashlib.sha256(json.dumps({"query": query, "queries": queries, "sources": searched,
        "limit": limit, "dense_cache": dense, "rerank_cache": rerank_evidence,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"schema_version": "1.0", "algorithm": "RRF k=60 over explicit BM25 queries and optional cached dense vectors" if fused else "BM25 k1=1.2 b=0.75; English terms and Chinese bigrams",
            "query": query, "searched_sources": searched, "chunk_count": len(chunks),
            "matching_chunks": len(ranked), "results": results, "not_returned_chunk_count": len(chunks) - len(results),
            "routes": routes, "dense_cache": dense, "rerank_cache": rerank_evidence, "input_fingerprint": fingerprint,
            "declared_counterevidence_sources": counter_sources,
            "counterevidence_retention_is_not_full_reading": True,
            "query_expansions_are_unverified_writer_inputs": True,
            "advisory_only": True, "automatic_source_exclusion": False,
            "scientific_completeness_verified": False, "paid_calls": 0, "network_requests": 0,
            "embedding_calls_made": 0, "reranker_calls_made": 0,
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
