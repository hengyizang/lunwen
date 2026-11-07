"""Incremental question-centred evidence and decision views; never invent evidence."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.research_artifacts import path_in, read, write, bound_source, record, sha

PHASES = {"idea", "planned", "running", "exploratory", "confirmatory", "failed", "stopped"}
STANCES = {"supports", "contradicts", "mixed", "unknown"}
CYCLE_OUTCOMES = {"pending", "unchanged", "changed", "failed", "stopped"}
NOTEBOOK = "program/research-notebook.json"


def failed_memory(project: Path, spec: dict) -> dict:
    """Reuse original failed/stopped decisions as leads, never as new evidence."""
    if not isinstance(spec, dict) or set(spec) - {"schema_version", "id", "question"} or spec.get("schema_version") != "1.0":
        raise ValueError("unsupported research-memory request")
    from scripts.literature_workbench import _id
    report = build(project)
    if report["errors"]:
        raise ValueError("research memory source is invalid: " + "; ".join(report["errors"]))
    entries = []
    for question in report["questions"]:
        evidence = {r["id"]: r for r in question["evidence"]}
        for decision in question["decisions"]:
            if decision.get("outcome") not in {"failed", "stopped"} and decision.get("phase") not in {"failed", "stopped"}:
                continue
            sources, missing = [], []
            for key in decision.get("evidence_ids", []):
                item = evidence[key]
                relative = item["source"]["path"]
                if relative == NOTEBOOK or relative.startswith(("state/", "reviews/", "reports/", "program/")):
                    missing.append("Memory/control/generated summaries cannot support a scientific assertion: " + relative)
                    continue
                from scripts.output_provenance import current_origin
                origin = current_origin(project, path_in(project, relative))
                if origin.get("status") != "tracked" or origin.get("provider") not in {"deterministic-control-plane", "human-attestation"}:
                    missing.append("Model-authored or untracked memory needs original source evidence: " + relative)
                    continue
                sources.append(item)
            entries.append({"question_id": question["id"], "question": question["question"], "decision": decision,
                "original_evidence": sources, "missing_evidence": missing,
                "reuse_as": "prior_attempt_lead_not_scientific_fact", "interpretation_verified": False})
    return {"schema_version": "1.0", "operation": "research_memory", "id": _id(spec.get("id")),
        "question": spec.get("question"), "notebook": {"path": NOTEBOOK, "sha256": sha(path_in(project, NOTEBOOK))},
        "failed_or_stopped_ideas": entries, "model_call_made": False, "scientific_completion_verified": False,
        "role_contract": "Inspect relevant prior failed/stopped ideas before proposing a repeat. Keep the original question, failure, contrary evidence and revisit condition. Memory is a search lead: reopen the original sources and never cite model summaries or earlier model agreement as independent scientific support."}


def build(project: Path) -> dict:
    inputs = read(path_in(project, NOTEBOOK))
    questions, errors, seen = [], [], set()
    for question in inputs.get("questions", []):
        try:
            identifier = question["id"]
            if identifier in seen or not identifier or not question.get("question"):
                raise ValueError("question needs a unique ID and text")
            seen.add(identifier)
            evidence, evidence_ids, decisions = [], set(), []
            for entry in question.get("evidence", []):
                if entry.get("id") in evidence_ids or not entry.get("id") or entry.get("stance") not in STANCES:
                    raise ValueError("evidence needs a unique ID and an explicit stance")
                evidence_ids.add(entry["id"])
                source = bound_source(project, entry["source"])
                if not entry.get("observation") or entry.get("read_scope") not in {"metadata", "abstract", "fulltext", "experiment"}:
                    raise ValueError("evidence needs an observation and honest reading scope")
                evidence.append({**entry, "source": source, "interpretation_verified": False})
            decision_ids = set()
            missing = question.get("missing_evidence", [])
            if not isinstance(missing, list) or any(not isinstance(item, str) or not item.strip() for item in missing):
                raise ValueError("missing_evidence must be an array of explicit text gaps")
            for decision in question.get("decisions", []):
                decision_id = decision.get("id")
                if decision_id is not None and (not isinstance(decision_id, str) or not decision_id or decision_id in decision_ids):
                    raise ValueError("decision IDs must be nonempty and unique within a question")
                decision_ids.add(decision_id)
                if decision.get("phase") not in PHASES or not decision.get("decision") or not decision.get("rationale"):
                    raise ValueError("decision needs phase, rationale and decision text")
                links = decision.get("evidence_ids", [])
                honest_pending = decision.get("cycle_id") and decision.get("outcome") in {"pending", "unchanged"} and missing
                if (not isinstance(links, list) or len(links) != len(set(links))
                        or (not links and not honest_pending) or not set(links).issubset(evidence_ids)):
                    raise ValueError("decision must link actual evidence, including contrary evidence where present")
                contrary = {e["id"] for e in evidence if e["stance"] in {"contradicts", "mixed"}}
                if contrary - set(links) and not decision.get("contrary_evidence_rationale"):
                    raise ValueError("omitted contrary evidence needs an explicit rationale")
                if not decision.get("failure_condition") or not decision.get("stop_rule"):
                    raise ValueError("decision needs a failure condition and stop rule")
                decisions.append(decision)
            questions.append({"id": identifier, "question": question["question"], "evidence": evidence,
                              "conflict_present": any(e["stance"] in {"contradicts", "mixed"} for e in evidence),
                              "decisions": decisions, "missing_evidence": question.get("missing_evidence", [])})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    fingerprint = hashlib.sha256(json.dumps({"inputs": inputs, "questions": questions}, sort_keys=True).encode()).hexdigest()
    return {"schema_version": "1.0", "input_fingerprint": fingerprint, "questions": questions,
            "status": "needs_scientific_review" if not errors else "blocked", "errors": errors,
            "gate_approved": False, "scientific_completion_verified": False}


def cycle_prompt(run_id: str) -> str:
    """One decision in the existing notebook, including an honest pending result."""
    return ("RESEARCH CYCLE DECISION: Update program/research-notebook.json; preserve existing questions, evidence and decisions. "
        "Append a decision under the most consequential question, with id, cycle_id=" + json.dumps(str(run_id)) +
        ", stage=current state.stage, paper_id=current active paper for G3-G5, phase, outcome "
        "(pending|unchanged|changed|failed|stopped), discriminating_test, decision, rationale, next_action, "
        "evidence_ids, failure_condition and stop_rule. The question states the unknown; discriminating_test explains "
        "which observation separates the competing explanations; decision states its effect on the method or claim. "
        "Reuse question evidence entries (id, stance, observation, read_scope, source:{path,sha256,locator}) and reference "
        "their actual IDs. A pending/unchanged decision may have no evidence only with explicit question.missing_evidence "
        "and next_action; never invent a result to fill this record. Include contrary/mixed evidence or explain its disposition. "
        "No new report, extra model role or claimed scientific improvement is required.")


def cycle_review(project: Path, stage: str, run_id: str, *, paper_id: str | None = None) -> dict:
    """Validate a current-cycle research decision; independent critics assess its meaning."""
    from scripts.scientific_reasoning import STAGES, concrete
    if stage not in STAGES:
        return {"status": "not_applicable", "decisions": []}
    report = build(project)
    if report["errors"]:
        raise ValueError("research cycle decision: " + "; ".join(report["errors"]))
    state_path = project / "state/run.json"
    state = read(state_path) if state_path.is_file() else {}
    decisions = []
    for question in report["questions"]:
        evidence = {row["id"]: row for row in question["evidence"]}
        for decision in question["decisions"]:
            if decision.get("cycle_id") != str(run_id):
                continue
            concrete(question["question"], "cycle research question")
            for key in ("id", "discriminating_test", "decision", "rationale", "next_action", "failure_condition", "stop_rule"):
                concrete(decision.get(key), "cycle decision." + key)
            if decision.get("stage") != stage or decision.get("outcome") not in CYCLE_OUTCOMES:
                raise ValueError("cycle decision must identify its actual stage and honest outcome")
            if stage in {"experiment-design", "experiment-execution", "writing-and-review"} and decision.get("paper_id") != (paper_id or state.get("active_paper")):
                raise ValueError("cycle decision must belong to the current paper")
            sources = [evidence[key]["source"] for key in decision["evidence_ids"]]
            if any(source["path"] == NOTEBOOK or source["path"].startswith(("state/", "reviews/", "reports/research-notebook"))
                   for source in sources):
                raise ValueError("a decision must cite scientific evidence, not its own notebook or control receipts")
            decisions.append({"question_id": question["id"], "question": question["question"],
                **decision, "sources": sources, "missing_evidence": question["missing_evidence"]})
    if not decisions:
        raise ValueError("this research cycle needs an unknown, discriminating test and source-bound or explicitly pending notebook decision")
    if len({row["id"] for row in decisions}) != len(decisions):
        raise ValueError("cycle decision IDs must be unique across questions")
    return {"status": "recorded_requires_independent_review", "cycle_id": str(run_id), "decisions": decisions,
            "notebook": {"path": NOTEBOOK, "sha256": sha(path_in(project, NOTEBOOK))},
            "scientific_completion_verified": False}


def cycle_assessment(project: Path, stage: str, run_id: str | None = None, *, paper_id: str | None = None) -> dict:
    """Expose the actual decision/evidence/critic chain without certifying scientific validity."""
    try:
        from scripts.scientific_reasoning import STAGES
        if stage not in STAGES:
            return {"status": "not_applicable", "decisions": []}
        from scripts import review_receipts
        state = read(project / "state/run.json")
        gate = next(gate for gate, name in review_receipts.STAGES.items() if name == stage)
        from scripts.paper_execution import enabled
        paper = (paper_id or state.get("active_paper")) if gate == "G5" or (enabled(project) and gate in {"G3", "G4"}) else None
        from scripts.research_phase import requires_submission
        from scripts import review_panel
        panel_pointer = project / review_panel.PREFIX / str(paper) / "latest.json"
        if gate == "G5" and requires_submission(project, stage, paper) and panel_pointer.exists():
            responses = review_panel.responses(project, paper)
            actual_run = responses[0]["receipt"]["run_id"]
            result = cycle_review(project, stage, str(run_id) if run_id is not None else actual_run, paper_id=paper_id)
            result.update(status="recorded_with_limited_panel_observations", panel_review=read(panel_pointer),
                assessment_scope="selected_panel_sources_only_not_notebook_decision_validation",
                current_stage_authorized=False, gate_authority=False,
                review_errors=[], independent_review=None)
            return result
        observed = project / review_receipts.PREFIX / review_receipts._key(gate, paper) / "observation-latest.json"
        if observed.is_file():
            actual = review_receipts.observation(project, stage, paper)
            receipt = actual["receipt"]
            run_id = str(run_id) if run_id is not None else receipt["run_id"]
            if receipt["run_id"] != run_id:
                raise ValueError("the latest observation belongs to a different research cycle")
            result = cycle_review(project, stage, run_id, paper_id=paper_id)
            if result["notebook"] not in receipt["materials"]["files"]:
                raise ValueError("the actual observation did not bind this research notebook")
            for source in receipt["materials"]["files"]:
                if sha(path_in(project, source["path"])) != source["sha256"]:
                    raise ValueError("observed scientific source changed: " + source["path"])
            result.update(status="independently_observed", independent_review=actual["pointer"],
                review_errors=[], current_stage_authorized=False, assessment_scope="reviewed_sources_only")
            return result
        latest = project / review_receipts.PREFIX / review_receipts._key(gate, paper) / "latest.json"
        pointer = read(latest)
        receipt = read(path_in(project, pointer["path"]))
        run_id = str(run_id) if run_id is not None else receipt.get("run_id")
        result = cycle_review(project, stage, run_id, paper_id=paper_id)
        purpose = receipt.get("materials", {}).get("review_purpose", "stage")
        issues = review_receipts.validate_gate(project, gate, paper, expected_purpose=purpose)
        if receipt.get("run_id") != str(run_id):
            issues.append("the latest critic did not assess this research cycle")
        current = result["notebook"]
        if current not in receipt.get("materials", {}).get("files", []):
            issues.append("the actual final critic did not bind the current research notebook")
        historical = None
        if issues == ["source-bound independent review: independent final review is stale for current scientific inputs"]:
            historical = _historical_assessment(project, latest, pointer, receipt)
            if historical:
                issues = []
        result.update(status="independently_reviewed" if not issues else "awaiting_independent_review",
                      independent_review=pointer if not issues else None, review_errors=issues)
        if historical:
            result.update(status="historically_reviewed", assessment_scope=historical, current_stage_authorized=False)
        return result
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        return {"status": "pending", "decisions": [], "errors": [str(exc)], "scientific_completion_verified": False}


def _historical_assessment(project, latest, pointer, final):
    """Read past scientific work after a controller transition; grant no gate authority."""
    from scripts import review_receipts, research_phase
    from scripts.researchctl import audit_document_valid
    from scripts.api_orchestrator import validate_remediation_notes
    state = read(project / "state/run.json")
    paper, purpose = final.get("paper_id"), final["materials"].get("review_purpose", "stage")
    mapping, scope = {}, None
    if (final.get("gate") == "G5" and purpose == "scientific_writing"
            and research_phase.writing_phase(project, paper) == "submission"
            and any(row.get("event") == "submission_preparation_started" and row.get("paper_id") == paper
                    for row in state.get("history", []))):
        scope = "completed_scientific_writing"
    elif final.get("gate") == "G4":
        reviewed = {row["path"]: row["sha256"] for row in final["materials"]["files"]}
        for archive in research_phase.histories(project, paper):
            plan = next(row for row in archive["files"] if row["archive_path"] == archive["plan_path"])
            if reviewed.get(plan["source"]) == plan["sha256"]:
                mapping = {row["source"]: row["archive_path"] for row in archive["files"]}
                scope = "archived_exploration"
                break
    if scope is None:
        return None
    for row in final["materials"]["files"]:
        if sha(path_in(project, mapping.get(row["path"], row["path"]))) != row["sha256"]:
            raise ValueError("historically reviewed scientific source changed: " + row["path"])
    review_receipts._owned(project, latest)
    target = path_in(project, pointer["path"])
    review_receipts._owned(project, target)
    if sha(target) != pointer["sha256"]:
        raise ValueError("historical final receipt pointer changed")
    initial_path = path_in(project, final["initial"]["path"])
    review_receipts._owned(project, initial_path)
    initial = read(initial_path)
    if (sha(initial_path) != final["initial"]["sha256"] or initial.get("phase") != "initial"
            or final.get("phase") != "final" or initial["materials"].get("review_purpose", "stage") != purpose
            or any(initial.get(key) != final.get(key) for key in ("gate", "stage", "paper_id", "run_id", "cycle_required"))):
        raise ValueError("historical review needs its unchanged matching initial and final invocations")
    errors, audits = [], []
    for receipt in (initial, final):
        review_receipts._identity(receipt["identity"], receipt["writer_family"])
        audit_path = path_in(project, receipt["audit"]["path"])
        review_receipts._owned(project, audit_path)
        if sha(audit_path) != receipt["audit"]["sha256"]:
            raise ValueError("historical independent audit changed")
        audit = read(audit_path); audits.append(audit)
        audit_document_valid(audit_path, audit, errors, final=receipt["phase"] == "final")
    validate_remediation_notes({"notes": final["dispositions"],
        "stage": "scientific-writing" if purpose == "scientific_writing" else final["stage"]}, audits[0])
    if errors or any(note.strip().lower().startswith("unresolved:") for note in final["dispositions"]):
        raise ValueError("historical scientific review has unresolved findings")
    return scope


def _delta(before: dict, after: dict) -> dict:
    changes = {name: [] for name in ("questions_added", "questions_changed", "questions_removed",
        "evidence_added", "evidence_changed", "evidence_removed", "decisions_added", "decisions_changed",
        "decisions_removed", "missing_added", "missing_removed", "conflicts_new", "conflicts_cleared_for_review")}
    left = {q["id"]: q for q in before.get("questions", [])}
    right = {q["id"]: q for q in after.get("questions", [])}
    for identifier in sorted(set(left) | set(right)):
        old, new = left.get(identifier, {}), right.get(identifier, {})
        if not old:
            changes["questions_added"].append(identifier)
        elif not new:
            changes["questions_removed"].append(identifier)
        elif old.get("question") != new.get("question"):
            changes["questions_changed"].append(identifier)
        for kind, field in (("evidence", "evidence"), ("decisions", "decisions")):
            def indexed(value):
                return {str(row.get("id") or f"position-{i + 1}"): row
                        for i, row in enumerate(value.get(field, []))}
            a, b = indexed(old), indexed(new)
            for key in sorted(set(a) | set(b)):
                tag = "added" if key not in a else "removed" if key not in b else "changed"
                if tag != "changed" or a[key] != b[key]:
                    changes[f"{kind}_{tag}"].append({"question_id": identifier, "id": key})
        a, b = set(old.get("missing_evidence", [])), set(new.get("missing_evidence", []))
        changes["missing_added"].extend({"question_id": identifier, "item": item} for item in sorted(b - a))
        changes["missing_removed"].extend({"question_id": identifier, "item": item,
            "status": "resolution_requires_review"} for item in sorted(a - b))
        if new.get("conflict_present") and not old.get("conflict_present"):
            changes["conflicts_new"].append(identifier)
        elif old.get("conflict_present") and not new.get("conflict_present"):
            changes["conflicts_cleared_for_review"].append(identifier)
    return changes


def daily_brief(project: Path, *, at: datetime | None = None, timezone_name: str = "Asia/Shanghai") -> dict:
    clock = at or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError("notebook event time needs a timezone")
    zone = ZoneInfo(timezone_name)
    day = clock.astimezone(zone).date().isoformat()
    journal = project / "reports/research-notebook-history.jsonl"
    events, undated = [], 0
    if journal.is_file():
        for line in journal.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if not isinstance(entry, dict):
                raise ValueError("notebook history entry is malformed")
            if not entry.get("recorded_at"):
                undated += 1
                continue
            stamp = datetime.fromisoformat(entry["recorded_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("history timestamps must include a timezone")
            if stamp.astimezone(zone).date().isoformat() == day:
                events.append(entry)
    combined = {}
    for event in events:
        for field, rows in event.get("changes", {}).items():
            combined.setdefault(field, []).extend(rows)
    result = {"schema_version": "1.0", "day": day, "timezone": timezone_name,
              "event_ids": [e["event_id"] for e in events], "event_count": len(events),
              "changes": combined, "undated_legacy_snapshots": undated,
              "failed_refreshes": [e["event_id"] for e in events if e.get("snapshot", {}).get("status") == "blocked"],
              "resolution_verified": False, "independent_scientific_review_required": True}
    directory = project / "reports/research-notebook-daily"
    output, summary = directory / f"{day}.json", directory / f"{day}.md"
    changed = not output.is_file() or read(output) != result
    if changed:
        write(output, result)
        lines = [f"# Research changes: {day} ({timezone_name})", "",
                 "Removed evidence or a cleared conflict is not proof of resolution. Review all dispositions.",
                 f"Events: {len(events)}; undated legacy snapshots: {undated}.", ""]
        for field, rows in combined.items():
            if rows:
                lines.extend([f"## {field}", *["- " + json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows], ""])
        if result["failed_refreshes"]:
            lines.append("Blocked refreshes: " + ", ".join(result["failed_refreshes"]))
        summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        record(project, [output, summary], "scripts/research_notebook.py")
    return {**result, "changed": changed, "path": output.relative_to(project).as_posix()}


def refresh(project: Path, *, at: datetime | None = None, timezone_name: str = "Asia/Shanghai") -> dict:
    clock = at or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError("notebook event time needs a timezone")
    result = build(project)
    output = project / "reports/research-notebook.json"
    previous = read(output) if output.is_file() else {}
    if previous == result:
        return {**result, "changed": False, "daily_brief": daily_brief(project, at=clock, timezone_name=timezone_name)}
    write(output, result)
    journal = project / "reports/research-notebook-history.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        stamp = clock.astimezone(timezone.utc).isoformat()
        event = {"schema_version": "2.0", "recorded_at": stamp, "snapshot": result,
                 "previous_fingerprint": previous.get("input_fingerprint"), "changes": _delta(previous, result)}
        event["event_id"] = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    text = ["# Research evidence and decisions", "", "Interpretations require scientific review; no gate is approved here.", ""]
    for question in result["questions"]:
        text.extend([f"## {question['id']}: {question['question']}", ""])
        for e in question["evidence"]:
            text.append(f"- {e['id']} [{e['stance']}; {e['read_scope']}]: {e['observation']} — {e['source']['path']} ({e['source']['locator']})")
        for d in question["decisions"]:
            text.append(f"- Decision [{d['phase']}]: {d['decision']} | reason: {d['rationale']} | fail: {d['failure_condition']} | stop: {d['stop_rule']}")
        text.append("")
    summary = project / "reports/research-notebook.md"
    summary.write_text("\n".join(text), encoding="utf-8")
    record(project, [output, journal, summary], "scripts/research_notebook.py")
    return {**result, "changed": True, "daily_brief": daily_brief(project, at=clock, timezone_name=timezone_name)}
