#!/usr/bin/env python3
"""Record a human-verified current JCR/SCI Q1 venue check."""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
class JcrVerificationError(RuntimeError):pass
def verify(payload):
    required=["database","verification_year","impact_factor","quartile","category","indexing","source_url","verified_by","verified_at"]
    missing=[k for k in required if k not in payload]
    if missing:raise JcrVerificationError(f"Missing fields: {', '.join(missing)}")
    if payload["database"]!="Clarivate Journal Citation Reports":raise JcrVerificationError("database must be Clarivate Journal Citation Reports")
    if not isinstance(payload["verification_year"],int) or payload["verification_year"]<2020:raise JcrVerificationError("verification_year must be a valid recent JCR year")
    if not isinstance(payload["impact_factor"],(int,float)) or isinstance(payload["impact_factor"],bool) or payload["impact_factor"]<=1.0:raise JcrVerificationError("impact_factor must be > 1.0")
    if payload["quartile"]!="Q1":raise JcrVerificationError("quartile must be Q1 for this Doctoral Research OS")
    if payload["indexing"] not in {"SCI","SCIE"}:raise JcrVerificationError("indexing must be SCI or SCIE")
    if not str(payload["source_url"]).startswith("https://"):raise JcrVerificationError("source_url must use HTTPS")
    if not str(payload["verified_by"]).strip() or not str(payload["verified_at"]).strip():raise JcrVerificationError("verified_by and verified_at are required")
def main():
    p=argparse.ArgumentParser();p.add_argument("--paper-dir",type=Path,required=True);p.add_argument("--year",type=int,required=True);p.add_argument("--impact-factor",type=float,required=True);p.add_argument("--quartile",choices=["Q1","Q2","Q3","Q4"],required=True);p.add_argument("--category",required=True);p.add_argument("--indexing",choices=["SCI","SCIE"],required=True);p.add_argument("--source-url",required=True);p.add_argument("--verified-by",required=True);p.add_argument("--notes",default="");a=p.parse_args()
    payload={"schema_version":"1.0","database":"Clarivate Journal Citation Reports","verification_year":a.year,"impact_factor":a.impact_factor,"quartile":a.quartile,"category":a.category,"indexing":a.indexing,"source_url":a.source_url,"verified_by":a.verified_by,"verified_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"notes":a.notes};verify(payload);a.paper_dir.mkdir(parents=True,exist_ok=True);out=a.paper_dir/"jcr-verification.json";out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(out);return 0
if __name__=="__main__":raise SystemExit(main())
