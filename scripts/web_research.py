#!/usr/bin/env python3
"""Current web leads with one metered POST and the shared cumulative CNY cap."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from scripts import cloud_checkpoint, model_spend
from scripts.cloud_research_steps import read, write
from scripts.free_jev_probe import NoRedirect


def search(query: str, max_results: int = 10, *, project_root: Path | None = None) -> dict:
    if project_root is None:
        raise RuntimeError('a project spending ledger is required for web search')
    if not isinstance(query,str) or not 1 <= len(query.strip()) <= 1000 or type(max_results) is not int or not 1 <= max_results <= 10:
        raise ValueError('web search needs a bounded query and 1–10 results')
    signature=hashlib.sha256(json.dumps([query,max_results]).encode()).hexdigest()
    target=project_root/'evidence/web-search'/f'{signature}.json'
    old=read(target)
    if (old and timedelta(0) <= datetime.now(timezone.utc)-datetime.fromisoformat(old['generated_at']) < timedelta(days=7)
            and cloud_checkpoint.sha(project_root/cloud_checkpoint.relative(old['raw_response_path']))==old['response_sha256']):
        return old
    key=os.environ.get('TAVILY_API_KEY','')
    try: rate=float(os.environ.get('DR_OS_TAVILY_CREDIT_CNY','0'))
    except ValueError: rate=0
    if not key or not math.isfinite(rate) or rate <= 0:
        raise RuntimeError('Tavily needs its key and an explicit current CNY/credit rate; official-source URLs can be supplied instead')
    control=model_spend.read(project_root,required=True)
    if control['reservations']:
        raise RuntimeError('billing reconciliation is required before another external API call')
    reservation=model_spend.reserve(project_root,max_cost_cny=rate,paper_id=None,paper_limit_cny=60,run_id='web-'+signature[:16])
    cloud_checkpoint.sync_billing(project_root)
    payload={'query':query,'max_results':max_results,'search_depth':'basic','auto_parameters':False,
             'include_answer':False,'include_usage':True,'include_raw_content':False}
    request=urllib.request.Request('https://api.tavily.com/search',data=json.dumps(payload).encode(),method='POST',
              headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','User-Agent':'DoctoralResearchOS/2.3'})
    try:
        with urllib.request.build_opener(NoRedirect).open(request,timeout=60) as response:
            raw=response.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('response exceeds limit')
        data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError('response must be an object')
    except (OSError,ValueError):
        raise RuntimeError('web search outcome is ambiguous; reservation retained, no automatic retry') from None
    credits=data.get('usage',{}).get('credits')
    if type(credits) is not int or credits<0:
        raise RuntimeError('web search credit usage missing; reconcile the retained reservation')
    # Even free plan credits are conservatively counted at the configured rate.
    # Unexpected overage is recorded and raises before any next paid call.
    model_spend.settle(project_root,reservation,actual_cost_cny=credits*rate)
    result={'schema_version':'1.0','query':query,'generated_at':datetime.now(timezone.utc).isoformat(),
            'provider':'tavily','search_depth':'basic','results':data.get('results',[])[:max_results],
            'request_id':data.get('request_id'),'usage_credits':credits,'estimated_cost_cny':credits*rate,
            'response_sha256':hashlib.sha256(raw).hexdigest(),
            'warning':'Search snippets are leads only. Retrieve and verify each primary posting before ranking.'}
    write(target,result)
    raw_path=target.with_name(target.stem+'.raw.json');raw_path.write_bytes(raw)
    result['raw_response_path']=raw_path.relative_to(project_root).as_posix();write(target,result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('query');parser.add_argument('--project',required=True)
    parser.add_argument('--max-results',type=int,default=10);args=parser.parse_args()
    from scripts.researchctl import project_dir
    print(json.dumps(search(args.query,args.max_results,project_root=project_dir(args.project)),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
