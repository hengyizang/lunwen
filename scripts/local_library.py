#!/usr/bin/env python3
"""Read-only local Zotero/Obsidian/PDF index with content hashes and wiki links.

An explicit local folder is read, never uploaded or copied. The index is a lead
for further checking; a citation or scientific claim still needs full evidence.
"""
from __future__ import annotations

import argparse
import json
import re
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


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True);p.add_argument("--source",type=Path,required=True)
    p.add_argument("--actor",required=True);p.add_argument("--output",default="evidence/local-library/index.json")
    args=p.parse_args();project=PROJECTS_ROOT/args.project
    print(json.dumps(index(args.source,project,args.actor,safe_file(project,args.output,"output")),indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
