"""Versioned scientific intent and historical decisions, independent of task permission."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts import output_provenance
from scripts.research_artifacts import path_in, read, sha, write, record

MODULE = "scripts/scientific_scope.py"
PREFIX = "state/scientific-scope"
GATES = ("G0", "G1", "G2", "G3", "G4", "G5")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _cloud():
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise ValueError("scientific-scope mutations require the authorized cloud controller")


def _owned(project, target):
    origin = output_provenance.current_origin(project, target)
    if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane" or origin.get("model") != MODULE:
        raise ValueError("scientific scope lacks current protected human-controller provenance")


def _optional(project, relative):
    target=path_in(project,relative,exists=False)
    return read(target) if target.is_file() else {}


def _meaning(value, paper_id=None):
    """Compare scientific intent, not titles, ranking targets or portfolio size."""
    core_fields=("theme_id","doctoral_question","distinct_contribution","falsification_conditions")
    extension_fields=(*core_fields,"mechanism_or_rationale","independent_evidence_plan","boundary_conditions","relationship_to_core")
    result={"core":{key:value.get("core",{}).get(key) for key in core_fields},
            "extension":{key:value.get("extension",{}).get(key) for key in extension_fields}}
    if "paper_contracts" in value:
        fields=("paper_id","research_question","distinct_contribution","relationship_to_core","relationship_to_extension",
                "falsification_conditions","dependencies","independence","hypothesis_outcomes","primary_metrics","originality_boundary")
        result["paper_contracts"]=[{key:row.get(key) for key in fields} for row in value["paper_contracts"]
                                   if paper_id is None or row.get("paper_id")==paper_id]
        mapping=value.get("paper_map",{})
        map_fields=("paper_id","theme_id","research_question","distinct_contribution","contribution","claim_ids","dependencies")
        result["paper_map"]={"papers":[{key:row.get(key) for key in map_fields}
            for row in mapping.get("papers",[]) if paper_id is None or row.get("paper_id")==paper_id]}
    return result


def projection(project: Path, gate: str, paper_id: str | None = None) -> dict:
    """Describe existing questions; undeclared papers never become prerequisites."""
    if gate not in {"G1","G2"}:raise ValueError("only G1/G2 describe historical topic scope")
    value={"core":_optional(project,"program/core-thesis.json"),
           "extension":_optional(project,"program/extension-thesis.json")}
    if gate=="G2":
        mapping=_optional(project,"program/paper-map.json")
        rows=mapping.get("papers",[])
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
            raise ValueError("paper mapping must be a list of objects")
        value["paper_map"]={"papers":sorted(rows,key=lambda row:str(row.get("paper_id","")))}
        value["paper_contracts"]=[]
        for path in sorted((project/"papers").glob("P[0-9][0-9]/paper-contract.json")):
            contract=read(path_in(project,path.relative_to(project).as_posix()))
            row=dict(contract)
            if isinstance(contract.get("scientific_bindings"),dict):
                row["hypothesis_outcomes"]=[{key:h.get(key) for key in ("id","statement","primary_outcome")}
                    for h in contract.get("hypotheses",[]) if isinstance(h,dict)]
                row["primary_metrics"]=[{key:h.get(key) for key in ("hypothesis_id","primary_metric")}
                    for h in contract["scientific_bindings"].get("hypotheses",[]) if isinstance(h,dict)]
            boundary=contract.get("originality_boundary",{})
            row["originality_boundary"]={key:boundary.get(key) for key in ("novel_elements","reused_elements","closest_prior_work_ids","differentiation","claim_limitations")}
            value["paper_contracts"].append(row)
    return _meaning(value,paper_id)


def changes(project: Path, paper_id: str | None = None) -> list[dict]:
    """Expose changed scientific intent without freezing unrelated research."""
    result=[]
    for gate in ("G1","G2"):
        target=path_in(project,f"{PREFIX}/{gate}.json",exists=False)
        if not target.is_file():continue
        original=read(target)
        before=_meaning(original.get("projection",{}),paper_id)
        after=projection(project,gate,paper_id)
        if before!=after:result.append({"gate":gate,"paper_id":paper_id,"before":before,"after":after})
    return result


def _pending(project):
    target = path_in(project, f"{PREFIX}/pending-amendment.json", exists=False)
    if not target.exists():
        return None
    _owned(project, target)
    value = read(target)
    return value if value.get("status") == "awaiting_reapproval" else None


def _supplemental_scope(project: Path, state: dict, gate: str) -> list[str]:
    """An exact approved child inherits its parent's thesis, never new G1/G2 approval."""
    context = state["supplemental_context"]
    project = project.resolve()
    if len(project.parents) < 5 or not isinstance(context, dict):
        raise ValueError("invalid supplemental scientific context")
    parent = project.parents[4]
    pid, round_id, scope_id = (context.get(k) for k in ("paper_id", "round_id", "scope_id"))
    if (not re.fullmatch(r"P[0-9]{2}", str(pid)) or not re.fullmatch(r"[RI][0-9]{3}", str(round_id))
            or not re.fullmatch(r"s[0-9]{3}", str(scope_id)) or context.get("parent_project") != parent.name
            or project != parent / "experiments/supplemental" / pid / round_id / scope_id):
        raise ValueError("supplemental scope must match its exact parent/paper/round directory")
    errors = validate(parent, "G5", pid)
    if errors:
        return errors
    control_path = path_in(parent, f"state/supplemental-experiments/{pid}/{round_id}/{scope_id}.json")
    origin = output_provenance.current_origin(parent, control_path)
    if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane" or origin.get("model") != "scripts/supplemental_experiments.py":
        raise ValueError("supplemental scope requires its actual protected parent protocol decision")
    control = read(control_path)
    if (control.get("scope_root") != project.relative_to(parent).as_posix() or control.get("paper_id") != pid
            or control.get("round_id") != round_id or control.get("scope_id") != scope_id
            or control.get("child_state_sha256") != sha(project / "state/run.json")
            or state.get("approvals") != [control.get("approval")] or control.get("retirement")):
        raise ValueError("supplemental authority/child state is stale or belongs to another scope")
    proposal = control["proposal"]
    if control.get("decision_kind")=="automated":
        from scripts import review_receipts
        binding=control.get("independent_review",{})
        target=path_in(parent,str(binding.get("path","")))
        review_receipts._owned(parent,target)
        if sha(target)!=binding.get("sha256"):
            raise ValueError("automatic supplemental authority needs its unchanged independent protocol receipt")
        final=read(target)
        if (final.get("paper_id")!=pid or final.get("phase")!="final"
                or final.get("materials",{}).get("review_purpose")!="supplemental_protocol"):
            raise ValueError("a paper audit or another scope cannot seal this supplemental protocol")
        review_receipts._identity(final["identity"],final["writer_family"])
        initial_binding=final["initial"]
        initial_path=path_in(parent,initial_binding["path"])
        review_receipts._owned(parent,initial_path)
        initial=read(initial_path)
        if (sha(initial_path)!=initial_binding["sha256"] or initial.get("phase")!="initial"
                or initial.get("materials",{}).get("review_purpose")!="supplemental_protocol"
                or any(initial.get(key)!=final.get(key) for key in ("gate","stage","paper_id","run_id"))):
            raise ValueError("automatic supplemental authority requires two actual same-purpose protocol audits")
        review_receipts._identity(initial["identity"],initial["writer_family"])
        reviewed={item["path"]:item.get("source_sha256",item["sha256"]) for item in final["materials"]["files"]}
        declared_raw={(item["path"], item["sha256"]) for item in final["materials"].get("declared_raw_inputs", [])
                      if item.get("declared_in") in reviewed}
        prereg=read(path_in(project,f"papers/{pid}/preregistration.json"))
        for item in prereg["files"]:
            if item["path"].startswith("data/quality/") and item["path"].endswith("-confirmation.json"):
                continue
            full=control["scope_root"]+"/"+item["path"]
            if "raw" in Path(item["path"]).parts and (full,item["sha256"]) in declared_raw:
                continue
            if reviewed.get(full)!=item["sha256"]:
                raise ValueError("supplemental frozen inputs differ from the independently reviewed protocol")
    from scripts.paper_execution import artifact_path
    if (sha(artifact_path(parent, "experiments/plan.json",pid)) != proposal.get("original_plan_sha256")
            or sha(path_in(parent, f"papers/{pid}/preregistration.json")) != proposal.get("original_preregistration_sha256")):
        raise ValueError("supplemental work cannot change its original parent protocol")
    child_claims = set(read(path_in(project, f"papers/{pid}/paper-contract.json")).get("independence", {}).get("unique_claim_ids", []))
    parent_claims = set(read(path_in(parent, f"papers/{pid}/paper-contract.json")).get("independence", {}).get("unique_claim_ids", []))
    if not child_claims or not child_claims <= parent_claims:
        raise ValueError("supplemental claims must stay within the approved parent scientific scope")
    return []


def validate(project: Path, gate: str, paper_id: str | None = None) -> list[str]:
    """Validate retained records, not eligibility to read, experiment or write."""
    try:
        state=read(project/"state/run.json")
        if state.get("supplemental_context") is not None:
            return _supplemental_scope(project,state,gate)
        for prior in ("G1","G2"):
            target=path_in(project,f"{PREFIX}/{prior}.json",exists=False)
            if not target.is_file():continue  # No invented seal for legacy or new work.
            _owned(project,target)
            seal=read(target)
            if seal.get("gate")!=prior or seal.get("projection_sha256")!=_digest(seal.get("projection")):
                raise ValueError("retained scientific scope record is inconsistent")
        return []
    except (OSError,ValueError,KeyError,TypeError,RuntimeError) as exc:
        return ["scientific scope record: "+str(exc)]


def seal_approval(project: Path, gate: str, actor: str, approval: dict) -> None:
    if gate not in {"G1", "G2"}:
        return
    _cloud()
    if not actor.strip() or approval.get("actor") != actor or approval.get("gate") != gate or not approval.get("artifact_sha256"):
        raise ValueError("scope sealing requires the actual named human gate approval")
    if gate == "G2":
        state = read(project / "state/run.json")
        expected = {f"P{n:02d}" for n in range(1, state["paper_count"] + 1)}
        votes = approval.get("paper_topic_approvals")
        if (not isinstance(votes, list) or len(votes) != len(expected)
            or any(not isinstance(v, dict) or not isinstance(v.get("actor"), str) or not v["actor"].strip()
                   or v.get("artifact_sha256") != approval.get("artifact_sha256") for v in votes)
            or {v.get("paper_id") for v in votes} != expected):
            raise ValueError("G2 requires an individual human topic approval for every paper")
    target = path_in(project, f"{PREFIX}/{gate}.json", exists=False)
    pending = _pending(project)
    current = projection(project, gate)
    if target.exists():
        _owned(project, target)
        old = read(target)
        if old.get("projection") != current and (not pending or pending["gate"] != gate):
            # A reapproved G1 necessarily retires the old G2 architecture.
            # Its replacement still needs fresh G2 checks and human approval.
            historical = path_in(project, f"{PREFIX}/pending-amendment.json", exists=False)
            authorizes_new_g2 = False
            if gate == "G2" and historical.exists():
                _owned(project, historical)
                previous = read(historical)
                state = read(project / "state/run.json")
                authorizes_new_g2 = (previous.get("gate") == "G1" and previous.get("status") == "reapproved"
                    and "G2" not in state.get("approved_gates", [])
                    and previous.get("new_seal_sha256") == sha(path_in(project, f"{PREFIX}/G1.json")))
            if not authorizes_new_g2:
                raise ValueError("changed scientific scope requires a human amendment route")
        archive = path_in(project, f"{PREFIX}/history/{gate}-{sha(target)}.json", exists=False)
        if not archive.exists():
            write(archive, old)
            record(project, [archive], MODULE)
    value = {"schema_version": "1.0", "gate": gate, "actor": actor, "approval": approval,
             "projection": current, "projection_sha256": _digest(current), "created_at": datetime.now(timezone.utc).isoformat(),
             "scientific_completion_verified": False}
    write(target, value)
    paths = [target]
    if pending and pending["gate"] == gate:
        pending_path = path_in(project, f"{PREFIX}/pending-amendment.json")
        write(pending_path, {**pending, "status": "reapproved", "new_seal_sha256": sha(target)})
        paths.append(pending_path)
    record(project, paths, MODULE)


def prepare_amendment(project: Path, source: str, actor: str) -> dict:
    _cloud()
    if not actor.strip() or not source.startswith("program/"):
        raise ValueError("named human and program scope-amendment proposal required")
    target = path_in(project, source)
    proposal = read(target)
    if set(proposal) != {"schema_version", "id", "gate", "reason", "expected_seal_sha256", "proposed_projection"} or proposal["schema_version"] != "1.0":
        raise ValueError("scope amendment needs its exact proposal schema")
    if proposal["gate"] not in {"G1", "G2"} or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", str(proposal["id"])) or not isinstance(proposal["reason"], str) or len(proposal["reason"].strip()) < 30:
        raise ValueError("scope amendment needs G1/G2, a safe ID and material scientific rationale")
    if _pending(project):
        raise ValueError("finish the pending scientific scope reapproval first")
    seal = path_in(project, f"{PREFIX}/{proposal['gate']}.json")
    _owned(project, seal)
    if sha(seal) != proposal["expected_seal_sha256"]:
        raise ValueError("amendment old scope CAS changed")
    if proposal["proposed_projection"] != projection(project, proposal["gate"]):
        raise ValueError("proposal must describe the exact current candidate scientific materials")
    if proposal["proposed_projection"] == read(seal)["projection"]:
        raise ValueError("amendment must identify an actual scientific scope change")
    if proposal["gate"] == "G2":
        old_core = read(path_in(project, f"{PREFIX}/G1.json"))["projection"]
        if old_core != projection(project, "G1"):
            raise ValueError("doctoral question/core-extension changes must reopen G1, not only G2")
    return {"schema_version": "1.0", "id": proposal["id"], "gate": proposal["gate"], "actor": actor,
            "source": {"path": source, "sha256": sha(target)}, "reason": proposal["reason"],
            "old_seal_sha256": sha(seal), "proposed_projection_sha256": _digest(proposal["proposed_projection"]),
            "effect": "record_changed_scientific_intent_without_resetting_other_work", "scientific_completion_verified": False}


def apply_amendment(project: Path, source: str, actor: str, review_sha256: str, run_id: str, note: str) -> dict:
    prepared = prepare_amendment(project, source, actor)
    if not re.fullmatch(r"[0-9a-f]{64}", str(review_sha256)) or not str(run_id).strip() or not str(note).strip():
        raise ValueError("human control dossier hash, cloud run and approval note required")
    receipt = path_in(project, f"{PREFIX}/amendments/{prepared['id']}.json", exists=False)
    if receipt.exists():
        raise ValueError("scope amendment IDs cannot overwrite history")
    value = {**prepared, "cloud_review_sha256": review_sha256, "source_run_id": run_id, "note": note,
             "status": "recorded", "created_at": datetime.now(timezone.utc).isoformat()}
    write(receipt, value)
    pending = path_in(project, f"{PREFIX}/pending-amendment.json", exists=False)
    write(pending, value)
    record(project, [receipt, pending], MODULE)
    state_path=path_in(project,"state/run.json");state=read(state_path)
    # Preserve original decisions and execution status. A new topic record is not
    # permission to overwrite frozen inputs or to rerun an observed experiment.
    state.setdefault("history",[]).append({"at":value["created_at"],"event":"scientific_scope_amendment",
        "gate":prepared["gate"],"actor":actor,"receipt":receipt.relative_to(project).as_posix(),
        "prior_approvals_preserved":True,"new_experiments_authorized":False})
    write(state_path,state)
    return value


def review_binding(project: Path, paper_id: str | None = None) -> dict:
    # Meaningful changes to this paper can stale its review. A title, another
    # paper or unrelated implementation file cannot invalidate its evidence.
    return {"schema_version":"2.0","scope":projection(project,"G2",paper_id)}
