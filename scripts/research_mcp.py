#!/usr/bin/env python3
"""Zero-cost MCP router for chat-first Doctoral Research OS management."""
from __future__ import annotations
import json,re,sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
ROUTES=(("citations",r"参考文献|引用|doi|citation|reference","citations"),("figures",r"图表|科研图|figure|plot|chart","figures"),("systematic-review",r"系统综述|prisma|systematic","systematic-review"),("paper-audit",r"全文一致|paper.?facts|术语|缩写|符号|audit","paper-audit"),("review",r"审稿|concern|rebuttal|reviewer","review"),("library-import",r"zotero|obsidian|文献库","library-import"),("journal",r"期刊|jcr|q1|q2|journal","journal"),("experiment",r"实验|experiment|docker","experiment"),("write",r"写作|正文|word|docx|latex|manuscript","write"),("api-tasks",r"api|成本|token|模型|route","api-tasks"))
def safe_project(value:str)->str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}",value):raise ValueError("invalid project slug")
    return value
def route_request(project:str,request:str)->dict[str,Any]:
    safe_project(project);request=request.strip()
    if not request:raise ValueError("request is required")
    intent=skill="doctoral-research"
    for candidate,pattern,target in ROUTES:
        if re.search(pattern,request,re.I):intent=candidate;skill=target;break
    match=re.search(r"\bP\d{2}\b",request,re.I)
    return {"project":project,"paper":match.group(0).upper() if match else None,"intent":intent,"skill":skill,"paid_call_started":False,"gate_approved":False,"submission_started":False,"next":"Read the routed Skill, inspect state, preflight costs, run deterministic checks, and stop at human gates."}
def status(project:str)->dict[str,Any]:
    safe_project(project);path=ROOT/"projects"/project/"state"/"run.json"
    if not path.is_file():return {"exists":False,"project":project,"paid_call_started":False}
    value=json.loads(path.read_text(encoding="utf-8"));return {"exists":True,"project":project,"stage":value.get("stage"),"gate":value.get("gate"),"status":value.get("status"),"active_paper":value.get("active_paper"),"paid_call_started":False}
TOOLS=[{"name":"research_route","description":"Route a natural-language research request without paid calls.","inputSchema":{"type":"object","required":["project","request"],"properties":{"project":{"type":"string"},"request":{"type":"string"}}}},{"name":"research_status","description":"Read current project stage and gate without mutation.","inputSchema":{"type":"object","required":["project"],"properties":{"project":{"type":"string"}}}}]
def handle(message:dict[str,Any])->dict[str,Any]:
    mid=message.get("id");method=message.get("method")
    if method=="initialize":return {"jsonrpc":"2.0","id":mid,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"doctoral-research-os","version":"2.3.0"}}}
    if method=="notifications/initialized":return {}
    if method=="tools/list":return {"jsonrpc":"2.0","id":mid,"result":{"tools":TOOLS}}
    if method=="tools/call":
        params=message.get("params",{});name=params.get("name");args=params.get("arguments",{})
        try:
            if name=="research_route":value=route_request(str(args.get("project","")),str(args.get("request","")))
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
