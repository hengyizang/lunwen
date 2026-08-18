#!/usr/bin/env python3
"""Dependency-free literature discovery using OpenAlex and Crossref.

Results are discovery evidence, not proof of novelty or quality. The caller
must preserve the returned IDs/DOIs and later perform human/source checks.
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "DoctoralResearchOS/1.0 (research discovery)"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def openalex(query: str, limit: int = 25) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"search": query, "per-page": min(limit, 100), "mailto": ""})
    data = get_json(f"https://api.openalex.org/works?{params}")
    out: list[dict[str, Any]] = []
    for item in data.get("results", []):
        out.append({
            "source": "openalex",
            "id": item.get("id"),
            "doi": item.get("doi"),
            "title": item.get("display_name"),
            "year": item.get("publication_year"),
            "cited_by_count": item.get("cited_by_count"),
            "type": item.get("type"),
            "primary_location": item.get("primary_location"),
            "open_access": item.get("open_access"),
        })
    return out


def crossref(query: str, limit: int = 25) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query.bibliographic": query, "rows": min(limit, 100)})
    data = get_json(f"https://api.crossref.org/works?{params}")
    out: list[dict[str, Any]] = []
    for item in data.get("message", {}).get("items", []):
        out.append({
            "source": "crossref",
            "doi": item.get("DOI"),
            "title": (item.get("title") or [None])[0],
            "year": ((item.get("published-print") or item.get("published-online") or {}).get("date-parts") or [[None]])[0][0],
            "container": (item.get("container-title") or [None])[0],
            "publisher": item.get("publisher"),
            "type": item.get("type"),
        })
    return out


def discover(query: str, limit: int) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "query": query,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sources": ["https://api.openalex.org", "https://api.crossref.org"],
        "openalex": openalex(query, limit),
        "crossref": crossref(query, limit),
        "interpretation": "Discovery only; do not infer novelty, JCR quartile, acceptance probability, or causal evidence from this file.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = discover(args.query, args.limit)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
