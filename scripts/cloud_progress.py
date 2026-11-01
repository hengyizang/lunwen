"""Record continuation progress; the cumulative ceiling governs model spending."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from scripts import researchctl

FILE = "state/continuation-progress.json"
MAX_CONTROL_CYCLES = 12


def read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def human_inputs(project: Path) -> str:
    # Only owner/control-plane files reset a paused control attempt. Draft
    # timestamps and audit wording do not establish new scientific evidence.
    paths = ["state/run.json", "state/data-authorizations.json", "state/human-inputs.json"]
    return digest({p: read(project / p) for p in paths})


def snapshot(slug: str) -> dict:
    project = researchctl.project_dir(slug)
    state = researchctl.load_state(slug)
    errors = researchctl.gate_errors(slug, state["gate"]) if state["gate"] else []
    errors = sorted(set(re.sub(r"\d{8}T\d+Z", "<run>", str(e).replace(str(project), "<project>")) for e in errors))
    # Successful controlled receipts count; arbitrary manuscript bytes do not.
    receipts = []
    for relative in ("evidence/literature-api-ledger.jsonl", "experiments/registry.jsonl"):
        path = project / relative
        for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
            item = json.loads(line)
            if item.get("status") in {"success", "succeeded"}:
                receipts.append(item.get("response_sha256") or digest(item.get("outputs", [])))
    from scripts import literature_evidence, literature_model_screening
    for item in literature_evidence.read_jsonl(project / "evidence/search-log.jsonl"):
        if str(item.get("screened_by", "")).startswith("model:") and not literature_model_screening.verify(project, item):
            receipts.append(digest({"receipt": item["evidence_receipt_id"], "screened_by": item["screened_by"],
                                    "included": item["included_work_ids"], "excluded": item["exclusion_reasons"]}))
    return {"scope": f"{state['stage']}:{state['active_paper']}", "errors": errors,
            "receipts": sorted(set(receipts)), "human_inputs": human_inputs(project)}


def external_blockers(project: Path, errors: list[str]) -> list[dict]:
    report = read(project / "state/research-steps.json", {})
    automatic_kinds = {"data_rights_evidence", "data_rights_review", "data_quality_confirmation", "reproduction_confirmation", "figure_visual_review", "literature_screening"}
    blockers = [item for item in report.get("blockers", []) if item.get("kind") not in automatic_kinds]
    if any(item.get("kind") in {"experiment_inspection", "experiment_failure_diagnosis"} for item in blockers):
        from scripts.primary_recovery import failure_control_status
        status = failure_control_status(project)
        if status["status"] in {"eligible", "retry_pending"}:
            blockers = [item for item in blockers if item.get("kind") not in {"experiment_inspection", "experiment_failure_diagnosis"}]
    patterns = {
        "jcr_source_required": ("licensed jcr", "jcr verification", "jcr source"),
    }
    for kind, phrases in patterns.items():
        matches = [e for e in errors if any(p in e.casefold() for p in phrases)]
        if matches:
            blockers.append({"kind": kind, "requirements": matches[:8]})
    return blockers


def record(slug: str, before: dict, run_id: str, exit_code: int) -> dict:
    project = researchctl.project_dir(slug)
    after = snapshot(slug)
    old = read(project / FILE, {})
    if old.get("scope") != after["scope"] or old.get("human_inputs") != after["human_inputs"]:
        old = {}
    report = read(project / "state/research-steps.json", {})
    paid = report.get("paid_model_cycle") is True
    reduced = set(after["errors"]) < set(before["errors"])
    evidence_added = bool(set(after["receipts"]) - set(before["receipts"]))
    progressed = reduced or evidence_added
    value = {"schema_version": "1.0", **after, "source_run_id": str(run_id),
             "last_exit_code": exit_code, "model_cycles": old.get("model_cycles", 0) + int(paid),
             "control_cycles": 0 if progressed else old.get("control_cycles", 0) + int(not paid),
             "stalled_cycles": 0 if progressed else old.get("stalled_cycles", 0) + int(paid),
             "semantic_progress": progressed, "external_blockers": external_blockers(project, after["errors"])}
    researchctl.write_json(project / FILE, value)
    return value


def pause_reason(slug: str) -> dict | None:
    project = researchctl.project_dir(slug)
    value = read(project / FILE, {})
    state = researchctl.load_state(slug)
    if (value.get("scope") != f"{state['stage']}:{state['active_paper']}"
            or value.get("human_inputs") != human_inputs(project)):
        return None
    current_errors = researchctl.gate_errors(slug, state["gate"]) if state.get("gate") else []
    current_external = external_blockers(project, current_errors)
    if current_external:
        return {"reason": "external_input_required", "blockers": current_external}
    if value.get("control_cycles", 0) >= MAX_CONTROL_CYCLES:
        return {"reason": "control_retry_limit", "attempts": value["control_cycles"], "limit": MAX_CONTROL_CYCLES}
    return None


def resume(slug: str, expected_sha256: str, actor: str, note: str, run_id: str) -> None:
    """Owner-reviewed repair only; does not grant money or any scientific gate."""
    from scripts.cloud_continuation import STATUS
    project = researchctl.project_dir(slug)
    status = project / STATUS
    if (not status.is_file() or hashlib.sha256(status.read_bytes()).hexdigest() != expected_sha256
            or not actor.strip() or not 10 <= len(note.strip()) <= 500):
        raise ValueError("resume requires the exact reviewed status hash, actor and repair note")
    history = project / "state/continuation-resumes.jsonl"
    event = {"actor": actor, "note": note, "run_id": str(run_id), "status_sha256": expected_sha256,
             "previous_status": read(status), "previous_progress": read(project / FILE)}
    with history.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    researchctl.write_json(status, {"schema_version": "1.0", "last_cycle_exit_code": 0,
                                   "reason": "owner_inspected_repair", "source_run_id": str(run_id)})
    (project / FILE).unlink(missing_ok=True)
