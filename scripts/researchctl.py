#!/usr/bin/env python3
"""Human-gated Doctoral Research OS state manager with publication-quality floors."""
from __future__ import annotations
import argparse,csv,hashlib,json,os,re,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Iterable
ROOT=Path(__file__).resolve().parents[1]; PROJECTS_ROOT=ROOT/"projects"; DEFAULTS_PATH=ROOT/"config/defaults.json"
if __package__ in {None,""}:sys.path.insert(0,str(ROOT))
STAGES=[{"name":"intake","gate":"G0"},{"name":"topic-intelligence","gate":"G1"},{"name":"paper-architecture","gate":"G2"},{"name":"experiment-design","gate":"G3"},{"name":"experiment-execution","gate":"G4"},{"name":"writing-and-review","gate":"G5"},{"name":"submission-ready","gate":None}]
SLUG_RE=re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$"); PAPER_RE=re.compile(r"^P[0-9]{2}$")
from scripts.paper_execution import artifact_path as experiment_path

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
def audit_document_valid(path,audit,errors,final=False):
    from scripts.literature_source_tasks import RESPONSE_FIELDS,validate_response_fields
    expected={"verdict","fatal_findings","major_findings","minor_findings","missing_evidence","remediation_steps","uncertainty"};valid=True
    if not expected<=set(audit) or set(audit)-expected-{"novelty_assessment"}-RESPONSE_FIELDS:errors.append(f"{path.name}: audit contains missing required or unsupported fields");valid=False
    try:validate_response_fields(audit)
    except ValueError as exc:errors.append(f"{path.name}: {exc}");valid=False
    if audit.get("verdict") not in {"block","revise","pass-with-conditions"}:errors.append(f"{path.name}: invalid verdict");valid=False
    for field in expected-{"verdict"}:
        value=audit.get(field)
        if not isinstance(value,list) or any(not isinstance(item,str) or not item.strip() for item in value):errors.append(f"{path.name}: {field} must be an array of non-empty strings");valid=False
    if final:
        blockers=any(audit.get(field) for field in ("fatal_findings","major_findings","missing_evidence","remediation_steps"))
        if audit.get("verdict")!="pass-with-conditions" or blockers:errors.append(f"{path.name}: final audit must pass with no fatal/major findings, missing evidence or remediation steps");valid=False
    return valid
def independent_audit_errors(project,gate,errors,paper_id=None,warnings=None):
    from scripts.paper_execution import enabled, selected
    if enabled(project) and gate in {"G3", "G4"}:paper_id=selected(project)
    from scripts.review_receipts import validate_gate
    diagnostics=validate_gate(project,gate,paper_id)
    if not nonempty(project/"reviews"/"decision-log.md"):diagnostics.append("reviews/decision-log.md must disposition independent findings")
    if warnings is not None:warnings.extend("stage review observation: "+issue for issue in diagnostics)
def quality_path(project,gate,paper_id=None):
    return {"G1":project/"program"/"quality-G1.json","G2":project/"papers"/str(paper_id)/"quality-G2.json","G3":experiment_path(project, 'experiments/quality-G3.json'),"G4":experiment_path(project, 'reports/quality-G4.json'),"G5":project/"papers"/str(paper_id)/"reviews"/"quality-G5.json"}[gate]
def quality_errors(project,gate,errors,paper_id=None,warnings=None):
    try:from scripts.quality_gate import validate_file
    except ImportError as exc:errors.append(f"quality gate validator unavailable: {exc}");return
    path=quality_path(project,gate,paper_id)
    if not path.is_file():
        if warnings is not None:warnings.append(f"{path}: no optional quality assessment recorded")
        return
    errors.extend(f"{path}: {e}" for e in validate_file(path,gate,project=project,require_facts=True,warnings=warnings))

def summarize_gate_errors(errors):
    """Group repeated checks for presentation without changing gate authority.

    Only known shared causes are combined. Unrecognized issues keep their exact
    text and separate identity; each original check remains available below it.
    Counts describe validator messages, never independent scientific problems.
    """
    groups = {}
    rules = (
        ("novelty_search", ("search_saturation", "saturation search", "saturation round", "citation chaining"),
         "文献检索与创新主张仍有待核对", "根据受影响的主张补查文献，并如实更新当前检索状态。"),
        ("literature_screening", ("requires a recorded screening decision",),
         "文献检索结果尚未完成筛选记录", "集中核对检索结果，记录纳入、排除和待定理由。"),
        ("source_integrity", ("source hash changed", "preregistered input changed", "output changed", "provenance"),
         "证据来源或冻结输入需要核对", "先定位变更的原始来源和运行记录，保留原版本后重新核验受影响证据。"),
        ("data_rights", ("license", "data rights", "research-use rights"),
         "数据使用依据尚未满足", "核对受影响数据集的使用条款与授权，或选择已获准的替代数据。"),
        ("experiment_protocol", ("power-analysis", "preregistration", "experiment design", "exploration."),
         "当前研究方案仍有缺口", "围绕关键未知补齐当前研究强度所需方案；探索无需伪造正式验证参数。"),
        ("experiment_execution", ("executor receipt", "registered attempt", "experiment registry", "execution pending"),
         "实验执行证据尚未齐备", "检查原生执行记录和完整日志，保留失败结果并决定下一项区分性检验。"),
        ("claim_support", ("claim-evidence", "claim evidence", "critical test", "unsupported claim"),
         "主张与区分性证据尚未对应", "定位受影响的主张、竞争解释和实际结果，补证据或收窄结论。"),
        ("independent_review", ("independent review", "independent audit"),
         "当前材料仍需独立审查", "完成当前材料的独立审查；发现实质问题后修复并复查，投稿前完成三视角互盲审查。"),
        ("submission_preparation", ("submission preparation", "academic-style", "venue-compliance", "pre-submission criteria"),
         "投稿准备尚未完成", "科学写作完成后集中处理投稿格式、风格、期刊要求和打包。"),
    )
    for error in errors:
        message = str(error)
        match = next((row for row in rules if any(term in message.casefold() for term in row[1])), None)
        identifier, title, action = ((match[0], match[2], match[3]) if match else
            ("check-" + hashlib.sha256(message.encode("utf-8")).hexdigest()[:16], message, "按原始检查定位并解决缺口。"))
        group = groups.setdefault(identifier, {"id": identifier, "title": title, "next_action": action, "count": 0, "checks": []})
        group["count"] += 1
        if message not in group["checks"]:
            group["checks"].append(message)
    return list(groups.values())

def _observe(warnings, label, check):
    if warnings is None:return
    try:warnings.extend(label+": "+str(issue) for issue in check())
    except (OSError,ValueError,RuntimeError,KeyError,TypeError,ImportError) as exc:warnings.append(label+": "+str(exc))


def paper_scientific_errors(project, pid):
    """A: factual evidence and preservation checks shared by both writing phases."""
    from scripts import manuscript_audit,ref_verify_adapter,statistical_reporting,revision_integrity,figure_provenance,manuscript_hygiene,literature_source_tasks
    paper=project/"papers"/pid;errors=[]
    for label,check in (
        ("paper-facts",lambda:manuscript_audit.validate_saved_report(paper)),
        ("citation claims",lambda:ref_verify_adapter.validate_saved_report(paper)),
        ("source evidence conflicts",lambda:literature_source_tasks.integrity_errors(project,pid)),
        ("statistical reporting",lambda:statistical_reporting.validate_saved_report(project,pid)),
        ("revision integrity",lambda:revision_integrity.validate_saved_report(paper,include_ledger=False)),
        ("figure provenance",lambda:figure_provenance.validate_figure_provenance(project,paper)),
        ("preserved originals",lambda:manuscript_hygiene.integrity_errors(project,pid))):
        try:errors.extend(f"{pid} {label}: {issue}" for issue in check())
        except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:errors.append(f"{pid} {label}: {exc}")
    if not any(nonempty(paper/"manuscript"/name) for name in ("main.tex","main.docx")):
        errors.append(f"{pid} requires a scientific manuscript")
    return errors


def paper_observations(project,pid,warnings):
    """C: diagnostics never acquire data, call a model or grant scientific approval."""
    if warnings is None:return
    from scripts import academic_style,manuscript_hygiene,manuscript_language,statistical_watermarks,pre_submission_review,figure_layout,revision_trace,revision_ledger,docx_revision,rebuttal_triage
    paper=project/"papers"/pid
    for label,check in (
        ("academic style",lambda:academic_style.validate_saved_audit(paper)),
        ("manuscript hygiene",lambda:manuscript_hygiene.validate_saved_report(project,pid)),
        ("language observation",lambda:manuscript_language.analyze_submission(paper).get("errors",[])),
        ("watermark observation",lambda:statistical_watermarks.validate_saved_report(project,pid)),
        ("pre-submission suggestions",lambda:pre_submission_review.validate_saved_report(paper)),
        ("figure layout",lambda:figure_layout.validate_saved_figures(paper)),
        ("revision trace",lambda:revision_trace.validate_saved_report(paper)),
        ("edit ledger",lambda:revision_ledger.validate_saved_report(project,pid,require_when_changed=True)),
        ("Word revisions",lambda:docx_revision.validate_saved_report(project,pid)),
        ("concern cards",lambda:rebuttal_triage.validate_saved_report(paper))):
        _observe(warnings,f"{pid} {label}",check)


def gate_errors(slug,gate,*,warnings=None):
    project=project_dir(slug);errors=[]
    from scripts.paper_execution import papers as selected_papers
    if gate is None:return errors
    if gate in {"G2","G5"}:
        from scripts.research_design import validate_portfolio_evidence
        pid=read_json(state_path(slug)).get("active_paper") if gate=="G5" else None
        errors.extend(validate_portfolio_evidence(project,pid,gate=gate))
    if gate in {"G1","G2","G5"}:
        from scripts.innovation_screening import validate_novelty_gate
        matrix=load_nonempty_json(project/"program/novelty-claim-matrix.json",errors)
        originality=load_nonempty_json(project/"program/originality-audit.json",errors)
        if matrix and originality:
            pid=read_json(state_path(slug)).get("active_paper") if gate=="G5" else None
            errors.extend(validate_novelty_gate(project,matrix,originality,gate,pid))
    from scripts.scientific_scope import validate as validate_scientific_scope
    errors.extend(validate_scientific_scope(project,gate,read_json(state_path(slug)).get("active_paper")))
    from scripts.research_phase import exploratory
    try:
        exploring = gate in {"G3", "G4"} and exploratory(project)
    except (OSError, ValueError) as exc:
        return errors + ["research phase: " + str(exc)]
    if gate in {"G3","G4","G5"} and not exploring:
        from scripts.experiment_evidence import validate_scientific_bindings
        state=read_json(state_path(slug))
        selected=[state.get("active_paper")] if gate=="G5" else selected_papers(project,gate)
        for pid in selected:errors.extend(validate_scientific_bindings(project,pid,gate))
    if gate in {"G3","G4","G5"}:
        from scripts.empirical_workflow import gate_errors as empirical_errors
        if not exploring:
            errors.extend(empirical_errors(project,gate,read_json(state_path(slug)).get("active_paper")))
        from scripts.primary_recovery import gate_errors as primary_recovery_errors
        errors.extend(primary_recovery_errors(project,gate,read_json(state_path(slug)).get("active_paper")))
    if gate in {"G2","G3","G4","G5"}:
        from scripts.research_identity import validate as validate_research_identity
        state=read_json(state_path(slug))
        selected=[state.get("active_paper")] if gate=="G5" else selected_papers(project,gate)
        for paper_id in selected:errors.extend(validate_research_identity(project,paper_id,"G3" if exploring else gate))
    if gate != "G0":
        from scripts.research_extensions import gate_errors as extension_errors
        errors.extend(f"research extensions: {x}" for x in extension_errors(project))
        from scripts.research_increments import gate_errors as increment_errors
        errors.extend(increment_errors(project, gate, read_json(project/"state/run.json").get("active_paper")))
    if gate=="G0":
        c=load_nonempty_json(project/"intake"/"constraints.json",errors)
        if c:
            try:
                from scripts.intake_validation import validate_constraints
                errors.extend(f"intake/constraints.json: {x}" for x in validate_constraints(c))
            except ImportError as exc:errors.append(f"intake validator unavailable: {exc}")
        return errors
    if gate=="G1":
        from scripts.direction_evidence import validate_saved as validate_direction_ranking
        errors.extend(validate_direction_ranking(project))
        searches=jsonl_objects(project/"evidence"/"search-log.jsonl",errors)
        ai4science_path=project/"evidence"/"ai4science-ledger.jsonl"
        if ai4science_path.is_file() and ai4science_path.read_text(encoding="utf-8").strip():
            try:
                from scripts.ai4science_evidence import read_ledger,validate
                errors.extend(f"evidence/ai4science-ledger.jsonl: {x}" for x in validate(project,read_ledger(ai4science_path)))
            except (ImportError,RuntimeError) as exc:errors.append(f"AI4Science evidence validator unavailable: {exc}")
        s=load_nonempty_json(project/"program"/"topic-shortlist.json",errors)
        if s:
            cs=s.get("candidates") or s.get("topics")
            if not isinstance(cs,list) or len(cs)<3:errors.append("topic-shortlist.json requires at least three candidates")
            try:
                from scripts.research_design import validate_selected_direction_cloud_feasibility
                errors.extend(f"program/topic-shortlist.json: {x}" for x in validate_selected_direction_cloud_feasibility(s,project=project))
            except ImportError as exc:errors.append(f"cloud feasibility validator unavailable: {exc}")
        core_thesis=load_nonempty_json(project/"program/core-thesis.json",errors)
        extension_thesis=load_nonempty_json(project/"program/extension-thesis.json",errors)
        if core_thesis and extension_thesis:
            try:
                from scripts.research_design import validate_theme_independence
                errors.extend(f"program/theme-independence: {x}" for x in validate_theme_independence(core_thesis,extension_thesis))
            except ImportError as exc:errors.append(f"theme independence validator unavailable: {exc}")
        originality=load_nonempty_json(project/"program"/"originality-audit.json",errors)
        if originality:
            try:
                from scripts.research_design import validate_originality_audit,validate_search_log
                errors.extend(f"program/originality-audit.json: {x}" for x in validate_originality_audit(originality))
                errors.extend(f"evidence/search-log.jsonl: {x}" for x in validate_search_log(searches,originality))
            except ImportError as exc:errors.append(f"originality validator unavailable: {exc}")
            try:
                from scripts.literature_evidence import validate_search_evidence
                errors.extend(f"evidence/search-log.jsonl: {x}" for x in validate_search_evidence(project,searches))
            except ImportError as exc:errors.append(f"literature evidence validator unavailable: {exc}")
            novelty_matrix=load_nonempty_json(project/"program"/"novelty-claim-matrix.json",errors)
            if novelty_matrix:
                try:
                    from scripts.research_quality import validate_novelty_claim_matrix
                    errors.extend(f"program/novelty-claim-matrix.json: {x}" for x in validate_novelty_claim_matrix(novelty_matrix,originality,searches,project=project))
                except ImportError as exc:errors.append(f"novelty claim-matrix validator unavailable: {exc}")
        if not nonempty(project/"program"/"topic-decision.md"):errors.append("program/topic-decision.md is required")
        try:
            from scripts.research_candidates import validate_saved_register
            errors.extend("specific-topic hypotheses: " + issue for issue in validate_saved_register(project))
        except ImportError as exc:errors.append(f"hypothesis validator unavailable: {exc}")
        quality_errors(project,gate,errors,warnings=warnings);independent_audit_errors(project,gate,errors,warnings=warnings);return errors
    if gate=="G2":
        paper_map=load_nonempty_json(project/"program"/"paper-map.json",errors);state=read_json(state_path(slug));dirs=sorted((project/"papers").glob("P[0-9][0-9]"))
        venue_observations=[]
        venue_registry=load_nonempty_json(project/"program"/"venue-candidates.json",venue_observations);venue_names_by_paper={}
        if venue_registry:
            try:
                from scripts.venue_candidates import validate_registry
                venue_observations.extend(f"program/venue-candidates.json: {x}" for x in validate_registry(project,venue_registry))
                for item in venue_registry.get("papers",[]) if isinstance(venue_registry.get("papers"),list) else []:
                    if isinstance(item,dict) and item.get("paper_id"):
                        values=item.get("candidates",[]);values=values if isinstance(values,list) else []
                        venue_names_by_paper[str(item["paper_id"])]=set(str(candidate.get("name")) for candidate in values if isinstance(candidate,dict) and candidate.get("name"))
            except ImportError as exc:venue_observations.append(f"venue candidate validator unavailable: {exc}")
        try:
            from scripts.journal_screening import validate_saved_report
            venue_observations.extend(f"program/journal-screening.json: {x}" for x in validate_saved_report(project))
        except ImportError as exc:venue_observations.append(f"journal screening validator unavailable: {exc}")
        if warnings is not None:warnings.extend(venue_observations)
        if len(dirs)!=state.get("paper_count"):errors.append(f"expected exactly {state.get('paper_count')} paper directories, found {len(dirs)}")
        originality=load_nonempty_json(project/"program"/"originality-audit.json",errors)
        prior_work_values=(originality or {}).get("closest_prior_work",[]);prior_work_values=prior_work_values if isinstance(prior_work_values,list) else []
        prior_work_ids={str(item.get("id")) for item in prior_work_values if isinstance(item,dict) and item.get("id")}
        mapped_values=(paper_map or {}).get("papers",[]);mapped_values=mapped_values if isinstance(mapped_values,list) else []
        mapped_claims={};mapped_targets={}
        for item in mapped_values:
            if not isinstance(item,dict) or not item.get("paper_id"):continue
            claim_values=item.get("unique_claim_ids",[]);claim_values=claim_values if isinstance(claim_values,list) else []
            mapped_claims[str(item.get("paper_id"))]=set(str(claim) for claim in claim_values)
            mapped_targets[str(item.get("paper_id"))]=str(item.get("target_jcr_quartile") or "").upper()
        try:
            from scripts.research_design import validate_paper_contract,validate_paper_map,validate_theme_independence,validate_theme_mapping
            if paper_map:errors.extend(f"program/paper-map.json: {x}" for x in validate_paper_map(paper_map,(pd.name for pd in dirs)))
            core_thesis=load_nonempty_json(project/"program/core-thesis.json",errors);extension_thesis=load_nonempty_json(project/"program/extension-thesis.json",errors)
            if core_thesis and extension_thesis:
                errors.extend(f"program/theme-independence: {x}" for x in validate_theme_independence(core_thesis,extension_thesis))
                if paper_map:errors.extend(f"program/paper-map.json: {x}" for x in validate_theme_mapping(paper_map,core_thesis,extension_thesis))
        except ImportError as exc:errors.append(f"paper architecture validator unavailable: {exc}");validate_paper_contract=None
        for pd in dirs:
            c=load_nonempty_json(pd/"paper-contract.json",errors)
            if c and validate_paper_contract:
                from scripts.study_routes import route
                errors.extend(f"{pd.name}/paper-contract.json: {x}" for x in validate_paper_contract(c,pd.name,study_route=route(project,pd.name)))
            if c:
                contract_target=str(c.get("target_jcr_quartile") or "").upper()
                if warnings is not None and mapped_targets.get(pd.name)!=contract_target:warnings.append(f"{pd.name} planning target JCR quartile differs from program/paper-map.json")
                contract_venue_values=c.get("target_venues",[]);contract_venue_values=contract_venue_values if isinstance(contract_venue_values,list) else []
                contract_venue_names=set(str(item.get("name")) for item in contract_venue_values if isinstance(item,dict) and item.get("name"))
                if warnings is not None and venue_names_by_paper.get(pd.name,set())!=contract_venue_names:warnings.append(f"{pd.name} provisional target venues differ from program/venue-candidates.json")
                boundary=c.get("originality_boundary") if isinstance(c.get("originality_boundary"),dict) else {};independence=c.get("independence") if isinstance(c.get("independence"),dict) else {}
                referenced_values=boundary.get("closest_prior_work_ids",[]);referenced_values=referenced_values if isinstance(referenced_values,list) else []
                referenced=set(str(item) for item in referenced_values);missing=sorted(referenced-prior_work_ids)
                if missing:errors.append(f"{pd.name}/paper-contract.json references prior work absent from G1 originality audit: {', '.join(missing)}")
                contract_claim_values=independence.get("unique_claim_ids",[]);contract_claim_values=contract_claim_values if isinstance(contract_claim_values,list) else []
                contract_claims=set(str(item) for item in contract_claim_values)
                if mapped_claims.get(pd.name,set())!=contract_claims:errors.append(f"{pd.name} unique claim IDs must match program/paper-map.json")
                quality_errors(project,gate,errors,pd.name,warnings=warnings)
        independent_audit_errors(project,gate,errors,warnings=warnings);return errors
    if gate=="G3":
        from scripts.research_phase import exploratory, exposure_errors
        if exploratory(project):
            from scripts.research_quality import validate_g3_quality
            errors.extend(validate_g3_quality(project))
            independent_audit_errors(project,gate,errors,warnings=warnings)
            return errors
        errors.extend(exposure_errors(project))
        from scripts.paper_execution import dataset_snapshot
        from scripts import study_routes
        manifest_path=dataset_snapshot(project)
        empirical=any(study_routes.route(project,p)=="empirical" for p in selected_papers(project,gate))
        datasets=jsonl_objects(manifest_path,errors) if empirical or (manifest_path.is_file() and manifest_path.stat().st_size) else []
        if not datasets and any(study_routes.route(project,p)=="empirical" for p in selected_papers(project,gate)):
            errors.append("at least one licensed dataset manifest is required")
        try:
            from scripts.dataset_fetch import validate_manifest
            for i,d in enumerate(datasets,1):
                for issue in validate_manifest(d):errors.append(f"datasets.jsonl entry {i}: {issue}")
                license_value=d.get("license") if isinstance(d.get("license"),dict) else {}
                download_value=d.get("download") if isinstance(d.get("download"),dict) else {}
                from scripts.dataset_fetch import license_errors
                errors.extend(f"datasets.jsonl entry {i}: {issue}" for issue in license_errors(d, project=project))
                if download_value.get("sha256")=="pending":errors.append(f"datasets.jsonl entry {i}: SHA-256 remains pending")
        except ImportError as exc:errors.append(f"dataset validator unavailable: {exc}")
        plan=load_nonempty_json(experiment_path(project, 'experiments/plan.json'),errors)
        if plan:
            try:
                from scripts.experiment_runner import validate_plan
                errors.extend(f"experiments/plan.json: {x}" for x in validate_plan(plan))
                from scripts.paper_execution import plan_errors
                errors.extend(plan_errors(project,plan))
            except ImportError as exc:errors.append(f"experiment plan validator unavailable: {exc}")
            try:
                from scripts.research_design import validate_experiment_design
                run_values=plan.get("runs",[]);run_values=run_values if isinstance(run_values,list) else []
                plan_runs={str(run.get("run_id")):run for run in run_values if isinstance(run,dict) and run.get("run_id")}
                manifest_ids={str(item.get("dataset_id")) for item in datasets if item.get("dataset_id")}
                paper_dirs=sorted((project/"papers").glob("P[0-9][0-9]"))
                state=read_json(state_path(slug))
                if len(paper_dirs)!=state.get("paper_count"):errors.append(f"expected exactly {state.get('paper_count')} paper directories, found {len(paper_dirs)}")
                paper_dirs=[p for p in paper_dirs if p.name in selected_papers(project,gate)]
                for paper_dir in paper_dirs:
                    contract=load_nonempty_json(paper_dir/"paper-contract.json",errors)
                    if study_routes.route(project,paper_dir.name)!="empirical":
                        errors.extend(f"{paper_dir.name} study route: {x}" for x in study_routes.plan_errors(project,paper_dir.name))
                        continue
                    experiment_dir=paper_dir/"experiments";design_paths=sorted(experiment_dir.glob("*.json"))
                    if not design_paths:errors.append(f"missing or empty: {experiment_dir}/*.json");continue
                    found_design_ids=set();assigned_run_ids=set();duplicate_run_ids=set()
                    for design_path in design_paths:
                        design=load_nonempty_json(design_path,errors)
                        if not design:continue
                        rel=design_path.relative_to(project)
                        errors.extend(f"{rel}: {x}" for x in validate_experiment_design(design,paper_dir.name,plan_runs))
                        design_id=design.get("design_id")
                        if isinstance(design_id,str) and design_id:
                            if design_id in found_design_ids:errors.append(f"{paper_dir.name} repeats experiment design_id {design_id}")
                            found_design_ids.add(design_id)
                        design_run_values=design.get("run_ids",[]);design_run_values=design_run_values if isinstance(design_run_values,list) else []
                        design_run_ids={str(item) for item in design_run_values}
                        duplicate_run_ids.update(assigned_run_ids&design_run_ids);assigned_run_ids.update(design_run_ids)
                        if contract:
                            hypothesis_values=contract.get("hypotheses",[]);hypothesis_values=hypothesis_values if isinstance(hypothesis_values,list) else []
                            contract_hypotheses={str(item.get("id")) for item in hypothesis_values if isinstance(item,dict) and item.get("id")}
                            design_hypotheses=design.get("hypothesis_ids",[]);design_hypotheses=design_hypotheses if isinstance(design_hypotheses,list) else []
                            missing=sorted(set(str(item) for item in design_hypotheses)-contract_hypotheses)
                            if missing:errors.append(f"{rel} references unknown hypotheses: {', '.join(missing)}")
                            data_protocol=design.get("data_protocol") if isinstance(design.get("data_protocol"),dict) else {}
                            contract_dataset_values=contract.get("datasets",[]);contract_dataset_values=contract_dataset_values if isinstance(contract_dataset_values,list) else []
                            design_dataset_values=data_protocol.get("datasets",[]);design_dataset_values=design_dataset_values if isinstance(design_dataset_values,list) else []
                            contract_datasets=set(str(item) for item in contract_dataset_values);design_datasets=set(str(item) for item in design_dataset_values)
                            missing_contract=sorted(design_datasets-contract_datasets)
                            if missing_contract:errors.append(f"{rel} datasets absent from paper-contract.json: {', '.join(missing_contract)}")
                            missing_manifest=sorted(design_datasets-manifest_ids)
                            if missing_manifest:errors.append(f"{rel} datasets absent from data/datasets.jsonl: {', '.join(missing_manifest)}")
                    if duplicate_run_ids:errors.append(f"{paper_dir.name} assigns runs to multiple designs: {', '.join(sorted(duplicate_run_ids))}")
                    paper_run_ids={run_id for run_id,run in plan_runs.items() if run.get("paper_id")==paper_dir.name}
                    if assigned_run_ids!=paper_run_ids:
                        missing=sorted(paper_run_ids-assigned_run_ids);extra=sorted(assigned_run_ids-paper_run_ids)
                        if missing:errors.append(f"{paper_dir.name} experiment designs omit planned runs: {', '.join(missing)}")
                        if extra:errors.append(f"{paper_dir.name} experiment designs include non-paper runs: {', '.join(extra)}")
                    if contract:
                        planned=contract.get("planned_experiments") if isinstance(contract.get("planned_experiments"),dict) else {}
                        planned_values=planned.get("design_ids",[]);planned_values=planned_values if isinstance(planned_values,list) else []
                        planned_designs=set(str(item) for item in planned_values)
                        if found_design_ids!=planned_designs:
                            missing=sorted(planned_designs-found_design_ids);extra=sorted(found_design_ids-planned_designs)
                            if missing:errors.append(f"{paper_dir.name} is missing contracted experiment designs: {', '.join(missing)}")
                            if extra:errors.append(f"{paper_dir.name} has uncontracted experiment designs: {', '.join(extra)}")
            except ImportError as exc:errors.append(f"paper experiment-design validator unavailable: {exc}")
        budget=load_nonempty_json(experiment_path(project, 'experiments/budget.json'),errors)
        if budget:
            if budget.get("status")!="ready_for_review":errors.append("experiments/budget.json status must be ready_for_review")
            ceiling=budget.get("hard_ceiling_usd")
            if not isinstance(ceiling,(int,float)) or isinstance(ceiling,bool) or ceiling<0:errors.append("experiments/budget.json needs non-negative hard_ceiling_usd")
            if plan:
                from scripts.experiment_runner import ExperimentError,compute_budget_authority
                try:compute_budget_authority(project,budget,plan)
                except ExperimentError as exc:errors.append("experiment compute authority: "+str(exc))
        try:
            from scripts.research_quality import ResearchQualityError,validate_g3_quality
            errors.extend(f"research quality: {x}" for x in validate_g3_quality(project))
        except ImportError as exc:errors.append(f"research-quality validator unavailable: {exc}")
        except ResearchQualityError as exc:errors.append(f"research-quality evidence is invalid: {exc}")
        quality_errors(project,gate,errors,warnings=warnings);independent_audit_errors(project,gate,errors,warnings=warnings);return errors
    if gate=="G4":
        from scripts.research_phase import exploratory
        if exploratory(project):
            from scripts.research_quality import validate_g4_quality
            errors.extend(validate_g4_quality(project))
            independent_audit_errors(project,gate,errors,warnings=warnings)
            return errors
        registry=jsonl_objects(experiment_path(project, 'experiments/registry.jsonl'),errors)
        if not registry:errors.append("at least one experiment registry entry is required")
        plan=load_nonempty_json(experiment_path(project, 'experiments/plan.json'),errors)
        claim=experiment_path(project, 'claims/claim-evidence.csv')
        try:
            from scripts.results_validation import validate_claim_evidence,validate_registry
            if plan:errors.extend(f"experiments/registry.jsonl: {x}" for x in validate_registry(project,plan,registry))
            errors.extend(f"claims/claim-evidence.csv: {x}" for x in validate_claim_evidence(project,claim,registry))
        except ImportError as exc:errors.append(f"results validator unavailable: {exc}")
        if not nonempty(experiment_path(project, 'reports/reproducibility.md')):errors.append("reports/reproducibility.md is required")
        try:
            from scripts.research_quality import ResearchQualityError,validate_g4_quality
            errors.extend(f"research quality: {x}" for x in validate_g4_quality(project))
        except ImportError as exc:errors.append(f"research-quality validator unavailable: {exc}")
        except ResearchQualityError as exc:errors.append(f"research-quality evidence is invalid: {exc}")
        quality_errors(project,gate,errors,warnings=warnings);independent_audit_errors(project,gate,errors,warnings=warnings);return errors
    if gate=="G5":
        pid=active_paper_id(slug);paper=project/"papers"/pid
        from scripts.research_phase import exploratory,requires_submission,SUBMISSION_PENDING
        try:
            prereg=read_json(paper/"preregistration.json") if (paper/"preregistration.json").is_file() else {}
            if exploratory(project,pid) or prereg.get("research_phase")=="exploratory":
                return errors+[f"{pid}: exploratory observations cannot enter G5; return to a reviewed confirmatory G3 protocol"]
        except (OSError,ValueError,KeyError,TypeError) as exc:return errors+[f"{pid} research phase: {exc}"]
        from scripts.supplemental_experiments import internal_errors
        errors.extend("internal follow-up: "+issue for issue in internal_errors(project,pid))
        from scripts import study_routes
        if study_routes.route(project,pid)!="empirical":errors.extend(study_routes.validation_errors(project,pid))
        errors.extend(paper_scientific_errors(project,pid))
        paper_observations(project,pid,warnings)
        if requires_submission(project,paper_id=pid):
            from scripts.submission_package import submission_checks,submission_check_binding
            state=read_json(state_path(slug))
            approval=next((item for item in reversed(state.get("approvals",[])) if item.get("gate")=="G5" and item.get("paper_id")==pid),None)
            sealed=(state.get("status")=="approved" and f"G5:{pid}" in state.get("approved_gates",[])
                    and approval and approval.get("submission_checks_sha256")
                    and approval.get("paper_artifact_sha256")==paper_artifact_hash(slug,pid))
            if sealed:
                try:
                    if approval["submission_checks_sha256"]!=submission_check_binding(project,pid):errors.append(f"{pid} final submission inputs changed after the G5 check")
                except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:errors.append(f"{pid} final submission binding: {exc}")
            else:errors.extend(submission_checks(project,pid,warnings=warnings))
            quality_errors(project,gate,errors,pid,warnings=warnings)
        else:errors.append(SUBMISSION_PENDING)
        independent_audit_errors(project,gate,errors,pid,warnings=warnings)
        return errors
    errors.append(f"unknown gate: {gate}");return errors
def active_paper_id(slug):return validate_paper_id(str(read_json(state_path(slug)).get("active_paper")))
def artifact_hash(slug,gate):
    project=project_dir(slug);d=hashlib.sha256()
    from scripts.paper_execution import relevant
    for path in sorted(project.rglob("*")):
        rel=path.relative_to(project)
        if not path.is_file() or rel.parts[0]=="state" or "raw" in rel.parts or "venue-template" in rel.parts or "build" in rel.parts or rel.parts[:2]==("experiments","runs"):continue
        if gate in {"G3","G4","G5"} and not relevant(project,rel.as_posix()):continue
        d.update(rel.as_posix().encode());d.update(b"\0");d.update(path.read_bytes());d.update(b"\0")
    d.update(gate.encode("ascii"));return d.hexdigest()
def paper_artifact_hash(slug,paper_id):
    paper=project_dir(slug)/"papers"/validate_paper_id(paper_id);d=hashlib.sha256()
    for path in sorted(paper.rglob("*")):
        if not path.is_file() or path.is_symlink():continue
        rel=path.relative_to(paper)
        if any(part in {"build","submission","venue-template"} for part in rel.parts):continue
        d.update(rel.as_posix().encode());d.update(b"\0");d.update(path.read_bytes());d.update(b"\0")
    from scripts.research_increments import paper_review_binding
    binding=paper_review_binding(project_dir(slug),paper_id)
    d.update(json.dumps(binding,sort_keys=True,separators=(",",":")).encode())
    from scripts.manuscript_hygiene import review_binding as hygiene_review_binding
    d.update(json.dumps(hygiene_review_binding(project_dir(slug),paper_id),sort_keys=True,separators=(",",":")).encode())
    from scripts import reviewer_rounds, publication_disclosure, statistical_watermarks
    for module in (reviewer_rounds,publication_disclosure,statistical_watermarks):
        d.update(json.dumps(module.review_binding(project_dir(slug),paper_id),sort_keys=True,separators=(",",":")).encode())
    from scripts.research_identity import review_binding as research_identity_binding
    d.update(json.dumps(research_identity_binding(project_dir(slug),paper_id),sort_keys=True,separators=(",",":")).encode())
    from scripts import review_receipts,scientific_scope
    for module in (review_receipts,scientific_scope):d.update(json.dumps(module.review_binding(project_dir(slug),paper_id),sort_keys=True,separators=(",",":")).encode())
    from scripts.supplemental_experiments import internal_binding
    d.update(json.dumps(internal_binding(project_dir(slug),paper_id),sort_keys=True,separators=(",",":")).encode())
    return d.hexdigest()
def initialize(args):
    slug=validate_slug(args.project);dest=project_dir(slug)
    if dest.exists():raise ResearchCtlError(f"Project already exists: {dest}")
    defaults=read_json(DEFAULTS_PATH);count=args.paper_count if args.paper_count is not None else int(defaults["paper_count"])
    portfolio=defaults.get("venue_portfolio",{}) if isinstance(defaults.get("venue_portfolio"),dict) else {}
    minimum_q1=int(portfolio.get("minimum_q1_papers",3))
    if not 1<=count<=20:raise ResearchCtlError("paper-count must be between 1 and 20")
    if count!=6:
        if getattr(args,"command",None)=="init" or os.environ.get("DR_OS_ROUTING_PROFILE")=="production" or os.environ.get("DR_OS_ROUTING_CONFIG"):
            raise ResearchCtlError("The supported doctoral workflow requires exactly six papers.")
        print("Non-six-paper initialization is a partial low-level fixture; the complete doctoral workflow supports six papers only.")
    for rel in ["state","intake","program","evidence/claude-science","data/raw","data/processed","data/quality","experiments/runs","claims","reports","reviews/codex","reviews/independent"]:(dest/rel).mkdir(parents=True,exist_ok=True)
    write_json(dest/"intake"/"constraints.json",{"schema_version":"1.1","status":"needs_user_input","execution_mode":"cloud_only","research_goal":None,"researcher_background":None,"available_skills":[],"preferred_domains":[],"candidate_application_routes":[],"time_horizon_years":None,"target_submission_ready_date":None,"weekly_hours":None,"cash_budget_usd":None,"model_api_budget_cny":None,"cloud_compute_budget_usd":None,"local_compute":{"gpu":None,"ram_gb":None,"storage_gb":None},"equipment":"No institutional laboratory assumed","data_constraint":"Prefer public or authorized datasets","topic_quality_requirements":{"novelty_evidence_required":True,"doctoral_depth_required":True,"original_contribution_required":True,"current_papers_cloud_feasible_required":True},"ranking_weights":{"funded_position_supply":None,"job_market_and_salary":None,"future_growth_potential":None,"phd_position_competition":None,"job_market_competition":None,"background_fit":None,"application_route_fit":None},"excluded_domains":[],"ethics_or_legal_constraints":[],"notes":[],"human_review_required":True})
    write_json(dest/"intake"/"capabilities.json",{"schema_version":"1.0","status":"unverified","os":"GitHub Actions Linux runner","orchestrator":"Codex control and API-first cloud orchestrator","semantic_planner":"Claude/Anthropic read-only","persistent_writer":"OpenAI/Codex","independent_auditor":"model family different from persistent writer","evidence_workbench":"Claude Science export contract","checked_at":None,"environment_report":None})
    write_json(dest/"state"/"output-provenance.json",{"schema_version":"1.0","files":{}})
    from scripts.research_increments import initialize as initialize_increments
    initialize_increments(dest)
    try:from scripts.model_spend import initial as initial_model_spend
    except ImportError:from model_spend import initial as initial_model_spend
    write_json(dest/"state"/"model-spend-control.json",initial_model_spend())
    negative_result_plan={"informative_if_unsupported":"","precision_limitations":"","stop_rule":"","claim_boundary":""}
    write_json(dest/"program"/"core-thesis.json",{"schema_version":"1.0","theme_id":"A","status":"draft","title":"","doctoral_question":"","distinct_contribution":"","novelty_claim_ids":[],"planned_paper_ids":[],"falsification_conditions":[],"negative_result_plan":negative_result_plan,"human_review_required":True})
    write_json(dest/"program"/"extension-thesis.json",{"schema_version":"1.0","theme_id":"B","status":"draft","title":"","doctoral_question":"","distinct_contribution":"","mechanism_or_rationale":"","novelty_claim_ids":[],"planned_paper_ids":[],"independent_evidence_plan":[],"falsification_conditions":[],"boundary_conditions":[],"relationship_to_core":{"shared_foundation":[],"independent_question":False,"independent_claims":False,"independent_primary_evidence":False,"survives_core_failure":False,"non_dependency_rationale":""},"fallback_if_unsupported":"","negative_result_plan":negative_result_plan,"human_review_required":True})
    write_json(dest/"program"/"topic-shortlist.json",{
        "candidates":[],
        "selection_decision":{"chosen_candidate_id":"","strongest_rival_candidate_id":"","why_selected_over_rival":"","change_of_mind_evidence":""},
        "selected_direction_cloud_feasibility":{"current_papers_feasible":False,"no_future_lab_dependency":False,
            "authorized_data_plan":"","cloud_experiment_plan":"","current_paper_scope":"",
            "feasibility_evidence":{"data_access":[],"research_rights":[],"compute_cost":[],"pilot":{"status":"not_run","limitation":""}}}})
    write_json(dest/"program"/"paper-map.json",{"schema_version":"1.0","status":"draft","independence_basis":"cumulative","papers":[],
        "thesis_synthesis":{"core_thesis":"","extension_thesis":"","cumulative_progression":"","integrated_contribution":"",
            "dependency_logic":"","argument_links":[],"evidence_alignment":[],"cumulative_contributions":[]}})
    write_json(dest/"program"/"novelty-claim-matrix.json",{"schema_version":"1.1","status":"draft","claims":[],
        "search_saturation":{"exact_query_rounds":0,"adjacent_field_rounds":0,"backward_chaining_complete":False,
            "forward_chaining_complete":False,"supporting_search_ids":[],"backward_chaining_search_ids":[],"forward_chaining_search_ids":[],
            "consecutive_no_material_new_work_rounds":0,"no_material_new_work_rounds":[],"unresolved_search_gaps":[],"saturation_rationale":"",
            "stopping_rule":"","retrieval_dispositions":[],"search_rounds":[]},"human_review_required":True})
    for rel in [
        "evidence/search-log.jsonl",
        "evidence/literature-api-ledger.jsonl",
        "evidence/ai4science-ledger.jsonl",
        "data/datasets.jsonl",
        "experiments/registry.jsonl",
    ]:
        write_text(dest / rel, "")
    write_text(dest/"claims/claim-evidence.csv","claim_id,paper_id,claim,evidence_ids,analysis_ids,comparison_ids,support,uncertainty,status\n")
    for n in range(1,count+1):
        pid=f"P{n:02d}";paper=dest/"papers"/pid
        for rel in ["manuscript","figures","tables","supplement","submission-materials","reviews","experiments","style"]:(paper/rel).mkdir(parents=True,exist_ok=True)
        from scripts.research_identity import template as research_identity_template
        write_json(paper/"research-identity.json",research_identity_template(pid))
        try:
            from scripts.venue_policy import default_target
        except ImportError:
            from venue_policy import default_target
        write_json(paper/"paper-contract.json",{"schema_version":"2.0","paper_id":pid,"writing_language":"en","target_jcr_quartile":default_target(n,count,minimum_q1),"working_title":"","research_question":"","distinct_contribution":"","relationship_to_core":"","relationship_to_extension":"","cloud_feasibility":{"current_paper_cloud_executable":False,"no_future_lab_dependency":False,"data_access_plan":"","cloud_execution_plan":"","evidence_and_claim_scope":""},"originality_boundary":{"novel_elements":[],"reused_elements":[],"closest_prior_work_ids":[],"differentiation":"","claim_limitations":""},"hypotheses":[],"datasets":[],"planned_experiments":{"design_ids":[],"baseline_classes":[],"ablations":[],"primary_evaluation":"","statistical_plan":"","external_validity_plan":"","reproducibility_plan":""},"falsification_conditions":[],"negative_result_plan":negative_result_plan,"scientific_bindings":{"schema_version":"1.0","hypotheses":[],"falsification_conditions":[]},"dependencies":[],"dependency_bindings":[],"independence":{"unique_claim_ids":[],"shared_assets":[],"overlap_with_other_papers":[],"why_not_merge":""},"target_venues":[],"status":"draft"})
        write_text(paper/"reviews"/"citation-claims.jsonl","")
        write_text(paper/"reviews"/"response-matrix.csv","comment_id,commitment_id,fulfillment_status,location,revised_text,unfulfilled_rationale\n")
    state={"schema_version":"2.0","project":slug,"created_at":now(),"updated_at":now(),"stage_index":0,"stage":"intake","gate":"G0","status":"awaiting_work","active_paper":"P01","paper_count":count,"paper_statuses":{f"P{n:02d}":"active" if n==1 else "planned" for n in range(1,count+1)},"approved_gates":[],"approvals":[],"history":[{"at":now(),"event":"project_initialized","stage":"intake"}]};save_state(slug,state)
    venue_id=args.venue or defaults.get("trial_venue")
    if venue_id:set_venue_values(slug,"P01",venue_id)
    print(f"Initialized {dest}")
def print_status(args):
    state=load_state(args.project);warnings=[];errors=gate_errors(args.project,state["gate"],warnings=warnings);out={**state,"gate_ready":not errors and state["gate"] is not None,"gate_errors":errors,"gate_warnings":warnings,"gate_error_groups":summarize_gate_errors(errors)}
    if state["gate"]=="G0":
        from scripts.intake_validation import guidance
        out["intake_guidance"]=guidance(read_json(project_dir(args.project)/"intake/constraints.json"))
    if args.json:print(json.dumps(out,ensure_ascii=False,indent=2));return
    print(f"Project: {state['project']}\nStage:   {state['stage']}\nGate:    {state['gate'] or '-'}\nStatus:  {state['status']}\nReady:   {'yes' if not errors else 'no'}")
    print_gate_error_groups(out["gate_error_groups"])
    for warning in warnings:print("  warning: "+warning)
    for item in out.get("intake_guidance",{}).get("questions",[]):print("  intake: "+item["question"])
def print_gate_error_groups(groups):
    summary=f"{len(groups)} issue group(s), {sum(group['count'] for group in groups)} check messages"
    if groups:print(f"Checks: {summary}")
    for group in groups:
        if group["count"] == 1 and group["title"] == group["checks"][0]:
            print(f"  - {group['title']}")
        else:
            print(f"  - {group['title']} ({group['count']} check messages)\n    {group['next_action']}")
    return summary
def check_gate(args):
    state=load_state(args.project);gate=args.gate or state["gate"];warnings=[];errors=gate_errors(args.project,gate,warnings=warnings)
    for warning in warnings:print("warning: "+warning)
    if errors:
        summary=print_gate_error_groups(summarize_gate_errors(errors))
        raise ResearchCtlError(f"{gate} is not ready: {summary} remain; use status --project {args.project} --json for all original checks")
    print(f"{gate} artifact and quality checks passed.")
def mark_ready(args):
    state=load_state(args.project);gate=state["gate"]
    if gate is None:raise ResearchCtlError("Project is already submission-ready.")
    errors=gate_errors(args.project,gate)
    if errors:
        summary=print_gate_error_groups(summarize_gate_errors(errors))
        raise ResearchCtlError(f"{gate} cannot be marked ready: {summary} remain; use status --project {args.project} --json for all original checks")
    current_hash=artifact_hash(args.project,gate)
    if gate=="G2":
        state["paper_topic_approvals"]=[x for x in state.get("paper_topic_approvals",[]) if x.get("artifact_sha256")==current_hash]
    state["status"]="awaiting_approval";state["ready_gate"]=gate;state["ready_artifact_sha256"]=current_hash;state["history"].append({"at":now(),"event":"gate_marked_ready","gate":gate,"note":args.note,"artifact_sha256":current_hash});save_state(args.project,state)
    if gate in {"G1","G2"}:
        print(f"{gate} is awaiting human topic approval.")
    else:
        _record_gate_decision(args.project,gate,"deterministic-control-plane",args.note,current_hash,"deterministic")
def reopen(args):
    state=load_state(args.project);gate=state["gate"]
    if gate is None:raise ResearchCtlError("Submission-ready projects have no gate to reopen.")
    if state["status"]!="awaiting_approval":raise ResearchCtlError("Only a gate awaiting approval can be reopened.")
    if not args.note.strip():raise ResearchCtlError("reopen requires a reason in --note")
    state["status"]="awaiting_work";state.pop("ready_gate",None);state.pop("ready_artifact_sha256",None);state["history"].append({"at":now(),"event":"gate_reopened","gate":gate,"note":args.note.strip()});save_state(args.project,state);print(f"{gate} reopened for revision; the prior ready snapshot is no longer approvable.")
def approve(args):
    state=load_state(args.project);gate=state["gate"]
    if gate!=args.gate:raise ResearchCtlError(f"Current gate is {gate}, not {args.gate}.")
    if state["status"]!="awaiting_approval":raise ResearchCtlError("Run gate-check and ready before approval.")
    if gate_errors(args.project,gate):raise ResearchCtlError("Gate artifacts or quality report changed and no longer pass checks.")
    current_hash=artifact_hash(args.project,gate)
    if state.get("ready_gate")!=gate or state.get("ready_artifact_sha256")!=current_hash:raise ResearchCtlError("Artifacts changed after ready; review them and run ready again before approval.")
    if gate not in {"G1","G2"}:raise ResearchCtlError("Only doctoral and paper topics require human approval.")
    if not args.actor.strip() or args.actor.strip()=="deterministic-control-plane":raise ResearchCtlError("actor must identify the human approver")
    if gate=="G2":
        paper=getattr(args,"paper",None)
        expected={f"P{n:02d}" for n in range(1,int(state["paper_count"])+1)}
        if paper not in expected:raise ResearchCtlError("G2 requires --paper for a declared paper topic")
        votes=[x for x in state.get("paper_topic_approvals",[]) if x.get("artifact_sha256")==current_hash and x.get("paper_id")!=paper]
        votes.append({"paper_id":paper,"actor":args.actor.strip(),"at":now(),"artifact_sha256":current_hash,"note":args.note})
        state["paper_topic_approvals"]=votes
        state["history"].append({"at":now(),"event":"paper_topic_approved","paper_id":paper,"actor":args.actor.strip(),"artifact_sha256":current_hash})
        save_state(args.project,state)
        if {v["paper_id"] for v in votes}!=expected:
            print(f"Recorded topic approval for {paper}; remaining paper topics require approval.");return
    _record_gate_decision(args.project,gate,args.actor.strip(),args.note,current_hash,"human_topic")

def _record_gate_decision(slug,gate,actor,note,current_hash,decision_type):
    state=load_state(slug)
    from scripts.paper_execution import enabled, papers as selected_papers
    scoped=enabled(project_dir(slug)) and gate in {"G3","G4","G5"}
    approval={"gate":gate,"actor":actor,"decision_type":decision_type,"at":now(),"note":note,"artifact_sha256":current_hash}
    if gate=="G2":approval["paper_topic_approvals"]=list(state.get("paper_topic_approvals",[]))
    if gate=="G3":
        p=project_dir(slug);approval["experiment_plan_sha256"]=file_sha256(experiment_path(p, 'experiments/plan.json'));approval["experiment_budget_sha256"]=file_sha256(experiment_path(p, 'experiments/budget.json'))
        approval["frozen_protocol_sha256"]={path.relative_to(p).as_posix():file_sha256(path) for path in sorted((p/"papers").glob("P[0-9][0-9]/preregistration.json")) if path.parent.name in selected_papers(p,"G3")}
        from scripts.experiment_runner import compute_budget_authority
        approval["compute_budget_authority"]=compute_budget_authority(p,read_json(experiment_path(p, 'experiments/budget.json')),read_json(experiment_path(p, 'experiments/plan.json')))
    key=gate
    if scoped:approval["paper_id"]=state["active_paper"];key=f"{gate}:{state['active_paper']}"
    if gate=="G5":
        from scripts.submission_package import submission_check_binding
        approval["paper_id"]=state["active_paper"];approval["paper_artifact_sha256"]=paper_artifact_hash(slug,state["active_paper"])
        approval["submission_checks_sha256"]=submission_check_binding(project_dir(slug),state["active_paper"])
        key=f"G5:{state['active_paper']}"
    state["approvals"].append(approval)
    if key not in state["approved_gates"]:state["approved_gates"].append(key)
    if gate in {"G1","G2"}:
        from scripts.scientific_scope import seal_approval
        seal_approval(project_dir(slug),gate,actor,approval)
    state["status"]="approved";state["history"].append({"at":now(),"event":"gate_approved" if decision_type=="human_topic" else "gate_auto_decided","gate":gate,"decision_type":decision_type});save_state(slug,state);print(f"Recorded {decision_type} decision for {gate}. Run advance to continue.")
def advance(args):
    state=load_state(args.project);gate=state["gate"]
    from scripts.paper_execution import enabled, enable
    scoped=enabled(project_dir(args.project)) and gate in {"G3","G4","G5"}
    if gate is None:raise ResearchCtlError("Project is already at the final stage.")
    key=f"{gate}:{state['active_paper']}" if scoped or gate=="G5" else gate
    if state["status"]!="approved" or key not in state["approved_gates"]:raise ResearchCtlError(f"{gate} has not been approved.")
    matching=next((x for x in reversed(state.get("approvals",[])) if x.get("gate")==gate and (not scoped and gate!="G5" or x.get("paper_id")==state["active_paper"])),None)
    if not matching or matching.get("artifact_sha256")!=artifact_hash(args.project,gate):raise ResearchCtlError("Artifacts changed after approval; run gate-check, ready and approve again.")
    if gate_errors(args.project,gate):raise ResearchCtlError("Gate checks no longer pass; review current evidence before advancing.")
    from scripts.research_phase import exploratory, archive_and_reopen
    if gate=="G4" and exploratory(project_dir(args.project)):
        archive_and_reopen(project_dir(args.project))
        print("Archived exploratory observations; prepare a new G3 protocol with prior exposure retained.")
        return
    if gate=="G2":
        enable(project_dir(args.project));state["paper_execution_mode"]="independent"
        state["history"].append({"at":now(),"event":"independent_paper_execution_enabled"})
    if gate=="G5":
        done=state["active_paper"];state.setdefault("paper_statuses",{})[done]="submission_ready";remaining=[f"P{n:02d}" for n in range(1,int(state["paper_count"])+1) if state["paper_statuses"].get(f"P{n:02d}")!="submission_ready"]
        if remaining:
            nxt=remaining[0];state["active_paper"]=nxt;state["paper_statuses"][nxt]="active";state["status"]="awaiting_work";state.pop("ready_gate",None);state.pop("ready_artifact_sha256",None)
            if enabled(project_dir(args.project)):state.update(stage_index=3,stage="experiment-design",gate="G3")
            state["history"].append({"at":now(),"event":"paper_advanced","from":done,"to":nxt});save_state(args.project,state);print(f"Marked {done} submission-ready; continuing {state['gate']} with {nxt}.");return
    i=state["stage_index"]+1;next_stage=STAGES[i];prev=state["stage"];state["stage_index"]=i;state["stage"]=next_stage["name"];state["gate"]=next_stage["gate"];state["status"]="submission_ready" if next_stage["gate"] is None else "awaiting_work";state.pop("ready_gate",None);state.pop("ready_artifact_sha256",None);state["history"].append({"at":now(),"event":"stage_advanced","from":prev,"to":next_stage["name"]});save_state(args.project,state);print(f"Advanced to {next_stage['name']}.")
def set_venue_values(slug,paper_id,venue_id):
    validate_paper_id(paper_id);source=ROOT/"venues"/venue_id/"venue.json"
    if not source.is_file():raise ResearchCtlError(f"Unknown venue manifest: {venue_id}")
    target=project_dir(slug)/"papers"/paper_id
    if not target.is_dir():raise ResearchCtlError(f"Unknown paper: {paper_id}")
    m=read_json(source);m["selected_at"]=now();m["selection_status"]="trial" if m.get("trial_only") else "candidate";write_json(target/"venue.json",m)
def set_venue(args):load_state(args.project);set_venue_values(args.project,args.paper,args.venue);print(f"Set {args.paper} venue to {args.venue}; verify current source-bound scope, article type and submission requirements. JCR rank remains a planning observation.")
def list_stages(_):print(json.dumps(STAGES,indent=2))
def parser():
    root=argparse.ArgumentParser(description=__doc__);cmd=root.add_subparsers(dest="command",required=True)
    p=cmd.add_parser("init");p.add_argument("--project",required=True);p.add_argument("--paper-count",type=int);p.add_argument("--venue",default=None);p.set_defaults(func=initialize)
    p=cmd.add_parser("status");p.add_argument("--project",required=True);p.add_argument("--json",action="store_true");p.set_defaults(func=print_status)
    p=cmd.add_parser("gate-check");p.add_argument("--project",required=True);p.add_argument("--gate");p.set_defaults(func=check_gate)
    p=cmd.add_parser("ready");p.add_argument("--project",required=True);p.add_argument("--note",default="");p.set_defaults(func=mark_ready)
    p=cmd.add_parser("reopen");p.add_argument("--project",required=True);p.add_argument("--note",required=True);p.set_defaults(func=reopen)
    p=cmd.add_parser("approve");p.add_argument("--project",required=True);p.add_argument("--gate",required=True);p.add_argument("--actor",required=True);p.add_argument("--paper",default=None);p.add_argument("--note",default="");p.set_defaults(func=approve)
    p=cmd.add_parser("advance");p.add_argument("--project",required=True);p.set_defaults(func=advance)
    p=cmd.add_parser("set-venue");p.add_argument("--project",required=True);p.add_argument("--paper",required=True);p.add_argument("--venue",required=True);p.set_defaults(func=set_venue)
    p=cmd.add_parser("stages");p.set_defaults(func=list_stages);return root
def main(argv:Iterable[str]|None=None):
    try:args=parser().parse_args(argv);args.func(args);return 0
    except ResearchCtlError as exc:print(f"error: {exc}",file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
