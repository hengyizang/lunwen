#!/usr/bin/env python3
"""Validate the machine-readable requirements matrix."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];MATRIX=ROOT/"config"/"requirements-traceability.json"
def validate(path:Path=MATRIX)->list[str]:
    try:value=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:return [str(exc)]
    if not isinstance(value,dict):return ["requirements trace must be a JSON object"]
    rows=value.get("requirements");errors=[]
    if value.get("schema_version")!="1.0" or not isinstance(rows,list) or not rows:return ["requirements trace must be schema_version 1.0 with requirements"]
    ids=set()
    for row in rows:
        if not isinstance(row,dict):errors.append("requirement row must be object");continue
        identifier=str(row.get("id",""))
        if identifier in ids or not identifier.startswith("R"):errors.append(f"duplicate or invalid id: {identifier}")
        ids.add(identifier)
        if row.get("implementation") not in {"complete","workflow-ready"}:errors.append(f"{identifier}: implementation not closed")
        evidence=row.get("evidence")
        if not isinstance(evidence,list) or not evidence:errors.append(f"{identifier}: evidence missing");continue
        for relative in evidence:
            if not (ROOT/str(relative)).exists():errors.append(f"{identifier}: missing evidence path {relative}")
    return errors
def main()->int:
    errors=validate();value=json.loads(MATRIX.read_text());print(json.dumps({"requirements":len(value["requirements"]),"pass":not errors,"errors":errors,"external_acceptance":[{"id":r["id"],"status":r["acceptance"]} for r in value["requirements"] if r["acceptance"] not in {"ci-required","gate-enforced"}]},indent=2));return 0 if not errors else 2
if __name__=="__main__":raise SystemExit(main())
