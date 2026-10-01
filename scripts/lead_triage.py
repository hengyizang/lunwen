"""Optional Jev queue labels for public metadata; never evidence or exclusion."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from scripts import bocha_jev_probe, free_jev_probe, literature_evidence
from scripts.cloud_research_steps import fresh, path_in, read, write


def triage(project: Path, receipt_id: str, provider: str, limit: int = 5) -> dict:
    if provider not in {'openrouter','bocha'} or type(limit) is not int or not 1 <= limit <= 8:
        raise ValueError('triage requires a supported provider and 1–8 public records')
    ledger = literature_evidence.read_jsonl(project/'evidence/literature-api-ledger.jsonl')
    receipt = next((r for r in ledger if r.get('receipt_id') == receipt_id and fresh(r,project)),None)
    if receipt is None:
        raise ValueError('triage needs a fresh, hash-verified controlled literature receipt')
    works = read(path_in(project,receipt['normalized_results_path']),{}).get('works',[])
    results=[]
    for work in works[:limit]:
        # Only metadata from a public search response is sent, never project
        # plans, unpublished manuscript text, credentials or private datasets.
        metadata={'title':str(work.get('title',''))[:1000],
                  'description':str(work.get('abstract') or work.get('summary') or '')[:2000]}
        identity=hashlib.sha256(json.dumps({'provider':provider,'metadata':metadata},sort_keys=True).encode()).hexdigest()
        output=project/'evidence/lead-triage'/f'{identity}.json'
        previous=read(output)
        if previous:
            if previous.get('status')!='passed':
                raise RuntimeError('an earlier Jev request has no verified outcome; inspect before retrying')
            results.append(previous);continue
        if provider=='openrouter' and not os.environ.get('OPENROUTER_API_KEY'):
            raise RuntimeError('optional OpenRouter triage is not configured; ordinary review retains every lead')
        if provider=='bocha' and (not os.environ.get('BOCHA_JEV_API_KEY') or not os.environ.get('BOCHA_JEV_FREE_POLICY_CHECKED_ON')):
            raise RuntimeError('optional Bocha triage needs its key and a current owner-checked no-charge policy date')
        base={'schema_version':'1.0','source_receipt_id':receipt_id,'public_metadata_sha256':identity,
              'scientific_evidence':False,'automatic_exclusion_allowed':False,'input_is_public_metadata':True}
        write(output,{**base,'status':'pending'})
        try:
            result=(free_jev_probe.probe(os.environ['OPENROUTER_API_KEY'],public_metadata=metadata)
                    if provider=='openrouter' else bocha_jev_probe.trial(os.environ['BOCHA_JEV_API_KEY'],
                        os.environ['BOCHA_JEV_FREE_POLICY_CHECKED_ON'],public_metadata=metadata))
        except (RuntimeError,ValueError,OSError) as exc:
            write(output,{**base,'status':'inspection_required','error':str(exc)[:400]})
            raise
        result={**result,**base};write(output,result);results.append(result)
    return {'provider':provider,'labels':results,'all_records_retained':True,
            'scientific_decisions_require_primary_sources_and_human_review':True}
