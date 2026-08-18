#!/usr/bin/env python3
"""Optional web-search adapter for current topic intelligence.

Uses Tavily when TAVILY_API_KEY is configured. Without it, the command fails
closed instead of pretending that static literature data is current job/market
evidence. Search results are evidence leads and must be human-verified.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


def search(query: str, max_results: int = 10) -> dict[str, Any]:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is required for live web evidence; configure it or use official-source URLs manually")
    payload = json.dumps({"api_key": key, "query": query, "max_results": max_results, "search_depth": "advanced"}).encode()
    request = urllib.request.Request(
        "https://api.tavily.com/search",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "DoctoralResearchOS/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Web search HTTP {exc.code}") from exc
    return {
        "schema_version": "1.0",
        "query": query,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "provider": "tavily",
        "results": data.get("results", []),
        "warning": "Search results are leads, not proof. Verify jobs, salary, institutional requirements, market claims and publication metrics at the primary source before G1/G5.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--max-results", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(search(args.query, args.max_results), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
