#!/usr/bin/env python3
"""Quality/risk/cost-aware routing for bounded auxiliary API tasks."""
from __future__ import annotations
import argparse,json,os,uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
try:
    from scripts import ai_providers,model_runtime
    from scripts.publication_figures import PROJECTS_ROOT,safe_file
except ImportError:
    import ai_providers,model_runtime  # type: ignore
    from publication_figures import PROJECTS_ROOT,safe_file  # type: ignore
PROFILES={"metadata-extraction":("openai","DR_OS_FAST_OPENAI_MODEL",1500,"basic","low"),"format-conversion":("openai","DR_OS_FAST_OPENAI_MODEL",1200,"basic","low"),"screening-assist":("openai","DR_OS_FAST_OPENAI_MODEL",2500,"standard","low"),"evidence-synthesis":("openai","DR_OS_PREMIUM_OPENAI_MODEL",5000,"standard","medium"),"scientific-judgment":("openai","DR_OS_PREMIUM_OPENAI_MODEL",5000,"premium","high"),"independent-critique":("anthropic","DR_OS_CRITIC_ANTHROPIC_MODEL",4500,"premium","high")}
TIERS={"basic":0,"standard":1,"premium":2}
def _json_env(name:str)->dict:
    try:value=json.loads(os.environ.get(name,"{}"))
    except json.JSONDecodeError as exc:raise ValueError(f"{name} must be valid JSON") from exc
    if not isinstance(value,dict):raise ValueError(f"{name} must be an object")
    return value
def _health(project:Path)->dict[tuple[str,str],str]:
    path=project/"state"/"model-health.jsonl";result={};cutoff=datetime.now(timezone.utc)-timedelta(hours=24)
    if not path.is_file():return result
    for line in path.read_text(encoding="utf-8").splitlines():
        try:row=json.loads(line);stamp=datetime.fromisoformat(str(row["checked_at"]).replace("Z","+00:00"))
        except (KeyError,ValueError,json.JSONDecodeError):continue
        if stamp>=cutoff:result[(str(row.get("provider")),str(row.get("model")))]=str(row.get("status"))
    return result
def _candidates(project:Path,kind:str,provider:str,configured:str,legacy:str|None,minimum:str)->list[dict]:
    raw=_json_env("DR_OS_ROUTING_CANDIDATES_JSON").get(kind,[]);rows=[]
    if legacy:rows.append({"provider":provider,"model":legacy,"tier":"standard","priority":10})
    if isinstance(raw,list):rows.extend(x for x in raw if isinstance(x,dict))
    rows.append({"provider":provider,"model":configured,"tier":"premium","priority":100});health=_health(project);seen=set();valid=[]
    for row in rows:
        candidate_provider=str(row.get("provider") or provider);model=str(row.get("model") or "");tier=str(row.get("tier") or "basic")
        if not model or (candidate_provider,model) in seen:continue
        seen.add((candidate_provider,model))
        if ai_providers.provider_family(candidate_provider)!=ai_providers.provider_family(provider) or tier not in TIERS or TIERS[tier]<TIERS[minimum] or health.get((candidate_provider,model))=="failed":continue
        valid.append({"provider":candidate_provider,"model":model,"tier":tier,"priority":int(row.get("priority",50)),"health":health.get((candidate_provider,model),"unknown")})
    return valid
def plan(project:Path,kind:str,provider:str,prompt:str,max_tokens:int|None=None)->dict:
    family,env_name,ceiling,minimum,risk=PROFILES[kind]
    if ai_providers.provider_family(provider)!=family:raise ValueError(f"{kind} requires {family} family")
    configured=ai_providers.configuration(provider)["model"];legacy=os.environ.get(env_name);rates=_json_env("DR_OS_MODEL_PRICING_JSON");candidates=_candidates(project,kind,provider,configured,legacy,minimum)
    if not candidates:raise ValueError("no healthy candidate satisfies family and minimum quality tier")
    for row in candidates:
        if row["model"]!=configured and row["model"] not in rates:raise ValueError(f"declare explicit CNY rates for alternate model {row['model']} in DR_OS_MODEL_PRICING_JSON")
    tokens=max_tokens or ceiling
    if not 1<=tokens<=ceiling:raise ValueError(f"{kind} output cap must be 1..{ceiling}")
    estimated=model_runtime.estimate_tokens(prompt)
    for row in candidates:row["maximum_estimated_cost_cny"]=model_runtime.cost_cny(row["provider"],estimated,tokens,row["model"])
    candidates.sort(key=(lambda x:(x["maximum_estimated_cost_cny"],x["priority"])) if risk=="low" else (lambda x:(x["priority"],-TIERS[x["tier"]])));chosen=candidates[0]
    state=project/"state"/"run.json";active=json.loads(state.read_text(encoding="utf-8")).get("active_paper") if state.is_file() else None;budget=model_runtime.budget_status(project,active);maximum=chosen["maximum_estimated_cost_cny"]
    return {"profile":kind,"provider":chosen["provider"],"model":chosen["model"],"family":family,"quality_tier":chosen["tier"],"risk":risk,"health":chosen["health"],"candidate_count":len(candidates),"input_tokens_estimated":estimated,"output_tokens_ceiling":tokens,"maximum_estimated_cost_cny":maximum,"budget":budget,"within_estimated_budget":maximum<=budget["project_remaining"] and (budget["paper_remaining"] is None or maximum<=budget["paper_remaining"]),"persistent_output":False}
def run(project:Path,kind:str,provider:str,prompt:str,max_tokens:int|None=None)->dict:
    info=plan(project,kind,provider,prompt,max_tokens);run_id="aux-"+uuid.uuid4().hex;state=project/"state"/"run.json";stage="writing-and-review" if state.is_file() and json.loads(state.read_text()).get("active_paper") else "auxiliary";result=model_runtime.call(project,run_id=run_id,stage=stage,role=kind,provider=info["provider"],model=info["model"],prompt=prompt,max_output_tokens=info["output_tokens_ceiling"]);directory=project/"api_runs"/run_id;directory.mkdir(parents=True,exist_ok=False);receipt={**info,"run_id":run_id,"reported_model":result.reported_model,"cache_hit":result.cache_hit,"text":result.text,"not_manuscript_or_evidence":True};(directory/"result.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n");return {"run_id":run_id,"result":(directory/"result.json").relative_to(project).as_posix(),"model":result.reported_model or result.model,"cache_hit":result.cache_hit,"not_manuscript_or_evidence":True}
def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--project",required=True);p.add_argument("--kind",choices=sorted(PROFILES),required=True);p.add_argument("--provider",choices=ai_providers.PROVIDERS,required=True);p.add_argument("--prompt-file",required=True);p.add_argument("--max-output-tokens",type=int);p.add_argument("--execute",action="store_true");a=p.parse_args();project=PROJECTS_ROOT/a.project;prompt=safe_file(project,a.prompt_file,"prompt-file").read_text();value=run(project,a.kind,a.provider,prompt,a.max_output_tokens) if a.execute else plan(project,a.kind,a.provider,prompt,a.max_output_tokens);print(json.dumps(value,indent=2,ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
