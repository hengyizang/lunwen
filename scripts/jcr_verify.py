#!/usr/bin/env python3
"""Record a human-verified current JCR/SCI Q1 venue check.

The script never impersonates Clarivate. The author must inspect current JCR/SCIE
information and record the primary source. Q1 is mandatory because this research
OS is configured to target JCR Q1 venues; acceptance is never guaranteed.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


class JcrVerificationError(RuntimeError):
    pass


def verify(payload: dict) -> None:
    required = ["database", "verification_year", "impact_factor", "quartile", "category", "indexing", "source_url", "verified_by", "verified_at"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise JcrVerificationError(f"Missing fields: {', '.join(missing)}")
    if payload["database"] != "Clarivate Journal Citation Reports":
        raise JcrVerificationError("database must be Clarivate Journal Citation Reports")
    if not isinstance(payload["verification_year"], int) or payload["verification_year"] < 2020:
        raise JcrVerificationError("verification_year must be a valid recent JCR year")
    if not isinstance(payload["impact_factor"], (int, float)) or isinstance(payload["impact_factor"], bool) or payload["impact_factor"] <= 1.0:
        raise JcrVerificationError("impact_factor must be > 1.0")
    if payload["quartile"] != "Q1":
        raise JcrVerificationError("quartile must be Q1 for this Doctoral Research OS")
    if payload["indexing"] not in {"SCIE", "SCI"}:
        raise JcrVerificationError("indexing must be SCI or SCIE")
    if not str(payload["source_url"]).startswith("https://"):
        raise JcrVerificationError("source_url must use HTTPS")
    if not str(payload["verified_by"]).strip() or not str(payload["verified_at"]).strip():
        raise JcrVerificationError("verified_by and verified_at are required")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-dir", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--impact-factor", type=float, required=True)
    parser.add_argument("--quartile", choices=["Q1", "Q2", "Q3", "Q4"], required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--indexing", choices=["SCI", "SCIE"], required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--verified-by", required=True)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    payload = {
        "schema_version": "1.0", "database": "Clarivate Journal Citation Reports",
        "verification_year": args.year, "impact_factor": args.impact_factor,
        "quartile": args.quartile, "category": args.category, "indexing": args.indexing,
        "source_url": args.source_url, "verified_by": args.verified_by,
        "verified_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "notes": args.notes,
    }
    verify(payload)
    args.paper_dir.mkdir(parents=True, exist_ok=True)
    output = args.paper_dir / "jcr-verification.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
