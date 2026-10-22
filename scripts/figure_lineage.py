"""Seal plot inputs to exact approved executor outputs or replayable CSV transforms.

Run identifiers are parent IDs or ``supplemental/P01/R001/s001/run-id``.
Source receipts are control-plane evidence, never a model-authored declaration.
No function here executes an experiment or calls a model.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys

if __package__ in {None,""}:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from scripts.research_artifacts import path_in, read, record, sha, write
from scripts.output_provenance import current_origin

MODULE = "scripts/figure_lineage.py"
PREFIX = "reports/figure-data"


def need(value, message):
    if not value:raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def _owned(project,path,model):
    origin=current_origin(project,path)
    need(origin.get("status")=="tracked" and origin.get("provider")=="deterministic-control-plane" and origin.get("model")==model,
         "Plot lineage requires current deterministic control-plane provenance")


def _scope(project,paper_id,identifier):
    if "/" not in identifier:
        need(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",identifier)),"Unsafe source run ID")
        return project,identifier,None
    matched=re.fullmatch(r"supplemental/(P\d{2})/(R\d{3})/(s\d{3})/([A-Za-z0-9][A-Za-z0-9_.-]{0,127})",identifier)
    need(matched and matched[1]==paper_id,"Supplemental source run belongs to another paper or namespace")
    _,round_id,scope,run_id=matched.groups()
    control_path=path_in(project,f"state/supplemental-experiments/{paper_id}/{round_id}/{scope}.json")
    _owned(project,control_path,"scripts/supplemental_experiments.py")
    control=read(control_path)
    expected=f"experiments/supplemental/{paper_id}/{round_id}/{scope}"
    need(control.get("scope_root")==expected and control.get("paper_id")==paper_id and control.get("round_id")==round_id and control.get("scope_id")==scope,
         "Supplemental figure source has a mismatched approved scope")
    child=path_in(project,expected+"/state/run.json").parent.parent
    need(sha(child/"state/run.json")==control.get("child_state_sha256"),"Supplemental approved state changed")
    need(read(child/"state/run.json").get("approvals")==[control.get("approval")],"Supplemental G3 authority changed")
    proposal=control.get("proposal",{})
    need(proposal.get("original_plan_sha256")==sha(project/"experiments/plan.json") and proposal.get("original_preregistration_sha256")==sha(project/f"papers/{paper_id}/preregistration.json"),"Parent protocol changed after supplemental approval")
    confirmation=control.get("confirmation")
    need(not control.get("retirement") and isinstance(confirmation,dict) and confirmation.get("actor") and confirmation.get("source_run_id")
         and re.fullmatch(r"[0-9a-f]{64}",str(confirmation.get("cloud_review_sha256",""))),"Supplemental plotted data needs named scientific confirmation")
    files=confirmation.get("files")
    need(isinstance(files,dict) and files,"Supplemental confirmation has no sealed evidence files")
    for relative,expected_hash in files.items():
        need(sha(path_in(child,relative))==expected_hash,"Confirmed supplemental source changed: "+relative)
    return child,run_id,{"path":control_path.relative_to(project).as_posix(),"sha256":sha(control_path)}


def run_seal(project:Path,paper_id:str,identifier:str)->dict:
    root,run_id,scope=_scope(project,paper_id,identifier)
    plan_path=path_in(root,"experiments/plan.json")
    plan=read(plan_path)
    state=read(path_in(root,"state/run.json"))
    approval=next((a for a in reversed(state.get("approvals",[])) if a.get("gate")=="G3"),{})
    plan_hash=sha(plan_path)
    need("G3" in state.get("approved_gates",[]) and approval.get("actor") and approval.get("experiment_plan_sha256")==plan_hash,
         "Plot source has no current named G3 plan approval")
    need(approval.get("experiment_budget_sha256")==sha(path_in(root,"experiments/budget.json")),"Plot source budget differs from G3 approval")
    runs=[r for r in plan.get("runs",[]) if r.get("run_id")==run_id]
    need(len(runs)==1 and runs[0].get("paper_id")==paper_id,"Plot source run is not an approved run for this paper")
    run=runs[0]
    prereg_relative=f"papers/{paper_id}/preregistration.json"
    prereg=path_in(root,prereg_relative)
    need(approval.get("frozen_protocol_sha256",{}).get(prereg_relative)==sha(prereg),"Plot source preregistration changed after G3 approval")
    frozen=read(prereg)
    need(frozen.get("status")=="frozen" and frozen.get("files"),"Plot source needs the frozen protocol inputs")
    from scripts.cloud_checkpoint import excluded
    for row in frozen["files"]:
        target=path_in(root,row["path"],exists=False)
        # Excluded original raw data need not be reacquired merely to package a
        # chart. Their immutable expected hashes remain in the G3/attempt seal.
        if target.is_file() or not excluded(row["path"]):
            need(target.is_file() and sha(target)==row["sha256"],"Plot source frozen input changed: "+row["path"])
    registry_path=path_in(root,"experiments/registry.jsonl")
    records=[json.loads(line) for line in registry_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    try:
        from scripts.primary_recovery import selected_attempt
    except ImportError:
        selected_attempt=None
    if selected_attempt:
        receipt=selected_attempt(root,run_id,records,plan_sha256=plan_hash)
    else:
        matches=[r for r in records if r.get("run_id")==run_id]
        need(len(matches)==1,"Plot source requires exactly one successful executor attempt or owner-approved recovery")
        receipt=matches[0]
    need(receipt.get("status")=="succeeded" and receipt.get("exit_code")==0 and receipt.get("timed_out") is False
         and receipt.get("paper_id")==paper_id and receipt.get("approved_plan_sha256")==plan_hash,"Plot source attempt did not succeed for the current approved paper/plan")
    for key,default in (("argv",None),("seed",None),("cwd","."),("timeout_seconds",None)):
        need(receipt.get(key)==run.get(key,default),"Plot executor receipt differs from approved "+key)
    expected_inputs={r["path"]:r["sha256"] for r in run.get("inputs",[])}
    need({r["path"]:r["sha256"] for r in receipt.get("inputs",[])}==expected_inputs,"Plot executor inputs differ from approved run")
    integrity=receipt.get("input_integrity",{})
    need(integrity.get("verified_after_run") is True and integrity.get("passed") is True and integrity.get("mutated_or_missing")==[],"Plot source lacks successful post-run input integrity")
    attempt_id=receipt.get("attempt_id")
    need(isinstance(attempt_id,str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}",attempt_id),"Unsafe plot source attempt ID")
    executor_path=path_in(root,f"experiments/runs/{attempt_id}/run.json")
    need(read(executor_path)==receipt,"Plot source registry differs from its executor-issued receipt")
    outputs=receipt.get("outputs",[])
    need(len(outputs)==len({r.get("path") for r in outputs}) and {r.get("path") for r in outputs}==set(run.get("expected_outputs",[]))
         and outputs and not receipt.get("missing_outputs"),"Plot source output set differs from its approved run")
    output_records=[]
    for row in outputs:
        path=path_in(root,row["path"])
        need(sha(path)==row.get("sha256"),"Sealed plotted output changed: "+row["path"])
        output_records.append({"path":path.relative_to(project).as_posix(),"sha256":row["sha256"]})
    return {"run_id":identifier,"paper_id":paper_id,"scope":scope,"plan_sha256":plan_hash,"preregistration_sha256":sha(prereg),
            "attempt_id":attempt_id,"executor_receipt":{"path":executor_path.relative_to(project).as_posix(),"sha256":sha(executor_path)},
            "registry_entry_sha256":digest(receipt),"outputs":output_records}


def receipt_path(project,relative):
    return path_in(project,PREFIX+"/"+hashlib.sha256(relative.encode()).hexdigest()+".json",exists=False)


def _csv_transform(project,spec):
    need(set(spec) in ({"operation","sources","columns","group_by"},{"operation","sources","columns","group_by","record_path"}),"CSV transform needs exact operation/sources/columns/group_by and optional JSON record_path")
    operation=spec["operation"]
    need(operation in {"concatenate","project","group_mean","json_rows"},"Unsupported plot aggregation; execute the analysis as an approved experiment")
    columns,groups=spec["columns"],spec["group_by"]
    need(isinstance(columns,list) and columns and len(columns)==len(set(columns)) and all(isinstance(c,str) and c for c in columns),"Plot columns need unique explicit names")
    need(isinstance(groups,list) and all(isinstance(c,str) and c for c in groups) and len(groups)==len(set(groups)) and not set(groups)&set(columns),"Invalid aggregation groups")
    need(operation=="group_mean" or not groups,"Groups apply only to group_mean")
    need((operation=="json_rows")== ("record_path" in spec),"JSON row projection needs an explicit record_path; other transforms cannot declare one")
    rows=[]
    for relative in spec["sources"]:
        path=path_in(project,relative)
        need(path.stat().st_size<=10_000_000,"Use bounded registered inputs for plot aggregation")
        if operation=="json_rows":
            need(path.suffix.lower()==".json","JSON row projection requires a registered JSON output")
            def at(value,key):
                need(isinstance(key,str) and bool(re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*",key)),"Use literal dotted JSON keys")
                for part in key.split("."):
                    need(isinstance(value,dict) and part in value,"JSON projection key is absent: "+key)
                    value=value[part]
                return value
            records=at(read(path),spec["record_path"])
            need(isinstance(records,list),"JSON projection record_path must identify an actual array")
            for source in records:
                row={key:at(source,key) for key in columns}
                need(all(type(value) in {str,int,float,bool} or value is None for value in row.values()),"JSON plot columns must be scalar recorded values")
                need(all(not isinstance(value,float) or math.isfinite(value) for value in row.values()),"Nonfinite JSON plot value")
                rows.append(row);need(len(rows)<=100000,"Plot aggregation exceeds 100,000 source rows")
            continue
        need(path.suffix.lower()==".csv","CSV aggregation requires registered CSV outputs")
        with path.open(newline="",encoding="utf-8") as handle:
            reader=csv.DictReader(handle)
            need(reader.fieldnames and set(columns+groups)<=set(reader.fieldnames),"Aggregation column is absent from the actual source")
            for row in reader:
                rows.append({c:row[c] for c in columns+groups})
                need(len(rows)<=100000,"Plot aggregation exceeds 100,000 source rows")
    need(rows,"Plot aggregation has no source rows")
    fieldnames=groups+columns
    if operation=="group_mean":
        grouped={}
        for row in rows:
            key=tuple(row[c] for c in groups)
            grouped.setdefault(key,[]).append(row)
        result=[]
        for key,values in sorted(grouped.items()):
            row=dict(zip(groups,key))
            for c in columns:
                numbers=[float(v[c]) for v in values]
                need(all(math.isfinite(v) for v in numbers),"Nonfinite aggregate input")
                row[c]=format(math.fsum(numbers)/len(numbers),".17g")
            result.append(row)
        rows=result
    stream=io.StringIO(newline="")
    writer=csv.DictWriter(stream,fieldnames=fieldnames,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def lineage(project,paper_id,inputs,runs,*,_stack=()):
    need(len(_stack)<20,"Derived plot-data ancestry exceeds 20 transformations")
    need(isinstance(runs,list) and runs and all(isinstance(r,str) for r in runs) and len(runs)<=100 and len(runs)==len(set(runs)),"Plot needs distinct explicit sealed source runs")
    need(isinstance(inputs,list) and inputs and all(isinstance(i,str) for i in inputs) and len(inputs)<=100 and len(inputs)==len(set(inputs)),"Plot needs distinct explicit source data")
    seals=[run_seal(project,paper_id,r) for r in sorted(runs)]
    leaves={}
    for seal in seals:
        for row in seal["outputs"]:leaves.setdefault(row["path"],[]).append((seal["run_id"],row["sha256"]))
    used=set();bound=[]
    for relative in inputs:
        path=path_in(project,relative)
        need(relative not in _stack,"Cyclic derived plot-data provenance")
        actual=sha(path)
        if relative in leaves:
            matches=[run for run,expected in leaves[relative] if expected==actual]
            need(matches,"Plot data differs from executor-sealed source")
            used.update(matches);bound.append({"path":relative,"sha256":actual,"kind":"executor_output"})
            continue
        receipt_file=receipt_path(project,relative)
        need(receipt_file.is_file(),"Unsealed plotted data has no deterministic derivation receipt: "+relative)
        _owned(project,receipt_file,MODULE)
        receipt=read(receipt_file)
        need(receipt.get("schema_version")=="1.0" and receipt.get("paper_id")==paper_id and receipt.get("output")=={"path":relative,"sha256":actual}
             and receipt.get("implementation_sha256")==sha(Path(__file__)),"Derived plot source receipt is stale or belongs to another paper")
        nested=lineage(project,paper_id,receipt["transform"]["sources"],receipt["source_run_ids"],_stack=(*_stack,relative))
        need(nested==receipt.get("lineage"),"Derived plotted-data ancestry changed")
        need(_csv_transform(project,receipt["transform"])==path.read_bytes(),"Derived plotted data differs from deterministic recomputation")
        need(set(receipt["source_run_ids"])<=set(runs),"Derived plot data references undeclared source runs")
        used.update(receipt["source_run_ids"])
        bound.append({"path":relative,"sha256":actual,"kind":"derived_csv","receipt":{"path":receipt_file.relative_to(project).as_posix(),"sha256":sha(receipt_file)}})
    need(used==set(runs),"Plot source run IDs include unrelated runs or omit actual data ancestry")
    return {"schema_version":"1.0","paper_id":paper_id,"inputs":bound,"runs":seals}


def derive(project,paper_id,output,transform,runs):
    need(os.environ.get("GITHUB_ACTIONS")=="true" or os.environ.get("DR_OS_CLOUD_EXECUTOR")=="1","Plot-data derivation requires the cloud executor")
    need(bool(re.fullmatch(r"P\d{2}",paper_id)),"Exact plot paper ID required")
    need(output.startswith(f"papers/{paper_id}/figures/source-data/") and output.endswith(".csv"),"Derived plot output belongs in this paper's figures/source-data directory")
    need(isinstance(transform,dict) and isinstance(transform.get("sources"),list) and output not in transform["sources"],"Explicit distinct aggregation sources required")
    ancestry=lineage(project,paper_id,transform["sources"],runs)
    payload=_csv_transform(project,transform)
    target=path_in(project,output,exists=False);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
    value={"schema_version":"1.0","paper_id":paper_id,"transform":transform,"source_run_ids":runs,"lineage":ancestry,
           "output":{"path":output,"sha256":sha(target)},"implementation_sha256":sha(Path(__file__)),"scientific_completion_verified":False}
    receipt=receipt_path(project,output);write(receipt,value);record(project,[target,receipt],MODULE)
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project",type=Path,required=True);parser.add_argument("--paper",required=True);parser.add_argument("--spec",required=True)
    args=parser.parse_args();value=read(path_in(args.project,args.spec))
    need(set(value)=={"output","transform","source_run_ids"},"Plot-data request needs output/transform/source_run_ids")
    print(json.dumps(derive(args.project,args.paper,value["output"],value["transform"],value["source_run_ids"]),ensure_ascii=False))


if __name__=="__main__":main()
