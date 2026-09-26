#!/usr/bin/env python3
"""Coverage-checked reviewer concern cards and venue-limited response drafts."""
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


STANCES={"accept","clarify","partial","disagree"}
IMPACT=("fatal","major","minor","editorial")


def triage(original: dict[str,Any], plan: dict[str,Any]) -> dict[str,Any]:
    comments=original.get("comments",[]);cards=plan.get("cards",[])
    if not isinstance(comments,list) or not isinstance(cards,list):raise ValueError("comments and cards must be arrays")
    ids=[str(c.get("comment_id","")) for c in comments]
    if not ids or len(set(ids))!=len(ids) or any(not item for item in ids):raise ValueError("unique original comment IDs required")
    card_ids=[str(c.get("comment_id","")) for c in cards]
    if len(card_ids)!=len(set(card_ids)) or set(card_ids)!=set(ids):
        raise ValueError("every original reviewer comment needs exactly one concern card")
    errors=[];ordered=sorted(cards,key=lambda c:(list(IMPACT).index(c.get("impact")) if c.get("impact") in IMPACT else 9,c.get("comment_id","")))
    for card in cards:
        cid=card.get("comment_id")
        if card.get("stance") not in STANCES or card.get("impact") not in IMPACT:errors.append(f"{cid}: invalid stance or impact")
        for field in ("underlying_concern","action","evidence_status","full_response","short_response","manuscript_location","effort"):
            if not str(card.get(field,"")).strip():errors.append(f"{cid}: {field} required")
        if card.get("stance")=="disagree" and not str(card.get("disagreement_evidence","")).strip():
            errors.append(f"{cid}: disagreement requires a defensible evidence citation")
    if errors:raise ValueError("; ".join(errors))
    budget=plan.get("venue_word_limit")
    if not isinstance(budget,int) or budget<100:raise ValueError("venue_word_limit must be at least 100")
    originals={c["comment_id"]:c for c in comments}
    header=str(plan.get("editor_summary","")).strip()
    if not header:raise ValueError("editor/Area Chair summary is required")
    extended=["# Internal full response", "", header, ""]
    short=["# Response to reviewers", "", header, ""]
    for card in ordered:
        item=originals[card["comment_id"]]
        reviewer=str(item.get("reviewer_id", "reviewer"))
        line=f"## {reviewer}, {card['comment_id']}"
        extended += [line,"",f"> {item.get('comment','')}","",card["full_response"],""]
        short += [line,"",card["short_response"],""]
    short_text="\n".join(short);count=len(re.findall(r"\b[\w'-]+\b",short_text))
    return {"schema_version":"1.0","comment_count":len(cards),"venue_word_limit":budget,
            "submitted_words":count,"within_limit":count<=budget,"full_text":"\n".join(extended),
            "short_text":short_text,"priority_order":[c["comment_id"] for c in ordered],
            "human_review_required":True,"note":"Evidence status is author supplied; revision-trace verifies commitments separately."}


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for field in ("project","paper","original","cards","output-dir"):
        p.add_argument("--"+field,required=True)
    args=p.parse_args();project=PROJECTS_ROOT/args.project
    base=f"papers/{args.paper}/reviews/"
    for name in (args.original,args.cards,args.output_dir):
        if not name.startswith(base):p.error("all inputs and outputs must be within the selected paper reviews folder")
    original=safe_file(project,args.original,"original");cards=safe_file(project,args.cards,"cards")
    report=triage(json.loads(original.read_text(encoding="utf-8")),json.loads(cards.read_text(encoding="utf-8")))
    output=safe_file(project,args.output_dir,"output-dir");output.mkdir(parents=True,exist_ok=True)
    (output/"internal-full.md").write_text(report.pop("full_text"),encoding="utf-8")
    (output/"submitted-short.md").write_text(report.pop("short_text"),encoding="utf-8")
    report["original_sha256"]=sha256_file(original);report["cards_sha256"]=sha256_file(cards)
    (output/"coverage.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2));return 0 if report["within_limit"] else 2


if __name__=="__main__":raise SystemExit(main())
