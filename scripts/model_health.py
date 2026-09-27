#!/usr/bin/env python3
"""Explicit low-token provider health probe; dry-run unless --execute is given."""
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
try:from scripts import ai_providers,model_runtime
except ImportError:import ai_providers,model_runtime  # type: ignore
ROOT=Path(__file__).resolve().parents[1]
def probe(project:Path,provider:str,model:str,execute:bool=False)->dict:
    row={"provider":provider,"model":model,"checked_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),"status":"dry-run","paid_call":False,"scientific_quality_test":False}
    if execute:
        try:
            result=model_runtime.call(project,run_id="health-"+datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),stage="health",role="endpoint-health",provider=provider,model=model,prompt="Reply with exactly OK.",max_output_tokens=8);row.update(status="passed" if result.text.strip() else "failed",paid_call=True,reported_model=result.reported_model)
        except (ai_providers.ProviderError,ValueError,OSError) as exc:row.update(status="failed",paid_call=True,error=str(exc))
        path=project/"state"/"model-health.jsonl";path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("a",encoding="utf-8") as handle:handle.write(json.dumps(row,ensure_ascii=False)+"\n")
    return row
def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--project",required=True);p.add_argument("--provider",required=True,choices=ai_providers.PROVIDERS);p.add_argument("--model",required=True);p.add_argument("--execute",action="store_true");a=p.parse_args();project=ROOT/"projects"/a.project;print(json.dumps(probe(project,a.provider,a.model,a.execute),indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
