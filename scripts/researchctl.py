#!/usr/bin/env python3
"""Human-gated Doctoral Research OS state manager with publication-quality floors."""
from __future__ import annotations
import argparse,csv,hashlib,json,os,re,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Iterable
ROOT=Path(__file__).resolve().parents[1]; PROJECTS_ROOT=ROOT/"projects"; DEFAULTS_PATH=ROOT/"config/defaults.json"
STAGES=[{"name":"intake","gate":"G0"},{"name":"topic-intelligence","gate":"G1"},{"name":"paper-architecture","gate":"G2"},{"name":"experiment-design","gate":"G3"},{"name":"experiment-execution","gate":"G4"},{"name":"writing-and-review","gate":"G5"},{"name":"submission-ready","gate":None}]
SLUG_RE=re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$"); PAPER_RE=re.compile(r"^P[0-9]{2}$")
class ResearchCtlError(RuntimeError): pass
def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
def read_json(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:raise ResearchCtlError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:raise ResearchCtlError(f"Invalid JSON in {path}: {exc}") from exc
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True); payload=json.dumps(value,ensure_ascii=False,indent=2)+"\n"
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,delete=False) as h:h.write(payload); tmp=h.name
    os.replace(tmp,path)
def write_text(path,value): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(value,encoding="utf-8")
def validate_slug(slug):
    if not SLUG_RE.fullmatch(slug): raise ResearchCtlError("Project slug must be 2-63 lowercase letters, digits or hyphens, starting with a letter or digit.")
    return slug
def validate_paper_id(paper_id):
    if not PAPER_RE.fullmatch(paper_id): raise ResearchCtlError("Paper id must look like P01.")
    return paper_id
def project_dir(slug): return PROJECTS_ROOT/validate_slug(slug)
def state_path(slug): return project_dir(slug)/"state"/"run.json"
def load_state(slug):
    state=read_json(state_path(slug)); index=state.get("stage_index")
    if not isinstance(index,int) or not 0<=index<len(STAGES): raise ResearchCtlError("State has an invalid stage_index.")
    expected=STAGES[index]
    if state.get("stage")!=expected["name"] or state.get("gate")!=expected["gate"]: raise ResearchCtlError("State stage/gate does not match stage_index.")
    if "paper_statuses" not in state:
        count=int(state.get("paper_count",1)); active=state.get("active_paper","P01")
        state["paper_statuses"]={f"P{n:02d}":("submission_ready" if state.get("gate") is None else "active" if f"P{n:02d}"==active else "planned") for n in range(1,count+1)}; state["schema_version"]="2.0"
    return state
def save_state(slug,state): state["updated_at"]=now(); write_json(state_path(slug),state)
def nonempty(path): return path.is_file() and path.stat().st_size>0
def file_sha256(path):
    d=hashlib.sha256()
    with path.open("rb") as h:
        for chunk in iter(lambda:h.read(1024*1024),b""):d.update(chunk)
    return d.hexdigest()
def load_nonempty_json(path,errors):
    if not nonempty(path):errors.append(f"missing or empty: {path}");return None
    try:value=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:errors.append(f"invalid JSON: {path} ({exc})");return None
    if not isinstance(value,dict):errors.append(f"expected JSON object: {path}");return None
    return value
def jsonl_objects(path,errors):
    if not nonempty(path):errors.append(f"missing or empty: {path}");return []
    out=[]
    for n,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip():continue
        try:v=json.loads(line)
        except json.JSONDecodeError as exc:errors.append(f"invalid JSONL at {path}:{n}: {exc}");continue
        if not isinstance(v,dict):errors.append(f"expected JSON object at {path}:{n}");continue
        out.append(v)
    return out
def independent_audit_errors(project,gate,errors,paper_id=None):
    prefix=f"{gate}-{paper_id}" if paper_id else gate; finals=sorted([*list((project/"reviews"/"independent").glob(f"{prefix}-*-final.json")),*list((project/"reviews"/"codex").glob(f"{prefix}-*-final.json"))]); valid=False
    if not finals:errors.append(f"{gate} requires a final independent model-family audit")
    for path in finals[-1:]:
        initial=path.with_name(path.name.replace("-final.json","-initial.json"))
        if not nonempty(initial):errors.append(f"{path.name}: matching initial independent audit is missing");continue
        audit=load_nonempty_json(path,errors)
        if audit and audit.get("verdict")=="pass-with-conditions" and not audit.get("fatal_findings"):valid=True
        elif audit:errors.append(f"{path.name}: final independent verdict must be pass-with-conditions and have no fatal findings")
    if not valid:errors.append(f"{gate} requires a passing final independent model-family audit")
    if not nonempty(project/"reviews"/"decision-log.md"):errors.append("reviews/decision-log.md must disposition independent findings")
def quality_path(project,gate,paper_id=None):
    return {"G1":project/"program"/"quality-G1.json","G2":project/"papers"/str(paper_id)/"quality-G2.json","G3":project/"experiments"/"quality-G3.json","G4":project/"reports"/"quality-G4.json","G5":project/"papers"/str(paper_id)/"reviews"/"quality-G5.json"}[gate]
def quality_errors(project,gate,errors,paper_id=None):
    try:from scripts.quality_gate import validate_file
    except ImportError as exc:errors.append(f"quality gate validator unavailable: {exc}");return
    path=quality_path(project,gate,paper_id);errors.extend(f"{path}: {e}" for e in validate_file(path,gate))
def gate_errors(slug,gate):
    project=project_dir(slug);errors=[]
    if gate is None:return errors
    if gate=="G0":
        c=load_nonempty_json(project/"intake"/"constraints.json",errors)
        if c and c.get("status")!="ready_for_review":errors.append("intake/constraints.json status must be ready_for_review")
        return errors
    if gate=="G1":
        if not nonempty(project/"evidence"/"search-log.jsonl"):errors.append("evidence/search-log.jsonl is required")
        s=load_nonempty_json(project/"program"/"topic-shortlist.json",errors)
        if s:
            cs=s.get("candidates") or s.get("topics")
            if not isinstance(cs,list) or len(cs)<3:errors.append("topic-shortlist.json requires at least three candidates")
        for rel in ("program/core-thesis.json","program/extension-thesis.json"):
            v=load_nonempty_json(project/rel,errors)
            if v and v.get("status") not in {"ready_for_review","approved"}:errors.append(f"{rel} status must be ready_for_review or approved")
        if not nonempty(project/"program"/"topic-decision.md"):errors.append("program/topic-decision.md is required")
        quality_errors(project,gate,errors);independent_audit_errors(project,gate,errors);return errors
    if gate=="G2":
        load_nonempty_json(project/"program"/"paper-map.json",errors);state=read_json(state_path(slug));dirs=sorted((project/"papers").glob("P[0-9][0-9]"))
        if len(dirs)!=state.get("paper_count"):errors.append(f"expected exactly {state.get('paper_count')} paper directories, found {len(dirs)}")
        for pd in dirs:
            c=load_nonempty_json(pd/"paper-contract.json",errors)
            if c and c.get("status") not in {"ready_for_review","approved"}:errors.append(f"{pd.name}/paper-contract.json must be ready_for_review or approved")
            if c:
                for f in ("working_title","research_question","distinct_contribution"):
                    if not str(c.get(f,"")).strip():errors.append(f"{pd.name}/paper-contract.json needs {f}")
                if not c.get("falsification_conditions"):errors.append(f"{pd.name}/paper-contract.json needs falsification conditions")
                if not isinstance(c.get("target_venues"),list) or len(c.get("target_venues"))<2:errors.append(f"{pd.name} needs at least two Q1 target venues")
                quality_errors(project,gate,errors,pd.name)
        independent_audit_errors(project,gate,errors);return errors
    if gate=="G3":
        datasets=jsonl_objects(project/"data"/"datasets.jsonl",errors)
        if not datasets:errors.append("at least one licensed dataset manifest is required")
        try:
            from scripts.dataset_fetch import validate_manifest
            for i,d in enumerate(datasets,1):
                for issue in validate_manifest(d):errors.append(f"datasets.jsonl entry {i}: {issue}")
                if d.get("license",{}).get("confirmed_by_human") is not True:errors.append(f"datasets.jsonl entry {i}: license needs human confirmation")
                if d.get("download",{}).get("sha256")=="pending":errors.append(f"datasets.jsonl entry {i}: SHA-256 remains pending")
        except ImportError as exc:errors.append(f"dataset validator unavailable: {exc}")
        plan=load_nonempty_json(project/"experiments"/"plan.json",errors)
        if plan:
            try:
                from scripts.experiment_runner import validate_plan
                errors.extend(f"experiments/plan.json: {x}" for x in validate_plan(plan))
            except ImportError as exc:errors.append(f"experiment plan validator unavailable: {exc}")
        budget=load_nonempty_json(project/"experiments"/"budget.json",errors)
        if budget:
            if budget.get("status")!="ready_for_review":errors.append("experiments/budget.json status must be ready_for_review")
            ceiling=budget.get("hard_ceiling_usd")
            if not isinstance(ceiling,(int,float)) or isinstance(ceiling,bool) or ceiling<0:errors.append("experiments/budget.json needs non-negative hard_ceiling_usd")
        quality_errors(project,gate,errors);independent_audit_errors(project,gate,errors);return errors
    if gate=="G4":
        registry=jsonl_objects(project/"experiments"/"registry.jsonl",errors)
        if not registry:errors.append("at least one experiment registry entry is required")
        plan=load_nonempty_json(project/"experiments"/"plan.json",errors)
        if plan:
            planned={x.get("run_id") for x in plan.get("runs",[]) if isinstance(x,dict)};attempted={x.get("run_id") for x in registry};missing=sorted(str(x) for x in planned-attempted)
            if missing:errors.append(f"planned runs without registry attempts: {', '.join(missing)}")
        claim=project/"claims"/"claim-evidence.csv"
        if not nonempty(claim):errors.append("claims/claim-evidence.csv is required")
        elif sum(1 for _ in csv.reader(claim.open(newline="",encoding="utf-8")))<2:errors.append("claim-evidence.csv needs at least one claim row")
        if not nonempty(project/"reports"/"reproducibility.md"):errors.append("reports/reproducibility.md is required")
        quality_errors(project,gate,errors);independent_audit_errors(project,gate,errors);return errors
    if gate=="G5":
        pid=active_paper_id(slug);paper=project/"papers"/pid
        try:
            from scripts.output_provenance import ProvenanceError,reject_current_anthropic_outputs
            final_files=[path for path in paper.rglob("*") if path.is_file() and not path.is_symlink() and not any(part in {"build","submission","venue-template"} for part in path.relative_to(paper).parts)]
            reject_current_anthropic_outputs(project,final_files)
        except ImportError as exc:errors.append(f"output provenance validator unavailable: {exc}")
        except ProvenanceError as exc:errors.append(str(exc))
        if not any(nonempty(p) for p in (paper/"manuscript"/"main.tex",paper/"manuscript"/"main.docx")):errors.append(f"{pid} requires manuscript/main.tex or manuscript/main.docx")
        venue=load_nonempty_json(paper/"venue.json",errors)
        if venue and not venue.get("g5_reverified_at"):errors.append(f"{pid}/venue.json needs g5_reverified_at")
        jcr=load_nonempty_json(paper/"jcr-verification.json",errors)
        if jcr:
            if jcr.get("quartile")!="Q1":errors.append(f"{pid} selected venue must be current JCR Q1")
            if jcr.get("indexing") not in {"SCI","SCIE"}:errors.append(f"{pid} selected venue must be SCI/SCIE")
            if not isinstance(jcr.get("impact_factor"),(int,float)) or jcr.get("impact_factor",0)<=1.0:errors.append(f"{pid} selected venue impact factor must be > 1.0")
        response=paper/"reviews"/"response-matrix.csv"
        if not nonempty(response) or sum(1 for _ in csv.reader(response.open(newline="",encoding="utf-8")))<2:errors.append(f"{pid} requires a non-empty reviews/response-matrix.csv")
        for n in (1,2):
            if not nonempty(paper/"reviews"/f"round-{n}.md"):errors.append(f"{pid} requires reviews/round-{n}.md")
        citation=load_nonempty_json(paper/"reviews"/"citation-audit.json",errors)
        if citation and citation.get("status")!="pass":errors.append(f"{pid} citation audit must pass")
        compliance=load_nonempty_json(paper/"reviews"/"venue-compliance.json",errors)
        if compliance and compliance.get("status")!="pass":errors.append(f"{pid} venue compliance report must pass")
        disclosures=load_nonempty_json(paper/"disclosures.json",errors)
        if disclosures and disclosures.get("status")!="ready_for_review":errors.append(f"{pid}/disclosures.json status must be ready_for_review")
        if disclosures:
            for f in ("author_contributions","conflicts","funding","ethics","ai_use"):
                if f not in disclosures:errors.append(f"{pid}/disclosures.json needs {f}")
        quality_errors(project,gate,errors,pid);independent_audit_errors(project,gate,errors,pid);return errors
    errors.append(f"unknown gate: {gate}");return errors
def active_paper_id(slug):return validate_paper_id(str(read_json(state_path(slug)).get("active_paper")))
def artifact_hash(slug,gate):
    project=project_dir(slug);d=hashlib.sha256()
    for path in sorted(project.rglob("*")):
        rel=path.relative_to(project)
        if not path.is_file() or rel.parts[0]=="state" or "raw" in rel.parts or "venue-template" in rel.parts or "build" in rel.parts or rel.parts[:2]==("experiments","runs"):continue
        d.update(rel.as_posix().encode());d.update(b"\0");d.update(path.read_bytes());d.update(b"\0")
    d.update(gate.encode("ascii"));return d.hexdigest()
def initialize(args):
    slug=validate_slug(args.project);dest=project_dir(slug)
    if dest.exists():raise ResearchCtlError(f"Project already exists: {dest}")
    defaults=read_json(DEFAULTS_PATH);count=args.paper_count or int(defaults["paper_count"])
    if not 1<=count<=20:raise ResearchCtlError("paper-count must be between 1 and 20")
    for rel in ["state","intake","program","evidence/claude-science","data/raw","data/processed","experiments/runs","claims","reports","reviews/codex","reviews/independent"]:(dest/rel).mkdir(parents=True,exist_ok=True)
    write_json(dest/"intake"/"constraints.json",{"schema_version":"1.0","status":"needs_user_input","research_goal":None,"preferred_domains":["AI","robotics","mechanical engineering"],"candidate_application_routes":["France PhD or industrial doctorate","Spain PhD or industrial doctorate","Netherlands EngD","United Kingdom PhD","Japan PhD","Hong Kong PhD","PhD by publication where legally and institutionally available"],"time_horizon_years":None,"weekly_hours":None,"cash_budget_usd":None,"cloud_compute_budget_usd":defaults["compute"]["default_cloud_budget_usd"],"local_compute":{"gpu":None,"ram_gb":None,"storage_gb":None},"equipment":"No institutional laboratory assumed","data_constraint":"Prefer public or authorized datasets","ranking_weights":{"novelty_and_doctoral_depth":None,"feasibility_without_lab":None,"funded_position_supply":None,"competition":None,"job_market_and_salary":None,"background_fit":None},"excluded_domains":[],"ethics_or_legal_constraints":[],"notes":[]})
    write_json(dest/"intake"/"capabilities.json",{"schema_version":"1.0","status":"unverified","os":"Windows 11 with WSL2 recommended","orchestrator":"API-first Python orchestrator","semantic_planner":"Claude/Anthropic read-only","persistent_writer":"OpenAI/Codex","independent_auditor":"model family different from persistent writer","evidence_workbench":"Claude Science export contract","checked_at":None,"environment_report":None})
    write_json(dest/"state"/"output-provenance.json",{"schema_version":"1.0","files":{}})
    for rel in ["evidence/search-log.jsonl","data/datasets.jsonl","experiments/registry.jsonl"]:write_text(dest/rel,"")
    write_text(dest/"claims/claim-evidence.csv","claim_id,paper_id,claim,evidence_ids,analysis_ids,support,uncertainty,status\n")
    for n in range(1,count+1):
        pid=f"P{n:02d}";paper=dest/"papers"/pid
        for rel in ["manuscript","figures","tables","supplement","submission-materials","reviews"]:(paper/rel).mkdir(parents=True,exist_ok=True)
        write_json(paper/"paper-contract.json",{"schema_version":"1.0","paper_id":pid,"working_title":"","research_question":"","distinct_contribution":"","relationship_to_core":"","relationship_to_extension":"","hypotheses":[],"datasets":[],"experiments":[],"falsification_conditions":[],"dependencies":[],"target_venues":[],"status":"draft"})
    state={"schema_version":"2.0","project":slug,"created_at":now(),"updated_at":now(),"stage_index":0,"stage":"intake","gate":"G0","status":"awaiting_work","active_paper":"P01","paper_count":count,"paper_statuses":{f"P{n:02d}":"active" if n==1 else "planned" for n in range(1,count+1)},"approved_gates":[],"approvals":[],"history":[{"at":now(),"event":"project_initialized","stage":"intake"}]};save_state(slug,state)
    venue_id=args.venue or defaults.get("trial_venue")
    if venue_id:set_venue_values(slug,"P01",venue_id)
    print(f"Initialized {dest}")
def print_status(args):
    state=load_state(args.project);errors=gate_errors(args.project,state["gate"]);out={**state,"gate_ready":not errors and state["gate"] is not None,"gate_errors":errors}
    if args.json:print(json.dumps(out,ensure_ascii=False,indent=2));return
    print(f"Project: {state['project']}\nStage:   {state['stage']}\nGate:    {state['gate'] or '-'}\nStatus:  {state['status']}\nReady:   {'yes' if not errors else 'no'}");[print(f"  - {e}") for e in errors]
def check_gate(args):
    state=load_state(args.project);gate=args.gate or state["gate"];errors=gate_errors(args.project,gate)
    if errors:[print(f"  - {e}") for e in errors];raise ResearchCtlError(f"{gate} is not ready: {len(errors)} requirement(s) remain")
    print(f"{gate} artifact and quality checks passed.")
def mark_ready(args):
    state=load_state(args.project);gate=state["gate"]
    if gate is None:raise ResearchCtlError("Project is already submission-ready.")
    errors=gate_errors(args.project,gate)
    if errors:raise ResearchCtlError(f"{gate} cannot be marked ready: {len(errors)} requirement(s) remain")
    state["status"]="awaiting_approval";state["history"].append({"at":now(),"event":"gate_marked_ready","gate":gate,"note":args.note});save_state(args.project,state);print(f"{gate} is awaiting explicit human approval.")
def approve(args):
    state=load_state(args.project);gate=state["gate"]
    if gate!=args.gate:raise ResearchCtlError(f"Current gate is {gate}, not {args.gate}.")
    if state["status"]!="awaiting_approval":raise ResearchCtlError("Run gate-check and ready before approval.")
    if gate_errors(args.project,gate):raise ResearchCtlError("Gate artifacts or quality report changed and no longer pass checks.")
    if not args.actor.strip():raise ResearchCtlError("actor must identify the human approver")
    approval={"gate":gate,"actor":args.actor.strip(),"at":now(),"note":args.note,"artifact_sha256":artifact_hash(args.project,gate)}
    if gate=="G3":
        p=project_dir(args.project);approval["experiment_plan_sha256"]=file_sha256(p/"experiments/plan.json");approval["experiment_budget_sha256"]=file_sha256(p/"experiments/budget.json")
    key=gate
    if gate=="G5":approval["paper_id"]=state["active_paper"];key=f"G5:{state['active_paper']}"
    state["approvals"].append(approval)
    if key not in state["approved_gates"]:state["approved_gates"].append(key)
    state["status"]="approved";state["history"].append({"at":now(),"event":"gate_approved","gate":gate});save_state(args.project,state);print(f"Recorded human approval for {gate}. Run advance to continue.")
def advance(args):
    state=load_state(args.project);gate=state["gate"]
    if gate is None:raise ResearchCtlError("Project is already at the final stage.")
    key=f"G5:{state['active_paper']}" if gate=="G5" else gate
    if state["status"]!="approved" or key not in state["approved_gates"]:raise ResearchCtlError(f"{gate} has not been approved.")
    matching=next((x for x in reversed(state.get("approvals",[])) if x.get("gate")==gate and (gate!="G5" or x.get("paper_id")==state["active_paper"])),None)
    if not matching or matching.get("artifact_sha256")!=artifact_hash(args.project,gate):raise ResearchCtlError("Artifacts changed after approval; run gate-check, ready and approve again.")
    if gate=="G5":
        done=state["active_paper"];state.setdefault("paper_statuses",{})[done]="submission_ready";remaining=[f"P{n:02d}" for n in range(1,int(state["paper_count"])+1) if state["paper_statuses"].get(f"P{n:02d}")!="submission_ready"]
        if remaining:
            nxt=remaining[0];state["active_paper"]=nxt;state["paper_statuses"][nxt]="active";state["status"]="awaiting_work";state["history"].append({"at":now(),"event":"paper_advanced","from":done,"to":nxt});save_state(args.project,state);print(f"Marked {done} submission-ready; continuing G5 with {nxt}.");return
    i=state["stage_index"]+1;next_stage=STAGES[i];prev=state["stage"];state["stage_index"]=i;state["stage"]=next_stage["name"];state["gate"]=next_stage["gate"];state["status"]="submission_ready" if next_stage["gate"] is None else "awaiting_work";state["history"].append({"at":now(),"event":"stage_advanced","from":prev,"to":next_stage["name"]});save_state(args.project,state);print(f"Advanced to {next_stage['name']}.")
def set_venue_values(slug,paper_id,venue_id):
    validate_paper_id(paper_id);source=ROOT/"venues"/venue_id/"venue.json"
    if not source.is_file():raise ResearchCtlError(f"Unknown venue manifest: {venue_id}")
    target=project_dir(slug)/"papers"/paper_id
    if not target.is_dir():raise ResearchCtlError(f"Unknown paper: {paper_id}")
    m=read_json(source);m["selected_at"]=now();m["selection_status"]="trial" if m.get("trial_only") else "candidate";write_json(target/"venue.json",m)
def set_venue(args):load_state(args.project);set_venue_values(args.project,args.paper,args.venue);print(f"Set {args.paper} venue to {args.venue}; current JCR Q1 verification remains required.")
def list_stages(_):print(json.dumps(STAGES,indent=2))
def parser():
    root=argparse.ArgumentParser(description=__doc__);cmd=root.add_subparsers(dest="command",required=True)
    p=cmd.add_parser("init");p.add_argument("--project",required=True);p.add_argument("--paper-count",type=int);p.add_argument("--venue",default=None);p.set_defaults(func=initialize)
    p=cmd.add_parser("status");p.add_argument("--project",required=True);p.add_argument("--json",action="store_true");p.set_defaults(func=print_status)
    p=cmd.add_parser("gate-check");p.add_argument("--project",required=True);p.add_argument("--gate");p.set_defaults(func=check_gate)
    p=cmd.add_parser("ready");p.add_argument("--project",required=True);p.add_argument("--note",default="");p.set_defaults(func=mark_ready)
    p=cmd.add_parser("approve");p.add_argument("--project",required=True);p.add_argument("--gate",required=True);p.add_argument("--actor",required=True);p.add_argument("--note",default="");p.set_defaults(func=approve)
    p=cmd.add_parser("advance");p.add_argument("--project",required=True);p.set_defaults(func=advance)
    p=cmd.add_parser("set-venue");p.add_argument("--project",required=True);p.add_argument("--paper",required=True);p.add_argument("--venue",required=True);p.set_defaults(func=set_venue)
    p=cmd.add_parser("stages");p.set_defaults(func=list_stages);return root
def main(argv:Iterable[str]|None=None):
    try:args=parser().parse_args(argv);args.func(args);return 0
    except ResearchCtlError as exc:print(f"error: {exc}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
