"""Incremental question-centred evidence and decision views; never invent evidence."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.research_artifacts import path_in, read, write, bound_source, record

PHASES = {"idea", "planned", "running", "exploratory", "confirmatory", "failed", "stopped"}
STANCES = {"supports", "contradicts", "mixed", "unknown"}


def build(project: Path) -> dict:
    inputs = read(path_in(project, "program/research-notebook.json"))
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
                if not links or not set(links).issubset(evidence_ids):
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
              "resolution_verified": False, "human_scientific_review_required": True}
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
