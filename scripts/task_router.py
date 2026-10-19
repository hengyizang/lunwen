#!/usr/bin/env python3
"""Quality/risk/cost-aware routing for bounded auxiliary API tasks."""
from __future__ import annotations
import argparse,json,os,uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
try:
    from scripts import ai_providers,model_runtime,model_routing,metadata_contract,engineering_contract
    from scripts.publication_figures import PROJECTS_ROOT,safe_file
except ImportError:
    import ai_providers,model_runtime,model_routing,metadata_contract,engineering_contract  # type: ignore
    from publication_figures import PROJECTS_ROOT,safe_file  # type: ignore
PROFILES={"metadata-extraction":("openai","DR_OS_FAST_OPENAI_MODEL",1500,"basic","low"),"format-conversion":("openai","DR_OS_FAST_OPENAI_MODEL",1200,"basic","low"),"screening-assist":("openai","DR_OS_FAST_OPENAI_MODEL",2500,"standard","low"),"evidence-synthesis":("openai","DR_OS_PREMIUM_OPENAI_MODEL",5000,"standard","medium"),"scientific-judgment":("openai","DR_OS_PREMIUM_OPENAI_MODEL",5000,"premium","high"),"independent-critique":("anthropic","DR_OS_CRITIC_ANTHROPIC_MODEL",4500,"premium","high"),"engineering-diagnosis":("deepseek","DR_OS_DIAGNOSTIC_MODEL",4000,"standard","medium"),"multimodal-inspection":("google","DR_OS_MULTIMODAL_MODEL",4000,"standard","medium")}
TIERS={"basic":0,"standard":1,"premium":2}
PROFILES.update({kind:("deepseek","DR_OS_DIAGNOSTIC_MODEL",4000,"standard","medium")
                 for kind in engineering_contract.TASKS})

def _contract_handler(kind:str):
    if kind=="metadata-extraction":return metadata_contract
    if kind in engineering_contract.TASKS:return engineering_contract
    raise ValueError("source contracts require metadata extraction or bounded engineering support")
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
def _task_prompt(route:dict,prompt:str)->str:
    specialization=engineering_contract.TASKS.get(route.get("role"),"")
    return "Task boundary: "+route["quality_boundary"]+"\n"+specialization+"\nReturn a candidate for review; do not invent missing source fields or perform a scientific approval.\n\n"+prompt


def _production_plan(project:Path,kind:str,provider:str,prompt:str,max_tokens:int|None=None,*,source_contract:dict|None=None)->dict:
    route=model_routing.select("auxiliary",kind)
    if _health(project).get((route["provider"],route["model"]))=="failed":
        raise ValueError("approved task route recently failed; inspect it before requesting another paid call")
    ceiling=route["max_output_tokens"];tokens=ceiling if max_tokens is None else max_tokens
    if type(tokens) is not int or not 1<=tokens<=ceiling:
        raise ValueError(f"{kind} output cap must be 1..{ceiling}")
    request_prompt=_task_prompt(route,prompt)
    contract_required=route["model_key"]=="luna" or kind in engineering_contract.TASKS
    complete=not contract_required or source_contract is not None
    if source_contract is not None:
        request_prompt=_contract_handler(kind).build_prompt(request_prompt,source_contract)
    estimated=model_runtime.estimate_tokens(request_prompt)
    maximum=model_runtime.cost_cny(route["provider"],estimated,tokens,route["model"])
    state=project/"state"/"run.json"
    active=json.loads(state.read_text(encoding="utf-8")).get("active_paper") if state.is_file() else None
    budget=model_runtime.budget_status(project,active)
    return {**route,"profile":kind,"quality_tier":"bounded_auxiliary" if route["model_key"]=="luna" else "approved_task_route",
            "risk":PROFILES[kind][4],"health":_health(project).get((route["provider"],route["model"]),"unknown"),
            "candidate_count":1,"input_tokens_estimated":estimated,"output_tokens_ceiling":tokens,
            "maximum_estimated_cost_cny":maximum,"budget":budget,
            "within_estimated_budget":complete and maximum<=budget["project_remaining"] and (budget["paper_remaining"] is None or maximum<=budget["paper_remaining"]),
            "persistent_output":False,"automatic_acceptance":False,"scientific_equivalence_verified":False,
            "source_contract_required":contract_required,"estimated_cost_complete":complete,
            "estimated_input_excludes_missing_sources":not complete,"ready_for_execution":complete}


def plan(project:Path,kind:str,provider:str,prompt:str,max_tokens:int|None=None,*,source_contract:dict|None=None)->dict:
    if kind not in PROFILES:raise ValueError(f"unknown auxiliary task kind: {kind}")
    if model_routing.production_enabled():return _production_plan(project,kind,provider,prompt,max_tokens,source_contract=source_contract)
    if kind in engineering_contract.TASKS:raise ValueError("bounded engineering support requires production routing")
    if source_contract is not None:raise ValueError("source-field contracts require production routing")
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
def run(project:Path,kind:str,provider:str,prompt:str,max_tokens:int|None=None,*,attachments:list[dict]|None=None,source_contract:dict|None=None)->dict:
    if model_routing.production_enabled() and (kind=="metadata-extraction" or kind in engineering_contract.TASKS):
        source_contract=_contract_handler(kind).validate_contract(source_contract)
    elif source_contract is not None:
        raise ValueError("source contracts require production metadata extraction or bounded engineering support")
    info=plan(project,kind,provider,prompt,max_tokens,source_contract=source_contract)
    if kind=="multimodal-inspection" and not attachments:
        raise ValueError("multimodal inspection requires explicit source attachments")
    if attachments and kind!="multimodal-inspection":
        raise ValueError("source attachments are supported only by multimodal inspection")
    run_id="aux-"+uuid.uuid4().hex;state=project/"state"/"run.json"
    stage="writing-and-review" if state.is_file() and json.loads(state.read_text()).get("active_paper") else "auxiliary"
    request={"run_id":run_id,"stage":stage,"role":kind,"provider":info["provider"],"model":info["model"],
             "prompt":prompt,"max_output_tokens":info["output_tokens_ceiling"]}
    if model_routing.production_enabled():
        request["reasoning_effort"]=info["reasoning_effort"]
        request["prompt"]=_task_prompt(info,prompt)
    if attachments:request["attachments"]=attachments
    if source_contract is not None:request["source_contract"]=source_contract
    result=model_runtime.call(project,**request)
    directory=project/"api_runs"/run_id;directory.mkdir(parents=True,exist_ok=False)
    receipt={**info,"run_id":run_id,"reported_model":result.reported_model,"cache_hit":result.cache_hit,
             "text":result.text,"not_manuscript_or_evidence":True,"automatic_acceptance":False}
    if source_contract is not None:receipt["source_contract_sha256"]=_contract_handler(kind).contract_sha256(source_contract)
    if kind in engineering_contract.TASKS:
        receipt["required_followup"]="OpenAI review/implementation and deterministic cloud checks; no automatic application"
        receipt["scientific_equivalence_verified"]=False
    (directory/"result.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return {"run_id":run_id,"result":(directory/"result.json").relative_to(project).as_posix(),"model":result.reported_model or result.model,
            "cache_hit":result.cache_hit,"not_manuscript_or_evidence":True}
def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True);p.add_argument("--kind",choices=sorted(PROFILES),required=True)
    p.add_argument("--provider",choices=ai_providers.PROVIDERS,default="openai")
    p.add_argument("--prompt-file",required=True);p.add_argument("--max-output-tokens",type=int)
    p.add_argument("--attachments-file",help="Project-relative JSON source attachment list for multimodal inspection")
    p.add_argument("--source-contract",help="Project-relative JSON source contract for metadata or engineering support")
    p.add_argument("--execute",action="store_true");a=p.parse_args();project=PROJECTS_ROOT/a.project
    prompt=safe_file(project,a.prompt_file,"prompt-file").read_text(encoding="utf-8")
    attachments=json.loads(safe_file(project,a.attachments_file,"attachments-file").read_text(encoding="utf-8")) if a.attachments_file else None
    source_contract=json.loads(safe_file(project,a.source_contract,"source-contract").read_text(encoding="utf-8")) if a.source_contract else None
    if source_contract is not None:source_contract=_contract_handler(a.kind).validate_contract(source_contract)
    if attachments is not None and not isinstance(attachments,list):raise ValueError("attachments must be a JSON list")
    if a.kind=="multimodal-inspection" and not attachments:raise ValueError("multimodal inspection requires source attachments")
    value=run(project,a.kind,a.provider,prompt,a.max_output_tokens,attachments=attachments,source_contract=source_contract) if a.execute else plan(project,a.kind,a.provider,prompt,a.max_output_tokens,source_contract=source_contract)
    if model_routing.production_enabled() and a.kind=="metadata-extraction":
        value["source_contract_required"]=True
        value["source_contract_supplied"]=source_contract is not None
    print(json.dumps(value,indent=2,ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
