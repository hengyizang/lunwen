"""Human-sealed doctoral scope; amendments reopen scientific gates, never waive them."""
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


def projection(project: Path, gate: str) -> dict:
    """Freeze scientific meaning, while leaving statuses, evidence and writing progress editable."""
    if gate not in {"G1", "G2"}:
        raise ValueError("only G1/G2 define doctoral scientific scope")
    state = read(project / "state/run.json")
    count = state.get("paper_count")
    if type(count) is not int or not 1 <= count <= 20:
        raise ValueError("declared paper count required")
    core = read(path_in(project, "program/core-thesis.json"))
    extension = read(path_in(project, "program/extension-thesis.json"))
    core_fields = ("theme_id", "doctoral_question", "distinct_contribution", "planned_paper_ids", "falsification_conditions")
    extension_fields = (*core_fields, "mechanism_or_rationale", "independent_evidence_plan", "boundary_conditions", "relationship_to_core")
    for obj in (core, extension):
        if not isinstance(obj.get("doctoral_question"), str) or not obj["doctoral_question"].strip():
            raise ValueError("a real declared doctoral question is required before scope approval")
    result = {"paper_count": count, "core": {k: core.get(k) for k in core_fields},
              "extension": {k: extension.get(k) for k in extension_fields}}
    if gate == "G2":
        mapping = read(path_in(project, "program/paper-map.json"))
        rows = mapping.get("papers")
        expected = {f"P{n:02d}" for n in range(1, count + 1)}
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows) or {r.get("paper_id") for r in rows} != expected or len(rows) != count:
            raise ValueError("scientific mapping must cover every declared paper exactly once")
        result["paper_map"] = {"papers": sorted(rows, key=lambda r: r["paper_id"]),
                               "pairwise_distinctness": sorted(mapping.get("pairwise_distinctness", []), key=lambda r: (r.get("paper_a", ""), r.get("paper_b", ""))),
                               "thesis_synthesis": mapping.get("thesis_synthesis")}
        fields = ("paper_id", "research_question", "distinct_contribution", "relationship_to_core", "relationship_to_extension",
                  "falsification_conditions", "dependencies", "independence", "target_jcr_quartile")
        result["paper_contracts"] = []
        for pid in sorted(expected):
            contract = read(path_in(project, f"papers/{pid}/paper-contract.json"))
            row = {k: contract.get(k) for k in fields}
            boundary = contract.get("originality_boundary", {})
            row["originality_boundary"] = {k: boundary.get(k) for k in ("novel_elements", "reused_elements", "differentiation", "claim_limitations")}
            result["paper_contracts"].append(row)
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
    if (not re.fullmatch(r"P[0-9]{2}", str(pid)) or not re.fullmatch(r"R[0-9]{3}", str(round_id))
            or not re.fullmatch(r"s[0-9]{3}", str(scope_id)) or context.get("parent_project") != parent.name
            or project != parent / "experiments/supplemental" / pid / round_id / scope_id):
        raise ValueError("supplemental scope must match its exact parent/paper/round directory")
    errors = validate(parent, "G5", pid)
    if errors:
        return errors
    control_path = path_in(parent, f"state/supplemental-experiments/{pid}/{round_id}/{scope_id}.json")
    origin = output_provenance.current_origin(parent, control_path)
    if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane" or origin.get("model") != "scripts/supplemental_experiments.py":
        raise ValueError("supplemental scope requires its actual protected parent human approval")
    control = read(control_path)
    if (control.get("scope_root") != project.relative_to(parent).as_posix() or control.get("paper_id") != pid
            or control.get("round_id") != round_id or control.get("scope_id") != scope_id
            or control.get("child_state_sha256") != sha(project / "state/run.json")
            or state.get("approvals") != [control.get("approval")] or control.get("retirement")):
        raise ValueError("supplemental authority/child state is stale or belongs to another scope")
    proposal = control["proposal"]
    if (sha(path_in(parent, "experiments/plan.json")) != proposal.get("original_plan_sha256")
            or sha(path_in(parent, f"papers/{pid}/preregistration.json")) != proposal.get("original_preregistration_sha256")):
        raise ValueError("supplemental work cannot change its original parent protocol")
    child_claims = set(read(path_in(project, f"papers/{pid}/paper-contract.json")).get("independence", {}).get("unique_claim_ids", []))
    parent_claims = set(read(path_in(parent, f"papers/{pid}/paper-contract.json")).get("independence", {}).get("unique_claim_ids", []))
    if not child_claims or not child_claims <= parent_claims:
        raise ValueError("supplemental claims must stay within the approved parent scientific scope")
    return []


def validate(project: Path, gate: str, paper_id: str | None = None) -> list[str]:
    if gate not in GATES or gate == "G0":
        return []
    try:
        state = read(project / "state/run.json")
        if state.get("supplemental_context") is not None:
            return _supplemental_scope(project, state, gate)
        pending = _pending(project)
        if pending and GATES.index(gate) > GATES.index(pending["gate"]):
            raise ValueError("scientific amendment must pass fresh " + pending["gate"] + " scientific review and human approval first")
        for prior_gate in ("G1", "G2"):
            if GATES.index(gate) < GATES.index(prior_gate):
                continue
            approved = prior_gate in state.get("approved_gates", [])
            target = path_in(project, f"{PREFIX}/{prior_gate}.json", exists=False)
            if pending and GATES.index(prior_gate) >= GATES.index(pending["gate"]):
                if prior_gate == pending["gate"] and _digest(projection(project, prior_gate)) != pending["proposed_projection_sha256"]:
                    raise ValueError("scope changed after the named human amendment authorization")
                continue
            if not approved:
                if GATES.index(gate) > GATES.index(prior_gate):
                    raise ValueError("later work requires human-approved " + prior_gate + " scientific scope")
                continue
            if not target.exists():
                raise ValueError("approved " + prior_gate + " lacks a protected scope seal; do not silently bless legacy artifacts")
            _owned(project, target)
            seal = read(target)
            if seal.get("gate") != prior_gate or seal.get("projection") != projection(project, prior_gate):
                raise ValueError("approved " + prior_gate + " doctoral question or paper mapping changed; request an explicit human scope amendment")
            if not any(a.get("gate") == prior_gate and a.get("artifact_sha256") == seal.get("approval", {}).get("artifact_sha256")
                       and a.get("actor") == seal.get("actor") for a in state.get("approvals", [])):
                raise ValueError("scope seal lacks its named original human approval")
        return []
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return ["approved scientific scope: " + str(exc)]


def seal_approval(project: Path, gate: str, actor: str, approval: dict) -> None:
    if gate not in {"G1", "G2"}:
        return
    _cloud()
    if not actor.strip() or approval.get("actor") != actor or approval.get("gate") != gate or not approval.get("artifact_sha256"):
        raise ValueError("scope sealing requires the actual named human gate approval")
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
            "effect": "reopen_scientific_gate_requires_fresh_reviews_and_human_reapproval", "scientific_completion_verified": False}


def apply_amendment(project: Path, source: str, actor: str, review_sha256: str, run_id: str, note: str) -> dict:
    prepared = prepare_amendment(project, source, actor)
    if not re.fullmatch(r"[0-9a-f]{64}", str(review_sha256)) or not str(run_id).strip() or not str(note).strip():
        raise ValueError("human control dossier hash, cloud run and approval note required")
    receipt = path_in(project, f"{PREFIX}/amendments/{prepared['id']}.json", exists=False)
    if receipt.exists():
        raise ValueError("scope amendment IDs cannot overwrite history")
    value = {**prepared, "cloud_review_sha256": review_sha256, "source_run_id": run_id, "note": note,
             "status": "awaiting_reapproval", "created_at": datetime.now(timezone.utc).isoformat()}
    write(receipt, value)
    pending = path_in(project, f"{PREFIX}/pending-amendment.json", exists=False)
    write(pending, value)
    record(project, [receipt, pending], MODULE)
    state_path = path_in(project, "state/run.json")
    state = read(state_path)
    index = GATES.index(prepared["gate"])
    state["approved_gates"] = [g for g in state.get("approved_gates", []) if g.split(":")[0] in GATES[:index]]
    state.update(stage_index=index, stage={"G1": "topic-intelligence", "G2": "paper-architecture"}[prepared["gate"]],
                 gate=prepared["gate"], status="awaiting_work")
    state.pop("ready_gate", None)
    state.pop("ready_artifact_sha256", None)
    for pid in state.get("paper_statuses", {}):
        state["paper_statuses"][pid] = "pending"
    state["active_paper"] = "P01"
    state.setdefault("history", []).append({"at": value["created_at"], "event": "human_scientific_scope_amendment",
        "gate": prepared["gate"], "actor": actor, "receipt": receipt.relative_to(project).as_posix(),
        "prior_approvals_preserved": True, "new_experiments_authorized": False})
    write(state_path, state)
    return value


def review_binding(project: Path, paper_id: str | None = None) -> dict:
    files = []
    for name in ("G1.json", "G2.json", "pending-amendment.json"):
        target = path_in(project, f"{PREFIX}/{name}", exists=False)
        files.append({"path": target.relative_to(project).as_posix(), "sha256": sha(target) if target.is_file() else None})
    return {"files": files, "implementation_sha256": sha(Path(__file__))}
