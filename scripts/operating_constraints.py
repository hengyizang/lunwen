"""Narrow owner amendments of the cumulative API ceiling and planning date.

This records explicit owner resource decisions without changing scientific
approvals, frozen experiments, results or the selected research task.
"""
from __future__ import annotations

import copy
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scripts import cloud_continuation, intake_validation, model_spend, output_provenance, researchctl
from scripts.research_artifacts import path_in, read, record, sha, write

MODULE = "scripts/operating_constraints.py"
PREFIX = "state/operating-constraints-amendments"


from scripts.paper_execution import artifact_path as experiment_path

def validate_selectors(new_ceiling_cny: int, target_submission_ready_date: str) -> None:
    if type(new_ceiling_cny) is not int or new_ceiling_cny <= 0:
        raise ValueError("cumulative model API ceiling must be a positive integer CNY amount")
    try:
        if (not isinstance(target_submission_ready_date, str)
                or date.fromisoformat(target_submission_ready_date).isoformat() != target_submission_ready_date):
            raise ValueError("non-canonical planning date")
    except (TypeError, ValueError):
        raise ValueError("target_submission_ready_date must be a canonical ISO date") from None


def _updated_constraints(original: dict, ceiling: int, deadline: str) -> dict:
    value = copy.deepcopy(original)
    old_date = original.get("target_submission_ready_date")
    old_budget = original.get("model_api_budget_cny")
    value.update(model_api_budget_cny=ceiling, target_submission_ready_date=deadline)
    # Replace only explicit operative dates, including the documented preceding
    # manuscript checkpoint. All other scientific/background wording is retained.
    replacements = {}
    if old_date and old_date != deadline:
        replacements[old_date] = deadline
        replacements[(date.fromisoformat(old_date) - timedelta(days=1)).isoformat()] = (
            date.fromisoformat(deadline) - timedelta(days=1)).isoformat()
    for key in ("research_goal", "notes"):
        texts = [value.get(key)] if key == "research_goal" else value.get(key,[])
        updated = []
        for text in texts:
            if not isinstance(text,str):
                updated.append(text)
                continue
            if key == "research_goal":
                if old_date in replacements:
                    text = re.sub(r"\b(before|by)(\s+)" + re.escape(old_date) + r"\b",
                                  lambda match: match.group(1) + match.group(2) + deadline, text)
            elif text.startswith("The requested date is preserved; the planning checkpoint is "):
                for prior, current in replacements.items():
                    text = text.replace(prior, current)
            if key == "notes" and old_budget != ceiling:
                token = f"initial cumulative model API envelope of CNY {old_budget:g}" if isinstance(old_budget,(int,float)) else "__no_previous_budget__"
                if token in text:
                    text = text.replace(token, f"current cumulative model API envelope of CNY {ceiling}")
                    text = re.sub(r", with CNY [\d.]+ per-paper warning and CNY [\d.]+ per-paper hard limits", "", text)
                    text = text.replace(
                        "This intake is not a ledger grant; the separate owner cloud authorize_budget job records the first tranche before any paid transport.",
                        "The hash-bound owner operating amendment records this exact cumulative ceiling; no paid transport is started by the amendment.")
                if text.startswith("Spending authorization is cumulative: initial approval for CNY "):
                    text = (f"Spending is cumulative: the current total ceiling is CNY {ceiling}. "
                            "Calls within its unused capacity need no separate spending approval, tranche or per-paper limit. "
                            "Actual charges or conservative bounded estimates count toward the same total; no automatic increase is authorized.")
            updated.append(text)
        value[key] = updated[0] if key == "research_goal" else updated
    return value


def prepare(project: Path, new_ceiling_cny: int, target_submission_ready_date: str, actor: str) -> dict:
    """Check resource commitments, independently of the project's research phase."""
    validate_selectors(new_ceiling_cny,target_submission_ready_date)
    if not isinstance(actor,str) or not actor.strip():raise ValueError("named owner required for operating amendment")
    state=read(path_in(project,"state/run.json"))
    if state.get("supplemental_context") is not None:
        raise ValueError("supplemental projects cannot amend parent operating authority")
    constraints_path=path_in(project,"intake/constraints.json")
    original=read(constraints_path)
    policy_path=path_in(project,cloud_continuation.POLICY.as_posix(),exists=False)
    policy=read(policy_path) if policy_path.is_file() else None
    if policy is not None and (type(policy.get("enabled")) is not bool or policy.get("actor")!=actor):
        raise ValueError("operating amendment must use the recorded owner authority")
    spend=model_spend.read(project,required=True)
    if new_ceiling_cny<spend["spent_cny"]+model_spend.reserved(spend):
        raise ValueError("amended cumulative ceiling cannot fall below spent and reserved charges")
    if (new_ceiling_cny==spend["authorized_ceiling_cny"] and new_ceiling_cny==original.get("model_api_budget_cny")
            and target_submission_ready_date==original.get("target_submission_ready_date")):
        raise ValueError("operating amendment must change a current constraint")
    updated=_updated_constraints(original,new_ceiling_cny,target_submission_ready_date)
    return {"constraints_before":original,"constraints_after":updated,"constraints_sha256_before":sha(constraints_path),
            "continuation_before":policy,"spend_before":spend,"run_before":state,
            "effect":"exact cumulative API ceiling and planning date only; no paid calls or scientific gate advance",
            "scientific_completion_verified":False}


def apply(project: Path, new_ceiling_cny: int, target_submission_ready_date: str,
          actor: str, review_sha256: str, run_id: str, note: str) -> list[Path]:
    prepared = prepare(project, new_ceiling_cny, target_submission_ready_date, actor)
    if (not re.fullmatch(r"[a-f0-9]{64}", str(review_sha256)) or not re.fullmatch(r"[0-9]+", str(run_id))
            or not isinstance(note, str) or not note.strip()):
        raise ValueError("exact owner dossier hash, numeric cloud run and authorization note required")
    receipt = path_in(project, f"{PREFIX}/{run_id}.json", exists=False)
    if receipt.exists():
        raise ValueError("operating amendment cannot overwrite its prior receipt")
    constraints_path = path_in(project, "intake/constraints.json")
    policy_path = path_in(project, cloud_continuation.POLICY.as_posix(), exists=False)
    state_path = path_in(project, "state/run.json")
    spend_path = path_in(project, model_spend.FILE.as_posix())
    provenance = path_in(project, output_provenance.REGISTRY_RELATIVE.as_posix(), exists=False)
    outputs = [constraints_path, state_path, spend_path, receipt]
    if prepared["continuation_before"] is not None:outputs.append(policy_path)
    originals = {p: p.read_bytes() if p.exists() else None for p in [*outputs, provenance]}
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        spend = prepared["spend_before"]
        if new_ceiling_cny != spend["authorized_ceiling_cny"]:
            model_spend.amend_ceiling(project, new_ceiling_cny=new_ceiling_cny,
                                     actor=actor, run_id=run_id, authorization_note=note)
        write(constraints_path, prepared["constraints_after"])
        decision={"kind":"operating_constraints_amendment","actor":actor,"at":timestamp,"note":note,
                  "cloud_review_sha256":review_sha256,"source_run_id":run_id,
                  "amended_fields":["model_api_budget_cny","target_submission_ready_date"],
                  "scientific_approval_granted":False}
        state = copy.deepcopy(prepared["run_before"])
        state.setdefault("history", []).append({"at": timestamp, "event": "owner_operating_constraints_amended",
            "actor": actor, "receipt": receipt.relative_to(project).as_posix(),
            "new_ceiling_cny": new_ceiling_cny, "target_submission_ready_date": target_submission_ready_date,
            "scientific_approval_granted": False, "paid_calls": 0})
        state["updated_at"] = timestamp
        write(state_path, state)
        policy=copy.deepcopy(prepared["continuation_before"])
        if policy is not None:
            policy["constraints_sha256"]=sha(constraints_path)
            write(policy_path,policy)
        write(receipt, {"schema_version": "1.0", **prepared, "actor": actor,
            "cloud_review_sha256": review_sha256, "source_run_id": run_id, "authorization_note": note,
            "created_at": timestamp, "constraints_sha256_after": sha(constraints_path),
            "continuation_after": policy, "spend_after": model_spend.read(project, required=True),
            "operating_decision": decision, "paid_calls": 0,
            "planning_date_is_not_a_completion_guarantee": True})
        record(project, outputs, MODULE)
    except Exception:
        # The serialized owner job persists only a complete control transaction.
        for path, content in originals.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise
    return outputs
