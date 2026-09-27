#!/usr/bin/env python3
"""Zero-cost MCP router for chat-first Doctoral Research OS management."""
from __future__ import annotations
import json,re,sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
ROUTES=(("citations",r"参考文献|引用|doi|citation|reference","citations"),("figures",r"图表|科研图|figure|plot|chart","figures"),("systematic-review",r"系统综述|prisma|systematic","systematic-review"),("paper-audit",r"全文一致|paper.?facts|术语|缩写|符号|manuscript audit","paper-audit"),("review",r"审稿|concern|rebuttal|reviewer","review"),("library-import",r"zotero|obsidian|文献库","library-import"),("journal",r"期刊|jcr|q1|q2|journal","journal"),("experiment",r"实验|experiment|docker","experiment"),("data",r"数据集|数据质量|dataset|data quality","data"),("write",r"写作|正文|word|docx|latex|manuscript","write"),("package",r"投稿包|投稿材料|submission package","package"),("retarget",r"改投|转投|retarget","retarget"),("topic",r"选题|研究方向|novelty|topic","topic"),("research-briefing",r"研究简报|research brief|briefing","research-briefing"),("audit",r"验收|仓库审计|validate repo|\bci\b","audit"),("api-tasks",r"api|成本|token|模型|route","api-tasks"),("start",r"新建|初始化|开始项目|initialize|new project","start"),("continue",r"继续|接着|resume|continue","continue"))
def safe_project(value:str)->str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}",value):raise ValueError("invalid project slug")
    return value
def route_request(project:str,request:str)->dict[str,Any]:
    safe_project(project);request=request.strip()
    if not request:raise ValueError("request is required")
    intent=skill="continue"
    for candidate,pattern,target in ROUTES:
        if re.search(pattern,request,re.I):intent=candidate;skill=target;break
    match=re.search(r"\bP\d{2}\b",request,re.I)
    return {"project":project,"paper":match.group(0).upper() if match else None,"intent":intent,"skill":skill,"paid_call_started":False,"gate_approved":False,"submission_started":False,"next":"Read the routed Skill, inspect state, preflight costs, run deterministic checks, and stop at human gates."}
def status(project:str)->dict[str,Any]:
    safe_project(project);path=ROOT/"projects"/project/"state"/"run.json"
    if not path.is_file():return {"exists":False,"project":project,"paid_call_started":False}
    value=json.loads(path.read_text(encoding="utf-8"));return {"exists":True,"project":project,"stage":value.get("stage"),"gate":value.get("gate"),"status":value.get("status"),"active_paper":value.get("active_paper"),"paid_call_started":False}
def projects()->dict[str,Any]:
    root=ROOT/"projects";items=[]
    if root.is_dir():
        for path in sorted(root.iterdir()):
            if not path.is_dir() or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}",path.name):continue
            try:value=status(path.name)
            except (OSError,ValueError,json.JSONDecodeError) as exc:value={"exists":True,"project":path.name,"status":"invalid","error":str(exc),"paid_call_started":False}
            if value.get("exists"):items.append(value)
    return {"projects":items,"count":len(items),"paid_call_started":False,"mutation_started":False}
def context(request:str,project:str|None=None)->dict[str,Any]:
    request=request.strip()
    if not request:raise ValueError("request is required")
    inventory=projects()["projects"]
    selected=project.strip() if isinstance(project,str) else ""
    if selected:safe_project(selected);resolution="explicit"
    elif len(inventory)==1:selected=str(inventory[0]["project"]);resolution="automatic-single-project"
    elif not inventory:
        return {"project":None,"project_resolution":"none","selection_required":False,"initialization_required":True,"skill":"start","intent":"start","paid_call_started":False,"gate_approved":False,"submission_started":False,"must_stop":True,"next":"Collect the research goal and constraints, then initialize a project only after the user confirms them."}
    else:
        return {"project":None,"project_resolution":"ambiguous","selection_required":True,"candidates":[item["project"] for item in inventory],"paid_call_started":False,"gate_approved":False,"submission_started":False,"must_stop":True,"next":"Ask the user to select one initialized project."}
    current=status(selected);routed=route_request(selected,request)
    state=current.get("status")
    if not current.get("exists"):
        next_action="Confirm the research goal and constraints, then use the start Skill to initialize this project."
        must_stop=True;human_action="confirm-project-initialization"
    elif state=="awaiting_approval":
        next_action="Present the gate dossier. Stop for explicit human approval, or reopen the gate if revision is requested."
        must_stop=True;human_action="approve-or-reopen-gate"
    elif state=="approved":
        next_action="Advance the already approved gate, reload state, then resume through the routed Skill."
        must_stop=False;human_action=None
    elif state=="submission_ready":
        next_action="Run deterministic package checks and request a named final human review before any submission."
        must_stop=True;human_action="final-package-review"
    else:
        next_action="Read the routed Skill, run deterministic preflight, disclose estimated cost before any paid call, and stop at the next human gate."
        must_stop=False;human_action=None
    return {**routed,"project_resolution":resolution,"project_state":current,"selection_required":False,"initialization_required":not current.get("exists",False),"must_stop":must_stop,"human_action":human_action,"paid_call_authorized":False,"next":next_action}
TOOLS=[{"name":"research_context","description":"Resolve the project, route a natural-language request, and report the safe next action in one zero-cost read-only call.","inputSchema":{"type":"object","required":["request"],"properties":{"project":{"type":"string"},"request":{"type":"string"}}}},{"name":"research_projects","description":"List initialized local research projects and their current stages without mutation.","inputSchema":{"type":"object","properties":{}}},{"name":"research_route","description":"Route a natural-language research request without paid calls.","inputSchema":{"type":"object","required":["project","request"],"properties":{"project":{"type":"string"},"request":{"type":"string"}}}},{"name":"research_status","description":"Read current project stage and gate without mutation.","inputSchema":{"type":"object","required":["project"],"properties":{"project":{"type":"string"}}}}]
def handle(message:dict[str,Any])->dict[str,Any]:
    mid=message.get("id");method=message.get("method")
    if method=="initialize":return {"jsonrpc":"2.0","id":mid,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"doctoral-research-os","version":"2.4.0"}}}
    if method=="notifications/initialized":return {}
    if method=="tools/list":return {"jsonrpc":"2.0","id":mid,"result":{"tools":TOOLS}}
    if method=="tools/call":
        params=message.get("params",{});name=params.get("name");args=params.get("arguments",{})
        try:
            if name=="research_context":value=context(str(args.get("request","")),args.get("project"))
            elif name=="research_projects":value=projects()
            elif name=="research_route":value=route_request(str(args.get("project","")),str(args.get("request","")))
            elif name=="research_status":value=status(str(args.get("project","")))
            else:raise ValueError("unknown tool")
        except (OSError,ValueError,json.JSONDecodeError) as exc:return {"jsonrpc":"2.0","id":mid,"result":{"isError":True,"content":[{"type":"text","text":str(exc)}]}}
        return {"jsonrpc":"2.0","id":mid,"result":{"content":[{"type":"text","text":json.dumps(value,ensure_ascii=False)}]}}
    return {"jsonrpc":"2.0","id":mid,"error":{"code":-32601,"message":"method not found"}}
def main()->int:
    for line in sys.stdin:
        try:response=handle(json.loads(line))
        except json.JSONDecodeError:continue
        if response:print(json.dumps(response,ensure_ascii=False),flush=True)
    return 0
if __name__=="__main__":raise SystemExit(main())
