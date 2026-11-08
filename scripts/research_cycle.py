"""Administrative intake or one ordinary critique; actual findings alone trigger repair."""
from scripts import review_receipts
from scripts.research_artifacts import read
from scripts.research_phase import disposition_stage


def research_decision(project, stage, run_id, *, reviewed=False):
    from scripts.research_notebook import cycle_review, cycle_assessment
    try:
        return cycle_assessment(project, stage, run_id) if reviewed else cycle_review(project, stage, run_id)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "pending", "errors": [str(exc)], "scientific_completion_verified": False}


def decision_errors(decision):
    """Use both the notebook and its actual independent assessment in adapters."""
    return ["research decision: " + issue for issue in dict.fromkeys(
        [*decision.get("errors", []), *decision.get("review_errors", [])])]


def requires_critic(stage):
    return stage != "intake"


def skipped_remediation(reviews):
    """Keep both adapters' no-call records honest about why review was skipped."""
    status, reason = {
        "administrative_intake": ("not_applicable", "Administrative intake uses planner and writer; no scientific critique or approval was performed."),
        "scientific_review": ("not_required", "No actionable initial findings; writer notes retained."),
        "three_blind_submission_views": ("panel_observations_recorded", "Read frozen panel concerns and retain source-bound author responses; scientific validity is not established."),
    }[reviews["review_mode"]]
    return {"status": status, "reason": reason, "model_call_made": False, "final_independent_review_required": False}


def review_cycle(project, stage, run_id, *, writer_family, prompt, invoke, remediate,
                 refresh, writer_notes, log):
    """Planner/writer run in adapters; intake needs no scientific critic.

    Adapters perform actual calls and protected writes. A material finding may justify repair and fresh re-review. Ordinary observations
    retain evidence and dissent but do not manufacture a second invocation or gate.
    """
    result = {"audits": {}, "paths": {}, "evidence": {}, "methods": {}, "review_mode": "scientific_review"}
    if not requires_critic(stage):
        result["evidence"]["initial"], result["methods"]["initial"] = refresh("initial")
        return {**result, "review_mode": "administrative_intake", "research_decision": research_decision(project, stage, run_id),
                "decision_log": None, "dispositions": [], "remediation_skipped": True}
    from scripts.api_orchestrator import remediation_required, validate_remediation_notes
    paper = read(project / "state/run.json").get("active_paper") if stage == "writing-and-review" else None
    note_stage = disposition_stage(project, stage)
    if stage in review_receipts.STAGES.values():
        import re
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", run_id):
            raise ValueError("safe actual review invocation ID required")
        review_receipts._cloud()
        # Reserve before any actual reviewer call, including calls that fail to
        # return parseable output. Replaying this ID never retries paid work.
        from scripts.research_artifacts import path_in, write, record
        gate = next(g for g, name in review_receipts.STAGES.items() if name == stage)
        state = read(project / "state/run.json")
        from scripts.paper_execution import enabled
        scoped = state.get("active_paper") if gate == "G5" or (enabled(project) and gate in {"G3", "G4"}) else None
        attempt = path_in(project, f"{review_receipts.PREFIX}/{review_receipts._key(gate, scoped)}/{run_id}/attempt.json", exists=False)
        attempt.parent.mkdir(parents=True, exist_ok=False)
        write(attempt, {"run_id":run_id, "stage":stage, "status":"started", "scientific_completion_verified":False})
        record(project, [attempt], review_receipts.MODULE)
    notes = []
    for phase in ("initial", "final"):
        result["evidence"][phase], result["methods"][phase] = refresh(phase)
        from scripts.automated_quality import checked_run
        quality = checked_run(project, stage)
        if quality is not None:
            result["evidence"][phase]["automated_quality"] = quality
        result["decision_before_review"] = research_decision(project, stage, run_id)
        materials = review_receipts.material_snapshot(project, stage, paper)
        request = prompt()
        audit, path, identity = invoke(phase, request)
        result["audits"][phase], result["paths"][phase] = audit, path
        if phase == "initial":
            notes = writer_notes(audit, note_stage) if callable(writer_notes) else writer_notes
            result["remediation_skipped"] = not remediation_required(audit, note_stage, notes)
        protocol_review = materials.get("review_purpose") == "supplemental_protocol"
        seal_phase = "observation" if phase == "initial" and result["remediation_skipped"] and not protocol_review else phase
        if path:
            review_receipts.seal_phase(project, stage=stage, run_id=run_id, phase=seal_phase,
                audit_path=path, prompt=request, identity=identity, writer_family=writer_family,
                materials=materials, notes=notes if seal_phase in {"final", "observation"} else None, cycle_required=True)
        if phase == "initial":
            if result["remediation_skipped"]:
                if not protocol_review:
                    break
                # An existing supplemental execution protocol still needs its
                # two actual authority receipts, even when no repair is needed.
                continue
            notes = remediate(audit, path, note_stage)
            notes = validate_remediation_notes({"stage": note_stage, "notes": notes}, audit)
        elif path:
            review_receipts.seal_phase(project, stage=stage, run_id=run_id, phase="observation",
                audit_path=path, prompt=request, identity=identity, writer_family=writer_family,
                materials=materials, notes=notes, cycle_required=True)
    result["dispositions"] = notes
    initial, final = result["paths"].get("initial"), result["paths"].get("final")
    result["decision_log"] = log(initial if final else None, final or initial, notes,
        result["audits"].get("final", result["audits"]["initial"])) if initial else None
    result["research_decision"] = research_decision(project, stage, run_id, reviewed=True)
    return result


def submission_cycle(project, run_id, *, writer_family, refresh):
    """The final checkpoint replaces the ordinary critic with three blind views."""
    from scripts import review_panel
    paper = read(project / "state/run.json")["active_paper"]
    evidence, methods = refresh("initial")
    decision = research_decision(project, "writing-and-review", run_id)
    panel = review_panel.run(project, paper, run_id, writer_family=writer_family)
    final_evidence, final_methods = refresh("panel")
    return {"panel": panel, "review_mode": "three_blind_submission_views", "audits": {}, "paths": {}, "decision_log": None,
        "evidence": {"initial": evidence, "final": final_evidence},
        "methods": {"initial": methods, "panel": final_methods}, "remediation_skipped": True,
        "decision_before_review": decision, "research_decision": {**decision,
            "assessment_scope": "notebook_record_only_panel_judgments_cover_their_declared_sources",
            "current_stage_authorized": False, "scientific_completion_verified": False}}


def after_reviews(project, stage, run_id, decision, gate_errors):
    """Apply bounded follow-ups without treating advisory opinions as approval."""
    result = {}
    if decision_errors(decision):
        return result
    if stage == "writing-and-review":
        from scripts.supplemental_experiments import automatic_approval
        from scripts.research_phase import enter_submission
        result["supplemental_approval"] = automatic_approval(
            project, read(project / "state/run.json")["active_paper"], run_id)
        if enter_submission(project, gate_errors()):
            result["writing_phase_transition"] = "submission"
    elif stage == "experiment-execution":
        from scripts.primary_recovery import automatic_retirement
        result["primary_recovery"] = automatic_retirement(project, run_id=run_id)
    return result
