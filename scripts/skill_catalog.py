#!/usr/bin/env python3
"""Independent, offline, incremental Codex Skill inventory and safe operations.

No global install, network update, or removal is performed by a scan. Update
and disable require a freshly generated one-use plan token and exact target.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_target(path: Path, roots: list[Path]) -> Path:
    if path.is_symlink() or not path.is_dir():raise ValueError("target must be a real skill folder")
    value=path.resolve()
    if not any(value.parent==root.resolve() for root in roots):
        raise ValueError("target must be a direct child of an explicitly listed root")
    if not (value/"SKILL.md").is_file() or (value/"SKILL.md").is_symlink():
        raise ValueError("target has no regular SKILL.md")
    return value


def _tree_digest(target: Path) -> str:
    import hashlib
    fingerprint=hashlib.sha256()
    for item in sorted(target.rglob("*")):
        if item.is_symlink():raise ValueError("planned Skill operations do not accept symlinks")
        if item.is_file():
            fingerprint.update(item.relative_to(target).as_posix().encode("utf-8"))
            fingerprint.update(bytes.fromhex(digest(item)))
    return fingerprint.hexdigest()


def _safe_destination(target: Path, destination: Path) -> Path:
    value=destination.resolve()
    if value==target or target in value.parents:
        raise ValueError("Skill catalog/backup destination cannot be inside the operated Skill")
    return value


def _metadata(path: Path) -> dict[str,Any]:
    source=path.read_text(encoding="utf-8")
    front=re.match(r"\A---\s*\n(.*?)\n---",source,re.S)
    if not front:raise ValueError(f"missing frontmatter: {path}")
    name=re.search(r"(?m)^name:\s*[\"']?([^\n\"']+)",front.group(1))
    desc=re.search(r"(?m)^description:\s*[\"']?([^\n\"']+)",front.group(1))
    if not name or not desc:raise ValueError(f"missing name/description: {path}")
    terms=set(re.findall(r"[a-z]{4,}",desc.group(1).lower()))-{"with","from","this","that","when","skill","skills"}
    return {"name":name.group(1).strip(),"description":desc.group(1).strip(),
            "capability_terms":sorted(terms),"headings":re.findall(r"(?m)^#{1,3}\s+(.+)$",source)[:20]}


def lint_skill(target: Path) -> dict[str,Any]:
    target=target.resolve();findings=[];file_count=0;total=0
    high={r"curl\s+[^\n|]+\|\s*(?:ba)?sh":"remote download piped to shell",r"wget\s+[^\n|]+\|\s*(?:ba)?sh":"remote download piped to shell",r"\brm\s+-rf\s+(?:/|~|\$HOME)":"broad destructive deletion",r"Invoke-Expression|\biex\s*\(":"dynamic PowerShell execution",r"(?:print|echo).{0,80}(?:API_KEY|TOKEN|PASSWORD)":"possible secret disclosure"}
    medium={r"\b(?:sudo|chmod\s+777)\b":"privileged or overly broad permission change",r"\b(?:eval|exec)\s*\(":"dynamic code execution",r"subprocess\.(?:run|Popen)|os\.system":"local process execution"}
    for item in sorted(target.rglob("*")):
        if item.is_symlink():findings.append({"severity":"high","path":item.relative_to(target).as_posix(),"issue":"symlink not allowed"});continue
        if not item.is_file():continue
        file_count+=1;size=item.stat().st_size;total+=size
        if size>1_000_000:findings.append({"severity":"high","path":item.relative_to(target).as_posix(),"issue":"file exceeds 1 MiB"});continue
        text=item.read_text(encoding="utf-8",errors="replace")
        for pattern,issue in high.items():
            if re.search(pattern,text,re.I):findings.append({"severity":"high","path":item.relative_to(target).as_posix(),"issue":issue})
        for pattern,issue in medium.items():
            if re.search(pattern,text,re.I):findings.append({"severity":"medium","path":item.relative_to(target).as_posix(),"issue":issue})
    if file_count>200:findings.append({"severity":"high","path":".","issue":"skill contains more than 200 files"})
    return {"file_count":file_count,"total_bytes":total,"findings":findings,"blocked":any(x["severity"]=="high" for x in findings)}


def mcp_inventory(configs:list[Path])->list[dict[str,Any]]:
    rows=[]
    for config in configs:
        if not config.is_file() or config.is_symlink():raise ValueError(f"invalid MCP config: {config}")
        value=json.loads(config.read_text(encoding="utf-8"));servers=value.get("mcpServers",{})
        if not isinstance(servers,dict):raise ValueError(f"mcpServers must be an object: {config}")
        for name,spec in sorted(servers.items()):
            if not isinstance(spec,dict):raise ValueError(f"malformed MCP server {name}")
            environment=spec.get("env",{});secret_literals=[]
            if isinstance(environment,dict):secret_literals=[key for key,val in environment.items() if re.search(r"KEY|TOKEN|SECRET|PASSWORD",key,re.I) and str(val).strip()]
            rows.append({"config":str(config.resolve()),"name":name,"type":spec.get("type"),"command":spec.get("command"),"args":spec.get("args",[]),"literal_secret_fields":secret_literals,"safe":not secret_literals})
    return rows


def scan(roots: list[Path], destination: Path, mcp_configs:list[Path]|None=None) -> dict[str,Any]:
    if not roots or any(not root.is_dir() for root in roots):raise ValueError("explicit existing roots required")
    destination.mkdir(parents=True,exist_ok=True)
    latest=destination/"latest.json"
    previous={row["path"]:row for row in json.loads(latest.read_text(encoding="utf-8")).get("skills",[])} if latest.is_file() else {}
    rows=[];reused=0
    for root in roots:
        for path in sorted(root.iterdir()):
            if path.is_symlink() or not path.is_dir() or not (path/"SKILL.md").is_file():continue
            target=path/"SKILL.md";key=str(path.resolve());hash_=digest(target)
            if key in previous and previous[key].get("sha256")==hash_:
                row=previous[key];row.setdefault("security",lint_skill(path));reused+=1
            else:
                row={"path":key,"sha256":hash_,**_metadata(target),"security":lint_skill(path)}
            rows.append(row)
            if len(rows)>2000:raise ValueError("skill inventory limit exceeded")
    for row in rows:
        matching=[];terms=set(row["capability_terms"])
        for other in rows:
            if other is row:continue
            shared=terms & set(other["capability_terms"])
            if len(shared)>=3 and len(shared)/max(1,len(terms|set(other["capability_terms"])))>=.35:
                matching.append(other["name"])
        row["possible_overlap_not_equivalence"]=sorted(set(matching))
    now=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report={"schema_version":"1.0","scanned_at":now,"roots":[str(p.resolve()) for p in roots],
            "skill_count":len(rows),"reused_hash_cache":reused,"new_or_changed":len(rows)-reused,
            "missing_since_previous":[p for p in previous if p not in {r["path"] for r in rows}],"skills":rows,"mcp_servers":mcp_inventory(mcp_configs or [])}
    body=json.dumps(report,indent=2,ensure_ascii=False)+"\n"
    latest.write_text(body,encoding="utf-8")
    history=destination/"history";history.mkdir(exist_ok=True)
    (history/f"{now}-{uuid.uuid4().hex[:6]}.json").write_text(body,encoding="utf-8")
    cards=[]
    for row in rows:
        cards.append("<article><h2>"+html.escape(row["name"])+"</h2><p>"+html.escape(row["description"])+
                     "</p><small>"+html.escape(row["path"])+"</small><p>Possible overlap: "+
                     html.escape(", ".join(row["possible_overlap_not_equivalence"]))+"</p></article>")
    (destination/"index.html").write_text("<!doctype html><meta charset=\"utf-8\"><title>Skill catalog</title>"
       "<style>body{font:16px system-ui;max-width:900px;margin:auto;color:#173341;background:#f8fbfc}"
       "article{background:white;padding:1rem;margin:1rem 0;border:1px solid #cadbe0;border-radius:12px}</style>"
       "<h1>Installed Skill catalog</h1><input id=\"q\" placeholder=\"Filter skills\" aria-label=\"Filter skills\">"
       "<main>"+"".join(cards)+"</main><script>document.getElementById('q').oninput=e=>"
       "document.querySelectorAll('article').forEach(x=>x.hidden=!x.textContent.toLowerCase().includes(e.target.value.toLowerCase()))</script>",encoding="utf-8")
    return {k:report[k] for k in ("skill_count","reused_hash_cache","new_or_changed","missing_since_previous")}


def plan_operation(target: Path, roots: list[Path], destination: Path, action: str, install_root:Path|None=None) -> dict[str,Any]:
    target=_safe_target(target,roots)
    destination=_safe_destination(target,destination)
    if action not in {"backup","update","disable","install"}:raise ValueError("unknown action")
    security=lint_skill(target)
    if action=="install":
        if security["blocked"]:raise ValueError("skill install blocked by high-severity security findings")
        if install_root is None:raise ValueError("install requires an explicit install_root")
        install_root=install_root.resolve();install_root.mkdir(parents=True,exist_ok=True)
        if target==install_root or install_root in target.parents:raise ValueError("install root cannot contain source Skill")
    if action=="update":
        gitroot=subprocess.run(["git","-C",str(target),"rev-parse","--show-toplevel"],capture_output=True,text=True,check=True).stdout.strip()
        if Path(gitroot).resolve()!=target:raise ValueError("update requires a standalone clean skill Git repository")
        status=subprocess.run(["git","-C",str(target),"status","--porcelain"],capture_output=True,text=True,check=True).stdout
        if status:raise ValueError("uncommitted changes; update refused")
        remote=subprocess.run(["git","-C",str(target),"remote","get-url","origin"],capture_output=True,text=True,check=True).stdout.strip()
        if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?",remote):
            raise ValueError("update requires a GitHub HTTPS origin")
    destination.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex
    plan={"action":action,"target":str(target),"roots":[str(root.resolve()) for root in roots],
          "skill_sha256":digest(target/"SKILL.md"),"tree_sha256":_tree_digest(target),"token":token,"security":security,"install_root":str(install_root) if install_root else None}
    plans=destination/"plans";plans.mkdir(exist_ok=True)
    (plans/(token+".json")).write_text(json.dumps(plan,indent=2),encoding="utf-8")
    return plan


def apply_operation(destination: Path, token: str) -> dict[str,Any]:
    if not re.fullmatch(r"[a-f0-9]{32}",token):raise ValueError("invalid confirmation token")
    path=destination/"plans"/(token+".json")
    plan=json.loads(path.read_text(encoding="utf-8"))
    target=_safe_target(Path(plan["target"]),[Path(root) for root in plan["roots"]])
    destination=_safe_destination(target,destination)
    if (digest(target/"SKILL.md")!=plan["skill_sha256"] or _tree_digest(target)!=plan["tree_sha256"]):
        raise ValueError("skill changed after plan; replan")
    action=plan["action"]
    if action=="backup":
        folder=destination/"backups";folder.mkdir(exist_ok=True)
        archive=folder/(target.name+"-"+token+".zip")
        with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_DEFLATED) as z:
            for item in target.rglob("*"):
                if item.is_file() and not item.is_symlink():z.write(item,item.relative_to(target.parent))
        result={"backup":str(archive)}
    elif action=="disable":
        folder=destination/"trash";folder.mkdir(exist_ok=True)
        moved=folder/(target.name+"-"+token)
        shutil.move(str(target),str(moved))
        result={"disabled_to":str(moved),"recoverable":True}
    elif action=="update":
        # No arbitrary shell and no force; any remote change or conflict fails.
        gitroot=subprocess.run(["git","-C",str(target),"rev-parse","--show-toplevel"],capture_output=True,text=True,check=True).stdout.strip()
        status=subprocess.run(["git","-C",str(target),"status","--porcelain"],capture_output=True,text=True,check=True).stdout
        remote=subprocess.run(["git","-C",str(target),"remote","get-url","origin"],capture_output=True,text=True,check=True).stdout.strip()
        if Path(gitroot).resolve()!=target or status or not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?",remote):
            raise ValueError("target update conditions changed after plan")
        subprocess.run(["git","-C",str(target),"pull","--ff-only"],check=True)
        result={"updated":str(target)}
    elif action=="install":
        if lint_skill(target)["blocked"]:raise ValueError("skill changed to a blocked security state")
        install_root=Path(plan["install_root"]).resolve();install_root.mkdir(parents=True,exist_ok=True);installed=install_root/target.name
        if installed.exists():raise ValueError("installed Skill already exists; disable it or use a reviewed update")
        shutil.copytree(target,installed,symlinks=False);result={"installed":str(installed),"activated":True,"tree_sha256":_tree_digest(installed)}
    else:raise ValueError("unknown plan action")
    path.unlink()
    return result


def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("command",choices=("scan","plan","apply","lint"))
    p.add_argument("--root",action="append",type=Path,default=[])
    p.add_argument("--output-dir",type=Path);p.add_argument("--target",type=Path)
    p.add_argument("--action",choices=("backup","update","disable","install"));p.add_argument("--confirm-token")
    p.add_argument("--install-root",type=Path);p.add_argument("--mcp-config",action="append",type=Path,default=[])
    args=p.parse_args()
    if args.command in {"scan","plan","apply"} and not args.output_dir:p.error(f"{args.command} requires --output-dir")
    if args.command=="scan":result=scan(args.root,args.output_dir,args.mcp_config)
    elif args.command=="plan":
        if not args.target or not args.action:p.error("plan requires --target and --action")
        result=plan_operation(args.target,args.root,args.output_dir,args.action,args.install_root)
    elif args.command=="lint":
        if not args.target:p.error("lint requires --target")
        result=lint_skill(args.target)
    else:
        if not args.confirm_token:p.error("apply requires --confirm-token")
        result=apply_operation(args.output_dir,args.confirm_token)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
