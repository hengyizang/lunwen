#!/usr/bin/env python3
"""Read-only local Zotero/Obsidian/PDF index with content hashes and wiki links.

An explicit local folder is read, never uploaded or copied. The index is a lead
for further checking; a citation or scientific claim still needs full evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import hashlib
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from scripts.publication_figures import PROJECTS_ROOT, safe_file, sha256_file
except ImportError:
    from publication_figures import PROJECTS_ROOT, safe_file, sha256_file  # type: ignore


EXTENSIONS = {".pdf", ".md", ".json", ".bib"}
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def _record(path: Path, root: Path, fmt: str) -> dict[str, Any]:
    row={"relative_path":path.relative_to(root).as_posix(),"format":fmt,
         "size_bytes":path.stat().st_size,"sha256":sha256_file(path),"title":path.stem,
         "doi":None,"full_text_checked":False}
    if fmt==".pdf":return row
    content=path.read_text(encoding="utf-8-sig",errors="replace")
    match=DOI_RE.search(content[:100_000])
    if match:row["doi"]=match.group(0).rstrip(".,;)")
    if fmt==".md":
        title=re.search(r"(?m)^#\s+(.+)$",content[:20_000])
        if title:row["title"]=title.group(1).strip()
        row["obsidian_links"]=sorted(set(re.findall(r"\[\[([^\]]{1,150})\]\]",content)))[:200]
    elif fmt==".json":
        try:value=json.loads(content)
        except json.JSONDecodeError:
            row["parse_warning"]="invalid JSON; kept as hash-bound file only";return row
        items=value.get("items",[]) if isinstance(value,dict) else value if isinstance(value,list) else []
        row["zotero_items"] = len(items) if isinstance(items,list) else 0
        if isinstance(items,list):
            row["bibliographic_items"]=[{"title":str(data.get("title", ""))[:400],
                "doi":str(data.get("DOI") or data.get("doi") or "")[:160],
                "year":str(data.get("date") or "")[:80]}
                for item in items[:500] if isinstance(item,dict)
                for data in [item.get("data",item)] if isinstance(data,dict) and data.get("title")]
    elif fmt==".bib":
        row["bib_entries"] = len(re.findall(r"@\w+\s*\{",content))
        parsed=[]
        for block in re.split(r"(?=@\w+\s*\{)",content):
            title_match=re.search(r"(?im)^\s*title\s*=\s*(.+?)(?:,\s*$|$)",block)
            if title_match:
                doi_match=DOI_RE.search(block)
                parsed.append({"title":title_match.group(1).strip("{} \n\""),
                               "doi":doi_match.group(0) if doi_match else ""})
            if len(parsed)>=500:break
        row["bibliographic_items"]=parsed
    return row


def index(source: Path, project: Path, actor: str, output: Path) -> dict[str, Any]:
    source=source.resolve()
    if not actor.strip() or not source.is_dir():
        raise ValueError("explicit existing folder and named actor required")
    files=[]
    for path in sorted(source.rglob("*")):
        if path.is_symlink():continue
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:continue
        if len(files)>=5000:raise ValueError("too many library files; split this source")
        if path.stat().st_size>100_000_000:continue
        files.append(_record(path,source,path.suffix.lower()))
    payload={"schema_version":"1.0","kind":"local-library-index","source_root":str(source),
             "indexed_by":actor.strip(),"file_count":len(files),"files":files,
             "caution":"Local metadata are leads; DOI and paper assertions need independent verification. No file was uploaded."}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    wiki=output.parent/"research-wiki.md"
    lines=["# Local research wiki index", "", f"Indexed files: {len(files)}", "",
           "Titles and DOIs below are unverified local leads. Open the original file before citing.", ""]
    for item in files:
        lines.append(f"- {item['title']} — DOI: {item['doi'] or 'not found'} — `{item['relative_path']}` — SHA-256: `{item['sha256']}`")
        for work in item.get("bibliographic_items",[]):
            lines.append(f"  - {work['title']} — DOI: {work.get('doi') or 'not found'} (unverified)")
        if item.get("obsidian_links"):
            lines.append("  - Obsidian links: "+", ".join(item["obsidian_links"][:20]))
    wiki.write_text("\n".join(lines)+"\n",encoding="utf-8")
    return {"index":output.relative_to(project).as_posix(),"wiki":wiki.relative_to(project).as_posix(),
            "file_count":len(files),"no_upload":True}


def obsidian_graph(source: Path, project: Path, actor: str, output: Path) -> dict[str,Any]:
    result=index(source,project,actor,output)
    notes={path.relative_to(source).with_suffix("").as_posix():path for path in source.rglob("*.md") if path.is_file() and not path.is_symlink()}
    stems={path.stem:key for key,path in notes.items()};edges=[];missing=[];tags={}
    for key,path in sorted(notes.items()):
        content=path.read_text(encoding="utf-8-sig",errors="replace");tags[key]=sorted(set(re.findall(r"(?<!\w)#([A-Za-z][\w/-]{1,80})",content)))
        for target in sorted(set(re.findall(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]",content))):
            normalized=target.strip().replace("\\","/").removesuffix(".md");destination=normalized if normalized in notes else stems.get(Path(normalized).name)
            (edges if destination else missing).append({"from":key,"to":destination} if destination else {"from":key,"target":target.strip()})
    linked={edge["from"] for edge in edges}|{edge["to"] for edge in edges}
    graph={"schema_version":"1.0","kind":"obsidian-graph","indexed_by":actor,"source_root":str(source.resolve()),"nodes":sorted(notes),"edges":edges,"tags":tags,"orphan_notes":sorted(set(notes)-linked),"missing_links":missing,"no_upload":True}
    graph_path=output.parent/"obsidian-graph.json";graph_path.write_text(json.dumps(graph,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {**result,"graph":graph_path.relative_to(project).as_posix(),"notes":len(notes),"links":len(edges),"missing_links":len(missing)}


def zotero_local(project: Path, actor: str, output: Path, *, limit: int=100, opener: Any=urllib.request.urlopen)->dict[str,Any]:
    if not actor.strip() or not 1<=limit<=100:raise ValueError("named actor and Zotero page limit 1..100 required")
    items=[];start=0
    while len(items)<5000:
        query=urllib.parse.urlencode({"format":"json","limit":limit,"start":start});request=urllib.request.Request("http://127.0.0.1:23119/api/users/0/items?"+query,headers={"Zotero-API-Version":"3","Accept":"application/json"})
        try:
            with opener(request,timeout=15) as response:payload=response.read(8*1024*1024+1)
        except OSError as exc:raise ValueError(f"Zotero Local API unavailable: {exc}") from exc
        if len(payload)>8*1024*1024:raise ValueError("Zotero Local API page exceeded 8 MiB")
        try:page=json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise ValueError("Zotero Local API returned invalid JSON") from exc
        if not isinstance(page,list):raise ValueError("Zotero Local API items response must be an array")
        items.extend(page)
        if len(page)<limit:break
        start+=len(page)
    if len(items)>=5000:raise ValueError("Zotero import reached 5000 items; narrow the library first")
    canonical=json.dumps(items,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode();normalized=[]
    for item in items:
        if not isinstance(item,dict):continue
        data=item.get("data") if isinstance(item.get("data"),dict) else item;creators=data.get("creators",[]) if isinstance(data,dict) else []
        normalized.append({"key":str(item.get("key") or data.get("key") or ""),"item_type":str(data.get("itemType") or ""),"title":str(data.get("title") or ""),"doi":str(data.get("DOI") or ""),"date":str(data.get("date") or ""),"url":str(data.get("url") or ""),"creators":[" ".join(str(c.get(k,"")) for k in ("firstName","lastName")).strip() for c in creators if isinstance(c,dict)]})
    payload={"schema_version":"1.0","kind":"zotero-local-api","indexed_by":actor.strip(),"endpoint":"http://127.0.0.1:23119/api/","item_count":len(normalized),"response_sha256":hashlib.sha256(canonical).hexdigest(),"items":normalized,"read_only":True,"no_cloud_key_used":True,"full_text_checked":False}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"index":output.relative_to(project).as_posix(),"item_count":len(normalized),"response_sha256":payload["response_sha256"],"read_only":True}


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True);p.add_argument("--source",type=Path)
    p.add_argument("--kind",choices=("folder","obsidian","zotero-local"),default="folder")
    p.add_argument("--actor",required=True);p.add_argument("--output",default="evidence/local-library/index.json")
    args=p.parse_args();project=PROJECTS_ROOT/args.project;output=safe_file(project,args.output,"output")
    if args.kind=="zotero-local":result=zotero_local(project,args.actor,output)
    else:
        if not args.source:p.error("--source is required for folder or obsidian imports")
        result=obsidian_graph(args.source,project,args.actor,output) if args.kind=="obsidian" else index(args.source,project,args.actor,output)
    print(json.dumps(result,indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
