#!/usr/bin/env python3
"""Record a human-verified, recent JCR/SCI Q1 venue check."""
from __future__ import annotations

import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path


class JcrVerificationError(RuntimeError):pass


def verify(payload):
    required=["schema_version","database","verification_year","impact_factor","quartile","category","indexing","source_url","verified_by","verified_at"]
    missing=[k for k in required if k not in payload]
    if missing:raise JcrVerificationError(f"Missing fields: {', '.join(missing)}")
    if payload["schema_version"]!="1.0":raise JcrVerificationError("schema_version must be 1.0")
    if payload["database"]!="Clarivate Journal Citation Reports":raise JcrVerificationError("database must be Clarivate Journal Citation Reports")
    current_year=datetime.now(timezone.utc).year;verification_year=payload["verification_year"]
    if not isinstance(verification_year,int) or isinstance(verification_year,bool) or verification_year not in {current_year,current_year-1}:raise JcrVerificationError("verification_year must identify the current or immediately previous JCR edition")
    if not isinstance(payload["impact_factor"],(int,float)) or isinstance(payload["impact_factor"],bool) or payload["impact_factor"]<=1.0:raise JcrVerificationError("impact_factor must be > 1.0")
    if payload["quartile"]!="Q1":raise JcrVerificationError("quartile must be current JCR Q1 for this Doctoral Research OS")
    if not isinstance(payload["category"],str) or not payload["category"].strip():raise JcrVerificationError("category must identify the verified JCR category")
    if payload["indexing"] not in {"SCI","SCIE"}:raise JcrVerificationError("indexing must be SCI or SCIE")
    if not isinstance(payload["source_url"],str) or not payload["source_url"].startswith("https://"):raise JcrVerificationError("source_url must use HTTPS")
    if not isinstance(payload["verified_by"],str) or not payload["verified_by"].strip():raise JcrVerificationError("verified_by must identify the human verifier")
    try:verified_at=datetime.fromisoformat(str(payload["verified_at"]).replace("Z","+00:00"))
    except ValueError as exc:raise JcrVerificationError("verified_at must be an ISO-8601 timestamp") from exc
    if verified_at.tzinfo is None:raise JcrVerificationError("verified_at must include a timezone")
    age=datetime.now(timezone.utc)-verified_at.astimezone(timezone.utc)
    if age < -timedelta(days=1) or age > timedelta(days=400):raise JcrVerificationError("verified_at must be a recent human check (within 400 days)")
def main():
    p=argparse.ArgumentParser();p.add_argument("--paper-dir",type=Path,required=True);p.add_argument("--year",type=int,required=True);p.add_argument("--impact-factor",type=float,required=True);p.add_argument("--quartile",choices=["Q1","Q2","Q3","Q4"],required=True);p.add_argument("--category",required=True);p.add_argument("--indexing",choices=["SCI","SCIE"],required=True);p.add_argument("--source-url",required=True);p.add_argument("--verified-by",required=True);p.add_argument("--notes",default="");a=p.parse_args()
    payload={"schema_version":"1.0","database":"Clarivate Journal Citation Reports","verification_year":a.year,"impact_factor":a.impact_factor,"quartile":a.quartile,"category":a.category,"indexing":a.indexing,"source_url":a.source_url,"verified_by":a.verified_by,"verified_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"notes":a.notes};verify(payload);a.paper_dir.mkdir(parents=True,exist_ok=True);out=a.paper_dir/"jcr-verification.json";out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(out);return 0
if __name__=="__main__":raise SystemExit(main())
