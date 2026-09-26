#!/usr/bin/env python3
"""Hash-bound screening ledger, PRISMA flow and interchange exports.

This is an execution layer over existing literature receipts. Only a named
human can make study-level inclusion/exclusion decisions. No pending decision
is silently converted to included or excluded.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

try:
    from scripts.publication_figures import PROJECTS_ROOT, safe_file, sha256_file
except ImportError:
    from publication_figures import PROJECTS_ROOT, safe_file, sha256_file  # type: ignore


MODES = {"quick": 1, "standard": 2, "deep": 3, "audit": 3}
STATES = {"include", "exclude", "pending"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _key(work: dict[str, Any]) -> str:
    doi = str(work.get("doi") or "").lower().removeprefix("https://doi.org/").strip()
    if doi:
        return "doi:"+doi
    title = re.sub(r"\W+", "", str(work.get("title", "")).casefold())
    year = str(work.get("year") or "")
    if not title:
        return "id:"+str(work.get("id"))
    return "title:"+title+":"+year


def verified_works(project: Path, receipt_ids: list[str]) -> tuple[list[dict[str, Any]], int]:
    ledger = {str(row.get("receipt_id")): row for row in _read_jsonl(project/"evidence"/"literature-api-ledger.jsonl")}
    found, unique = 0, {}
    if len(set(receipt_ids)) != len(receipt_ids):
        raise ValueError("duplicate receipt IDs")
    for receipt_id in receipt_ids:
        receipt = ledger.get(receipt_id)
        if not receipt or receipt.get("status") != "success":
            raise ValueError(f"missing or failed source receipt: {receipt_id}")
        path = safe_file(project, receipt["normalized_results_path"], "normalized_results_path")
        if sha256_file(path) != receipt.get("normalized_results_sha256"):
            raise ValueError(f"normalized results changed since receipt: {receipt_id}")
        works = json.loads(path.read_text(encoding="utf-8"))["works"]
        found += len(works)
        for work in works:
            key = _key(work)
            if key not in unique:
                unique[key] = {"work":work,"receipt_ids":[receipt_id]}
            else:
                unique[key]["receipt_ids"].append(receipt_id)
    return [dict(study_id=key, **item) for key,item in sorted(unique.items())], found


def seed(project: Path, receipt_ids: list[str], mode: str, criteria: str, actor: str,
         output: Path) -> dict[str, Any]:
    if mode not in MODES or not actor.strip() or not criteria.strip():
        raise ValueError("mode, named actor and predeclared inclusion criteria required")
    if len(receipt_ids) < MODES[mode]:
        raise ValueError(f"{mode} requires at least {MODES[mode]} executed source receipts")
    if output.exists():
        raise ValueError("refusing to overwrite existing screening decisions")
    works, found = verified_works(project, receipt_ids)
    value = {"schema_version":"1.0","mode":mode,"criteria":criteria,
             "seeded_by":actor,"receipt_ids":receipt_ids,"identified_count":found,
             "studies":[{**item,"title_abstract":{"decision":"pending","reason":"","reviewer":"","independent_reviews":[],"adjudication":{}},
                         "full_text":{"decision":"pending","reason":"","reviewer":"","evidence_location":"","independent_reviews":[],"adjudication":{}},
                         "comparison":{"method":"","population":"","outcome":"","estimate":"",
                                       "contradiction_group":"","limitations":""}} for item in works]}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {"identified":found,"deduplicated":len(works),"duplicates":found-len(works),
            "ledger":output.relative_to(project).as_posix()}


def _decision(item: dict[str, Any], stage: str, mode: str) -> str:
    value = item.get(stage)
    allowed = STATES | ({"not_retrieved"} if stage == "full_text" else set())
    if not isinstance(value,dict) or value.get("decision") not in allowed:
        raise ValueError(f"{item.get('study_id')}: {stage} needs a valid decision")
    choice = value["decision"]
    if choice != "pending" and (not str(value.get("reviewer","")).strip() or
                                choice in {"exclude", "not_retrieved"} and not str(value.get("reason","")).strip()):
        raise ValueError(f"{item.get('study_id')}: {stage} needs a reviewer and exclusion reason")
    if stage == "full_text" and choice == "include" and not str(value.get("evidence_location","")).strip():
        raise ValueError(f"{item.get('study_id')}: included full text needs an exact evidence location")
    if mode in {"deep", "audit"} and choice != "pending":
        reviews = value.get("independent_reviews")
        if not isinstance(reviews, list) or len(reviews) != 2:
            raise ValueError(f"{item.get('study_id')}: {stage} needs two independent screening decisions")
        names = [str(review.get("reviewer", "")).strip() for review in reviews if isinstance(review, dict)]
        decisions = [review.get("decision") for review in reviews if isinstance(review, dict)]
        if len(names) != 2 or not all(names) or names[0] == names[1] or any(decision not in allowed-{"pending"} for decision in decisions):
            raise ValueError(f"{item.get('study_id')}: {stage} requires two named, distinct stage decisions")
        if any(review["decision"] in {"exclude", "not_retrieved"} and not str(review.get("reason", "")).strip() for review in reviews):
            raise ValueError(f"{item.get('study_id')}: {stage} each exclusion needs a reason")
        if decisions[0] == decisions[1]:
            if choice != decisions[0] or value["reviewer"] not in names:
                raise ValueError(f"{item.get('study_id')}: {stage} final decision must match the independent agreement")
        else:
            adjudication = value.get("adjudication")
            if (not isinstance(adjudication, dict) or
                    str(adjudication.get("reviewer", "")).strip() in {"", *names} or
                    adjudication.get("decision") != choice or
                    not str(adjudication.get("reason", "")).strip() or
                    value["reviewer"] != adjudication["reviewer"]):
                raise ValueError(f"{item.get('study_id')}: {stage} disagreement needs a third named adjudicator and rationale")
    return choice


def assess(project: Path, ledger_path: Path) -> dict[str, Any]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("schema_version")!="1.0" or ledger.get("mode") not in MODES:
        raise ValueError("invalid systematic review ledger")
    current, found = verified_works(project, ledger["receipt_ids"])
    studies = ledger.get("studies")
    if not isinstance(studies,list) or {s.get("study_id") for s in studies}!={s["study_id"] for s in current} or len(studies)!=len(current):
        raise ValueError("study identities no longer match verified receipts")
    original = {s["study_id"]:s for s in current}
    screened=excluded_title=fulltext=not_retrieved=excluded_full=included=pending=0
    reasons=Counter()
    for item in studies:
        seed_item=original[item["study_id"]]
        if item.get("work")!=seed_item["work"] or item.get("receipt_ids")!=seed_item["receipt_ids"]:
            raise ValueError(f"study source metadata changed: {item['study_id']}")
        title = _decision(item,"title_abstract",ledger["mode"])
        if title=="pending":
            if item.get("full_text",{}).get("decision")!="pending":
                raise ValueError(f"{item['study_id']}: full text cannot be decided before title/abstract")
            pending+=1;continue
        screened+=1
        if title=="exclude":
            if item.get("full_text",{}).get("decision")!="pending":
                raise ValueError(f"{item['study_id']}: full text cannot be decided after title/abstract exclusion")
            excluded_title+=1;reasons[str(item["title_abstract"]["reason"])]+=1;continue
        fulltext+=1
        full = _decision(item,"full_text",ledger["mode"])
        if full=="pending":pending+=1
        elif full=="not_retrieved":not_retrieved+=1
        elif full=="exclude":
            excluded_full+=1;reasons[str(item["full_text"]["reason"])]+=1
        else:
            if ledger["mode"] in {"deep", "audit"}:
                comparison = item.get("comparison") or {}
                if any(not str(comparison.get(key, "")).strip() for key in ("method", "population", "outcome", "limitations")):
                    raise ValueError(f"{item['study_id']}: deep/audit inclusion needs a method, population, outcome and limitations comparison")
            included+=1
    return {"schema_version":"1.0","mode":ledger["mode"],"ledger_sha256":sha256_file(ledger_path),
            "identified":found,"duplicates_removed":found-len(studies),"unique":len(studies),
            "title_abstract_screened":screened,"title_abstract_excluded":excluded_title,
            "full_text_sought":fulltext,"reports_not_retrieved":not_retrieved,
            "reports_assessed":excluded_full+included,
            "full_text_excluded":excluded_full,"included":included,
            "pending_decisions":pending,"complete":pending==0,"exclusion_reasons":dict(sorted(reasons.items())),
            "search_receipt_ids":ledger["receipt_ids"],
            "screening_method":"dual independent + third adjudicator on conflict" if ledger["mode"] in {"deep","audit"} else "named single screening",
            "warning":"PRISMA-style accounting; one normalized work is treated as one record/report. Multi-report studies, registration/protocol, complete search strategy and risk-of-bias require author reconciliation."}


def _svg(counts: dict[str, Any]) -> str:
    cells = [("Records identified",counts["identified"]),("Duplicates removed",counts["duplicates_removed"]),
             ("Title/abstract screened",counts["title_abstract_screened"]),
             ("Title/abstract excluded",counts["title_abstract_excluded"]),
             ("Full text sought",counts["full_text_sought"]),("Reports not retrieved",counts["reports_not_retrieved"]),
             ("Reports assessed",counts["reports_assessed"]),("Full text excluded",counts["full_text_excluded"]),
             ("Studies included",counts["included"]),("Unresolved decisions",counts["pending_decisions"])]
    canvas_height=80+len(cells)*85
    lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="620" height="{canvas_height}" viewBox="0 0 620 {canvas_height}">',
           f'<rect width="620" height="{canvas_height}" fill="white"/>',
           '<text x="310" y="32" text-anchor="middle" font-size="19" fill="#173341">PRISMA-style screening flow</text>']
    for index,(label,number) in enumerate(cells):
        y=55+index*85
        lines += [f'<rect x="120" y="{y}" width="380" height="60" rx="9" fill="#E8F2F4" stroke="#426775"/>',
                  f'<text x="310" y="{y+25}" text-anchor="middle" font-size="13" fill="#173341">{escape(label)}</text>',
                  f'<text x="310" y="{y+47}" text-anchor="middle" font-size="17" fill="#173341">{number}</text>']
        if index<len(cells)-1:
            lines.append(f'<path d="M310,{y+60} V{y+85}" stroke="#426775" stroke-width="2"/>')
    lines.append('</svg>')
    return "\n".join(lines)


def _bib_escape(value: Any) -> str:
    return str(value or "").replace("\\","\\textbackslash{}").replace("{","\\{").replace("}","\\}").replace("%","\\%")


def export(project: Path, ledger_path: Path, output_dir: Path) -> dict[str, Any]:
    report=assess(project,ledger_path)
    data=json.loads(ledger_path.read_text(encoding="utf-8"))
    selected=[s for s in data["studies"] if s["title_abstract"]["decision"]=="include" and s["full_text"]["decision"]=="include"]
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/"prisma.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (output_dir/"prisma.svg").write_text(_svg(report),encoding="utf-8")
    (output_dir/"included.json").write_text(json.dumps(selected,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    source_receipts = {str(row.get("receipt_id")): row for row in _read_jsonl(project/"evidence"/"literature-api-ledger.jsonl")}
    search_log = [{key: source_receipts[receipt_id].get(key) for key in
                   ("receipt_id", "provider", "query", "query_family", "date_range", "filters", "request_url", "retrieved_at", "status", "normalized_results_sha256")}
                  for receipt_id in data["receipt_ids"]]
    (output_dir/"search-strategy.json").write_text(json.dumps({"criteria":data["criteria"],"source_receipts":search_log,
        "manual_PRISMA_S_check_required":True},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    checklist={"schema_version":"1.0","not_a_completed_reporting_checklist":True,
               "PRISMA_2020_reference":"https://www.prisma-statement.org/prisma-2020-checklist",
               "PRISMA_S_reference":"https://www.prisma-statement.org/prisma-search",
               "PRISMA_2020":[{"item_number":str(n),"status":"author-review-needed","manuscript_location":""} for n in range(1,28)],
               "PRISMA_S":[{"item_number":str(n),"status":"author-review-needed","manuscript_location":""} for n in range(1,17)]}
    (output_dir/"reporting-checklist-template.json").write_text(json.dumps(checklist,indent=2)+"\n",encoding="utf-8")
    headers=["study_id","title","year","doi","source","evidence_location","method","population","outcome","estimate","contradiction_group","limitations"]
    with (output_dir/"comparison-matrix.csv").open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=headers);writer.writeheader()
        for item in selected:
            work=item["work"];comparison=item.get("comparison") or {}
            writer.writerow({"study_id":item["study_id"],"title":work.get("title"),"year":work.get("year"),
                "doi":work.get("doi"),"source":work.get("source"),"evidence_location":item["full_text"]["evidence_location"],
                **{field:comparison.get(field,"") for field in headers[6:]}})
    bib=[];ris=[];rows=[]
    for index,item in enumerate(selected,1):
        work=item["work"];key=f"review{index}"
        bib.append(f"@article{{{key},\n  title = {{{_bib_escape(work.get('title'))}}},\n  year = {{{_bib_escape(work.get('year'))}}},\n  doi = {{{_bib_escape(work.get('doi'))}}}\n}}")
        ris.extend(["TY  - JOUR",f"TI  - {work.get('title','')}",f"PY  - {work.get('year','')}",f"DO  - {work.get('doi','')}","ER  - ",""])
        rows.append(f"<tr><td>{html.escape(str(work.get('title','')))}</td><td>{html.escape(str(work.get('year','')))}</td><td>{html.escape(str(work.get('doi','')))}</td></tr>")
    (output_dir/"included.bib").write_text("\n\n".join(bib)+"\n",encoding="utf-8")
    (output_dir/"included.ris").write_text("\n".join(ris),encoding="utf-8")
    (output_dir/"report.html").write_text("<!doctype html><meta charset=\"utf-8\"><h1>Screening report</h1>"+
        f"<p>Complete: {report['complete']}; included: {report['included']}; pending: {report['pending_decisions']}</p>"+
        "<table><tr><th>Title</th><th>Year</th><th>DOI</th></tr>"+"".join(rows)+"</table>",encoding="utf-8")
    return {**report,"files":[p.relative_to(project).as_posix() for p in sorted(output_dir.iterdir()) if p.is_file()]}


def main()->int:
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest="command",required=True)
    s=sub.add_parser("seed");s.add_argument("--project",required=True);s.add_argument("--receipt",action="append",required=True)
    s.add_argument("--mode",choices=sorted(MODES),required=True);s.add_argument("--criteria",required=True);s.add_argument("--actor",required=True)
    s.add_argument("--output",default="evidence/systematic/screening.json")
    r=sub.add_parser("report");r.add_argument("--project",required=True)
    r.add_argument("--ledger",default="evidence/systematic/screening.json");r.add_argument("--output-dir",default="evidence/systematic/report")
    args=p.parse_args();project=PROJECTS_ROOT/args.project
    if args.command=="seed":result=seed(project,args.receipt,args.mode,args.criteria,args.actor,safe_file(project,args.output,"output"))
    else:result=export(project,safe_file(project,args.ledger,"ledger"),safe_file(project,args.output_dir,"output-dir"))
    print(json.dumps(result,indent=2,ensure_ascii=False));return 0


if __name__=="__main__":raise SystemExit(main())
