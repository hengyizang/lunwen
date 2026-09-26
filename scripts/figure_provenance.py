#!/usr/bin/env python3
"""Record and validate deterministic, non-Claude final figure provenance."""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

try:
    from scripts import output_provenance
except ImportError:
    import output_provenance  # type: ignore


FIGURE_SUFFIXES={".png",".svg",".pdf",".eps",".tif",".tiff"}
FIGURE_TYPES={"data_chart","conceptual_diagram","conceptual_illustration"}


def _relative(project:Path,value:str,field:str)->tuple[Path,str]:
    candidate=Path(value)
    if candidate.is_absolute():raise ValueError(f"{field} must be project-relative")
    path=(project/candidate).resolve();root=project.resolve()
    if path==root or root not in path.parents:raise ValueError(f"{field} escapes the project")
    return path,path.relative_to(root).as_posix()


def _load_registry(path:Path)->dict[str,Any]:
    if not path.is_file():return {"schema_version":"1.0","figures":[]}
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict) or value.get("schema_version")!="1.0" or not isinstance(value.get("figures"),list):raise ValueError("unsupported figure provenance registry")
    return value


def _write(path:Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,delete=False) as handle:handle.write(payload);temporary=Path(handle.name)
    os.replace(temporary,path)


def record_figure(project:Path,paper_id:str,figure:str,figure_type:str,renderer:str,inputs:list[str],runs:list[str],config:str|None=None,language_checked_by:str="")->str:
    if not re.fullmatch(r"P[0-9]{2}",paper_id):raise ValueError("paper must look like P01")
    if figure_type not in FIGURE_TYPES-{"conceptual_illustration"}:raise ValueError("use record_generated_illustration for conceptual_illustration")
    if not language_checked_by.strip():raise ValueError("language_checked_by must identify the human who confirmed English figure text")
    figure_path,figure_rel=_relative(project,figure,"figure")
    renderer_path,renderer_rel=_relative(project,renderer,"renderer")
    if not figure_path.is_file() or figure_path.suffix.lower() not in FIGURE_SUFFIXES:raise ValueError("figure must be an existing supported figure file")
    expected_root=(project/"papers"/paper_id/"figures").resolve()
    if expected_root not in figure_path.parents:raise ValueError("figure must be inside the selected paper's figures directory")
    if not renderer_path.is_file():raise ValueError("renderer must be an existing local source file")
    origin=output_provenance.current_origin(project,renderer_path)
    if origin.get("status")!="tracked" or origin.get("family")=="anthropic":raise ValueError("renderer needs current Codex/local/human non-Claude provenance")
    input_records=[]
    for item in inputs:
        path,relative=_relative(project,item,"input")
        if not path.is_file():raise ValueError(f"figure input is missing: {relative}")
        input_records.append({"path":relative,"sha256":output_provenance.sha256_file(path)})
    if figure_type=="data_chart" and (not input_records or not runs):raise ValueError("data_chart needs at least one input and source run")
    config_record=None
    if config:
        config_path,config_rel=_relative(project,config,"config")
        if not config_path.is_file():raise ValueError("figure config is missing")
        config_origin=output_provenance.current_origin(project,config_path)
        if config_origin.get("status")!="tracked" or config_origin.get("family")=="anthropic":raise ValueError("figure config needs current Codex/local/human non-Claude provenance")
        config_record={"path":config_rel,"sha256":output_provenance.sha256_file(config_path)}
    registry_path=project/"papers"/paper_id/"figures"/"figure-provenance.json"
    registry=_load_registry(registry_path)
    timestamp=output_provenance.utc_now();record={"figure_path":figure_rel,"figure_type":figure_type,"renderer":{"path":renderer_rel,"sha256":output_provenance.sha256_file(renderer_path)},"config":config_record,"inputs":input_records,"source_run_ids":sorted(set(runs)),"output_sha256":output_provenance.sha256_file(figure_path),"deterministic":True,"generated_by":"local-tool","language_checked_by":language_checked_by.strip(),"language_checked_at":timestamp,"recorded_at":timestamp}
    registry["figures"]=[item for item in registry["figures"] if isinstance(item,dict) and item.get("figure_path")!=figure_rel]+[record]
    _write(registry_path,registry)
    output_provenance.record_model_writes(project,[figure_path,registry_path],family="other",provider="deterministic-local-renderer",model=renderer_rel,role="final-figure",run_id="figure-"+output_provenance.utc_now().replace(":","-"))
    return figure_rel


def record_generated_illustration(project:Path,paper_id:str,figure:str,source_record:str,
                                  checked_by:str,disclosure_location:str)->str:
    """Approve an explicitly illustrative image only after human visual inspection."""
    if not re.fullmatch(r"P[0-9]{2}",paper_id):raise ValueError("invalid paper ID")
    if not checked_by.strip() or not disclosure_location.strip():
        raise ValueError("named human review and AI-use disclosure location are required")
    path,relative=_relative(project,figure,"figure")
    source,source_rel=_relative(project,source_record,"source_record")
    if not path.is_file() or path.suffix.lower() not in {".png",".tif",".tiff"} or not source.is_file():
        raise ValueError("generated illustration and source receipt must exist")
    if (project/"papers"/paper_id/"figures").resolve() not in path.parents:
        raise ValueError("generated illustration must be in the paper's figures directory")
    receipt=json.loads(source.read_text(encoding="utf-8"))
    if receipt.get("kind")!="conceptual_illustration" or receipt.get("source") not in {"gpt-image-api","chatgpt-web"}:
        raise ValueError("invalid illustration source")
    if receipt.get("output_sha256")!=output_provenance.sha256_file(path) or not re.fullmatch(r"[0-9a-f]{64}",str(receipt.get("prompt_sha256",""))):
        raise ValueError("stale illustration receipt or missing prompt hash")
    if not str(receipt.get("model_id","")).strip():raise ValueError("model_id is required (unverified if unknown)")
    origin=output_provenance.current_origin(project,path)
    if origin.get("status")!="tracked" or origin.get("family")=="anthropic":
        raise ValueError("illustration requires current non-Claude output provenance")
    registry_path=project/"papers"/paper_id/"figures"/"figure-provenance.json"
    registry=_load_registry(registry_path);timestamp=output_provenance.utc_now()
    record={"figure_path":relative,"figure_type":"conceptual_illustration",
            "renderer":{"path":source_rel,"sha256":output_provenance.sha256_file(source)},
            "config":None,"inputs":[],"source_run_ids":[],
            "output_sha256":output_provenance.sha256_file(path),"deterministic":False,
            "generated_by":receipt["source"],"prompt_sha256":receipt["prompt_sha256"],
            "model_id":receipt["model_id"],"disclosure_location":disclosure_location.strip(),
            "human_content_checked_by":checked_by.strip(),
            "language_checked_by":checked_by.strip(),"language_checked_at":timestamp,"recorded_at":timestamp}
    registry["figures"]=[item for item in registry["figures"] if isinstance(item,dict) and item.get("figure_path")!=relative]+[record]
    _write(registry_path,registry)
    output_provenance.record_model_writes(project,[registry_path],family="other",provider="local-provenance-check",
        model="scripts/figure_provenance.py",role="illustration-approval",run_id="illustration-"+timestamp.replace(":","-"))
    return relative


def validate_figure_provenance(project:Path,paper:Path)->list[str]:
    errors=[];figures_dir=paper/"figures"
    actual={path.relative_to(project).as_posix() for path in figures_dir.rglob("*") if path.is_file() and path.suffix.lower() in FIGURE_SUFFIXES}
    registry_path=figures_dir/"figure-provenance.json"
    if not actual:
        if registry_path.is_file() and registry_path.stat().st_size:return errors
        return errors
    try:registry=_load_registry(registry_path)
    except (OSError,ValueError,json.JSONDecodeError) as exc:return [f"cannot read registry: {exc}"]
    records={}
    for index,item in enumerate(registry["figures"]):
        if not isinstance(item,dict) or not isinstance(item.get("figure_path"),str):errors.append(f"record {index+1} is malformed");continue
        if item["figure_path"] in records:errors.append(f"duplicate record for {item['figure_path']}")
        records[item["figure_path"]]=item
    if actual-set(records):errors.append("unregistered final figures: "+", ".join(sorted(actual-set(records))))
    if set(records)-actual:errors.append("stale/extra figure records: "+", ".join(sorted(set(records)-actual)))
    successful={}
    registry_runs=project/"experiments"/"registry.jsonl"
    if registry_runs.is_file():
        for line in registry_runs.read_text(encoding="utf-8").splitlines():
            try:
                value=json.loads(line)
                if value.get("status")=="succeeded":successful[str(value.get("run_id"))]=value.get("paper_id")
            except json.JSONDecodeError:pass
    for relative,item in records.items():
        try:
            path,_=_relative(project,relative,"figure_path")
            if not path.is_file() or item.get("output_sha256")!=output_provenance.sha256_file(path):errors.append(f"{relative}: output hash is stale")
            illustration=item.get("figure_type")=="conceptual_illustration"
            if item.get("figure_type") not in FIGURE_TYPES:errors.append(f"{relative}: invalid figure type")
            if illustration:
                if item.get("deterministic") is not False or item.get("generated_by") not in {"gpt-image-api","chatgpt-web"} or not str(item.get("human_content_checked_by","")).strip() or not str(item.get("disclosure_location","")).strip() or not re.fullmatch(r"[0-9a-f]{64}",str(item.get("prompt_sha256",""))):
                    errors.append(f"{relative}: conceptual illustration needs explicit source, approval and disclosure")
                origin=output_provenance.current_origin(project,path)
                if origin.get("status")!="tracked" or origin.get("family")=="anthropic":errors.append(f"{relative}: illustration needs current non-Claude provenance")
            elif item.get("deterministic") is not True or item.get("generated_by")!="local-tool":
                errors.append(f"{relative}: invalid deterministic rendering declaration")
            if not isinstance(item.get("language_checked_by"),str) or not item["language_checked_by"].strip() or not isinstance(item.get("language_checked_at"),str) or not item["language_checked_at"].strip():errors.append(f"{relative}: named human English-label confirmation is required")
            renderer=item.get("renderer") if isinstance(item.get("renderer"),dict) else {};renderer_path,_=_relative(project,str(renderer.get("path","")),"renderer")
            if not renderer_path.is_file() or renderer.get("sha256")!=output_provenance.sha256_file(renderer_path):errors.append(f"{relative}: renderer hash is stale")
            origin=output_provenance.current_origin(project,renderer_path)
            if origin.get("status")!="tracked" or origin.get("family")=="anthropic":errors.append(f"{relative}: renderer/source lacks current non-Claude provenance")
            inputs=item.get("inputs") if isinstance(item.get("inputs"),list) else []
            for input_item in inputs:
                if not isinstance(input_item,dict):errors.append(f"{relative}: malformed input record");continue
                input_path,_=_relative(project,str(input_item.get("path","")),"input")
                if not input_path.is_file() or input_item.get("sha256")!=output_provenance.sha256_file(input_path):errors.append(f"{relative}: input hash is stale: {input_item.get('path')}")
            config=item.get("config")
            if isinstance(config,dict):
                config_path,_=_relative(project,str(config.get("path","")),"config")
                if not config_path.is_file() or config.get("sha256")!=output_provenance.sha256_file(config_path):errors.append(f"{relative}: config hash is stale")
                config_origin=output_provenance.current_origin(project,config_path)
                if config_origin.get("status")!="tracked" or config_origin.get("family")=="anthropic":errors.append(f"{relative}: config lacks current non-Claude provenance")
            runs=set(str(value) for value in item.get("source_run_ids",[]) if value)
            if item.get("figure_type")=="data_chart" and (not inputs or not runs or not runs.issubset(successful) or any(successful.get(run)!=paper.name for run in runs)):errors.append(f"{relative}: data chart needs current inputs and successful source runs for {paper.name}")
            if illustration and (inputs or runs):errors.append(f"{relative}: conceptual illustration may not assert experimental inputs or runs")
        except (OSError,ValueError) as exc:errors.append(f"{relative}: {exc}")
    if any(item.get("figure_type")=="conceptual_illustration" for item in records.values() if isinstance(item,dict)):
        disclosure_file=paper/"disclosures.json"
        if disclosure_file.is_file():
            try:
                disclosures=json.loads(disclosure_file.read_text(encoding="utf-8"))
                ai_use=disclosures.get("ai_use","") if isinstance(disclosures,dict) else ""
                statement=ai_use if isinstance(ai_use,str) else json.dumps(ai_use,ensure_ascii=False)
                if not statement.strip() or re.fullmatch(r"\s*(none|no|not used|n/a)\s*\.?",statement,re.I):
                    errors.append("conceptual illustration requires an actual AI-use disclosure; source receipt alone is insufficient")
            except (OSError,json.JSONDecodeError):
                errors.append("cannot verify conceptual illustration AI-use disclosure")
    return errors


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="command",required=True)
    record=sub.add_parser("record");record.add_argument("--project",required=True);record.add_argument("--paper",required=True);record.add_argument("--figure",required=True);record.add_argument("--type",required=True,choices=sorted(FIGURE_TYPES-{"conceptual_illustration"}));record.add_argument("--renderer",required=True);record.add_argument("--input",action="append",default=[],dest="inputs");record.add_argument("--run",action="append",default=[],dest="runs");record.add_argument("--config");record.add_argument("--language-checked-by",required=True)
    illustration=sub.add_parser("approve-illustration");illustration.add_argument("--project",required=True);illustration.add_argument("--paper",required=True);illustration.add_argument("--figure",required=True);illustration.add_argument("--receipt",required=True);illustration.add_argument("--checked-by",required=True);illustration.add_argument("--disclosure-location",required=True)
    validate=sub.add_parser("validate");validate.add_argument("--project",required=True);validate.add_argument("--paper",required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1];project=root/"projects"/args.project;paper=project/"papers"/args.paper
    try:
        if args.command=="record":print(record_figure(project,args.paper,args.figure,args.type,args.renderer,args.inputs,args.runs,args.config,args.language_checked_by))
        elif args.command=="approve-illustration":print(record_generated_illustration(project,args.paper,args.figure,args.receipt,args.checked_by,args.disclosure_location))
        else:
            errors=validate_figure_provenance(project,paper)
            if errors:raise ValueError("; ".join(errors))
            print("figure provenance passed")
        return 0
    except (OSError,ValueError,json.JSONDecodeError) as exc:print(f"error: {exc}");return 2


if __name__=="__main__":raise SystemExit(main())
