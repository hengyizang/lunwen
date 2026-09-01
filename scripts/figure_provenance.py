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
FIGURE_TYPES={"data_chart","conceptual_diagram"}


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
    if figure_type not in FIGURE_TYPES:raise ValueError("type must be data_chart or conceptual_diagram")
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
    output_provenance.record_model_writes(project,[figure_path],family="other",provider="deterministic-local-renderer",model=renderer_rel,role="final-figure",run_id="figure-"+output_provenance.utc_now().replace(":","-"))
    return figure_rel


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
            if item.get("figure_type") not in FIGURE_TYPES or item.get("deterministic") is not True or item.get("generated_by")!="local-tool":errors.append(f"{relative}: invalid deterministic rendering declaration")
            if not isinstance(item.get("language_checked_by"),str) or not item["language_checked_by"].strip() or not isinstance(item.get("language_checked_at"),str) or not item["language_checked_at"].strip():errors.append(f"{relative}: named human English-label confirmation is required")
            renderer=item.get("renderer") if isinstance(item.get("renderer"),dict) else {};renderer_path,_=_relative(project,str(renderer.get("path","")),"renderer")
            if not renderer_path.is_file() or renderer.get("sha256")!=output_provenance.sha256_file(renderer_path):errors.append(f"{relative}: renderer hash is stale")
            origin=output_provenance.current_origin(project,renderer_path)
            if origin.get("status")!="tracked" or origin.get("family")=="anthropic":errors.append(f"{relative}: renderer lacks current non-Claude provenance")
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
        except (OSError,ValueError) as exc:errors.append(f"{relative}: {exc}")
    return errors


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest="command",required=True)
    record=sub.add_parser("record");record.add_argument("--project",required=True);record.add_argument("--paper",required=True);record.add_argument("--figure",required=True);record.add_argument("--type",required=True,choices=sorted(FIGURE_TYPES));record.add_argument("--renderer",required=True);record.add_argument("--input",action="append",default=[],dest="inputs");record.add_argument("--run",action="append",default=[],dest="runs");record.add_argument("--config");record.add_argument("--language-checked-by",required=True)
    validate=sub.add_parser("validate");validate.add_argument("--project",required=True);validate.add_argument("--paper",required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1];project=root/"projects"/args.project;paper=project/"papers"/args.paper
    try:
        if args.command=="record":print(record_figure(project,args.paper,args.figure,args.type,args.renderer,args.inputs,args.runs,args.config,args.language_checked_by))
        else:
            errors=validate_figure_provenance(project,paper)
            if errors:raise ValueError("; ".join(errors))
            print("figure provenance passed")
        return 0
    except (OSError,ValueError,json.JSONDecodeError) as exc:print(f"error: {exc}");return 2


if __name__=="__main__":raise SystemExit(main())
