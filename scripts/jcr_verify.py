#!/usr/bin/env python3
"""Record source-bound JCR metadata and report venue-target observations."""
from __future__ import annotations

import argparse,json,math
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlsplit


class JcrVerificationError(RuntimeError):pass


def verify(payload, required_quartile="Q1"):
    if not isinstance(payload,dict):raise JcrVerificationError("JCR record must be an object")
    required=["schema_version","database","verification_year","impact_factor","quartile","category","indexing","source_url","verified_by","verified_at"]
    missing=[k for k in required if k not in payload]
    if missing:raise JcrVerificationError(f"Missing fields: {', '.join(missing)}")
    if payload["schema_version"]!="1.0":raise JcrVerificationError("schema_version must be 1.0")
    if payload["database"]!="Clarivate Journal Citation Reports":raise JcrVerificationError("database must be Clarivate Journal Citation Reports")
    current_year=datetime.now(timezone.utc).year;verification_year=payload["verification_year"]
    if type(verification_year) is not int or not 1<=verification_year<=current_year:raise JcrVerificationError("verification_year must identify an actual, non-future JCR edition")
    if type(payload["impact_factor"]) not in (int,float) or (type(payload["impact_factor"]) is float and not math.isfinite(payload["impact_factor"])) or payload["impact_factor"]<0:raise JcrVerificationError("impact_factor must be a finite non-negative number")
    try:
        from scripts.venue_policy import meets_target,normalize_quartile
    except ImportError:
        from venue_policy import meets_target,normalize_quartile
    required=normalize_quartile(required_quartile)
    if required is None:raise JcrVerificationError("required quartile must be Q1 or Q2")
    if payload["quartile"] not in {"Q1","Q2","Q3","Q4"}:raise JcrVerificationError("quartile must identify the recorded JCR Q1, Q2, Q3 or Q4 category-year value")
    if not isinstance(payload["category"],str) or not payload["category"].strip():raise JcrVerificationError("category must identify the verified JCR category")
    if payload["indexing"] not in {"SCI","SCIE","SSCI","AHCI","ESCI"}:raise JcrVerificationError("indexing must identify the actual Web of Science index")
    source=urlsplit(payload["source_url"]) if isinstance(payload["source_url"],str) else None
    if source is None or source.scheme!="https" or not source.hostname or source.username or source.password:raise JcrVerificationError("source_url must use HTTPS without embedded credentials")
    if not isinstance(payload["verified_by"],str) or not payload["verified_by"].strip():raise JcrVerificationError("verified_by must identify the actual recorder")
    try:verified_at=datetime.fromisoformat(str(payload["verified_at"]).replace("Z","+00:00"))
    except ValueError as exc:raise JcrVerificationError("verified_at must be an ISO-8601 timestamp") from exc
    if verified_at.tzinfo is None:raise JcrVerificationError("verified_at must include a timezone")
    age=datetime.now(timezone.utc)-verified_at.astimezone(timezone.utc)
    if age < -timedelta(days=1):raise JcrVerificationError("verified_at cannot claim a future verification")
    observations=[]
    if not meets_target(payload["quartile"],required):observations.append(f"recorded {payload['quartile']} differs from the {required} planning target; assess actual venue fit")
    if verification_year<current_year-1:observations.append(f"record describes JCR edition {verification_year}; current ranking remains unknown")
    return observations
def main():
    p=argparse.ArgumentParser();p.add_argument("--paper-dir",type=Path,required=True);p.add_argument("--year",type=int,required=True);p.add_argument("--impact-factor",type=float,required=True);p.add_argument("--quartile",choices=["Q1","Q2","Q3","Q4"],required=True);p.add_argument("--category",required=True);p.add_argument("--indexing",choices=["SCI","SCIE","SSCI","AHCI","ESCI"],required=True);p.add_argument("--source-url",required=True);p.add_argument("--verified-by",required=True);p.add_argument("--notes",default="");a=p.parse_args()
    payload={"schema_version":"1.0","database":"Clarivate Journal Citation Reports","verification_year":a.year,"impact_factor":a.impact_factor,"quartile":a.quartile,"category":a.category,"indexing":a.indexing,"source_url":a.source_url,"verified_by":a.verified_by,"verified_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"notes":a.notes}
    target="Q1";contract=a.paper_dir/"paper-contract.json"
    if contract.is_file():
        try:
            from scripts.venue_policy import target_from_contract
        except ImportError:
            from venue_policy import target_from_contract
        try:target=target_from_contract(json.loads(contract.read_text(encoding="utf-8")))
        except (OSError,json.JSONDecodeError):pass
    observations=verify(payload,target);a.paper_dir.mkdir(parents=True,exist_ok=True);out=a.paper_dir/"jcr-verification.json";out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(out)
    for observation in observations:print("Planning observation: "+observation)
    return 0
if __name__=="__main__":raise SystemExit(main())
