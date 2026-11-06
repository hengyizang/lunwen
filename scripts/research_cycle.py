"""The shared fresh-review lifecycle; transports retain their own write authority."""
from scripts import review_receipts
from scripts.research_artifacts import read
from scripts.research_phase import disposition_stage


def research_decision(project, stage, run_id, *, reviewed=False):
    from scripts.research_notebook import cycle_review, cycle_assessment
    try:
        return cycle_assessment(project, stage, run_id) if reviewed else cycle_review(project, stage, run_id)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "pending", "errors": [str(exc)], "scientific_completion_verified": False}


def review_cycle(project, stage, run_id, *, writer_family, prompt, invoke, remediate,
                 refresh, writer_notes, log):
    """Refresh → initial critic → optional repair → refresh → fresh final critic.

    Adapters perform actual calls and protected writes. Both transports share the
    same source snapshots, receipt sealing, disposition and decision requirements.
    """
    from scripts.api_orchestrator import remediation_required, validate_remediation_notes
    paper = read(project / "state/run.json").get("active_paper") if stage == "writing-and-review" else None
    note_stage = disposition_stage(project, stage)
    result = {"audits": {}, "paths": {}, "evidence": {}, "methods": {}}
    notes = []
    for phase in ("initial", "final"):
        result["evidence"][phase], result["methods"][phase] = refresh(phase)
        from scripts.automated_quality import checked_run
        quality = checked_run(project, stage)
        if quality is not None:
            result["evidence"][phase]["automated_quality"] = quality
        if phase == "final":
            result["decision_before_review"] = research_decision(project, stage, run_id)
        materials = review_receipts.material_snapshot(project, stage, paper)
        request = prompt()
        audit, path, identity = invoke(phase, request)
        result["audits"][phase], result["paths"][phase] = audit, path
        if path:
            review_receipts.seal_phase(project, stage=stage, run_id=run_id, phase=phase,
                audit_path=path, prompt=request, identity=identity, writer_family=writer_family,
                materials=materials, notes=notes if phase == "final" else None, cycle_required=True)
        if phase == "initial":
            notes = writer_notes(audit, note_stage) if callable(writer_notes) else writer_notes
            result["remediation_skipped"] = not remediation_required(audit, note_stage, notes)
            if not result["remediation_skipped"]:
                notes = remediate(audit, path, note_stage)
            notes = validate_remediation_notes({"stage": note_stage, "notes": notes}, audit)
    result["dispositions"] = notes
    initial, final = result["paths"]["initial"], result["paths"]["final"]
    result["decision_log"] = log(initial, final, notes, result["audits"]["final"]) if initial and final else None
    result["research_decision"] = research_decision(project, stage, run_id, reviewed=True)
    return result


def after_reviews(project, stage, run_id, decision, gate_errors):
    """Apply the same bounded follow-ups after both independently sealed reviews."""
    result = {}
    if stage == "writing-and-review":
        from scripts.supplemental_experiments import automatic_approval
        from scripts.research_phase import enter_submission
        result["supplemental_approval"] = automatic_approval(
            project, read(project / "state/run.json")["active_paper"], run_id)
        if not decision.get("errors") and enter_submission(project, gate_errors()):
            result["writing_phase_transition"] = "submission"
    elif stage == "experiment-execution":
        from scripts.primary_recovery import automatic_retirement
        result["primary_recovery"] = automatic_retirement(project, run_id=run_id)
    return result
