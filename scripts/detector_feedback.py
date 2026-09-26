#!/usr/bin/env python3
"""Optional detector-feedback editing ledger with strict scientific preservation.

A user-supplied detector score may guide a bounded editorial pass. This tool
does not claim a detector is accurate or remove required AI-use disclosures.
It never auto-rewrites or certifies human authorship.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.revision_integrity import tokens, multiset_delta, sha256_file
    from scripts.manuscript_language import extract_text
    from scripts.academic_style import analyze_text
except ImportError:
    from revision_integrity import tokens, multiset_delta, sha256_file  # type: ignore
    from manuscript_language import extract_text  # type: ignore
    from academic_style import analyze_text  # type: ignore


def _style(path: Path) -> dict[str,Any]:
    report=analyze_text(extract_text(path))
    return {"word_count":report["word_count"],"errors":report["errors"],"warnings":report["warnings"],
            "formulaic_finding_count":report["formulaic_pattern_finding_count"],
            "located_findings":[{"line":item["line"],"guidance":item["guidance"],"excerpt":item["excerpt"]}
                                for item in report["formulaic_pattern_findings"][:30]]}


def prepare_revision(before: Path, feedback: dict[str,Any]) -> dict[str,Any]:
    if feedback.get("schema_version")!="1.0" or not feedback.get("detector_name") or not feedback.get("detector_version"):
        raise ValueError("detector name/version and schema_version 1.0 required")
    if feedback.get("direction") not in {"lower_is_better","higher_is_better"}:
        raise ValueError("explicit score direction required")
    initial=feedback.get("before")
    if not isinstance(initial,dict) or initial.get("sha256")!=sha256_file(before):
        raise ValueError("before detector report must be bound to the text hash")
    try:score=float(initial["score"])
    except (ValueError,TypeError,KeyError) as exc:raise ValueError("numeric score required") from exc
    if not 0<=score<=100:raise ValueError("score scale must be 0..100")
    return {"schema_version":"1.0","source_sha256":sha256_file(before),"detector":feedback["detector_name"],
            "detector_version":feedback["detector_version"],"score":score,"style":_style(before),
            "revision_instructions":["Edit only locally identified weak passages for precision, varied argument function and natural flow.",
                "Keep all evidence, numerical values, citations, uncertainty, unfavorable findings and AI-use disclosures.",
                "Re-run independent scientific review, revision integrity and venue compliance after editing."],
            "score_goal":"secondary feedback only; no guarantee of detector outcome or authorship",
            "author_review_required":True}


def evaluate(before: Path, after: Path, feedback: dict[str,Any]) -> dict[str,Any]:
    prepared=prepare_revision(before,feedback)
    initial,final=feedback.get("before"),feedback.get("after")
    if not isinstance(initial,dict) or not isinstance(final,dict):raise ValueError("before and after results required")
    if initial.get("sha256")!=sha256_file(before) or final.get("sha256")!=sha256_file(after):
        raise ValueError("detector report must be hash-bound to both texts")
    try:
        one,two=float(initial["score"]),float(final["score"])
    except (ValueError,TypeError,KeyError) as exc:raise ValueError("numeric scores required") from exc
    if not all(0<=n<=100 for n in (one,two)):raise ValueError("score scale must be 0..100")
    previous,current=tokens(before),tokens(after)
    changes={key:multiset_delta(previous[key],current[key]) for key in previous}
    protected=any(values[side] for values in changes.values() for side in ("added","removed"))
    improved=two<one if feedback["direction"]=="lower_is_better" else two>one
    style_after=_style(after)
    new_style_errors=sorted(set(style_after["errors"])-set(prepared["style"]["errors"]))
    return {"schema_version":"1.0","detector":feedback["detector_name"],"version":feedback["detector_version"],
            "before":one,"after":two,"score_improved":improved,"protected_token_changes":changes,
            "style_before":prepared["style"],"style_after":style_after,
            "new_style_errors":new_style_errors,
            "scientific_integrity_review_required":protected,"human_review_required":True,
            "accept_automatically":False,"disclosure_must_remain":True,
            "editing_brief":["Remove unsupported or formulaic language while preserving the exact claim and source.",
                "Vary only where it improves paragraph function, information flow and disciplinary precision.",
                "Do not spin synonyms, alter statistical meaning, omit negative results or remove AI-use disclosure."],
            "warning":"Detector score is not a reliable authorship verdict; lower score never overrides G5 evidence, integrity or disclosure."}


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before",type=Path,required=True);p.add_argument("--after",type=Path)
    p.add_argument("--feedback",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--prepare",action="store_true",help="produce a local line-level revision brief before editing")
    args=p.parse_args();feedback=json.loads(args.feedback.read_text(encoding="utf-8"))
    if not args.prepare and not args.after:p.error("--after is required unless --prepare is used")
    report=prepare_revision(args.before,feedback) if args.prepare else evaluate(args.before,args.after,feedback)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False));return 0


if __name__=="__main__":raise SystemExit(main())
