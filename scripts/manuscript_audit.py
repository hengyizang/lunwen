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
MATH_BLOCK=re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$|\\\(.*?\\\)|\\\[.*?\\\]",re.S)
MATH_TOKEN=re.compile(r"\\[A-Za-z]+|[A-Za-z]")
GREEK={"alpha","beta","gamma","delta","epsilon","varepsilon","zeta","eta","theta","vartheta","iota","kappa","lambda","mu","nu","xi","pi","varpi","rho","varrho","sigma","varsigma","tau","upsilon","phi","varphi","chi","psi","omega"}
RESULT_STATUSES={"supported","partially_supported","not_supported","contradicted","inconclusive"}
INFERENCE_LEVELS={"descriptive":0,"association":1,"prediction":2,"causal":3,"mechanism":4}


def _nonempty(item: dict[str, Any], fields: tuple[str, ...], errors: list[str], prefix: str)->None:
    for field in fields:
        if not str(item.get(field,"")).strip():errors.append(f"{prefix}.{field} is required")

def _section_key(heading:str)->str|None:
    value=re.sub(r"[^a-z ]+"," ",heading.lower())
    if "abstract" in value:return "abstract"
    if any(x in value for x in ("research question","objective","aim","introduction")):return "question"
    if any(x in value for x in ("result","finding","analysis")):return "results"
    if any(x in value for x in ("conclusion","discussion")):return "conclusion"
    return None


def _tex_regions(raw):
    regions=[]
    for pattern,key in ((r"\\title\s*\{([^{}]+)\}","title"),(r"\\begin\{abstract\}(.*?)\\end\{abstract\}","abstract")):
        match=re.search(pattern,raw,re.S)
        if match:regions.append((key,match.start(1),match.end(1)))
    markers=list(re.finditer(r"\\(?:section|subsection)\*?\{([^{}]+)\}",raw,re.S))
    for i,marker in enumerate(markers):
        key=_section_key(marker.group(1))
        if key:regions.append((key,marker.end(),markers[i+1].start() if i+1<len(markers) else len(raw)))
    return regions
def _section_buckets(manuscript:Path,raw:str|None=None)->dict[str,str]:
    buckets={key:"" for key in SECTION};suffix=manuscript.suffix.lower()
    if suffix==".tex":
        if raw is None:
            try:from scripts.tex_sources import expand
            except ModuleNotFoundError:from tex_sources import expand
            raw=expand(manuscript).text
        for key,start,end in _tex_regions(raw):buckets[key]+="\n"+raw[start:end]
    elif suffix in {".md",".markdown"}:
        raw=manuscript.read_text(encoding="utf-8");markers=list(re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$",raw))
        for i,marker in enumerate(markers):
            key="title" if i==0 and marker.group(0).startswith("# ") else _section_key(marker.group(1));end=markers[i+1].start() if i+1<len(markers) else len(raw)
            if key:buckets[key]+="\n"+marker.group(1)+"\n"+raw[marker.end():end]
    elif suffix==".docx":
        try:
            from docx import Document
            current=None
            for paragraph in Document(manuscript).paragraphs:
                content=paragraph.text.strip();style=str(paragraph.style.name or "").lower()
                if not content:continue
                if "title" in style and not buckets["title"]:buckets["title"]=content;current=None;continue
                if "heading" in style:current=_section_key(content);continue
                if current:buckets[current]+="\n"+content
        except (ImportError,OSError,ValueError):pass
    return buckets


def audit(project: Path, manuscript: Path, spec: Path) -> dict[str, Any]:
    config=json.loads(spec.read_text(encoding="utf-8"))
    text=extract_text(manuscript)
    expanded=None
    if manuscript.suffix.lower()==".tex":
        try:from scripts.tex_sources import expand
        except ModuleNotFoundError:from tex_sources import expand
        expanded=expand(manuscript)
    symbol_text=expanded.text if expanded else text
    section_buckets=_section_buckets(manuscript,symbol_text if expanded else None)
    source_locations=[]
    errors=[]; warnings=[]; fact_ids=set();claim_ids=set()
    if config.get("schema_version")!="1.0":errors.append("schema_version must be 1.0")
    for name in ("facts", "claim_alignment", "measurement", "argument_ledger", "glossary", "symbols"):
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
        _nonempty(link,("claim_id","research_question","canonical_claim","allowed_inference","claim_strength","result_status","evidence_ids"),errors,"alignment")
        allowed=str(link.get("allowed_inference","")).lower();strength=str(link.get("claim_strength","")).lower()
        if allowed not in INFERENCE_LEVELS:errors.append(f"{identifier}: invalid allowed_inference")
        if strength not in INFERENCE_LEVELS:errors.append(f"{identifier}: invalid claim_strength")
        elif allowed in INFERENCE_LEVELS and INFERENCE_LEVELS[strength]>INFERENCE_LEVELS[allowed]:errors.append(f"{identifier}: claim_strength exceeds allowed_inference")
        if link.get("result_status") not in RESULT_STATUSES:errors.append(f"{identifier}: invalid result_status")
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
                if not str(phrase).strip():errors.append(f"{identifier}: {section} needs a non-empty anchor")
                elif not section_buckets.get(section):errors.append(f"{identifier}: cannot locate the manuscript {section} region")
                elif phrase not in section_buckets[section]:errors.append(f"{identifier}: {section} anchor is outside the declared manuscript region")
                elif expanded:
                    for key,start,end in _tex_regions(expanded.text):
                        if key==section:
                            for match in re.finditer(re.escape(phrase),expanded.text[start:end]):
                                source_locations.append({"claim_id":identifier,"section":section,**expanded.locate(start+match.start())})
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
    declared=set()
    for entry in config.get("symbols",[]):
        _nonempty(entry,("symbol","definition","first_use","unit"),errors,"symbol");symbol=str(entry.get("symbol","")).strip();first=str(entry.get("first_use","")).strip()
        if not re.fullmatch(r"(?:\\[A-Za-z]+|[A-Za-z])",symbol):errors.append(f"symbol {symbol!r}: use one canonical Latin or LaTeX Greek token");continue
        if symbol in declared:errors.append(f"duplicate symbol definition: {symbol}")
        declared.add(symbol)
        if first and first not in symbol_text:errors.append(f"symbol {symbol}: first-use definition not found")
        for variant in entry.get("forbidden_variants",[]):
            if str(variant) and str(variant) in symbol_text:errors.append(f"symbol {symbol}: inconsistent variant {variant!r}")
    ignored_symbols=config.get("ignored_symbols",[])
    if not isinstance(ignored_symbols,list) or any(not isinstance(x,str) for x in ignored_symbols):errors.append("ignored_symbols must be an array of canonical symbol tokens");ignored_symbols=[]
    used=set()
    blocks=MATH_BLOCK.findall(symbol_text)
    blocks.extend(match.group(2) for match in re.finditer(r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}(.*?)\\end\{\1\}",symbol_text,re.S))
    for block in blocks:
        block=re.sub(r"\\(?:text|textrm|operatorname)\s*\{[^{}]*\}","",block)
        used.update(token for token in MATH_TOKEN.findall(block) if not token.startswith("\\") or token[1:].lower() in GREEK)
    undeclared=sorted(used-declared-set(ignored_symbols)-{"e","i"})
    if undeclared:errors.append("undeclared mathematical symbols: "+", ".join(undeclared))
    unused=sorted(declared-used)
    if unused:warnings.append("declared symbols not found in a math expression: "+", ".join(unused))
    contribution_review = {"status": "not_assessed", "errors": [], "semantic_support_verified": False}
    relative = spec.relative_to(project).parts
    if len(relative) >= 3 and relative[0] == "papers" and re.fullmatch(r"P[0-9]{2}", relative[1]):
        try:
            from scripts.contribution_reporting import audit as audit_contributions
        except ImportError:
            from contribution_reporting import audit as audit_contributions
        contribution_review = audit_contributions(project, relative[1], config)
        # Legacy source-only checks stay diagnostic; the final G5 validator below
        # requires every current claim to have explicit contribution evidence.
        if any("contribution_detail" in row for row in config.get("claim_alignment", [])):
            errors.extend("contribution: " + item for item in contribution_review["errors"])
    return {"schema_version":"1.0","manuscript_sha256":manuscript_digest(manuscript),
            "spec_sha256":sha256_file(spec),"fact_count":len(fact_ids),"claim_count":len(claim_ids),
            "measurement_chains":len(config.get("measurement",[])),"paragraphs":len(config.get("argument_ledger",[])),
            "symbol_count":len(declared),"used_math_symbols":sorted(used),"section_regions_found":sorted(k for k,v in section_buckets.items() if v.strip()),"source_locations":source_locations,"errors":errors,"warnings":warnings,"pass":not errors,
            "human_review_required":True,"contribution_reporting":contribution_review}


def validate_saved_report(paper: Path) -> list[str]:
    """Require and recompute the full fact/alignment/measurement/symbol audit at G5."""
    spec=paper/"reviews"/"paper-facts.json"
    output=paper/"reviews"/"manuscript-audit.json"
    if not spec.is_file() or not output.is_file():return ["paper-facts input and manuscript audit must both exist"]
    try:
        current=audit(paper.parent.parent,canonical_manuscript(paper),spec)
        saved=json.loads(output.read_text(encoding="utf-8"))
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:
        return [f"cannot validate paper-facts audit: {exc}"]
    errors=[]
    if not current["pass"]:errors.extend(current["errors"])
    if current["contribution_reporting"]["status"] != "ready_for_scientific_review":
        errors.extend("contribution reporting: " + item for item in current["contribution_reporting"].get("errors", []))
        if not current["contribution_reporting"].get("errors"):
            errors.append("current contribution reporting is not assessed")
    for key in ("manuscript_sha256","spec_sha256","errors","fact_count","claim_count","measurement_chains","paragraphs","symbol_count","used_math_symbols","section_regions_found","source_locations","contribution_reporting"):
        if saved.get(key)!=current.get(key):errors.append(f"stale paper-facts audit field: {key}")
    return errors


def refresh(project: Path, paper_id: str) -> dict[str, Any]:
    """Use the existing protected paper audit after initial writing/remediation."""
    if not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("an explicit paper ID is required")
    paper = project / "papers" / paper_id
    spec = paper / "reviews/paper-facts.json"
    if not spec.is_file():
        return {"status": "input_missing", "required": str(spec.relative_to(project)), "pass": False}
    report = audit(project, canonical_manuscript(paper), spec)
    report["pass"] = report["pass"] and report["contribution_reporting"]["status"] == "ready_for_scientific_review"
    from scripts.research_artifacts import write, record
    target = paper / "reviews/manuscript-audit.json"
    write(target, report)
    record(project, [target], "scripts/manuscript_audit.py")
    return {"path": target.relative_to(project).as_posix(), "sha256": sha256_file(target),
            "pass": report["pass"], "status": report["contribution_reporting"]["status"],
            "errors": report["errors"] + report["contribution_reporting"]["errors"]}


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
