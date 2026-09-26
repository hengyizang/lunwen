#!/usr/bin/env python3
"""Cost-aware auxiliary API tasks; full manuscript writing uses the gated cycle.

The router writes only to protected api_runs, never directly to manuscripts or
figure assets. It refuses a low-cost alternate model without declared rates.
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

try:
    from scripts import ai_providers, model_runtime
    from scripts.publication_figures import PROJECTS_ROOT, safe_file
except ImportError:
    import ai_providers, model_runtime  # type: ignore
    from publication_figures import PROJECTS_ROOT, safe_file  # type: ignore


PROFILES={
    "metadata-extraction": ("openai","DR_OS_FAST_OPENAI_MODEL",1500),
    "format-conversion": ("openai","DR_OS_FAST_OPENAI_MODEL",1200),
    "screening-assist": ("openai","DR_OS_FAST_OPENAI_MODEL",2500),
    "evidence-synthesis": ("openai","DR_OS_PREMIUM_OPENAI_MODEL",5000),
    "scientific-judgment": ("openai","DR_OS_PREMIUM_OPENAI_MODEL",5000),
    "independent-critique": ("anthropic","DR_OS_CRITIC_ANTHROPIC_MODEL",4500),
}


def plan(project: Path, kind: str, provider: str, prompt: str, max_tokens: int | None = None) -> dict:
    family,env_name,ceiling=PROFILES[kind]
    if ai_providers.provider_family(provider)!=family:
        raise ValueError(f"{kind} requires {family} family")
    configured=ai_providers.configuration(provider)["model"]
    model=os.environ.get(env_name) or configured
    if not model:raise ValueError(f"configure {env_name} or the provider's model")
    try:rates=json.loads(os.environ.get("DR_OS_MODEL_PRICING_JSON","{}"))
    except json.JSONDecodeError as exc:raise ValueError("DR_OS_MODEL_PRICING_JSON must be valid JSON") from exc
    if not isinstance(rates,dict):raise ValueError("DR_OS_MODEL_PRICING_JSON must be an object")
    if model!=configured and model not in rates:
        raise ValueError(f"declare explicit CNY rates for alternate model {model} in DR_OS_MODEL_PRICING_JSON")
    tokens=max_tokens or ceiling
    if not 1<=tokens<=ceiling:raise ValueError(f"{kind} output cap must be 1..{ceiling}")
    estimated=model_runtime.estimate_tokens(prompt)
    active=None
    state=project/"state"/"run.json"
    if state.is_file():
        active=json.loads(state.read_text(encoding="utf-8")).get("active_paper")
    budget=model_runtime.budget_status(project,active)
    maximum=model_runtime.cost_cny(provider,estimated,tokens,model)
    return {"profile":kind,"provider":provider,"model":model,"family":family,
            "input_tokens_estimated":estimated,"output_tokens_ceiling":tokens,
            "maximum_estimated_cost_cny":maximum,
            "budget":budget,"within_estimated_budget":maximum<=budget["project_remaining"] and (
                budget["paper_remaining"] is None or maximum<=budget["paper_remaining"]),
            "persistent_output":False}


def run(project: Path, kind: str, provider: str, prompt: str, max_tokens: int | None = None) -> dict:
    info=plan(project,kind,provider,prompt,max_tokens)
    run_id="aux-"+uuid.uuid4().hex
    stage="writing-and-review" if (project/"state"/"run.json").is_file() and \
        json.loads((project/"state"/"run.json").read_text(encoding="utf-8")).get("active_paper") else "auxiliary"
    result=model_runtime.call(project,run_id=run_id,stage=stage,role=kind,provider=provider,
        model=info["model"],prompt=prompt,max_output_tokens=info["output_tokens_ceiling"])
    directory=project/"api_runs"/run_id;directory.mkdir(parents=True,exist_ok=False)
    receipt={**info,"run_id":run_id,"requested_model":result.model,
        "reported_model":result.reported_model,"cache_hit":result.cache_hit,
        "text":result.text,"not_manuscript_or_evidence":True}
    (directory/"result.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return {"run_id":run_id,"result":(directory/"result.json").relative_to(project).as_posix(),
            "model":result.reported_model or result.model,"cache_hit":result.cache_hit,
            "not_manuscript_or_evidence":True}


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True);p.add_argument("--kind",choices=sorted(PROFILES),required=True)
    p.add_argument("--provider",choices=ai_providers.PROVIDERS,required=True)
    p.add_argument("--prompt-file",required=True);p.add_argument("--max-output-tokens",type=int)
    p.add_argument("--execute",action="store_true",help="explicitly send a paid API request")
    args=p.parse_args();project=PROJECTS_ROOT/args.project
    prompt=safe_file(project,args.prompt_file,"prompt-file").read_text(encoding="utf-8")
    value=run(project,args.kind,args.provider,prompt,args.max_output_tokens) if args.execute else plan(project,args.kind,args.provider,prompt,args.max_output_tokens)
    print(json.dumps(value,indent=2,ensure_ascii=False));return 0


if __name__=="__main__":raise SystemExit(main())
