"""Narrow owner amendments of the cumulative API ceiling and planning date.

This is an authenticated cloud control, never a model operation or a scientific
approval. It is deliberately limited to G1 before any later gate or experiment.
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
        texts = [value[key]] if key == "research_goal" else value[key]
        updated = []
        for text in texts:
            if key == "research_goal":
                if old_date in replacements:
                    text = re.sub(r"\b(before|by)(\s+)" + re.escape(old_date) + r"\b",
                                  lambda match: match.group(1) + match.group(2) + deadline, text)
            elif text.startswith("The requested date is preserved; the planning checkpoint is "):
                for prior, current in replacements.items():
                    text = text.replace(prior, current)
            if key == "notes" and old_budget != ceiling:
                token = f"initial cumulative model API envelope of CNY {old_budget:g}"
                if token in text:
                    text = text.replace(token, f"current cumulative model API envelope of CNY {ceiling}")
                    text = text.replace(
                        "This intake is not a ledger grant; the separate owner cloud authorize_budget job records the first tranche before any paid transport.",
                        "The hash-bound owner operating amendment records this exact cumulative ceiling; no paid transport is started by the amendment.")
                if text.startswith("Spending authorization is cumulative: initial approval for CNY "):
                    text = (f"Spending authorization is cumulative: the current owner-approved ceiling is CNY {ceiling}. "
                            f"A later explicit owner tranche approval may add CNY {model_spend.STEP_CNY}, "
                            f"for example CNY {ceiling + model_spend.STEP_CNY}; no automatic increase is authorized. "
                            "Calls within the approved unused ceiling need no repeated spending approval. "
                            "A larger ceiling must not silently override a separately agreed paper hard limit.")
            updated.append(text)
        value[key] = updated[0] if key == "research_goal" else updated
    return value


def prepare(project: Path, new_ceiling_cny: int, target_submission_ready_date: str, actor: str) -> dict:
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise ValueError("operating amendments require the authenticated cloud controller")
    validate_selectors(new_ceiling_cny, target_submission_ready_date)
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("named owner required for operating amendment")
    state = researchctl.load_state(project.name)
    if (state.get("gate") != "G1" or state.get("status") != "awaiting_work"
            or state.get("approved_gates") != ["G0"]
            or not isinstance(state.get("approvals"), list) or not state["approvals"]
            or any(a.get("gate") != "G0" for a in state["approvals"])):
        raise ValueError("operating amendment is limited to open G1 with only the actual G0 approval")
    if state.get("supplemental_context") is not None:
        raise ValueError("supplemental projects cannot amend parent operating authority")
    registry = path_in(project, "experiments/registry.jsonl", exists=False)
    if registry.exists() and registry.read_text(encoding="utf-8").strip():
        raise ValueError("operating amendment cannot rebind an executed experiment protocol")
    for candidate in (project / "papers").glob("P[0-9][0-9]/preregistration.json"):
        if candidate.is_file() and read(candidate).get("frozen_at"):
            raise ValueError("frozen scientific protocols require their own reviewed amendment route")
    constraints_path = path_in(project, "intake/constraints.json")
    original = read(constraints_path)
    errors = intake_validation.validate_constraints(original)
    if errors or original.get("execution_mode") != "cloud_only":
        raise ValueError("valid owner-approved cloud-only intake required: " + "; ".join(errors))
    policy_path = path_in(project, cloud_continuation.POLICY.as_posix())
    policy = read(policy_path)
    approval = state["approvals"][-1]
    if (set(policy) != cloud_continuation.POLICY_FIELDS or policy.get("schema_version") != "1.0"
            or type(policy.get("enabled")) is not bool or policy.get("actor") != actor
            or approval.get("actor") != actor or policy.get("constraints_sha256") != sha(constraints_path)
            or policy.get("g0_approval_artifact_sha256") != approval.get("artifact_sha256")
            or not re.fullmatch(r"[a-f0-9]{64}", str(approval.get("artifact_sha256")))
            or policy.get("system_execution_hours_per_day") != 24
            or policy.get("resume_interval_minutes") != 15
            or policy.get("stop_when") != "all_papers_submission_ready"):
        raise ValueError("original named G0 and continuation input hashes must still match")
    spend = model_spend.read(project, required=True)
    assert spend is not None
    if new_ceiling_cny < spend["spent_cny"] + model_spend.reserved(spend):
        raise ValueError("amended cumulative ceiling cannot fall below spent and reserved charges")
    if (new_ceiling_cny == spend["authorized_ceiling_cny"]
            and new_ceiling_cny == original["model_api_budget_cny"]
            and target_submission_ready_date == original.get("target_submission_ready_date")):
        raise ValueError("operating amendment must change a current constraint")
    updated = _updated_constraints(original, new_ceiling_cny, target_submission_ready_date)
    if intake_validation.validate_constraints(updated):
        raise ValueError("amended intake must remain valid without weakening scientific constraints")
    return {"constraints_before": original, "constraints_after": updated,
            "constraints_sha256_before": sha(constraints_path), "continuation_before": policy,
            "spend_before": spend, "run_before": state,
            "effect": "exact cumulative API ceiling and planning date only; no paid calls or scientific gate advance",
            "scientific_completion_verified": False}


def apply(project: Path, new_ceiling_cny: int, target_submission_ready_date: str,
          actor: str, review_sha256: str, run_id: str, note: str) -> list[Path]:
    prepared = prepare(project, new_ceiling_cny, target_submission_ready_date, actor)
    if (not re.fullmatch(r"[a-f0-9]{64}", str(review_sha256)) or not re.fullmatch(r"[0-9]+", str(run_id))
            or not isinstance(note, str) or not 10 <= len(note.strip()) <= 500):
        raise ValueError("exact owner dossier hash, numeric cloud run and authorization note required")
    receipt = path_in(project, f"{PREFIX}/{run_id}.json", exists=False)
    if receipt.exists():
        raise ValueError("operating amendment cannot overwrite its prior receipt")
    constraints_path = path_in(project, "intake/constraints.json")
    policy_path = path_in(project, cloud_continuation.POLICY.as_posix())
    state_path = path_in(project, "state/run.json")
    spend_path = path_in(project, model_spend.FILE.as_posix())
    provenance = path_in(project, output_provenance.REGISTRY_RELATIVE.as_posix(), exists=False)
    outputs = [constraints_path, policy_path, state_path, spend_path, receipt]
    originals = {p: p.read_bytes() if p.exists() else None for p in [*outputs, provenance]}
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        spend = prepared["spend_before"]
        if new_ceiling_cny != spend["authorized_ceiling_cny"]:
            model_spend.amend_ceiling(project, new_ceiling_cny=new_ceiling_cny,
                                     actor=actor, run_id=run_id, authorization_note=note)
        write(constraints_path, prepared["constraints_after"])
        # The prior G0 is retained verbatim. This explicit narrow intake decision
        # authorizes only these operating values, never a G1-G5 scientific verdict.
        approval = {"gate": "G0", "kind": "operating_constraints_amendment", "actor": actor,
                    "at": timestamp, "note": note, "artifact_sha256": researchctl.artifact_hash(project.name, "G0"),
                    "prior_g0_artifact_sha256": prepared["run_before"]["approvals"][-1]["artifact_sha256"],
                    "cloud_review_sha256": review_sha256, "source_run_id": run_id,
                    "amended_fields": ["model_api_budget_cny", "target_submission_ready_date"],
                    "scientific_approval_granted": False}
        state = copy.deepcopy(prepared["run_before"])
        state["approvals"].append(approval)
        state.pop("ready_gate", None)
        state.pop("ready_artifact_sha256", None)
        state.setdefault("history", []).append({"at": timestamp, "event": "owner_operating_constraints_amended",
            "actor": actor, "receipt": receipt.relative_to(project).as_posix(),
            "new_ceiling_cny": new_ceiling_cny, "target_submission_ready_date": target_submission_ready_date,
            "scientific_approval_granted": False, "paid_calls": 0})
        state["updated_at"] = timestamp
        write(state_path, state)
        policy = copy.deepcopy(prepared["continuation_before"])
        policy.update(constraints_sha256=sha(constraints_path),
                      g0_approval_artifact_sha256=approval["artifact_sha256"])
        write(policy_path, policy)
        write(receipt, {"schema_version": "1.0", **prepared, "actor": actor,
            "cloud_review_sha256": review_sha256, "source_run_id": run_id, "authorization_note": note,
            "created_at": timestamp, "constraints_sha256_after": sha(constraints_path),
            "continuation_after": policy, "spend_after": model_spend.read(project, required=True),
            "g0_operating_amendment": approval, "paid_calls": 0,
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
