#!/usr/bin/env python3
"""Verify located paper facts, measurement chains, argument and terminology.

These checks identify gaps; they cannot determine whether a theory is valid or
whether an author's interpretation is scientifically persuasive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.publication_figures import PROJECTS_ROOT, safe_file, sha256_file
    from scripts.manuscript_language import extract_text
    from scripts.ref_verify_adapter import canonical_manuscript
    from scripts.citation_audit import manuscript_digest
except ImportError:
    from publication_figures import PROJECTS_ROOT, safe_file, sha256_file  # type: ignore
    from manuscript_language import extract_text  # type: ignore
    from ref_verify_adapter import canonical_manuscript  # type: ignore
    from citation_audit import manuscript_digest  # type: ignore


ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,7}s?\b")
SECTION = {"title","abstract","question","results","conclusion"}


def _nonempty(item: dict[str, Any], fields: tuple[str, ...], errors: list[str], prefix: str)->None:
    for field in fields:
        if not str(item.get(field,"")).strip():errors.append(f"{prefix}.{field} is required")


def audit(project: Path, manuscript: Path, spec: Path) -> dict[str, Any]:
    config=json.loads(spec.read_text(encoding="utf-8"))
    text=extract_text(manuscript)
    errors=[]; warnings=[]; fact_ids=set();claim_ids=set()
    if config.get("schema_version")!="1.0":errors.append("schema_version must be 1.0")
    for name in ("facts", "claim_alignment", "measurement", "argument_ledger", "glossary"):
        if not isinstance(config.get(name), list):
            errors.append(f"{name} must be an array")
            config[name]=[]
        elif name in {"facts", "claim_alignment", "argument_ledger"} and not config[name]:
            errors.append(f"{name} cannot be empty")
        if any(not isinstance(row, dict) for row in config[name]):
            errors.append(f"{name} contains a non-object")
            config[name]=[row for row in config[name] if isinstance(row, dict)]
    if not config["measurement"] and not str(config.get("measurement_not_applicable_reason", "")).strip():
        errors.append("measurement requires a construct–measurement chain or a reason why it is not applicable")
    for fact in config.get("facts",[]):
        identifier=str(fact.get("id", ""))
        if identifier in fact_ids:errors.append(f"duplicate fact ID: {identifier}")
        fact_ids.add(identifier)
        _nonempty(fact,("id","statement","source_path","location","verbatim_evidence"),errors,"fact")
        try:
            path=safe_file(project,fact["source_path"],"fact source")
            if not path.is_file() or path.is_symlink():raise ValueError("missing or symlinked source")
            if fact.get("source_sha256") != sha256_file(path):errors.append(f"{identifier}: source hash changed")
            if path.suffix.lower() in {".tex",".txt",".md",".csv",".json"}:
                if fact["verbatim_evidence"] not in path.read_text(encoding="utf-8"):
                    errors.append(f"{identifier}: exact evidence is absent from source")
            else:
                warnings.append(f"{identifier}: location in PDF/image needs human visual verification")
        except (KeyError, OSError, ValueError) as exc:errors.append(f"{identifier}: {exc}")
    for link in config.get("claim_alignment",[]):
        identifier=str(link.get("claim_id",""))
        if identifier in claim_ids:errors.append(f"duplicate claim alignment: {identifier}")
        claim_ids.add(identifier)
        _nonempty(link,("claim_id","research_question","allowed_inference","evidence_ids"),errors,"alignment")
        evidence_ids=link.get("evidence_ids")
        if not isinstance(evidence_ids,list) or not evidence_ids or any(not isinstance(id_,str) for id_ in evidence_ids):
            errors.append(f"{identifier}: evidence_ids must be a nonempty array of fact IDs")
        elif not set(evidence_ids).issubset(fact_ids):errors.append(f"{identifier}: unknown fact IDs")
        locations=link.get("sections",{})
        if not isinstance(locations,dict) or not SECTION.issubset(locations):
            errors.append(f"{identifier}: title/abstract/question/results/conclusion locations required")
        else:
            for section, phrase in locations.items():
                if section not in SECTION:continue
                if phrase and phrase not in text:
                    errors.append(f"{identifier}: {section} anchor absent from manuscript")
                if not phrase:warnings.append(f"{identifier}: {section} does not explicitly state the claim")
    for chain in config.get("measurement",[]):
        _nonempty(chain,("construct_id","definition","operationalization","measurement_item",
                         "coding_rule","analysis_id","claim_id","validity_risk"),errors,"measurement")
        if chain.get("claim_id") not in claim_ids:errors.append(f"measurement {chain.get('construct_id')}: unknown claim")
        if not isinstance(chain.get("evidence_ids"),list) or not chain["evidence_ids"] or any(not isinstance(id_,str) for id_ in chain["evidence_ids"]):
            errors.append(f"measurement {chain.get('construct_id')}: evidence_ids must be a nonempty array of fact IDs")
        elif not set(chain["evidence_ids"]).issubset(fact_ids):errors.append(f"measurement {chain.get('construct_id')}: unknown fact")
    for para in config.get("argument_ledger",[]):
        _nonempty(para,("paragraph_id","section","function","claim_id","inference_boundary","transition"),errors,"paragraph")
        if para.get("claim_id") not in claim_ids:errors.append(f"paragraph {para.get('paragraph_id')}: unknown claim")
        if not isinstance(para.get("evidence_ids"),list) or not para["evidence_ids"] or any(not isinstance(id_,str) for id_ in para["evidence_ids"]):
            errors.append(f"paragraph {para.get('paragraph_id')}: evidence_ids must be a nonempty array of fact IDs")
        elif not set(para["evidence_ids"]).issubset(fact_ids):errors.append(f"paragraph {para.get('paragraph_id')}: unknown fact")
        anchor=para.get("text_anchor","")
        if anchor and anchor not in text:errors.append(f"paragraph {para.get('paragraph_id')}: text anchor absent")
    glossary=config.get("glossary",[])
    explained=set()
    for entry in glossary:
        _nonempty(entry,("term","definition","first_use"),errors,"glossary")
        term=str(entry.get("term",""));first=str(entry.get("first_use",""))
        if term in explained:errors.append(f"duplicate glossary term: {term}")
        explained.add(term)
        if first and first not in text:errors.append(f"glossary {term}: first-use definition not found")
        elif term and re.search(r"\b"+re.escape(term)+r"\b",text) and text.find(term)<text.find(first):
            warnings.append(f"glossary {term}: abbreviation appears before its listed definition")
        for variant in entry.get("forbidden_variants",[]):
            if re.search(r"\b"+re.escape(variant)+r"\b",text,flags=re.I):
                errors.append(f"glossary {term}: inconsistent variant {variant!r}")
    ignored={"PDF","DOI","DNA","AI","SCI","Q1","Q2","ROC","PR","CI","CSV","API","URL","GPU"}
    acronyms=set(ACRONYM.findall(text))-explained-ignored
    for acronym in sorted(acronyms):
        if len(re.findall(r"\b"+re.escape(acronym)+r"\b",text))>=2:
            warnings.append(f"unlisted acronym: {acronym}")
    return {"schema_version":"1.0","manuscript_sha256":manuscript_digest(manuscript),
            "spec_sha256":sha256_file(spec),"fact_count":len(fact_ids),"claim_count":len(claim_ids),
            "measurement_chains":len(config.get("measurement",[])),"paragraphs":len(config.get("argument_ledger",[])),
            "errors":errors,"warnings":warnings,"pass":not errors,
            "human_review_required":True}


def validate_saved_report(paper: Path) -> list[str]:
    """Check a present ledger at G5 without breaking older projects without it."""
    spec=paper/"reviews"/"paper-facts.json"
    output=paper/"reviews"/"manuscript-audit.json"
    if not spec.is_file() and not output.is_file():return []
    if not spec.is_file() or not output.is_file():return ["paper-facts input and manuscript audit must both exist"]
    try:
        current=audit(paper.parent.parent,canonical_manuscript(paper),spec)
        saved=json.loads(output.read_text(encoding="utf-8"))
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:
        return [f"cannot validate paper-facts audit: {exc}"]
    errors=[]
    if not current["pass"]:errors.extend(current["errors"])
    for key in ("manuscript_sha256","spec_sha256","errors","fact_count","claim_count","measurement_chains","paragraphs"):
        if saved.get(key)!=current.get(key):errors.append(f"stale paper-facts audit field: {key}")
    return errors


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True);p.add_argument("--paper",required=True)
    p.add_argument("--manuscript",required=True);p.add_argument("--spec",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args();root=PROJECTS_ROOT/a.project
    for rel in (a.manuscript,a.spec,a.output):
        if not rel.startswith(f"papers/{a.paper}/"):
            p.error("all paths must be inside the selected paper")
    report=audit(root,safe_file(root,a.manuscript,"manuscript"),safe_file(root,a.spec,"spec"))
    target=safe_file(root,a.output,"output");target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False));return 0 if report["pass"] else 2


if __name__=="__main__":raise SystemExit(main())
